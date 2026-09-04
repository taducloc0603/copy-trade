"""Tầng dữ liệu: schema, migration, repository, dọn dẹp.

Không dùng ORM. SQL viết trực tiếp — schema nhỏ và các ràng buộc là phần quan trọng nhất.
"""

from bridge.db.migrations import apply_migrations, current_version
from bridge.db.repo import Database, RepoError

__all__ = ["Database", "RepoError", "apply_migrations", "current_version"]
