"""Danh sách vị thế ở tab Trade của Toolbox — nơi duy nhất mở được hộp thoại đóng.

Vì sao phải đi qua đây thay vì gửi một lệnh menu như đường MỞ: **không có ID lệnh menu nào cho
"Close position"**. Đo ngày 2026-09-10, đọc toàn bộ cây menu của terminal bằng `GetMenu`: mục
`Tools` chỉ có `32848 New Order`, và không có mục đóng vị thế ở bất kỳ nhánh nào. Đóng lệnh chỉ
nằm ở menu chuột phải của chính danh sách này.

**Điều quan trọng nhất về module này, và nó là một giới hạn chứ không phải một tính năng:**

> Danh sách **không đọc được nội dung**. `LVM_GETITEMTEXT` chép về 0 ký tự vì MT5 tự vẽ từng dòng
> và không giữ chuỗi trong control. Nên không có cách nào hỏi "dòng nào là vị thế 72205853".

Cái đọc được là **hình học và lựa chọn**: số dòng, hình chữ nhật từng dòng, chọn dòng theo chỉ số.
Tức là nhắm một dòng thì **tất định**, nhưng biết dòng đó là vị thế nào thì không.

Chỗ bịt lỗ hổng đó nằm ở `dialog.ClosePositionDialog`: sau khi hộp thoại mở ra, ticket đọc được
từ ba nguồn độc lập. Nên việc mở một dòng biến từ **phép đoán** thành một bước của **phép tìm có
kiểm chứng** — mở, đọc ngược, sai thì huỷ rồi thử dòng khác. Mở và huỷ hộp thoại **không đặt lệnh
nào**, nên toàn bộ phép tìm nằm ở phía an toàn của ranh giới D-24.
"""

from __future__ import annotations

from bridge.logging_setup import get_logger
from clicker.ui import win32

log = get_logger(__name__)

#: ctrlID của thanh Toolbox. Cùng số với lệnh menu `View → Toolbox (Ctrl+T)`, đọc từ menu thật.
CTRL_TOOLBOX = 32841

#: ctrlID của `SysListView32` **riêng tab Trade**. Mỗi tab của Toolbox có một ctrlID khác nhau
#: (10109, 10149, 10328, …) và chỉ tab đang mở mới `visible`. Nhờ vậy hằng số này vừa nhận ra
#: đúng danh sách, vừa trả lời luôn câu "tab Trade có đang mở không" — thay vì phải hỏi
#: `SysTabControl32` xem tab nào đang chọn, vốn không đọc được chữ vì MT5 tự vẽ.
#:
#: Đo trên Connext-Demo build 5.00. Sàn khác thì đo lại bằng `python -m clicker.ui.dump`.
CTRL_TRADE_LIST = 10328

#: Hoành độ của cú bấm, tính trong toạ độ client của danh sách. Nằm trong cột đầu (rộng 231px khi
#: đo) nên không rơi ra ngoài dù cửa sổ hẹp lại. Tung độ **luôn** lấy từ `LVM_GETITEMRECT`, không
#: bao giờ tự tính bằng chiều cao dòng nhân chỉ số — có cuộn dọc là sai ngay, mà sai ở đây nghĩa
#: là mở nhầm vị thế.
CLICK_X = 100


class TradeTabError(RuntimeError):
    """Không tìm thấy danh sách vị thế, hoặc tab Trade không mở."""


def tim_danh_sach(terminal_hwnd: int) -> int:
    """HWND của danh sách vị thế, hoặc ném lỗi nói rõ vì sao không có.

    Từ chối chứ không đoán: nếu tab Trade không phải tab đang mở thì `SysListView32` của nó không
    `visible`, và cái đang hiện là danh sách của tab khác (Journal, History…). Bấm vào đó không
    mở hộp thoại nào — nhưng cũng không được lặng lẽ thử.
    """
    ung_vien = [c for c in win32.enum_children(terminal_hwnd)
                if c.ctrl_id == CTRL_TRADE_LIST and c.class_name == win32.LISTVIEW_CLASS]
    if not ung_vien:
        raise TradeTabError(
            f"Khong thay danh sach vi the (ctrlID {CTRL_TRADE_LIST}) trong cua so terminal. "
            "Toolbox co dang bi tat khong? Bat lai bang Ctrl+T.")
    hien = [c for c in ung_vien if c.visible]
    if not hien:
        raise TradeTabError(
            f"Danh sach vi the (ctrlID {CTRL_TRADE_LIST}) ton tai nhung khong hien. "
            "Tab Trade cua Toolbox dang khong mo — chuyen sang tab Trade roi thu lai.")
    if len(hien) > 1:
        # Không bao giờ nên xảy ra. Hai danh sách cùng ctrlID cùng hiện thì không có cách nào
        # chọn đúng, và chọn sai nghĩa là đóng nhầm vị thế.
        raise TradeTabError(f"Co {len(hien)} danh sach cung ctrlID {CTRL_TRADE_LIST} dang hien")
    return hien[0].hwnd


def so_dong(list_hwnd: int) -> int | None:
    """Số dòng của danh sách. `None` nghĩa là control không trả lời.

    Lưu ý `0` là câu trả lời hợp lệ và khác `None`: danh sách rỗng nghĩa là **không có vị thế nào
    để đóng**, còn `None` nghĩa là không hỏi được.
    """
    return win32.listview_item_count(list_hwnd)


def mo_hop_thoai_dong(list_hwnd: int, row: int, nhanh: bool = True) -> bool:
    """Mở hộp thoại đóng cho dòng thứ `row`. Trả về việc message có gửi được hay không.

    **Không** trả về "đã mở đúng vị thế" — nó không biết điều đó, và không thể biết. Chỗ gọi phải
    chờ hộp thoại rồi đọc ngược ticket (`dialog.ClosePositionDialog`).

    Hai bước, cả hai đều đo được (2026-09-10):

    1. `LVM_SETITEMSTATE` chọn dòng — bằng API của ListView, không qua chuột, nên tất định.
    2. `WM_LBUTTONDBLCLK` bằng **`SendMessage`**. `PostMessage` bốn message chuột **không mở được**
       hộp thoại; xem `win32.send_double_click` để biết vì sao và vì sao điều đó không có nghĩa là
       `PostMessage` vô dụng ở đây.
    """
    rect = win32.listview_item_rect(list_hwnd, row)
    if rect is None:
        log.warning("Khong lay duoc hinh chu nhat cua dong %d", row)
        return False

    if not win32.listview_select_row(list_hwnd, row):
        log.warning("Khong chon duoc dong %d", row)
        return False

    y = (rect[1] + rect[3]) // 2
    # `nhanh` (mặc định): nhấn/nhả gửi kiểu KHÔNG chờ rồi double-click gửi kiểu chờ. Đo trên VPS
    # 2026-09-12: gửi `WM_LBUTTONDOWN` kiểu chờ treo hết hạn ở cú nhấp đầu của **mọi** lệnh đóng,
    # bản post thì không treo lần nào. `nhanh=False` giữ đường cũ đã đo kỹ từ 2026-09-10, dùng cho
    # lần thử thứ hai — hai cơ chế khác nhau thì một cái hỏng trên bản MT5 lạ vẫn còn cái kia.
    bam = win32.post_then_double_click if nhanh else win32.send_double_click
    return bam(list_hwnd, CLICK_X, y)
