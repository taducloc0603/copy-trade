"""Test luồng đóng lệnh (plan `07-dong-lenh.md`).

Đây là phase dễ mất tiền nhất nếu sai, nên bộ test này cố tình nặng về **những gì KHÔNG được
xảy ra**: không đóng nhầm cặp khác cùng symbol, không cascade khi Master chưa xác nhận, không
đóng vị thế người dùng mở tay, không sinh vòng lặp.

Các cặp ở đây mở bằng đường EA (`open_route = 'EA'`) cho gọn — đường đóng không đổi gì giữa hai
đường mở, nên không cần dựng clicker.
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
from tests.test_server import MASTER_LOGIN, MASTER_TOKEN, _wait_until

SYMBOL = "XAUUSD"
CLIENT_SYMBOL = "XAUUSDm"
MAGIC = 770001


@dataclass
class Env:
    db: Database
    server: BridgeServer
    dispatcher: CommandDispatcher
    processor: EventProcessor
    master: MockAgent
    clients: dict[str, MockAgent]
    _seq: int = 0
    _alert_moc: int = 0
    _positions: dict[int, float] = field(default_factory=dict)

    # -- kích thích ------------------------------------------------------------------------

    async def master_open(self, position_id: int, volume: float = 1.0,
                          direction: str = "BUY") -> str:
        self._seq += 1
        eid = f"EVT-M-{position_id}-{self._seq}"
        await self.master.send_raw({
            "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": eid, "seq": self._seq,
            "type": "position_opened",
            "data": {"position_id": position_id, "deal_entry": "IN", "symbol": SYMBOL,
                     "direction": direction, "volume_delta": volume, "volume_after": volume,
                     "price": 2650.0, "magic": 0},
        })
        await _wait_until(lambda: self.db.get_event(eid) is not None)
        await self.processor.process_pending()
        self._positions[position_id] = volume
        return eid

    async def master_close(self, position_id: int, volume_delta: float | None = None,
                           event_id: str | None = None,
                           loai: str | None = None) -> str:
        """Master đóng hết hoặc đóng bớt. `volume_delta` None nghĩa là đóng hết."""
        con = self._positions.get(position_id, 1.0)
        delta = con if volume_delta is None else volume_delta
        sau = round(con - delta, 8)
        self._positions[position_id] = sau
        self._seq += 1
        eid = event_id or f"EVT-MC-{position_id}-{self._seq}"
        await self.master.send_raw({
            "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": eid, "seq": self._seq,
            "type": loai or ("position_closed" if sau <= 0 else "position_changed"),
            "data": {"position_id": position_id, "deal_entry": "OUT", "symbol": SYMBOL,
                     "direction": "BUY", "volume_delta": delta, "volume_after": sau},
        })
        await _wait_until(lambda: self.db.get_event(eid) is not None)
        await self.processor.process_pending()
        return eid

    async def client_close(self, client_key: str, position_id: int,
                           volume_after: float = 0.0, volume_delta: float = 0.5) -> None:
        """Client tự đóng — `caused_by_command_id` là NULL, tức do người dùng."""
        agent = self.clients[client_key]
        await agent.send_event(
            "position_closed" if volume_after <= 0 else "position_changed",
            position_id=position_id, deal_entry="OUT", symbol=CLIENT_SYMBOL,
            direction="SELL", volume_delta=volume_delta, volume_after=volume_after)
        await _wait_until(lambda: self.db.query_one(
            "SELECT 1 FROM event WHERE agent_id = ? AND position_id = ? AND type LIKE 'position_c%'",
            (agent.agent_id, position_id)) is not None)
        await self.processor.process_pending()

    # -- quan sát --------------------------------------------------------------------------

    def pairs(self, **where) -> list:
        sql = "SELECT * FROM pair"
        if where:
            sql += " WHERE " + " AND ".join(f"{k} = ?" for k in where)
        return self.db.query_all(sql + " ORDER BY pair_id", tuple(where.values()))

    def pair_of(self, master_position_id: int, client_id: str = "CL-01"):
        return self.db.query_one(
            "SELECT * FROM pair WHERE master_position_id = ? AND client_id = ?",
            (master_position_id, client_id))

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
        await _wait_until(lambda: self.db.get_pair(pair_id)["status"] == status,
                          timeout=timeout)


async def _dung_env(db: Database, so_client: int = 1,
                    can_close_master: int = 0) -> tuple[Env, list]:
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.replace_symbol_specs(MASTER_AGENT, [{
        "symbol": SYMBOL, "digits": 2, "point": 0.01, "volume_min": 0.01,
        "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])

    tokens = {}
    for i in range(1, so_client + 1):
        cid, aid = f"CL-{i:02d}", f"AG-CLIENT-{i}"
        tok = f"token-client-{i}-xxxxxxxxxxxx"
        tokens[cid] = (aid, tok, 222220 + i)
        db.upsert_agent(aid, role="CLIENT", token_hash=hash_token(tok),
                        magic_number=MAGIC, account_login=222220 + i)
        db.upsert_client_account(cid, agent_id=aid, copy_mode="OPPOSITE",
                                 volume_multiplier=0.5, can_close_master=can_close_master)
        db.upsert_symbol_map(cid, SYMBOL, CLIENT_SYMBOL)
        db.replace_symbol_specs(aid, [{
            "symbol": CLIENT_SYMBOL, "digits": 2, "point": 0.01, "volume_min": 0.01,
            "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])
    db.set_config("run_mode", "RUNNING")
    return tokens  # type: ignore[return-value]


@pytest.fixture
async def env(db: Database) -> AsyncIterator[Env]:
    async for e in _make_env(db, so_client=1, can_close_master=0):
        yield e


@pytest.fixture
async def env_cascade(db: Database) -> AsyncIterator[Env]:
    async for e in _make_env(db, so_client=3, can_close_master=1):
        yield e


@pytest.fixture
async def env_2client(db: Database) -> AsyncIterator[Env]:
    """Hai Client chung một vị thế Master — đủ để kiểm việc chống đóng Master hai lần."""
    async for e in _make_env(db, so_client=2, can_close_master=0):
        yield e


async def _make_env(db: Database, so_client: int, can_close_master: int):
    tokens = await _dung_env(db, so_client, can_close_master)
    server = BridgeServer(db, ServerConfig(host="127.0.0.1", port=0, hello_timeout_sec=1.0,
                                           monitor_interval_sec=0.05,
                                           heartbeat_timeout_ms=8000))
    dispatcher = CommandDispatcher(db, server)
    processor = EventProcessor(db, server, dispatcher)
    await server.start()

    master = MockAgent(host="127.0.0.1", port=server.port, token=MASTER_TOKEN, role="MASTER",
                       account_login=MASTER_LOGIN, magic=MAGIC, emit_events=False)
    await master.start()
    clients: dict[str, MockAgent] = {}
    for cid, (_aid, tok, login) in tokens.items():
        agent = MockAgent(host="127.0.0.1", port=server.port, token=tok, role="CLIENT",
                          account_login=login, magic=MAGIC,
                          known_symbols={CLIENT_SYMBOL})
        await agent.start()
        clients[cid] = agent

    e = Env(db, server, dispatcher, processor, master, clients)
    e.moc_alert()
    try:
        yield e
    finally:
        await processor.stop()
        await master.kill()
        for agent in clients.values():
            await agent.kill()
        await server.stop()


def _client_pos(env: Env, pair_id: str) -> int:
    return env.db.get_pair(pair_id)["client_position_id"]


# -- 7.2 Master đóng hoàn toàn -------------------------------------------------------------

async def test_master_dong_chi_dong_dung_cap_do(env: Env) -> None:
    """TEST-03: hai vị thế cùng symbol, đóng một cái → cái kia không bị động tới.

    Đây là test quan trọng nhất của cả file: nó chứng minh việc tra cứu đi theo `position_id`
    chứ không theo symbol (FR-11).
    """
    await env.master_open(900001, 1.0)
    await env.master_open(900002, 1.0)
    await _wait_until(lambda: len(env.pairs(status="OPEN")) == 2, timeout=3.0)
    cap1, cap2 = env.pair_of(900001), env.pair_of(900002)

    await env.master_close(900001)
    await env.cho_pair(cap1["pair_id"], "CLOSED")

    assert env.db.get_pair(cap2["pair_id"])["status"] == "OPEN", "Cap cung symbol bi dong lay"
    assert env.db.get_pair(cap1["pair_id"])["close_source"] == "MASTER"
    assert env.db.get_master_position(900001)["status"] == "CLOSED"
    assert env.db.get_master_position(900002)["status"] == "OPEN"


async def test_ba_lenh_dong_cai_o_giua(env: Env) -> None:
    """TEST-07: ba vị thế cùng symbol, đóng cái giữa."""
    for pid in (900001, 900002, 900003):
        await env.master_open(pid, 1.0)
    await _wait_until(lambda: len(env.pairs(status="OPEN")) == 3, timeout=4.0)

    giua = env.pair_of(900002)
    await env.master_close(900002)
    await env.cho_pair(giua["pair_id"], "CLOSED")

    assert env.db.get_pair(env.pair_of(900001)["pair_id"])["status"] == "OPEN"
    assert env.db.get_pair(env.pair_of(900003)["pair_id"])["status"] == "OPEN"


async def test_ack_already_closed_van_la_dong_thanh_cong(env: Env) -> None:
    """FR-18: hai bên cùng đóng gần như đồng thời là chuyện bình thường, không phải lỗi."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap = env.pair_of(900001)
    # Client đã tự đóng trước: vị thế không còn trong bộ nhớ mock, ack sẽ là already_closed.
    env.clients["CL-01"].positions.clear()

    await env.master_close(900001)
    await env.cho_pair(cap["pair_id"], "CLOSED")
    assert not env.alerts("CLOSE_FAILED")


# -- 7.3 Đóng một phần ---------------------------------------------------------------------

async def test_dong_mot_phan_dung_ty_le(env: Env) -> None:
    """TEST-06: Master 1.00 / Client 0.50, Master đóng 25% → Client đóng 0.125 → 0.12."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap = env.pair_of(900001)
    assert cap["client_current_volume"] == 0.5

    await env.master_close(900001, volume_delta=0.25)
    await _wait_until(
        lambda: env.db.get_pair(cap["pair_id"])["client_current_volume"] < 0.5, timeout=3.0)

    sau = env.db.get_pair(cap["pair_id"])
    assert sau["status"] == "PARTIALLY_CLOSED"
    assert sau["master_current_volume"] == 0.75
    # 0.50 x 25% = 0.125, lam tron XUONG theo step 0.01 -> 0.12. Con lai 0.38.
    assert abs(sau["client_current_volume"] - 0.38) < 1e-9, sau["client_current_volume"]


async def test_dong_mot_phan_ba_lan_lien_tiep(env: Env) -> None:
    """Mỗi lần lấy tỷ lệ trên volume **còn lại**, không phải volume ban đầu."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]

    for delta, master_con in ((0.2, 0.8), (0.3, 0.5), (0.25, 0.25)):
        truoc = env.db.get_pair(cap_id)["client_current_volume"]
        await env.master_close(900001, volume_delta=delta)
        await _wait_until(
            lambda muc=truoc: env.db.get_pair(cap_id)["client_current_volume"] < muc,
            timeout=3.0)
        assert abs(env.db.get_pair(cap_id)["master_current_volume"] - master_con) < 1e-9

    sau = env.db.get_pair(cap_id)
    assert 0 < sau["client_current_volume"] < 0.5
    assert sau["status"] == "PARTIALLY_CLOSED"


async def test_dong_mot_phan_lam_tron_ra_0_thi_khong_gui_lenh(env: Env) -> None:
    """Phần lệch tích luỹ lại, không gửi command, chỉ WARNING."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]
    truoc = env.db.get_pair(cap_id)["client_current_volume"]
    so_lenh = len(env.commands("CLOSE_PARTIAL"))

    # Master dong 1% cua 1.0 -> Client 0.5 x 1% = 0.005, lam tron xuong step 0.01 -> 0.
    await env.master_close(900001, volume_delta=0.01)
    await asyncio.sleep(0.2)

    assert len(env.commands("CLOSE_PARTIAL")) == so_lenh, "Khong duoc gui lenh"
    assert env.db.get_pair(cap_id)["client_current_volume"] == truoc
    assert env.alerts("PARTIAL_CLOSE_ROUNDS_TO_ZERO")
    # Nhung volume Master thi van phai cap nhat: do la su that EA bao (D-14).
    assert abs(env.db.get_pair(cap_id)["master_current_volume"] - 0.99) < 1e-9


async def test_doi_multiplier_giua_chung_khong_lam_lech_cap_dang_chay(env: Env) -> None:
    """D-19, FR-06: dùng `effective_multiplier` đã khoá, không dùng hệ số cấu hình hiện tại."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]

    env.db.upsert_client_account("CL-01", agent_id="AG-CLIENT-1", volume_multiplier=5.0)

    await env.master_close(900001, volume_delta=0.5)
    await _wait_until(
        lambda: env.db.get_pair(cap_id)["client_current_volume"] < 0.5, timeout=3.0)

    # 50% cua 0.50 = 0.25, khong lien quan gi toi he so 5.0 vua doi.
    assert abs(env.db.get_pair(cap_id)["client_current_volume"] - 0.25) < 1e-9


# -- 7.4 Client đóng, công tắc TẮT -----------------------------------------------------------

async def test_client_dong_cong_tac_tat_thi_master_giu_nguyen(env: Env) -> None:
    """TEST-04: mặc định D-20. Master phơi nhiễm, và điều đó phải hiện lên đỏ."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]
    so_lenh = len(env.commands())

    await env.client_close("CL-01", _client_pos(env, cap_id))

    cap = env.db.get_pair(cap_id)
    assert cap["status"] == "ORPHANED"
    assert cap["orphan_side"] == "MASTER"
    assert cap["close_source"] == "CLIENT"
    assert env.alerts("ORPHANED_MASTER")
    assert len(env.commands()) == so_lenh, "Khong duoc tao lenh dong nao cho Master"
    assert env.db.get_master_position(900001)["status"] == "OPEN"


async def test_dong_vi_the_mo_tay_khong_anh_huong_gi(env: Env) -> None:
    """FR-12: vị thế không thuộc pair nào thì bỏ qua hoàn toàn."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    so_lenh = len(env.commands())

    await env.client_close("CL-01", 999999)  # position_id khong thuoc pair nao

    assert len(env.commands()) == so_lenh
    assert env.pairs(status="OPEN"), "Cap that khong duoc dung toi"
    ev = env.db.query_one(
        "SELECT process_status, process_error FROM event WHERE position_id = 999999")
    assert ev["process_status"] == "IGNORED"
    assert "mo tay" in ev["process_error"]


# -- 7.5 Cascade -----------------------------------------------------------------------------

async def test_cascade_dong_master_va_cac_client_con_lai(env_cascade: Env) -> None:
    """TEST-05 mở rộng: A đóng → Master đóng → B và C đóng. Đúng thứ tự, không vòng lặp."""
    env = env_cascade
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: len(env.pairs(status="OPEN")) == 3, timeout=4.0)
    cap_a = env.pair_of(900001, "CL-01")

    await env.client_close("CL-01", _client_pos(env, cap_a["pair_id"]))
    await _wait_until(lambda: len(env.pairs(status="CLOSED")) == 3, timeout=8.0)

    assert env.db.get_master_position(900001)["status"] == "CLOSED"
    # Dung MOT lenh dong cho Master, khong phai hai, khong phai vo han.
    lenh_master = [c for c in env.commands("CLOSE")
                   if c["target_agent_id"] == MASTER_AGENT]
    assert len(lenh_master) == 1, f"Sinh {len(lenh_master)} lenh dong Master"
    assert not env.alerts("CASCADE_MASTER_TIMEOUT")


async def test_cascade_master_khong_phan_hoi_thi_khong_dong_client_khac(
        env_cascade: Env) -> None:
    """Master từ chối mà ta đã đóng B và C thì cả nhóm mất hedge. Đóng trước hỏi sau là sai."""
    env = env_cascade
    env.db.set_config("cascade_wait_master_ms", "1000")
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: len(env.pairs(status="OPEN")) == 3, timeout=4.0)
    cap_a = env.pair_of(900001, "CL-01")
    env.master.auto_ack = False  # Master khong tra loi lenh dong

    await env.client_close("CL-01", _client_pos(env, cap_a["pair_id"]))
    await _wait_until(lambda: bool(env.alerts("CASCADE_MASTER_TIMEOUT")), timeout=8.0)

    for cid in ("CL-02", "CL-03"):
        cap = env.pair_of(900001, cid)
        assert cap["status"] == "ORPHANED", f"{cid} phai ORPHANED"
        assert env.clients[cid].positions, f"{cid} VAN phai giu vi the"


async def test_client_dong_mot_phan_thi_khong_cascade(env_cascade: Env) -> None:
    """D-11: đóng một phần từ phía Client không bao giờ cascade."""
    env = env_cascade
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: len(env.pairs(status="OPEN")) == 3, timeout=4.0)
    cap_a = env.pair_of(900001, "CL-01")
    so_lenh = len(env.commands("CLOSE"))

    await env.client_close("CL-01", _client_pos(env, cap_a["pair_id"]),
                           volume_after=0.2, volume_delta=0.3)
    await asyncio.sleep(0.3)

    assert len(env.commands("CLOSE")) == so_lenh, "Khong duoc cascade"
    assert env.db.get_pair(cap_a["pair_id"])["status"] == "PARTIALLY_CLOSED"
    assert env.alerts("CLIENT_PARTIAL_CLOSE")
    assert env.db.get_master_position(900001)["status"] == "OPEN"


# -- 7.6 Đóng đồng thời ----------------------------------------------------------------------

async def test_moi_cap_chi_mot_lenh_dong_dang_chay(env: Env) -> None:
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]
    env.clients["CL-01"].auto_ack = False  # giu lenh dong o trang thai SENT

    await env.master_close(900001, event_id="EVT-X1")
    await env.master_close(900001, event_id="EVT-X2", volume_delta=0.0)

    assert len([c for c in env.commands("CLOSE") if c["pair_id"] == cap_id]) == 1


# -- 7.7 Close-by ----------------------------------------------------------------------------

async def test_out_by_xu_ly_nhu_hai_su_kien_dong_doc_lap(env: Env) -> None:
    """D-12: chạy đúng nhờ nguyên tắc chung (tra theo `position_id`), không nhánh đặc biệt.

    Broker demo hiện tại không hỗ trợ Close By nên phải bơm event giả — ghi rõ ở plan 7.7.
    """
    await env.master_open(900001, 1.0)
    await env.master_open(900002, 1.0)
    await _wait_until(lambda: len(env.pairs(status="OPEN")) == 2, timeout=3.0)
    cap1, cap2 = env.pair_of(900001), env.pair_of(900002)

    for pid in (900001, 900002):
        self_seq = env._seq = env._seq + 1
        await env.master.send_raw({
            "v": 1, "kind": "event", "ts": to_iso(utc_now()),
            "id": f"EVT-OUTBY-{pid}", "seq": self_seq, "type": "position_closed",
            "data": {"position_id": pid, "deal_entry": "OUT_BY", "symbol": SYMBOL,
                     "direction": "BUY", "volume_delta": 1.0, "volume_after": 0.0},
        })
        await _wait_until(lambda p=pid: env.db.get_event(f"EVT-OUTBY-{p}") is not None)
    await env.processor.process_pending()

    await env.cho_pair(cap1["pair_id"], "CLOSED")
    await env.cho_pair(cap2["pair_id"], "CLOSED")


# -- 7.8 Ba chế độ dừng ----------------------------------------------------------------------

async def test_pause_new_entries_van_dong_bo_dong(env: Env) -> None:
    """Tắt đồng bộ đóng ở chế độ này là bỏ rơi vị thế đang mở."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]
    env.db.set_config("run_mode", "PAUSE_NEW_ENTRIES")

    await env.master_close(900001)
    await env.cho_pair(cap_id, "CLOSED")


async def test_paused_thi_khong_dong_bo_dong(env: Env) -> None:
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]
    env.db.set_config("run_mode", "PAUSED")

    eid = await env.master_close(900001)
    await asyncio.sleep(0.2)

    assert env.db.get_pair(cap_id)["status"] == "OPEN"
    assert env.db.get_event(eid)["process_status"] == "IGNORED"
    # Nhung so sach vi the Master van phai dung, ke ca khi khong dong bo.
    assert env.db.get_master_position(900001)["status"] == "CLOSED"


async def test_emergency_dong_het_ca_hai_phia(env: Env) -> None:
    """TEST-21. Bản trước của test này chỉ kiểm phía Client và **khoá lại chính khiếm khuyết**.

    Nút dừng khẩn cấp im lặng bỏ qua phía Master suốt mười phase: nó cắt một chân hedge, để
    nguyên chân kia, rồi báo thành công (kiểm toán 2026-09-06, F-01). Bài kiểm quyết định không
    phải `pair.status` — trạng thái đó do ack của Client quyết định nên nó luôn đẹp — mà là
    **vị thế Master có thật sự được đóng không**.
    """
    await env.master_open(900001, 1.0)
    await env.master_open(900002, 1.0)
    await _wait_until(lambda: len(env.pairs(status="OPEN")) == 2, timeout=3.0)

    so = await env.processor.closing.emergency_close_all()
    assert so == {"client": 2, "master": 2}, so
    await _wait_until(lambda: len(env.pairs(status="CLOSED")) == 2, timeout=4.0)
    assert env.alerts("EMERGENCY_CLOSE_ALL")

    # Vế bị bỏ quên: phải có lệnh đóng gửi cho EA của MASTER, và vị thế Master phải phẳng.
    lenh_master = [c for c in env.commands("CLOSE") if c["target_agent_id"] == MASTER_AGENT]
    assert len(lenh_master) == 2, "Khong co lenh dong nao gui cho Master"
    for position_id in (900001, 900002):
        await _wait_until(
            lambda pid=position_id: env.db.get_master_position(pid)["status"] == "CLOSED",
            timeout=4.0)

    # Va so sach phai theo kip: nghiem thu demo 2026-09-06 thay cap `CLOSED` van con
    # `master_current_volume = 0.02` vi con so do chi duoc don khi Client ack.
    for cap in env.pairs():
        assert cap["master_current_volume"] == 0, cap["pair_id"]


async def test_emergency_dong_client_truoc_master_sau(env: Env) -> None:
    """Thứ tự là một phần của hợp đồng, không phải chi tiết cài đặt.

    Đóng Master trước sẽ kích hoạt đồng bộ đóng thông thường ngay giữa lúc cần mọi thứ đơn giản
    nhất, nên lệnh cho Client phải được tạo trước lệnh cho Master.
    """
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))

    await env.processor.closing.emergency_close_all()

    lenh = [c for c in env.commands("CLOSE")]
    vai_tro = [env.db.get_agent(c["target_agent_id"])["role"] for c in lenh]
    assert vai_tro == ["CLIENT", "MASTER"], vai_tro


async def test_emergency_nhieu_cap_chung_mot_master_chi_dong_master_mot_lan(
        env_2client: Env) -> None:
    """Một vị thế Master có N Client thì vẫn chỉ có **một** lệnh đóng Master.

    Gửi hai lệnh đóng cho cùng một vị thế là cách tạo ra lỗi "đóng nhầm lệnh vừa mở" trên tài
    khoản hedging.
    """
    env = env_2client
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: len(env.pairs(status="OPEN")) == 2, timeout=3.0)

    so = await env.processor.closing.emergency_close_all()
    assert so == {"client": 2, "master": 1}, so

    lenh_master = [c for c in env.commands("CLOSE") if c["target_agent_id"] == MASTER_AGENT]
    assert len(lenh_master) == 1


# -- hai lỗ hổng của plan 7.4b ---------------------------------------------------------------

async def test_master_dong_khi_cap_con_cho_tuong_quan(env: Env) -> None:
    """Lỗ hổng 1: chưa có `client_position_id` thì không có gì để đóng — phải ồn ào."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]
    # Ep cap ve trang thai "dang cho tuong quan" nhu duong UI cua phase 6b.
    env.db.update_pair(cap_id, status="PENDING_OPEN", client_position_id=None)
    so_lenh = len(env.commands("CLOSE"))

    await env.master_close(900001)
    await asyncio.sleep(0.2)

    assert len(env.commands("CLOSE")) == so_lenh, "Khong the dong cai chua biet dia chi"
    cap = env.db.get_pair(cap_id)
    assert cap["close_time_master"], "Phai ghi y dinh dong de tuong quan xong thi dong ngay"
    assert cap["close_source"] == "MASTER"
    assert env.alerts("MASTER_CLOSED_WHILE_PENDING")


async def test_dong_cap_ghep_bang_suy_doan_thi_canh_bao(env: Env) -> None:
    """Lỗ hổng 2: có thể đang đóng vị thế của người dùng. Vẫn đóng, nhưng phải đỏ."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]
    env.db.create_alert("WARNING", "UI_CORRELATE_HEURISTIC",
                        "ghep bang suy doan", pair_id=cap_id)

    await env.master_close(900001)
    await env.cho_pair(cap_id, "CLOSED")

    assert env.alerts("CLOSING_HEURISTIC_PAIR"), "Dong cap ghep suy doan phai canh bao"


# -- FR-11: không bao giờ đóng theo symbol ---------------------------------------------------

def test_khong_co_cau_sql_nao_dong_lenh_theo_symbol(project_root) -> None:
    """Soi thẳng mã nguồn: một câu SQL đóng lệnh có `WHERE symbol = ?` là bug (FR-11)."""
    nguon = (project_root / "bridge" / "engine" / "closing.py").read_text(encoding="utf-8")
    for dong in nguon.splitlines():
        thap = dong.lower()
        # Chi soi dong SQL that, khong soi van xuoi giai thich chinh quy tac nay.
        la_sql = any(tu in thap for tu in ("select ", "update ", "delete "))
        if la_sql and "symbol" in thap:
            assert "client_symbol" in dong, f"Nghi van tra cuu theo symbol: {dong.strip()}"


async def test_emergency_tu_kich_hoat_va_chi_chay_mot_lan(env: Env) -> None:
    """`run_mode = EMERGENCY` phải tự đóng hết, và không lặp lại mỗi vòng quét."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    env.db.set_config("run_mode", "EMERGENCY")

    await env.processor.check_emergency()
    await env.processor.check_emergency()
    await env.processor.check_emergency()

    await _wait_until(lambda: bool(env.pairs(status="CLOSED")), timeout=4.0)
    assert len(env.alerts("EMERGENCY_CLOSE_ALL")) == 1, "Khong duoc lam ngap alert"

    # Roi che do roi vao lai thi phai chay lai.
    env.db.set_config("run_mode", "RUNNING")
    await env.processor.check_emergency()
    env.db.set_config("run_mode", "EMERGENCY")
    await env.processor.check_emergency()
    assert len(env.alerts("EMERGENCY_CLOSE_ALL")) == 1, "Khong con cap nao de dong"


async def test_out_by_de_lai_vi_the_du_thi_bao_unpaired_master(env: Env) -> None:
    """plan 7.7: phần dư của Close By phải hiện lên, và **không** được copy sang Client."""
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    so_open = len(env.commands("OPEN"))

    # Master con mot vi the khong thuoc cap nao — dung phan du ma Close By de lai.
    env.master.positions.clear()
    env.master._position_counter = 900500
    from tests.mock_agent import MockPosition
    env.master.positions[900501] = MockPosition(
        position_id=900501, symbol=SYMBOL, direction="BUY", volume=0.4)

    env._seq += 1
    await env.master.send_raw({
        "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": "EVT-OUTBY-DU",
        "seq": env._seq, "type": "position_closed",
        "data": {"position_id": 900001, "deal_entry": "OUT_BY", "symbol": SYMBOL,
                 "direction": "BUY", "volume_delta": 1.0, "volume_after": 0.0},
    })
    await _wait_until(lambda: env.db.get_event("EVT-OUTBY-DU") is not None)
    await env.processor.process_pending()

    await _wait_until(lambda: bool(env.alerts("UNPAIRED_MASTER")), timeout=8.0)
    assert env.db.get_master_position(900501)["status"] == "UNPAIRED"
    assert len(env.commands("OPEN")) == so_open, "KHONG duoc copy vi the du sang Client"


async def test_volume_con_lai_khong_co_sai_so_float(env: Env) -> None:
    """`0.05 - 0.02` bằng float ra 0.030000000000000002, và sai số đó tích luỹ.

    Bắt được ở nghiệm thu phase 7 trên demo thật, không phải do nghĩ ra.
    """
    await env.master_open(900001, 0.10)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]
    assert env.db.get_pair(cap_id)["client_current_volume"] == 0.05

    await env.master_close(900001, volume_delta=0.04)   # 40% -> Client dong 0.02
    await _wait_until(
        lambda: env.db.get_pair(cap_id)["client_current_volume"] < 0.05, timeout=3.0)

    con = env.db.get_pair(cap_id)["client_current_volume"]
    assert repr(con) == "0.03", f"Sai so float: {con!r}"


async def test_dong_mot_phan_lay_ty_le_tren_volume_con_lai_khong_phai_he_so_khoa(
        env: Env) -> None:
    """D-19 bản phase 11, ghim bằng con số chính xác chứ không phải một khoảng.

    Đây là chuỗi mà hai công thức cho kết quả **khác nhau** — chỗ mà bộ test cũ không đi tới vì
    nó chỉ khẳng định `0 < volume < 0.5`:

    * lấy tỷ lệ trên volume còn lại (đang chạy) → Client còn **0.13**
    * `delta × effective_multiplier` (chữ của D-19 bản 1) → Client còn 0.14
    * lý tưởng không làm tròn → 0.125

    Bản đang chạy gần lý tưởng hơn vì phần dư do làm tròn xuống được thu lại ở lần đóng sau, thay
    vì tồn tại vĩnh viễn. Đó là lý do phase 11 sửa quyết định theo code chứ không ngược lại.
    """
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]
    assert env.db.get_pair(cap_id)["client_current_volume"] == 0.5

    for _ in range(3):
        truoc = env.db.get_pair(cap_id)["client_current_volume"]
        await env.master_close(900001, volume_delta=0.25)
        await _wait_until(
            lambda muc=truoc: env.db.get_pair(cap_id)["client_current_volume"] < muc,
            timeout=3.0)

    sau = env.db.get_pair(cap_id)
    assert abs(sau["master_current_volume"] - 0.25) < 1e-9
    assert abs(sau["client_current_volume"] - 0.13) < 1e-9, sau["client_current_volume"]


async def test_he_so_cau_hinh_doi_giua_chung_khong_co_duong_nao_cham_toi_cap_dang_chay(
        env: Env) -> None:
    """FR-06 vẫn được bảo đảm sau khi sửa D-19 — mạnh hơn bản cũ, không yếu đi.

    Đường đóng một phần **không đọc `client_account`** chút nào, nên hệ số cấu hình đổi giữa
    chừng không có cách nào ảnh hưởng tới cặp đang chạy.
    """
    await env.master_open(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="OPEN")))
    cap_id = env.pair_of(900001)["pair_id"]

    env.db.upsert_client_account("CL-01", agent_id="AG-CLIENT-1", volume_multiplier=5.0)
    await env.master_close(900001, volume_delta=0.5)
    await _wait_until(
        lambda: env.db.get_pair(cap_id)["client_current_volume"] < 0.5, timeout=3.0)

    # 50% cua 0.50 con lai = 0.25. He so 5.0 vua doi khong xuat hien o dau ca.
    assert abs(env.db.get_pair(cap_id)["client_current_volume"] - 0.25) < 1e-9
