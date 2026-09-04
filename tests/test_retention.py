"""Test dọn dẹp dữ liệu nóng (D-17).

Trọng tâm không phải "xoá được không" mà là **xoá đúng cái được phép xoá**: bản ghi còn treo
và sổ sách vị thế phải sống sót qua mọi lần dọn dẹp.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bridge.db.repo import Database
from bridge.db.retention import archive_dir_for, run_retention
from tests.conftest import CLIENT_AGENT, CLIENT_ID, MASTER_AGENT, MASTER_POSITION_ID

CU = "2025-01-15T10:00:00.000Z"          # quá hạn
CU_THANG_KHAC = "2025-02-20T10:00:00.000Z"  # quá hạn, tháng khác
MOI = "2026-09-01T10:00:00.000Z"         # còn hạn


def _them_event(db: Database, event_id: str, seq: int, received_at: str,
                process_status: str = "DONE") -> None:
    db.record_event(event_id, MASTER_AGENT, seq, "position_opened")
    with db.transaction() as conn:
        conn.execute(
            "UPDATE event SET received_at = ?, process_status = ? WHERE event_id = ?",
            (received_at, process_status, event_id),
        )


def _them_command(db: Database, command_id: str, created_at: str,
                  status: str = "ACK_OK") -> None:
    db.create_command(command_id, CLIENT_AGENT, "OPEN")
    with db.transaction() as conn:
        conn.execute(
            "UPDATE command SET created_at = ?, status = ? WHERE command_id = ?",
            (created_at, status, command_id),
        )


def _doc_archive(path: Path, table: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        conn.close()


def test_event_cu_vao_archive_va_bien_mat_khoi_db_nong(seeded: Database) -> None:
    _them_event(seeded, "EVT-CU", 1, CU)
    _them_event(seeded, "EVT-MOI", 2, MOI)

    report = run_retention(seeded, retention_days=30)

    assert report.archived_events == 1
    assert report.deleted_events == 1
    assert seeded.get_event("EVT-CU") is None, "Event cũ vẫn còn trong DB nóng"
    assert seeded.get_event("EVT-MOI") is not None, "Event mới bị xoá nhầm"

    archive = archive_dir_for(seeded) / "2025-01.db"
    assert archive.is_file()
    rows = _doc_archive(archive, "event")
    assert [r["event_id"] for r in rows] == ["EVT-CU"]
    assert rows[0]["seq"] == 1


def test_khong_bao_gio_xoa_event_con_treo(seeded: Database) -> None:
    """Event PENDING quá hạn 30 ngày là dấu hiệu hỏng hóc — xoá đi là xoá mất bằng chứng."""
    _them_event(seeded, "EVT-TREO", 1, CU, process_status="PENDING")
    _them_event(seeded, "EVT-LOI", 2, CU, process_status="ERROR")
    _them_event(seeded, "EVT-XONG", 3, CU, process_status="DONE")

    report = run_retention(seeded, retention_days=30)

    assert report.deleted_events == 1
    assert seeded.get_event("EVT-TREO") is not None
    assert seeded.get_event("EVT-LOI") is not None
    assert seeded.get_event("EVT-XONG") is None


def test_khong_bao_gio_xoa_command_con_treo(seeded: Database) -> None:
    _them_command(seeded, "CMD-CHO", CU, status="PENDING")
    _them_command(seeded, "CMD-DA-GUI", CU, status="SENT")
    _them_command(seeded, "CMD-TIMEOUT", CU, status="TIMEOUT")
    _them_command(seeded, "CMD-HONG", CU, status="ACK_FAILED")
    _them_command(seeded, "CMD-XONG", CU, status="ACK_OK")
    _them_command(seeded, "CMD-HUY", CU, status="CANCELLED")

    report = run_retention(seeded, retention_days=30)

    assert report.deleted_commands == 2
    for still_here in ("CMD-CHO", "CMD-DA-GUI", "CMD-TIMEOUT", "CMD-HONG"):
        assert seeded.get_command(still_here) is not None, f"{still_here} bị xoá nhầm"
    assert seeded.get_command("CMD-XONG") is None
    assert seeded.get_command("CMD-HUY") is None


def test_pair_va_master_position_khong_bao_gio_bi_dong_toi(seeded: Database) -> None:
    """D-17: không bao giờ xoá `pair` và `master_position` theo thời gian."""
    pair_id = seeded.create_pending_pair(MASTER_POSITION_ID, CLIENT_ID, "OPPOSITE", 1.0, 0.5)
    with seeded.transaction() as conn:
        conn.execute("UPDATE pair SET created_at = ?, status = 'CLOSED'", (CU,))
        conn.execute("UPDATE master_position SET created_at = ?, status = 'CLOSED'", (CU,))
    _them_event(seeded, "EVT-CU", 1, CU)

    run_retention(seeded, retention_days=30)

    assert seeded.get_pair(pair_id) is not None
    assert seeded.get_master_position(MASTER_POSITION_ID) is not None


def test_tach_archive_theo_thang(seeded: Database) -> None:
    _them_event(seeded, "EVT-T1", 1, CU)
    _them_event(seeded, "EVT-T2", 2, CU_THANG_KHAC)

    report = run_retention(seeded, retention_days=30)

    assert report.deleted_events == 2
    assert sorted(p.name for p in report.archive_files) == ["2025-01.db", "2025-02.db"]
    assert [r["event_id"] for r in _doc_archive(archive_dir_for(seeded) / "2025-01.db",
                                                "event")] == ["EVT-T1"]
    assert [r["event_id"] for r in _doc_archive(archive_dir_for(seeded) / "2025-02.db",
                                                "event")] == ["EVT-T2"]


def test_khong_co_gi_qua_han_thi_khong_tao_file_archive(seeded: Database) -> None:
    _them_event(seeded, "EVT-MOI", 1, MOI)
    report = run_retention(seeded, retention_days=30)

    assert report.total_deleted == 0
    assert report.archive_files == []
    assert not archive_dir_for(seeded).exists()


def test_chay_lai_retention_khong_sinh_ban_ghi_trung(seeded: Database) -> None:
    """Chép và xoá là hai giao dịch tách rời — chạy lại phải an toàn."""
    _them_event(seeded, "EVT-CU", 1, CU)
    run_retention(seeded, retention_days=30)

    _them_event(seeded, "EVT-CU-2", 2, CU)
    run_retention(seeded, retention_days=30)

    rows = _doc_archive(archive_dir_for(seeded) / "2025-01.db", "event")
    assert sorted(r["event_id"] for r in rows) == ["EVT-CU", "EVT-CU-2"]
    assert len(rows) == 2


def test_retention_days_lay_tu_system_config(seeded: Database) -> None:
    _them_event(seeded, "EVT-CU", 1, CU)
    seeded.set_config("event_retention_days", "100000")

    report = run_retention(seeded)

    assert report.deleted_events == 0, "Phải tôn trọng event_retention_days trong system_config"
    assert seeded.get_event("EVT-CU") is not None


def test_command_giu_du_truong_khi_vao_archive(seeded: Database) -> None:
    pair_id = seeded.create_pending_pair(MASTER_POSITION_ID, CLIENT_ID, "OPPOSITE", 1.0, 0.5)
    seeded.create_command("CMD-1", CLIENT_AGENT, "CLOSE_PARTIAL", pair_id=pair_id,
                          payload_json='{"volume": 0.25}')
    seeded.mark_command_acked("CMD-1", "ACK_OK", retcode=10009, executed_volume=0.25,
                              result_position_id=4242)
    with seeded.transaction() as conn:
        conn.execute("UPDATE command SET created_at = ? WHERE command_id = 'CMD-1'", (CU,))

    run_retention(seeded, retention_days=30)

    rows = _doc_archive(archive_dir_for(seeded) / "2025-01.db", "command")
    assert len(rows) == 1
    assert rows[0]["type"] == "CLOSE_PARTIAL"
    assert rows[0]["pair_id"] == pair_id
    assert rows[0]["retcode"] == 10009
    assert rows[0]["executed_volume"] == 0.25
    assert rows[0]["payload_json"] == '{"volume": 0.25}'
