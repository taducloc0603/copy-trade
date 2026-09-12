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

#: Message của ListView, dùng cho khảo sát Bước 0 (đường đóng). `LVM_GETITEMCOUNT` trả về 0 hoặc
#: lỗi khi control **không phải** ListView thật — và đó là một câu trả lời, không phải một thất bại.
LVM_FIRST = 0x1000
LVM_GETITEMCOUNT = LVM_FIRST + 4
LVM_GETITEMTEXTW = LVM_FIRST + 115
#: `LVITEMW.mask` cho biết chỉ quan tâm trường text.
LVIF_TEXT = 0x0001

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

#: Hạn chờ riêng cho ba message chuột của `send_double_click`, ngắn hơn hẳn `SEND_TIMEOUT_MS`.
#:
#: Đo trên VPS 2026-09-12, 6/6 lần đóng: cú nhấp **đầu tiên** của mỗi lần đóng treo tới đúng hết hạn
#: 2 giây rồi không mở hộp thoại nào; cú nhấp lại ngay sau đó mở trong 0,28–1,17 giây. Hai giây ấy
#: là tiền vô ích trả cho **mỗi** lệnh đóng.
#:
#: Hạ được vì giá trị trả về của ba message này **không phải bằng chứng**: bằng chứng duy nhất là hộp
#: thoại có hiện ra hay không (xem `send_double_click`). Hết hạn sớm chỉ làm chỗ gọi biết sớm hơn là
#: nên nhấp lại. 600 ms vẫn dư gấp đôi cho một cú nhấp thành công (đo 0,25–0,35 giây).
CLICK_TIMEOUT_MS = 600


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


# -- khảo sát Bước 0: đọc thêm, vẫn không tác động ---------------------------------------------
#
# Cả phần dưới đây **chỉ đọc**. Không có `PostMessage`, không `WM_SETTEXT`, không `WM_CHAR`. Nó
# sinh ra để trả lời bốn câu hỏi của Bước 0 trong kế hoạch đổi đường ĐÓNG sang giao diện: tab
# Trade có control Win32 thật không, từng dòng vị thế có đọc được không, hộp thoại đóng có hình
# dạng gì, và có ID lệnh menu nào mở được nó.
#
# Một phép đo **âm** ở đây cũng là kết quả. `listview_item_count()` trả `None` nghĩa là control
# đó không phải ListView thật, và đó chính là thông tin cần để quyết định đi tiếp hay dừng.


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Toạ độ màn hình của một cửa sổ: `(left, top, right, bottom)`.

    Cần cho Bước 0 vì nếu danh sách vị thế không có HWND cho từng dòng thì đường duy nhất còn lại
    là bấm theo toạ độ — và phải nhìn thấy kích thước thật mới đánh giá được việc đó mong manh tới
    đâu.
    """
    rect = RECT()
    if not user32().GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return (0, 0, 0, 0)
    return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))


def get_parent(hwnd: int) -> int:
    """HWND cha, hoặc 0. Dùng để dựng lại cây từ danh sách phẳng của `EnumChildWindows`."""
    return int(user32().GetParent(wintypes.HWND(hwnd)) or 0)


# -- menu (chỉ đọc) ----------------------------------------------------------------------------

def get_menu(hwnd: int) -> int:
    """HMENU của thanh menu một cửa sổ, hoặc 0 nếu nó không có menu chuẩn.

    Trả 0 là một câu trả lời có nghĩa: nghĩa là MT5 tự vẽ thanh menu, và khi đó không có ID lệnh
    nào để `PostMessage(WM_COMMAND, ...)` như cách mở hộp thoại New Order đang làm.
    """
    return int(user32().GetMenu(wintypes.HWND(hwnd)) or 0)


def get_menu_item_count(hmenu: int) -> int:
    count = int(user32().GetMenuItemCount(wintypes.HMENU(hmenu)))
    return count if count > 0 else 0


def get_sub_menu(hmenu: int, position: int) -> int:
    return int(user32().GetSubMenu(wintypes.HMENU(hmenu), position) or 0)


def get_menu_item_id(hmenu: int, position: int) -> int:
    """ID lệnh của một mục menu. `-1` nghĩa là mục đó mở menu con chứ không phải một lệnh."""
    return int(ctypes.c_int(user32().GetMenuItemID(wintypes.HMENU(hmenu), position)).value)


def get_menu_string(hmenu: int, position: int) -> str:
    """Chữ của một mục menu, tra **theo vị trí**.

    Chuỗi rỗng với mục owner-drawn là bình thường và cũng là một câu trả lời — nó nói rằng không
    nhận ra mục cần tìm bằng chữ được, phải dựa vào vị trí hoặc vào ID.
    """
    api = user32()
    MF_BYPOSITION = 0x0400
    length = int(api.GetMenuStringW(wintypes.HMENU(hmenu), position, None, 0, MF_BYPOSITION))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    api.GetMenuStringW(wintypes.HMENU(hmenu), position, buffer, length + 1, MF_BYPOSITION)
    return buffer.value


# -- ListView (chỉ đọc, qua bộ nhớ tiến trình đích) --------------------------------------------
#
# Đọc text của một dòng ListView thuộc tiến trình khác đòi hỏi cấp phát một vùng đệm **bên trong**
# tiến trình đó: `LVM_GETITEMTEXTW` nhận một con trỏ và control sẽ ghi vào đúng con trỏ ấy trong
# không gian địa chỉ của nó, nên một buffer của Python là vô nghĩa.
#
# Vẫn là **chỉ đọc** theo đúng nghĩa quan trọng: không có message nào làm MT5 đặt lệnh, huỷ lệnh
# hay đổi trạng thái. Thứ được ghi là một vùng nhớ rác do chính ta cấp phát và giải phóng ngay.

_kernel32: ctypes.WinDLL | None = None

PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04


class LVITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", wintypes.UINT), ("iItem", ctypes.c_int), ("iSubItem", ctypes.c_int),
        ("state", wintypes.UINT), ("stateMask", wintypes.UINT),
        ("pszText", ctypes.c_void_p), ("cchTextMax", ctypes.c_int),
        ("iImage", ctypes.c_int), ("lParam", ctypes.c_void_p),
        ("iIndent", ctypes.c_int), ("iGroupId", ctypes.c_int),
        ("cColumns", wintypes.UINT), ("puColumns", ctypes.c_void_p),
        ("piColFmt", ctypes.c_void_p), ("iGroup", ctypes.c_int),
    ]


def kernel32() -> ctypes.WinDLL:
    global _kernel32
    if _kernel32 is not None:
        return _kernel32
    if not sys.platform.startswith("win"):
        raise Win32Unavailable(f"Clicker chi chay tren Windows, dang la {sys.platform}")
    try:
        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError as exc:  # pragma: no cover - chỉ xảy ra trên máy hỏng
        raise Win32Unavailable(f"Khong nap duoc kernel32.dll: {exc}") from exc
    return _kernel32


def _send_timeout(hwnd: int, msg: int, wparam: int, lparam: int,
                  timeout_ms: int = SEND_TIMEOUT_MS) -> int | None:
    """`SendMessageTimeoutW` trần. `None` nghĩa là control không trả lời (hoặc đang treo)."""
    result = ctypes.c_size_t()
    ok = user32().SendMessageTimeoutW(
        wintypes.HWND(hwnd), msg, ctypes.c_size_t(wparam), ctypes.c_void_p(lparam),
        SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(result),
    )
    return int(result.value) if ok else None


#: Lớp của ListView chuẩn. Cần đối chiếu vì `LVM_GETITEMCOUNT` **không** phân biệt được
#: "ListView rỗng" với "không phải ListView" — xem `listview_item_count`.
LISTVIEW_CLASS = "SysListView32"


def listview_item_count(hwnd: int) -> int | None:
    """Số dòng của một ListView chuẩn.

    **Đọc kỹ giá trị trả về, nó không nói điều bạn tưởng.** Đo trên Windows 11 ngày 2026-09-10:
    một control **không phải** ListView vẫn trả về `0` chứ không báo lỗi — nó nhận một message lạ,
    không hiểu, và trả `0` như mọi message không xử lý. Nên:

    * `None` — control không trả lời trong `SEND_TIMEOUT_MS`, tức là đang treo. Hiếm.
    * `0` — **mơ hồ**: hoặc là ListView rỗng, hoặc không phải ListView. Một mình nó không kết luận
      được gì; phải đối chiếu `get_class_name(hwnd) == LISTVIEW_CLASS`.
    * `> 0` — gần như chắc chắn là ListView thật và đang có dữ liệu.

    Ghi lại đầy đủ vì đây đúng loại phép đo dễ đọc nhầm thành kết quả dương: chạy trên tab Trade
    có vị thế thật mà thấy `0` thì câu trả lời là **không đọc được**, không phải "không có vị thế".
    """
    return _send_timeout(hwnd, LVM_GETITEMCOUNT, 0, 0)


class _RemoteBuffer:
    """Vùng đệm cấp phát trong tiến trình đích, tự giải phóng khi ra khỏi `with`."""

    def __init__(self, pid: int, size: int) -> None:
        self.size = size
        api = kernel32()
        api.OpenProcess.restype = wintypes.HANDLE
        self.process = api.OpenProcess(
            PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE
            | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.process:
            raise Win32Unavailable(f"Khong mo duoc tien trinh {pid} de doc ListView")
        api.VirtualAllocEx.restype = ctypes.c_void_p
        self.address = api.VirtualAllocEx(self.process, None, size,
                                          MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
        if not self.address:
            api.CloseHandle(self.process)
            raise Win32Unavailable(f"Khong cap phat duoc {size} byte trong tien trinh {pid}")

    def __enter__(self) -> _RemoteBuffer:
        return self

    def __exit__(self, *_exc: object) -> None:
        api = kernel32()
        api.VirtualFreeEx(self.process, ctypes.c_void_p(self.address), 0, MEM_RELEASE)
        api.CloseHandle(self.process)

    def write(self, offset: int, data: bytes) -> bool:
        written = ctypes.c_size_t()
        return bool(kernel32().WriteProcessMemory(
            self.process, ctypes.c_void_p(self.address + offset), data, len(data),
            ctypes.byref(written)))

    def read(self, offset: int, size: int) -> bytes:
        buffer = (ctypes.c_char * size)()
        got = ctypes.c_size_t()
        if not kernel32().ReadProcessMemory(
                self.process, ctypes.c_void_p(self.address + offset), buffer, size,
                ctypes.byref(got)):
            return b""
        return bytes(buffer[:int(got.value)])


def listview_item_text(hwnd: int, row: int, column: int = 0, max_chars: int = 260) -> str:
    """Text của một ô trong ListView chuẩn. Chuỗi rỗng nếu không đọc được."""
    pid = get_process_id(hwnd)
    text_bytes = max_chars * 2
    item_size = ctypes.sizeof(LVITEMW)
    try:
        with _RemoteBuffer(pid, item_size + text_bytes) as remote:
            item = LVITEMW()
            item.mask = LVIF_TEXT
            item.iItem = row
            item.iSubItem = column
            item.pszText = remote.address + item_size
            item.cchTextMax = max_chars
            if not remote.write(0, bytes(memoryview(item).tobytes())):
                return ""
            if _send_timeout(hwnd, LVM_GETITEMTEXTW, row, remote.address) is None:
                return ""
            raw = remote.read(item_size, text_bytes)
            if not raw:
                return ""
            return raw.decode("utf-16-le", errors="replace").split("\x00", 1)[0]
    except Win32Unavailable:
        return ""


# -- ListView: hình học và lựa chọn ------------------------------------------------------------
#
# Đo ngày 2026-09-10 trên tab Trade của Connext-Demo build 5.00: control là `SysListView32` thật,
# và tuy **không đọc được text của dòng** (MT5 tự vẽ), nó vẫn trả lời đầy đủ các message về hình
# học và lựa chọn. Nhờ vậy việc nhắm một dòng là **tất định**, không phải đoán toạ độ pixel trên
# một canvas — khác hẳn tình huống mà D-26 đã loại khi bàn về One Click Trading.

LVM_GETITEMRECT = LVM_FIRST + 14
LVM_SETITEMSTATE = LVM_FIRST + 43
LVM_GETNEXTITEM = LVM_FIRST + 12

LVIF_STATE = 0x0008
LVIS_FOCUSED = 0x0001
LVIS_SELECTED = 0x0002
LVNI_SELECTED = 0x0002

#: Toàn bộ dòng, kể cả các cột phụ.
LVIR_BOUNDS = 0

WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
MK_LBUTTON = 0x0001


def listview_item_rect(hwnd: int, row: int) -> tuple[int, int, int, int] | None:
    """Hình chữ nhật của một dòng, theo toạ độ **client** của chính ListView.

    Đây là nguồn toạ độ duy nhất được phép dùng để bấm vào một dòng. Tự tính bằng chiều cao dòng
    nhân chỉ số là sai ngay khi có cuộn dọc, mà lúc đó cú bấm rơi vào **dòng khác** — nghĩa là
    mở nhầm vị thế.
    """
    pid = get_process_id(hwnd)
    size = ctypes.sizeof(RECT)
    try:
        with _RemoteBuffer(pid, size) as remote:
            # `left` mang mã LVIR_* khi gửi đi, không phải toạ độ.
            yeu_cau = RECT()
            yeu_cau.left = LVIR_BOUNDS
            if not remote.write(0, bytes(memoryview(yeu_cau).tobytes())):
                return None
            if _send_timeout(hwnd, LVM_GETITEMRECT, row, remote.address) is None:
                return None
            raw = remote.read(0, size)
            if len(raw) < size:
                return None
            got = RECT.from_buffer_copy(raw)
            return (int(got.left), int(got.top), int(got.right), int(got.bottom))
    except Win32Unavailable:
        return None


def listview_selected_row(hwnd: int) -> int | None:
    """Chỉ số dòng đang được chọn, hoặc `None` nếu không có dòng nào.

    `LVM_GETNEXTITEM` trả về `-1` khi không tìm thấy, và giá trị đó về đây dưới dạng số không dấu
    64-bit, nên phải đổi lại tường minh chứ không so với `-1`.
    """
    ket_qua = _send_timeout(hwnd, LVM_GETNEXTITEM, 0xFFFFFFFFFFFFFFFF, LVNI_SELECTED)
    if ket_qua is None:
        return None
    row = ctypes.c_ssize_t(ket_qua).value
    return None if row < 0 else row


def listview_select_row(hwnd: int, row: int) -> bool:
    """Chọn một dòng bằng chính API của ListView, **không** qua chuột.

    Dùng trước cú double-click: đo được rằng MT5 mở hộp thoại theo dòng đang chọn, và đặt lựa chọn
    bằng message thì tất định hơn hẳn việc trông chờ một cú bấm chuột rơi đúng chỗ.
    """
    pid = get_process_id(hwnd)
    try:
        with _RemoteBuffer(pid, ctypes.sizeof(LVITEMW)) as remote:
            item = LVITEMW()
            item.mask = LVIF_STATE
            item.state = LVIS_SELECTED | LVIS_FOCUSED
            item.stateMask = LVIS_SELECTED | LVIS_FOCUSED
            if not remote.write(0, bytes(memoryview(item).tobytes())):
                return False
            return bool(_send_timeout(hwnd, LVM_SETITEMSTATE, row, remote.address))
    except Win32Unavailable:
        return False


def send_double_click(hwnd: int, x: int, y: int) -> bool:
    """Double-click vào một điểm trong cửa sổ, bằng `SendMessageTimeout`.

    **`SendMessage` chứ không phải `PostMessage`, và đó là kết quả đo chứ không phải sở thích.**
    Ngày 2026-09-10, gửi đủ bốn message `WM_LBUTTONDOWN/UP/DBLCLK/UP` bằng `PostMessage` vào tab
    Trade **không mở được** hộp thoại, chờ 5 giây, cả hai dòng. Cùng điểm ấy, `WM_LBUTTONDBLCLK`
    bằng `SendMessage` thì mở được ngay.

    Đáng ghi lại vì phép thử đầu suýt cho kết luận sai — rằng `PostMessage` không điều khiển được
    tab Trade. Nó **có**: một cú bấm đơn `PostMessage` đổi được lựa chọn từ 0 sang 1, tức message
    tới nơi và `lParam` được dùng thật; MT5 **không** đọc vị trí con trỏ thật.

    Vẫn là message gửi thẳng tới window proc chứ không phải `SendInput` bơm vào hàng đợi của phiên
    tương tác, nên tính chất sống-qua-RDP có cơ sở — nhưng **chưa được chứng minh**, và chỉ đo trên
    VPS mới chứng minh được (B-08, TEST-19).

    Dùng `SendMessageTimeout` chứ không phải `SendMessage` trần: message này làm MT5 mở một hộp
    thoại modal, và `SendMessage` trần sẽ chặn tới khi hộp thoại đóng — tức là treo cả clicker.

    **Phải gửi đủ `WM_LBUTTONDOWN` + `WM_LBUTTONUP` trước `WM_LBUTTONDBLCLK`**, và đây cũng là kết
    quả đo chứ không phải làm cho giống thật. Bản đầu chỉ gửi mỗi `WM_LBUTTONDBLCLK`: nó mở được
    dòng 0 nhưng **không** mở được dòng 1. Lý do là dòng 0 tình cờ đã nhận một cú bấm đơn ở phép đo
    trước đó, nên nó có sẵn trạng thái mà `WM_LBUTTONDBLCLK` cần; dòng 1 thì không.

    Đúng loại bẫy khó thấy nhất: bản thiếu vẫn chạy trên **dòng đầu tiên**, tức là chạy trên đúng
    trường hợp mà người ta thử tay. Không gửi `WM_LBUTTONUP` cuối cùng vì lúc đó MT5 đã ở trong
    vòng lặp modal của hộp thoại, và message ấy chỉ tổ chờ hết hạn.
    """
    lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    if _send_timeout(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam, CLICK_TIMEOUT_MS) is None:
        return False
    if _send_timeout(hwnd, WM_LBUTTONUP, 0, lparam, CLICK_TIMEOUT_MS) is None:
        return False
    return _send_timeout(
        hwnd, WM_LBUTTONDBLCLK, MK_LBUTTON, lparam, CLICK_TIMEOUT_MS) is not None
