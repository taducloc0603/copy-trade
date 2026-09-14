"""Test đường ĐÓNG phía **Master** qua giao diện (phase 12, D-21c).

Câu hỏi trung tâm khác hẳn phase 11. Ở đó là *"bấm đúng vị thế nào"*; ở đây là **định tuyến và
nhận cha**:

1. Lệnh đóng chân Master phải đi tới **clicker của Master**, không phải clicker của Client và
   không phải EA — nhầm chỗ này thì hoặc deal mang `EXPERT`, hoặc ghi sổ chân Client bằng kết quả
   của một lệnh đóng chân Master.
2. Cú đóng Master **do chính Bridge gây ra** không được nhìn giống một cú đóng tay. EA Master
   không gọi `OrderSend` nên không có gì để gắn cha, y hệt lỗ hổng D-27 đã gặp ở phía Client.

Không cần MT5: hai clicker giả và hai EA giả.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from bridge.clock import to_iso, utc_now
from bridge.db.repo import Database
from bridge.engine.closing import MASTER_CLICKER_KEY, MASTER_CLOSE_ROUTE_KEY
from bridge.engine.processor import EventProcessor
from bridge.protocol.auth import hash_token
from bridge.protocol.dispatcher import CommandDispatcher
from bridge.protocol.server import BridgeServer, ServerConfig
from tests.conftest import MASTER_AGENT
from tests.mock_agent import MockAgent
from tests.mock_clicker import MockClicker
from tests.test_server import MASTER_LOGIN, MASTER_TOKEN, _wait_until

SYMBOL, CLIENT_SYMBOL, MAGIC = "XAUUSD", "XAUUSDm", 770001
CLIENT_ID = "CL-01"
CLIENT_AGENT = "AG-CLIENT-1"
CLICKER_AGENT = "AG-CLICKER-1"
CLICKER_MASTER_AGENT = "AG-CLICKER-MASTER"
CLIENT_TOKEN = "token-client-1-xxxxxxxxxxxx"
CLICKER_TOKEN = "token-clicker-1-xxxxxxxxxx"
CLICKER_MASTER_TOKEN = "token-clicker-master-xxxxx"

MASTER_POS = 9001
CLIENT_POS = 8001
REASON_CLIENT = 0
REASON_EXPERT = 3


@dataclass
class Env:
    db: Database
    processor: EventProcessor
    master: MockAgent
    client: MockAgent
    clicker: MockClicker
    clicker_master: MockClicker
    _seq: int = 0

    def tao_cap(self) -> str:
        """Dựng thẳng một cặp đang mở. Luồng mở là việc của phase 6b, không phải của test này."""
        self.db.upsert_master_position(
            MASTER_POS, agent_id=MASTER_AGENT, symbol=SYMBOL, direction="BUY",
            initial_volume=1.0, current_volume=1.0, status="OPEN")
        pair_id = self.db.create_pending_pair(
            MASTER_POS, CLIENT_ID, copy_mode="OPPOSITE", master_initial_volume=1.0,
            effective_multiplier=0.5, client_symbol=CLIENT_SYMBOL, client_direction="SELL",
            open_time_master=to_iso(utc_now()))
        self.db.mark_pair_open(pair_id, client_position_id=CLIENT_POS, client_ticket=CLIENT_POS,
                               client_volume=0.5)
        return pair_id

    async def client_dong_tay(self) -> None:
        """Người dùng đóng chân Client bằng tay: `caused_by_command_id` NULL, không lệnh nào đang bay."""
        await self.client.send_event(
            "position_closed", position_id=CLIENT_POS, deal_entry="OUT", symbol=CLIENT_SYMBOL,
            direction="SELL", volume_delta=0.5, volume_after=0.0, reason=REASON_CLIENT)
        await _wait_until(lambda: self.db.query_one(
            "SELECT 1 FROM event WHERE agent_id = ? AND position_id = ?",
            (self.client.agent_id, CLIENT_POS)) is not None)
        await self.processor.process_pending()

    async def master_bao_da_dong(self, reason: int = REASON_CLIENT) -> str:
        """EA Master báo vị thế đã đóng, **không** kèm `caused_by_command_id` — như đời thật."""
        self._seq += 1
        eid = f"EVT-MC-{self._seq}"
        await self.master.send_raw({
            "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": eid, "seq": self._seq,
            "type": "position_closed",
            "data": {"position_id": MASTER_POS, "deal_entry": "OUT", "symbol": SYMBOL,
                     "direction": "BUY", "volume_delta": 1.0, "volume_after": 0.0,
                     "price": 2660.0, "magic": 0, "reason": reason},
        })
        await _wait_until(lambda: self.db.get_event(eid) is not None)
        await self.processor.process_pending()
        return eid

    def commands(self, loai: str) -> list:
        return self.db.query_all(
            "SELECT * FROM command WHERE type = ? ORDER BY created_at, command_id", (loai,))

    def alerts(self, code: str) -> list:
        return self.db.query_all("SELECT * FROM alert WHERE code = ? ORDER BY id", (code,))


async def _make_env(db: Database, *, route: str = "UI",
                    khai_clicker_master: bool = True) -> AsyncIterator[Env]:
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash=hash_token(CLIENT_TOKEN),
                    magic_number=MAGIC, account_login=222221)
    db.upsert_agent(CLICKER_AGENT, role="CLICKER", token_hash=hash_token(CLICKER_TOKEN),
                    magic_number=MAGIC, account_login=222221)
    db.upsert_agent(CLICKER_MASTER_AGENT, role="CLICKER",
                    token_hash=hash_token(CLICKER_MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, copy_mode="OPPOSITE",
                             volume_multiplier=0.5, can_close_master=1,
                             clicker_agent_id=CLICKER_AGENT, close_route="UI")
    db.upsert_symbol_map(CLIENT_ID, SYMBOL, CLIENT_SYMBOL)
    db.set_config("run_mode", "RUNNING")
    db.set_config(MASTER_CLOSE_ROUTE_KEY, route)
    db.set_config(MASTER_CLICKER_KEY, CLICKER_MASTER_AGENT if khai_clicker_master else "")

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
                       account_login=222221, magic=MAGIC, emit_events=False)
    await client.start()
    clicker = MockClicker(host="127.0.0.1", port=server.port, token=CLICKER_TOKEN,
                          account_login=222221, magic=0)
    await clicker.start()
    clicker_master = MockClicker(host="127.0.0.1", port=server.port,
                                 token=CLICKER_MASTER_TOKEN, account_login=MASTER_LOGIN, magic=0)
    await clicker_master.start()
    await _wait_until(
        lambda: db.get_agent(CLICKER_MASTER_AGENT)["status"] == "ONLINE", timeout=3.0)

    try:
        yield Env(db, processor, master, client, clicker, clicker_master)
    finally:
        await processor.stop()
        await master.kill()
        await client.kill()
        await clicker.kill()
        await clicker_master.kill()
        await server.stop()


@pytest.fixture
async def env(db: Database) -> AsyncIterator[Env]:
    async for e in _make_env(db):
        yield e


# ---------------------------------------------------------------------------------------------
# Định tuyến
# ---------------------------------------------------------------------------------------------

async def test_cascade_gui_CLOSE_UI_toi_clicker_cua_MASTER(env: Env) -> None:
    """Đích đến là thứ quyết định `DEAL_REASON`, nên nó phải đúng agent chứ không chỉ đúng loại."""
    env.tao_cap()
    await env.client_dong_tay()

    lenh = env.commands("CLOSE_UI")
    assert len(lenh) == 1
    assert lenh[0]["target_agent_id"] == CLICKER_MASTER_AGENT
    assert env.commands("CLOSE") == [], "Khong duoc gui song song ca duong EA"


async def test_payload_dong_master_qua_giao_dien_khong_mang_magic(env: Env) -> None:
    """Giao diện không đặt được `magic`; payload có nó là dấu hiệu định tuyến sai (clicker từ chối)."""
    env.tao_cap()
    await env.client_dong_tay()

    import json
    payload = json.loads(env.commands("CLOSE_UI")[0]["payload_json"])
    assert payload == {"position_id": MASTER_POS}


async def test_route_EA_van_di_duong_cu_va_khong_bao_dong(db: Database) -> None:
    """Mặc định `EA`: nâng cấp không đổi hành vi, và đó là cấu hình bình thường chứ không phải sự cố."""
    async for env in _make_env(db, route="EA"):
        env.tao_cap()
        await env.client_dong_tay()

        lenh = env.commands("CLOSE")
        assert len(lenh) == 1 and lenh[0]["target_agent_id"] == MASTER_AGENT
        assert env.commands("CLOSE_UI") == []
        assert env.alerts("CLOSE_MASTER_FELL_BACK_TO_EA") == []


async def test_chua_khai_clicker_master_thi_roi_ve_EA_kem_CRITICAL(db: Database) -> None:
    """Bật `UI` mà chưa có clicker là cấu hình vô nghĩa — nhưng vị thế Master vẫn phải đóng được."""
    async for env in _make_env(db, route="UI", khai_clicker_master=False):
        env.tao_cap()
        await env.client_dong_tay()

        lenh = env.commands("CLOSE")
        assert len(lenh) == 1 and lenh[0]["target_agent_id"] == MASTER_AGENT
        canh_bao = env.alerts("CLOSE_MASTER_FELL_BACK_TO_EA")
        assert len(canh_bao) == 1 and canh_bao[0]["level"] == "CRITICAL"


# ---------------------------------------------------------------------------------------------
# Nhận cha — D-27 cho phía Master
# ---------------------------------------------------------------------------------------------

async def test_cu_dong_master_cua_bot_khong_tu_kich_hoat_lai(env: Env) -> None:
    """Event đóng Master do chính bot gây ra mang `caused_by_command_id` NULL — như một cú đóng tay.

    Không nhận cha thì mỗi lần cascade tự kích hoạt một lượt đồng bộ nữa.
    """
    env.tao_cap()
    await env.client_dong_tay()
    so_lenh_truoc = len(env.db.query_all("SELECT 1 FROM command"))

    eid = await env.master_bao_da_dong()

    assert env.db.get_event(eid)["caused_by_command_id"] is not None, "Phai nhan cha"
    assert env.db.get_event(eid)["process_status"] == "IGNORED"
    assert len(env.db.query_all("SELECT 1 FROM command")) == so_lenh_truoc


async def test_lenh_cua_clicker_CLIENT_khong_bi_nham_la_cha(db: Database) -> None:
    """Hai clicker, cùng cặp, cùng cửa sổ thời gian — lọc sai agent thì một cú đóng tay bị nuốt.

    Ở đây Master đi đường **EA**, nên lệnh `CLOSE_UI` duy nhất đang bay là của clicker phía Client.
    Cú đóng Master sau đó là **của người dùng** và phải được xử lý như vậy.
    """
    async for env in _make_env(db, route="EA"):
        pair_id = env.tao_cap()
        env.db.update_pair(pair_id, status="CLOSING")
        await env.processor.dispatcher.dispatch(
            CLICKER_AGENT, "CLOSE_UI", pair_id=pair_id, payload={"position_id": CLIENT_POS})

        eid = await env.master_bao_da_dong(reason=REASON_EXPERT)

        assert env.db.get_event(eid)["caused_by_command_id"] is None, \
            "Lenh cua clicker CLIENT khong phai cha cua cu dong MASTER"


# ---------------------------------------------------------------------------------------------
# Đo được: DEAL_REASON của deal đóng Master
# ---------------------------------------------------------------------------------------------

async def test_ghi_reason_dong_master_va_khong_bao_dong_khi_dung_kenh(env: Env) -> None:
    env.tao_cap()
    await env.client_dong_tay()
    await env.master_bao_da_dong(reason=REASON_CLIENT)

    assert env.db.get_master_position(MASTER_POS)["close_reason"] == REASON_CLIENT
    assert env.alerts("MASTER_CLOSE_REASON_MISMATCH") == []


async def test_deal_dong_master_mang_EXPERT_tren_duong_UI_thi_bao_dong(env: Env) -> None:
    """Đây là chỗ biến mục tiêu thành thứ đo được thay vì thứ được tin."""
    env.tao_cap()
    await env.client_dong_tay()
    await env.master_bao_da_dong(reason=REASON_EXPERT)

    assert env.db.get_master_position(MASTER_POS)["close_reason"] == REASON_EXPERT
    assert len(env.alerts("MASTER_CLOSE_REASON_MISMATCH")) == 1


async def test_duong_EA_thi_EXPERT_la_dung_va_khong_bao_dong(db: Database) -> None:
    async for env in _make_env(db, route="EA"):
        env.tao_cap()
        await env.client_dong_tay()
        await env.master_bao_da_dong(reason=REASON_EXPERT)

        assert env.db.get_master_position(MASTER_POS)["close_reason"] == REASON_EXPERT
        assert env.alerts("MASTER_CLOSE_REASON_MISMATCH") == []
