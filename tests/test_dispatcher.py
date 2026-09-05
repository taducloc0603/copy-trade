"""Test outbox command.

Trọng tâm: thứ tự ghi-trước-gửi-sau, và phân biệt "chưa gửi được" với "đã gửi mà không có
phản hồi". Trộn lẫn hai thứ đó là cách làm hỏng phần đối chiếu ở phase 8.
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


#: Payload OPEN đầy đủ, đúng như Bridge sẽ gửi ở phase 6: mọi thông số đã tính sẵn.
OPEN_PAYLOAD = {"symbol": "XAUUSDm", "direction": "SELL", "volume": 0.5,
                "deviation": 20, "magic": 770001}


def _client(server: BridgeServer, **kwargs: object) -> MockAgent:
    return MockAgent(host="127.0.0.1", port=server.port, token=CLIENT_TOKEN, role="CLIENT",
                     account_login=CLIENT_LOGIN, **kwargs)


# ---------------------------------------------------------------------------------------------
# Ghi trước, gửi sau
# ---------------------------------------------------------------------------------------------


async def test_command_duoc_ghi_vao_db_truoc_khi_gui(stack, agents_db: Database) -> None:
    server, dispatcher = stack
    agent = _client(server, auto_ack=False)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "CLOSE", pair_id=None,
                                               payload={"position_id": 4242})
        row = agents_db.get_command(command_id)
        assert row is not None, "Command phải có trong DB"
        assert row["status"] == "SENT"
        assert row["attempt"] == 1
        assert row["sent_at"] is not None
        assert row["deadline_at"] is not None

        received = await agent.wait_for_command()
        assert received["command_id"] == command_id
        assert received["type"] == "CLOSE"
        assert received["payload"] == {"position_id": 4242}
        assert received["deadline_ts"] == row["deadline_at"]
    finally:
        await agent.kill()


async def test_command_cho_agent_offline_nam_lai_pending(stack, agents_db: Database) -> None:
    _, dispatcher = stack
    command_id = await dispatcher.dispatch(CLIENT_AGENT, "CLOSE")

    row = agents_db.get_command(command_id)
    assert row["status"] == "PENDING", "Chưa gửi được thì không được đánh SENT"
    assert row["sent_at"] is None
    assert row["attempt"] == 0


async def test_agent_noi_lai_thi_command_ton_dong_duoc_gui(stack, agents_db: Database) -> None:
    server, dispatcher = stack
    command_id = await dispatcher.dispatch(CLIENT_AGENT, "CLOSE", payload={"position_id": 7})
    assert agents_db.get_command(command_id)["status"] == "PENDING"

    agent = _client(server, auto_ack=False)
    await agent.start()
    try:
        received = await agent.wait_for_command("CLOSE", timeout=3.0)
        assert received["command_id"] == command_id
        await _wait_until(lambda: agents_db.get_command(command_id)["status"] == "SENT")
    finally:
        await agent.kill()


async def test_bat_tay_xong_thi_bridge_yeu_cau_snapshot(stack, agents_db: Database) -> None:
    server, _ = stack
    agent = _client(server)
    agent.positions[4242] = MockPosition(position_id=4242, symbol="XAUUSDm", direction="SELL",
                                         volume=0.5, magic=770001)
    agent.positions[9999] = MockPosition(position_id=9999, symbol="EURUSDm", direction="BUY",
                                         volume=0.1)
    await agent.start()
    try:
        await _wait_until(lambda: CLIENT_AGENT in server.latest_snapshots, timeout=3.0)
        snapshot = server.latest_snapshots[CLIENT_AGENT]
        assert {p.position_id for p in snapshot.positions} == {4242, 9999}
        # Gồm cả vị thế không mang magic của bot (FR-12).
        assert [p.magic for p in snapshot.positions if p.position_id == 9999] == [None]
    finally:
        await agent.kill()


# ---------------------------------------------------------------------------------------------
# Ack
# ---------------------------------------------------------------------------------------------


async def test_ack_thanh_cong_duoc_ghi_vao_db(stack, agents_db: Database) -> None:
    server, dispatcher = stack
    agent = _client(server)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "OPEN", payload=OPEN_PAYLOAD)
        await _wait_until(
            lambda: agents_db.get_command(command_id)["status"] == "ACK_OK", timeout=3.0
        )
        row = agents_db.get_command(command_id)
        assert row["retcode"] == 10009
        assert row["executed_volume"] == 0.5
        assert row["acked_at"] is not None
    finally:
        await agent.kill()


async def test_ack_that_bai_giu_nguyen_retcode(stack, agents_db: Database) -> None:
    """`retcode` giữ nguyên bản để Bridge tự phân loại ở phase 6."""
    server, dispatcher = stack
    agent = _client(server, next_retcode=10019)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(
            CLIENT_AGENT, "OPEN", payload={**OPEN_PAYLOAD, "volume": 100.0}
        )
        await _wait_until(
            lambda: agents_db.get_command(command_id)["status"] == "ACK_FAILED", timeout=3.0
        )
        assert agents_db.get_command(command_id)["retcode"] == 10019
    finally:
        await agent.kill()


async def test_ack_already_closed_duoc_coi_la_thanh_cong(stack, agents_db: Database) -> None:
    """Hai bên cùng đóng gần như đồng thời là tình huống bình thường (FR-18)."""
    server, dispatcher = stack
    agent = _client(server, auto_ack=False)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "CLOSE")
        await agent.wait_for_command()
        await agent.send_ack(command_id, status="already_closed", retcode=10009)
        await _wait_until(lambda: agents_db.get_command(command_id)["status"] == "ACK_OK")
    finally:
        await agent.kill()


async def test_ack_cho_command_khong_ton_tai_khong_lam_sap(stack, agents_db: Database) -> None:
    server, _ = stack
    agent = _client(server, auto_ack=False)
    await agent.start()
    try:
        await agent.send_ack("CMD-khong-co-that")
        await agent.send_heartbeat()
        await _wait_until(lambda: agents_db.get_agent(CLIENT_AGENT)["equity"] == 10000.0)
    finally:
        await agent.kill()


# ---------------------------------------------------------------------------------------------
# Hạn
# ---------------------------------------------------------------------------------------------


async def test_command_qua_han_khong_co_ack_thi_timeout_va_co_alert(
    stack, agents_db: Database
) -> None:
    server, dispatcher = stack
    agent = _client(server, auto_ack=False)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "CLOSE", deadline_ms=1)
        await agent.wait_for_command()
        await asyncio.sleep(0.05)

        assert dispatcher.scan_deadlines() == 1
        assert agents_db.get_command(command_id)["status"] == "TIMEOUT"
        alerts = [a for a in agents_db.list_open_alerts() if a["code"] == "COMMAND_TIMEOUT"]
        assert len(alerts) == 1
        assert alerts[0]["level"] == "ERROR"
    finally:
        await agent.kill()


async def test_command_pending_qua_han_khong_bi_danh_timeout(stack,
                                                             agents_db: Database) -> None:
    """"Chưa gửi được" khác hẳn "đã gửi mà không có phản hồi" — không được trộn lẫn."""
    _, dispatcher = stack
    command_id = await dispatcher.dispatch(CLIENT_AGENT, "CLOSE", deadline_ms=1)
    await asyncio.sleep(0.05)

    assert dispatcher.scan_deadlines() == 0
    assert agents_db.get_command(command_id)["status"] == "PENDING"
    assert [a for a in agents_db.list_open_alerts() if a["code"] == "COMMAND_TIMEOUT"] == []


async def test_command_da_co_ack_khong_bi_danh_timeout(stack, agents_db: Database) -> None:
    """Đã có ack rồi thì quá hạn cũng không được đánh TIMEOUT."""
    server, dispatcher = stack
    agent = _client(server)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "CLOSE", deadline_ms=60000)
        await _wait_until(
            lambda: agents_db.get_command(command_id)["status"] == "ACK_OK", timeout=3.0
        )
        # Đẩy hạn về quá khứ sau khi đã có ack.
        with agents_db.transaction() as conn:
            conn.execute(
                "UPDATE command SET deadline_at = '2000-01-01T00:00:00.000Z' "
                "WHERE command_id = ?", (command_id,)
            )
        assert dispatcher.scan_deadlines() == 0
        assert agents_db.get_command(command_id)["status"] == "ACK_OK"
    finally:
        await agent.kill()


async def test_scan_deadlines_khong_dung_toi_command_chua_toi_han(stack,
                                                                  agents_db: Database) -> None:
    server, dispatcher = stack
    agent = _client(server, auto_ack=False)
    await agent.start()
    try:
        command_id = await dispatcher.dispatch(CLIENT_AGENT, "CLOSE", deadline_ms=60000)
        await agent.wait_for_command()
        assert dispatcher.scan_deadlines() == 0
        assert agents_db.get_command(command_id)["status"] == "SENT"
    finally:
        await agent.kill()


async def test_deadline_at_duoc_tinh_tu_bay_gio(stack, agents_db: Database) -> None:
    _, dispatcher = stack
    command_id = await dispatcher.dispatch(CLIENT_AGENT, "CLOSE", deadline_ms=5000)
    deadline = agents_db.get_command(command_id)["deadline_at"]
    assert deadline > to_iso(utc_now())
