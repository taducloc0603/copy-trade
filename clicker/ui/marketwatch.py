"""Market Watch — đường mở hộp thoại New Order **đúng symbol**, không phụ thuộc chart (trả B-01).

Vì sao không mở bằng `WM_COMMAND 32848` như trước: lệnh đó mở New Order theo **chart đang active**,
nên mỗi terminal Client chỉ copy được đúng một symbol. Nhấp đúp một dòng Market Watch thì mở New
Order **cho symbol của dòng đó**, và chart active không đổi.

Đo 2026-09-25 trên Connext-Demo (terminal Client 538217, không đặt lệnh nào — chỉ mở, đọc, huỷ):

* Nhấp đúp (`post_then_double_click`): **24/24** lần ra đúng symbol của dòng — 10 lần lặp cùng dòng,
  8 lần xen kẽ hai dòng, 6 lần với cửa sổ terminal **minimized**. Hộp thoại hiện sau 0,22–0,73 s.
* Chọn dòng bằng `LVM_SETITEMSTATE` rồi gửi `32848`: **luôn** ra symbol của chart. Lựa chọn trong
  Market Watch không ảnh hưởng lệnh menu, nên đường này bị loại.
* Dòng cuối ("click to add") **không** mở hộp thoại: nó mở một ô gõ symbol ngay trong danh sách.

Cùng giới hạn với tab Trade (`tradetab.py`): **danh sách không đọc được nội dung**. `LVM_GETITEMTEXT`
chép về chuỗi rỗng vì MT5 tự vẽ. Nên nhận ra dòng bằng **phép tìm có kiểm chứng**: mở hộp thoại từ
một dòng, đọc symbol trong chính hộp thoại, sai thì huỷ. Mở rồi huỷ không đặt lệnh nào, nên toàn bộ
phép tìm nằm ở phía an toàn của ranh giới D-24. Và `Mt5UiDriver._commit` vẫn đọc lại symbol lần cuối
trước cú bấm.
"""

from __future__ import annotations

from bridge.logging_setup import get_logger
from clicker.ui import win32

log = get_logger(__name__)

#: ctrlID của `SysListView32` trong Market Watch. Cha của nó là control bar mang tiêu đề
#: `'Market Watch: hh:mm:ss'`. Đo trên Connext-Demo build 5.00, **cả hai** terminal cùng số.
CTRL_MARKET_WATCH = 10144

#: Hoành độ cú nhấp, trong toạ độ client của danh sách: nằm trong cột Symbol. Tung độ **luôn** lấy
#: từ `LVM_GETITEMRECT` — xem `tradetab.CLICK_X` về vì sao không tự tính.
CLICK_X = 40

#: Chờ hộp thoại sau một cú nhấp. Đo được 0,22–0,73 s; dòng không mở hộp thoại (dòng "click to add")
#: tiêu trọn khoảng này, nên không để dài.
CHO_HOP_THOAI_SEC = 1.5


class MarketWatchError(RuntimeError):
    """Không tìm thấy Market Watch, hoặc không dòng nào mở ra symbol cần tìm."""


def tim_danh_sach(terminal_hwnd: int) -> int:
    """HWND của danh sách Market Watch, hoặc ném lỗi nói rõ vì sao không có."""
    ung_vien = [c for c in win32.enum_children(terminal_hwnd, doc_chu=frozenset())
                if c.ctrl_id == CTRL_MARKET_WATCH and c.class_name == win32.LISTVIEW_CLASS]
    hien = [c for c in ung_vien if c.visible]
    if not hien:
        raise MarketWatchError(
            f"Khong thay Market Watch (ctrlID {CTRL_MARKET_WATCH}) dang hien tren terminal. "
            "Bat lai bang Ctrl+M va giu no luon mo.")
    if len(hien) > 1:
        # Hai danh sách cùng ctrlID cùng hiện thì không biết nhấp vào đâu.
        raise MarketWatchError(f"Co {len(hien)} Market Watch cung ctrlID {CTRL_MARKET_WATCH}")
    return hien[0].hwnd


def so_dong(list_hwnd: int) -> int | None:
    """Số dòng, **kể cả** dòng "click to add" cuối cùng. `None`: control không trả lời."""
    return win32.listview_item_count(list_hwnd)


def mo_new_order(list_hwnd: int, row: int) -> bool:
    """Nhấp đúp dòng `row`. Trả về việc message có gửi được hay không.

    **Không** trả về "đã mở đúng symbol" — nó không biết điều đó. Chỗ gọi phải chờ hộp thoại rồi
    đọc symbol trong đó.
    """
    rect = win32.listview_item_rect(list_hwnd, row)
    if rect is None:
        log.warning("Market Watch: khong lay duoc hinh chu nhat cua dong %d", row)
        return False
    return win32.post_then_double_click(list_hwnd, CLICK_X, (rect[1] + rect[3]) // 2)


def dong_o_them_symbol(list_hwnd: int) -> None:
    """Đóng ô gõ symbol nếu một cú nhấp vừa rơi vào dòng "click to add".

    Để nguyên thì ô gõ ở lại trong Market Watch của người dùng, và phím Enter kế tiếp sẽ thêm symbol.
    """
    for c in win32.enum_children(list_hwnd, doc_chu=frozenset()):
        if c.class_name == "Edit" and c.visible:
            log.info("Market Watch: dong o go symbol vua mo nham")
            win32.post_escape(c.hwnd)


def thu_tu_do(so_dong: int, symbol: str, ban_do: dict[str, int]) -> list[int]:
    """Thứ tự các dòng nên nhấp để tìm `symbol`.

    Dòng bản đồ gợi ý đi trước; còn lại theo thứ tự từ trên xuống. Dòng cuối tự nhiên nằm cuối — đó
    thường là "click to add", chỉ tới lượt nó khi mọi dòng khác đều không phải.
    """
    goi_y = ban_do.get(symbol)
    dau = [goi_y] if goi_y is not None and 0 <= goi_y < so_dong else []
    return dau + [r for r in range(so_dong) if r not in dau]


def ghi_ban_do(ban_do: dict[str, int], row: int, symbol: str | None) -> None:
    """Ghi điều vừa đọc được ở `row`. Mục cũ nào trỏ vào dòng này mà khác symbol thì đã sai — xoá."""
    for cu in [k for k, v in ban_do.items() if v == row and k != symbol]:
        del ban_do[cu]
    if symbol:
        ban_do[symbol] = row
