"""Canary: chứng minh clicker còn điều khiển được giao diện, trước khi Bridge tin nó.

> **Bridge không bao giờ được gửi `OPEN_UI` cho một clicker chưa chứng minh được nó đang điều
> khiển được giao diện.**

Bài học ở `plan/08` mục 8.1: thứ nguy hiểm nhất không phải thành phần chết, mà là thành phần
**trông vẫn khoẻ** trong khi đã mất khả năng làm việc. Một clicker mất cửa sổ MT5 vẫn gửi
heartbeat đều đặn và vẫn nhận command — rồi im lặng không mở lệnh nào.

Kết quả probe đi vào `heartbeat.broker_connected`, **diễn giải lại cho role CLICKER** thành
*"tôi điều khiển được giao diện"*. False → Bridge cho agent sang `DEGRADED` bằng đúng cơ chế sẵn
có của phase 3 → luồng mở lệnh bỏ qua Client đó kèm alert ERROR, và **không** rơi về đường EA.
"""

from __future__ import annotations

from dataclasses import dataclass

from clicker.ui import win32


@dataclass(frozen=True)
class ProbeResult:
    """Kết quả một lần kiểm tra sức khoẻ."""

    healthy: bool
    detail: str
    hwnd: int | None = None
    title: str = ""

    def __bool__(self) -> bool:
        return self.healthy


def find_terminal(title_contains: str) -> ProbeResult:
    """Tìm cửa sổ terminal MT5 theo class **và** một mẩu tiêu đề.

    Hai điều kiện chứ không phải một: class loại bỏ mọi cửa sổ không phải MT5, còn tiêu đề chứa
    số tài khoản đang đăng nhập nên nó kiểm luôn **đúng tài khoản**. Gửi lệnh nhầm terminal là
    hỏng theo cách tệ nhất — mất tiền ở một tài khoản mà sổ sách không hề biết tới.
    """
    if not title_contains:
        return ProbeResult(False, "Chua cau hinh terminal_title")
    if not win32.is_available():
        return ProbeResult(False, "Khong goi duoc Win32 o moi truong nay")

    matches = [hwnd for hwnd in win32.enum_top_level(win32.TERMINAL_CLASS)
               if title_contains in win32.get_window_text(hwnd)]
    if not matches:
        return ProbeResult(False, f"Khong thay cua so nao co tieu de chua {title_contains!r}")
    if len(matches) > 1:
        # Hai terminal cùng khớp thì không có cách nào chọn đúng. Từ chối, đừng đoán.
        return ProbeResult(False, f"Co {len(matches)} cua so cung khop {title_contains!r}")
    return ProbeResult(True, "Thay dung mot cua so terminal", hwnd=matches[0],
                       title=win32.get_window_text(matches[0]))


def account_login_from_title(title: str) -> int | None:
    """Số tài khoản đọc từ tiêu đề `'538217 - Connext-Demo: ...'`.

    Nhờ nó, kiểm tra `ACCOUNT_MISMATCH` sẵn có ở `bridge/protocol/server.py` thành hàng rào
    thật: clicker trỏ nhầm terminal thì Bridge từ chối bắt tay. Rẻ, và bắt đúng loại lỗi cấu
    hình nguy hiểm nhất.
    """
    head = title.split(" ", 1)[0].strip()
    return int(head) if head.isdigit() else None


def probe(title_contains: str) -> ProbeResult:
    """Kiểm tra nhẹ, chạy mỗi chu kỳ heartbeat: cửa sổ còn đó và tiêu đề vẫn đúng login."""
    result = find_terminal(title_contains)
    if not result.healthy or result.hwnd is None:
        return result
    if not win32.is_window(result.hwnd):
        return ProbeResult(False, "Handle cua so khong con hop le", hwnd=result.hwnd)
    return ProbeResult(True, "Cua so terminal con song", hwnd=result.hwnd, title=result.title)
