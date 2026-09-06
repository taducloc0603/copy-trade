"""Dọn dẹp dữ liệu nóng (D-17).

Giữ `event` và `command` trong SQLite nóng đúng `event_retention_days` ngày. Cũ hơn thì
**xuất sang `data/archive/YYYY-MM.db` trước, rồi mới xoá**.

Hai luật cứng của file này:

* Chỉ xoá bản ghi đã kết thúc: `event` có `process_status IN ('DONE','IGNORED')` và `command`
  có `status IN ('ACK_OK','CANCELLED')`. **Không bao giờ xoá bản ghi còn đang treo** — một
  event `PENDING` quá hạn 30 ngày là dấu hiệu hỏng hóc, xoá nó đi là xoá mất bằng chứng.
* **Không bao giờ xoá `pair` hoặc `master_position` theo thời gian.** Một vị thế có thể mở
  nhiều tháng; mất sổ sách của nó là mất khả năng đối chiếu.

Vì DB nóng chạy WAL, SQLite không cam kết giao dịch nguyên tử xuyên qua nhiều database. Nên
thứ tự là: chép sang archive (giao dịch 1) → xoá khỏi DB nóng (giao dịch 2). Gián đoạn giữa
hai bước thì tệ nhất là dữ liệu nằm ở cả hai nơi, và lần chạy sau `INSERT OR IGNORE` sẽ bỏ qua
bản trùng. Làm ngược lại thì gián đoạn là mất dữ liệu.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from bridge.clock import iso_days_ago
from bridge.db.repo import Database
from bridge.logging_setup import get_logger

log = get_logger(__name__)

ARCHIVE_SCHEMA_PATH = Path(__file__).resolve().parent / "archive_schema.sql"

DEFAULT_RETENTION_DAYS = 30
ARCHIVE_DIR_NAME = "archive"

#: Chỉ những trạng thái này mới được phép rời khỏi DB nóng.
DELETABLE_EVENT_STATUSES: tuple[str, ...] = ("DONE", "IGNORED")
DELETABLE_COMMAND_STATUSES: tuple[str, ...] = ("ACK_OK", "CANCELLED")

EVENT_COLUMNS = (
    "id", "event_id", "agent_id", "seq", "type", "position_id", "pair_id",
    "caused_by_command_id", "deal_entry", "volume_delta", "volume_after", "price",
    "payload_json", "ts_agent", "received_at", "processed_at", "process_status", "process_error",
)
COMMAND_COLUMNS = (
    "command_id", "target_agent_id", "pair_id", "type", "payload_json", "status", "attempt",
    "retcode", "retmsg", "executed_volume", "result_position_id", "deadline_at", "sent_at",
    "acked_at", "created_at", "updated_at",
)


@dataclass
class RetentionReport:
    """Kết quả một lần dọn dẹp. Ghi vào log để vận hành đối chiếu được."""

    cutoff: str
    archived_events: int = 0
    archived_commands: int = 0
    deleted_events: int = 0
    deleted_commands: int = 0
    archive_files: list[Path] = field(default_factory=list)

    @property
    def total_deleted(self) -> int:
        return self.deleted_events + self.deleted_commands


def archive_dir_for(db: Database) -> Path:
    """Thư mục archive nằm cạnh file database nóng."""
    return db.path.parent / ARCHIVE_DIR_NAME


def _months(db: Database, table: str, time_column: str, statuses: tuple[str, ...],
            cutoff: str) -> list[str]:
    """Các tháng ``YYYY-MM`` có bản ghi quá hạn và được phép xoá."""
    holders = ", ".join("?" for _ in statuses)
    status_column = "process_status" if table == "event" else "status"
    rows = db.query_all(
        f"SELECT DISTINCT substr({time_column}, 1, 7) AS month FROM {table} "
        f"WHERE {time_column} < ? AND {status_column} IN ({holders}) ORDER BY month",
        (cutoff, *statuses),
    )
    return [row["month"] for row in rows]


def _ensure_archive(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(ARCHIVE_SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def _copy_and_delete(db: Database, archive_path: Path, month: str, cutoff: str,
                     report: RetentionReport) -> None:
    """Chép rồi xoá dữ liệu của đúng một tháng. ATTACH không chạy được trong giao dịch."""
    _ensure_archive(archive_path)
    db.conn.execute("ATTACH DATABASE ? AS arch", (str(archive_path),))
    try:
        event_cols = ", ".join(EVENT_COLUMNS)
        command_cols = ", ".join(COMMAND_COLUMNS)
        event_statuses = ", ".join("?" for _ in DELETABLE_EVENT_STATUSES)
        command_statuses = ", ".join("?" for _ in DELETABLE_COMMAND_STATUSES)

        event_where = (
            f"substr(received_at, 1, 7) = ? AND received_at < ? "
            f"AND process_status IN ({event_statuses})"
        )
        command_where = (
            f"substr(created_at, 1, 7) = ? AND created_at < ? "
            f"AND status IN ({command_statuses})"
        )
        event_params = (month, cutoff, *DELETABLE_EVENT_STATUSES)
        command_params = (month, cutoff, *DELETABLE_COMMAND_STATUSES)

        # Giao dịch 1: chép sang archive.
        with db.transaction() as conn:
            cur = conn.execute(
                f"INSERT OR IGNORE INTO arch.event ({event_cols}) "
                f"SELECT {event_cols} FROM main.event WHERE {event_where}",
                event_params,
            )
            report.archived_events += cur.rowcount
            cur = conn.execute(
                f"INSERT OR IGNORE INTO arch.command ({command_cols}) "
                f"SELECT {command_cols} FROM main.command WHERE {command_where}",
                command_params,
            )
            report.archived_commands += cur.rowcount

        # Giao dịch 2: chỉ xoá những dòng đã chắc chắn có mặt trong archive.
        with db.transaction() as conn:
            cur = conn.execute(
                f"DELETE FROM main.event WHERE {event_where} "
                f"AND event_id IN (SELECT event_id FROM arch.event)",
                event_params,
            )
            report.deleted_events += cur.rowcount
            cur = conn.execute(
                f"DELETE FROM main.command WHERE {command_where} "
                f"AND command_id IN (SELECT command_id FROM arch.command)",
                command_params,
            )
            report.deleted_commands += cur.rowcount
    finally:
        db.conn.execute("DETACH DATABASE arch")

    report.archive_files.append(archive_path)


def run_retention(db: Database, *, retention_days: int | None = None,
                  archive_dir: Path | None = None,
                  now: datetime | None = None) -> RetentionReport:
    """Chạy một lượt dọn dẹp. Trả về báo cáo số bản ghi đã xử lý.

    `retention_days` mặc định lấy từ `system_config.event_retention_days`.
    Chạy khi không có gì quá hạn thì không tạo file archive nào.
    """
    days = retention_days if retention_days is not None else db.get_config_int(
        "event_retention_days", DEFAULT_RETENTION_DAYS
    )
    cutoff = iso_days_ago(days, now)
    report = RetentionReport(cutoff=cutoff)
    directory = archive_dir if archive_dir is not None else archive_dir_for(db)

    months = sorted(
        set(_months(db, "event", "received_at", DELETABLE_EVENT_STATUSES, cutoff))
        | set(_months(db, "command", "created_at", DELETABLE_COMMAND_STATUSES, cutoff))
    )
    if not months:
        log.info("Retention: khong co ban ghi nao cu hon %d ngay (moc %s)", days, cutoff)
        return report

    for month in months:
        _copy_and_delete(db, directory / f"{month}.db", month, cutoff, report)

    log.info(
        "Retention: luu tru %d event va %d command, xoa %d event va %d command, moc %s",
        report.archived_events, report.archived_commands,
        report.deleted_events, report.deleted_commands, cutoff,
    )
    return report
