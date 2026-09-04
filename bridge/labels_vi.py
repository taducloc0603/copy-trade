"""Bảng nhãn tiếng Việt (D-16).

Đây là **nơi duy nhất** trong toàn dự án được chứa chuỗi tiếng Việt hướng tới người dùng.
Enum trong DB, log và message giao thức luôn là tiếng Anh không dấu; việc dịch chỉ xảy ra
ở tầng hiển thị, qua đúng file này.

BUY, SELL và tên symbol giữ nguyên gốc, không dịch.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

PAIR_STATUS = {
    "PENDING_OPEN": "Chờ mở",
    "OPEN": "Đang hedge",
    "PARTIALLY_CLOSED": "Đóng một phần",
    "CLOSING": "Đang đóng",
    "CLOSED": "Đã đóng",
    "OPEN_FAILED": "Mở thất bại",
    "ORPHANED": "Mất hedge",
}
RUN_MODE = {
    "RUNNING": "Đang chạy",
    "PAUSE_NEW_ENTRIES": "Tạm dừng lệnh mới",
    "PAUSED": "Đã dừng",
    "EMERGENCY": "Khẩn cấp",
}
AGENT_STATUS = {"ONLINE": "Kết nối", "OFFLINE": "Mất kết nối", "DEGRADED": "Mất kết nối sàn"}
COPY_MODE = {"SAME": "Cùng chiều", "OPPOSITE": "Khác chiều"}
CLOSE_SOURCE = {"MASTER": "Từ Master", "CLIENT": "Từ Client", "BOT": "Bot đồng bộ",
                "BROKER": "Sàn đóng", "MANUAL": "Thủ công"}
ALERT_LEVEL = {"INFO": "Thông tin", "WARNING": "Cảnh báo",
               "ERROR": "Lỗi", "CRITICAL": "Nghiêm trọng"}
MASTER_POSITION_STATUS = {"OPEN": "Đang mở", "CLOSED": "Đã đóng", "UNPAIRED": "Chưa ghép cặp"}

#: Mọi nhóm nhãn, dùng cho test và cho việc duyệt toàn bộ bảng nhãn.
ALL_GROUPS: dict[str, dict[str, str]] = {
    "PAIR_STATUS": PAIR_STATUS,
    "RUN_MODE": RUN_MODE,
    "AGENT_STATUS": AGENT_STATUS,
    "COPY_MODE": COPY_MODE,
    "CLOSE_SOURCE": CLOSE_SOURCE,
    "ALERT_LEVEL": ALERT_LEVEL,
    "MASTER_POSITION_STATUS": MASTER_POSITION_STATUS,
}


def label(group: dict[str, str], key: str) -> str:
    """Trả về nhãn tiếng Việt của ``key`` trong ``group``.

    Thiếu nhãn thì trả về chính ``key`` và ghi WARNING. Hàm này **không bao giờ ném exception**:
    thiếu một nhãn không đáng làm sập dashboard.
    """
    if key is None:
        _log.warning("label() nhận key None")
        return ""
    text = group.get(key)
    if text is None:
        _log.warning("Thiếu nhãn tiếng Việt cho key %r", key)
        return key
    return text
