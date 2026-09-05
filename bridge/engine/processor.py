"""Vòng xử lý sự kiện và luồng mở lệnh (plan mục 6.1–6.6).

Đây là nơi Bridge bắt đầu **tự quyết định**. Trước phase này nó chỉ là đường ống.

Ba nguyên tắc chi phối toàn bộ file:

* **Mỗi lý do bỏ qua phải ghi log rõ ràng.** "Không copy" mà không biết vì sao là tình huống
  tệ nhất khi vận hành, tệ hơn cả copy sai.
* **Tạo pair và tạo command nằm trong ĐÚNG MỘT giao dịch DB**, rồi mới gửi qua socket. Sổ sách
  không bao giờ được đi sau thực tế.
* **Không tự động thử lại sau timeout** (D-13). Không biết lệnh đã khớp hay chưa mà mở thêm là
  hành động tăng rủi ro. Để đối chiếu ở phase 8 dọn.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3
from typing import Any

from bridge.clock import parse_iso, utc_now, utc_now_iso
from bridge.db.repo import Database
from bridge.engine.closing import CloseFlow
from bridge.engine.reconcile import Reconciler
from bridge.engine.sizing import (
    SizingInputs,
    compute_client_volume,
    inherit,
    resolve_direction,
)
from bridge.logging_setup import get_logger
from bridge.protocol.dispatcher import CommandDispatcher, new_command_id
from bridge.protocol.server import BridgeServer

log = get_logger(__name__)

SUCCESS_RETCODE = 10009

#: Lỗi tạm thời: thử lại có ý nghĩa (bảng ở plan mục 5.3).
RETRY_RETCODES = frozenset({10004, 10006, 10018, 10021, 10031})

#: Lỗi phải DỪNG HẲN. Retry một lệnh thiếu margin 50 lần chỉ làm chậm hệ thống và che mất
#: cảnh báo thật. Nhóm "dừng" quan trọng ngang nhóm "retry".
STOP_RETCODES = frozenset({10013, 10014, 10015, 10019, 10030})

#: Hạn tối thiểu cho một command. Hàng rào hạn lệnh phía EA có độ phân giải một giây và sai về
#: phía từ chối (phát hiện ở phase 5), nên hạn quá ngắn sẽ bị EA từ chối oan.
MIN_DEADLINE_MS = 2000

DEFAULT_POLL_INTERVAL_SEC = 0.1
DEFAULT_DEADLINE_SCAN_SEC = 1.0

#: `DEAL_REASON_CLIENT`. Mục tiêu của đường mở lệnh qua giao diện (D-21).
DEAL_REASON_CLIENT = 0

#: Tiền tố thẻ tương quan. Thẻ suy được từ `command_id` nên không cần cột riêng để tra ngược.
TAG_PREFIX = "CB"
TAG_ID_CHARS = 10


def open_tag_for(command_id: str) -> str:
    """Thẻ tương quan của một lệnh mở qua giao diện.

    Ngắn (12 ký tự) để chịu được việc sàn cắt — giới hạn comment của MT5 là 31 ký tự.
    """
    return TAG_PREFIX + command_id[-TAG_ID_CHARS:]


class EventProcessor:
    """Task nền: lấy event `PENDING` theo thứ tự `id` và xử lý tuần tự."""

    def __init__(self, db: Database, server: BridgeServer, dispatcher: CommandDispatcher,
                 poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC,
                 deadline_scan_sec: float = DEFAULT_DEADLINE_SCAN_SEC) -> None:
        self.db = db
        self.server = server
        self.dispatcher = dispatcher
        self.poll_interval_sec = poll_interval_sec
        self.deadline_scan_sec = deadline_scan_sec
        self._task: asyncio.Task[None] | None = None
        self._retry_tasks: set[asyncio.Task[None]] = set()
        #: Đã chạy đóng khẩn cấp cho lần vào `EMERGENCY` này chưa. Đặt lại khi rời chế độ,
        #: để lần vào `EMERGENCY` sau vẫn chạy — nhưng không lặp lại mỗi vòng quét.
        self._emergency_done = False
        #: Cặp vừa tương quan xong nhưng Master đã đóng từ trước — phải đóng ngay (plan 7.4b).
        #: Xếp hàng thay vì gọi thẳng, để việc đóng nằm ngoài giao dịch DB của bước ghép.
        self._deferred_close: list[str] = []
        #: Toàn bộ ngữ nghĩa đóng lệnh (phase 7). Processor chỉ định tuyến vào đây.
        self.closing = CloseFlow(db, dispatcher, self._alert, server)
        #: Đối chiếu ba nguồn (phase 8).
        self.reconciler = Reconciler(db, server, dispatcher, self.closing, self._alert)
        self._last_reconcile = 0.0
        self._reconcile_task: asyncio.Task[None] | None = None

        # Đối chiếu khi agent nối lại (plan 8.4). Nối vào sau `CommandDispatcher` chứ không
        # thay nó: dispatcher cần chạy trước để gửi bù command tồn đọng.
        truoc = server.on_agent_online

        async def sau_khi_agent_online(agent_id: str) -> None:
            if truoc is not None:
                await truoc(agent_id)
            self.schedule_reconcile("AGENT_ONLINE")

        server.on_agent_online = sau_khi_agent_online

        server.on_command_acked = self.on_command_acked
        dispatcher.on_timeout = self.on_command_timeout

    # -- vòng đời --------------------------------------------------------------------------

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def schedule_reconcile(self, trigger: str) -> None:
        """Xếp một vòng đối chiếu chạy nền.

        Không chạy thẳng trong đường bắt tay: đối chiếu phải chờ snapshot của **tất cả** agent,
        mất vài giây, và giữ đường bắt tay lâu như vậy sẽ làm agent tưởng Bridge treo. Cũng gộp
        nhiều lời gọi liên tiếp thành một — ba agent nối lại cùng lúc chỉ cần một vòng.
        """
        if self._reconcile_task is not None and not self._reconcile_task.done():
            return
        self._reconcile_task = asyncio.create_task(self._chay_doi_chieu(trigger))

    async def _chay_doi_chieu(self, trigger: str) -> None:
        """Chờ Master lên rồi mới đối chiếu.

        Agent nào nối trước cũng kích hoạt, mà Client thường nối trước Master. Chạy ngay lúc đó
        thì không có snapshot Master, vòng đối chiếu vô ích và để lại một alert
        `RECONCILE_NO_SNAPSHOT` báo giả — thứ làm người vận hành quen với việc bỏ qua alert.
        """
        het = asyncio.get_running_loop().time() + 15.0
        while asyncio.get_running_loop().time() < het:
            await asyncio.sleep(0.5)
            master = self.db.query_one("SELECT status FROM agent WHERE role = 'MASTER' LIMIT 1")
            if master is not None and master["status"] == "ONLINE":
                break
        else:
            log.info("Bo qua vong doi chieu %s: Master chua len sau 15s", trigger)
            return
        try:
            await self.reconciler.run(trigger)
        except Exception:
            log.exception("Loi trong vong doi chieu")
        self._last_reconcile = asyncio.get_running_loop().time()

    async def stop(self) -> None:
        await self.closing.stop()
        for task in (self._task, self._reconcile_task, *self._retry_tasks):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._retry_tasks.clear()
        self._task = None

    async def _loop(self) -> None:
        last_scan = 0.0
        while True:
            try:
                processed = await self.process_pending()
                now = asyncio.get_running_loop().time()
                if now - last_scan >= self.deadline_scan_sec:
                    self.dispatcher.scan_deadlines()
                    self.scan_correlation_deadlines()
                    await self.check_emergency()
                    await self.check_reconcile(now)
                    last_scan = now
                if not processed:
                    await asyncio.sleep(self.poll_interval_sec)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Loi trong vong xu ly su kien")
                await asyncio.sleep(self.poll_interval_sec)

    # -- xử lý event -----------------------------------------------------------------------

    async def process_pending(self, limit: int = 50) -> int:
        """Xử lý các event `PENDING` đang chờ. Trả về số event đã xử lý.

        Xử lý **tuần tự** theo `id` tăng dần. Thứ tự là ràng buộc nghiệp vụ, không phải tiểu tiết.
        """
        count = 0
        while count < limit:
            row = self.db.claim_next_pending_event()
            if row is None:
                break
            await self._process_event(row)
            count += 1
        return count

    async def _process_event(self, event: sqlite3.Row) -> None:
        event_id = event["event_id"]
        try:
            status, reason, pair_id = await self._route(event)
        except Exception as exc:
            log.exception("Xu ly event %s that bai", event_id, extra={"event_id": event_id})
            self.db.mark_event_processed(event_id, "ERROR", error=str(exc)[:500])
            self.db.create_alert("ERROR", "EVENT_PROCESSING_FAILED",
                                 f"Xu ly event {event_id} that bai: {exc}"[:500],
                                 agent_id=event["agent_id"])
            return
        self.db.mark_event_processed(event_id, status, error=reason, pair_id=pair_id)
        await self._flush_deferred_close()

    async def check_reconcile(self, now: float) -> None:
        """Đối chiếu định kỳ mỗi `reconcile_interval_sec` (plan 8.4)."""
        moi = self.db.get_config_int("reconcile_interval_sec", 60)
        if moi <= 0 or now - self._last_reconcile < moi:
            return
        self._last_reconcile = now
        await self.reconciler.run(trigger="PERIODIC")

    async def check_emergency(self) -> None:
        """`run_mode = EMERGENCY` thì đóng toàn bộ cặp đang quản lý (plan 7.8).

        Chạy **một lần** cho mỗi lần vào chế độ. `emergency_close_all()` tự bỏ qua cặp đã đóng
        và cặp đang có lệnh chạy, nhưng gọi lại mỗi vòng quét sẽ làm ngập alert đúng lúc người
        vận hành cần đọc alert nhất.
        """
        mode = self.db.get_config("run_mode", "PAUSED")
        if mode != "EMERGENCY":
            self._emergency_done = False
            return
        if self._emergency_done:
            return
        self._emergency_done = True
        await self.closing.emergency_close_all()

    async def _flush_deferred_close(self) -> None:
        """Đóng những cặp vừa biết `client_position_id` mà Master đã đóng từ trước."""
        while self._deferred_close:
            pair_id = self._deferred_close.pop(0)
            pair = self.db.get_pair(pair_id)
            if pair is None or pair["status"] not in ("OPEN", "PARTIALLY_CLOSED"):
                continue
            await self.closing.close_pair_now(pair, pair["close_source"] or "MASTER")

    async def _route(self, event: sqlite3.Row) -> tuple[str, str | None, str | None]:
        """Quyết định xử lý một event thế nào. Trả về (process_status, lý do, pair_id)."""
        agent = self.db.get_agent(event["agent_id"])
        if agent is None:
            return "ERROR", f"Khong biet agent {event['agent_id']}", None

        if event["type"] in ("position_closed", "position_changed"):
            if agent["role"] == "MASTER":
                return await self.closing.on_master_close(event, agent)
            return await self.closing.on_client_close(event, agent)

        if event["type"] != "position_opened":
            return "IGNORED", f"Chua xu ly loai event {event['type']}", None

        if agent["role"] != "MASTER":
            # Vị thế mở trên Client. KHÔNG bao giờ copy ngược lên Master — chiều copy chỉ đi
            # một chiều. Nhưng event này là **đường về duy nhất** để biết `position_id` của
            # lệnh mở qua giao diện (D-23), nên phải thử tương quan trước khi bỏ qua.
            return await self._correlate_client_open(event, agent)

        if event["caused_by_command_id"]:
            # Do chính bot gây ra thì KHÔNG lan truyền (D-08).
            return "IGNORED", "Do bot gay ra, khong lan truyen", None

        return await self._handle_master_open(event, agent)

    # -- luồng mở lệnh ---------------------------------------------------------------------

    async def _handle_master_open(self, event: sqlite3.Row,
                                  agent: sqlite3.Row) -> tuple[str, str | None, str | None]:
        payload = json.loads(event["payload_json"] or "{}")
        data = payload.get("data", {})
        master_position_id = event["position_id"]
        symbol = data.get("symbol")
        direction = data.get("direction")
        volume = event["volume_after"]

        if not master_position_id or not symbol or not direction or not volume:
            return "ERROR", "Event position_opened thieu truong bat buoc", None

        # Ghi nhận vị thế Master trong MỌI trường hợp, kể cả khi không copy. Đối chiếu ở phase 8
        # cần biết Master đang có những gì, không phụ thuộc chế độ vận hành.
        self.db.upsert_master_position(
            master_position_id, agent_id=event["agent_id"], symbol=symbol, direction=direction,
            initial_volume=volume, current_volume=volume, status="OPEN",
            ticket=data.get("ticket"), open_price=data.get("price"),
            open_time=event["received_at"], magic=data.get("magic"),
        )

        run_mode = self.db.get_config("run_mode", "PAUSED")
        if run_mode != "RUNNING":
            log.info("run_mode = %s nen khong copy lenh moi (vi the Master van duoc ghi nhan)",
                     run_mode, extra={"event_id": event["event_id"]})
            return "IGNORED", f"run_mode = {run_mode}", None

        clients = self.db.list_enabled_clients()
        if not clients:
            return "IGNORED", "Khong co Client nao dang bat", None

        created: list[str] = []
        reasons: list[str] = []
        for client in clients:
            pair_id, reason = await self._open_for_client(event, client, master_position_id,
                                                          symbol, direction, volume)
            if pair_id:
                created.append(pair_id)
            else:
                reasons.append(f"{client['client_id']}: {reason}")

        if created:
            return "DONE", None, created[0]
        return "IGNORED", "; ".join(reasons)[:500], None

    async def _open_for_client(self, event: sqlite3.Row, client: sqlite3.Row,
                               master_position_id: int, symbol: str, direction: str,
                               master_volume: float) -> tuple[str | None, str]:
        """Tính và mở lệnh cho một Client. Trả về (pair_id, lý do nếu bỏ qua)."""
        client_id = client["client_id"]
        ctx = {"event_id": event["event_id"], "agent_id": client["agent_id"]}

        # Chống copy trùng: đã có pair cho cặp này thì thôi.
        existing = self.db.query_one(
            "SELECT pair_id FROM pair WHERE master_position_id = ? AND client_id = ?",
            (master_position_id, client_id),
        )
        if existing is not None:
            log.info("Da co pair %s cho vi the Master %s va Client %s, bo qua event lap",
                     existing["pair_id"], master_position_id, client_id, extra=ctx)
            return None, "da co pair"

        # Bước 1: ánh xạ symbol. Tuyệt đối không mặc định hai sàn dùng cùng tên symbol.
        mapping = self.db.find_symbol_map(client_id, symbol)
        if mapping is None:
            self._alert("WARNING", "NO_SYMBOL_MAPPING",
                        f"Client {client_id} khong co anh xa cho symbol {symbol}, bo qua lenh",
                        agent_id=client["agent_id"])
            return None, f"khong co anh xa cho {symbol}"
        if not mapping["enabled"]:
            log.info("Anh xa %s -> %s cua Client %s dang tat", symbol, mapping["client_symbol"],
                     client_id, extra=ctx)
            return None, "anh xa dang tat"

        # Tuổi sự kiện. Dùng `ts_agent` chứ không phải `received_at`: một event gửi bù sau khi
        # Bridge chết 20 phút thì `received_at` vẫn mới tinh, mà lệnh thì đã cũ.
        age_ms = self._event_age_ms(event)
        max_age = client["max_event_age_ms"]
        if age_ms is not None and age_ms > max_age:
            self._alert("WARNING", "EVENT_TOO_OLD",
                        f"Event {event['event_id']} da {age_ms}ms tuoi, vuot gioi han "
                        f"{max_age}ms cua Client {client_id}, bo qua lenh",
                        agent_id=client["agent_id"])
            return None, f"event qua cu ({age_ms}ms)"

        # Client phải đang kết nối và terminal phải còn kết nối sàn.
        agent_row = self.db.get_agent(client["agent_id"])
        if agent_row is None or agent_row["status"] != "ONLINE":
            policy = self.db.get_config("offline_reopen_policy", "NONE")
            status = agent_row["status"] if agent_row else "UNKNOWN"
            self._alert("ERROR", "CLIENT_NOT_AVAILABLE",
                        f"Client {client_id} dang {status}, khong copy lenh nay. "
                        f"offline_reopen_policy = {policy}",
                        agent_id=client["agent_id"])
            return None, f"client {status}"

        client_symbol = mapping["client_symbol"]
        spec = self.db.get_symbol_spec(client["agent_id"], client_symbol)
        if spec is None:
            self._alert("ERROR", "NO_SYMBOL_SPEC",
                        f"Chua co thong so cua symbol {client_symbol} tren Client {client_id}. "
                        "Agent da day symbol_specs len chua?",
                        agent_id=client["agent_id"])
            return None, f"khong co spec cho {client_symbol}"

        master_spec = self.db.get_symbol_spec(event["agent_id"], symbol)

        # Bước 2 và 3: chiều và hệ số, cả hai đều kế thừa từ `client_account` khi symbol_map NULL.
        copy_mode = inherit(mapping["copy_mode"], client["copy_mode"])
        multiplier = inherit(mapping["volume_multiplier"], client["volume_multiplier"])
        client_direction = resolve_direction(direction, copy_mode)

        totals = self.db.query_one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(client_current_volume), 0) AS total FROM pair "
            "WHERE client_id = ? AND status IN ('OPEN', 'PARTIALLY_CLOSED', 'PENDING_OPEN')",
            (client_id,),
        )

        result = compute_client_volume(SizingInputs(
            master_volume=master_volume,
            multiplier=multiplier,
            rounding_mode=client["rounding_mode"],
            below_min_policy=client["below_min_policy"],
            volume_min=spec["volume_min"],
            volume_max=spec["volume_max"],
            volume_step=spec["volume_step"],
            master_contract_size=master_spec["contract_size"] if master_spec else None,
            client_contract_size=spec["contract_size"],
            max_volume_per_order=client["max_volume_per_order"],
            max_total_volume=client["max_total_volume"],
            current_total_volume=float(totals["total"] or 0.0),
            max_open_pairs=client["max_open_pairs"],
            current_open_pairs=int(totals["n"] or 0),
        ))

        for level, code, message in result.alerts:
            self._alert(level, code, f"[{client_id}] {message}", agent_id=client["agent_id"])
        for note in result.notes:
            log.info("[%s] %s", client_id, note, extra=ctx)

        if result.skipped:
            return None, result.skip_reason or "bo qua"

        via_ui = client["open_route"] == "UI"
        if via_ui:
            skip = self._ui_route_blocked(client)
            if skip is not None:
                return None, skip

        command_id = new_command_id()
        tag = open_tag_for(command_id) if via_ui else None

        if via_ui:
            target_agent = client["clicker_agent_id"]
            command_type = "OPEN_UI"
            deadline_ms = max(
                self.db.get_config_int("ui_open_deadline_ms", 15000), MIN_DEADLINE_MS
            )
            # KHÔNG có khoá `magic`: hộp thoại New Order không đặt được magic, và việc thiếu nó
            # làm `Guard()` của EA từ chối nếu command này đi nhầm địa chỉ (D-22).
            command_payload = {
                "symbol": client_symbol,
                "direction": client_direction,
                "volume": result.volume,
                "deviation": client["max_deviation_points"],
                "comment": tag,
            }
        else:
            target_agent = client["agent_id"]
            command_type = "OPEN"
            deadline_ms = max(int(client["max_event_age_ms"]), MIN_DEADLINE_MS)
            command_payload = {
                "symbol": client_symbol,
                "direction": client_direction,
                "volume": result.volume,
                "deviation": client["max_deviation_points"],
                "magic": agent_row["magic_number"],
            }

        # MỘT giao dịch: pair + command. Rồi mới gửi qua socket.
        with self.db.transaction():
            pair_id = self.db.create_pending_pair(
                master_position_id, client_id, copy_mode=copy_mode,
                master_initial_volume=master_volume,
                effective_multiplier=result.effective_multiplier,
                client_symbol=client_symbol, client_direction=client_direction,
                open_time_master=event["received_at"], last_event_id=event["event_id"],
                open_tag=tag,
            )
            if pair_id is None:
                return None, "da co pair (rang buoc DB chan)"
            self.db.create_command(
                command_id, target_agent, command_type, pair_id=pair_id,
                payload_json=json.dumps(command_payload, ensure_ascii=False,
                                        separators=(",", ":")),
                deadline_at=_deadline(deadline_ms),
            )

        log.info("Tao cap %s: Master %s %s %s -> Client %s %s %s (ty le thuc %.4f)",
                 pair_id, symbol, direction, master_volume, client_id, client_symbol,
                 client_direction, result.effective_multiplier,
                 extra={"pair_id": pair_id, "event_id": event["event_id"],
                        "command_id": command_id, "agent_id": client["agent_id"]})

        await self.dispatcher.send_existing(command_id)
        return pair_id, ""

    # -- ack ---------------------------------------------------------------------------------

    async def on_command_acked(self, command: sqlite3.Row, message: Any) -> None:
        """Hook được `BridgeServer` gọi sau khi ghi ack vào DB."""
        if command["type"] in ("CLOSE", "CLOSE_PARTIAL"):
            if command["pair_id"]:
                await self.closing.on_close_acked(command, message)
            return

        if command["type"] not in ("OPEN", "OPEN_UI") or not command["pair_id"]:
            return
        pair = self.db.get_pair(command["pair_id"])
        if pair is None or pair["status"] != "PENDING_OPEN":
            return

        if command["type"] == "OPEN_UI":
            await self._on_ui_ack(pair, command, message)
            return

        if message.status in ("ok", "already_closed") and message.retcode in (
            None, SUCCESS_RETCODE
        ):
            await self._on_open_success(pair, message)
        elif message.status == "unknown":
            # Agent khong biet lenh da khop hay chua. KHONG retry, KHONG danh that bai.
            self.db.update_pair(command["pair_id"], error_message="ACK_UNKNOWN")
            log.critical("Cap %s co ack unknown, cho doi chieu xu ly", command["pair_id"],
                         extra={"pair_id": command["pair_id"]})
        else:
            await self._on_open_failure(pair, command, message)

    async def _on_open_success(self, pair: sqlite3.Row, message: Any) -> None:
        now = utc_now_iso()
        self.db.mark_pair_open(
            pair["pair_id"],
            client_position_id=message.result_position_id,
            client_ticket=message.result_position_id,
            client_volume=message.executed_volume or pair["master_initial_volume"],
            open_time_client=now,
        )
        latency = _latency_ms(pair["open_time_master"], now)
        log.info("Cap %s da hedge xong, do tre copy %s ms", pair["pair_id"],
                 latency if latency is not None else "?",
                 extra={"pair_id": pair["pair_id"]})

    async def _on_open_failure(self, pair: sqlite3.Row, command: sqlite3.Row,
                               message: Any) -> None:
        pair_id = pair["pair_id"]
        client = self.db.get_client_account(pair["client_id"])
        retcode = message.retcode
        attempt = int(pair["retry_count"] or 0)

        self.db.update_pair(pair_id, error_code=retcode,
                            error_message=(message.retmsg or "")[:500])

        can_retry = (
            retcode in RETRY_RETCODES
            and retcode not in STOP_RETCODES
            and attempt < int(client["max_retry"])
        )
        if can_retry:
            self.db.update_pair(pair_id, retry_count=attempt + 1)
            log.warning("Mo lenh cho cap %s that bai retcode %s, thu lai lan %d sau %dms",
                        pair_id, retcode, attempt + 1, client["retry_interval_ms"],
                        extra={"pair_id": pair_id})
            task = asyncio.create_task(
                self._retry_open(pair_id, command, int(client["retry_interval_ms"]))
            )
            self._retry_tasks.add(task)
            task.add_done_callback(self._retry_tasks.discard)
            return

        await self._apply_open_fail_policy(pair, client, retcode, message.retmsg)

    async def _retry_open(self, pair_id: str, command: sqlite3.Row, delay_ms: int) -> None:
        await asyncio.sleep(delay_ms / 1000.0)
        pair = self.db.get_pair(pair_id)
        if pair is None or pair["status"] != "PENDING_OPEN":
            return
        client = self.db.get_client_account(pair["client_id"])
        deadline_ms = max(int(client["max_event_age_ms"]), MIN_DEADLINE_MS)
        command_id = new_command_id()
        self.db.create_command(
            command_id, command["target_agent_id"], command["type"], pair_id=pair_id,
            payload_json=command["payload_json"], deadline_at=_deadline(deadline_ms),
        )
        await self.dispatcher.send_existing(command_id)

    async def _apply_open_fail_policy(self, pair: sqlite3.Row, client: sqlite3.Row,
                                      retcode: int | None, retmsg: str | None) -> None:
        pair_id = pair["pair_id"]
        policy = client["open_fail_policy"]

        self.db.update_pair(pair_id, status="OPEN_FAILED")
        self._alert("ERROR", "OPEN_FAILED",
                    f"Cap {pair_id} mo lenh that bai, retcode {retcode} {retmsg or ''}. "
                    f"Chinh sach {policy}.",
                    pair_id=pair_id, agent_id=client["agent_id"])

        if policy != "RETRY_CLOSE_MASTER":
            return

        # Với nhiều Client, đóng Master vì MỘT Client hỏng sẽ kéo theo mọi Client khác. Phải
        # nhìn thấy được điều đó, nhưng vẫn thực hiện đúng cấu hình.
        siblings = self.db.query_all(
            "SELECT pair_id, client_id FROM pair WHERE master_position_id = ? "
            "AND pair_id <> ? AND status IN ('OPEN', 'PARTIALLY_CLOSED')",
            (pair["master_position_id"], pair_id),
        )
        if siblings:
            self._alert("CRITICAL", "CLOSE_MASTER_AFFECTS_OTHERS",
                        f"Dong Master {pair['master_position_id']} vi cap {pair_id} that bai "
                        f"se lam mat hedge cua {len(siblings)} cap khac: "
                        f"{[s['pair_id'] for s in siblings]}",
                        pair_id=pair_id)

        master = self.db.get_master_position(pair["master_position_id"])
        if master is None:
            return
        self._alert("CRITICAL", "CLOSING_MASTER_AFTER_OPEN_FAILURE",
                    f"Dong vi the Master {pair['master_position_id']} theo chinh sach "
                    f"RETRY_CLOSE_MASTER cua Client {pair['client_id']}",
                    pair_id=pair_id, agent_id=master["agent_id"])
        await self.dispatcher.dispatch(
            master["agent_id"], "CLOSE", pair_id=pair_id,
            payload={"position_id": pair["master_position_id"],
                     "magic": self.db.get_agent(master["agent_id"])["magic_number"]},
            deadline_ms=MIN_DEADLINE_MS * 2,
        )

    # -- timeout -------------------------------------------------------------------------------

    def on_command_timeout(self, command: sqlite3.Row) -> None:
        """Command quá hạn mà chưa có ack.

        **Không tự động thử lại** (D-13): không biết lệnh đã khớp hay chưa, và mở thêm là hành
        động tăng rủi ro. Để đối chiếu ở phase 8 dọn.
        """
        if command["type"] in ("CLOSE", "CLOSE_PARTIAL"):
            self.closing.on_close_timeout(command)
            return

        if command["type"] not in ("OPEN", "OPEN_UI") or not command["pair_id"]:
            return
        pair = self.db.get_pair(command["pair_id"])
        if pair is None or pair["status"] != "PENDING_OPEN":
            return
        if command["type"] == "OPEN_UI":
            # Clicker im lặng KHÔNG có nghĩa là chưa bấm. Đánh `OPEN_FAILED` ở đây là tự tay xoá
            # cặp lệnh có thể đang tồn tại thật trên terminal. Giữ `PENDING_OPEN` chờ tương quan.
            self.db.update_pair(command["pair_id"], error_message="UI_ACK_TIMEOUT")
            self._alert("CRITICAL", "UI_OPEN_TIMEOUT",
                        f"Cap {command['pair_id']} khong nhan duoc ack tu clicker truoc han. "
                        "KHONG ket luan la that bai; cho event tuong quan hoac doi chieu.",
                        pair_id=command["pair_id"], agent_id=command["target_agent_id"])
            return
        self.db.update_pair(command["pair_id"], status="OPEN_FAILED",
                            error_message="Command OPEN qua han ma chua co ack")
        self._alert("ERROR", "OPEN_TIMEOUT",
                    f"Cap {command['pair_id']} khong nhan duoc ack truoc han. KHONG tu dong "
                    "thu lai; cho doi chieu xu ly.",
                    pair_id=command["pair_id"], agent_id=command["target_agent_id"])

    # -- đường mở lệnh qua giao diện (phase 6b) ----------------------------------------------

    def _ui_route_blocked(self, client: sqlite3.Row) -> str | None:
        """Lý do KHÔNG được gửi `OPEN_UI` lúc này, hoặc ``None`` nếu đi được.

        Hai cổng, cả hai đều **chỉ biết bỏ qua**. Rơi về đường EA khi clicker hỏng là lặng lẽ
        đặt một lệnh `EXPERT` — đúng thứ phase này tồn tại để làm cho bất khả thi (D-25).
        """
        client_id = client["client_id"]
        clicker_id = client["clicker_agent_id"]
        clicker = self.db.get_agent(clicker_id) if clicker_id else None

        # Cổng 1 — canary. DEGRADED với role CLICKER nghĩa là "không điều khiển được giao diện".
        if clicker is None or clicker["status"] != "ONLINE":
            status = clicker["status"] if clicker is not None else "KHONG TON TAI"
            fallback = self.db.get_config("ui_degraded_fallback", "SKIP")
            self._alert("ERROR", "CLICKER_NOT_AVAILABLE",
                        f"Clicker {clicker_id} cua Client {client_id} dang {status}, "
                        f"khong copy lenh nay. ui_degraded_fallback = {fallback}. "
                        "KHONG tu rot ve duong EA.",
                        agent_id=clicker_id)
            return f"clicker {status}"

        # Cổng 2 — đúng MỘT `OPEN_UI` đang bay cho mỗi Client. Đây là thứ biến bài toán tương
        # quan mờ thành hàng đợi một phần tử, luôn phân giải được.
        inflight = self.db.query_one(
            "SELECT c.command_id FROM command c JOIN pair p ON p.pair_id = c.pair_id "
            "WHERE c.type = 'OPEN_UI' AND c.status IN ('PENDING', 'SENT') AND p.client_id = ? "
            "LIMIT 1",
            (client_id,),
        )
        if inflight is not None:
            self._alert("WARNING", "UI_OPEN_BUSY",
                        f"Client {client_id} dang co lenh mo qua giao dien "
                        f"{inflight['command_id']} chua xong, bo qua lenh nay",
                        agent_id=clicker_id)
            return "clicker dang ban"
        return None

    async def _on_ui_ack(self, pair: sqlite3.Row, command: sqlite3.Row, message: Any) -> None:
        """Ack của clicker. Đọc theo hợp đồng ở plan 6b mục 6b.3.

        `ok` nói *"tôi đã bấm"*, **không** nói *"vị thế nào"*. Việc mở pair do tương quan quyết
        định (D-23), nên ở đây không có nhánh nào gọi `mark_pair_open()`.
        """
        pair_id = pair["pair_id"]
        status = message.status

        if status == "ok":
            if message.result_position_id:
                self._alert("WARNING", "UI_ACK_HAS_POSITION_ID",
                            f"Clicker tra ve result_position_id cho cap {pair_id}. Giao dien "
                            "khong biet position_id; gia tri nay bi bo qua.",
                            pair_id=pair_id, agent_id=command["target_agent_id"])
            log.info("Clicker bao da bam xong cho cap %s, cho event tuong quan", pair_id,
                     extra={"pair_id": pair_id, "command_id": command["command_id"]})
            return

        if status == "unknown":
            # Không biết đã bấm hay chưa. Giữ `PENDING_OPEN` — đánh thất bại ở đây là xoá sổ một
            # vị thế có thể đang tồn tại thật.
            self.db.update_pair(pair_id, error_message="UI_ACK_UNKNOWN")
            self._alert("CRITICAL", "UI_ACK_UNKNOWN",
                        f"Clicker khong biet lenh cua cap {pair_id} da gui hay chua. KHONG thu "
                        "lai; cho event tuong quan hoac doi chieu.",
                        pair_id=pair_id, agent_id=command["target_agent_id"])
            return

        client = self.db.get_client_account(pair["client_id"])
        self.db.update_pair(pair_id, error_code=message.retcode,
                            error_message=(message.retmsg or status)[:500])

        # `rejected` là trạng thái DUY NHẤT chứng minh được là chưa bấm nút gửi, nên cũng là
        # trạng thái duy nhất được phép thử lại (D-24).
        attempt = int(pair["retry_count"] or 0)
        if status == "rejected" and attempt < int(client["max_retry"]):
            self.db.update_pair(pair_id, retry_count=attempt + 1)
            log.warning("Clicker tu choi cap %s (%s), thu lai lan %d sau %dms",
                        pair_id, message.retmsg, attempt + 1, client["retry_interval_ms"],
                        extra={"pair_id": pair_id})
            task = asyncio.create_task(
                self._retry_open(pair_id, command, int(client["retry_interval_ms"]))
            )
            self._retry_tasks.add(task)
            task.add_done_callback(self._retry_tasks.discard)
            return

        await self._apply_open_fail_policy(pair, client, message.retcode, message.retmsg)

    async def _correlate_client_open(self, event: sqlite3.Row,
                                     agent: sqlite3.Row) -> tuple[str, str | None, str | None]:
        """Ghép một vị thế vừa mở trên Client vào cặp lệnh đang chờ (plan 6b mục 6b.4)."""
        if event["caused_by_command_id"]:
            # Đã tương quan rồi. Idempotent với event gửi bù sau khi kết nối lại.
            return "IGNORED", "Da tuong quan truoc do", None

        position_id = event["position_id"]
        if not position_id:
            return "ERROR", "Event position_opened tu Client thieu position_id", None

        client = self.db.query_one(
            "SELECT * FROM client_account WHERE agent_id = ?", (agent["agent_id"],)
        )
        if client is None:
            return "IGNORED", "Agent CLIENT chua duoc cau hinh trong client_account", None
        client_id = client["client_id"]

        # Vị thế đã thuộc một pair rồi thì KHÔNG ghép lại, chỉ đồng bộ volume.
        existing = self.db.find_pair_by_client_position(client_id, position_id)
        if existing is not None:
            if event["volume_after"]:
                self.db.update_pair(existing["pair_id"],
                                    client_current_volume=event["volume_after"])
            return "DONE", None, existing["pair_id"]

        data = json.loads(event["payload_json"] or "{}").get("data", {})
        # EA gửi volume dưới tên `volume_after` / `volume_delta`. So sánh với payload `OPEN_UI`
        # cần một khoá thống nhất, nên chuẩn hoá ngay ở đây thay vì rải điều kiện xuống dưới.
        if data.get("volume") is None:
            data["volume"] = event["volume_after"] or data.get("volume_after")

        candidates = self._open_ui_candidates(client_id)
        if not candidates:
            return "IGNORED", "Khong co lenh OPEN_UI nao dang cho, coi la lenh mo tay", None

        comment = f"{data.get('comment') or ''} {data.get('order_comment') or ''}"
        matched = [c for c in candidates if c["open_tag"] and c["open_tag"] in comment]

        if len(matched) > 1:
            # KHÔNG ĐOÁN. Ghép sai một vị thế vào một cặp là sai lệch sổ sách mà không có cách
            # nào tự phát hiện về sau.
            self._alert("CRITICAL", "UI_CORRELATE_AMBIGUOUS",
                        f"Vi the {position_id} tren Client {client_id} khop {len(matched)} the "
                        f"tuong quan: {[c['pair_id'] for c in matched]}. Khong ghep tu dong.",
                        agent_id=agent["agent_id"])
            return "ERROR", "Nhieu the tuong quan cung khop", None

        if len(matched) == 1:
            how = "the tuong quan"
        else:
            matched, how = self._heuristic_match(candidates, data, client_id, position_id)
            if not matched:
                return "IGNORED", "Khong khop lenh OPEN_UI nao, coi la lenh mo tay (FR-12)", None

        return self._bind(matched[0], event, data, client_id, position_id, how)

    def _open_ui_candidates(self, client_id: str) -> list[sqlite3.Row]:
        """Các lệnh `OPEN_UI` còn trong cửa sổ tương quan của một Client."""
        rows = self.db.query_all(
            "SELECT c.command_id, c.deadline_at, c.payload_json, p.pair_id, p.open_tag, "
            "       p.client_symbol, p.client_direction "
            "FROM command c JOIN pair p ON p.pair_id = c.pair_id "
            "WHERE c.type = 'OPEN_UI' AND p.client_id = ? AND p.status = 'PENDING_OPEN' "
            "  AND p.client_position_id IS NULL "
            "ORDER BY c.created_at",
            (client_id,),
        )
        grace_ms = self.db.get_config_int("ui_correlate_grace_ms", 10000)
        now_iso = utc_now_iso()
        return [r for r in rows
                if (_latency_ms(r["deadline_at"], now_iso) or 0) <= grace_ms]

    def _heuristic_match(self, candidates: list[sqlite3.Row], data: dict[str, Any],
                         client_id: str, position_id: int) -> tuple[list[sqlite3.Row], str]:
        """Ghép bằng suy đoán khi thẻ bị mất. Chỉ chạy khi `ui_fallback_match = HEURISTIC`."""
        mode = (self.db.get_config("ui_fallback_match", "STRICT") or "STRICT").upper()
        if mode != "HEURISTIC":
            log.info("Vi the %s tren Client %s khong mang the tuong quan, ui_fallback_match = "
                     "%s nen khong doan", position_id, client_id, mode)
            return [], ""

        hits = [
            c for c in candidates
            if c["client_symbol"] == data.get("symbol")
            and c["client_direction"] == data.get("direction")
            and _same_volume(c["payload_json"], data.get("volume"))
        ]
        if len(hits) != 1:
            log.info("Suy doan cho vi the %s tren Client %s ra %d ung vien, khong ghep",
                     position_id, client_id, len(hits))
            return [], ""

        self._alert("WARNING", "UI_CORRELATE_HEURISTIC",
                    f"Ghep vi the {position_id} vao cap {hits[0]['pair_id']} bang SUY DOAN "
                    "(symbol/chieu/volume), khong phai bang the tuong quan.",
                    pair_id=hits[0]["pair_id"])
        return hits, "suy doan"

    def _bind(self, candidate: sqlite3.Row, event: sqlite3.Row, data: dict[str, Any],
              client_id: str, position_id: int, how: str) -> tuple[str, str | None, str | None]:
        """Ghép vị thế vào cặp lệnh. Một giao dịch DB duy nhất."""
        pair_id = candidate["pair_id"]
        command_id = candidate["command_id"]
        volume = event["volume_after"] or data.get("volume")
        reason = data.get("reason")
        now = utc_now_iso()

        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "UPDATE event SET caused_by_command_id = ?, pair_id = ? WHERE event_id = ?",
                    (command_id, pair_id, event["event_id"]),
                )
                conn.execute(
                    "UPDATE command SET result_position_id = ?, executed_volume = ?, "
                    "updated_at = ? WHERE command_id = ?",
                    (position_id, volume, now, command_id),
                )
                conn.execute(
                    "UPDATE pair SET status = 'OPEN', client_position_id = ?, client_ticket = ?, "
                    "client_initial_volume = ?, client_current_volume = ?, open_time_client = ?, "
                    "client_open_reason = ?, last_event_id = ?, updated_at = ? "
                    "WHERE pair_id = ? AND status = 'PENDING_OPEN'",
                    (position_id, data.get("ticket"), volume, volume, now, reason,
                     event["event_id"], now, pair_id),
                )
        except sqlite3.IntegrityError as exc:
            # `idx_pair_client_pos` là lưới an toàn cuối cùng chống ghép một vị thế vào hai pair.
            self._alert("CRITICAL", "UI_CORRELATE_CONFLICT",
                        f"Khong ghep duoc vi the {position_id} vao cap {pair_id}: {exc}. "
                        "Vi the nay co the da thuoc mot cap khac.",
                        pair_id=pair_id)
            return "ERROR", f"xung dot rang buoc khi ghep: {exc}"[:500], None

        pair = self.db.get_pair(pair_id)
        latency = _latency_ms(pair["open_time_master"] if pair else None, now)
        log.info("Ghep vi the %s tren Client %s vao cap %s bang %s, do tre copy %s ms",
                 position_id, client_id, pair_id, how,
                 latency if latency is not None else "?",
                 extra={"pair_id": pair_id, "command_id": command_id,
                        "event_id": event["event_id"]})

        self._check_ui_result(pair_id, candidate, data, reason)

        # Lỗ hổng 1 của plan 7.4b: Master có thể đã đóng trong lúc lệnh mở này còn đang bay.
        # `close_time_master` khác NULL chính là "ý định đóng đang chờ địa chỉ" — giờ đã có
        # `client_position_id` thì đóng ngay, nếu không ta để lại một vị thế Client không đối ứng.
        if pair is not None and pair["close_time_master"]:
            log.critical("Cap %s vua tuong quan xong nhung Master da dong tu truoc, dong ngay",
                         pair_id, extra={"pair_id": pair_id})
            self._deferred_close.append(pair_id)

        return "DONE", None, pair_id

    def _check_ui_result(self, pair_id: str, candidate: sqlite3.Row, data: dict[str, Any],
                         reason: Any) -> None:
        """Tự kiểm chứng mục tiêu của cả phase, thay vì tin (plan 6b mục 6b.7)."""
        if reason is not None and int(reason) != DEAL_REASON_CLIENT:
            self._alert("CRITICAL", "UI_REASON_MISMATCH",
                        f"Cap {pair_id} mo qua giao dien nhung DEAL_REASON = {reason}, khong "
                        f"phai {DEAL_REASON_CLIENT} (CLIENT). Co che mo lenh qua giao dien da "
                        "ngung hoat dong.",
                        pair_id=pair_id)

        payload = json.loads(candidate["payload_json"] or "{}")
        lech = [
            f"{ten}: yeu cau {payload.get(ten)!r}, thuc te {thuc!r}"
            for ten, thuc in (("symbol", data.get("symbol")),
                              ("direction", data.get("direction")))
            if payload.get(ten) is not None and payload.get(ten) != thuc
        ]
        if not _same_volume(candidate["payload_json"], data.get("volume")):
            lech.append(f"volume: yeu cau {payload.get('volume')!r}, "
                        f"thuc te {data.get('volume')!r}")
        if not lech:
            return

        action = (self.db.get_config("ui_mismatch_action", "ALERT") or "ALERT").upper()
        self._alert("CRITICAL" if action == "CLOSE" else "ERROR", "UI_PARAM_MISMATCH",
                    f"Cap {pair_id}: lenh thuc te lech so voi payload OPEN_UI. "
                    f"{'; '.join(lech)}. ui_mismatch_action = {action}.",
                    pair_id=pair_id)

    def scan_correlation_deadlines(self) -> None:
        """Cặp mở qua giao diện quá cửa sổ tương quan mà vẫn chưa ghép được vị thế nào.

        **Không** đánh `OPEN_FAILED`: không ghép được không có nghĩa là không có lệnh. Cảnh báo
        đúng một lần rồi để đối chiếu ở phase 8 quyết định.
        """
        grace_ms = self.db.get_config_int("ui_correlate_grace_ms", 10000)
        rows = self.db.query_all(
            "SELECT c.deadline_at, c.target_agent_id, p.pair_id FROM command c "
            "JOIN pair p ON p.pair_id = c.pair_id "
            "WHERE c.type = 'OPEN_UI' AND p.status = 'PENDING_OPEN' "
            "  AND p.client_position_id IS NULL "
            "  AND COALESCE(p.error_message, '') <> 'UI_CORRELATE_EXPIRED'"
        )
        now_iso = utc_now_iso()
        for row in rows:
            if (_latency_ms(row["deadline_at"], now_iso) or 0) <= grace_ms:
                continue
            self.db.update_pair(row["pair_id"], error_message="UI_CORRELATE_EXPIRED")
            self._alert("CRITICAL", "UI_CORRELATE_EXPIRED",
                        f"Cap {row['pair_id']} het cua so tuong quan ma khong ghep duoc vi the "
                        "nao. Cap giu PENDING_OPEN; can doi chieu xac nhan terminal Client "
                        "that su khong co vi the tuong ung.",
                        pair_id=row["pair_id"], agent_id=row["target_agent_id"])

    # -- tiện ích --------------------------------------------------------------------------------

    def _alert(self, level: str, code: str, message: str, **fields: Any) -> None:
        self.db.create_alert(level, code, message, **fields)
        logger = {"INFO": log.info, "WARNING": log.warning,
                  "ERROR": log.error, "CRITICAL": log.critical}[level]
        logger("%s: %s", code, message,
               extra={k: v for k, v in fields.items() if k in ("pair_id", "agent_id")})

    @staticmethod
    def _event_age_ms(event: sqlite3.Row) -> int | None:
        """Tuổi sự kiện tính từ `ts_agent`.

        Độ phân giải của `ts_agent` là khoảng một giây (giới hạn của MQL5, xem PROGRESS phase 4),
        nên con số này chỉ nên dùng để so với ngưỡng vài giây, không dùng để đo độ trễ.
        """
        return _latency_ms(event["ts_agent"], utc_now_iso())


def _same_volume(payload_json: str | None, actual: Any) -> bool:
    """So volume yêu cầu với volume thực tế, với dung sai của số thực."""
    if actual is None:
        return True
    try:
        want = json.loads(payload_json or "{}").get("volume")
        return want is None or abs(float(want) - float(actual)) < 1e-9
    except (TypeError, ValueError):
        return False


def _latency_ms(start_iso: str | None, end_iso: str | None) -> int | None:
    if not start_iso or not end_iso:
        return None
    try:
        return int((parse_iso(end_iso) - parse_iso(start_iso)).total_seconds() * 1000)
    except ValueError:
        return None


def _deadline(deadline_ms: int) -> str:
    from datetime import timedelta

    return (utc_now() + timedelta(milliseconds=deadline_ms)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
