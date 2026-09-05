"""Test luồng mở lệnh đầu-cuối (plan mục 6).

Master phát sự kiện → Bridge lọc, tính volume, tạo pair và command → Client thực thi → Bridge
ghi kết quả. Chạy qua mock agent, không cần MT5.

Vòng lặp nền của `EventProcessor` **không** được bật trong test: mỗi test tự gọi
`process_pending()` để thời điểm xử lý là xác định, không phụ thuộc bộ đếm thời gian.
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
from tests.mock_agent import MockAgent
from tests.test_server import CLIENT_LOGIN, CLIENT_TOKEN, MASTER_LOGIN, MASTER_TOKEN, _wait_until

MASTER_SYMBOL = "XAUUSD"
CLIENT_SYMBOL = "XAUUSDm"
MAGIC = 770001


@dataclass
class Env:
    db: Database
    server: BridgeServer
    dispatcher: CommandDispatcher
    processor: EventProcessor
    master: MockAgent
    client: MockAgent
    _seq: int = 0

    async def emit_open(self, position_id: int, volume: float, symbol: str = MASTER_SYMBOL,
                        direction: str = "BUY", event_id: str | None = None,
                        ts_agent: str | None = None) -> str:
        """Master mở một vị thế. Trả về `event_id`."""
        self._seq += 1
        eid = event_id or f"EVT-M-{position_id}-{self._seq}"
        await self.master.send_raw({
            "v": 1, "kind": "event", "ts": ts_agent or to_iso(utc_now()),
            "id": eid, "seq": self._seq, "type": "position_opened",
            "data": {"position_id": position_id, "deal_entry": "IN", "symbol": symbol,
                     "direction": direction, "volume_delta": volume, "volume_after": volume,
                     "price": 2650.0, "magic": 0},
        })
        await _wait_until(lambda: self.db.get_event(eid) is not None)
        return eid

    async def run_processor(self) -> int:
        return await self.processor.process_pending()

    async def copy(self, position_id: int, volume: float, **kwargs) -> str:
        """Mở lệnh Master rồi cho Bridge xử lý. Trả về `event_id`."""
        event_id = await self.emit_open(position_id, volume, **kwargs)
        await self.run_processor()
        return event_id

    def pairs(self, **where) -> list:
        sql = "SELECT * FROM pair"
        if where:
            sql += " WHERE " + " AND ".join(f"{k} = ?" for k in where)
        return self.db.query_all(sql + " ORDER BY pair_id", tuple(where.values()))

    def alerts(self, code: str) -> list:
        return [a for a in self.db.list_open_alerts() if a["code"] == code]

    async def wait_pair(self, status: str, timeout: float = 3.0) -> list:
        await _wait_until(lambda: bool(self.pairs(status=status)), timeout=timeout)
        return self.pairs(status=status)


@pytest.fixture
async def env(db: Database) -> AsyncIterator[Env]:
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash=hash_token(CLIENT_TOKEN),
                    magic_number=MAGIC, account_login=CLIENT_LOGIN)
    db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, copy_mode="OPPOSITE",
                             volume_multiplier=0.5)
    db.upsert_symbol_map(CLIENT_ID, MASTER_SYMBOL, CLIENT_SYMBOL)
    for agent, symbol in ((MASTER_AGENT, MASTER_SYMBOL), (CLIENT_AGENT, CLIENT_SYMBOL)):
        db.replace_symbol_specs(agent, [{
            "symbol": symbol, "digits": 2, "point": 0.01, "volume_min": 0.01,
            "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0,
        }])
    db.set_config("run_mode", "RUNNING")

    server = BridgeServer(db, ServerConfig(host="127.0.0.1", port=0, hello_timeout_sec=1.0,
                                           monitor_interval_sec=0.05,
                                           heartbeat_timeout_ms=5000))
    dispatcher = CommandDispatcher(db, server)
    processor = EventProcessor(db, server, dispatcher)
    await server.start()

    master = MockAgent(host="127.0.0.1", port=server.port, token=MASTER_TOKEN, role="MASTER",
                       account_login=MASTER_LOGIN, magic=MAGIC, emit_events=False)
    client = MockAgent(host="127.0.0.1", port=server.port, token=CLIENT_TOKEN, role="CLIENT",
                       account_login=CLIENT_LOGIN, magic=MAGIC,
                       known_symbols={CLIENT_SYMBOL, "EURUSDm", "GBPUSDm"})
    await master.start()
    await client.start()
    try:
        yield Env(db, server, dispatcher, processor, master, client)
    finally:
        await processor.stop()
        await master.kill()
        await client.kill()
        await server.stop()


# ---------------------------------------------------------------------------------------------
# Đường đi thuận lợi
# ---------------------------------------------------------------------------------------------


async def test_copy_khac_chieu(env: Env) -> None:
    """TEST-02: Master BUY 1.00, hệ số 0.50, khác chiều → Client SELL 0.50."""
    await env.copy(900001, 1.0)
    pairs = await env.wait_pair("OPEN")

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["pair_id"].startswith("PAIR-")
    assert pair["client_symbol"] == CLIENT_SYMBOL
    assert pair["client_direction"] == "SELL"
    assert pair["client_initial_volume"] == 0.5
    assert pair["copy_mode"] == "OPPOSITE"
    assert pair["effective_multiplier"] == pytest.approx(0.5)
    assert pair["open_time_master"] and pair["open_time_client"]


async def test_copy_cung_chieu(env: Env) -> None:
    """TEST-01: cùng dữ liệu, chế độ cùng chiều → Client BUY."""
    env.db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, copy_mode="SAME")
    await env.copy(900001, 1.0)
    pairs = await env.wait_pair("OPEN")
    assert pairs[0]["client_direction"] == "BUY"


async def test_ba_lenh_cung_symbol_tao_ba_pair_id_khac_nhau(env: Env) -> None:
    """TEST-07."""
    for index, position_id in enumerate((900001, 900002, 900003), start=1):
        await env.copy(position_id, 0.1 * index)
    await _wait_until(lambda: len(env.pairs(status="OPEN")) == 3)

    pairs = env.pairs(status="OPEN")
    assert len({p["pair_id"] for p in pairs}) == 3
    assert len({p["master_position_id"] for p in pairs}) == 3
    assert len({p["client_position_id"] for p in pairs}) == 3


async def test_nhieu_symbol_dong_thoi_theo_mapping_rieng(env: Env) -> None:
    """TEST-08: mỗi symbol có ánh xạ và hệ số riêng."""
    env.db.upsert_symbol_map(CLIENT_ID, "EURUSD", "EURUSDm", volume_multiplier=1.0)
    env.db.upsert_symbol_map(CLIENT_ID, "GBPUSD", "GBPUSDm", copy_mode="SAME")
    env.db.replace_symbol_specs(CLIENT_AGENT, [
        {"symbol": s, "volume_min": 0.01, "volume_max": 50.0, "volume_step": 0.01,
         "contract_size": 100.0}
        for s in (CLIENT_SYMBOL, "EURUSDm", "GBPUSDm")
    ])

    await env.copy(900001, 1.0, symbol=MASTER_SYMBOL)
    await env.copy(900002, 1.0, symbol="EURUSD")
    await env.copy(900003, 1.0, symbol="GBPUSD")
    await _wait_until(lambda: len(env.pairs(status="OPEN")) == 3)

    by_symbol = {p["client_symbol"]: p for p in env.pairs(status="OPEN")}
    assert by_symbol[CLIENT_SYMBOL]["client_initial_volume"] == 0.5      # ke thua he so 0.5
    assert by_symbol[CLIENT_SYMBOL]["client_direction"] == "SELL"
    assert by_symbol["EURUSDm"]["client_initial_volume"] == 1.0          # override he so 1.0
    assert by_symbol["GBPUSDm"]["client_direction"] == "BUY"             # override cung chieu


async def test_effective_multiplier_la_ty_le_that_sau_lam_tron(env: Env) -> None:
    """Master 0.07, hệ số 0.33 → Client 0.02, tỷ lệ thật 0.2857 — kiểm tra GIÁ TRỊ TRONG DB."""
    env.db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, volume_multiplier=0.33)
    await env.copy(900001, 0.07)
    pairs = await env.wait_pair("OPEN")

    assert pairs[0]["client_initial_volume"] == 0.02
    assert pairs[0]["effective_multiplier"] == pytest.approx(0.2857, abs=1e-4)


# ---------------------------------------------------------------------------------------------
# Chống copy trùng
# ---------------------------------------------------------------------------------------------


async def test_bom_cung_mot_event_hai_lan_chi_tao_mot_pair(env: Env) -> None:
    event_id = await env.copy(900001, 1.0)
    await env.wait_pair("OPEN")

    # Gửi lại đúng event đó: `record_event()` dedup theo `event_id`.
    await env.emit_open(900001, 1.0, event_id=event_id)
    await env.run_processor()
    await asyncio.sleep(0.2)

    assert len(env.pairs()) == 1


async def test_hai_event_khac_nhau_cung_vi_the_master_chi_tao_mot_pair(env: Env) -> None:
    """Ràng buộc `UNIQUE (master_position_id, client_id)` là lưới cuối cùng."""
    await env.copy(900001, 1.0)
    await env.wait_pair("OPEN")

    await env.copy(900001, 1.0, event_id="EVT-KHAC-ID")
    await asyncio.sleep(0.2)

    assert len(env.pairs()) == 1
    assert len(env.client.positions) == 1


# ---------------------------------------------------------------------------------------------
# Điều kiện lọc (mục 6.2)
# ---------------------------------------------------------------------------------------------


async def test_symbol_khong_co_mapping_thi_khong_copy(env: Env) -> None:
    await env.copy(900001, 1.0, symbol="BTCUSD")
    await _wait_until(lambda: bool(env.alerts("NO_SYMBOL_MAPPING")))

    assert env.pairs() == []
    assert env.db.get_event("EVT-M-900001-1")["process_status"] == "IGNORED"
    # Vẫn phải ghi nhận vị thế Master, để đối chiếu ở phase 8 nhìn thấy.
    assert env.db.get_master_position(900001) is not None


async def test_mapping_bi_tat_thi_khong_copy(env: Env) -> None:
    env.db.upsert_symbol_map(CLIENT_ID, MASTER_SYMBOL, CLIENT_SYMBOL, enabled=0)
    await env.copy(900001, 1.0)
    await asyncio.sleep(0.2)
    assert env.pairs() == []


async def test_run_mode_pause_new_entries_ghi_nhan_nhung_khong_tao_pair(env: Env) -> None:
    env.db.set_config("run_mode", "PAUSE_NEW_ENTRIES")
    event_id = await env.copy(900001, 1.0)
    await asyncio.sleep(0.2)

    assert env.pairs() == []
    assert env.db.get_master_position(900001) is not None, "Van phai ghi nhan vi the Master"
    assert env.db.get_event(event_id)["process_status"] == "IGNORED"


async def test_run_mode_paused_khong_tao_pair(env: Env) -> None:
    env.db.set_config("run_mode", "PAUSED")
    await env.copy(900001, 1.0)
    await asyncio.sleep(0.2)
    assert env.pairs() == []


async def test_event_qua_cu_thi_bo_qua_va_ghi_ro_tuoi(env: Env) -> None:
    old = to_iso(utc_now().replace(year=utc_now().year - 1))
    await env.copy(900001, 1.0, ts_agent=old)
    await _wait_until(lambda: bool(env.alerts("EVENT_TOO_OLD")))

    assert env.pairs() == []
    message = env.alerts("EVENT_TOO_OLD")[0]["message"]
    assert "ms tuoi" in message, f"Canh bao phai ghi ro tuoi thuc te: {message}"


async def test_client_offline_thi_khong_copy_va_khong_de_command_treo(env: Env) -> None:
    await env.client.kill()
    await _wait_until(lambda: env.db.get_agent(CLIENT_AGENT)["status"] == "OFFLINE")

    await env.copy(900001, 1.0)
    await _wait_until(lambda: bool(env.alerts("CLIENT_NOT_AVAILABLE")))

    assert env.pairs() == []
    assert env.db.list_inflight_commands() == [], "Khong duoc de command treo vo han"


async def test_client_degraded_thi_khong_copy(env: Env) -> None:
    """Terminal mất kết nối sàn thì mọi lệnh đều hỏng — đừng gửi."""
    await env.client.send_heartbeat(broker_connected=False)
    await _wait_until(lambda: env.db.get_agent(CLIENT_AGENT)["status"] == "DEGRADED")

    await env.copy(900001, 1.0)
    await _wait_until(lambda: bool(env.alerts("CLIENT_NOT_AVAILABLE")))
    assert env.pairs() == []


async def test_client_bi_tat_thi_khong_copy(env: Env) -> None:
    env.db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, enabled=0)
    await env.copy(900001, 1.0)
    await asyncio.sleep(0.2)
    assert env.pairs() == []


# ---------------------------------------------------------------------------------------------
# Volume dưới mức tối thiểu
# ---------------------------------------------------------------------------------------------


async def test_volume_duoi_muc_toi_thieu_thi_bo_qua_va_canh_bao(env: Env) -> None:
    """Master 0.01, hệ số 0.50, volume_min 0.01 → bỏ qua lệnh, không tạo pair (D-18)."""
    await env.copy(900001, 0.01)
    await _wait_until(lambda: bool(env.alerts("VOLUME_BELOW_MIN")))

    assert env.pairs() == []
    assert env.client.positions == {}


async def test_volume_duoi_toi_thieu_voi_use_min(env: Env) -> None:
    env.db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, below_min_policy="USE_MIN")
    await env.copy(900001, 0.01)
    pairs = await env.wait_pair("OPEN")

    assert pairs[0]["client_initial_volume"] == 0.01
    assert [a["level"] for a in env.alerts("VOLUME_RAISED_TO_MIN")] == ["INFO"]


# ---------------------------------------------------------------------------------------------
# Xử lý ack thất bại (mục 6.5)
# ---------------------------------------------------------------------------------------------


async def test_retry_hai_lan_roi_thanh_cong(env: Env) -> None:
    """Client trả 10004 hai lần rồi thành công → ba command, pair cuối cùng OPEN."""
    env.db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, max_retry=3,
                                 retry_interval_ms=10)
    env.client.retcode_sequence = [10004, 10004]   # hong hai lan roi thanh cong

    await env.copy(900001, 1.0)
    pairs = await env.wait_pair("OPEN", timeout=5.0)

    commands = env.db.query_all(
        "SELECT * FROM command WHERE pair_id = ? AND type = 'OPEN' ORDER BY created_at",
        (pairs[0]["pair_id"],),
    )
    assert len(commands) == 3, f"Mong doi 3 command, co {len(commands)}"
    assert pairs[0]["retry_count"] == 2


async def test_loi_dung_han_thi_open_failed_va_master_khong_bi_dong(env: Env) -> None:
    """Client trả 10019 → hết retry, OPEN_FAILED, alert ERROR, Master giữ nguyên."""
    env.client.next_retcode = 10019
    await env.copy(900001, 1.0)
    pairs = await env.wait_pair("OPEN_FAILED", timeout=5.0)

    assert pairs[0]["error_code"] == 10019
    assert env.alerts("OPEN_FAILED"), "Phai co alert"
    assert [a["level"] for a in env.alerts("OPEN_FAILED")] == ["ERROR"]

    master_commands = env.db.query_all(
        "SELECT * FROM command WHERE target_agent_id = ? AND type = 'CLOSE'", (MASTER_AGENT,)
    )
    assert master_commands == [], "Chinh sach ALERT_ONLY: Master khong duoc dong"


async def test_10019_khong_duoc_retry(env: Env) -> None:
    """Nhóm dừng quan trọng ngang nhóm retry. Retry lệnh thiếu margin chỉ che mất cảnh báo thật."""
    env.db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, max_retry=5,
                                 retry_interval_ms=10)
    env.client.next_retcode = 10019
    await env.copy(900001, 1.0)
    pairs = await env.wait_pair("OPEN_FAILED", timeout=5.0)
    await asyncio.sleep(0.3)

    commands = env.db.query_all(
        "SELECT * FROM command WHERE pair_id = ? AND type = 'OPEN'", (pairs[0]["pair_id"],)
    )
    assert len(commands) == 1, "Khong duoc thu lai loi thuoc nhom dung"


async def test_retry_close_master_gui_lenh_dong_master_va_alert_critical(env: Env) -> None:
    env.db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT,
                                 open_fail_policy="RETRY_CLOSE_MASTER", max_retry=0)
    env.client.next_retcode = 10019
    await env.copy(900001, 1.0)
    await env.wait_pair("OPEN_FAILED", timeout=5.0)

    await _wait_until(lambda: bool(env.db.query_all(
        "SELECT * FROM command WHERE target_agent_id = ? AND type = 'CLOSE'", (MASTER_AGENT,)
    )), timeout=3.0)
    close = env.db.query_all(
        "SELECT * FROM command WHERE target_agent_id = ? AND type = 'CLOSE'", (MASTER_AGENT,)
    )
    assert len(close) == 1
    assert "900001" in close[0]["payload_json"]
    assert env.alerts("CLOSING_MASTER_AFTER_OPEN_FAILURE")
    assert [a["level"] for a in env.alerts("CLOSING_MASTER_AFTER_OPEN_FAILURE")] == ["CRITICAL"]


# ---------------------------------------------------------------------------------------------
# Timeout (mục 6.6)
# ---------------------------------------------------------------------------------------------


async def test_command_open_qua_han_thi_open_failed_va_khong_tu_gui_lai(env: Env) -> None:
    env.client.auto_ack = False
    await env.copy(900001, 1.0)
    await _wait_until(lambda: bool(env.pairs(status="PENDING_OPEN")))
    pair_id = env.pairs(status="PENDING_OPEN")[0]["pair_id"]

    with env.db.transaction() as conn:
        conn.execute(
            "UPDATE command SET deadline_at = '2000-01-01T00:00:00.000Z' WHERE pair_id = ?",
            (pair_id,),
        )
    env.dispatcher.scan_deadlines()

    assert env.db.get_pair(pair_id)["status"] == "OPEN_FAILED"
    assert env.alerts("OPEN_TIMEOUT")

    await asyncio.sleep(0.3)
    commands = env.db.query_all(
        "SELECT * FROM command WHERE pair_id = ? AND type = 'OPEN'", (pair_id,)
    )
    assert len(commands) == 1, "KHONG duoc tu dong gui lai sau timeout (D-13)"


# ---------------------------------------------------------------------------------------------
# Event không thuộc luồng mở lệnh
# ---------------------------------------------------------------------------------------------


async def test_event_do_bot_gay_ra_khong_lan_truyen(env: Env) -> None:
    """D-08: `caused_by_command_id` khác NULL nghĩa là chính bot gây ra."""
    await env.master.send_raw({
        "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": "EVT-BOT", "seq": 50,
        "type": "position_opened", "caused_by_command_id": "CMD-nao-do",
        "data": {"position_id": 900009, "deal_entry": "IN", "symbol": MASTER_SYMBOL,
                 "direction": "BUY", "volume_after": 1.0},
    })
    await _wait_until(lambda: env.db.get_event("EVT-BOT") is not None)
    await env.run_processor()

    assert env.pairs() == []
    assert env.db.get_event("EVT-BOT")["process_status"] == "IGNORED"


async def test_master_dong_thi_client_dong_theo(env: Env) -> None:
    """Phase 7 đã đồng bộ đóng.

    Test này ở phase 6 khẳng định điều **ngược lại** — rằng event đóng bị bỏ qua vì chưa tới
    phạm vi. Giữ nguyên bối cảnh cũ nhưng đảo kỳ vọng, để nếu ai đó vô tình gỡ mất định tuyến
    đóng trong `_route()` thì test này bắt được ngay.
    """
    await env.copy(900001, 1.0)
    await env.wait_pair("OPEN")

    await env.master.send_raw({
        "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": "EVT-CLOSE", "seq": 60,
        "type": "position_closed",
        "data": {"position_id": 900001, "deal_entry": "OUT", "symbol": MASTER_SYMBOL,
                 "direction": "BUY", "volume_delta": 1.0, "volume_after": 0.0},
    })
    await _wait_until(lambda: env.db.get_event("EVT-CLOSE") is not None)
    await env.run_processor()

    assert env.db.get_event("EVT-CLOSE")["process_status"] == "DONE"
    await _wait_until(lambda: bool(env.pairs(status="CLOSED")), timeout=3.0)
    cap = env.pairs(status="CLOSED")[0]
    assert cap["close_source"] == "MASTER"
    assert env.db.get_master_position(900001)["status"] == "CLOSED"
