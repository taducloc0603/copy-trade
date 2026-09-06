"""Test schema và các ràng buộc.

Đây là những test quan trọng nhất của cả dự án. Logic ứng dụng có thể sai, ràng buộc DB thì
không — nhưng chỉ khi ràng buộc thật sự được bật và thật sự chặn.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bridge.db.migrations import (
    SCHEMA_VERSION,
    MigrationError,
    apply_migrations,
    current_version,
    discover_migrations,
    split_statements,
)
from bridge.db.repo import Database
from tests.conftest import CLIENT_ID, MASTER_POSITION_ID

# ---------------------------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------------------------


def test_migration_chay_hai_lan_khong_loi(db_path: Path) -> None:
    """Chạy lại không được làm gì thêm và không được lỗi.

    So với **version mới nhất tìm được**, không phải một con số cứng: thêm migration mới là
    chuyện bình thường, và một test về cơ chế không nên vỡ mỗi lần đó xảy ra.
    """
    moi_nhat = max(m.version for m in discover_migrations())
    first = Database(db_path)
    assert current_version(first.conn) == moi_nhat
    assert apply_migrations(first.conn) == moi_nhat
    assert apply_migrations(first.conn) == moi_nhat
    rows = first.query_all("SELECT version FROM schema_version ORDER BY version")
    da_ghi = [r["version"] for r in rows]
    assert da_ghi == list(range(SCHEMA_VERSION, moi_nhat + 1)), "Version bi ghi lap hoac thieu"
    first.close()

    # Mở lại từ đầu trên đúng file đó cũng không được chạy lại migration.
    second = Database(db_path)
    assert current_version(second.conn) == moi_nhat
    second.close()


def test_database_trong_co_version_0(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "trong.db"))
    assert current_version(conn) == 0
    conn.close()


def test_discover_migrations_co_schema_goc(tmp_path: Path) -> None:
    found = discover_migrations(tmp_path)
    assert len(found) == 1
    assert found[0].version == SCHEMA_VERSION
    assert found[0].path.name == "schema.sql"


def test_migration_ten_sai_dinh_dang_bi_tu_choi(tmp_path: Path) -> None:
    (tmp_path / "them-cot.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError):
        discover_migrations(tmp_path)


def test_migration_dung_lai_version_cua_schema_goc_bi_tu_choi(tmp_path: Path) -> None:
    (tmp_path / "001_lap_lai.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError):
        discover_migrations(tmp_path)


def test_split_statements_khong_bi_nham_dau_cham_phay_trong_chuoi() -> None:
    sql = "INSERT INTO t (a) VALUES ('co; dau cham phay');\nSELECT 1;\n"
    assert split_statements(sql) == [
        "INSERT INTO t (a) VALUES ('co; dau cham phay');",
        "SELECT 1;",
    ]


def test_split_statements_bao_loi_khi_sql_do_dang() -> None:
    with pytest.raises(MigrationError):
        split_statements("CREATE TABLE t (")


def test_migration_hong_thi_rollback_ca_cum(tmp_path: Path, db_path: Path) -> None:
    """Migration lỗi giữa chừng không được để lại nửa bảng."""
    # Version phải cao hơn mọi migration thật, nếu không nó bị coi là "đã chạy rồi" và bỏ qua.
    (tmp_path / "999_hong.sql").write_text(
        "CREATE TABLE tam (a INTEGER);\nCAU LENH SAI CU PHAP;\n", encoding="utf-8"
    )
    database = Database(db_path)
    truoc = current_version(database.conn)
    with pytest.raises(MigrationError):
        apply_migrations(database.conn, tmp_path)
    exists = database.query_one("SELECT name FROM sqlite_master WHERE name = 'tam'")
    assert exists is None, "Bảng của migration hỏng vẫn còn — giao dịch không được rollback"
    assert current_version(database.conn) == truoc
    database.close()


# ---------------------------------------------------------------------------------------------
# Pragma
# ---------------------------------------------------------------------------------------------


def test_foreign_keys_that_su_duoc_bat(db: Database) -> None:
    """SQLite tắt foreign_keys mặc định ở mỗi kết nối — rất dễ quên."""
    assert db.query_one("PRAGMA foreign_keys")[0] == 1


def test_journal_mode_wal_va_synchronous_full(db: Database) -> None:
    assert db.query_one("PRAGMA journal_mode")[0].lower() == "wal"
    assert db.query_one("PRAGMA synchronous")[0] == 2  # 2 = FULL


def test_khoa_ngoai_that_su_chan(db: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO client_account (client_id, agent_id, created_at, updated_at) "
            "VALUES ('CL-MA', 'AGENT-KHONG-TON-TAI', '2026-01-01T00:00:00.000Z', "
            "'2026-01-01T00:00:00.000Z')"
        )


# ---------------------------------------------------------------------------------------------
# Hai ràng buộc quan trọng nhất của bảng pair
# ---------------------------------------------------------------------------------------------


def _insert_pair(db: Database, pair_id: str, **overrides: object) -> None:
    columns = {
        "pair_id": pair_id,
        "master_position_id": MASTER_POSITION_ID,
        "client_id": CLIENT_ID,
        "copy_mode": "OPPOSITE",
        "master_initial_volume": 1.0,
        "master_current_volume": 1.0,
        "effective_multiplier": 0.5,
        "status": "PENDING_OPEN",
        "created_at": "2026-01-01T00:00:00.000Z",
        "updated_at": "2026-01-01T00:00:00.000Z",
        **overrides,
    }
    names = ", ".join(columns)
    holders = ", ".join("?" for _ in columns)
    with db.transaction() as conn:
        conn.execute(f"INSERT INTO pair ({names}) VALUES ({holders})", tuple(columns.values()))


def test_hai_pair_cung_master_position_va_client_bi_chan(seeded: Database) -> None:
    _insert_pair(seeded, "PAIR-20260101-000001")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pair(seeded, "PAIR-20260101-000002")


def test_hai_pair_cung_client_position_bi_chan(seeded: Database) -> None:
    seeded.upsert_master_position(
        MASTER_POSITION_ID + 1, agent_id="AG-MASTER", symbol="XAUUSD", direction="BUY",
        initial_volume=1.0, current_volume=1.0, status="OPEN",
    )
    _insert_pair(seeded, "PAIR-20260101-000001", client_position_id=4242)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pair(
            seeded, "PAIR-20260101-000002",
            master_position_id=MASTER_POSITION_ID + 1, client_position_id=4242,
        )


def test_nhieu_pair_cung_client_voi_client_position_id_null_van_duoc(seeded: Database) -> None:
    """Hai cặp đang chờ mở thì chưa có position id — index một phần phải cho phép."""
    seeded.upsert_master_position(
        MASTER_POSITION_ID + 1, agent_id="AG-MASTER", symbol="EURUSD", direction="SELL",
        initial_volume=1.0, current_volume=1.0, status="OPEN",
    )
    _insert_pair(seeded, "PAIR-20260101-000001", client_position_id=None)
    _insert_pair(
        seeded, "PAIR-20260101-000002",
        master_position_id=MASTER_POSITION_ID + 1, client_position_id=None,
    )
    assert len(seeded.query_all("SELECT * FROM pair")) == 2


# ---------------------------------------------------------------------------------------------
# CHECK trên enum và giá trị số
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("status", "BANANA"),
        ("status", "open"),
        ("copy_mode", "NGUOC"),
        ("client_direction", "LONG"),
        ("orphan_side", "BOTH"),
        ("close_source", "AI_DO"),
    ],
)
def test_enum_sai_tren_pair_bi_chan(seeded: Database, column: str, value: str) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pair(seeded, "PAIR-20260101-000009", **{column: value})


def test_effective_multiplier_khong_duong_bi_chan(seeded: Database) -> None:
    for bad in (0, -1, -0.5):
        with pytest.raises(sqlite3.IntegrityError):
            _insert_pair(seeded, f"PAIR-20260101-00001{bad}", effective_multiplier=bad)


def test_pair_khong_co_effective_multiplier_bi_chan(seeded: Database) -> None:
    """D-19: không cặp nào được tồn tại mà chưa khoá tỷ lệ."""
    with pytest.raises(sqlite3.IntegrityError):
        _insert_pair(seeded, "PAIR-20260101-000011", effective_multiplier=None)


@pytest.mark.parametrize("bad", [0, -1, -0.001])
def test_volume_multiplier_khong_duong_bi_chan(seeded: Database, bad: float) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        seeded.upsert_client_account("CL-XX", agent_id="AG-CLIENT", volume_multiplier=bad)


@pytest.mark.parametrize(
    ("table", "column", "value"),
    [
        ("agent", "role", "BOSS"),
        ("agent", "status", "BUSY"),
        ("client_account", "rounding_mode", "UP"),
        ("client_account", "below_min_policy", "FORCE"),
        ("client_account", "open_fail_policy", "IGNORE"),
        ("master_position", "direction", "LONG"),
        ("master_position", "status", "HALF"),
        ("event", "process_status", "MAYBE"),
        ("event", "type", "position_exploded"),
        ("event", "deal_entry", "SIDEWAYS"),
        ("command", "type", "MODIFY"),
        ("command", "status", "MAYBE"),
        ("alert", "level", "DEBUG"),
        ("reconcile_finding", "severity", "MEDIUM"),
        ("reconcile_finding", "resolution", "MAYBE"),
    ],
)
def test_enum_sai_bi_chan_tren_moi_bang(seeded: Database, table: str, column: str,
                                        value: str) -> None:
    rows = {
        "agent": {"agent_id": "AG-X", "role": "CLIENT", "token_hash": "h", "magic_number": 1,
                  "created_at": "t", "updated_at": "t"},
        "client_account": {"client_id": "CL-X", "agent_id": "AG-CLIENT",
                           "created_at": "t", "updated_at": "t"},
        "master_position": {"master_position_id": 999999, "agent_id": "AG-MASTER",
                            "symbol": "X", "direction": "BUY", "initial_volume": 1.0,
                            "current_volume": 1.0, "status": "OPEN",
                            "created_at": "t", "updated_at": "t"},
        "event": {"event_id": "EVT-X", "agent_id": "AG-MASTER", "seq": 1, "type": "position_opened",
                  "received_at": "t"},
        "command": {"command_id": "CMD-X", "target_agent_id": "AG-CLIENT", "type": "OPEN",
                    "created_at": "t", "updated_at": "t"},
        "alert": {"level": "INFO", "code": "C", "message": "m", "created_at": "t"},
        "reconcile_finding": {"run_id": "R", "severity": "SAFE", "kind": "K",
                              "created_at": "t"},
    }[table]
    rows = {**rows, column: value}
    names = ", ".join(rows)
    holders = ", ".join("?" for _ in rows)
    with pytest.raises(sqlite3.IntegrityError), seeded.transaction() as conn:
        conn.execute(f"INSERT INTO {table} ({names}) VALUES ({holders})", tuple(rows.values()))


# ---------------------------------------------------------------------------------------------
# system_config
# ---------------------------------------------------------------------------------------------


def test_system_config_khoi_tao_dung_gia_tri(db: Database) -> None:
    assert db.get_config("run_mode") == "PAUSED", "D-15: phải khởi động ở PAUSED"
    assert db.get_config("cascade_wait_master_ms") == "15000"
    assert db.get_config("cascade_on_partial_close") == "0"
    assert db.get_config("closeby_remainder_action") == "ALERT"
    assert db.get_config("offline_reopen_policy") == "NONE"
    assert db.get_config("max_reopen_slippage_points") == "0"
    assert db.get_config("event_retention_days") == "30"
    assert db.get_config("heartbeat_interval_ms") == "1000"
    assert db.get_config("heartbeat_timeout_ms") == "5000"
    assert db.get_config("reconcile_interval_sec") == "60"


def test_chay_lai_migration_khong_ghi_de_config_da_sua(db_path: Path) -> None:
    first = Database(db_path)
    first.set_config("run_mode", "RUNNING")
    first.close()

    second = Database(db_path)
    assert second.get_config("run_mode") == "RUNNING", "INSERT OR IGNORE phải giữ giá trị cũ"
    second.close()
