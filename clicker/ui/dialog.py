"""Tìm, đọc và điền hộp thoại New Order của MT5.

Tách khỏi `driver.py` một cách cố ý: **toàn bộ file này test được mà không đặt lệnh nào**. Mở
hộp thoại, đọc lại, đóng bằng ESC — không có hàm nào ở đây bấm nút gửi lệnh. Việc bấm nằm ở
`driver.py`, sau `commit()`.

Cách mở hộp thoại: `PostMessage(WM_COMMAND, 32848)` — chính là `Tools → New Order (F9)`, id đọc
trực tiếp từ menu của bản MT5 đang chạy. Không dùng phím giả lập, nên không cần focus và không
cần desktop tương tác; đó là điều kiện để sống qua phiên RDP đã ngắt.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from bridge.logging_setup import get_logger
from clicker.ui import win32

log = get_logger(__name__)

# ctrlID đo trên Connext-Demo, bản MT5 build 5.00. Xem `plan/06b` mục "Số liệu đã đo".
CTRL_VOLUME = 10333
CTRL_COMMENT = 1001
CTRL_BUY = 10408
CTRL_SELL = 10409
CTRL_SYMBOL_COMBO = 10331
CTRL_SYMBOL_EDIT = 10325
CTRL_PRICE = 10413

#: Chữ trên nút **đang hiện**. Bản ẩn cùng ctrlID mang chữ `'Buy'`/`'Sell'` trần.
BUY_TEXT = "Buy by Market"
SELL_TEXT = "Sell by Market"

#: Hộp thoại phải có đủ những control này thì mới đúng là New Order. Chữ ký chặt hơn nhiều so
#: với chỉ khớp lớp `#32770` — terminal có nhiều hộp thoại cùng lớp.
SIGNATURE = (CTRL_VOLUME, CTRL_COMMENT, CTRL_BUY, CTRL_SELL)

OPEN_TIMEOUT_SEC = 5.0
POLL_SEC = 0.05


class DialogError(RuntimeError):
    """Không tìm được hộp thoại, hoặc nó không có hình dạng mong đợi."""


@dataclass(frozen=True)
class DialogState:
    """Những gì hộp thoại đang thực sự hiển thị. Nguồn duy nhất cho việc đọc lại."""

    symbol: str
    volume: str
    comment: str
    price: str

    def volume_as_float(self) -> float | None:
        """Volume dạng số.

        Chuẩn hoá dấu thập phân và bỏ khoảng trắng phân nhóm trước khi đổi: locale là thuộc
        tính của **máy**, không phải của sàn, nên so chuỗi là bẫy chờ sẵn cho máy khác.
        """
        raw = self.volume.replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            return None


@dataclass
class NewOrderDialog:
    """Một hộp thoại New Order đang mở."""

    hwnd: int
    controls: dict[int, win32.ControlInfo]

    # -- mở và đóng --------------------------------------------------------------------------

    @classmethod
    def open(cls, terminal_hwnd: int, timeout_sec: float = OPEN_TIMEOUT_SEC) -> NewOrderDialog:
        """Mở hộp thoại trên đúng terminal đã cho, hoặc dùng lại cái đang mở sẵn."""
        pid = win32.get_process_id(terminal_hwnd)

        existing = cls._find(pid)
        if existing is not None:
            log.info("Hop thoai New Order da mo san, dung lai")
            return existing

        if not win32.post_command(terminal_hwnd, win32.MENU_NEW_ORDER):
            raise DialogError("PostMessage WM_COMMAND that bai")

        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            found = cls._find(pid)
            if found is not None:
                return found
            time.sleep(POLL_SEC)
        raise DialogError(f"Khong thay hop thoai New Order sau {timeout_sec}s")

    @classmethod
    def _find(cls, pid: int) -> NewOrderDialog | None:
        """Hộp thoại `#32770` của **đúng tiến trình đó** và mang đủ chữ ký control.

        Lọc theo PID là bắt buộc: dự án này chạy hai terminal cạnh nhau, và hộp thoại của cái
        kia cũng là `#32770`.
        """
        for hwnd in win32.enum_top_level(win32.DIALOG_CLASS):
            if win32.get_process_id(hwnd) != pid or not win32.is_visible(hwnd):
                continue
            controls = cls._map_controls(hwnd)
            if all(ctrl_id in controls for ctrl_id in SIGNATURE):
                return cls(hwnd=hwnd, controls=controls)
        return None

    @staticmethod
    def _map_controls(dialog_hwnd: int) -> dict[int, win32.ControlInfo]:
        """Ánh xạ ctrlID → control, **chỉ lấy control đang hiện**.

        ctrlID 10408/10409 xuất hiện hai lần trong hộp thoại; bản ẩn mang chữ `'Buy'`/`'Sell'`
        trần. Bấm nhầm vào bản vô hình là một cú bấm không đi đâu cả — và tệ hơn, nó không báo
        lỗi. Nên vừa lọc `visible` vừa đối chiếu text ở `button()`.
        """
        mapped: dict[int, win32.ControlInfo] = {}
        for control in win32.enum_children(dialog_hwnd):
            if control.visible and control.ctrl_id > 0:
                mapped.setdefault(control.ctrl_id, control)
        return mapped

    def cancel(self) -> None:
        """Đóng hộp thoại mà không gửi gì. Đây là đường thoát của `commit()` khi đọc lại lệch."""
        win32.post_close(self.hwnd)

    def is_open(self) -> bool:
        return win32.is_window(self.hwnd) and win32.is_visible(self.hwnd)

    def wait_closed(self, timeout_sec: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if not self.is_open():
                return True
            time.sleep(POLL_SEC)
        return False

    # -- đọc ---------------------------------------------------------------------------------

    def control(self, ctrl_id: int) -> win32.ControlInfo:
        try:
            return self.controls[ctrl_id]
        except KeyError:
            raise DialogError(f"Hop thoai khong co control {ctrl_id}") from None

    def button(self, direction: str) -> win32.ControlInfo:
        """Nút Buy hoặc Sell **đang hiện**, đối chiếu cả ctrlID lẫn chữ trên nút."""
        ctrl_id, expect = ((CTRL_BUY, BUY_TEXT) if direction == "BUY"
                           else (CTRL_SELL, SELL_TEXT))
        control = self.control(ctrl_id)
        if expect.lower() not in control.text.lower():
            raise DialogError(
                f"Nut {direction} (ctrlID {ctrl_id}) mang chu {control.text!r}, "
                f"khong phai {expect!r}. Co the dang bam vao ban an."
            )
        return control

    def read_back(self) -> DialogState:
        """Đọc lại nguyên trạng từ hộp thoại. Không dùng cache — đó là điểm của việc đọc lại."""
        return DialogState(
            symbol=win32.get_control_text(self.control(CTRL_SYMBOL_EDIT).hwnd),
            volume=win32.get_control_text(self.control(CTRL_VOLUME).hwnd),
            comment=win32.get_control_text(self.control(CTRL_COMMENT).hwnd),
            price=win32.get_control_text(self.control(CTRL_PRICE).hwnd),
        )

    # -- điền --------------------------------------------------------------------------------

    def set_volume(self, volume: float) -> bool:
        """Ghi volume bằng `WM_CHAR`. **Không** được đổi sang `WM_SETTEXT** — xem `win32.type_text`.

        Dấu chấm thập phân, luôn luôn. `read_back()` sẽ bắt được nếu máy khác nghĩ khác, nhưng
        lưu ý `read_back()` **một mình nó không đủ**: nó chỉ đọc chữ, mà chữ và giá trị MT5 dùng
        có thể khác nhau.
        """
        return win32.type_text(self.control(CTRL_VOLUME).hwnd, f"{volume:g}")

    def set_comment(self, comment: str) -> bool:
        return win32.type_text(self.control(CTRL_COMMENT).hwnd, comment)
