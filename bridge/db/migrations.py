"""Migration runner.

Cách đánh số:

* **Version 1** là toàn bộ `bridge/db/schema.sql`. File đó vừa là migration đầu tiên vừa là
  bản mô tả schema chính thức để đọc bằng mắt — giữ một bản duy nhất thay vì chép đôi sang
  `migrations/001_*.sql`, vì hai bản chép tay sẽ lệch nhau sớm muộn.
* **Version 2 trở đi** là các file `bridge/db/migrations/NNN_*.sql`, chạy tuần tự theo số.

Idempotent: chạy hai lần không lỗi. Mỗi migration chạy trong **một giao dịch** và chỉ ghi vào
`schema_version` khi đã chạy xong.

> Không dùng `Cursor.executescript()`: nó phát một `COMMIT` ngầm trước khi chạy, tức là sẽ đóng
> mất giao dịch ta vừa mở và migration hết nguyên tử. Thay vào đó tách SQL thành từng câu lệnh
> bằng `sqlite3.complete_statement` (hàm này hiểu chuỗi và chú thích nên không bị nhầm dấu `;`).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from bridge.clock import utc_now_iso
from bridge.logging_setup import get_logger

log = get_logger(__name__)

DB_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = DB_DIR / "schema.sql"
MIGRATIONS_DIR = DB_DIR / "migrations"
SCHEMA_VERSION = 1

_MIGRATION_NAME = re.compile(r"^(\d{3})_[A-Za-z0-9_]+\.sql$")
_IS_PRAGMA = re.compile(r"^\s*PRAGMA\b", re.IGNORECASE)

SCHEMA_VERSION_DDL = (
    "CREATE TABLE IF NOT EXISTS schema_version ("
    "    version    INTEGER PRIMARY KEY,"
    "    applied_at TEXT    NOT NULL"
    ")"
)


class MigrationError(Exception):
    """Migration hỏng. Bridge không được chạy tiếp trên một schema nửa vời."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    def read_sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def split_statements(sql: str) -> list[str]:
    """Tách một file SQL thành từng câu lệnh hoàn chỉnh.

    Dùng `sqlite3.complete_statement` thay vì `sql.split(";")` vì dấu chấm phẩy có thể nằm
    trong chuỗi hoặc chú thích.
    """
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            text = buffer.strip()
            if text and text != ";":
                statements.append(text)
            buffer = ""
    tail = buffer.strip()
    if tail:
        raise MigrationError(f"SQL kết thúc giữa chừng một câu lệnh: {tail[:120]!r}")
    return statements


def discover_migrations(migrations_dir: Path | None = None) -> list[Migration]:
    """Liệt kê mọi migration theo version tăng dần, bắt đầu bằng schema gốc."""
    directory = migrations_dir if migrations_dir is not None else MIGRATIONS_DIR
    found = [Migration(version=SCHEMA_VERSION, name="initial_schema", path=SCHEMA_PATH)]

    seen: dict[int, Path] = {SCHEMA_VERSION: SCHEMA_PATH}
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if path.suffix != ".sql":
                continue
            match = _MIGRATION_NAME.match(path.name)
            if match is None:
                raise MigrationError(
                    f"Tên migration sai định dạng: {path.name}. Phải là NNN_ten_khong_dau.sql"
                )
            version = int(match.group(1))
            if version <= SCHEMA_VERSION:
                raise MigrationError(
                    f"{path.name} dùng version {version}, nhưng {SCHEMA_VERSION} đã là schema gốc"
                )
            if version in seen:
                raise MigrationError(f"Trùng version {version}: {seen[version].name} và {path.name}")
            seen[version] = path
            found.append(Migration(version=version, name=path.stem, path=path))

    found.sort(key=lambda m: m.version)
    return found


def current_version(conn: sqlite3.Connection) -> int:
    """Version cao nhất đã áp dụng. Trả về 0 khi database còn trống."""
    conn.execute(SCHEMA_VERSION_DDL)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    value = row[0] if row is not None else None
    return int(value) if value is not None else 0


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> int:
    """Chạy mọi migration còn thiếu. Trả về version sau khi chạy xong.

    Gọi lại trên database đã cập nhật thì không làm gì và không lỗi.
    """
    applied_before = current_version(conn)
    version = applied_before

    for migration in discover_migrations(migrations_dir):
        if migration.version <= applied_before:
            continue
        log.info("Áp dụng migration %03d_%s", migration.version, migration.name)

        statements = split_statements(migration.read_sql())
        # PRAGMA không chạy được trong giao dịch (journal_mode chẳng hạn) và dù sao cũng phải
        # áp dụng lại ở mỗi kết nối — `Database` lo việc đó.
        body = [s for s in statements if not _IS_PRAGMA.match(s)]

        try:
            conn.execute("BEGIN IMMEDIATE")
            for statement in body:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (migration.version, utc_now_iso()),
            )
            conn.execute("COMMIT")
        except Exception as exc:
            conn.execute("ROLLBACK")
            raise MigrationError(
                f"Migration {migration.version:03d}_{migration.name} thất bại: {exc}"
            ) from exc
        version = migration.version

    if version == applied_before:
        log.info("Schema đã ở version %d, không có migration nào phải chạy", version)
    return version
