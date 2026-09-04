"""Test tầng repository."""

from __future__ import annotations

import re
import sqlite3

import pytest

from bridge.clock import day_key
from bridge.db.repo import PAIR_ID_MAX_PER_DAY, Database, PairIdExhausted
from tests.conftest import CLIENT_AGENT, CLIENT_ID, MASTER_AGENT, MASTER_POSITION_ID

PAIR_ID_RE = re.compile(r"^PAIR-\d{8}-\d{6}$")

# ---------------------------------------------------------------------------------------------
# Giao dịch
# ---------------------------------------------------------------------------------------------


def test_giao_dich_loi_thi_rollback(seeded: Database) -> None:
    with pytest.raises(RuntimeError):
        with seeded.transaction() as conn:
            conn.execute("UPDATE master_position SET symbol = 'DA_SUA'")
            raise RuntimeError("hỏng giữa chừng")
    row = seeded.get_master_position(MASTER_POSITION_ID)
    assert row["symbol"] == "XAUUSD"


def test_giao_dich_long_nhau_chi_commit_o_lop_ngoai_cung(seeded: Database) -> None:
    """Phase 6 cần gói ba lệnh ghi vào đúng một giao dịch — lồng nhau phải hoạt động."""
    with pytest.raises(RuntimeError):
        with seeded.transaction():
            seeded.create_alert("INFO", "TEST", "trong giao dịch ngoài")
            seeded.upsert_client_account("CL-02", agent_id=CLIENT_AGENT)
            raise RuntimeError("hỏng sau khi các hàm con đã COMMIT của riêng chúng")
    assert seeded.list_open_alerts() == []
    assert seeded.get_client_account("CL-02") is None


# ---------------------------------------------------------------------------------------------
# Pair ID
# ---------------------------------------------------------------------------------------------


def test_sinh_1000_pair_id_khong_trung_dung_dinh_dang_dung_ngay(db: Database) -> None:
    today = day_key()
    ids = [db.next_pair_id() for _ in range(1000)]
    assert len(set(ids)) == 1000, "Có Pair ID trùng"
    for index, pair_id in enumerate(ids, start=1):
        assert PAIR_ID_RE.match(pair_id), f"Sai định dạng: {pair_id}"
        assert pair_id == f"PAIR-{today}-{index:06d}"


def test_bo_dem_pair_id_reset_theo_ngay(db: Database) -> None:
    assert db.next_pair_id("20260101") == "PAIR-20260101-000001"
    assert db.next_pair_id("20260101") == "PAIR-20260101-000002"
    assert db.next_pair_id("20260102") == "PAIR-20260102-000001"
    assert db.next_pair_id("20260101") == "PAIR-20260101-000003"


def test_het_pair_id_trong_ngay_thi_bao_loi(db: Database) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO pair_id_seq (day, last_number) VALUES (?, ?)",
            ("20260101", PAIR_ID_MAX_PER_DAY),
        )
    with pytest.raises(PairIdExhausted):
        db.next_pair_id("20260101")


# ---------------------------------------------------------------------------------------------
# event
# ---------------------------------------------------------------------------------------------


def test_record_event_trung_event_id_tra_ve_ban_ghi_cu(seeded: Database) -> None:
    first, created = seeded.record_event("EVT-M-1", MASTER_AGENT, 1, "position_opened",
                                         position_id=123, volume_after=1.0)
    assert created is True

    second, created_again = seeded.record_event("EVT-M-1", MASTER_AGENT, 1, "position_opened",
                                                position_id=123, volume_after=1.0)
    assert created_again is False, "Phải nhận ra là bản trùng"
    assert second["id"] == first["id"]
    assert len(seeded.query_all("SELECT * FROM event")) == 1


def test_record_event_trung_event_id_khong_nem_exception_du_du_lieu_khac(
    seeded: Database,
) -> None:
    """Dedup theo `event_id` là tuyệt đối: cùng id thì bản ghi đầu tiên thắng."""
    seeded.record_event("EVT-M-1", MASTER_AGENT, 1, "position_opened", volume_after=1.0)
    row, created = seeded.record_event("EVT-M-1", MASTER_AGENT, 1, "position_closed",
                                       volume_after=0.0)
    assert created is False
    assert row["type"] == "position_opened"
    assert row["volume_after"] == 1.0


def test_hai_event_cung_agent_va_seq_thi_bao_loi(seeded: Database) -> None:
    """Hai sự kiện khác nhau mang cùng số thứ tự là dấu hiệu agent hỏng — phải nhìn thấy."""
    seeded.record_event("EVT-M-1", MASTER_AGENT, 7, "position_opened")
    with pytest.raises(sqlite3.IntegrityError):
        seeded.record_event("EVT-M-2", MASTER_AGENT, 7, "position_closed")


def test_cung_seq_khac_agent_van_duoc(seeded: Database) -> None:
    seeded.record_event("EVT-M-1", MASTER_AGENT, 7, "position_opened")
    seeded.record_event("EVT-C-1", CLIENT_AGENT, 7, "position_opened")
    assert len(seeded.query_all("SELECT * FROM event")) == 2


def test_claim_next_pending_event_theo_thu_tu_id(seeded: Database) -> None:
    for seq in (1, 2, 3):
        seeded.record_event(f"EVT-M-{seq}", MASTER_AGENT, seq, "position_opened")
    seeded.record_event("EVT-C-1", CLIENT_AGENT, 1, "position_opened")

    assert seeded.claim_next_pending_event()["event_id"] == "EVT-M-1"
    seeded.mark_event_processed("EVT-M-1", "DONE")
    assert seeded.claim_next_pending_event()["event_id"] == "EVT-M-2"
    assert seeded.claim_next_pending_event(CLIENT_AGENT)["event_id"] == "EVT-C-1"


def test_claim_next_pending_event_tra_none_khi_het(seeded: Database) -> None:
    assert seeded.claim_next_pending_event() is None


def test_mark_event_processed_ghi_dung_trang_thai(seeded: Database) -> None:
    seeded.record_event("EVT-M-1", MASTER_AGENT, 1, "position_opened")
    seeded.mark_event_processed("EVT-M-1", "IGNORED", error="symbol khong co mapping")
    row = seeded.get_event("EVT-M-1")
    assert row["process_status"] == "IGNORED"
    assert row["process_error"] == "symbol khong co mapping"
    assert row["processed_at"] is not None


def test_max_seq_for_agent(seeded: Database) -> None:
    assert seeded.max_seq_for_agent(MASTER_AGENT) == 0
    seeded.record_event("EVT-M-1", MASTER_AGENT, 5, "position_opened")
    seeded.record_event("EVT-M-2", MASTER_AGENT, 9, "position_opened")
    assert seeded.max_seq_for_agent(MASTER_AGENT) == 9
    assert seeded.max_seq_for_agent(CLIENT_AGENT) == 0


# ---------------------------------------------------------------------------------------------
# pair
# ---------------------------------------------------------------------------------------------


def test_create_pending_pair_lan_hai_tra_none_khong_nem_loi(seeded: Database) -> None:
    """Event lặp không phải lỗi — trả về None để nơi gọi ghi INFO rồi bỏ qua."""
    pair_id = seeded.create_pending_pair(MASTER_POSITION_ID, CLIENT_ID, "OPPOSITE", 1.0, 0.5)
    assert pair_id is not None

    again = seeded.create_pending_pair(MASTER_POSITION_ID, CLIENT_ID, "OPPOSITE", 1.0, 0.5)
    assert again is None
    assert len(seeded.query_all("SELECT * FROM pair")) == 1


def test_find_pair_by_client_position(seeded: Database) -> None:
    pair_id = seeded.create_pending_pair(MASTER_POSITION_ID, CLIENT_ID, "OPPOSITE", 1.0, 0.5)
    assert seeded.find_pair_by_client_position(CLIENT_ID, 8888) is None

    seeded.mark_pair_open(pair_id, client_position_id=8888, client_ticket=99, client_volume=0.5)
    found = seeded.find_pair_by_client_position(CLIENT_ID, 8888)
    assert found is not None
    assert found["pair_id"] == pair_id


def test_list_pairs_needing_attention_sap_theo_muc_nghiem_trong(seeded: Database) -> None:
    """ORPHANED và OPEN_FAILED lên đầu; cặp đang chạy bình thường không xuất hiện."""
    statuses = ["OPEN", "OPEN_FAILED", "ORPHANED", "PARTIALLY_CLOSED", "CLOSED"]
    for index, status in enumerate(statuses):
        position_id = MASTER_POSITION_ID + 10 + index
        seeded.upsert_master_position(
            position_id, agent_id=MASTER_AGENT, symbol="XAUUSD", direction="BUY",
            initial_volume=1.0, current_volume=1.0, status="OPEN",
        )
        pair_id = seeded.create_pending_pair(position_id, CLIENT_ID, "OPPOSITE", 1.0, 0.5)
        seeded.update_pair(pair_id, status=status)

    rows = seeded.list_pairs_needing_attention()
    assert [r["status"] for r in rows] == ["ORPHANED", "OPEN_FAILED"]


def test_update_pair_khong_co_truong_thi_khong_lam_gi(seeded: Database) -> None:
    pair_id = seeded.create_pending_pair(MASTER_POSITION_ID, CLIENT_ID, "OPPOSITE", 1.0, 0.5)
    before = seeded.get_pair(pair_id)["updated_at"]
    seeded.update_pair(pair_id)
    assert seeded.get_pair(pair_id)["updated_at"] == before


# ---------------------------------------------------------------------------------------------
# Vòng đời đầy đủ — tiêu chí hoàn thành của phase 2
# ---------------------------------------------------------------------------------------------


def test_vong_doi_day_du_tu_pending_open_toi_closed(seeded: Database) -> None:
    """Dựng một cặp lệnh hoàn chỉnh chỉ bằng các hàm repository, chưa cần mạng."""
    # 1. Master mở lệnh.
    seeded.record_event("EVT-M-1", MASTER_AGENT, 1, "position_opened",
                        position_id=MASTER_POSITION_ID, deal_entry="IN", volume_after=1.0)

    # 2. Tạo pair và command OPEN trong CÙNG một giao dịch (đúng như phase 6 sẽ làm).
    with seeded.transaction():
        pair_id = seeded.create_pending_pair(
            MASTER_POSITION_ID, CLIENT_ID, copy_mode="OPPOSITE",
            master_initial_volume=1.0, effective_multiplier=0.5,
            client_symbol="XAUUSDm", client_direction="SELL", open_time_master="2026-01-01",
        )
        seeded.create_command("CMD-1", CLIENT_AGENT, "OPEN", pair_id=pair_id,
                              payload_json='{"volume": 0.5}')
    assert seeded.get_pair(pair_id)["status"] == "PENDING_OPEN"

    # 3. Gửi command rồi nhận ack thành công.
    seeded.mark_command_sent("CMD-1")
    assert seeded.get_command("CMD-1")["status"] == "SENT"
    assert seeded.get_command("CMD-1")["attempt"] == 1
    seeded.mark_command_acked("CMD-1", "ACK_OK", retcode=10009, executed_volume=0.5,
                              result_position_id=4242)
    seeded.mark_pair_open(pair_id, client_position_id=4242, client_ticket=777, client_volume=0.5)
    seeded.mark_event_processed("EVT-M-1", "DONE", pair_id=pair_id)

    opened = seeded.get_pair(pair_id)
    assert opened["status"] == "OPEN"
    assert opened["client_position_id"] == 4242
    assert opened["client_initial_volume"] == 0.5
    assert opened["effective_multiplier"] == 0.5

    # 4. Master đóng hoàn toàn.
    seeded.record_event("EVT-M-2", MASTER_AGENT, 2, "position_closed",
                        position_id=MASTER_POSITION_ID, deal_entry="OUT", volume_after=0.0,
                        pair_id=pair_id)
    seeded.update_pair(pair_id, status="CLOSING")
    seeded.create_command("CMD-2", CLIENT_AGENT, "CLOSE", pair_id=pair_id)
    assert len(seeded.list_inflight_commands(pair_id)) == 1

    seeded.mark_command_sent("CMD-2")
    seeded.mark_command_acked("CMD-2", "ACK_OK", retcode=10009, executed_volume=0.5)
    seeded.mark_pair_closed(pair_id, close_source="MASTER")
    seeded.set_master_position_status(MASTER_POSITION_ID, "CLOSED", current_volume=0.0)
    seeded.mark_event_processed("EVT-M-2", "DONE", pair_id=pair_id)

    closed = seeded.get_pair(pair_id)
    assert closed["status"] == "CLOSED"
    assert closed["close_source"] == "MASTER"
    assert closed["master_current_volume"] == 0
    assert closed["client_current_volume"] == 0
    assert seeded.get_master_position(MASTER_POSITION_ID)["status"] == "CLOSED"
    assert seeded.list_inflight_commands(pair_id) == []
    assert seeded.list_pairs_needing_attention() == []


# ---------------------------------------------------------------------------------------------
# Các bảng phụ trợ
# ---------------------------------------------------------------------------------------------


def test_replace_symbol_specs_ghi_de_khong_merge(seeded: Database) -> None:
    seeded.replace_symbol_specs(CLIENT_AGENT, [
        {"symbol": "XAUUSDm", "volume_min": 0.01, "volume_step": 0.01, "volume_max": 50.0},
        {"symbol": "EURUSDm", "volume_min": 0.01, "volume_step": 0.01, "volume_max": 100.0},
    ])
    assert seeded.get_symbol_spec(CLIENT_AGENT, "EURUSDm") is not None

    seeded.replace_symbol_specs(CLIENT_AGENT, [
        {"symbol": "XAUUSDm", "volume_min": 0.10, "volume_step": 0.10, "volume_max": 50.0},
    ])
    assert seeded.get_symbol_spec(CLIENT_AGENT, "EURUSDm") is None, "Spec cũ phải biến mất"
    assert seeded.get_symbol_spec(CLIENT_AGENT, "XAUUSDm")["volume_min"] == 0.10


def test_symbol_map_unique_theo_client_va_master_symbol(seeded: Database) -> None:
    seeded.upsert_symbol_map(CLIENT_ID, "XAUUSD", "XAUUSDm")
    seeded.upsert_symbol_map(CLIENT_ID, "XAUUSD", "XAUUSDn")
    rows = seeded.query_all("SELECT * FROM symbol_map")
    assert len(rows) == 1
    assert rows[0]["client_symbol"] == "XAUUSDn"


def test_symbol_map_ke_thua_bang_null(seeded: Database) -> None:
    seeded.upsert_symbol_map(CLIENT_ID, "XAUUSD", "XAUUSDm")
    row = seeded.find_symbol_map(CLIENT_ID, "XAUUSD")
    assert row["copy_mode"] is None, "NULL nghĩa là kế thừa từ client_account"
    assert row["volume_multiplier"] is None
    assert row["verified_at"] is None, "Chưa kiểm tra với sàn"


def test_xoa_client_thi_symbol_map_bi_xoa_theo(seeded: Database) -> None:
    seeded.upsert_symbol_map(CLIENT_ID, "XAUUSD", "XAUUSDm")
    with seeded.transaction() as conn:
        conn.execute("DELETE FROM client_account WHERE client_id = ?", (CLIENT_ID,))
    assert seeded.query_all("SELECT * FROM symbol_map") == []


def test_alert_va_acknowledge(seeded: Database) -> None:
    alert_id = seeded.create_alert("ERROR", "MAT_HEDGE", "Master con 1.00 lot XAUUSD")
    assert len(seeded.list_open_alerts()) == 1
    assert len(seeded.list_open_alerts("ERROR")) == 1
    assert len(seeded.list_open_alerts("CRITICAL")) == 0

    seeded.acknowledge_alert(alert_id)
    assert seeded.list_open_alerts() == []


def test_client_account_mac_dinh_dung_quyet_dinh(seeded: Database) -> None:
    row = seeded.get_client_account(CLIENT_ID)
    assert row["can_close_master"] == 0, "D-20: mặc định TẮT"
    assert row["rounding_mode"] == "DOWN", "D-18: mặc định làm tròn xuống"
    assert row["below_min_policy"] == "SKIP", "D-18: dưới tối thiểu thì bỏ qua"
    assert row["copy_mode"] == "OPPOSITE"
    assert row["open_fail_policy"] == "RETRY"
    assert row["max_event_age_ms"] == 5000


def test_get_config_int_gia_tri_hong_thi_dung_mac_dinh(db: Database,
                                                       caplog_bridge) -> None:
    db.set_config("event_retention_days", "ba muoi")
    assert db.get_config_int("event_retention_days", 30) == 30
    assert any("không phải số" in r.getMessage() for r in caplog_bridge.records)


def test_event_lap_khong_dot_mat_pair_id(seeded: Database) -> None:
    """Event lặp phải bị chặn TRƯỚC khi cấp số, để dãy Pair ID không bị thủng lỗ."""
    first = seeded.create_pending_pair(MASTER_POSITION_ID, CLIENT_ID, "OPPOSITE", 1.0, 0.5)
    assert seeded.create_pending_pair(MASTER_POSITION_ID, CLIENT_ID, "OPPOSITE", 1.0, 0.5) is None

    seeded.upsert_master_position(
        MASTER_POSITION_ID + 1, agent_id=MASTER_AGENT, symbol="EURUSD", direction="SELL",
        initial_volume=1.0, current_volume=1.0, status="OPEN",
    )
    second = seeded.create_pending_pair(MASTER_POSITION_ID + 1, CLIENT_ID, "SAME", 1.0, 0.5)

    assert int(first.rsplit("-", 1)[1]) + 1 == int(second.rsplit("-", 1)[1])
