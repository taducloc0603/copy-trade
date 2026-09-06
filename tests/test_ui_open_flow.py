"""Test luồng mở lệnh qua giao diện (plan `06b-mo-lenh-qua-giao-dien.md`).

Khác biệt cốt lõi so với `test_open_flow.py`: **ack không mang `position_id`**. Cặp lệnh chỉ
được mở khi event `position_opened` của EA Client tới và tương quan được. Vì vậy phần lớn test
ở đây kiểm tra chuyện ghép — nhất là những ca mà thiết kế phải **từ chối đoán**.

Vòng lặp nền của `EventProcessor` không bật; mỗi test tự gọi `process_pending()`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from bridge.clock import to_iso, utc_now
from bridge.db.repo import Database
from bridge.engine.processor import EventProcessor, open_tag_for
from bridge.protocol.auth import hash_token
from bridge.protocol.dispatcher import CommandDispatcher, new_command_id
from bridge.protocol.server import BridgeServer, ServerConfig
from tests.conftest import CLIENT_AGENT, CLIENT_ID, MASTER_AGENT
from tests.mock_agent import MockAgent
from tests.mock_clicker import MockClicker
from tests.test_server import CLIENT_LOGIN, CLIENT_TOKEN, MASTER_LOGIN, MASTER_TOKEN, _wait_until

MASTER_SYMBOL = "XAUUSD"
CLIENT_SYMBOL = "XAUUSDm"
MAGIC = 770001
CLICKER_AGENT = "AG-CLICKER"
CLICKER_TOKEN = "token-clicker-6b"
CLICKER_LOGIN = 333333

#: `DEAL_REASON_CLIENT` — thứ cả phase này tồn tại để đạt được.
REASON_CLIENT = 0


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
    _position: int = 800000

    # -- kích thích ------------------------------------------------------------------------

    async def emit_master_open(self, position_id: int, volume: float = 1.0,
                               direction: str = "BUY") -> str:
        self._seq += 1
        eid = f"EVT-M-{position_id}-{self._seq}"
        await self.master.send_raw({
            "v": 1, "kind": "event", "ts": to_iso(utc_now()), "id": eid, "seq": self._seq,
            "type": "position_opened",
            "data": {"position_id": position_id, "deal_entry": "IN", "symbol": MASTER_SYMBOL,
                     "direction": direction, "volume_delta": volume, "volume_after": volume,
                     "price": 2650.0, "magic": 0},
        })
        await _wait_until(lambda: self.db.get_event(eid) is not None)
        await self.processor.process_pending()
        return eid

    async def emit_client_open(self, *, comment: str | None = None,
                               order_comment: str | None = None,
                               symbol: str = CLIENT_SYMBOL, direction: str = "SELL",
                               volume: float = 0.5, reason: int | None = REASON_CLIENT,
                               position_id: int | None = None) -> int:
        """EA Client báo một vị thế vừa mở. Đây là **nguồn sự thật** của `position_id`."""
        self._position += 1
        pid = position_id if position_id is not None else self._position
        await self.client.send_event(
            "position_opened", position_id=pid, deal_entry="IN", symbol=symbol,
            direction=direction, volume_delta=volume, volume_after=volume, ticket=pid,
            magic=0, comment=comment, order_comment=order_comment, reason=reason,
        )
        await _wait_until(lambda: self.db.query_one(
            "SELECT 1 FROM event WHERE agent_id = ? AND position_id = ?",
            (CLIENT_AGENT, pid)) is not None)
        await self.processor.process_pending()
        return pid

    # -- quan sát --------------------------------------------------------------------------

    def pairs(self, **where) -> list:
        sql = "SELECT * FROM pair"
        if where:
            sql += " WHERE " + " AND ".join(f"{k} = ?" for k in where)
        return self.db.query_all(sql + " ORDER BY pair_id", tuple(where.values()))

    def only_pair(self):
        rows = self.pairs()
        assert len(rows) == 1, f"Mong doi dung mot pair, co {len(rows)}"
        return rows[0]

    def commands(self, command_type: str | None = None) -> list:
        if command_type is None:
            return self.db.query_all("SELECT * FROM command ORDER BY created_at, command_id")
        return self.db.query_all(
            "SELECT * FROM command WHERE type = ? ORDER BY created_at, command_id",
            (command_type,))

    def alerts(self, code: str) -> list:
        return [a for a in self.db.query_all("SELECT * FROM alert ORDER BY id")
                if a["code"] == code]

    async def wait_ack(self, timeout: float = 3.0) -> None:
        await _wait_until(
            lambda: not self.db.query_all(
                "SELECT 1 FROM command WHERE type = 'OPEN_UI' AND status IN ('PENDING','SENT')"),
            timeout=timeout)


@pytest.fixture
async def env(db: Database) -> AsyncIterator[Env]:
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash=hash_token(MASTER_TOKEN),
                    magic_number=MAGIC, account_login=MASTER_LOGIN)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash=hash_token(CLIENT_TOKEN),
                    magic_number=MAGIC, account_login=CLIENT_LOGIN)
    db.upsert_agent(CLICKER_AGENT, role="CLICKER", token_hash=hash_token(CLICKER_TOKEN),
                    magic_number=MAGIC, account_login=CLICKER_LOGIN)
    db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, copy_mode="OPPOSITE",
                             volume_multiplier=0.5, open_route="UI",
                             clicker_agent_id=CLICKER_AGENT)
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
                       account_login=CLIENT_LOGIN, magic=MAGIC, emit_events=False)
    clicker = MockClicker(host="127.0.0.1", port=server.port, token=CLICKER_TOKEN,
                          role="CLICKER", account_login=CLICKER_LOGIN, magic=MAGIC,
                          known_symbols={CLIENT_SYMBOL})
    await master.start()
    await client.start()
    await clicker.start()
    try:
        yield Env(db, server, dispatcher, processor, master, client, clicker)
    finally:
        await processor.stop()
        for agent in (master, client, clicker):
            await agent.kill()
        await server.stop()


# -- định tuyến ----------------------------------------------------------------------------

async def test_lenh_mo_di_toi_clicker_khong_toi_ea(env: Env) -> None:
    """Client cấu hình `open_route = UI` thì EA Client KHÔNG được nhận lệnh mở."""
    await env.emit_master_open(700001)
    await env.wait_ack()

    opens = env.commands("OPEN")
    assert opens == [], "EA Client khong duoc nhan command OPEN khi di duong giao dien"

    ui = env.commands("OPEN_UI")
    assert len(ui) == 1
    assert ui[0]["target_agent_id"] == CLICKER_AGENT


async def test_payload_open_ui_khong_co_magic_va_co_the(env: Env) -> None:
    """Thiếu `magic` là **lớp bảo vệ thứ hai**: EA sẽ từ chối nếu command đi nhầm địa chỉ."""
    await env.emit_master_open(700002)
    await env.wait_ack()

    command = env.commands("OPEN_UI")[0]
    payload = json.loads(command["payload_json"])
    assert "magic" not in payload
    assert payload["symbol"] == CLIENT_SYMBOL
    assert payload["direction"] == "SELL"      # copy_mode = OPPOSITE
    assert payload["volume"] == 0.5            # multiplier = 0.5

    tag = open_tag_for(command["command_id"])
    assert payload["comment"] == tag
    assert len(tag) <= 31, "The phai song sot qua gioi han comment cua MT5"
    assert env.only_pair()["open_tag"] == tag


async def test_clicker_khong_nhan_request_snapshot(env: Env) -> None:
    """Clicker không có vị thế nào để báo cáo — hỏi nó là hỏi sai người."""
    assert env.commands("REQUEST_SNAPSHOT") != []
    for command in env.commands("REQUEST_SNAPSHOT"):
        assert command["target_agent_id"] != CLICKER_AGENT


def _pair_da_mo(env: Env, master_position_id: int, client_position_id: int) -> str:
    """Một cặp đã OPEN sẵn, để dựng tình huống tranh chấp vị thế."""
    env.db.upsert_master_position(master_position_id, agent_id=MASTER_AGENT,
                                  symbol=MASTER_SYMBOL, direction="BUY", initial_volume=1.0,
                                  current_volume=1.0, status="OPEN")
    pair_id = env.db.create_pending_pair(
        master_position_id, CLIENT_ID, copy_mode="OPPOSITE", master_initial_volume=1.0,
        effective_multiplier=0.5, client_symbol=CLIENT_SYMBOL, client_direction="SELL")
    env.db.mark_pair_open(pair_id, client_position_id=client_position_id,
                          client_ticket=client_position_id, client_volume=0.5)
    return pair_id


# -- tương quan ----------------------------------------------------------------------------

async def test_ghep_bang_the_mo_duoc_cap(env: Env) -> None:
    await env.emit_master_open(700003)
    await env.wait_ack()
    tag = env.only_pair()["open_tag"]

    position_id = await env.emit_client_open(comment=tag)

    pair = env.only_pair()
    assert pair["status"] == "OPEN"
    assert pair["client_position_id"] == position_id
    assert pair["client_initial_volume"] == 0.5
    assert pair["client_open_reason"] == REASON_CLIENT

    command = env.commands("OPEN_UI")[0]
    assert command["result_position_id"] == position_id
    event = env.db.query_one(
        "SELECT * FROM event WHERE agent_id = ? AND position_id = ?",
        (CLIENT_AGENT, position_id))
    assert event["caused_by_command_id"] == command["command_id"]
    assert event["process_status"] == "DONE"


async def test_the_nam_trong_order_comment_cung_ghep_duoc(env: Env) -> None:
    """MT5 có khi giữ comment ở order chứ không ở deal. Cả hai đường đều phải nhận."""
    await env.emit_master_open(700004)
    await env.wait_ack()
    tag = env.only_pair()["open_tag"]

    await env.emit_client_open(comment="", order_comment=f"{tag} extra")
    assert env.only_pair()["status"] == "OPEN"


async def test_event_toi_truoc_ack_van_ghep_dung(env: Env) -> None:
    """Thiết kế không được phụ thuộc thứ tự đến của ack và event."""
    env.clicker.execution_delay_sec = 0.3
    await env.emit_master_open(700005)
    await _wait_until(lambda: bool(env.commands("OPEN_UI")))
    tag = env.only_pair()["open_tag"]

    await env.emit_client_open(comment=tag)
    assert env.only_pair()["status"] == "OPEN", "Cap phai mo duoc truoc ca khi co ack"

    await env.wait_ack()
    assert env.only_pair()["status"] == "OPEN"


async def test_event_lap_lai_khong_ghep_lan_hai(env: Env) -> None:
    await env.emit_master_open(700006)
    await env.wait_ack()
    tag = env.only_pair()["open_tag"]
    position_id = await env.emit_client_open(comment=tag)

    # Gửi lại đúng vị thế đó, như khi EA gửi bù sau khi kết nối lại.
    await env.emit_client_open(comment=tag, position_id=position_id, volume=0.5)

    assert len(env.pairs()) == 1
    assert env.only_pair()["client_position_id"] == position_id
    assert env.alerts("UI_CORRELATE_CONFLICT") == []


async def test_hai_the_cung_khop_thi_khong_doan(env: Env) -> None:
    """Ghép sai một vị thế vào một cặp là sai lệch sổ sách không tự phát hiện được."""
    await env.emit_master_open(700007)
    await env.wait_ack()
    tag_1 = env.only_pair()["open_tag"]

    # Dựng tay một ứng viên thứ hai: cổng "một lệnh đang bay" chặn không cho Bridge tự tạo.
    command_id = new_command_id()
    tag_2 = open_tag_for(command_id)
    env.db.upsert_master_position(700099, agent_id=MASTER_AGENT, symbol=MASTER_SYMBOL,
                                  direction="BUY", initial_volume=1.0, current_volume=1.0,
                                  status="OPEN")
    pair_id = env.db.create_pending_pair(
        700099, CLIENT_ID, copy_mode="OPPOSITE", master_initial_volume=1.0,
        effective_multiplier=0.5, client_symbol=CLIENT_SYMBOL, client_direction="SELL",
        open_tag=tag_2)
    env.db.create_command(command_id, CLICKER_AGENT, "OPEN_UI", pair_id=pair_id,
                          payload_json=json.dumps({"symbol": CLIENT_SYMBOL,
                                                   "direction": "SELL", "volume": 0.5,
                                                   "comment": tag_2}),
                          deadline_at=to_iso(utc_now()))

    await env.emit_client_open(comment=f"{tag_1} {tag_2}")

    assert env.pairs(status="OPEN") == []
    assert len(env.alerts("UI_CORRELATE_AMBIGUOUS")) == 1
    assert env.alerts("UI_CORRELATE_AMBIGUOUS")[0]["level"] == "CRITICAL"


async def test_mat_the_voi_strict_thi_khong_ghep(env: Env) -> None:
    await env.emit_master_open(700008)
    await env.wait_ack()

    await env.emit_client_open(comment="")

    pair = env.only_pair()
    assert pair["status"] == "PENDING_OPEN"
    assert pair["client_position_id"] is None


async def test_mat_the_voi_heuristic_thi_ghep_kem_canh_bao(env: Env) -> None:
    env.db.set_config("ui_fallback_match", "HEURISTIC")
    await env.emit_master_open(700009)
    await env.wait_ack()

    position_id = await env.emit_client_open(comment="")

    pair = env.only_pair()
    assert pair["status"] == "OPEN"
    assert pair["client_position_id"] == position_id
    assert len(env.alerts("UI_CORRELATE_HEURISTIC")) == 1


async def test_heuristic_lech_thong_so_thi_van_khong_ghep(env: Env) -> None:
    """Suy đoán mà không khớp cả symbol, chiều lẫn volume thì là lệnh mở tay (FR-12)."""
    env.db.set_config("ui_fallback_match", "HEURISTIC")
    await env.emit_master_open(700010)
    await env.wait_ack()

    await env.emit_client_open(comment="", volume=0.07)

    assert env.only_pair()["status"] == "PENDING_OPEN"
    assert env.alerts("UI_CORRELATE_HEURISTIC") == []


async def test_lenh_mo_tay_khong_bi_nhan_nham(env: Env) -> None:
    """Không có `OPEN_UI` nào đang chờ thì mọi vị thế trên Client đều là mở tay."""
    position_id = await env.emit_client_open(comment="CBkhongcothat")

    assert env.pairs() == []
    event = env.db.query_one("SELECT * FROM event WHERE position_id = ?", (position_id,))
    assert event["process_status"] == "IGNORED"


async def test_event_toi_qua_muon_thi_khong_ghep(env: Env) -> None:
    env.db.set_config("ui_correlate_grace_ms", "0")
    await env.emit_master_open(700011)
    await env.wait_ack()
    tag = env.only_pair()["open_tag"]

    # Đẩy hạn về quá khứ thay vì chờ thật — thời gian trôi không phải thứ nên test bằng sleep.
    env.db.query_one("SELECT 1")
    with env.db.transaction() as conn:
        conn.execute("UPDATE command SET deadline_at = ? WHERE type = 'OPEN_UI'",
                     ("2020-01-01T00:00:00.000Z",))

    await env.emit_client_open(comment=tag)
    assert env.only_pair()["status"] == "PENDING_OPEN"


async def test_qua_han_tuong_quan_thi_canh_bao_dung_mot_lan(env: Env) -> None:
    env.db.set_config("ui_correlate_grace_ms", "0")
    await env.emit_master_open(700012)
    await env.wait_ack()
    with env.db.transaction() as conn:
        conn.execute("UPDATE command SET deadline_at = ? WHERE type = 'OPEN_UI'",
                     ("2020-01-01T00:00:00.000Z",))

    env.processor.scan_correlation_deadlines()
    env.processor.scan_correlation_deadlines()

    assert len(env.alerts("UI_CORRELATE_EXPIRED")) == 1
    # KHÔNG đánh thất bại: không ghép được không có nghĩa là không có lệnh.
    assert env.only_pair()["status"] == "PENDING_OPEN"


async def test_vi_the_da_thuoc_cap_khac_thi_khong_ghep_lai(env: Env) -> None:
    """Vị thế đã có chủ thì thẻ tương quan cũng không được cướp nó sang cặp khác."""
    await env.emit_master_open(700013)
    await env.wait_ack()
    tagged = env.only_pair()["pair_id"]
    tag = env.only_pair()["open_tag"]
    other = _pair_da_mo(env, master_position_id=700098, client_position_id=800999)

    await env.emit_client_open(comment=tag, position_id=800999)

    assert env.db.get_pair(tagged)["status"] == "PENDING_OPEN"
    assert env.db.get_pair(other)["client_position_id"] == 800999
    assert env.db.get_pair(tagged)["client_position_id"] is None


async def test_rang_buoc_db_la_luoi_an_toan_cuoi_cung(env: Env) -> None:
    """`idx_pair_client_pos` chặn ghép một vị thế vào hai pair, kể cả khi logic phía trên hỏng.

    Gọi thẳng `_bind()` vì đường đi bình thường đã chặn từ trước — mà chính vì thế lưới này
    không bao giờ được kiểm tra nếu không ép nó chạy.
    """
    await env.emit_master_open(700014)
    await env.wait_ack()
    _pair_da_mo(env, master_position_id=700097, client_position_id=800998)

    candidate = env.db.query_all(
        "SELECT c.command_id, c.deadline_at, c.payload_json, p.pair_id, p.open_tag, "
        "       p.client_symbol, p.client_direction "
        "FROM command c JOIN pair p ON p.pair_id = c.pair_id WHERE c.type = 'OPEN_UI'")[0]
    position_id = await env.emit_client_open(comment="khong co the")
    event = env.db.query_one("SELECT * FROM event WHERE position_id = ?", (position_id,))

    status, reason, pair_id = env.processor._bind(
        candidate, event, {"volume": 0.5}, CLIENT_ID, 800998, "ep buoc")

    assert status == "ERROR" and pair_id is None
    assert reason and "xung dot" in reason
    assert len(env.alerts("UI_CORRELATE_CONFLICT")) == 1
    assert env.alerts("UI_CORRELATE_CONFLICT")[0]["level"] == "CRITICAL"


# -- tự kiểm chứng --------------------------------------------------------------------------

async def test_reason_khac_client_thi_bao_dong(env: Env) -> None:
    """Mục tiêu của cả phase phải là giá trị đo được, không phải niềm tin."""
    await env.emit_master_open(700014)
    await env.wait_ack()
    tag = env.only_pair()["open_tag"]

    await env.emit_client_open(comment=tag, reason=3)   # DEAL_REASON_EXPERT

    assert env.only_pair()["status"] == "OPEN"
    assert env.only_pair()["client_open_reason"] == 3
    assert len(env.alerts("UI_REASON_MISMATCH")) == 1
    assert env.alerts("UI_REASON_MISMATCH")[0]["level"] == "CRITICAL"


async def test_thong_so_thuc_te_lech_payload_thi_canh_bao(env: Env) -> None:
    await env.emit_master_open(700015)
    await env.wait_ack()
    tag = env.only_pair()["open_tag"]

    await env.emit_client_open(comment=tag, volume=0.9)

    assert len(env.alerts("UI_PARAM_MISMATCH")) == 1


# -- ngữ nghĩa ack -------------------------------------------------------------------------

async def test_ack_ok_khong_tu_mo_cap(env: Env) -> None:
    """`ok` nói "tôi đã bấm", không nói "vị thế nào"."""
    await env.emit_master_open(700016)
    await env.wait_ack()

    pair = env.only_pair()
    assert pair["status"] == "PENDING_OPEN"
    assert pair["client_position_id"] is None


async def test_ack_rejected_duoc_thu_lai(env: Env) -> None:
    """`rejected` là trạng thái duy nhất chứng minh được là chưa bấm."""
    env.clicker.status_sequence = ["rejected"]
    await env.emit_master_open(700017)
    await _wait_until(lambda: len(env.commands("OPEN_UI")) == 2, timeout=3.0)

    assert env.only_pair()["retry_count"] == 1
    assert env.only_pair()["status"] == "PENDING_OPEN"
    assert len(env.clicker.clicked) == 1, "Lan bi tu choi khong duoc tinh la da bam"


async def test_ack_failed_khong_thu_lai(env: Env) -> None:
    env.clicker.next_status = "failed"
    await env.emit_master_open(700018)
    await env.wait_ack()
    await _wait_until(lambda: bool(env.pairs(status="OPEN_FAILED")), timeout=3.0)

    assert len(env.commands("OPEN_UI")) == 1
    assert env.only_pair()["retry_count"] == 0


async def test_ack_unknown_giu_pending_va_bao_dong(env: Env) -> None:
    """Không biết đã bấm hay chưa thì tuyệt đối không mở thêm lệnh nữa."""
    env.clicker.next_status = "unknown"
    await env.emit_master_open(700019)
    await env.wait_ack()
    await _wait_until(lambda: bool(env.alerts("UI_ACK_UNKNOWN")), timeout=3.0)

    pair = env.only_pair()
    assert pair["status"] == "PENDING_OPEN"
    assert pair["error_message"] == "UI_ACK_UNKNOWN"
    assert len(env.commands("OPEN_UI")) == 1


async def test_ack_unknown_van_ghep_duoc_bang_event_toi_muon(env: Env) -> None:
    env.clicker.next_status = "unknown"
    await env.emit_master_open(700020)
    await env.wait_ack()
    tag = env.only_pair()["open_tag"]

    position_id = await env.emit_client_open(comment=tag)

    pair = env.only_pair()
    assert pair["status"] == "OPEN"
    assert pair["client_position_id"] == position_id


# -- bất biến ------------------------------------------------------------------------------

async def test_gui_lai_cung_command_id_khong_bam_lan_hai(env: Env) -> None:
    """Giết clicker sau khi giữ chỗ, trước khi báo về. Khởi động lại không được bấm lại."""
    env.clicker.swallow_ack = True
    await env.emit_master_open(700021)
    await _wait_until(lambda: len(env.clicker.clicked) == 1, timeout=3.0)

    command_id = env.commands("OPEN_UI")[0]["command_id"]
    env.clicker.restart_journal()          # ack trong bộ nhớ mất, nhật ký trên đĩa còn
    env.clicker.swallow_ack = False

    await env.dispatcher.send_existing(command_id)
    await env.wait_ack()

    command = env.db.get_command(command_id)
    # `unknown` được ghi là TIMEOUT chứ không phải ACK_FAILED — ACK_FAILED sẽ kích hoạt retry.
    assert command["status"] == "TIMEOUT"
    assert command["retmsg"] and "khong biet da bam" in command["retmsg"]
    assert len(env.clicker.clicked) == 1, "TUYET DOI khong duoc bam lan hai"


async def test_mot_lenh_dang_bay_moi_client(env: Env) -> None:
    """Hàng đợi một phần tử là thứ biến tương quan mờ thành bài toán luôn giải được."""
    env.clicker.execution_delay_sec = 0.5
    await env.emit_master_open(700022)
    await _wait_until(lambda: len(env.commands("OPEN_UI")) == 1)

    await env.emit_master_open(700023)

    assert len(env.commands("OPEN_UI")) == 1
    assert len(env.pairs()) == 1
    canh_bao = env.alerts("UI_OPEN_BUSY")
    assert len(canh_bao) == 1
    # Muc ERROR, khong phai WARNING: bo mot lenh copy la mat hedge, va chi ERROR tro len moi
    # duoc kenh canh bao gui ra ngoai (`bridge/alerting.py`, MUC_GUI).
    assert canh_bao[0]["level"] == "ERROR"


# -- canary --------------------------------------------------------------------------------

async def test_clicker_offline_thi_bo_qua_chu_khong_rot_ve_ea(env: Env) -> None:
    """Rơi về đường EA khi clicker hỏng là lặng lẽ vi phạm chính yêu cầu của phase này."""
    await env.clicker.kill()
    await _wait_until(lambda: env.db.get_agent(CLICKER_AGENT)["status"] != "ONLINE", timeout=3.0)

    await env.emit_master_open(700024)

    assert env.commands("OPEN_UI") == []
    assert env.commands("OPEN") == [], "KHONG duoc rot ve duong EA"
    assert env.pairs() == []
    assert len(env.alerts("CLICKER_NOT_AVAILABLE")) == 1


async def test_clicker_degraded_thi_bo_qua(env: Env) -> None:
    """Với role CLICKER, `broker_connected = false` nghĩa là không điều khiển được giao diện."""
    await env.clicker.send_heartbeat(broker_connected=False)
    await _wait_until(lambda: env.db.get_agent(CLICKER_AGENT)["status"] == "DEGRADED",
                      timeout=3.0)

    await env.emit_master_open(700025)

    assert env.commands("OPEN_UI") == []
    assert env.pairs() == []
    assert len(env.alerts("CLICKER_NOT_AVAILABLE")) == 1


async def test_clicker_tu_choi_command_khong_phai_open_ui(env: Env) -> None:
    """Lớp phòng thủ cuối: định tuyến sai cũng không sinh ra lệnh nào."""
    command_id = new_command_id()
    env.db.create_command(command_id, CLICKER_AGENT, "OPEN",
                          payload_json=json.dumps({"symbol": CLIENT_SYMBOL,
                                                   "direction": "BUY", "volume": 0.1,
                                                   "magic": MAGIC}),
                          deadline_at=to_iso(utc_now().replace(year=utc_now().year + 1)))
    await env.dispatcher.send_existing(command_id)
    await _wait_until(lambda: env.db.get_command(command_id)["status"] == "ACK_FAILED",
                      timeout=3.0)

    command = env.db.get_command(command_id)
    assert command["retmsg"] and "khong nhan command loai OPEN" in command["retmsg"]
    assert env.clicker.clicked == []
