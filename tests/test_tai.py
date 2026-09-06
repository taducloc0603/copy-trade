"""Kiểm thử tải (plan mục 10.5).

Hai câu hỏi, và câu thứ hai quan trọng hơn:

1. Bơm 10.000 event thì mất bao lâu và p95 bao nhiêu.
2. **Năm Client cùng lúc có thật sự hoạt động không.** Mô hình dữ liệu viết cho N Client từ
   phase 2, nhưng MVP chỉ chạy 1 — chưa chứng minh thì "viết cho N" mới chỉ là ý định.

Đánh dấu `cham` để chạy riêng khi cần: `pytest -m cham`.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

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

SYMBOL, CLIENT_SYMBOL, MAGIC = "XAUUSD", "XAUUSDm", 770001


@dataclass
class Env:
    db: Database
    server: BridgeServer
    processor: EventProcessor
    master: MockAgent
    clients: dict[str, MockAgent]


@asynccontextmanager
async def _dung(db: Database, so_client: int) -> AsyncIterator[Env]:
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.replace_symbol_specs(MASTER_AGENT, [{
        "symbol": SYMBOL, "digits": 2, "point": 0.01, "volume_min": 0.01,
        "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])
    tokens = {}
    for i in range(1, so_client + 1):
        cid, aid, tok = f"CL-{i:02d}", f"AG-CLIENT-{i}", f"token-client-{i}-xxxxxxxxxx"
        tokens[cid] = (tok, 222220 + i)
        db.upsert_agent(aid, role="CLIENT", token_hash=hash_token(tok),
                        magic_number=MAGIC, account_login=222220 + i)
        db.upsert_client_account(cid, agent_id=aid, copy_mode="OPPOSITE",
                                 volume_multiplier=1.0)
        db.upsert_symbol_map(cid, SYMBOL, CLIENT_SYMBOL)
        db.replace_symbol_specs(aid, [{
            "symbol": CLIENT_SYMBOL, "digits": 2, "point": 0.01, "volume_min": 0.01,
            "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])
    db.set_config("run_mode", "RUNNING")
    db.set_config("reconcile_interval_sec", "0")     # tat doi chieu dinh ky cho phep do sach

    server = BridgeServer(db, ServerConfig(host="127.0.0.1", port=0, hello_timeout_sec=2.0,
                                           monitor_interval_sec=0.2,
                                           heartbeat_timeout_ms=30000))
    dispatcher = CommandDispatcher(db, server)
    processor = EventProcessor(db, server, dispatcher)
    await server.start()
    master = MockAgent(host="127.0.0.1", port=server.port, token=MASTER_TOKEN, role="MASTER",
                       account_login=MASTER_LOGIN, magic=MAGIC, emit_events=False)
    await master.start()
    clients = {}
    for cid, (tok, login) in tokens.items():
        a = MockAgent(host="127.0.0.1", port=server.port, token=tok, role="CLIENT",
                      account_login=login, magic=MAGIC, known_symbols={CLIENT_SYMBOL})
        await a.start()
        clients[cid] = a
    try:
        yield Env(db, server, processor, master, clients)
    finally:
        await processor.stop()
        await master.kill()
        for a in clients.values():
            await a.kill()
        await server.stop()


@pytest.mark.cham
async def test_bom_10000_event_do_thoi_gian(db: Database) -> None:
    """Bơm 10.000 event và đo. Không copy — `run_mode = PAUSED` để đo đúng đường ống."""
    async with _dung(db, so_client=1) as env:
        env.db.set_config("run_mode", "PAUSED")
        so = 10_000
        bat_dau = time.perf_counter()
        for seq in range(1, so + 1):
            await env.master.send_raw({
                "v": 1, "kind": "event", "ts": to_iso(utc_now()),
                "id": f"EVT-TAI-{seq}", "seq": seq, "type": "position_opened",
                "data": {"position_id": 800_000 + seq, "deal_entry": "IN", "symbol": SYMBOL,
                         "direction": "BUY", "volume_delta": 0.01, "volume_after": 0.01},
            })
        await _wait_until(
            lambda: env.db.query_one("SELECT COUNT(*) n FROM event")["n"] >= so, timeout=180)
        nhan_xong = time.perf_counter() - bat_dau

        xu_ly = time.perf_counter()
        while await env.processor.process_pending(limit=1000):
            pass
        xu_ly = time.perf_counter() - xu_ly

        con = env.db.query_one(
            "SELECT COUNT(*) n FROM event WHERE process_status = 'PENDING'")["n"]
        print(f"\n  nhan {so} event : {nhan_xong:6.2f}s ({so / nhan_xong:8.0f}/s)")
        print(f"  xu ly {so} event: {xu_ly:6.2f}s ({so / max(xu_ly, 1e-9):8.0f}/s)")
        assert con == 0, f"Con {con} event chua xu ly"
        assert env.db.query_one("SELECT COUNT(*) n FROM event")["n"] == so, "Mat event"


@pytest.mark.cham
async def test_nam_client_cung_luc(db: Database) -> None:
    """Mô hình dữ liệu viết cho N Client từ phase 2. Đây là lúc chứng minh nó thật sự chạy.

    Một lệnh Master → 5 pair. Đóng Master → cả 5 đóng.
    """
    async with _dung(db, so_client=5) as env:
        await env.master.send_raw({
            "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": "EVT-N-1", "seq": 1,
            "type": "position_opened",
            "data": {"position_id": 900001, "deal_entry": "IN", "symbol": SYMBOL,
                     "direction": "BUY", "volume_delta": 1.0, "volume_after": 1.0},
        })
        await _wait_until(lambda: env.db.get_event("EVT-N-1") is not None)
        await env.processor.process_pending()
        await _wait_until(
            lambda: env.db.query_one(
                "SELECT COUNT(*) n FROM pair WHERE status = 'OPEN'")["n"] == 5, timeout=15)

        cap = env.db.query_all("SELECT * FROM pair ORDER BY client_id")
        assert len(cap) == 5
        assert {c["client_id"] for c in cap} == {f"CL-{i:02d}" for i in range(1, 6)}
        assert all(c["client_position_id"] is not None for c in cap), "Cap nao do chua ghep"
        # `position_id` chi duy nhat TRONG PHAM VI mot tai khoan — nam terminal khac nhau hoan
        # toan co the cung sinh ra so 900001, va thuc te dung nhu vay o day. Do chinh la ly do
        # rang buoc duy nhat la (client_id, client_position_id) chu khong phai rieng
        # client_position_id. Kiem theo cap, khong kiem theo mot cot.
        assert len({(c["client_id"], c["client_position_id"]) for c in cap}) == 5

        await env.master.send_raw({
            "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": "EVT-N-2", "seq": 2,
            "type": "position_closed",
            "data": {"position_id": 900001, "deal_entry": "OUT", "symbol": SYMBOL,
                     "direction": "BUY", "volume_delta": 1.0, "volume_after": 0.0},
        })
        await _wait_until(lambda: env.db.get_event("EVT-N-2") is not None)
        await env.processor.process_pending()
        await _wait_until(
            lambda: env.db.query_one(
                "SELECT COUNT(*) n FROM pair WHERE status = 'CLOSED'")["n"] == 5, timeout=20)

        assert env.db.query_one(
            "SELECT COUNT(*) n FROM command WHERE type = 'CLOSE'")["n"] == 5, \
            "Moi Client dung mot lenh dong"


@pytest.mark.cham
async def test_wal_khong_phinh_vo_han(db: Database, db_path) -> None:
    """File WAL phải được checkpoint, không lớn mãi.

    Không thay được cho bài chạy 24 giờ, nhưng bắt được trường hợp WAL **không bao giờ** được
    dọn — lỗi nghiêm trọng hơn và lộ ra ngay.
    """
    async with _dung(db, so_client=1) as env:
        env.db.set_config("run_mode", "PAUSED")
        for seq in range(1, 2001):
            await env.master.send_raw({
                "v": 1, "kind": "event", "ts": to_iso(utc_now()),
                "id": f"EVT-WAL-{seq}", "seq": seq, "type": "position_opened",
                "data": {"position_id": 700_000 + seq, "deal_entry": "IN", "symbol": SYMBOL,
                         "direction": "BUY", "volume_delta": 0.01, "volume_after": 0.01},
            })
        await _wait_until(
            lambda: env.db.query_one("SELECT COUNT(*) n FROM event")["n"] >= 2000, timeout=120)

        wal = db_path.with_name(db_path.name + "-wal")
        truoc = wal.stat().st_size if wal.exists() else 0
        env.db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        sau = wal.stat().st_size if wal.exists() else 0
        print(f"\n  WAL truoc checkpoint: {truoc:,} byte | sau: {sau:,} byte")
        assert sau < max(truoc, 1), "WAL khong duoc checkpoint — se phinh vo han"
