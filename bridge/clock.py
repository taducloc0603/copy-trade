"""Đồng hồ dùng chung.

Mọi timestamp lưu vào DB đều là **UTC, ISO 8601, có mili giây, hậu tố `Z`**:
``2026-09-04T09:41:42.086Z``.

Chọn UTC là cố ý: Bridge và các agent có thể ở khác múi giờ, và so sánh chuỗi ISO 8601 dạng
UTC cho ra đúng thứ tự thời gian — nên `WHERE received_at < ?` chạy được mà không cần hàm ngày
tháng của SQLite. Định dạng cố định 24 ký tự nên `substr(received_at, 1, 7)` luôn là `YYYY-MM`.

Log thì ngược lại, dùng giờ địa phương có offset (xem `bridge/logging_setup.py`) vì log là để
người đọc.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


def utc_now() -> datetime:
    """Thời điểm hiện tại, luôn kèm tzinfo UTC. Không bao giờ trả về datetime naive."""
    return datetime.now(UTC)


def to_iso(moment: datetime) -> str:
    """Chuyển datetime sang chuỗi ISO 8601 UTC có mili giây.

    Datetime naive được coi là UTC — chấp nhận input lỏng lẻo nhưng output luôn chặt.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    return moment.strftime(ISO_FORMAT)[:-3] + "Z"


def utc_now_iso() -> str:
    """Thời điểm hiện tại dạng chuỗi ISO 8601 UTC. Đây là hàm dùng ở mọi cột `*_at`."""
    return to_iso(utc_now())


def parse_iso(text: str) -> datetime:
    """Đọc lại chuỗi do `to_iso()` sinh ra. Trả về datetime có tzinfo UTC."""
    return datetime.strptime(text, ISO_FORMAT + "Z").replace(tzinfo=UTC)


def iso_days_ago(days: int, now: datetime | None = None) -> str:
    """Mốc thời gian ``days`` ngày trước, dùng làm ngưỡng cắt cho retention."""
    return to_iso((now or utc_now()) - timedelta(days=days))


def day_key(moment: datetime | None = None) -> str:
    """Khoá ngày dạng ``YYYYMMDD`` theo UTC, dùng cho bộ đếm Pair ID."""
    return (moment or utc_now()).astimezone(UTC).strftime("%Y%m%d")
