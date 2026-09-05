"""Test thực thi lệnh phía Client (phase 5).

Chạy qua mock agent, không cần MT5. Test trên terminal thật nằm ở phần nghiệm thu của phase 5.

Test quan trọng nhất của cả phase: **gửi lại cùng `command_id` không được tạo lệnh thứ hai.**
Đây là lần đầu hệ thống gửi lệnh giao dịch thật, nên một lệnh thừa là tiền thật bị mất.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from bridge.clock import to_iso, utc_now
from bridge.db.repo import Database
from bridge.protocol.auth import hash_token
from bridge.protocol.dispatcher import CommandDispatcher
from bridge.protocol.server import BridgeServer, ServerConfig
from tests.conftest import CLIENT_AGENT, MASTER_AGENT
from tests.mock_agent import MockAgent, MockPosition
from tests.test_server import CLIENT_LOGIN, CLIENT_TOKEN, MASTER_LOGIN, MASTER_TOKEN, _wait_until

#: Payload OPEN đầy đủ. Bridge tính sẵn tất cả; EA không tính toán gì thêm (D-01).
OPEN_PAYLOAD = {"symbol": "XAUUSDm", "direction": "SELL", "volume": 0.5,
                "deviation": 20, "magic": 770001}


@pytest.fixture
def agents_db(db: Database) -> Database:
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=770001, account_login=MASTER_LOGIN)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash=hash_token(CLIENT_TOKEN),
                    magic_number=770001, account_login=CLIENT_LOGIN)
    return db


@pytest.fixture
async def stack(agents_db: Database) -> AsyncIterator[tuple[BridgeServer, CommandDispatcher]]:
    server = BridgeServer(agents_db, ServerConfig(
        host="127.0.0.1", port=0, hello_timeout_sec=1.0, monitor_interval_sec=0.05,
        heartbeat_timeout_ms=5000,
    ))
    dispatcher = CommandDispatcher(agents_db, server)
    await server.start()
    try:
        yield server, dispatcher
    finally:
        await server.stop()


def _client(server: BridgeServer, **kwargs: object) -> MockAgent:
    return MockAgent(host="127.0.0.1", port=server.port, token=CLIENT_TOKEN, role="CLIENT",
                     account_login=CLIENT_LOGIN, **kwargs)


async def _ack(db: Database, command_id: str, timeout: float = 3.0) -> dict:
    await _wait_until(
        lambda: db.get_command(command_id)["status"] in ("ACK_OK", "ACK_FAILED", "TIMEOUT"),
        timeout=timeout,
    )
    return dict(db.get_command(command_id))


# ---------------------------------------------------------------------------------------------
# Tính bất biến — phần quan trọng nhất của phase 5
# ---------------------------------------------------------------------------------------------


async def test_gui_lai_cung_command_id_khong_mo_lenh_thu_hai(stack, agents_db) -> None:
    """Test quan trọng nhất của phase. Một lệnh thừa là tiền thật bị mất."""
    server, dispatcher = stack
    agent = _client(server)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD)
        await _ack(agents_db, command_id)
        assert len(agent.positions) == 1

        # Bridge gửi lại đúng command đó (mô phỏng mất ack rồi gửi lại).
        await server.send_to(CLIENT_AGENT, _repeat(command_id, "OPEN", OPEN_PAYLOAD))
        await _wait_until(lambda: command_id in agent.duplicate_commands)
        await asyncio.sleep(0.1)

        assert len(agent.positions) == 1, "Đã mở lệnh thứ hai — tính bất biến hỏng"
        assert agent.executed_commands.count(command_id) == 1
    finally:
        await agent.kill()


async def test_command_trung_tra_lai_ack_cu_nguyen_van(stack, agents_db) -> None:
    server, dispatcher = stack
    agent = _client(server)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD)
        await _ack(agents_db, command_id)
        first = dict(agent.handled_commands[command_id])

        await server.send_to(CLIENT_AGENT, _repeat(command_id, "OPEN", OPEN_PAYLOAD))
        await _wait_until(lambda: command_id in agent.duplicate_commands)

        assert agent.handled_commands[command_id] == first, "Ack lần hai phải y hệt lần đầu"
    finally:
        await agent.kill()


async def test_nhieu_command_khac_nhau_thi_deu_duoc_thuc_thi(stack, agents_db) -> None:
    """Bất biến là theo `command_id`, không phải theo nội dung — hai lệnh giống hệt nhau
    nhưng khác id thì vẫn phải mở hai vị thế."""
    server, dispatcher = stack
    agent = _client(server)
    await agent.start()
    try:
        for _ in range(3):
            command_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD)
            await _ack(agents_db, command_id)
        assert len(agent.positions) == 3
    finally:
        await agent.kill()


def _repeat(command_id: str, command_type: str, payload: dict):
    from bridge.protocol.messages import CommandMessage
    return CommandMessage(
        command_id=command_id, type=command_type, payload=payload,
        deadline_ts=to_iso(utc_now().replace(year=2030)), ts=to_iso(utc_now()),
    )


# ---------------------------------------------------------------------------------------------
# OPEN
# ---------------------------------------------------------------------------------------------


async def test_open_tra_ve_position_id_va_volume_thuc_te(stack, agents_db) -> None:
    server, dispatcher = stack
    agent = _client(server)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD)
        row = await _ack(agents_db, command_id)

        assert row["status"] == "ACK_OK"
        assert row["retcode"] == 10009
        assert row["executed_volume"] == 0.5
        assert row["result_position_id"] is not None
        position = agent.positions[row["result_position_id"]]
        assert position.symbol == "XAUUSDm"
        assert position.direction == "SELL"
    finally:
        await agent.kill()


async def test_open_that_bai_giu_nguyen_retcode(stack, agents_db) -> None:
    """`retcode` nguyên bản, không dịch, không gộp nhóm — Bridge tự phân loại ở phase 6."""
    server, dispatcher = stack
    agent = _client(server, next_retcode=10019)   # 10019 = khong du tien
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD)
        row = await _ack(agents_db, command_id)

        assert row["status"] == "ACK_FAILED"
        assert row["retcode"] == 10019
        assert agent.positions == {}, "Không được mở lệnh khi báo thất bại"
    finally:
        await agent.kill()


@pytest.mark.parametrize("retcode", [10004, 10006, 10013, 10014, 10018, 10021, 10030, 10031])
async def test_moi_ma_loi_deu_di_qua_nguyen_ven(stack, agents_db, retcode: int) -> None:
    """Toàn bộ bảng retcode ở mục 5.3 phải tới được Bridge nguyên vẹn."""
    server, dispatcher = stack
    agent = _client(server, next_retcode=retcode)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD)
        row = await _ack(agents_db, command_id)
        assert row["retcode"] == retcode
        assert row["status"] == "ACK_FAILED"
    finally:
        await agent.kill()


# ---------------------------------------------------------------------------------------------
# CLOSE và CLOSE_PARTIAL
# ---------------------------------------------------------------------------------------------


async def test_close_vi_the_da_bi_dong_tra_ve_already_closed(stack, agents_db) -> None:
    """Tình huống bình thường khi hai bên cùng đóng gần như đồng thời (FR-18), KHÔNG phải lỗi."""
    server, dispatcher = stack
    agent = _client(server)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(
            CLIENT_AGENT, "CLOSE", payload={"position_id": 999999}
        )
        row = await _ack(agents_db, command_id)

        assert row["status"] == "ACK_OK", "already_closed phải được coi là thành công"
        assert agent.handled_commands[command_id]["status"] == "already_closed"
    finally:
        await agent.kill()


async def test_close_dong_dung_vi_the_theo_position_id(stack, agents_db) -> None:
    server, dispatcher = stack
    agent = _client(server)
    agent.positions[4242] = MockPosition(4242, "XAUUSDm", "SELL", 0.5)
    agent.positions[4243] = MockPosition(4243, "XAUUSDm", "SELL", 0.5)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(
            CLIENT_AGENT, "CLOSE", payload={"position_id": 4242}
        )
        row = await _ack(agents_db, command_id)

        assert row["status"] == "ACK_OK"
        assert row["executed_volume"] == 0.5
        assert 4242 not in agent.positions
        assert 4243 in agent.positions, "Chỉ được đóng đúng position_id được chỉ định"
    finally:
        await agent.kill()


async def test_close_partial_dong_dung_volume(stack, agents_db) -> None:
    server, dispatcher = stack
    agent = _client(server)
    agent.positions[4242] = MockPosition(4242, "XAUUSDm", "SELL", 0.5)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(
            CLIENT_AGENT, "CLOSE_PARTIAL", payload={"position_id": 4242, "volume": 0.2}
        )
        row = await _ack(agents_db, command_id)

        assert row["executed_volume"] == 0.2
        assert agent.positions[4242].volume == pytest.approx(0.3)
    finally:
        await agent.kill()


async def test_close_partial_volume_lon_hon_phan_con_lai_thi_dong_het(stack, agents_db) -> None:
    """Không báo lỗi — đóng hết phần còn lại và ack ghi đúng `executed_volume` thực tế."""
    server, dispatcher = stack
    agent = _client(server)
    agent.positions[4242] = MockPosition(4242, "XAUUSDm", "SELL", 0.3)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(
            CLIENT_AGENT, "CLOSE_PARTIAL", payload={"position_id": 4242, "volume": 0.9}
        )
        row = await _ack(agents_db, command_id)

        assert row["status"] == "ACK_OK", "Không được coi là lỗi"
        assert row["executed_volume"] == 0.3, "Phải báo volume THỰC TẾ đã đóng"
        assert 4242 not in agent.positions
    finally:
        await agent.kill()


# ---------------------------------------------------------------------------------------------
# Hàng rào an toàn phía EA (mục 5.4)
# ---------------------------------------------------------------------------------------------


async def test_command_qua_han_bi_tu_choi_khong_dat_lenh(stack, agents_db) -> None:
    """Lệnh cũ không được thực thi muộn.

    `execution_delay_sec` mô phỏng độ trễ khớp lệnh: command tới khi còn hạn, nhưng tới lúc
    agent thực sự xử lý thì đã quá hạn. Đó chính là tình huống hàng rào này sinh ra để chặn.
    """
    server, dispatcher = stack
    agent = _client(server, execution_delay_sec=0.15)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD,
                                               deadline_ms=1)
        row = await _ack(agents_db, command_id)

        assert row["status"] == "ACK_FAILED"
        assert "deadline" in agent.handled_commands[command_id]["retmsg"].lower()
        assert agent.positions == {}, "Không được đặt lệnh khi đã quá hạn"
    finally:
        await agent.kill()


async def test_magic_lech_bi_tu_choi(stack, agents_db) -> None:
    server, dispatcher = stack
    agent = _client(server, magic=770001)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(
            CLIENT_AGENT, "OPEN", payload={**OPEN_PAYLOAD, "magic": 999999}
        )
        row = await _ack(agents_db, command_id)

        assert row["status"] == "ACK_FAILED"
        assert "magic" in agent.handled_commands[command_id]["retmsg"].lower()
        assert agent.positions == {}
    finally:
        await agent.kill()


@pytest.mark.parametrize("volume", [0, -1.0])
async def test_volume_khong_duong_bi_tu_choi(stack, agents_db, volume: float) -> None:
    server, dispatcher = stack
    agent = _client(server)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(
            CLIENT_AGENT, "OPEN", payload={**OPEN_PAYLOAD, "volume": volume}
        )
        row = await _ack(agents_db, command_id)

        assert row["status"] == "ACK_FAILED"
        assert "volume" in agent.handled_commands[command_id]["retmsg"].lower()
        assert agent.positions == {}
    finally:
        await agent.kill()


async def test_symbol_khong_ton_tai_bi_tu_choi_khong_lam_sap_agent(stack, agents_db) -> None:
    server, dispatcher = stack
    agent = _client(server, known_symbols={"XAUUSDm", "EURUSDm"})
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(
            CLIENT_AGENT, "OPEN", payload={**OPEN_PAYLOAD, "symbol": "KHONGCOTHAT"}
        )
        row = await _ack(agents_db, command_id)
        assert row["status"] == "ACK_FAILED"
        assert "symbol" in agent.handled_commands[command_id]["retmsg"].lower()

        # Agent vẫn sống và vẫn nhận command tiếp theo.
        ok_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD)
        assert (await _ack(agents_db, ok_id))["status"] == "ACK_OK"
    finally:
        await agent.kill()


# ---------------------------------------------------------------------------------------------
# `caused_by_command_id` — nền tảng chống vòng lặp ở phase 7
# ---------------------------------------------------------------------------------------------


async def test_event_sinh_tu_command_mang_caused_by_command_id(stack, agents_db) -> None:
    """Không có trường này thì phase 7 sẽ sai (D-08)."""
    server, dispatcher = stack
    agent = _client(server)
    agent.positions[4242] = MockPosition(4242, "XAUUSDm", "SELL", 0.5)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(
            CLIENT_AGENT, "CLOSE", payload={"position_id": 4242}
        )
        await _ack(agents_db, command_id)
        await _wait_until(lambda: agents_db.max_seq_for_agent(CLIENT_AGENT) > 0)

        rows = agents_db.query_all(
            "SELECT * FROM event WHERE agent_id = ? ORDER BY seq", (CLIENT_AGENT,)
        )
        assert len(rows) == 1
        assert rows[0]["type"] == "position_closed"
        assert rows[0]["caused_by_command_id"] == command_id
        assert rows[0]["volume_after"] == 0.0
    finally:
        await agent.kill()


async def test_lenh_mo_tay_khong_mang_caused_by_command_id(stack, agents_db) -> None:
    """Sự kiện do người dùng gây ra phải có `caused_by_command_id = NULL` để được lan truyền."""
    server, _ = stack
    agent = _client(server)
    await agent.start()
    try:
        await agent.send_event("position_opened", position_id=7777, deal_entry="IN",
                               symbol="XAUUSDm", direction="BUY", volume_after=0.1)
        await _wait_until(lambda: agents_db.max_seq_for_agent(CLIENT_AGENT) > 0)

        row = agents_db.query_all(
            "SELECT * FROM event WHERE agent_id = ?", (CLIENT_AGENT,)
        )[0]
        assert row["caused_by_command_id"] is None
    finally:
        await agent.kill()


# ---------------------------------------------------------------------------------------------
# Ack `unknown`
# ---------------------------------------------------------------------------------------------


async def test_ack_unknown_bi_danh_timeout_va_alert_critical(stack, agents_db) -> None:
    """EA giữ chỗ command rồi terminal chết: không biết lệnh đã khớp hay chưa.

    Bridge phải đánh TIMEOUT chứ KHÔNG phải ACK_FAILED — ACK_FAILED sẽ kích hoạt chính sách
    retry ở phase 6 và có thể mở lệnh thứ hai.
    """
    server, dispatcher = stack
    agent = _client(server, auto_ack=False)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD)
        await agent.wait_for_command()
        await agent.send_ack(command_id, status="unknown", retcode=None,
                             retmsg="Command reserved but result unknown after restart")
        await _wait_until(lambda: agents_db.get_command(command_id)["status"] == "TIMEOUT")

        alerts = [a for a in agents_db.list_open_alerts() if a["code"] == "ACK_UNKNOWN"]
        assert len(alerts) == 1
        assert alerts[0]["level"] == "CRITICAL"
    finally:
        await agent.kill()


# ---------------------------------------------------------------------------------------------
# Độ trễ khớp lệnh
# ---------------------------------------------------------------------------------------------


async def test_tre_khop_lenh_khong_lam_mat_ack(stack, agents_db) -> None:
    server, dispatcher = stack
    agent = _client(server, execution_delay_sec=0.3)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD,
                                               deadline_ms=60000)
        assert agents_db.get_command(command_id)["status"] == "SENT"
        row = await _ack(agents_db, command_id)
        assert row["status"] == "ACK_OK"
    finally:
        await agent.kill()
