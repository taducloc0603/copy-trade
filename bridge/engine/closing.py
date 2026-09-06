"""Luồng đóng lệnh (plan mục 7.1–7.8).

Đây là phase dễ mất tiền nhất nếu sai, nên bốn nguyên tắc dưới đây chi phối mọi dòng trong file:

* **Tra cứu luôn theo `position_id`, không bao giờ theo symbol** (FR-11). Một câu SQL đóng lệnh
  có `WHERE symbol = ?` là bug, không phải phong cách.
* **Sự kiện là tín hiệu, không phải nguồn sự thật** (D-14). `volume_after` do EA báo là con số
  được dùng; Bridge không tự trừ ra.
* **Chống vòng lặp bằng `caused_by_command_id`** (D-08). Khác NULL nghĩa là do chính bot gây ra:
  cập nhật trạng thái, KHÔNG lan truyền tiếp.
* **Đóng trước hỏi sau là sai.** Cascade phải chờ Master xác nhận đã đóng rồi mới đụng tới các
  Client còn lại (D-10). Master từ chối lệnh đóng mà ta đã đóng B và C thì cả nhóm mất hedge.

Tách khỏi `processor.py` vì file đó đã dài, và vì đóng lệnh là một tập ngữ nghĩa đứng riêng —
đọc hết file này là hiểu hết đường đóng, không phải nhảy qua lại với đường mở.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3
from decimal import Decimal
from typing import Any

from bridge.clock import utc_now_iso
from bridge.db.repo import Database
from bridge.engine.sizing import round_to_step, to_decimal
from bridge.logging_setup import get_logger
from bridge.protocol.dispatcher import CommandDispatcher

log = get_logger(__name__)

#: `run_mode` mà đồng bộ đóng vẫn phải chạy. `PAUSE_NEW_ENTRIES` **có mặt ở đây là cố ý**: nó là
#: chế độ "ngừng vào lệnh mới nhưng vẫn bảo vệ cặp đang chạy", tắt đồng bộ đóng ở đó là bỏ rơi
#: vị thế đang mở (plan mục 7.8).
SYNC_CLOSE_MODES = frozenset({"RUNNING", "PAUSE_NEW_ENTRIES", "EMERGENCY"})

#: Trạng thái pair đã kết thúc, không còn gì để đóng.
TERMINAL_STATUSES = frozenset({"CLOSED", "OPEN_FAILED"})

DEFAULT_CLOSE_DEADLINE_MS = 20000
DEFAULT_CASCADE_WAIT_MS = 15000


class CloseFlow:
    """Toàn bộ ngữ nghĩa đóng lệnh. `EventProcessor` chỉ định tuyến vào đây."""

    def __init__(self, db: Database, dispatcher: CommandDispatcher, alert: Any,
                 server: Any = None) -> None:
        self.db = db
        self.dispatcher = dispatcher
        #: Dùng để đọc snapshot trả về sau `OUT_BY` (plan 7.7). Không bắt buộc.
        self.server = server
        #: `EventProcessor._alert` — dùng chung để alert vừa vào DB vừa ra log.
        self._alert = alert
        self._tasks: set[asyncio.Task[None]] = set()

    async def stop(self) -> None:
        for task in list(self._tasks):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # -- cổng chung ----------------------------------------------------------------------------

    def _sync_allowed(self) -> tuple[bool, str]:
        mode = self.db.get_config("run_mode", "PAUSED") or "PAUSED"
        return (mode in SYNC_CLOSE_MODES), mode

    # -- Master đóng (plan 7.2, 7.3) -----------------------------------------------------------

    async def on_master_close(self, event: sqlite3.Row,
                              agent: sqlite3.Row) -> tuple[str, str | None, str | None]:
        """Master đóng hoặc đóng bớt một vị thế."""
        master_position_id = event["position_id"]
        if not master_position_id:
            return "ERROR", "Event dong tu Master thieu position_id", None

        data = json.loads(event["payload_json"] or "{}").get("data", {})
        volume_after = event["volume_after"]
        if volume_after is None:
            return "ERROR", "Event dong thieu volume_after (D-14)", None

        # Ghi nhận vị thế Master trong MỌI trường hợp, kể cả khi không đồng bộ. Sổ sách phải
        # phản ánh terminal ngay cả lúc `run_mode = PAUSED`; đây cũng là chỗ trả món nợ
        # "master_position của vị thế đã đóng vẫn mang status OPEN" ghi từ phase 6.
        dong_han = volume_after <= 0
        self.db.set_master_position_status(
            master_position_id, "CLOSED" if dong_han else "OPEN",
            current_volume=0.0 if dong_han else volume_after,
            close_time=event["received_at"] if dong_han else None,
        )

        if event["caused_by_command_id"]:
            # Do chính bot gây ra. Trạng thái cặp đã được cập nhật ở đường ack; ở đây chỉ ghi
            # nhận rồi dừng, tuyệt đối không khởi động lại quy trình đóng (D-08).
            return "IGNORED", "Do bot gay ra, khong lan truyen", None

        cho_phep, mode = self._sync_allowed()
        if not cho_phep:
            return "IGNORED", f"run_mode = {mode} nen khong dong bo dong", None

        pairs = [p for p in self.db.list_pairs_for_master_position(master_position_id)
                 if p["status"] not in TERMINAL_STATUSES]
        if not pairs:
            return "IGNORED", "Vi the Master khong thuoc cap nao", None

        da_xu_ly: list[str] = []
        for pair in pairs:
            if dong_han:
                ok = await self._close_pair_fully(pair, "MASTER", event)
            else:
                ok = await self._close_pair_partially(pair, event, data)
            if ok:
                da_xu_ly.append(pair["pair_id"])

        if data.get("deal_entry") == "OUT_BY":
            # plan 7.7: Close By đóng hai vị thế cùng lúc và có thể để lại phần dư. Phần trên
            # đã chạy đúng nhờ tra cứu theo `position_id`; ở đây chỉ cần soi lại Master xem có
            # vị thế nào không thuộc cặp nào.
            self._spawn(self._doi_chieu_sau_out_by(agent["agent_id"]))

        if not da_xu_ly:
            return "IGNORED", "Khong cap nao can gui lenh dong", pairs[0]["pair_id"]
        return "DONE", None, da_xu_ly[0]

    async def _doi_chieu_sau_out_by(self, master_agent_id: str) -> None:
        """Hỏi Master còn những vị thế nào, rồi đánh dấu cái không thuộc cặp nào.

        Đây là bản thô, cố ý: đối chiếu đầy đủ là phase 8. Việc ở đây chỉ là **không im lặng**
        khi Close By để lại một vị thế Master mà sổ sách không biết. Và tuyệt đối **không tự
        copy nó sang Client** — vị thế dư có thể là của người dùng.
        """
        if self.server is None:
            return
        truoc = self.server.latest_snapshots.get(master_agent_id)
        await self.dispatcher.request_snapshot(master_agent_id)
        for _ in range(40):
            await asyncio.sleep(0.1)
            snap = self.server.latest_snapshots.get(master_agent_id)
            if snap is not None and snap is not truoc:
                break
        else:
            return

        for vi_the in snap.positions:
            co_cap = self.db.query_one(
                "SELECT 1 FROM pair WHERE master_position_id = ? "
                "AND status NOT IN ('CLOSED','OPEN_FAILED') LIMIT 1",
                (vi_the.position_id,))
            if co_cap is not None:
                continue
            master = self.db.get_master_position(vi_the.position_id)
            if master is not None and master["status"] == "UNPAIRED":
                continue
            self.db.upsert_master_position(
                vi_the.position_id, agent_id=master_agent_id, symbol=vi_the.symbol,
                direction=vi_the.direction, initial_volume=vi_the.volume,
                current_volume=vi_the.volume, status="UNPAIRED")
            self._alert("ERROR", "UNPAIRED_MASTER",
                        f"Sau Close By, vi the Master {vi_the.position_id} "
                        f"({vi_the.direction} {vi_the.volume} {vi_the.symbol}) khong thuoc cap "
                        "nao. KHONG tu copy sang Client; can nguoi xem lai.")

    async def close_pair_now(self, pair: sqlite3.Row, close_source: str) -> bool:
        """Dong ngay mot cap da biet `client_position_id` (lo hong 1, plan 7.4b)."""
        return await self._close_pair_fully(pair, close_source, None)

    async def _close_pair_fully(self, pair: sqlite3.Row, close_source: str,
                                event: sqlite3.Row | None) -> bool:
        """Gửi lệnh đóng toàn bộ vị thế Client của một cặp. Trả về có gửi hay không."""
        pair_id = pair["pair_id"]
        now = utc_now_iso()

        # -- Lỗ hổng 1 (plan 7.4b): cặp chưa biết `client_position_id` -------------------------
        if pair["client_position_id"] is None:
            # Chưa có địa chỉ để đóng. Ghi **ý định** đóng vào `close_time_master`; bộ tương quan
            # của phase 6b sẽ thấy nó khi ghép được vị thế và đóng ngay lúc đó.
            self.db.update_pair(pair_id, close_time_master=now, close_source=close_source)
            self._alert("CRITICAL", "MASTER_CLOSED_WHILE_PENDING",
                        f"Master {pair['master_position_id']} da dong trong khi lenh mo cua cap "
                        f"{pair_id} con dang bay. Chua co client_position_id de dong. Se dong "
                        "ngay khi tuong quan xong; neu khong tuong quan duoc, CAN DOI CHIEU.",
                        pair_id=pair_id)
            return False

        # -- 7.6: mỗi cặp chỉ một lệnh đóng đang chạy ------------------------------------------
        if self.db.list_inflight_commands(pair_id):
            log.info("Cap %s da co lenh dong dang chay, khong tao them", pair_id,
                     extra={"pair_id": pair_id})
            return False

        self._canh_bao_neu_ghep_suy_doan(pair)

        client = self.db.get_client_account(pair["client_id"])
        self.db.update_pair(pair_id, status="CLOSING", close_time_master=now,
                            close_source=close_source)
        await self._gui_lenh_dong(pair, client, "CLOSE",
                                  {"position_id": pair["client_position_id"]})
        return True

    async def _close_pair_partially(self, pair: sqlite3.Row, event: sqlite3.Row,
                                    data: dict[str, Any]) -> bool:
        """Master đóng bớt: đóng đúng tỷ lệ tương ứng bên Client (plan 7.3)."""
        pair_id = pair["pair_id"]
        volume_after = event["volume_after"]
        truoc = float(pair["master_current_volume"] or 0.0)
        delta = data.get("volume_delta")
        if delta is None:
            delta = max(truoc - float(volume_after), 0.0)

        # Ghi nhận volume Master mới ngay: đó là **sự thật do EA báo**, không phụ thuộc việc
        # bên Client có đóng được hay không.
        self.db.update_pair(pair_id, master_current_volume=float(volume_after))

        if pair["client_position_id"] is None:
            self._alert("WARNING", "PARTIAL_CLOSE_WHILE_PENDING",
                        f"Master dong bot trong khi cap {pair_id} chua tuong quan xong. "
                        "Bo qua lan nay; phan lech se duoc dong o lan sau hoac khi dong het.",
                        pair_id=pair_id)
            return False

        if truoc <= 0 or delta <= 0:
            log.info("Cap %s: khong tinh duoc ty le dong (truoc=%s delta=%s)",
                     pair_id, truoc, delta, extra={"pair_id": pair_id})
            return False

        if self.db.list_inflight_commands(pair_id):
            log.info("Cap %s da co lenh dong dang chay, bo qua lan dong bot nay", pair_id,
                     extra={"pair_id": pair_id})
            return False

        client = self.db.get_client_account(pair["client_id"])
        spec = self.db.get_symbol_spec(client["agent_id"], pair["client_symbol"])
        if spec is None:
            self._alert("ERROR", "NO_SYMBOL_SPEC",
                        f"Khong co spec cua {pair['client_symbol']} de lam tron lenh dong bot "
                        f"cua cap {pair_id}",
                        pair_id=pair_id)
            return False

        con_lai = to_decimal(pair["client_current_volume"] or 0.0)
        ty_le = to_decimal(delta) / to_decimal(truoc)
        # Làm tròn XUỐNG: đóng thiếu còn sửa được ở lần sau, đóng thừa thì không.
        can_dong = round_to_step(con_lai * ty_le, to_decimal(spec["volume_step"]), "DOWN")

        if can_dong <= 0:
            # ERROR (B-08): phan Client dang le phai dong bi bo lai, va phan lech nay
            # TICH LUY qua tung lan dong chu khong tu bien mat.
            self._alert("ERROR", "PARTIAL_CLOSE_ROUNDS_TO_ZERO",
                        f"Cap {pair_id}: Master dong {delta} ({ty_le:.4f}) nhung phan Client "
                        f"tuong ung lam tron xuong ra 0 (con {con_lai}, step "
                        f"{spec['volume_step']}). Khong gui lenh; phan lech tich luy lai.",
                        pair_id=pair_id)
            return False

        self._canh_bao_neu_ghep_suy_doan(pair)
        self.db.update_pair(pair_id, status="PARTIALLY_CLOSED")
        await self._gui_lenh_dong(pair, client, "CLOSE_PARTIAL",
                                  {"position_id": pair["client_position_id"],
                                   "volume": float(can_dong)})
        return True

    # -- Client đóng (plan 7.4, 7.5) -----------------------------------------------------------

    async def on_client_close(self, event: sqlite3.Row,
                              agent: sqlite3.Row) -> tuple[str, str | None, str | None]:
        position_id = event["position_id"]
        if not position_id:
            return "ERROR", "Event dong tu Client thieu position_id", None
        volume_after = event["volume_after"]
        if volume_after is None:
            return "ERROR", "Event dong thieu volume_after (D-14)", None

        client = self.db.query_one(
            "SELECT * FROM client_account WHERE agent_id = ?", (agent["agent_id"],))
        if client is None:
            return "IGNORED", "Agent CLIENT chua duoc cau hinh", None

        # **Toàn bộ** cách phân biệt lệnh của bot với lệnh người dùng mở tay ở phía Client
        # (D-07b). Không dùng magic: vị thế mở qua giao diện có `magic = 0`.
        pair = self.db.find_pair_by_client_position(client["client_id"], position_id)
        if pair is None:
            return "IGNORED", "Vi the mo tay, khong thuoc cap nao (FR-12)", None

        if event["caused_by_command_id"]:
            # Do chính bot đóng. Trạng thái đã xử lý ở đường ack.
            return "IGNORED", "Do bot gay ra, khong lan truyen", pair["pair_id"]

        cho_phep, mode = self._sync_allowed()
        if not cho_phep:
            return "IGNORED", f"run_mode = {mode} nen khong dong bo dong", pair["pair_id"]

        if volume_after > 0:
            # Đóng một phần từ phía Client: KHÔNG cascade (D-11). Cặp đã lệch tỷ lệ.
            self.db.update_pair(pair["pair_id"], client_current_volume=float(volume_after),
                                status="PARTIALLY_CLOSED")
            self._alert("WARNING", "CLIENT_PARTIAL_CLOSE",
                        f"Client dong bot cap {pair['pair_id']}, con {volume_after}. "
                        "KHONG cascade (D-11); cap nay da lech ty le so voi Master.",
                        pair_id=pair["pair_id"], agent_id=agent["agent_id"])
            return "DONE", None, pair["pair_id"]

        if not client["can_close_master"]:
            return await self._client_dong_khong_cascade(pair, client, agent)
        return await self._cascade(pair, client, agent)

    async def _client_dong_khong_cascade(self, pair: sqlite3.Row, client: sqlite3.Row,
                                         agent: sqlite3.Row) -> tuple[str, str | None, str]:
        """Công tắc TẮT — mặc định (D-20). Master giữ nguyên và **đang phơi nhiễm**."""
        pair_id = pair["pair_id"]
        self.db.update_pair(pair_id, status="ORPHANED", orphan_side="MASTER",
                            close_source="CLIENT", close_time_client=utc_now_iso(),
                            client_current_volume=0.0)
        self._alert("ERROR", "ORPHANED_MASTER",
                    f"Client dong cap {pair_id} nhung can_close_master = 0 nen Master giu "
                    f"nguyen. Master {pair['master_position_id']} dang pho nhiem "
                    f"{pair['master_current_volume']} lot tren {pair['client_symbol']} "
                    "ma khong con doi ung.",
                    pair_id=pair_id, agent_id=agent["agent_id"])
        return "DONE", None, pair_id

    async def _cascade(self, pair: sqlite3.Row, client: sqlite3.Row,
                       agent: sqlite3.Row) -> tuple[str, str | None, str]:
        """Công tắc BẬT — phần nguy hiểm nhất của hệ thống (plan 7.5, D-09, D-10)."""
        pair_id = pair["pair_id"]
        master_position_id = pair["master_position_id"]
        master = self.db.get_master_position(master_position_id)
        if master is None:
            self._alert("ERROR", "CASCADE_NO_MASTER",
                        f"Khong tim thay vi the Master {master_position_id} de cascade tu cap "
                        f"{pair_id}",
                        pair_id=pair_id)
            return "ERROR", "khong tim thay vi the Master", pair_id

        self.db.update_pair(pair_id, status="CLOSED", close_source="CLIENT",
                            close_time_client=utc_now_iso(), client_current_volume=0.0)

        if self.db.list_inflight_commands(pair_id=None) and self._dang_dong_master(
                master_position_id):
            log.info("Master %s da co lenh dong dang chay, khong tao them",
                     master_position_id, extra={"pair_id": pair_id})
            return "DONE", None, pair_id

        self._alert("WARNING", "CASCADE_STARTED",
                    f"Client dong cap {pair_id} va can_close_master = 1: dong vi the Master "
                    f"{master_position_id}, roi moi dong cac Client con lai.",
                    pair_id=pair_id, agent_id=agent["agent_id"])

        command_id = await self._gui_lenh_dong_master(master, master_position_id, pair_id)
        self._spawn(self._cho_master_dong(master_position_id, pair_id, command_id))
        return "DONE", None, pair_id

    async def _gui_lenh_dong_master(self, master: sqlite3.Row, master_position_id: int,
                                    pair_id: str) -> str:
        """Gửi `CLOSE` cho **EA của Master**.

        Tách riêng vì có hai nơi cần đóng vị thế Master — cascade (D-09) và đóng khẩn cấp — và
        trước phase 11 thì đường khẩn cấp **không có** bước này: nó đóng phía Client rồi dừng,
        biến một sổ đang hedge thành một sổ phơi nhiễm một chiều mà vẫn báo là đã xong.
        """
        return await self.dispatcher.dispatch(
            master["agent_id"], "CLOSE", pair_id=pair_id,
            payload={"position_id": master_position_id,
                     "magic": self.db.get_agent(master["agent_id"])["magic_number"]},
            deadline_ms=self.db.get_config_int("cascade_wait_master_ms",
                                               DEFAULT_CASCADE_WAIT_MS),
        )

    def _dang_dong_master(self, master_position_id: int) -> bool:
        row = self.db.query_one(
            "SELECT 1 FROM command c JOIN pair p ON p.pair_id = c.pair_id "
            "WHERE c.type = 'CLOSE' AND c.status IN ('PENDING','SENT') "
            "AND p.master_position_id = ? LIMIT 1",
            (master_position_id,))
        return row is not None

    async def _cho_master_dong(self, master_position_id: int, pair_id: str,
                               command_id: str) -> None:
        """Chờ Master xác nhận đã đóng rồi mới đụng tới các Client còn lại.

        **Không được đi đường tắt.** Nếu Master từ chối lệnh đóng — requote liên tục, thị trường
        đóng cửa, mất kết nối — mà ta đã đóng B và C rồi thì cả nhóm mất hedge trong khi Master
        vẫn còn vị thế. Đóng trước hỏi sau ở đây là sai (D-10).
        """
        han_ms = self.db.get_config_int("cascade_wait_master_ms", DEFAULT_CASCADE_WAIT_MS)
        het = asyncio.get_running_loop().time() + han_ms / 1000.0
        while asyncio.get_running_loop().time() < het:
            master = self.db.get_master_position(master_position_id)
            if master is not None and master["status"] == "CLOSED":
                await self._dong_cac_client_con_lai(master_position_id, pair_id)
                return
            command = self.db.get_command(command_id)
            if command is not None and command["status"] in ("ACK_FAILED", "TIMEOUT"):
                break
            await asyncio.sleep(0.2)

        # Hết hạn hoặc Master từ chối: KHÔNG cascade. Các Client còn lại giữ nguyên vị thế.
        con_lai = [p for p in self.db.list_pairs_for_master_position(master_position_id)
                   if p["status"] not in TERMINAL_STATUSES]
        for p in con_lai:
            self.db.update_pair(p["pair_id"], status="ORPHANED", orphan_side="CLIENT")
        self._alert("CRITICAL", "CASCADE_MASTER_TIMEOUT",
                    f"Master {master_position_id} khong xac nhan dong trong {han_ms}ms. "
                    f"KHONG cascade: {len(con_lai)} cap chuyen ORPHANED va cac Client con lai "
                    "VAN GIU vi the. Can nguoi xu ly.",
                    pair_id=pair_id)

    async def _dong_cac_client_con_lai(self, master_position_id: int,
                                       pair_id_goc: str) -> None:
        con_lai = [p for p in self.db.list_pairs_for_master_position(master_position_id)
                   if p["status"] not in TERMINAL_STATUSES and p["pair_id"] != pair_id_goc]
        if not con_lai:
            log.info("Cascade tu cap %s: khong con Client nao khac", pair_id_goc,
                     extra={"pair_id": pair_id_goc})
            return
        log.info("Master %s da xac nhan dong, dong tiep %d Client con lai",
                 master_position_id, len(con_lai))
        for p in con_lai:
            await self._close_pair_fully(p, "CLIENT", None)

    # -- ack và timeout ------------------------------------------------------------------------

    async def on_close_acked(self, command: sqlite3.Row, message: Any) -> None:
        pair = self.db.get_pair(command["pair_id"])
        if pair is None:
            return
        target = self.db.get_agent(command["target_agent_id"])
        la_master = target is not None and target["role"] == "MASTER"

        if message.status in ("ok", "already_closed"):
            # `already_closed` là kết quả **bình thường** khi hai bên cùng đóng gần như đồng
            # thời (FR-18), không phải lỗi và không tạo alert.
            if la_master:
                self.db.set_master_position_status(pair["master_position_id"], "CLOSED",
                                                   current_volume=0.0,
                                                   close_time=utc_now_iso())
                # Bay gio moi CHAC CHAN chan Master da phang, nen moi duoc ghi 0 vao cac cap
                # dung chung vi the nay. `mark_pair_closed` co y khong tu ghi con so nay khi
                # chi co ack cua Client (F-01) — cai gia la phai don not o day, neu khong cap
                # se nam lai voi mot volume Master cu vinh vien.
                self.db.zero_master_volume(pair["master_position_id"])
                return
            if command["type"] == "CLOSE_PARTIAL":
                await self._sau_dong_bot(pair, message)
            else:
                self.db.mark_pair_closed(pair["pair_id"],
                                         close_source=pair["close_source"] or "MASTER",
                                         close_time_client=utc_now_iso())
                log.info("Cap %s da dong xong", pair["pair_id"],
                         extra={"pair_id": pair["pair_id"]})
            return

        if message.status == "unknown":
            self.db.update_pair(pair["pair_id"], error_message="CLOSE_ACK_UNKNOWN")
            self._alert("CRITICAL", "CLOSE_ACK_UNKNOWN",
                        f"Agent khong biet lenh dong cua cap {pair['pair_id']} da thuc hien hay "
                        "chua. KHONG thu lai; cho doi chieu.",
                        pair_id=pair["pair_id"], agent_id=command["target_agent_id"])
            return

        await self._dong_that_bai(pair, command, message, la_master)

    async def _sau_dong_bot(self, pair: sqlite3.Row, message: Any) -> None:
        # Trừ bằng `Decimal`, không bằng float. `0.05 - 0.02` trong float ra
        # 0.030000000000000002, và sai số đó **tích luỹ** qua nhiều lần đóng một phần liên
        # tiếp — đúng thứ mục 7.3 yêu cầu tính chính xác. Đo được ở nghiệm thu phase 7.
        con_dec = max(to_decimal(pair["client_current_volume"] or 0.0)
                      - to_decimal(message.executed_volume or 0.0), Decimal(0))
        con = float(con_dec)
        if con <= 0:
            self.db.mark_pair_closed(pair["pair_id"],
                                     close_source=pair["close_source"] or "MASTER",
                                     close_time_client=utc_now_iso())
            return
        self.db.update_pair(pair["pair_id"], client_current_volume=con,
                            status="PARTIALLY_CLOSED")
        log.info("Cap %s dong bot xong, Client con %s", pair["pair_id"], con,
                 extra={"pair_id": pair["pair_id"]})

    async def _dong_that_bai(self, pair: sqlite3.Row, command: sqlite3.Row, message: Any,
                             la_master: bool) -> None:
        pair_id = pair["pair_id"]
        self.db.update_pair(pair_id, error_code=message.retcode,
                            error_message=(message.retmsg or "")[:500])
        side = "MASTER" if la_master else "CLIENT"
        self.db.update_pair(pair_id, status="ORPHANED", orphan_side=side)
        self._alert("CRITICAL", "CLOSE_FAILED",
                    f"Dong cap {pair_id} that bai, retcode {message.retcode} "
                    f"{message.retmsg or ''}. Cap chuyen ORPHANED phia {side}. Can nguoi xu ly.",
                    pair_id=pair_id, agent_id=command["target_agent_id"])

    def on_close_timeout(self, command: sqlite3.Row) -> None:
        pair = self.db.get_pair(command["pair_id"]) if command["pair_id"] else None
        if pair is None or pair["status"] in TERMINAL_STATUSES:
            return
        self.db.update_pair(pair["pair_id"], error_message="CLOSE_TIMEOUT")
        self._alert("CRITICAL", "CLOSE_TIMEOUT",
                    f"Lenh dong cua cap {pair['pair_id']} qua han ma chua co ack. KHONG tu dong "
                    "thu lai; cho doi chieu.",
                    pair_id=pair["pair_id"], agent_id=command["target_agent_id"])

    # -- EMERGENCY (plan 7.8) ------------------------------------------------------------------

    async def emergency_close_all(self) -> dict[str, int]:
        """Đóng toàn bộ cặp đang quản lý: **Client trước, Master sau**.

        Thứ tự không đảo được: đóng Master trước sẽ kích hoạt đồng bộ đóng thông thường và làm
        rối trạng thái ngay giữa lúc đang cần mọi thứ đơn giản nhất.

        Tới hết phase 10 hàm này **chỉ làm vế đầu**: nó gửi lệnh đóng cho Client rồi dừng, không
        có một dòng nào đụng tới Master, trong khi docstring và alert đều nói "Client trước Master
        sau". Hậu quả là nút dừng khẩn cấp biến một sổ đang hedge đầy đủ thành một sổ phơi nhiễm
        một chiều — rồi báo thành công. Kiểm toán 2026-09-06 bắt được (F-01); phase 11 sửa.

        Trả về số lệnh đã gửi cho **từng vế**, không phải số cặp được xét — con số cũ (`len(pairs)`)
        báo ra là 3 kể cả khi không đóng được gì.
        """
        pairs = self.db.query_all(
            "SELECT * FROM pair WHERE status NOT IN ('CLOSED','OPEN_FAILED') ORDER BY pair_id")
        if not pairs:
            return {"client": 0, "master": 0}
        self._alert("CRITICAL", "EMERGENCY_CLOSE_ALL",
                    f"run_mode = EMERGENCY: dong toan bo {len(pairs)} cap, Client truoc Master sau.")

        lenh_client: list[str] = []
        for pair in pairs:
            client = self.db.get_client_account(pair["client_id"])
            if pair["client_position_id"] is not None and not self.db.list_inflight_commands(
                    pair["pair_id"]):
                self.db.update_pair(pair["pair_id"], status="CLOSING", close_source="BOT")
                lenh_client.append(await self._gui_lenh_dong(
                    pair, client, "CLOSE", {"position_id": pair["client_position_id"]}))

        await self._cho_lenh_xong(lenh_client)
        so_master = await self._dong_cac_master(pairs)
        return {"client": len(lenh_client), "master": so_master}

    async def _cho_lenh_xong(self, command_ids: list[str], han_sec: float = 10.0) -> None:
        """Chờ các lệnh rời khỏi hàng đợi, có hạn.

        Đây chính là chữ "trước" trong "Client trước, Master sau". Hết hạn thì vẫn đi tiếp: một
        Client không ack **không được** trở thành lý do để vị thế Master nằm lại mà không ai đóng.
        """
        if not command_ids:
            return
        het = asyncio.get_running_loop().time() + han_sec
        while asyncio.get_running_loop().time() < het:
            con = [c for c in command_ids
                   if (row := self.db.get_command(c)) is not None
                   and row["status"] in ("PENDING", "SENT")]
            if not con:
                return
            await asyncio.sleep(0.2)
        log.warning("Dong khan cap: %d lenh Client chua xong sau %.0fs, van dong Master",
                    len(command_ids), han_sec)

    async def _dong_cac_master(self, pairs: list[sqlite3.Row]) -> int:
        """Đóng **mỗi vị thế Master đúng một lần**, kể cả khi nhiều Client dùng chung nó."""
        so = 0
        for master_position_id in dict.fromkeys(p["master_position_id"] for p in pairs):
            master = self.db.get_master_position(master_position_id)
            if master is None or master["status"] == "CLOSED":
                continue
            if self._dang_dong_master(master_position_id):
                continue
            pair_id = next(p["pair_id"] for p in pairs
                           if p["master_position_id"] == master_position_id)
            await self._gui_lenh_dong_master(master, master_position_id, pair_id)
            so += 1
        return so

    # -- tiện ích ------------------------------------------------------------------------------

    async def _gui_lenh_dong(self, pair: sqlite3.Row, client: sqlite3.Row, loai: str,
                             payload: dict[str, Any]) -> str:
        """Gửi lệnh đóng tới **EA của Client**, không phải clicker.

        Phase 6b thêm agent thứ hai cho mỗi Client và clicker chỉ nhận `OPEN_UI`. Schema cũng
        không có loại `CLOSE_UI`, nên định tuyến sai bị chặn ở hai lớp — nhưng viết ra ở đây để
        không ai phải suy luận.
        """
        agent_id = client["agent_id"]
        payload = {**payload, "magic": self.db.get_agent(agent_id)["magic_number"]}
        return await self.dispatcher.dispatch(
            agent_id, loai, pair_id=pair["pair_id"], payload=payload,
            deadline_ms=max(int(client["max_event_age_ms"]), DEFAULT_CLOSE_DEADLINE_MS),
        )

    def _canh_bao_neu_ghep_suy_doan(self, pair: sqlite3.Row) -> None:
        """Lỗ hổng 2 (plan 7.4b): cặp được ghép bằng suy đoán thì cú đóng này có thể là đóng
        **vị thế của người dùng**, không phải của bot.

        Không chặn — để nguyên nghĩa là giữ mãi một vị thế mà sổ sách tin là hedge trong khi
        Master đã đóng. Nhưng nó phải hiện lên đỏ chứ không được im lặng.
        """
        row = self.db.query_one(
            "SELECT 1 FROM alert WHERE code = 'UI_CORRELATE_HEURISTIC' AND pair_id = ? LIMIT 1",
            (pair["pair_id"],))
        if row is None:
            return
        self._alert("ERROR", "CLOSING_HEURISTIC_PAIR",
                    f"Cap {pair['pair_id']} duoc ghep bang SUY DOAN (khong khop the tuong quan). "
                    f"Dang dong vi the {pair['client_position_id']} — neu ghep nham thi day la "
                    "vi the cua nguoi dung, khong phai cua bot.",
                    pair_id=pair["pair_id"])


def phan_du_sau_lam_tron(con_lai: Decimal, ty_le: Decimal, step: Decimal) -> Decimal:
    """Phần bị bỏ lại do làm tròn xuống. Tách ra để test được trực tiếp."""
    return con_lai * ty_le - round_to_step(con_lai * ty_le, step, "DOWN")
