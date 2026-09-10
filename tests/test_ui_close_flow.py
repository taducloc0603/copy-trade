"""Test đường ĐÓNG qua giao diện, phía Bridge (`close_route = 'UI'`).

Test quan trọng nhất trong file này là **bộ tương quan đóng**, và lý do đáng nói rõ vì nó không
hiển nhiên:

Đường đóng qua EA có `RememberCause` — EA gọi `OrderSend` nên biết deal nào là con của command
nào và gắn `caused_by_command_id` (D-08). Đường đóng qua **giao diện** không có gì tương đương:
EA không gọi `OrderSend` nên không có gì để nhớ, và hộp thoại đóng **không có ô Comment** nên
mẹo gắn thẻ của D-07b/D-23 cũng không dùng được.

Hệ quả nếu để nguyên: mọi event `position_closed` do chính bot phát ra sẽ về Bridge với
`caused_by_command_id = NULL`, tức mang **đúng dấu hiệu của một lệnh người dùng đóng tay**. Với
`can_close_master = 1`, mỗi lệnh đóng của bot sẽ tự kích hoạt một cascade đóng vị thế Master.
Đó là lỗi mất tiền, không phải lỗi trạng thái — và `test_lenh_dong_cua_bot_KHONG_kich_hoat_cascade`
là bài kiểm tra tồn tại để chặn nó.

Các cặp ở đây **mở** bằng đường EA cho gọn; hai đường mở không ảnh hưởng gì tới đường đóng.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest

from bridge.clock import to_iso, utc_now
from bridge.db.repo import Database
from bridge.engine.processor import EventProcessor
from bridge.protocol.auth import hash_token
from bridge.protocol.dispatcher import CommandDispatcher
from bridge.protocol.server import BridgeServer, ServerConfig
from tests.conftest import MASTER_AGENT
from tests.mock_agent import MockAgent
from tests.mock_clicker import MockClicker
from tests.test_server import MASTER_LOGIN, MASTER_TOKEN, _wait_until

SYMBOL = "XAUUSD"
CLIENT_SYMBOL = "XAUUSDm"
MAGIC = 770001
CLIENT_ID = "CL-01"
CLIENT_AGENT = "AG-CLIENT-1"
CLICKER_AGENT = "AG-CLICKER-1"
CLIENT_TOKEN = "token-client-1-xxxxxxxxxxxx"
CLICKER_TOKEN = "token-clicker-1-xxxxxxxxxx"

#: `DEAL_REASON`. `0` là CLIENT (đặt qua giao diện), `3` là EXPERT (đặt qua `OrderSend`).
REASON_CLIENT = 0
REASON_EXPERT = 3


@dataclass
class Env:
    db: Database
    server: BridgeServer
    dispatcher: CommandDispatcher
    processor: EventProcessor
    master: MockAgent
    client: MockAgent
    clicker: MockClicker
    _seq: int = 0
    _alert_moc: int = 0
    _positions: dict[int, float] = field(default_factory=dict)

    # -- kích thích ------------------------------------------------------------------------

    async def master_open(self, position_id: int, volume: float = 1.0) -> str:
        self._seq += 1
        eid = f"EVT-M-{position_id}-{self._seq}"
        await self.master.send_raw({
            "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": eid, "seq": self._seq,
            "type": "position_opened",
            "data": {"position_id": position_id, "deal_entry": "IN", "symbol": SYMBOL,
                     "direction": "BUY", "volume_delta": volume, "volume_after": volume,
                     "price": 2650.0, "magic": 0},
        })
        await _wait_until(lambda: self.db.get_event(eid) is not None)
        await self.processor.process_pending()
        await _wait_until(lambda: self.pair_of(position_id) is not None)
        pair = self.pair_of(position_id)
        await _wait_until(lambda: self.db.get_pair(pair["pair_id"])["status"] == "OPEN",
                          timeout=3.0)
        self._positions[position_id] = volume
        return pair["pair_id"]

    async def master_close(self, position_id: int, volume_after: float = 0.0,
                           volume_delta: float | None = None) -> None:
        truoc = self._positions.get(position_id, 1.0)
        delta = truoc - volume_after if volume_delta is None else volume_delta
        self._seq += 1
        eid = f"EVT-MC-{position_id}-{self._seq}"
        await self.master.send_raw({
            "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": eid, "seq": self._seq,
            "type": "position_closed" if volume_after <= 0 else "position_changed",
            "data": {"position_id": position_id, "deal_entry": "OUT", "symbol": SYMBOL,
                     "direction": "BUY", "volume_delta": delta, "volume_after": volume_after,
                     "price": 2660.0, "magic": 0},
        })
        await _wait_until(lambda: self.db.get_event(eid) is not None)
        self._positions[position_id] = volume_after
        await self.processor.process_pending()

    async def client_close(self, position_id: int, volume_after: float = 0.0,
                           volume_delta: float = 0.5, reason: int = REASON_CLIENT) -> None:
        """Event đóng từ Client, `caused_by_command_id` **luôn NULL**.

        Đúng như đời thật: khi lệnh đóng đi qua giao diện, EA không có gì để gắn cha, nên event
        của một lần đóng do bot gây ra **không phân biệt được** với một lần người dùng đóng tay
        nếu chỉ nhìn trường này.
        """
        await self.client.send_event(
            "position_closed" if volume_after <= 0 else "position_changed",
            position_id=position_id, deal_entry="OUT", symbol=CLIENT_SYMBOL,
            direction="SELL", volume_delta=volume_delta, volume_after=volume_after,
            reason=reason)
        await _wait_until(lambda: self.db.query_one(
            "SELECT 1 FROM event WHERE agent_id = ? AND position_id = ? "
            "AND type LIKE 'position_c%'", (self.client.agent_id, position_id)) is not None)
        await self.processor.process_pending()

    # -- quan sát --------------------------------------------------------------------------

    def pair_of(self, master_position_id: int):
        return self.db.query_one(
            "SELECT * FROM pair WHERE master_position_id = ? AND client_id = ?",
            (master_position_id, CLIENT_ID))

    def commands(self, loai: str | None = None) -> list:
        if loai is None:
            return self.db.query_all("SELECT * FROM command ORDER BY created_at, command_id")
        return self.db.query_all(
            "SELECT * FROM command WHERE type = ? ORDER BY created_at, command_id", (loai,))

    def alerts(self, code: str) -> list:
        return [a for a in self.db.query_all("SELECT * FROM alert WHERE id > ?",
                                             (self._alert_moc,)) if a["code"] == code]

    def moc_alert(self) -> None:
        self._alert_moc = self.db.query_one("SELECT COALESCE(MAX(id),0) n FROM alert")["n"]

    async def cho_pair(self, pair_id: str, status: str, timeout: float = 3.0) -> None:
        await _wait_until(lambda: self.db.get_pair(pair_id)["status"] == status, timeout=timeout)


async def _dung_db(db: Database, can_close_master: int, close_route: str) -> None:
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.replace_symbol_specs(MASTER_AGENT, [{
        "symbol": SYMBOL, "digits": 2, "point": 0.01, "volume_min": 0.01,
        "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])

    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash=hash_token(CLIENT_TOKEN),
                    magic_number=MAGIC, account_login=222221)
    db.upsert_agent(CLICKER_AGENT, role="CLICKER", token_hash=hash_token(CLICKER_TOKEN),
                    magic_number=MAGIC, account_login=222221)
    db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, copy_mode="OPPOSITE",
                             volume_multiplier=0.5, can_close_master=can_close_master,
                             clicker_agent_id=CLICKER_AGENT, close_route=close_route)
    db.upsert_symbol_map(CLIENT_ID, SYMBOL, CLIENT_SYMBOL)
    db.replace_symbol_specs(CLIENT_AGENT, [{
        "symbol": CLIENT_SYMBOL, "digits": 2, "point": 0.01, "volume_min": 0.01,
        "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])
    db.set_config("run_mode", "RUNNING")


async def _make_env(db: Database, can_close_master: int = 0,
                    close_route: str = "UI") -> AsyncIterator[Env]:
    await _dung_db(db, can_close_master, close_route)
    server = BridgeServer(db, ServerConfig(host="127.0.0.1", port=0, hello_timeout_sec=1.0,
                                           monitor_interval_sec=0.05,
                                           heartbeat_timeout_ms=8000))
    dispatcher = CommandDispatcher(db, server)
    processor = EventProcessor(db, server, dispatcher)
    await server.start()

    master = MockAgent(host="127.0.0.1", port=server.port, token=MASTER_TOKEN, role="MASTER",
                       account_login=MASTER_LOGIN, magic=MAGIC, emit_events=False)
    await master.start()
    client = MockAgent(host="127.0.0.1", port=server.port, token=CLIENT_TOKEN, role="CLIENT",
                       account_login=222221, magic=MAGIC, known_symbols={CLIENT_SYMBOL})
    await client.start()
    clicker = MockClicker(host="127.0.0.1", port=server.port, token=CLICKER_TOKEN,
                          account_login=222221, magic=0)
    await clicker.start()
    await _wait_until(lambda: db.get_agent(CLICKER_AGENT)["status"] == "ONLINE", timeout=3.0)

    e = Env(db, server, dispatcher, processor, master, client, clicker)
    e.moc_alert()
    try:
        yield e
    finally:
        await processor.stop()
        await master.kill()
        await client.kill()
        await clicker.kill()
        await server.stop()


@pytest.fixture
async def env(db: Database) -> AsyncIterator[Env]:
    async for e in _make_env(db):
        yield e


@pytest.fixture
async def env_cascade(db: Database) -> AsyncIterator[Env]:
    async for e in _make_env(db, can_close_master=1):
        yield e


def _client_pos(env: Env, pair_id: str) -> int:
    return env.db.get_pair(pair_id)["client_position_id"]


# ---------------------------------------------------------------------------------------------
# Định tuyến
# ---------------------------------------------------------------------------------------------

async def test_master_dong_sinh_CLOSE_UI_gui_toi_clicker(env: Env) -> None:
    pair_id = await env.master_open(5001)
    await env.master_close(5001)

    lenh = env.commands("CLOSE_UI")
    assert len(lenh) == 1, "Phai la CLOSE_UI, khong phai CLOSE"
    assert lenh[0]["target_agent_id"] == CLICKER_AGENT, "Gui cho clicker, khong phai EA"
    assert lenh[0]["pair_id"] == pair_id
    assert env.commands("CLOSE") == []


async def test_payload_dong_qua_giao_dien_khong_mang_magic(env: Env) -> None:
    """`magic` không đặt được qua giao diện, và clicker từ chối thẳng payload có nó (D-22)."""
    import json

    await env.master_open(5002)
    await env.master_close(5002)

    payload = json.loads(env.commands("CLOSE_UI")[0]["payload_json"])
    assert "magic" not in payload
    assert payload["position_id"] > 0


async def test_dong_mot_phan_sinh_CLOSE_UI_PARTIAL_kem_volume(env: Env) -> None:
    pair_id = await env.master_open(5003, volume=1.0)
    await env.master_close(5003, volume_after=0.5)

    import json
    lenh = env.commands("CLOSE_UI_PARTIAL")
    assert len(lenh) == 1
    payload = json.loads(lenh[0]["payload_json"])
    # Master đóng 50% của 1.0; Client giữ 0.5 nên phần tương ứng là 0.25.
    assert payload["volume"] == pytest.approx(0.25)
    assert env.db.get_pair(pair_id)["status"] in ("PARTIALLY_CLOSED", "CLOSED")


async def test_close_route_EA_van_di_duong_cu_va_KHONG_bao_dong(db: Database) -> None:
    """Client chưa bật đường giao diện thì đóng qua EA là **bình thường**, không phải sự cố."""
    async for e in _make_env(db, close_route="EA"):
        await e.master_open(5004)
        await e.master_close(5004)

        assert len(e.commands("CLOSE")) == 1
        assert e.commands("CLOSE_UI") == []
        assert e.alerts("CLOSE_FELL_BACK_TO_EA") == [], "Cau hinh binh thuong khong duoc bao dong"
        return


# ---------------------------------------------------------------------------------------------
# Bộ tương quan đóng — phần nguy hiểm nhất
# ---------------------------------------------------------------------------------------------

async def test_lenh_dong_cua_bot_KHONG_kich_hoat_cascade(env_cascade: Env) -> None:
    """**Bài kiểm tra quan trọng nhất của cả thay đổi này.**

    `can_close_master = 1`. Bot gửi `CLOSE_UI`, rồi event đóng về với `caused_by_command_id`
    NULL — vì đóng qua giao diện thì EA không có gì để gắn cha. Không có bộ tương quan thì
    `on_client_close` sẽ hiểu đây là người dùng đóng tay và **cascade đóng luôn vị thế Master**.
    """
    pair_id = await env_cascade.master_open(5010)
    pos = _client_pos(env_cascade, pair_id)
    await env_cascade.master_close(5010)
    assert len(env_cascade.commands("CLOSE_UI")) == 1

    await env_cascade.client_close(pos)

    assert env_cascade.commands("CLOSE") == [], "KHONG duoc sinh lenh dong Master"
    assert env_cascade.alerts("CASCADE_STARTED") == []
    master = env_cascade.db.get_master_position(5010)
    assert master["status"] == "CLOSED", "Master dong vi CHINH no dong truoc, khong phai vi cascade"


async def test_event_dong_do_bot_gay_ra_duoc_nhan_cha(env: Env) -> None:
    """Không gắn cha thì nhật ký event nói dối: lệnh của bot trông y hệt lệnh đóng tay."""
    pair_id = await env.master_open(5011)
    pos = _client_pos(env, pair_id)
    await env.master_close(5011)
    command_id = env.commands("CLOSE_UI")[0]["command_id"]

    await env.client_close(pos)

    row = env.db.query_one(
        "SELECT caused_by_command_id FROM event WHERE agent_id = ? AND position_id = ? "
        "AND type = 'position_closed'", (CLIENT_AGENT, pos))
    assert row["caused_by_command_id"] == command_id


async def test_nguoi_dung_dong_tay_van_cascade_nhu_cu(env_cascade: Env) -> None:
    """Bộ tương quan **không được nuốt** lệnh đóng tay của người dùng (FR-22 vẫn phải chạy)."""
    pair_id = await env_cascade.master_open(5012)
    pos = _client_pos(env_cascade, pair_id)

    # Khong co lenh CLOSE_UI nao duoc gui -> khong co cha de nhan.
    await env_cascade.client_close(pos)

    assert len(env_cascade.commands("CLOSE")) == 1, "Phai cascade dong Master"
    assert env_cascade.commands("CLOSE")[0]["target_agent_id"] == MASTER_AGENT
    assert env_cascade.alerts("CASCADE_STARTED")


async def test_ngoai_cua_so_grace_thi_van_coi_la_dong_tay(env_cascade: Env) -> None:
    """Cửa sổ nhận cha phải **hẹp**: quá hạn rồi thì một cú đóng là của người dùng."""
    pair_id = await env_cascade.master_open(5013)
    pos = _client_pos(env_cascade, pair_id)
    await env_cascade.master_close(5013)

    # Lenh da ack xong tu lau: day ack ve qua khu, ngoai cua so grace.
    env_cascade.db.set_config("ui_close_correlate_grace_ms", "1")
    cmd = env_cascade.commands("CLOSE_UI")[0]
    with env_cascade.db.transaction() as conn:
        conn.execute("UPDATE command SET status = 'ACK_OK', acked_at = ? WHERE command_id = ?",
                     ("2000-01-01T00:00:00.000Z", cmd["command_id"]))

    await env_cascade.client_close(pos)

    assert len(env_cascade.commands("CLOSE")) == 1, "Ngoai cua so thi phai cascade"


# ---------------------------------------------------------------------------------------------
# Rơi về đường EA khi clicker hỏng
# ---------------------------------------------------------------------------------------------

async def test_clicker_chet_thi_roi_ve_EA_va_bao_dong_CRITICAL(env: Env) -> None:
    """Không **mở** được thì an toàn; không **đóng** được thì không. Nên ở đây được rơi về EA."""
    pair_id = await env.master_open(5020)
    await env.clicker.kill()
    await _wait_until(lambda: env.db.get_agent(CLICKER_AGENT)["status"] != "ONLINE", timeout=5.0)

    await env.master_close(5020)

    assert len(env.commands("CLOSE")) == 1, "Van phai dong duoc"
    assert env.commands("CLOSE_UI") == []
    canh_bao = env.alerts("CLOSE_FELL_BACK_TO_EA")
    assert canh_bao and canh_bao[0]["level"] == "CRITICAL"
    assert "EXPERT" in canh_bao[0]["message"], "Phai noi ro cai gia da tra"
    assert env.db.get_pair(pair_id)["error_message"] == "CLOSE_FELL_BACK_TO_EA"


async def test_dat_SKIP_thi_khong_dong_gi_ca_va_bao_dong(env: Env) -> None:
    """Lựa chọn có ý thức: chấp nhận giữ vị thế trần thay vì để một deal mang `EXPERT`."""
    await env.master_open(5021)
    env.db.set_config("close_degraded_fallback", "SKIP")
    await env.clicker.kill()
    await _wait_until(lambda: env.db.get_agent(CLICKER_AGENT)["status"] != "ONLINE", timeout=5.0)

    await env.master_close(5021)

    assert env.commands("CLOSE") == [] and env.commands("CLOSE_UI") == []
    assert env.alerts("CLOSE_KHONG_GUI_DUOC")


# ---------------------------------------------------------------------------------------------
# `DEAL_REASON` — biến mục tiêu thành thứ đo được
# ---------------------------------------------------------------------------------------------

async def test_deal_dong_mang_CLIENT_thi_ghi_lai_va_khong_bao_dong(env: Env) -> None:
    pair_id = await env.master_open(5030)
    pos = _client_pos(env, pair_id)
    await env.master_close(5030)
    await env.client_close(pos, reason=REASON_CLIENT)

    assert env.db.get_pair(pair_id)["client_close_reason"] == REASON_CLIENT
    assert env.alerts("UI_CLOSE_REASON_MISMATCH") == []


async def test_deal_dong_mang_EXPERT_tren_duong_UI_thi_bao_dong_CRITICAL(env: Env) -> None:
    """Đây là toàn bộ mục đích của thay đổi. Sai kênh mà im lặng thì không ai biết cho tới lúc muộn."""
    pair_id = await env.master_open(5031)
    pos = _client_pos(env, pair_id)
    await env.master_close(5031)
    await env.client_close(pos, reason=REASON_EXPERT)

    assert env.db.get_pair(pair_id)["client_close_reason"] == REASON_EXPERT
    canh_bao = env.alerts("UI_CLOSE_REASON_MISMATCH")
    assert canh_bao and canh_bao[0]["level"] == "CRITICAL"


async def test_deal_EXPERT_sau_khi_roi_ve_EA_thi_KHONG_bao_dong_them(env: Env) -> None:
    """Cú rơi về EA đã có alert riêng rồi; báo động lần hai chỉ làm loãng thứ đáng nhìn."""
    pair_id = await env.master_open(5032)
    pos = _client_pos(env, pair_id)
    await env.clicker.kill()
    await _wait_until(lambda: env.db.get_agent(CLICKER_AGENT)["status"] != "ONLINE", timeout=5.0)
    await env.master_close(5032)
    await env.client_close(pos, reason=REASON_EXPERT)

    assert env.db.get_pair(pair_id)["client_close_reason"] == REASON_EXPERT
    assert env.alerts("UI_CLOSE_REASON_MISMATCH") == []


# ---------------------------------------------------------------------------------------------
# Ack — cái bẫy "rơi vào nhánh mặc định rồi bị bỏ qua im lặng"
# ---------------------------------------------------------------------------------------------

async def test_ack_ok_cua_CLOSE_UI_dong_so_dung_cap(env: Env) -> None:
    """Bẫy đã cắn ở phase 6b với `OPEN_UI`: ack rơi vào nhánh mặc định và bị bỏ qua im lặng."""
    pair_id = await env.master_open(5040)
    await env.master_close(5040)
    await env.cho_pair(pair_id, "CLOSED")

    lenh = env.commands("CLOSE_UI")[0]
    assert lenh["status"] == "ACK_OK"
    assert env.db.get_pair(pair_id)["close_source"] == "MASTER"


async def test_ack_already_closed_la_binh_thuong_khong_phai_loi(env: Env) -> None:
    """Quét hết danh sách mà không thấy vị thế nghĩa là nó đã đóng rồi (FR-18)."""
    pair_id = await env.master_open(5041)
    env.clicker.open_positions = set()          # danh sach rong -> khong tim thay
    await env.master_close(5041)
    await env.cho_pair(pair_id, "CLOSED")

    assert env.db.get_pair(pair_id)["status"] == "CLOSED"
    assert env.alerts("CLOSE_FAILED") == []


async def test_ack_ok_cua_CLOSE_UI_PARTIAL_giu_dung_volume_con_lai(env: Env) -> None:
    """Bỏ sót loại này ở nhánh ack nghĩa là đóng bớt bị ghi sổ như đóng hẳn."""
    pair_id = await env.master_open(5042, volume=1.0)
    await env.master_close(5042, volume_after=0.5)
    # Cho tan ACK chu khong chi cho trang thai: `PARTIALLY_CLOSED` duoc dat NGAY LUC GUI lenh,
    # nen cho no la cho mot moc da qua truoc khi volume kip cap nhat.
    await _wait_until(lambda: env.commands("CLOSE_UI_PARTIAL")[0]["status"] == "ACK_OK",
                      timeout=3.0)

    pair = env.db.get_pair(pair_id)
    assert pair["status"] == "PARTIALLY_CLOSED"
    assert pair["client_current_volume"] == pytest.approx(0.25)


async def test_ack_rejected_thi_thu_lai_bang_duong_EA_chu_khong_bo_cuoc(env: Env) -> None:
    """`rejected` nghĩa là **chứng minh được chưa bấm** — đúng trạng thái D-24 cho phép thử lại.

    Nguyên nhân hay gặp nhất ở đường đóng là chuyện vận hành: tab Trade không mở, đọc lại lệch.
    Để cặp thành `ORPHANED` thì vị thế Client vẫn đang mở không có đối ứng — đúng cái mà
    `close_degraded_fallback = EA` sinh ra để tránh.
    """
    pair_id = await env.master_open(5043)
    env.clicker.next_status = "rejected"
    await env.master_close(5043)
    await _wait_until(lambda: len(env.commands("CLOSE")) == 1, timeout=3.0)

    assert env.commands("CLOSE")[0]["target_agent_id"] == CLIENT_AGENT
    assert env.db.get_pair(pair_id)["status"] != "ORPHANED"
    assert env.alerts("CLOSE_FELL_BACK_TO_EA")


async def test_ack_rejected_voi_SKIP_thi_van_ORPHANED(env: Env) -> None:
    """Đặt `SKIP` là chấp nhận giữ vị thế trần thay vì để một deal mang `EXPERT`."""
    pair_id = await env.master_open(5045)
    env.db.set_config("close_degraded_fallback", "SKIP")
    env.clicker.next_status = "rejected"
    await env.master_close(5045)
    await env.cho_pair(pair_id, "ORPHANED")

    assert env.commands("CLOSE") == []
    assert env.alerts("CLOSE_FAILED")


async def test_ack_unknown_van_duoc_nhan_cha_nen_khong_cascade(env_cascade: Env) -> None:
    """Clicker bấm xong rồi chết trước khi báo về: ack `unknown` -> command `TIMEOUT`.

    Lenh **da thuc su khop**. Bo tuong quan chi xet `ACK_OK` se bo sot dung ca nay, va voi
    `can_close_master = 1` thi event dong vua ve se cascade dong vi the Master.
    """
    pair_id = await env_cascade.master_open(5046)
    pos = _client_pos(env_cascade, pair_id)
    env_cascade.clicker.next_status = "unknown"
    await env_cascade.master_close(5046)
    await _wait_until(
        lambda: env_cascade.commands("CLOSE_UI")[0]["status"] == "TIMEOUT", timeout=3.0)

    await env_cascade.client_close(pos)

    assert env_cascade.commands("CLOSE") == [], "KHONG duoc cascade dong Master"
    assert env_cascade.alerts("CASCADE_STARTED") == []


async def test_khong_bao_gio_gui_CLOSE_tran_cho_clicker(env: Env) -> None:
    """Hàng rào chống định tuyến sai: clicker nhận `CLOSE` trần sẽ từ chối, nhưng đừng để tới đó."""
    await env.master_open(5044)
    await env.master_close(5044)
    await asyncio.sleep(0.2)

    cho_clicker = [c for c in env.commands() if c["target_agent_id"] == CLICKER_AGENT]
    assert all(c["type"] in ("OPEN_UI", "CLOSE_UI", "CLOSE_UI_PARTIAL") for c in cho_clicker)
    assert env.clicker.closed, "Clicker phai thuc su nhan va xu ly lenh dong"
