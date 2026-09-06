"""Test đối chiếu ba nguồn (plan `08-ket-noi-doi-chieu.md`).

Trọng tâm là **ma trận sai lệch** ở mục 8.4: mỗi dòng một hành vi, và vài dòng trong đó nếu cài
sai sẽ dẫn tới đóng nhầm vị thế của người dùng. Đặc biệt hai dòng:

* `ACK_LOST` **không có thẻ** phải là `DECISION`, không phải `SAFE` — `accept_all_safe()` tuyệt
  đối không được chạm tới nó.
* Vị thế Client mở tay **không mang thẻ** phải **không xuất hiện** trong danh sách finding.
  Nhận dạng theo thẻ và theo bảng `pair`, không theo magic (D-07b).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from bridge.clock import to_iso, utc_now
from bridge.db.repo import Database
from bridge.engine.processor import EventProcessor
from bridge.protocol.auth import hash_token
from bridge.protocol.dispatcher import CommandDispatcher
from bridge.protocol.server import BridgeServer, ServerConfig
from tests.conftest import CLIENT_AGENT, CLIENT_ID, MASTER_AGENT
from tests.mock_agent import MockAgent, MockPosition
from tests.test_server import CLIENT_LOGIN, CLIENT_TOKEN, MASTER_LOGIN, MASTER_TOKEN, _wait_until

SYMBOL, CLIENT_SYMBOL, MAGIC = "XAUUSD", "XAUUSDm", 770001


@dataclass
class Env:
    db: Database
    server: BridgeServer
    processor: EventProcessor
    master: MockAgent
    client: MockAgent

    def tao_cap(self, master_pos: int, client_pos: int | None, status: str = "OPEN",
                the: str | None = None, volume: float = 1.0,
                client_volume: float | None = None) -> str:
        """Dựng thẳng một cặp trong DB, không đi qua luồng mở — để cô lập phần đối chiếu."""
        self.db.upsert_master_position(
            master_pos, agent_id=MASTER_AGENT, symbol=SYMBOL, direction="BUY",
            initial_volume=volume, current_volume=volume, status="OPEN")
        pair_id = self.db.create_pending_pair(
            master_pos, CLIENT_ID, copy_mode="OPPOSITE", master_initial_volume=volume,
            effective_multiplier=0.5, client_symbol=CLIENT_SYMBOL, client_direction="SELL",
            open_time_master=to_iso(utc_now()), open_tag=the)
        if status != "PENDING_OPEN" and client_pos is not None:
            self.db.mark_pair_open(pair_id, client_position_id=client_pos,
                                   client_ticket=client_pos,
                                   client_volume=client_volume
                                   if client_volume is not None else volume * 0.5)
            if status != "OPEN":
                self.db.update_pair(pair_id, status=status)
        return pair_id

    def vi_the_master(self, position_id: int, volume: float = 1.0) -> None:
        self.master.positions[position_id] = MockPosition(
            position_id=position_id, symbol=SYMBOL, direction="BUY", volume=volume)

    def vi_the_client(self, position_id: int, volume: float = 0.5,
                      comment: str | None = None) -> None:
        self.client.positions[position_id] = MockPosition(
            position_id=position_id, symbol=CLIENT_SYMBOL, direction="SELL",
            volume=volume, magic=0, comment=comment)

    def findings(self, run_id: str, kind: str | None = None) -> list:
        rows = self.db.list_findings(run_id=run_id)
        return [r for r in rows if kind is None or r["kind"] == kind]


@pytest.fixture
async def env(db: Database) -> AsyncIterator[Env]:
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash=hash_token(CLIENT_TOKEN),
                    magic_number=MAGIC, account_login=CLIENT_LOGIN)
    db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, copy_mode="OPPOSITE",
                             volume_multiplier=0.5)
    db.upsert_symbol_map(CLIENT_ID, SYMBOL, CLIENT_SYMBOL)
    for agent_id, sym in ((MASTER_AGENT, SYMBOL), (CLIENT_AGENT, CLIENT_SYMBOL)):
        db.replace_symbol_specs(agent_id, [{
            "symbol": sym, "digits": 2, "point": 0.01, "volume_min": 0.01,
            "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])

    server = BridgeServer(db, ServerConfig(host="127.0.0.1", port=0, hello_timeout_sec=1.0,
                                           monitor_interval_sec=0.05,
                                           heartbeat_timeout_ms=8000))
    dispatcher = CommandDispatcher(db, server)
    processor = EventProcessor(db, server, dispatcher)
    await server.start()
    master = MockAgent(host="127.0.0.1", port=server.port, token=MASTER_TOKEN, role="MASTER",
                       account_login=MASTER_LOGIN, magic=MAGIC, emit_events=False)
    client = MockAgent(host="127.0.0.1", port=server.port, token=CLIENT_TOKEN, role="CLIENT",
                       account_login=CLIENT_LOGIN, magic=MAGIC, emit_events=False)
    await master.start()
    await client.start()
    try:
        yield Env(db, server, processor, master, client)
    finally:
        await processor.stop()
        await master.kill()
        await client.kill()
        await server.stop()


# -- ma trận sai lệch (plan 8.4) -------------------------------------------------------------

async def test_khop_ca_ba_nguon_thi_khong_tao_finding_rac(env: Env) -> None:
    """Đối chiếu định kỳ khi mọi thứ khớp phải im lặng."""
    env.tao_cap(900001, 800001)
    env.vi_the_master(900001)
    env.vi_the_client(800001)

    run_id = await env.processor.reconciler.run("TEST")
    assert env.findings(run_id) == []


async def test_master_da_dong_client_con_thi_SAFE_dong_client(env: Env) -> None:
    pair_id = env.tao_cap(900001, 800001)
    env.vi_the_client(800001)          # Master khong con vi the nao

    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "MASTER_CLOSED_OFFLINE")
    assert len(f) == 1
    assert f[0]["severity"] == "SAFE"
    assert f[0]["suggested_action"] == "CLOSE_CLIENT"
    assert f[0]["pair_id"] == pair_id


async def test_client_da_dong_master_con_thi_DECISION_khong_dong_master(env: Env) -> None:
    """Đóng Master lúc này là một quyết định giao dịch mới, không phải đồng bộ."""
    env.db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, can_close_master=1)
    env.tao_cap(900001, 800001)
    env.vi_the_master(900001)          # Client khong con vi the nao

    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "CLIENT_CLOSED_OFFLINE")
    assert len(f) == 1
    assert f[0]["severity"] == "DECISION", "KHONG duoc la SAFE du can_close_master = 1"
    assert f[0]["suggested_action"] == "MARK_ORPHANED"


async def test_ca_hai_da_dong_thi_SAFE_cap_nhat_so_sach(env: Env) -> None:
    env.tao_cap(900001, 800001)
    run_id = await env.processor.reconciler.run("TEST")

    f = env.findings(run_id, "BOTH_CLOSED")
    assert len(f) == 1 and f[0]["severity"] == "SAFE"


async def test_ack_lost_co_the_thi_SAFE_va_ghep_lai_duoc(env: Env) -> None:
    pair_id = env.tao_cap(900001, None, status="PENDING_OPEN", the="CBabc1234567")
    env.vi_the_master(900001)
    env.vi_the_client(800009, comment="CBabc1234567")

    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "ACK_LOST")
    assert len(f) == 1 and f[0]["severity"] == "SAFE"
    assert f[0]["suggested_action"] == "REBIND_BY_TAG"

    assert await env.processor.reconciler.accept_finding(f[0]["id"])
    cap = env.db.get_pair(pair_id)
    assert cap["status"] == "OPEN" and cap["client_position_id"] == 800009


async def test_ack_lost_khong_the_thi_DECISION_chu_khong_phai_SAFE(env: Env) -> None:
    """Ghép sai ở đây nghĩa là gắn vị thế người dùng vào một cặp, rồi phase 7 sẽ đóng nó."""
    env.tao_cap(900001, None, status="PENDING_OPEN", the="CBabc1234567")
    env.vi_the_master(900001)
    env.vi_the_client(800009, comment="")     # cung symbol/chieu nhung KHONG mang the

    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "ACK_LOST")
    assert len(f) == 1
    assert f[0]["severity"] == "DECISION", "Suy doan KHONG duoc xep SAFE"
    assert f[0]["suggested_action"] == "REBIND_BY_GUESS"


async def test_client_chua_mo_thi_DECISION_va_ap_chinh_sach(env: Env) -> None:
    env.tao_cap(900001, None, status="PENDING_OPEN", the="CBxyz9999999")
    env.vi_the_master(900001)

    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "CLIENT_NOT_OPENED")
    assert len(f) == 1 and f[0]["severity"] == "DECISION"
    assert f[0]["suggested_action"] == "APPLY_POLICY:NONE"


async def test_vi_the_master_khong_thuoc_cap_nao(env: Env) -> None:
    env.vi_the_master(900777)
    run_id = await env.processor.reconciler.run("TEST")

    f = env.findings(run_id, "UNPAIRED_MASTER")
    assert len(f) == 1 and f[0]["severity"] == "DECISION"
    assert f[0]["suggested_action"] == "ALERT_ONLY"
    assert not env.db.query_all("SELECT 1 FROM command WHERE type = 'OPEN'"), \
        "KHONG duoc copy vi the khong ro nguon goc"


async def test_vi_the_client_mo_tay_khong_the_thi_KHONG_vao_danh_sach(env: Env) -> None:
    """D-07b: nhận dạng theo thẻ và theo bảng `pair`, không theo magic.

    Vị thế mở qua giao diện cũng có `magic = 0`, nên nhận dạng bằng magic sẽ coi **mọi** vị thế
    là của bot và lôi cả lệnh của người dùng vào danh sách.
    """
    env.vi_the_client(800555, comment="lenh tay cua toi")
    run_id = await env.processor.reconciler.run("TEST")

    assert env.findings(run_id, "UNPAIRED_CLIENT") == []
    assert env.findings(run_id) == []


async def test_vi_the_client_con_the_cua_open_ui_da_biet(env: Env) -> None:
    env.tao_cap(900001, 800001, the="CBdeadbeef01")
    env.vi_the_master(900001)
    env.vi_the_client(800001)
    env.vi_the_client(800556, comment="CBdeadbeef01 con sot")   # khong thuoc cap nao

    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "UNPAIRED_CLIENT")
    assert len(f) == 1 and f[0]["severity"] == "DECISION"


async def test_lech_volume_thi_bao(env: Env) -> None:
    env.tao_cap(900001, 800001, volume=1.0)      # mong doi Client 0.5
    env.vi_the_master(900001, volume=1.0)
    env.vi_the_client(800001, volume=0.2)        # thuc te chi 0.2

    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "VOLUME_MISMATCH")
    assert len(f) == 1 and f[0]["severity"] == "DECISION"


async def test_reason_khac_client_tren_duong_ui_thi_bao(env: Env) -> None:
    """Mục tiêu của phase 6b, kiểm lại ở đây thay vì tin."""
    env.db.upsert_agent("AG-CLICKER", role="CLICKER", token_hash="h", magic_number=0)
    env.db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, open_route="UI",
                                 clicker_agent_id="AG-CLICKER")
    pair_id = env.tao_cap(900001, 800001)
    env.db.update_pair(pair_id, client_open_reason=3)     # 3 = EXPERT
    env.vi_the_master(900001)
    env.vi_the_client(800001)

    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "UI_REASON_MISMATCH")
    assert len(f) == 1 and f[0]["severity"] == "DECISION"


# -- API xử lý finding (plan 8.7) ------------------------------------------------------------

async def test_accept_all_safe_khong_dong_toi_finding_decision(env: Env) -> None:
    """Không có hàm nào chấp nhận hàng loạt các finding `DECISION`."""
    env.db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, can_close_master=1)
    env.tao_cap(900001, 800001)          # ca hai deu mat -> BOTH_CLOSED, SAFE
    env.tao_cap(900002, 800002)          # Client mat -> CLIENT_CLOSED_OFFLINE, DECISION
    env.vi_the_master(900002)

    run_id = await env.processor.reconciler.run("TEST")
    assert len(env.findings(run_id)) == 2

    so = await env.processor.reconciler.accept_all_safe(run_id)
    assert so == 1
    con = [f for f in env.db.list_findings(run_id=run_id, resolution="PENDING")]
    assert len(con) == 1 and con[0]["severity"] == "DECISION"


async def test_skip_finding_tao_alert_ton_tai(env: Env) -> None:
    """Bỏ qua không có nghĩa là quên."""
    env.tao_cap(900001, 800001)
    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id)[0]

    assert env.processor.reconciler.skip_finding(f["id"], "toi tu xu ly tay")
    assert env.db.get_finding(f["id"])["resolution"] == "SKIPPED"
    alerts = [a for a in env.db.list_open_alerts() if a["code"] == "FINDING_SKIPPED"]
    assert alerts, "Bo qua phai de lai mot alert ton tai"


async def test_accept_mot_finding_hai_lan_thi_lan_hai_khong_lam_gi(env: Env) -> None:
    env.tao_cap(900001, 800001)
    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id)[0]

    assert await env.processor.reconciler.accept_finding(f["id"])
    assert not await env.processor.reconciler.accept_finding(f["id"])


async def test_accept_master_closed_offline_thi_dong_client(env: Env) -> None:
    pair_id = env.tao_cap(900001, 800001)
    env.vi_the_client(800001)
    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "MASTER_CLOSED_OFFLINE")[0]

    assert await env.processor.reconciler.accept_finding(f["id"])
    await _wait_until(lambda: env.db.get_pair(pair_id)["status"] in ("CLOSING", "CLOSED"),
                      timeout=3.0)
    lenh = env.db.query_all("SELECT * FROM command WHERE type = 'CLOSE'")
    assert len(lenh) == 1
    assert lenh[0]["target_agent_id"] == CLIENT_AGENT


# -- 8.5 chính sách mở bù ---------------------------------------------------------------------

async def test_offline_reopen_policy_NONE_thi_khong_mo_bu(env: Env) -> None:
    env.tao_cap(900001, None, status="PENDING_OPEN", the="CBaaaa111122")
    env.vi_the_master(900001)
    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "CLIENT_NOT_OPENED")[0]

    assert await env.processor.reconciler.accept_finding(f["id"])
    assert not env.db.query_all("SELECT 1 FROM command WHERE type IN ('OPEN','OPEN_UI')"), \
        "NONE thi tuyet doi khong mo bu"


async def test_if_still_open_van_can_ca_dieu_kien_gia(env: Env) -> None:
    """Chỉ dùng điều kiện thời gian là không đủ — vàng nhảy 200 điểm trong 10 giây khi ra tin."""
    env.db.set_config("offline_reopen_policy", "IF_STILL_OPEN")
    env.db.set_config("max_reopen_slippage_points", "0")     # chua cau hinh
    env.tao_cap(900001, None, status="PENDING_OPEN", the="CBbbbb222233")
    env.vi_the_master(900001)
    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "CLIENT_NOT_OPENED")[0]

    await env.processor.reconciler.accept_finding(f["id"])
    bo_qua = [a for a in env.db.list_open_alerts() if a["code"] == "REOPEN_SKIPPED"]
    assert bo_qua, "Thieu nguong truot gia thi khong duoc mo bu"
    assert not env.db.query_all("SELECT 1 FROM command WHERE type IN ('OPEN','OPEN_UI')")


# -- 8.6 thứ tự khởi động ---------------------------------------------------------------------

async def test_doi_chieu_khong_bao_gio_tu_chuyen_sang_running(env: Env) -> None:
    """Sau một sự cố, thứ tệ nhất là hệ thống tự hồi sinh và vào lệnh trước khi ai kịp nhìn."""
    env.db.set_config("run_mode", "PAUSED")
    env.tao_cap(900001, 800001)
    await env.processor.reconciler.run("STARTUP")
    assert env.db.get_config("run_mode") == "PAUSED"


async def test_doi_chieu_tu_chay_khi_agent_noi_lai(db: Database) -> None:
    """plan 8.4: đối chiếu chạy khi Bridge khởi động và khi agent nối lại."""
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash=hash_token(CLIENT_TOKEN),
                    magic_number=MAGIC, account_login=CLIENT_LOGIN)
    db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT)

    server = BridgeServer(db, ServerConfig(host="127.0.0.1", port=0, hello_timeout_sec=1.0,
                                           monitor_interval_sec=0.05,
                                           heartbeat_timeout_ms=8000))
    dispatcher = CommandDispatcher(db, server)
    processor = EventProcessor(db, server, dispatcher)
    await server.start()
    goi: list[str] = []
    processor.reconciler.run = lambda trigger="?": goi.append(trigger)  # type: ignore[assignment]

    master = MockAgent(host="127.0.0.1", port=server.port, token=MASTER_TOKEN, role="MASTER",
                       account_login=MASTER_LOGIN, magic=MAGIC, emit_events=False)
    await master.start()
    try:
        await _wait_until(lambda: bool(goi), timeout=5.0)
        assert goi == ["AGENT_ONLINE"]
    finally:
        await processor.stop()
        await master.kill()
        await server.stop()


async def test_nhieu_agent_noi_cung_luc_chi_chay_mot_vong(db: Database) -> None:
    """Ba agent nối lại cùng lúc chỉ cần một vòng đối chiếu, không phải ba."""
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash=hash_token(CLIENT_TOKEN),
                    magic_number=MAGIC, account_login=CLIENT_LOGIN)
    db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT)

    server = BridgeServer(db, ServerConfig(host="127.0.0.1", port=0, hello_timeout_sec=1.0,
                                           monitor_interval_sec=0.05,
                                           heartbeat_timeout_ms=8000))
    dispatcher = CommandDispatcher(db, server)
    processor = EventProcessor(db, server, dispatcher)
    await server.start()
    goi: list[str] = []
    processor.reconciler.run = lambda trigger="?": goi.append(trigger)  # type: ignore[assignment]

    master = MockAgent(host="127.0.0.1", port=server.port, token=MASTER_TOKEN, role="MASTER",
                       account_login=MASTER_LOGIN, magic=MAGIC, emit_events=False)
    client = MockAgent(host="127.0.0.1", port=server.port, token=CLIENT_TOKEN, role="CLIENT",
                       account_login=CLIENT_LOGIN, magic=MAGIC, emit_events=False)
    await master.start()
    await client.start()
    try:
        await _wait_until(lambda: bool(goi), timeout=5.0)
        assert len(goi) == 1, f"Chay {len(goi)} vong doi chieu cho hai agent"
    finally:
        await processor.stop()
        await master.kill()
        await client.kill()
        await server.stop()


async def test_doi_chieu_khong_tao_command_trung_voi_lenh_dang_chay(env: Env) -> None:
    """plan 8: đối chiếu chạy đồng thời với một lệnh đóng đang bay không được tạo cái thứ hai.

    Cổng bảo vệ nằm ở `CloseFlow._close_pair_fully` (một lệnh đóng mỗi cặp, plan 7.6). Đối
    chiếu **dùng lại** đường đóng của phase 7 thay vì tự tạo command, nên nó thừa hưởng cổng đó
    — đây là lý do `Reconciler` cầm `CloseFlow` chứ không cầm `CommandDispatcher`.
    """
    pair_id = env.tao_cap(900001, 800001)
    env.vi_the_client(800001)

    # Dung mot lenh dong DANG BAY, nhu cascade cua phase 7 vua tao. Khong tat auto_ack cua mock:
    # lam vay se chan luon tra loi REQUEST_SNAPSHOT va vong doi chieu se khong co du lieu.
    env.db.create_command("CMD-DANG-BAY", CLIENT_AGENT, "CLOSE", pair_id=pair_id,
                          payload_json='{"position_id": 800001}',
                          deadline_at=to_iso(utc_now()))
    env.db.mark_command_sent("CMD-DANG-BAY")
    assert env.db.list_inflight_commands(pair_id)

    run_id = await env.processor.reconciler.run("TEST")
    for f in env.findings(run_id, "MASTER_CLOSED_OFFLINE"):
        await env.processor.reconciler.accept_finding(f["id"])

    lenh = env.db.query_all("SELECT * FROM command WHERE type = 'CLOSE' AND pair_id = ?",
                            (pair_id,))
    assert len(lenh) == 1, f"Sinh {len(lenh)} lenh dong cho cung mot cap"
    assert lenh[0]["command_id"] == "CMD-DANG-BAY"


async def test_chay_hai_lan_khong_de_them_finding_trung(env: Env) -> None:
    """Đối chiếu chạy mỗi phút. Sai lệch chưa xử lý không được đẻ thêm một dòng mỗi vòng.

    Danh sách finding mà đầy dòng trùng thì người vận hành ngừng đọc nó, và nó mất luôn tác
    dụng của chính mình.
    """
    env.tao_cap(900001, 800001)
    env.vi_the_client(800001)

    run1 = await env.processor.reconciler.run("TEST-1")
    assert len(env.findings(run1, "MASTER_CLOSED_OFFLINE")) == 1

    run2 = await env.processor.reconciler.run("TEST-2")
    assert env.findings(run2) == [], "Vong thu hai khong duoc ghi lai cung sai lech"
    assert len(env.db.list_findings(resolution="PENDING")) == 1


async def test_cap_orphaned_khong_bi_bao_lai_moi_vong(env: Env) -> None:
    """`ORPHANED` nghĩa là đã phát hiện, đã có alert, đang chờ người. Đừng nhắc lại mỗi phút."""
    pair_id = env.tao_cap(900001, 800001)
    env.db.update_pair(pair_id, status="ORPHANED", orphan_side="MASTER")
    env.vi_the_master(900001)     # Master con, Client mat — dung tinh huong da ORPHANED

    run_id = await env.processor.reconciler.run("TEST")
    assert env.findings(run_id) == []


async def test_khong_doi_chieu_khi_master_chua_len(db: Database) -> None:
    """Client thường nối trước Master. Chạy ngay lúc đó chỉ để lại một alert báo giả."""
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash=hash_token(CLIENT_TOKEN),
                    magic_number=MAGIC, account_login=CLIENT_LOGIN)
    db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT)

    server = BridgeServer(db, ServerConfig(host="127.0.0.1", port=0, hello_timeout_sec=1.0,
                                           monitor_interval_sec=0.05,
                                           heartbeat_timeout_ms=8000))
    dispatcher = CommandDispatcher(db, server)
    processor = EventProcessor(db, server, dispatcher)
    await server.start()
    goi: list[str] = []
    processor.reconciler.run = lambda trigger="?": goi.append(trigger)  # type: ignore[assignment]

    client = MockAgent(host="127.0.0.1", port=server.port, token=CLIENT_TOKEN, role="CLIENT",
                       account_login=CLIENT_LOGIN, magic=MAGIC, emit_events=False)
    await client.start()          # chi Client len, Master khong bao gio len
    try:
        await asyncio.sleep(2.0)
        assert goi == [], "Khong duoc doi chieu khi chua co snapshot Master"
        assert not [a for a in db.list_open_alerts() if a["code"] == "RECONCILE_NO_SNAPSHOT"]
    finally:
        await processor.stop()
        await client.kill()
        await server.stop()


# -- F-05: cap ORPHANED phai duoc xem lai khi tinh huong da thay doi ---------------------------

async def test_cap_orphaned_hai_chan_deu_bien_mat_thi_bao_da_xong(env: Env) -> None:
    """`ORPHANED` nằm ngoài `LIVE_STATUSES` nên trước phase 11 nó **không bao giờ** được soi lại.

    Kiểm toán 2026-09-06 tìm thấy `PAIR-20260905-000025` ở đúng tình trạng này: người vận hành đã
    đóng tay chân Master từ hôm trước, sổ sách vẫn ghi Master còn 0.01 lot, và không vòng đối
    chiếu nào từng nhắc tới nó (F-05).
    """
    pair_id = env.tao_cap(900001, 800001, status="ORPHANED")
    # Khong khai bao vi the nao ca: ca hai chan deu da bien mat khoi terminal.

    run_id = await env.processor.reconciler.run("TEST")
    f = env.findings(run_id, "ORPHAN_RESOLVED")
    assert len(f) == 1
    assert f[0]["severity"] == "SAFE"
    assert f[0]["suggested_action"] == "MARK_CLOSED"
    assert f[0]["pair_id"] == pair_id


async def test_cap_orphaned_con_mot_chan_thi_van_im_lang(env: Env) -> None:
    """Chân Client còn đó nghĩa là chưa ai xử lý xong — im lặng, đúng lý do ORPHANED bị loại ra."""
    env.tao_cap(900001, 800001, status="ORPHANED")
    env.vi_the_client(800001)

    run_id = await env.processor.reconciler.run("TEST")
    assert env.findings(run_id, "ORPHAN_RESOLVED") == []


async def test_orphan_resolved_khong_lap_lai_moi_vong(env: Env) -> None:
    """Đúng lý do khiến ORPHANED bị loại ra ban đầu: không được đẻ một dòng mỗi phút."""
    env.tao_cap(900001, 800001, status="ORPHANED")

    dau = await env.processor.reconciler.run("TEST")
    sau = await env.processor.reconciler.run("TEST")
    assert len(env.findings(dau, "ORPHAN_RESOLVED")) == 1
    assert env.findings(sau, "ORPHAN_RESOLVED") == []


# -- F-06: bao cao phai noi dung dieu no do ----------------------------------------------------

async def test_bao_cao_phan_biet_sai_lech_moi_va_tong_dang_cho(env: Env, caplog) -> None:
    """"0 sai lech" tung co nghia la "0 finding MOI", nhung doc ra thanh "so sach khop thuc te".

    Hôm kiểm toán, log ghi `0 sai lech` trong khi 2/2 cặp đều sai và một finding đang chờ.
    """
    import logging

    env.tao_cap(900001, 800001, status="ORPHANED")
    await env.processor.reconciler.run("TEST")          # sinh 1 finding, no nam PENDING

    caplog.set_level(logging.INFO, logger="bridge.engine.reconcile")
    await env.processor.reconciler.run("TEST")          # vong hai: 0 moi, nhung 1 dang cho

    dong = [r.getMessage() for r in caplog.records if "Doi chieu" in r.getMessage()]
    assert dong, "Khong thay dong bao cao doi chieu"
    assert "0 sai lech moi" in dong[-1], dong[-1]
    assert "1 dang cho xu ly" in dong[-1], dong[-1]


# -- B-08: muc alert phai theo hau qua that ----------------------------------------------------

async def test_finding_can_quyet_dinh_thi_bao_muc_ERROR(env: Env) -> None:
    """Chỉ ERROR trở lên mới ra được kênh cảnh báo ngoài, nên mức phải theo mức nghiêm trọng thật."""
    env.tao_cap(900001, 800001)
    env.vi_the_master(900001)
    env.vi_the_client(800001, volume=0.99)      # lech volume -> finding DECISION

    await env.processor.reconciler.run("TEST")
    canh_bao = [a for a in env.db.query_all("SELECT * FROM alert")
                if a["code"] == "RECONCILE_FINDINGS"]
    assert canh_bao and canh_bao[-1]["level"] == "ERROR", canh_bao


async def test_toan_finding_SAFE_thi_o_muc_WARNING(env: Env) -> None:
    """Sai lệch tự dọn được thì để trong dashboard là đủ, không cần làm phiền điện thoại."""
    env.tao_cap(900001, 800001)
    env.vi_the_client(800001)                   # Master khong con -> MASTER_CLOSED_OFFLINE (SAFE)

    await env.processor.reconciler.run("TEST")
    canh_bao = [a for a in env.db.query_all("SELECT * FROM alert")
                if a["code"] == "RECONCILE_FINDINGS"]
    assert canh_bao and canh_bao[-1]["level"] == "WARNING", canh_bao


# -- B-09: sai lech nam cho qua lau phai duoc nhac lai -----------------------------------------

async def test_nhac_lai_khi_finding_nam_cho_qua_lau(env: Env) -> None:
    """Cổng chống trùng khiến mỗi sai lệch chỉ báo **một lần** — đúng, nhưng rồi im luôn.

    Kiểm toán 2026-09-06 tìm thấy một finding nằm `PENDING` suốt cả ngày, đi qua trọn một phiên
    làm việc mà không ai để ý (B-09).
    """
    env.tao_cap(900001, 800001)
    env.vi_the_client(800001)
    await env.processor.reconciler.run("TEST")
    assert not [a for a in env.db.query_all("SELECT * FROM alert") if a["code"] == "FINDING_BO_QUEN"]

    # Day finding lui lai qua han roi chay vong nua.
    with env.db.transaction() as conn:
        conn.execute("UPDATE reconcile_finding SET created_at = '2020-01-01T00:00:00.000Z'")
    await env.processor.reconciler.run("TEST")

    nhac = [a for a in env.db.query_all("SELECT * FROM alert") if a["code"] == "FINDING_BO_QUEN"]
    assert len(nhac) == 1, nhac
    assert nhac[0]["level"] == "ERROR"


async def test_khong_nhac_lai_lien_tuc_trong_cung_cua_so(env: Env) -> None:
    """Nhắc mãi cũng thành rác. Mốc nhắc nằm trong `system_config` nên khởi động lại không xoá."""
    env.tao_cap(900001, 800001)
    env.vi_the_client(800001)
    await env.processor.reconciler.run("TEST")
    with env.db.transaction() as conn:
        conn.execute("UPDATE reconcile_finding SET created_at = '2020-01-01T00:00:00.000Z'")

    for _ in range(3):
        await env.processor.reconciler.run("TEST")

    nhac = [a for a in env.db.query_all("SELECT * FROM alert") if a["code"] == "FINDING_BO_QUEN"]
    assert len(nhac) == 1, f"Nhac {len(nhac)} lan trong cung cua so"
    assert env.db.get_config("finding_nhac_lan_cuoi") is not None


async def test_tat_nhac_duoc_bang_cau_hinh(env: Env) -> None:
    env.db.set_config("finding_nhac_sau_phut", "0")
    env.tao_cap(900001, 800001)
    env.vi_the_client(800001)
    await env.processor.reconciler.run("TEST")
    with env.db.transaction() as conn:
        conn.execute("UPDATE reconcile_finding SET created_at = '2020-01-01T00:00:00.000Z'")
    await env.processor.reconciler.run("TEST")

    assert not [a for a in env.db.query_all("SELECT * FROM alert") if a["code"] == "FINDING_BO_QUEN"]
