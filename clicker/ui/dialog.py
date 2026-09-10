"""Tìm, đọc và điền hộp thoại lệnh của MT5 — cả bản MỞ lẫn bản ĐÓNG.

Tách khỏi `driver.py` một cách cố ý: **toàn bộ file này test được mà không đặt lệnh nào**. Mở
hộp thoại, đọc lại, đóng bằng ESC — không có hàm nào ở đây bấm nút gửi lệnh. Việc bấm nằm ở
`driver.py`, sau `commit()`.

Cách mở hộp thoại MỞ: `PostMessage(WM_COMMAND, 32848)` — chính là `Tools → New Order (F9)`, id đọc
trực tiếp từ menu của bản MT5 đang chạy. Không dùng phím giả lập, nên không cần focus và không
cần desktop tương tác; đó là điều kiện để sống qua phiên RDP đã ngắt.

Cách mở hộp thoại ĐÓNG thì khác hẳn, và lý do được ghi ở `tradetab.py`: **không có ID lệnh menu
nào** cho "Close position" — đo ngày 2026-09-10, cả cây menu của terminal không có mục đó.

> **Hai hộp thoại này là MỘT hộp thoại ở hai chế độ.** Cùng lớp `#32770`, và bản ĐÓNG mang đủ cả
> bốn control của `SIGNATURE`. Nên chữ ký một mình nó **không** phân biệt được chúng — xem
> `la_che_do_dong()`. Đây không phải chi tiết vụn: `NewOrderDialog.open()` có nhánh "dùng lại cái
> đang mở sẵn", nên nếu không phân biệt thì một hộp thoại đóng do người vận hành lỡ để mở sẽ nuốt
> mất lệnh `OPEN_UI` kế tiếp.
"""

from __future__ import annotations

import re
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

#: Nút đóng vị thế, chỉ có ở chế độ ĐÓNG. Đo 2026-09-10. Nó cũng có **bản ẩn** mang chữ `'Close'`
#: trần, đúng cái bẫy đã biết với 10408/10409 — nên luôn phải lọc `visible` cộng đối chiếu chữ.
CTRL_CLOSE = 10410
#: ComboBox chọn vị thế. `CB_GETLBTEXT` **không** đọc được (MT5 tự vẽ, trả về độ dài nhưng không
#: ghi byte nào), nhưng `WM_GETTEXT` đọc được mục đang chọn — đó là đường thứ ba để lấy ticket.
CTRL_POSITION_COMBO = 10672

#: Chữ trên nút **đang hiện**. Bản ẩn cùng ctrlID mang chữ `'Buy'`/`'Sell'` trần.
BUY_TEXT = "Buy by Market"
SELL_TEXT = "Sell by Market"

#: Chữ mở đầu nút đóng: `'Close #72205853 buy 0.01 BTCUSD.s 78500.01 by Market'`.
CLOSE_TEXT_PREFIX = "Close #"
#: Tiêu đề cửa sổ ở chế độ đóng: `'Position: #72205853 buy 0.01 BTCUSD.s 78500.01'`.
POSITION_TITLE_PREFIX = "Position: #"

#: Hộp thoại phải có đủ những control này thì mới đúng là hộp thoại lệnh. Chặt hơn nhiều so với
#: chỉ khớp lớp `#32770` — terminal có nhiều hộp thoại cùng lớp. Nhưng **không** đủ để phân biệt
#: chế độ MỞ với chế độ ĐÓNG; việc đó là của `la_che_do_dong()`.
SIGNATURE = (CTRL_VOLUME, CTRL_COMMENT, CTRL_BUY, CTRL_SELL)

OPEN_TIMEOUT_SEC = 5.0
POLL_SEC = 0.05

_TICKET = re.compile(r"#(\d+)")


class DialogError(RuntimeError):
    """Không tìm được hộp thoại, hoặc nó không có hình dạng mong đợi."""


def doc_ticket(text: str) -> int | None:
    """Số vị thế trong một chuỗi kiểu `'Close #72205853 buy 0.01 ...'`.

    Trả `None` khi không có `#<số>` — và chỗ gọi phải coi đó là lý do **từ chối**, không phải lý do
    để đoán. Không biết đang đóng vị thế nào thì không được bấm.
    """
    khop = _TICKET.search(text or "")
    return int(khop.group(1)) if khop else None


def _map_controls(dialog_hwnd: int) -> dict[int, win32.ControlInfo]:
    """Ánh xạ ctrlID → control, **chỉ lấy control đang hiện**.

    ctrlID 10408/10409 xuất hiện hai lần trong hộp thoại; bản ẩn mang chữ `'Buy'`/`'Sell'` trần.
    Bấm nhầm vào bản vô hình là một cú bấm không đi đâu cả — và tệ hơn, nó không báo lỗi. Nên vừa
    lọc `visible` vừa đối chiếu text ở `button()`. 10410 cũng có bản ẩn y hệt.
    """
    mapped: dict[int, win32.ControlInfo] = {}
    for control in win32.enum_children(dialog_hwnd):
        if control.visible and control.ctrl_id > 0:
            mapped.setdefault(control.ctrl_id, control)
    return mapped


def la_che_do_dong(hwnd: int, controls: dict[int, win32.ControlInfo]) -> bool:
    """Hộp thoại này đang ở chế độ ĐÓNG một vị thế cụ thể hay không.

    Hai dấu hiệu độc lập, chỉ cần một là đủ — chúng đến từ hai nguồn khác nhau (tiêu đề cửa sổ do
    hệ điều hành cache, chữ trên nút do chính control giữ) nên không cùng hỏng vì một lý do.
    """
    if win32.get_window_text(hwnd).startswith(POSITION_TITLE_PREFIX):
        return True
    nut = controls.get(CTRL_CLOSE)
    return nut is not None and nut.text.startswith(CLOSE_TEXT_PREFIX)


def _quet(pid: int) -> list[tuple[int, dict[int, win32.ControlInfo]]]:
    """Mọi hộp thoại lệnh đang hiện của **đúng tiến trình đó**, kèm bản đồ control.

    Lọc theo PID là bắt buộc: dự án này chạy hai terminal cạnh nhau, và hộp thoại của cái kia
    cũng là `#32770`.
    """
    ket_qua = []
    for hwnd in win32.enum_top_level(win32.DIALOG_CLASS):
        if win32.get_process_id(hwnd) != pid or not win32.is_visible(hwnd):
            continue
        controls = _map_controls(hwnd)
        if all(ctrl_id in controls for ctrl_id in SIGNATURE):
            ket_qua.append((hwnd, controls))
    return ket_qua


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
        raw = self.volume.replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            return None


@dataclass(frozen=True)
class CloseState:
    """Những gì hộp thoại ĐÓNG đang hiển thị, kèm ticket đọc được từ ba nguồn.

    Ba nguồn chứ không phải một là có chủ ý: đây là **toàn bộ** cách biết mình đang đóng đúng vị
    thế nào, vì danh sách vị thế không đọc được text (MT5 tự vẽ). Một nguồn im lặng sai thì hai
    nguồn kia phải cãi lại.
    """

    ticket_tieu_de: int | None
    ticket_nut: int | None
    ticket_combo: int | None
    volume: str
    symbol: str
    nut_text: str

    def ticket(self) -> int | None:
        """Ticket khi **mọi nguồn đọc được đều đồng ý**, ngược lại `None`.

        Bất đồng giữa các nguồn nghĩa là hộp thoại đang ở trạng thái ta không hiểu — có thể nó
        vừa đổi vị thế giữa chừng. Không đoán: `None` sẽ thành `rejected` ở `driver.py`.
        """
        co = [t for t in (self.ticket_tieu_de, self.ticket_nut, self.ticket_combo)
              if t is not None]
        if not co or len(set(co)) != 1:
            return None
        return co[0]

    def volume_as_float(self) -> float | None:
        raw = self.volume.replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            return None


@dataclass
class _HopThoai:
    """Phần chung của hai chế độ: đọc control, đóng lại, chờ đóng."""

    hwnd: int
    controls: dict[int, win32.ControlInfo]

    def control(self, ctrl_id: int) -> win32.ControlInfo:
        try:
            return self.controls[ctrl_id]
        except KeyError:
            raise DialogError(f"Hop thoai khong co control {ctrl_id}") from None

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

    def set_volume(self, volume: float) -> bool:
        """Ghi volume bằng `WM_CHAR`. **Không** được đổi sang `WM_SETTEXT` — xem `win32.type_text`.

        Dấu chấm thập phân, luôn luôn. `read_back()` sẽ bắt được nếu máy khác nghĩ khác, nhưng
        lưu ý `read_back()` **một mình nó không đủ**: nó chỉ đọc chữ, mà chữ và giá trị MT5 dùng
        có thể khác nhau.

        Ô volume của hộp thoại ĐÓNG là **cùng ctrlID `10333`** với hộp thoại MỞ (đo 2026-09-10),
        nên bài học này áp nguyên vẹn cho cả hai chế độ, không phải học lại.
        """
        return win32.type_text(self.control(CTRL_VOLUME).hwnd, f"{volume:g}")


@dataclass
class NewOrderDialog(_HopThoai):
    """Một hộp thoại New Order đang mở."""

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
        """Hộp thoại lệnh **đang ở chế độ MỞ**.

        Loại bỏ chế độ ĐÓNG là bắt buộc, không phải cẩn thận thừa: chữ ký bốn control khớp cả hai
        chế độ, mà `open()` lại dùng lại hộp thoại đang mở sẵn. Không lọc ở đây thì một hộp thoại
        đóng người vận hành lỡ để mở sẽ được điền volume rồi bấm `'Buy by Market'`.
        """
        for hwnd, controls in _quet(pid):
            if la_che_do_dong(hwnd, controls):
                log.info("Bo qua hop thoai dang o che do DONG (hwnd=%#x)", hwnd)
                continue
            return cls(hwnd=hwnd, controls=controls)
        return None

    # -- đọc ---------------------------------------------------------------------------------

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

    def set_comment(self, comment: str) -> bool:
        return win32.type_text(self.control(CTRL_COMMENT).hwnd, comment)


@dataclass
class ClosePositionDialog(_HopThoai):
    """Một hộp thoại đang ở chế độ ĐÓNG, gắn với đúng một vị thế.

    Hộp thoại này **không có đường nào chọn vị thế**: combo `10672` liệt kê được đúng vị thế hiện
    tại và không đọc được danh sách. Nên nó không phải công cụ để *chọn* — nó là công cụ để
    **kiểm chứng** rằng cú bấm vào một dòng đã mở đúng vị thế mình cần.
    """

    @classmethod
    def find(cls, pid: int) -> ClosePositionDialog | None:
        for hwnd, controls in _quet(pid):
            if la_che_do_dong(hwnd, controls):
                return cls(hwnd=hwnd, controls=controls)
        return None

    @classmethod
    def cho_mo(cls, pid: int, timeout_sec: float = OPEN_TIMEOUT_SEC) -> ClosePositionDialog | None:
        """Chờ một hộp thoại đóng xuất hiện, hoặc `None` khi hết hạn."""
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            found = cls.find(pid)
            if found is not None:
                return found
            time.sleep(POLL_SEC)
        return None

    def close_button(self) -> win32.ControlInfo:
        """Nút `Close #...` **đang hiện**, đối chiếu cả ctrlID lẫn chữ.

        Bản ẩn cùng ctrlID mang chữ `'Close'` trần, nên chỉ tra theo ID là bấm vào nút vô hình —
        một cú bấm không đi đâu cả và không báo lỗi.
        """
        control = self.control(CTRL_CLOSE)
        # Đọc chữ **tươi** chứ không dùng bản đã cache lúc lập bản đồ control: giữa hai thời điểm
        # có một lần gõ volume vào hộp thoại, và caption của nút này nhắc lại chính con số sẽ
        # được đóng. Kiểm bằng chữ cũ là kiểm một thứ đã hết hạn.
        chu = win32.get_control_text(control.hwnd)
        if not chu.startswith(CLOSE_TEXT_PREFIX):
            raise DialogError(
                f"Nut dong (ctrlID {CTRL_CLOSE}) mang chu {chu!r}, khong bat dau bang "
                f"{CLOSE_TEXT_PREFIX!r}. Co the dang bam vao ban an."
            )
        return control

    def read_back(self) -> CloseState:
        """Đọc lại nguyên trạng, lấy ticket từ **cả ba** nguồn độc lập."""
        nut_text = win32.get_control_text(self.control(CTRL_CLOSE).hwnd)
        combo = self.controls.get(CTRL_POSITION_COMBO)
        return CloseState(
            ticket_tieu_de=doc_ticket(win32.get_window_text(self.hwnd)),
            ticket_nut=doc_ticket(nut_text),
            ticket_combo=(doc_ticket(win32.get_control_text(combo.hwnd))
                          if combo is not None else None),
            volume=win32.get_control_text(self.control(CTRL_VOLUME).hwnd),
            symbol=win32.get_control_text(self.control(CTRL_SYMBOL_EDIT).hwnd),
            nut_text=nut_text,
        )
