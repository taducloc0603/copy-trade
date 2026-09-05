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

        server.on_command_acked = self.on_command_acked
        dispatcher.on_timeout = self.on_command_timeout

    # -- vòng đời --------------------------------------------------------------------------

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        for task in (self._task, *self._retry_tasks):
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

    async def _route(self, event: sqlite3.Row) -> tuple[str, str | None, str | None]:
        """Quyết định xử lý một event thế nào. Trả về (process_status, lý do, pair_id)."""
        agent = self.db.get_agent(event["agent_id"])
        if agent is None:
            return "ERROR", f"Khong biet agent {event['agent_id']}", None

        if event["type"] != "position_opened":
            # Đóng lệnh là phase 7. Ở phase 6, Master đóng thì Client KHÔNG đóng — đúng phạm vi.
            return "IGNORED", f"Phase 6 chua xu ly loai event {event['type']}", None

        if agent["role"] != "MASTER":
            # Vị thế mở trên Client: hoặc do chính bot mở (có `caused_by_command_id`, đã xử lý
            # qua ack), hoặc do người mở tay (FR-12: bỏ qua hoàn toàn).
            return "IGNORED", "position_opened tu agent CLIENT, khong copy nguoc", None

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

        deadline_ms = max(int(client["max_event_age_ms"]), MIN_DEADLINE_MS)
        command_id = new_command_id()
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
            )
            if pair_id is None:
                return None, "da co pair (rang buoc DB chan)"
            self.db.create_command(
                command_id, client["agent_id"], "OPEN", pair_id=pair_id,
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
        if command["type"] != "OPEN" or not command["pair_id"]:
            return
        pair = self.db.get_pair(command["pair_id"])
        if pair is None or pair["status"] != "PENDING_OPEN":
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
            command_id, command["target_agent_id"], "OPEN", pair_id=pair_id,
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
        if command["type"] != "OPEN" or not command["pair_id"]:
            return
        pair = self.db.get_pair(command["pair_id"])
        if pair is None or pair["status"] != "PENDING_OPEN":
            return
        self.db.update_pair(command["pair_id"], status="OPEN_FAILED",
                            error_message="Command OPEN qua han ma chua co ack")
        self._alert("ERROR", "OPEN_TIMEOUT",
                    f"Cap {command['pair_id']} khong nhan duoc ack truoc han. KHONG tu dong "
                    "thu lai; cho doi chieu xu ly.",
                    pair_id=command["pair_id"], agent_id=command["target_agent_id"])

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
