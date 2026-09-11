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

#: Nhóm nhãn **ánh xạ từ enum trong DB**. Key phải là enum tiếng Anh viết hoa, đúng như giá trị
#: được lưu. Nhóm `UI` ở cuối file KHÔNG thuộc đây: key của nó là id chuỗi giao diện, không phải
#: enum, nên không chịu ràng buộc viết hoa.
ENUM_GROUPS: dict[str, dict[str, str]] = {
    "PAIR_STATUS": PAIR_STATUS,
    "RUN_MODE": RUN_MODE,
    "AGENT_STATUS": AGENT_STATUS,
    "COPY_MODE": COPY_MODE,
    "CLOSE_SOURCE": CLOSE_SOURCE,
    "ALERT_LEVEL": ALERT_LEVEL,
    "MASTER_POSITION_STATUS": MASTER_POSITION_STATUS,
}

#: Mọi nhóm nhãn, dùng cho test và cho việc duyệt toàn bộ bảng nhãn.
ALL_GROUPS: dict[str, dict[str, str]] = dict(ENUM_GROUPS)


def label(group: dict[str, str], key: str) -> str:
    """Trả về nhãn tiếng Việt của ``key`` trong ``group``.

    Thiếu nhãn thì trả về chính ``key`` và ghi WARNING. Hàm này **không bao giờ ném exception**:
    thiếu một nhãn không đáng làm sập dashboard.
    """
    if key is None:
        _log.warning("label() nhan key None")
        return ""
    text = group.get(key)
    if text is None:
        _log.warning("Thieu nhan tieng Viet cho key %r", key)
        return key
    return text


# ---------------------------------------------------------------------------------------------
# Nhãn giao diện (phase 9).
#
# Template và JavaScript **không được** chứa chuỗi tiếng Việt nào. Chúng hiển thị đúng những gì
# tầng Python gửi xuống, và tầng Python lấy chữ từ đây. Nhờ vậy đổi cách gọi một khái niệm chỉ
# phải sửa một chỗ, và `grep` tìm chuỗi tiếng Việt lọt ra ngoài trở thành một phép kiểm được.
# ---------------------------------------------------------------------------------------------

UI = {
    "app_title": "MT5 Copy Bridge",
    "nav_main": "Tổng quan",
    "nav_findings": "Sai lệch",
    "nav_config": "Cấu hình",
    "nav_log": "Nhật ký",

    "run_mode_label": "Chế độ vận hành",
    "agents": "Trạng thái agent",
    "canary_last_ok": "Canary gần nhất",
    "trade_allowed": "Algo Trading",
    "trade_not_allowed": ("Algo Trading đang TẮT trên terminal này. Lệnh ĐÓNG sẽ thất "
                          "bại, trong khi lệnh MỞ qua giao diện vẫn chạy."),
    "canary_never": "chưa lần nào",

    "metric_p50": "Độ trễ copy p50",
    "metric_p95": "Độ trễ copy p95",
    "metric_hedged": "Cặp đang hedge",
    "metric_attention": "Cần can thiệp",

    "pairs_title": "Cặp lệnh",
    "col_pair": "Cặp",
    "col_symbol": "Symbol",
    "col_direction": "Chiều",
    "col_volume": "Vol M/C",
    "col_status": "Trạng thái",
    "orphan_master_left": "Mất hedge — còn Master",
    "orphan_client_left": "Mất hedge — còn Client",
    "reason_mismatch": "Sai kênh mở lệnh",
    "close_reason_mismatch": "Sai kênh đóng lệnh",
    "reason_mismatch_ca_hai": "Sai kênh cả mở lẫn đóng",
    "no_pairs": "Chưa có cặp lệnh nào",

    "btn_pause_new": "Tạm dừng lệnh mới",
    "btn_stop_sync": "Dừng toàn bộ đồng bộ",
    "btn_resume": "Bắt đầu copy",
    "btn_emergency": "Đóng khẩn cấp tất cả",
    "confirm_stop_sync": "Dừng toàn bộ đồng bộ sẽ bỏ rơi các cặp đang chạy. Tiếp tục?",
    "confirm_emergency": "Gõ đúng chuỗi dưới đây để đóng toàn bộ cặp đang quản lý:",
    "emergency_phrase": "DONG TAT CA",
    "emergency_wrong": "Chuỗi xác nhận không đúng. Không có lệnh nào được gửi.",

    "findings_title": "Sai lệch cần xử lý",
    "findings_safe": "An toàn — khắc phục chỉ gồm đóng lệnh hoặc sửa sổ sách",
    "findings_decision": "Cần quyết định — dính tới mở lệnh hoặc đóng Master",
    "evidence_db": "Sổ sách",
    "evidence_master": "Master thực tế",
    "evidence_client": "Client thực tế",
    "btn_accept": "Chấp nhận",
    "btn_accept_all_safe": "Chấp nhận tất cả mục an toàn",
    "btn_skip": "Bỏ qua",
    "skip_note_prompt": "Lý do bỏ qua (sẽ để lại một cảnh báo tồn tại):",
    "no_findings": "Không có sai lệch nào",
    "confirm_resume_with_findings": "Còn {n} sai lệch chưa xử lý:",

    "cfg_title": "Cấu hình",
    "cfg_effect_now": "Có hiệu lực ngay",
    "cfg_effect_next_open": ("Chỉ áp dụng cho lệnh mở sau khi lưu. "
                             "Các cặp đang chạy giữ nguyên tỷ lệ."),
    "cfg_multiplier": "Hệ số volume",
    "cfg_preview": "Xem trước",
    "cfg_open_route": "Kênh mở lệnh phía Client",
    # Chinh cot nay quyet dinh deal DONG mang CLIENT hay EXPERT, nen no phai nhin thay duoc
    # tren dashboard chu khong chi qua `bridge.admin cau-hinh-client`.
    "cfg_close_route": "Kênh đóng lệnh phía Client",
    "cfg_master_close_always": "Master đóng thì Client đóng: LUÔN BẬT, không tắt được",
    "cfg_can_close_master": "Cho phép Client đóng ngược Master",
    "confirm_can_close_master": ("Bật mục này nghĩa là khi một Client đóng, Bridge sẽ đóng "
                                 "Master, rồi đóng nốt các Client còn lại. Tiếp tục?"),
    "confirm_open_route_ui": ("Chuyển sang kênh giao diện: thông lượng còn khoảng một lệnh mỗi "
                              "giây, độ trễ copy tăng lên khoảng nửa giây tới vài giây. "
                              "Bắt buộc phải có một clicker đang kết nối. Tiếp tục?"),
    "map_title": "Ánh xạ symbol",
    "btn_verify": "Kiểm tra với sàn",
    "map_unverified": "Chưa kiểm tra — không lưu được",
    "map_verify_failed": "Sàn Client không có symbol này",

    "log_title": "Nhật ký cảnh báo",
    "btn_ack": "Đã xử lý",
    "no_alerts": "Không có cảnh báo nào",

    "login_title": "Đăng nhập",
    "login_password": "Mật khẩu",
    "login_submit": "Vào",
    "login_wrong": "Mật khẩu không đúng",
}

ALL_GROUPS["UI"] = UI

