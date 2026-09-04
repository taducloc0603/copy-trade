"""Thiết lập logging cho Bridge.

Bốn mức dùng trong dự án: INFO, WARNING, ERROR, CRITICAL. DEBUG chỉ dùng khi gỡ lỗi tại chỗ.

Hai yêu cầu bắt buộc:

1. Mọi log liên quan tới một cặp lệnh phải mang ``pair_id``; liên quan tới một sự kiện phải
   mang ``event_id``. Truyền qua ``extra={}``, formatter tự chèn khi có::

       log.info("Đã tạo cặp", extra={"pair_id": "PAIR-20260904-000001"})
       # 2026-09-04T10:12:33.481+0700 | INFO     | bridge.engine | [pair_id=PAIR-...] Đã tạo cặp

2. **Không log token, không log mật khẩu.** ``RedactingFilter`` che giá trị của các trường nhạy
   cảm trong ``extra`` và che các cặp ``token=...`` lọt vào nội dung message. Đây là lưới an toàn
   cuối cùng, không phải lý do để viết code log token.
"""

from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

#: Các trường ngữ cảnh được formatter tự chèn vào dòng log khi có mặt trong ``extra``.
CONTEXT_FIELDS: tuple[str, ...] = ("pair_id", "event_id", "command_id", "agent_id")

#: Tên trường bị coi là nhạy cảm, giá trị không bao giờ được ghi ra log.
SENSITIVE_FIELDS: frozenset[str] = frozenset({"token", "password", "passwd", "secret", "api_key"})

REDACTED = "***"

#: Bắt các cặp `token=abc`, `password: "abc"`, `secret = abc` lọt vào nội dung message.
_SENSITIVE_PATTERN = re.compile(
    r"(?i)\b(token|password|passwd|secret|api_key)\b(\s*[=:]\s*)([\"']?)([^\s,;\"']+)\3"
)

DEFAULT_LOG_DIR = Path("logs")
DEFAULT_LOG_FILENAME = "bridge.log"
DEFAULT_BACKUP_DAYS = 30


class RedactingFilter(logging.Filter):
    """Che token và mật khẩu trước khi log chạm tới bất kỳ handler nào."""

    def filter(self, record: logging.LogRecord) -> bool:
        for field in SENSITIVE_FIELDS:
            if hasattr(record, field):
                setattr(record, field, REDACTED)
        if isinstance(record.msg, str) and _SENSITIVE_PATTERN.search(record.msg):
            record.msg = _SENSITIVE_PATTERN.sub(rf"\1\2\3{REDACTED}\3", record.msg)
        return True


class ContextFormatter(logging.Formatter):
    """Formatter chèn timestamp ISO 8601 có mili giây và các trường ngữ cảnh."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        # ISO 8601 kèm mili giây và offset múi giờ, ví dụ 2026-09-04T10:12:33.481+0700.
        dt = datetime.fromtimestamp(record.created).astimezone()
        return f"{dt:%Y-%m-%dT%H:%M:%S}.{int(record.msecs):03d}{dt:%z}"

    def format(self, record: logging.LogRecord) -> str:
        parts = []
        for field in CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                parts.append(f"{field}={value}")
        record.context = f"[{' '.join(parts)}] " if parts else ""
        return super().format(record)


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(context)s%(message)s"


def _build_formatter() -> ContextFormatter:
    return ContextFormatter(LOG_FORMAT)


def setup_logging(
    level: int | str = logging.INFO,
    log_dir: Path | str = DEFAULT_LOG_DIR,
    filename: str = DEFAULT_LOG_FILENAME,
    backup_days: int = DEFAULT_BACKUP_DAYS,
    to_console: bool = True,
) -> logging.Logger:
    """Cấu hình logger gốc: ghi đồng thời ra console và file xoay vòng theo ngày.

    Gọi lại nhiều lần là an toàn — các handler cũ do hàm này tạo sẽ bị gỡ trước.
    Trả về logger gốc.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, "_copybridge", False):
            root.removeHandler(handler)
            handler.close()

    formatter = _build_formatter()
    redactor = RedactingFilter()

    file_handler = TimedRotatingFileHandler(
        log_dir / filename, when="midnight", backupCount=backup_days, encoding="utf-8", utc=False
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)
    file_handler._copybridge = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    if to_console:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        console.addFilter(redactor)
        console._copybridge = True  # type: ignore[attr-defined]
        root.addHandler(console)

    return root


def get_logger(name: str) -> logging.Logger:
    """Lấy logger theo tên module. Dùng ``get_logger(__name__)`` ở mọi module."""
    return logging.getLogger(name)
