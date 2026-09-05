"""Bọc mỏng các hàm `user32.dll` cần dùng. Không có quyết định nghiệp vụ nào ở đây.

Ràng buộc "không import DLL" của dự án áp cho **MQL5**, không áp cho Python — đó chính là lý do
clicker là một tiến trình Python riêng chứ không phải một phần của EA.

Vì sao `PostMessage` chứ không phải `SendInput`: `SendInput` bơm sự kiện vào hàng đợi bàn phím
của phiên tương tác, nên nó chết khi phiên RDP bị ngắt — đúng cách VPS được vận hành.
`PostMessage` gửi thẳng message tới handle cửa sổ và không cần desktop tương tác. Điều kiện để
làm được vậy là hộp thoại phải có control Win32 thật, và phép đo E1 đã xác nhận: hộp thoại New
Order là lớp `#32770` với 53 control thật.

Module này import được trên mọi nền tảng; `user32.dll` chỉ được nạp khi gọi hàm đầu tiên, để
test chạy được cả khi không ở Windows.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass

#: Message của Win32 mà driver dùng tới.
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
BM_CLICK = 0x00F5
CB_GETCURSEL = 0x0147
CB_SETCURSEL = 0x014E
WM_CHAR = 0x0102
EM_SETSEL = 0x00B1

#: Lớp cửa sổ của hộp thoại chuẩn — hộp thoại New Order thuộc lớp này (đo ở E1).
DIALOG_CLASS = "#32770"

#: Lớp cửa sổ chính của terminal MT5. Chặt hơn hẳn việc chỉ khớp tiêu đề.
TERMINAL_CLASS = "MetaQuotes::MetaTrader::5.00"

#: `Tools → New Order` (F9) trong menu của terminal. Đo trực tiếp từ menu của bản đang chạy.
#: Gửi được bằng `PostMessage` nên **không cần focus, không cần bàn phím, không cần desktop
#: tương tác** — đây là mảnh cuối của cơ chế sống qua phiên RDP đã ngắt.
MENU_NEW_ORDER = 32848

#: Thời gian chờ tối đa cho một lời gọi `SendMessageTimeout`, tính bằng ms. Giao diện treo là
#: chuyện có thật; treo cả clicker theo nó thì mất luôn khả năng báo cáo.
SEND_TIMEOUT_MS = 2000
SMTO_ABORTIFHUNG = 0x0002


class Win32Unavailable(RuntimeError):
    """Không chạy trên Windows, hoặc không nạp được `user32.dll`."""


@dataclass(frozen=True)
class ControlInfo:
    """Một control con trong hộp thoại."""

    hwnd: int
    ctrl_id: int
    class_name: str
    text: str
    #: Bắt buộc phải có: ctrlID 10408/10409 xuất hiện **hai lần** trong hộp thoại New Order, bản
    #: ẩn mang text `'Buy'`/`'Sell'`. Tra theo ID trần là bấm nhầm nút vô hình.
    visible: bool = True


_user32: ctypes.WinDLL | None = None


def user32() -> ctypes.WinDLL:
    """Nạp `user32.dll` một lần, hoặc báo lỗi rõ ràng nếu không nạp được."""
    global _user32
    if _user32 is not None:
        return _user32
    if not sys.platform.startswith("win"):
        raise Win32Unavailable(f"Clicker chi chay tren Windows, dang la {sys.platform}")
    try:
        _user32 = ctypes.WinDLL("user32", use_last_error=True)
    except OSError as exc:  # pragma: no cover - chỉ xảy ra trên máy hỏng
        raise Win32Unavailable(f"Khong nap duoc user32.dll: {exc}") from exc
    return _user32


def is_available() -> bool:
    """Có gọi được Win32 ở môi trường hiện tại không."""
    try:
        user32()
    except Win32Unavailable:
        return False
    return True


# -- đọc cây cửa sổ --------------------------------------------------------------------------

def get_window_text(hwnd: int) -> str:
    """Tiêu đề một cửa sổ, **không bao giờ chặn**.

    Cố tình dùng `GetWindowTextW` chứ không phải `SendMessage(WM_GETTEXT)`. Với cửa sổ của tiến
    trình khác, `GetWindowTextW` đọc bản cache của hệ điều hành và trả về ngay; `SendMessage`
    thì xếp hàng vào vòng lặp message của tiến trình đó và **chặn vô hạn nếu nó đang treo**.

    Đây không phải lo xa: máy đo có 348 cửa sổ cấp cao nhất, và bản đầu của hàm này đã treo cứng
    khi quét hết chúng. Một clicker treo im lặng là đúng thứ nguy hiểm nhất — nó vẫn còn sống
    dưới mắt Bridge trong khi đã ngừng làm được việc.
    """
    api = user32()
    buffer = ctypes.create_unicode_buffer(512)
    api.GetWindowTextW(wintypes.HWND(hwnd), buffer, len(buffer))
    return buffer.value


def get_control_text(hwnd: int) -> str:
    """Nội dung một control **trong hộp thoại của chính mình**.

    Ở đây phải dùng `WM_GETTEXT` thật: `GetWindowTextW` không đọc được nội dung control thuộc
    tiến trình khác. Bù lại bằng `SendMessageTimeoutW` + `SMTO_ABORTIFHUNG` để giao diện treo
    thì hàm trả về chuỗi rỗng chứ không kéo cả clicker treo theo.
    """
    api = user32()
    buffer = ctypes.create_unicode_buffer(512)
    result = wintypes.DWORD()
    ok = api.SendMessageTimeoutW(
        wintypes.HWND(hwnd), WM_GETTEXT, len(buffer), buffer,
        SMTO_ABORTIFHUNG, SEND_TIMEOUT_MS, ctypes.byref(result),
    )
    return buffer.value if ok else ""


def get_class_name(hwnd: int) -> str:
    api = user32()
    buffer = ctypes.create_unicode_buffer(256)
    api.GetClassNameW(wintypes.HWND(hwnd), buffer, len(buffer))
    return buffer.value


def get_ctrl_id(hwnd: int) -> int:
    return int(user32().GetDlgCtrlID(wintypes.HWND(hwnd)))


def is_window(hwnd: int) -> bool:
    return bool(user32().IsWindow(wintypes.HWND(hwnd)))


def is_visible(hwnd: int) -> bool:
    return bool(user32().IsWindowVisible(wintypes.HWND(hwnd)))


def get_process_id(hwnd: int) -> int:
    """PID sở hữu một cửa sổ.

    Dùng để chắc chắn hộp thoại vừa mở thuộc **đúng terminal** mình vừa bấm, chứ không phải hộp
    thoại cùng lớp `#32770` của terminal thứ hai đang chạy cạnh đó. Hai terminal trên cùng một
    máy là cấu hình bình thường của dự án này, nên đây là hàng rào thật.
    """
    pid = wintypes.DWORD()
    user32().GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def enum_top_level(class_name: str | None = None) -> list[int]:
    """Handle của mọi cửa sổ cấp cao nhất, lọc theo class nếu có.

    Lọc bằng `class_name` **trước** rồi mới đọc tiêu đề: `GetClassNameW` rẻ và không chặn, nên
    quét vài trăm cửa sổ vẫn xong trong vài mili giây.
    """
    api = user32()
    found: list[int] = []

    def callback(hwnd: int, _param: int) -> bool:
        handle = int(hwnd)
        if class_name is None or get_class_name(handle) == class_name:
            found.append(handle)
        return True

    api.EnumWindows(_ENUM_PROC(callback), 0)
    return found


def enum_children(parent: int) -> list[ControlInfo]:
    """Toàn bộ control con của một cửa sổ, kèm `ctrl_id` — khoá để nhận ra từng ô."""
    api = user32()
    found: list[ControlInfo] = []

    def callback(hwnd: int, _param: int) -> bool:
        handle = int(hwnd)
        found.append(ControlInfo(hwnd=handle, ctrl_id=get_ctrl_id(handle),
                                 class_name=get_class_name(handle),
                                 text=get_control_text(handle),
                                 visible=is_visible(handle)))
        return True

    api.EnumChildWindows(wintypes.HWND(parent), _ENUM_PROC(callback), 0)
    return found


# -- tác động --------------------------------------------------------------------------------

def set_text(hwnd: int, text: str) -> bool:
    """Đặt nội dung một ô.

    Trả về việc lời gọi có thành công hay không — **không** phải việc MT5 đã ghi nhận giá trị
    hay chưa. Ẩn số "`WM_SETTEXT` cập nhật trạng thái nội bộ hay chỉ đổi chữ hiển thị" chỉ trả
    lời được bằng đo thật (Bước 4), nên mọi đường đi tới nút gửi lệnh đều phải đọc lại trước.
    """
    api = user32()
    result = wintypes.DWORD()
    ok = api.SendMessageTimeoutW(
        wintypes.HWND(hwnd), WM_SETTEXT, 0, ctypes.c_wchar_p(text),
        SMTO_ABORTIFHUNG, SEND_TIMEOUT_MS, ctypes.byref(result),
    )
    return bool(ok)


def type_text(hwnd: int, text: str) -> bool:
    """Gõ vào một ô **như người dùng gõ**: bôi đen hết rồi gửi từng `WM_CHAR`.

    Đây không phải cách viết dài dòng của `set_text()`. Đo trên MT5 build 5.00 ngày 2026-09-05:

    * `WM_SETTEXT` đổi chữ hiển thị nhưng **không** cập nhật trạng thái nội bộ của MT5. Lệnh gửi
      đi mang volume cũ, trong khi hộp thoại và cả `read_back()` đều hiện giá trị mới.
    * Báo thêm `EN_CHANGE` cho dialog cha: vẫn hỏng.
    * Gửi TAB cho ô mất focus: vẫn hỏng, và gửi đi **volume của lệnh trước** — MT5 giữ trạng
      thái nội bộ qua các lần mở hộp thoại.
    * `WM_CHAR` từng ký tự: **đúng**.

    Ghi lại đầy đủ vì đọc lại chữ trong ô **không** chứng minh được điều gì về giá trị MT5 sẽ
    dùng. Ai đó "dọn dẹp" hàm này thành `set_text()` sẽ tạo ra một lỗi không thể thấy bằng mắt.
    """
    api = user32()
    result = wintypes.DWORD()
    if not api.SendMessageTimeoutW(wintypes.HWND(hwnd), EM_SETSEL, 0, -1,
                                   SMTO_ABORTIFHUNG, SEND_TIMEOUT_MS, ctypes.byref(result)):
        return False
    for char in text:
        if not api.SendMessageTimeoutW(wintypes.HWND(hwnd), WM_CHAR, ord(char), 0,
                                       SMTO_ABORTIFHUNG, SEND_TIMEOUT_MS,
                                       ctypes.byref(result)):
            return False
    return True


def post_click(hwnd: int) -> bool:
    """Bấm một nút bằng `PostMessage` — không cần desktop tương tác, sống qua RDP ngắt phiên."""
    return bool(user32().PostMessageW(wintypes.HWND(hwnd), BM_CLICK, 0, 0))


def post_close(hwnd: int) -> bool:
    return bool(user32().PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0))


def post_command(hwnd: int, command_id: int) -> bool:
    """Gửi một lệnh menu tới cửa sổ, như thể người dùng vừa chọn nó."""
    return bool(user32().PostMessageW(wintypes.HWND(hwnd), WM_COMMAND, command_id, 0))
