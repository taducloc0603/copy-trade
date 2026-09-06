"""Test TCP server: bắt tay, khung dòng qua mạng thật, chuỗi sự kiện, heartbeat."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import pytest

from bridge.db.repo import Database
from bridge.protocol.auth import hash_token
from bridge.protocol.framing import encode_line
from bridge.protocol.server import BridgeServer, ServerConfig
from tests.conftest import CLIENT_AGENT, MASTER_AGENT
from tests.mock_agent import MockAgent

MASTER_TOKEN = "token-cua-master-1234567890"
CLIENT_TOKEN = "token-cua-client-0987654321"
MASTER_LOGIN = 111111
CLIENT_LOGIN = 222222


@pytest.fixture
def agents_db(db: Database) -> Database:
    """DB có sẵn hai agent với token đã băm."""
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=770001, account_login=MASTER_LOGIN)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash=hash_token(CLIENT_TOKEN),
                    magic_number=770001, account_login=CLIENT_LOGIN)
    return db


@pytest.fixture
async def server(agents_db: Database) -> AsyncIterator[BridgeServer]:
    """Server chạy trên cổng ngẫu nhiên, thời gian chờ rút ngắn cho test."""
    instance = BridgeServer(agents_db, ServerConfig(
        host="127.0.0.1", port=0, hello_timeout_sec=0.4, monitor_interval_sec=0.05,
        heartbeat_timeout_ms=300,
    ))
    await instance.start()
    try:
        yield instance
    finally:
        await instance.stop()


def _master(server: BridgeServer, **kwargs: object) -> MockAgent:
    return MockAgent(host="127.0.0.1", port=server.port, token=MASTER_TOKEN, role="MASTER",
                     account_login=MASTER_LOGIN, **kwargs)


def _client(server: BridgeServer, **kwargs: object) -> MockAgent:
    return MockAgent(host="127.0.0.1", port=server.port, token=CLIENT_TOKEN, role="CLIENT",
                     account_login=CLIENT_LOGIN, **kwargs)


async def _wait_until(predicate, timeout: float = 2.0) -> None:
    """Chờ tới khi điều kiện đúng. Dùng cho các thay đổi xảy ra trong task nền của server."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Điều kiện không xảy ra trong thời gian chờ")


# ---------------------------------------------------------------------------------------------
# Bắt tay
# ---------------------------------------------------------------------------------------------


async def test_bat_tay_thanh_cong_voi_token_dung(server: BridgeServer,
                                                 agents_db: Database) -> None:
    agent = _master(server)
    reply = await agent.start()
    try:
        assert reply["kind"] == "hello_ack"
        assert reply["agent_id"] == MASTER_AGENT
        assert reply["last_seq"] == 0
        assert reply["config"]["heartbeat_interval_ms"] == 1000
        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["status"] == "ONLINE")
    finally:
        await agent.kill()


async def test_token_sai_bi_tu_choi_va_khong_co_log_nao_chua_token(
    server: BridgeServer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="bridge")
    bad_token = "TOKEN-SAI-KHONG-DUOC-XUAT-HIEN-TRONG-LOG"
    agent = MockAgent(host="127.0.0.1", port=server.port, token=bad_token, role="MASTER",
                      account_login=MASTER_LOGIN)
    await agent.connect()
    try:
        reply = await agent.handshake()
        assert reply["kind"] == "error"
        assert reply["code"] == "BAD_TOKEN"
    finally:
        await agent.kill()

    for record in caplog.records:
        assert bad_token not in record.getMessage(), "Token lọt vào log"
        assert bad_token not in str(record.args or ""), "Token lọt vào log qua args"


async def test_account_login_lech_bi_tu_choi(server: BridgeServer) -> None:
    """Một token chỉ dùng cho đúng một tài khoản MT5."""
    agent = _master(server)
    await agent.connect()
    try:
        reply = await agent.handshake(account_login=999999)
        assert reply["kind"] == "error"
        assert reply["code"] == "ACCOUNT_MISMATCH"
    finally:
        await agent.kill()


async def test_role_lech_bi_tu_choi(server: BridgeServer) -> None:
    agent = _master(server)
    await agent.connect()
    try:
        reply = await agent.handshake(role="CLIENT")
        assert reply["kind"] == "error"
        assert reply["code"] == "ROLE_MISMATCH"
    finally:
        await agent.kill()


async def test_agent_bi_vo_hieu_hoa_khong_ket_noi_duoc(server: BridgeServer,
                                                       agents_db: Database) -> None:
    with agents_db.transaction() as conn:
        conn.execute("UPDATE agent SET enabled = 0 WHERE agent_id = ?", (MASTER_AGENT,))
    agent = _master(server)
    await agent.connect()
    try:
        reply = await agent.handshake()
        assert reply["kind"] == "error"
        assert reply["code"] == "AGENT_DISABLED"
    finally:
        await agent.kill()


async def test_khong_gui_hello_thi_bi_dong_ket_noi(server: BridgeServer) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    try:
        data = await asyncio.wait_for(reader.read(65536), 2.0)
        # Hoặc nhận message error rồi kết nối đóng, hoặc bị đóng thẳng.
        if data:
            assert b"HELLO_TIMEOUT" in data
        assert await asyncio.wait_for(reader.read(65536), 2.0) == b""
    finally:
        writer.close()


async def test_gui_message_khac_truoc_hello_bi_tu_choi(server: BridgeServer) -> None:
    agent = _master(server)
    await agent.connect()
    try:
        await agent.send_heartbeat()
        reply = await agent.expect("error")
        assert reply["code"] == "HELLO_EXPECTED"
    finally:
        await agent.kill()


async def test_ket_noi_thu_hai_cung_agent_dong_ket_noi_cu(server: BridgeServer) -> None:
    """Terminal khởi động lại là chuyện thường; kết nối cũ chỉ là xác chết."""
    first = _master(server)
    await first.start()
    second = _master(server)
    try:
        reply = await second.start()
        assert reply["kind"] == "hello_ack"
        await _wait_until(lambda: server.connections.get(MASTER_AGENT) is not None)
        assert server.connections[MASTER_AGENT].peer == second.writer.get_extra_info(
            "sockname"
        )[0] + ":" + str(second.writer.get_extra_info("sockname")[1])

        # Kết nối mới hoạt động bình thường.
        await second.send_heartbeat()
        await _wait_until(lambda: server.db.get_agent(MASTER_AGENT)["status"] == "ONLINE")
    finally:
        await first.kill()
        await second.kill()


# ---------------------------------------------------------------------------------------------
# Khung dòng qua mạng thật
# ---------------------------------------------------------------------------------------------


async def test_message_bi_cat_lam_ba_manh_tcp_van_xu_ly_dung(server: BridgeServer,
                                                             agents_db: Database) -> None:
    agent = _master(server)
    await agent.start()
    try:
        data = encode_line({
            "v": 1, "kind": "event", "id": "EVT-CAT", "seq": 1, "type": "position_opened",
            "data": {"position_id": 1, "deal_entry": "IN", "volume_after": 1.0},
        })
        a, b = len(data) // 3, 2 * len(data) // 3
        await agent.send_bytes(data[:a])
        await asyncio.sleep(0.02)
        await agent.send_bytes(data[a:b])
        await asyncio.sleep(0.02)
        await agent.send_bytes(data[b:])

        await _wait_until(lambda: agents_db.get_event("EVT-CAT") is not None)
    finally:
        await agent.kill()


async def test_hai_message_dinh_trong_mot_goi_tcp(server: BridgeServer,
                                                  agents_db: Database) -> None:
    agent = _master(server)
    await agent.start()
    try:
        blob = b"".join(
            encode_line({
                "v": 1, "kind": "event", "id": f"EVT-{i}", "seq": i, "type": "position_opened",
                "data": {"position_id": i, "deal_entry": "IN", "volume_after": 1.0},
            })
            for i in (1, 2)
        )
        await agent.send_bytes(blob)
        await _wait_until(lambda: agents_db.get_event("EVT-2") is not None)
        assert agents_db.get_event("EVT-1") is not None
    finally:
        await agent.kill()


async def test_dong_rac_khong_lam_sap_ket_noi(server: BridgeServer, agents_db: Database,
                                              caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR, logger="bridge")
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_bytes(b"day khong phai json\n")
        await agent.send_event("position_opened", position_id=1, deal_entry="IN",
                               volume_after=1.0, event_id="EVT-SAU-RAC")

        await _wait_until(lambda: agents_db.get_event("EVT-SAU-RAC") is not None)
        assert any("khong giai ma duoc" in r.getMessage() for r in caplog.records)
    finally:
        await agent.kill()


async def test_message_sai_schema_nhan_error_nhung_ket_noi_van_song(
    server: BridgeServer, agents_db: Database
) -> None:
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_raw({"v": 1, "kind": "event", "id": "EVT-X", "seq": 1,
                              "type": "position_closed",
                              "data": {"position_id": 1, "deal_entry": "OUT"}})
        reply = await agent.expect("error")
        assert reply["code"] == "BAD_MESSAGE"

        await agent.send_event("position_opened", position_id=1, deal_entry="IN",
                               volume_after=1.0, event_id="EVT-SAU-LOI")
        await _wait_until(lambda: agents_db.get_event("EVT-SAU-LOI") is not None)
        assert agents_db.get_event("EVT-X") is None, "Event sai schema không được vào DB"
    finally:
        await agent.kill()


async def test_dong_qua_dai_thi_dong_ket_noi(agents_db: Database) -> None:
    instance = BridgeServer(agents_db, ServerConfig(
        host="127.0.0.1", port=0, hello_timeout_sec=1.0, monitor_interval_sec=0.05,
        heartbeat_timeout_ms=5000, max_line_bytes=2048,
    ))
    await instance.start()
    agent = _master(instance)
    try:
        await agent.start()
        await agent.send_bytes(b"x" * 8192)
        await _wait_until(lambda: MASTER_AGENT not in instance.connections, timeout=3.0)
    finally:
        await agent.kill()
        await instance.stop()


# ---------------------------------------------------------------------------------------------
# Chuỗi sự kiện và gửi bù
# ---------------------------------------------------------------------------------------------


async def test_seq_nhay_coc_thi_bridge_yeu_cau_gui_bu(server: BridgeServer) -> None:
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_event("position_opened", seq=1, position_id=1, deal_entry="IN",
                               volume_after=1.0)
        await agent.send_event("position_opened", seq=5, position_id=5, deal_entry="IN",
                               volume_after=1.0)
        resend = await agent.expect("resend")
        assert resend["from_seq"] == 2
    finally:
        await agent.kill()


async def test_gui_bu_xong_thi_last_seq_duoi_kip(server: BridgeServer,
                                                 agents_db: Database) -> None:
    """`last_seq` chỉ nhảy qua lỗ hổng khi lỗ hổng đã được lấp."""
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_event("position_opened", seq=1, position_id=1, deal_entry="IN",
                               volume_after=1.0)
        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["last_seq"] == 1)

        await agent.send_event("position_opened", seq=4, position_id=4, deal_entry="IN",
                               volume_after=1.0)
        await agent.expect("resend")
        await asyncio.sleep(0.05)
        assert agents_db.get_agent(MASTER_AGENT)["last_seq"] == 1, "Không được nhảy qua lỗ hổng"

        await agent.send_event("position_opened", seq=2, position_id=2, deal_entry="IN",
                               volume_after=1.0)
        await agent.send_event("position_opened", seq=3, position_id=3, deal_entry="IN",
                               volume_after=1.0)
        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["last_seq"] == 4)
    finally:
        await agent.kill()


async def test_gui_lai_event_seq_cu_khong_tao_ban_ghi_thu_hai(server: BridgeServer,
                                                              agents_db: Database) -> None:
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_event("position_opened", seq=1, event_id="EVT-TRUNG", position_id=1,
                               deal_entry="IN", volume_after=1.0)
        await _wait_until(lambda: agents_db.get_event("EVT-TRUNG") is not None)

        await agent.send_event("position_opened", seq=1, event_id="EVT-TRUNG", position_id=1,
                               deal_entry="IN", volume_after=1.0)
        await asyncio.sleep(0.1)

        rows = agents_db.query_all("SELECT * FROM event WHERE agent_id = ?", (MASTER_AGENT,))
        assert len(rows) == 1
    finally:
        await agent.kill()


async def test_hello_khai_seq_cao_hon_bridge_thi_duoc_yeu_cau_gui_bu(
    server: BridgeServer,
) -> None:
    """Agent nối lại sau khi đã sinh event lúc Bridge chết."""
    agent = _master(server, seq=7)
    await agent.connect()
    try:
        reply = await agent.handshake(seq=7)
        assert reply["kind"] == "hello_ack"
        assert reply["last_seq"] == 0
        resend = await agent.expect("resend")
        assert resend["from_seq"] == 1
    finally:
        await agent.kill()


async def test_1000_event_voi_vai_lan_ngat_ket_noi(server: BridgeServer,
                                                   agents_db: Database) -> None:
    """Tiêu chí hoàn thành của phase 3: DB có đúng 1000 event, seq liên tục, không lỗ hổng."""
    total = 1000
    seq = 0
    for _ in range(4):
        agent = _master(server, seq=seq)
        await agent.start(seq=seq)
        try:
            for _ in range(total // 4):
                seq += 1
                await agent.send_event("position_opened", seq=seq, position_id=seq,
                                       deal_entry="IN", volume_after=1.0)
            await _wait_until(
                lambda s=seq: agents_db.get_agent(MASTER_AGENT)["last_seq"] == s, timeout=10.0
            )
        finally:
            await agent.kill()  # ngắt đột ngột giữa chừng

    rows = agents_db.query_all(
        "SELECT seq FROM event WHERE agent_id = ? ORDER BY seq", (MASTER_AGENT,)
    )
    assert len(rows) == total
    assert [r["seq"] for r in rows] == list(range(1, total + 1)), "Chuỗi seq có lỗ hổng"
    assert agents_db.get_agent(MASTER_AGENT)["last_seq"] == total


# ---------------------------------------------------------------------------------------------
# Heartbeat và trạng thái agent
# ---------------------------------------------------------------------------------------------


async def test_ngung_heartbeat_thi_chuyen_offline_va_co_alert(server: BridgeServer,
                                                              agents_db: Database) -> None:
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_heartbeat()
        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["status"] == "ONLINE")

        # Không gửi gì nữa; heartbeat_timeout_ms = 300 trong fixture.
        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["status"] == "OFFLINE")
        alerts = [a for a in agents_db.list_open_alerts() if a["code"] == "AGENT_OFFLINE"]
        assert alerts, "Phải có alert khi agent mất kết nối"
        # Master offline là CRITICAL, Client offline là ERROR (plan 8.2). Mất Master nghĩa là
        # mù hoàn toàn về nguồn lệnh; mất một Client chỉ mất một nhánh copy.
        assert alerts[0]["level"] == "CRITICAL"
    finally:
        await agent.kill()


async def test_client_offline_la_error_chu_khong_phai_critical(server: BridgeServer,
                                                               agents_db: Database) -> None:
    agent = _client(server)
    await agent.start()
    try:
        await agent.send_heartbeat()
        await _wait_until(lambda: agents_db.get_agent(CLIENT_AGENT)["status"] == "ONLINE")
        await _wait_until(lambda: agents_db.get_agent(CLIENT_AGENT)["status"] == "OFFLINE")
        alerts = [a for a in agents_db.list_open_alerts()
                  if a["code"] == "AGENT_OFFLINE" and a["agent_id"] == CLIENT_AGENT]
        assert alerts and alerts[0]["level"] == "ERROR"
    finally:
        await agent.kill()


async def test_broker_connected_false_thi_degraded_va_alert_error(server: BridgeServer,
                                                                  agents_db: Database) -> None:
    """Đây là trạng thái nguy hiểm nhất: nhìn từ ngoài hệ thống có vẻ vẫn khoẻ."""
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_heartbeat(broker_connected=False)
        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["status"] == "DEGRADED")

        alerts = [a for a in agents_db.list_open_alerts() if a["code"] == "AGENT_DEGRADED"]
        assert alerts, "Phải có alert khi terminal mất kết nối sàn"
        assert alerts[0]["level"] == "ERROR"
        assert agents_db.get_agent(MASTER_AGENT)["broker_connected"] == 0
    finally:
        await agent.kill()


async def test_khong_tao_alert_lap_lai_moi_vong_quet(server: BridgeServer,
                                                     agents_db: Database) -> None:
    """Alert lặp mỗi vòng quét sẽ làm người vận hành quen với màu đỏ."""
    agent = _master(server)
    await agent.start()
    try:
        for _ in range(5):
            await agent.send_heartbeat(broker_connected=False)
            await asyncio.sleep(0.02)
        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["status"] == "DEGRADED")
        await asyncio.sleep(0.2)

        alerts = [a for a in agents_db.list_open_alerts() if a["code"] == "AGENT_DEGRADED"]
        assert len(alerts) == 1
    finally:
        await agent.kill()


async def test_heartbeat_ghi_equity_va_do_tre(server: BridgeServer,
                                              agents_db: Database) -> None:
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_heartbeat(equity=12345.67, margin_level=250.5)
        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["equity"] == 12345.67)
        row = agents_db.get_agent(MASTER_AGENT)
        assert row["margin_level"] == 250.5
        assert row["latency_ms"] is not None
    finally:
        await agent.kill()


async def test_ngat_ket_noi_thi_agent_chuyen_offline(server: BridgeServer,
                                                     agents_db: Database) -> None:
    agent = _master(server)
    await agent.start()
    await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["status"] == "ONLINE")
    await agent.kill()
    await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["status"] == "OFFLINE")


# ---------------------------------------------------------------------------------------------
# symbol_specs và snapshot
# ---------------------------------------------------------------------------------------------


async def test_symbol_specs_duoc_ghi_de_vao_db(server: BridgeServer,
                                               agents_db: Database) -> None:
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_symbol_specs([
            {"symbol": "XAUUSD", "digits": 2, "volume_min": 0.01, "volume_step": 0.01,
             "volume_max": 50.0, "contract_size": 100.0},
            {"symbol": "EURUSD", "digits": 5, "volume_min": 0.01, "volume_step": 0.01,
             "volume_max": 100.0, "contract_size": 100000.0},
        ])
        await _wait_until(
            lambda: agents_db.get_symbol_spec(MASTER_AGENT, "EURUSD") is not None
        )
        spec = agents_db.get_symbol_spec(MASTER_AGENT, "XAUUSD")
        assert spec["volume_step"] == 0.01
        assert spec["contract_size"] == 100.0
    finally:
        await agent.kill()


async def test_ten_symbol_ngoai_ascii_khong_hong(server: BridgeServer,
                                                 agents_db: Database) -> None:
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_symbol_specs([{"symbol": "XAUUSD€ß", "volume_min": 0.01}])
        await _wait_until(
            lambda: agents_db.get_symbol_spec(MASTER_AGENT, "XAUUSD€ß") is not None
        )
    finally:
        await agent.kill()


async def test_hai_event_trung_event_id_qua_duong_mang_chi_tao_mot_ban_ghi(
    server: BridgeServer, agents_db: Database
) -> None:
    """Ràng buộc DB của phase 2 vẫn phải đứng vững khi đi qua đường mạng.

    Khác test trên: `seq` tăng bình thường nên đi vào nhánh "event mới", và chỉ có `event_id`
    trùng. Dedup phải chặn ở tầng `record_event()`.
    """
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_event("position_opened", seq=1, event_id="EVT-CUNG-ID", position_id=1,
                               deal_entry="IN", volume_after=1.0)
        await _wait_until(lambda: agents_db.get_event("EVT-CUNG-ID") is not None)

        await agent.send_event("position_closed", seq=2, event_id="EVT-CUNG-ID", position_id=1,
                               deal_entry="OUT", volume_after=0.0)
        await asyncio.sleep(0.15)

        rows = agents_db.query_all("SELECT * FROM event WHERE agent_id = ?", (MASTER_AGENT,))
        assert len(rows) == 1, "event_id trùng phải bị dedup, không tạo bản ghi thứ hai"
        assert rows[0]["type"] == "position_opened", "Bản ghi đầu tiên thắng"
    finally:
        await agent.kill()


async def test_lo_hong_khong_lap_duoc_thi_dung_lai_chu_khong_hoi_mai(
        server: BridgeServer, agents_db: Database) -> None:
    """Tái hiện đúng sự cố ngày 2026-09-05 đã làm treo EA.

    Bridge có `last_seq = 0`, EA đang ở seq cao, và những seq ở giữa **không tồn tại ở cả hai
    bên** (xảy ra khi tạo lại DB hoặc khôi phục từ bản sao lưu). Bản cũ hỏi gửi bù cho từng
    event lệch thứ tự, mà mỗi lần hỏi lại kéo về nhiều event lệch thứ tự nữa — mỗi vòng nhân
    lên, hàng nghìn message trong 0,4 giây.
    """
    agent = _master(server)
    await agent.start()
    try:
        # EA chỉ còn giữ 11..14; seq 1..10 đã biến mất vĩnh viễn ở cả hai bên.
        for seq in (11, 12, 13, 14):
            await agent.send_event("position_opened", seq=seq, position_id=seq,
                                   deal_entry="IN", volume_after=1.0)

        await _wait_until(
            lambda: any(a["code"] == "EVENT_GAP_UNFILLED"
                        for a in agents_db.list_open_alerts()), timeout=3.0
        )
        alert = next(a for a in agents_db.list_open_alerts()
                     if a["code"] == "EVENT_GAP_UNFILLED")
        assert alert["level"] == "CRITICAL"
        assert "1..13" in alert["message"], "Alert phai ghi ro khoang seq da mat"

        # Số lần hỏi có trần, không bùng nổ.
        so_lan_hoi = sum(1 for m in agent.inbox if m.get("kind") == "resend")
        assert so_lan_hoi <= 3, f"Hoi gui bu {so_lan_hoi} lan, phai co tran"

        # Và quan trọng nhất: hệ thống đi tiếp được thay vì bế tắc vĩnh viễn.
        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["last_seq"] == 14,
                          timeout=3.0)
        await agent.send_event("position_opened", seq=15, position_id=15, deal_entry="IN",
                               volume_after=1.0)
        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["last_seq"] == 15,
                          timeout=3.0)
        # Event thật sự nhận được vẫn nằm nguyên trong DB — chỉ khoảng trống là bị bỏ.
        assert agents_db.query_one("SELECT COUNT(*) AS n FROM event")["n"] == 5
    finally:
        await agent.kill()


async def test_lo_hong_lap_duoc_thi_khong_bao_dong_va_khong_bo_event(
        server: BridgeServer, agents_db: Database) -> None:
    """Trần hỏi gửi bù không được làm hỏng đường đi bình thường."""
    agent = _master(server)
    await agent.start()
    try:
        await agent.send_event("position_opened", seq=3, position_id=3, deal_entry="IN",
                               volume_after=1.0)
        await agent.expect("resend")
        for seq in (1, 2):
            await agent.send_event("position_opened", seq=seq, position_id=seq,
                                   deal_entry="IN", volume_after=1.0)

        await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["last_seq"] == 3)
        assert not [a for a in agents_db.list_open_alerts()
                    if a["code"] == "EVENT_GAP_UNFILLED"]
        assert agents_db.query_one("SELECT COUNT(*) AS n FROM event")["n"] == 3
    finally:
        await agent.kill()


async def test_bo_dem_hoi_gui_bu_dat_lai_khi_noi_lai(server: BridgeServer,
                                                     agents_db: Database) -> None:
    """Hỏi lại là chuyện của một phiên. Nối lại thì agent xứng đáng được hỏi lại từ đầu."""
    agent = _master(server)
    await agent.start()
    for seq in (20, 21, 22, 23):
        await agent.send_event("position_opened", seq=seq, position_id=seq,
                               deal_entry="IN", volume_after=1.0)
    await _wait_until(lambda: any(a["code"] == "EVENT_GAP_UNFILLED"
                                  for a in agents_db.list_open_alerts()), timeout=3.0)
    await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["last_seq"] == 23, timeout=3.0)
    await agent.kill()

    lai = _master(server)
    await lai.start()
    try:
        await lai.send_event("position_opened", seq=40, position_id=40, deal_entry="IN",
                             volume_after=1.0)
        resend = await lai.expect("resend", timeout=3.0)
        assert resend["from_seq"] == 24, "Phien moi phai duoc hoi lai tu dau"
    finally:
        await lai.kill()


async def test_agent_offline_chi_log_mot_lan(server: BridgeServer,
                                             caplog: pytest.LogCaptureFixture) -> None:
    """Vòng quét chạy mỗi vài trăm ms; in mỗi vòng làm nhoè log đúng lúc cần đọc log."""
    agent = _master(server)
    await agent.start()
    try:
        caplog.set_level(logging.WARNING, logger="bridge.protocol.server")
        for _ in range(5):
            server.check_heartbeats()
        im_lang = [r for r in caplog.records if "im lặng quá" in r.getMessage()]
        assert len(im_lang) <= 1, f"In {len(im_lang)} lan cho cung mot lan chuyen OFFLINE"
    finally:
        await agent.kill()


async def test_trang_thai_online_cu_bi_don_khi_bridge_khoi_dong(agents_db: Database) -> None:
    """Bridge chết đột ngột để lại `ONLINE` trong DB; lần khởi động sau phải dọn.

    `check_heartbeats()` chỉ duyệt `self.connections` — rỗng lúc khởi động — nên nếu không dọn
    ở đây thì dòng `ONLINE` cũ **không bao giờ** được sửa cho tới khi chính agent đó nối lại.
    Cổng canary của D-25 đọc đúng cột này, nên trạng thái cũ làm nó gác nhầm.
    """
    with agents_db.transaction() as conn:
        conn.execute("UPDATE agent SET status = 'ONLINE'")
    assert agents_db.get_agent(MASTER_AGENT)["status"] == "ONLINE"

    instance = BridgeServer(agents_db, ServerConfig(host="127.0.0.1", port=0))
    await instance.start()
    try:
        assert agents_db.get_agent(MASTER_AGENT)["status"] == "OFFLINE"
        assert agents_db.get_agent(CLIENT_AGENT)["status"] == "OFFLINE"
    finally:
        await instance.stop()


async def test_agent_ve_offline_khi_bridge_dung(server: BridgeServer,
                                                agents_db: Database) -> None:
    agent = _master(server)
    await agent.start()
    await _wait_until(lambda: agents_db.get_agent(MASTER_AGENT)["status"] == "ONLINE")
    await server.stop()
    try:
        assert agents_db.get_agent(MASTER_AGENT)["status"] == "OFFLINE"
    finally:
        await agent.kill()
