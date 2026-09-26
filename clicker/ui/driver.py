"""Hợp đồng của driver giao diện, bản `--dry-run`, và driver thật.

Ẩn số lớn nhất của phase này đã được trả lời bằng đo, không phải bằng suy luận (2026-09-05):
**`WM_SETTEXT` chỉ đổi chữ hiển thị, không cập nhật trạng thái nội bộ của MT5.** Lệnh gửi đi
mang volume cũ trong khi hộp thoại — và cả việc đọc lại — đều hiện giá trị mới. Tệ hơn: MT5 giữ
volume nội bộ **qua các lần mở hộp thoại**, nên hỏng kiểu này gửi đi kích thước của *lệnh trước*
chứ không phải một giá trị mặc định dễ nhận ra. Cách duy nhất chạy được là `WM_CHAR` gõ từng ký
tự, xem `win32.type_text()`.

Hệ quả cho người đọc file này về sau: **đọc lại chữ trong ô không chứng minh được gì** về giá
trị MT5 sẽ dùng. Việc đọc lại vẫn cần — nó bắt được ô sai, hộp thoại sai, symbol sai — nhưng nó
không phải bằng chứng. Bằng chứng duy nhất là deal thật.

Cái quan trọng nhất trong file này không phải code, mà là **ranh giới giữa `rejected` và
`unknown`**, và nó nằm ở hàm `commit()` của driver thật:

* `rejected` — **chứng minh được là chưa bấm nút gửi lệnh**. Trạng thái DUY NHẤT được retry.
* `unknown`  — mọi trường hợp còn lại. Không bao giờ retry.

Sau khi điền, driver phải đọc ngược Symbol / Volume / Comment / chiều từ chính hộp thoại; lệch
thì huỷ, đóng hộp thoại, trả `rejected`. Phải gom vào một hàm duy nhất sao cho **không có đường
nào tới nút gửi mà không đi qua nó** (D-24). Toàn bộ chính sách retry của Bridge dựa vào ranh
giới này, nên nó là hợp đồng chứ không phải chi tiết triển khai.

## Đường ĐÓNG, và vì sao nó là một phép TÌM chứ không phải một cú bấm

Đường MỞ biết trước mình đang điền vào đâu. Đường ĐÓNG thì không: danh sách vị thế **không đọc
được nội dung** (`LVM_GETITEMTEXT` chép 0 ký tự, MT5 tự vẽ), nên không có cách nào hỏi "vị thế
72205853 nằm ở dòng nào".

Cái bù lại nằm ở hộp thoại: mở ra rồi thì ticket đọc được từ ba nguồn độc lập. Nên `close()` là
một **phép tìm có kiểm chứng** — mở một dòng, đọc ngược ticket, sai thì huỷ và thử dòng khác, đúng
mới điền volume và bấm. Dòng nào mở trước do `clicker/ui/timdong.py` chọn (bản đồ ticket → dòng, rồi
tìm nhị phân); nó chỉ đổi thứ tự, không đổi việc mọi dòng đều bị kiểm chứng.

Điều làm phép tìm này an toàn: **mở và huỷ hộp thoại không đặt lệnh nào.** Mọi bước dò đều nằm ở
phía an toàn của ranh giới D-24, nên một lần dò trượt vẫn là `rejected` đúng nghĩa. Đây không phải
đoán rồi sửa sau — không có "sau".

## Đường MỞ cũng là một phép tìm, từ khi copy nhiều symbol (D-44)

Hộp thoại mở bằng lệnh menu lấy symbol theo **chart đang active**, nên trước đây mỗi terminal Client
chỉ copy được một symbol (B-01). Nay hộp thoại được mở bằng cách nhấp đúp **dòng Market Watch** của
symbol cần mở — cùng kiểu tìm có kiểm chứng như đường đóng, chỉ khác là đọc symbol thay cho ticket.
Xem `clicker/ui/marketwatch.py`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from bridge.logging_setup import get_logger
from clicker.ui import marketwatch, probe, timdong, tradetab, win32
from clicker.ui.dialog import (
    ClosePositionDialog,
    DialogError,
    HopThoaiDongSoBo,
    NewOrderDialog,
    cho_so_bo,
    ten_symbol,
    tim_so_bo,
)
from clicker.ui.marketwatch import MarketWatchError

log = get_logger(__name__)


@dataclass(frozen=True)
class OpenRequest:
    """Nội dung một lệnh `OPEN_UI`. Không có `magic` — giao diện không đặt được (D-22)."""

    symbol: str
    direction: str
    volume: float
    comment: str
    deviation: int | None = None

    @classmethod
    def from_payload(cls, payload: dict) -> OpenRequest:
        """Đọc payload từ Bridge. Thiếu trường nào cũng là lỗi, không có mặc định."""
        thieu = [name for name in ("symbol", "direction", "volume")
                 if payload.get(name) in (None, "")]
        if thieu:
            raise ValueError(f"Payload OPEN_UI thieu {', '.join(thieu)}")
        if "magic" in payload:
            # Nhận được `magic` nghĩa là đang cầm một payload của đường EA. Từ chối ngay.
            raise ValueError("Payload OPEN_UI khong duoc mang magic")
        if payload["direction"] not in ("BUY", "SELL"):
            raise ValueError(f"Chieu khong hop le: {payload['direction']!r}")
        volume = float(payload["volume"])
        if volume <= 0:
            raise ValueError(f"Volume phai duong, nhan duoc {volume}")
        return cls(symbol=str(payload["symbol"]), direction=payload["direction"],
                   volume=volume, comment=str(payload.get("comment") or ""),
                   deviation=payload.get("deviation"))


@dataclass(frozen=True)
class CloseRequest:
    """Nội dung một lệnh `CLOSE_UI` / `CLOSE_UI_PARTIAL`.

    `volume = None` nghĩa là **đóng hẳn**: giữ nguyên volume hộp thoại đã điền sẵn thay vì tự gõ
    lại con số của mình. Bridge và terminal có thể bất đồng về volume còn lại của một vị thế
    (một lần đóng bớt vừa khớp mà event chưa về chẳng hạn), và trong tình huống đó thứ đúng là
    thứ terminal đang giữ, không phải thứ sổ sách nghĩ.
    """

    position_id: int
    volume: float | None = None

    #: Loại command đóng hẳn, và loại đóng một phần. Hai loại riêng chứ không phải một loại với
    #: `volume` tuỳ chọn, vì chúng phải **mâu thuẫn ồn ào** khi payload sai — xem `from_payload`.
    LOAI_DONG_HAN = "CLOSE_UI"
    LOAI_DONG_BOT = "CLOSE_UI_PARTIAL"

    @classmethod
    def from_payload(cls, payload: dict, command_type: str) -> CloseRequest:
        """Đọc payload, và **bắt loại command khớp với payload**.

        Chỗ này đáng một đoạn giải thích vì nó chặn một lỗi mất tiền im lặng: một
        `CLOSE_UI_PARTIAL` rơi mất trường `volume` mà vẫn được chấp nhận sẽ thành **đóng hẳn**.
        Không có gì trong hộp thoại báo động — nó chỉ đóng nhiều hơn phần đáng lẽ phải đóng, và
        sổ sách thì tin là đã đóng đúng một phần.

        Nên hai loại phải soi lẫn nhau: `CLOSE_UI` mà **có** `volume` cũng bị từ chối, vì nó nghĩa
        là bên gọi đang nghĩ một đằng còn loại command nói một nẻo.
        """
        if command_type not in (cls.LOAI_DONG_HAN, cls.LOAI_DONG_BOT):
            raise ValueError(f"Loai command khong phai lenh dong: {command_type!r}")
        if payload.get("position_id") in (None, ""):
            raise ValueError(f"Payload {command_type} thieu position_id")
        if "magic" in payload:
            # Cùng lý do với `OpenRequest`: có `magic` nghĩa là đang cầm payload của đường EA.
            raise ValueError(f"Payload {command_type} khong duoc mang magic")
        position_id = int(payload["position_id"])
        if position_id <= 0:
            raise ValueError(f"position_id phai duong, nhan duoc {position_id}")

        volume = payload.get("volume")
        if command_type == cls.LOAI_DONG_HAN:
            if volume is not None:
                raise ValueError(f"{cls.LOAI_DONG_HAN} khong duoc mang volume "
                                 f"(nhan duoc {volume}); dong mot phan phai dung "
                                 f"{cls.LOAI_DONG_BOT}")
            return cls(position_id=position_id, volume=None)

        if volume is None:
            raise ValueError(f"{cls.LOAI_DONG_BOT} thieu volume")
        volume = float(volume)
        if volume <= 0:
            raise ValueError(f"Volume phai duong, nhan duoc {volume}")
        return cls(position_id=position_id, volume=volume)


@dataclass(frozen=True)
class Outcome:
    """Kết quả một lần thao tác, theo đúng bốn trạng thái của hợp đồng ack (plan 6b mục 6b.3)."""

    status: str
    reason: str
    #: `True` chỉ khi driver **biết chắc** đã bấm nút gửi. `None` nghĩa là không biết.
    clicked: bool | None = None

    #: `already_closed` chỉ dùng được ở đường ĐÓNG, và nó có nghĩa hẹp: **đã quét hết danh sách
    #: vị thế và không có vị thế đó**. Đây là kết quả bình thường chứ không phải lỗi (FR-18), và
    #: nó khớp đúng ngữ nghĩa mà EA trả khi `PositionSelectByTicket` thất bại.
    HOP_LE = ("ok", "failed", "already_closed", "rejected", "unknown")

    def __post_init__(self) -> None:
        if self.status not in self.HOP_LE:
            raise ValueError(f"Trang thai khong hop le: {self.status!r}")


#: Tên cũ, giữ lại vì nó xuất hiện trong test và trong log của các phase trước.
OpenOutcome = Outcome


class UiDriver(Protocol):
    """Thứ duy nhất clicker cần biết về giao diện."""

    def open(self, request: OpenRequest) -> Outcome:
        ...

    def close(self, request: CloseRequest) -> Outcome:
        ...

    def dry_probe(self) -> Outcome:
        """Probe khô: mở hộp thoại, đọc lại các field, bấm ESC. Không đặt lệnh nào."""
        ...


#: Tên cũ của `UiDriver`, từ khi driver mới chỉ biết mở lệnh.
OpenDriver = UiDriver


class DryRunDriver:
    """Driver không chạm vào giao diện. Luôn trả `rejected` với lý do `DRY_RUN`.

    `rejected` là lựa chọn đúng chứ không phải cho tiện: nó có nghĩa chính xác là *"chứng minh
    được là chưa bấm nút gửi lệnh"*, và ở chế độ này thì đúng là chưa có gì được bấm. Trả
    `unknown` sẽ khiến Bridge treo cặp lệnh chờ đối chiếu một cách vô cớ.
    """

    #: Lý do được ghi vào `retmsg` để nhìn thấy được ở dashboard và trong DB.
    REASON = "DRY_RUN"

    def __init__(self) -> None:
        #: Các yêu cầu đã nhận, để test và để đọc log khi chạy thử.
        self.seen: list[OpenRequest | CloseRequest] = []

    def open(self, request: OpenRequest) -> Outcome:
        self.seen.append(request)
        return Outcome(
            "rejected",
            f"{self.REASON}: che do chay thu, khong cham vao giao dien "
            f"({request.direction} {request.volume} {request.symbol})",
            clicked=False,
        )

    def close(self, request: CloseRequest) -> Outcome:
        self.seen.append(request)
        phan = "toan bo" if request.volume is None else f"{request.volume:g}"
        return Outcome(
            "rejected",
            f"{self.REASON}: che do chay thu, khong cham vao giao dien "
            f"(dong {phan} cua vi the {request.position_id})",
            clicked=False,
        )

    def dry_probe(self) -> Outcome:
        return Outcome("rejected", f"{self.REASON}: khong chay probe kho", clicked=False)


class Mt5UiDriver:
    """Driver thật: điền hộp thoại của MT5 rồi bấm.

    Trình tự đường MỞ **được đo chứ không suy ra** (2026-09-05, Connext-Demo, build 5.00):
    10/10 lệnh cho ra deal đúng volume, đúng chiều, comment nguyên vẹn, `DEAL_REASON = CLIENT`.
    Lặp lại 5/5 với cửa sổ minimized.

    Đường sống của cả lớp này là **thứ tự**: mọi thứ có thể hỏng đều phải hỏng **trước** cú bấm,
    vì trước cú bấm thì `rejected` là sự thật chứng minh được, còn sau cú bấm thì không còn gì
    chứng minh được nữa.
    """

    #: Chờ hộp thoại đóng hiện ra sau một cú bấm vào dòng. Đo được 200–300 ms, nên 2 giây là dư
    #: gấp nhiều lần. Phải nhỏ vì **mỗi dòng không phải vị thế sẽ tiêu đúng ngần này** — danh sách
    #: có cả dòng tổng kết Balance, và nó không mở hộp thoại nào.
    PROBE_CLOSE_SEC = 2.0
    #: Số lần nhấp lại một dòng khi cú double-click **bị treo hết hạn** mà không mở hộp thoại nào
    #: (xem `_mo_dong`). Một lần là đủ theo đo đạc; nhiều hơn chỉ kéo dài phép dò khi terminal treo
    #: thật, mà lúc đó Bridge còn đường rơi về EA.
    NHAP_LAI_KHI_TREO = 1
    #: Chờ hộp thoại sau một cú nhấp **bị treo** trước khi nhấp lại.
    #:
    #: Đo trên VPS 2026-09-12, 6/6 lần đóng: cú nhấp treo **không bao giờ** mở hộp thoại, kể cả khi
    #: chờ thêm 3 giây; cú nhấp lại thì mở. Nên khoảng chờ này chỉ để chắc chắn, không phải để hy
    #: vọng — giữ ngắn, vì nó cộng vào **mỗi** lệnh đóng.
    CHO_SAU_KHI_TREO_SEC = 0.15
    #: Chờ hộp thoại khi cú nhấp **không** bị treo (message trả lời ngay). Đo trên VPS 2026-09-16/17:
    #: hộp thoại thật luôn hiện trong 0,20–0,38 s; dòng không ra hộp thoại (dòng Balance, hoặc dòng
    #: của vị thế vừa đóng mà MT5 chưa kịp xoá) tốn trọn khoảng chờ này. Log thật: 5 lần chờ vô ích
    #: 2,09–2,12 s khi còn `PROBE_CLOSE_SEC` cho mọi dòng. Hộp thoại mở muộn hơn khoảng này vẫn bị bắt
    #: ở vòng dò kế tiếp như hộp thoại sót — phép tìm thành bẩn, không kết luận sai.
    CHO_KHONG_TREO_SEC = 1.0
    #: Sau khi đóng hẳn: chờ tối đa ngần này cho MT5 xoá dòng của vị thế vừa đóng khỏi danh sách.
    #: Đo VPS: đóng liên tiếp cách nhau ~0,8 s thì lệnh sau dò trúng dòng "xác chết" chưa bị xoá.
    CHO_XOA_DONG_SEC = 0.8
    #: Trần cho số dòng cuối danh sách được học là "không phải vị thế" (xem `_so_dong_cuoi_khong_mo`).
    #: Đo VPS 2026-09-17: tab Trade có **hai** dòng như vậy (một dòng phụ rồi dòng Balance).
    TRAN_DONG_CUOI = 3

    def __init__(self, terminal_title: str,
                 on_before_click: Callable[[], None] | None = None,
                 settle_sec: float = 0.05, close_timeout_sec: float = 5.0,
                 account_login: int = 0) -> None:
        self.terminal_title = terminal_title
        #: Số tài khoản Bridge giao (D-32). Mỗi lần mở/đóng đều đối chiếu nó với số đọc từ tiêu đề
        #: cửa sổ **đang tồn tại**, chứ không tin một lần kiểm lúc bắt tay: giữa hai nhịp heartbeat
        #: vẫn đủ chỗ cho một terminal đăng nhập sang tài khoản khác, và cú bấm thì không lấy lại được.
        self.account_login = account_login
        #: Gọi ngay TRƯỚC cú bấm. `link.py` dùng nó để ghi "đã bấm" xuống đĩa trước khi bấm —
        #: nếu mất điện đúng lúc này, lần khởi động lại phải giả định là đã bấm.
        self.on_before_click = on_before_click
        self.settle_sec = settle_sec
        self.close_timeout_sec = close_timeout_sec
        #: `ticket → dòng` đọc được từ những lần dò trước. Chỉ là **thứ tự dò**, không phải kết
        #: luận — xem `clicker/ui/timdong.py`.
        self._ban_do: dict[int, int] = {}
        #: Số dòng cuối danh sách đã **thấy** không ra hộp thoại (dòng phụ + dòng Balance). Học dần:
        #: đo VPS 2026-09-17 cho thấy dò hỏng luôn rơi vào dòng `so_dong - 2` — mọi lần đóng vị thế
        #: cuối cùng, phép nhị phân chọn đúng dòng phụ đó làm điểm giữa và mất ~1,1 s. Chỉ ảnh hưởng
        #: thứ tự dò, không ảnh hưởng kiểm chứng.
        self._so_dong_cuoi_khong_mo = 1
        #: `symbol → dòng` Market Watch đọc được từ những lần mở trước. Cũng chỉ là **thứ tự dò**:
        #: dòng gợi ý vẫn bị đọc symbol trong hộp thoại trước khi dùng. Bỏ hết khi số dòng đổi —
        #: người dùng vừa thêm hoặc bớt symbol.
        self._mw_ban_do: dict[str, int] = {}
        self._mw_so_dong: int | None = None

    # -- mở lệnh ---------------------------------------------------------------------------

    def open(self, request: OpenRequest) -> Outcome:
        # Mốc thời gian từng bước — để đo trên VPS bằng log chứ không đoán (bài học B-15). Vào lệnh
        # liên tục cách nhau ~3 giây, mà đường mở trước đây không có dòng log thời gian nào.
        self._moc = {"bat_dau": time.monotonic()}
        health = probe.probe(self.terminal_title, self.account_login)
        if not health or health.hwnd is None:
            return Outcome("rejected", f"Canary do: {health.detail}", clicked=False)
        self._moc["probe"] = time.monotonic()
        try:
            dialog = self._mo_new_order(health.hwnd, request.symbol)
        except (DialogError, MarketWatchError) as exc:
            return Outcome("rejected", f"Khong mo duoc hop thoai: {exc}", clicked=False)
        self._moc["mo"] = time.monotonic()
        return self._commit(dialog, request)

    def _mo_new_order(self, terminal_hwnd: int, symbol: str) -> NewOrderDialog:
        """Hộp thoại New Order **đang ở đúng `symbol`**, mở qua Market Watch (D-44).

        Phép tìm có kiểm chứng: nhấp đúp một dòng, đọc symbol trong hộp thoại, sai thì huỷ và thử
        dòng khác. Chưa có gì được điền, nên mọi lối ra bằng ngoại lệ ở đây đều là `rejected` thật.
        """
        pid = win32.get_process_id(terminal_hwnd)

        # Hộp thoại mở sẵn (người vận hành để lại, hoặc lần trước chưa kịp đóng). Đúng symbol thì
        # dùng luôn như trước; sai thì đóng đi rồi mở qua Market Watch thay vì từ chối.
        san = NewOrderDialog.cho(pid, 0)
        if san is not None:
            dang = self._doc_symbol(san)
            if dang == symbol:
                log.info("Hop thoai New Order da mo san o %s, dung lai", symbol)
                return san
            log.info("Hop thoai New Order mo san o %r, dong de mo %s qua Market Watch", dang, symbol)
            san.cancel()
            if not san.wait_closed():
                raise DialogError("Hop thoai New Order mo san khong dong duoc")

        danh_sach = marketwatch.tim_danh_sach(terminal_hwnd)
        so_dong = marketwatch.so_dong(danh_sach)
        if not so_dong:
            raise MarketWatchError(f"Market Watch khong tra loi so dong ({so_dong!r})")
        if so_dong != self._mw_so_dong:
            self._mw_ban_do.clear()
            self._mw_so_dong = so_dong

        da_thu: list[str] = []
        for row in marketwatch.thu_tu_do(so_dong, symbol, self._mw_ban_do):
            if not marketwatch.mo_new_order(danh_sach, row):
                da_thu.append(f"{row}:?")
                continue
            dialog = NewOrderDialog.cho(pid, marketwatch.CHO_HOP_THOAI_SEC)
            if dialog is None:
                # Dòng "click to add" (hoặc nhấp không tới): không có hộp thoại, có thể có ô gõ.
                marketwatch.dong_o_them_symbol(danh_sach)
                marketwatch.ghi_ban_do(self._mw_ban_do, row, None)
                da_thu.append(f"{row}:-")
                continue
            thay = self._doc_symbol(dialog)
            marketwatch.ghi_ban_do(self._mw_ban_do, row, thay)
            if thay == symbol:
                log.info("Market Watch: %s o dong %d/%d, %d lan mo", symbol, row, so_dong,
                         len(da_thu) + 1)
                return dialog
            da_thu.append(f"{row}:{thay}")
            dialog.cancel()
            if not dialog.wait_closed():
                raise DialogError(f"Hop thoai {thay} khong dong sau khi huy")
        raise MarketWatchError(
            f"Khong dong Market Watch nao mo ra {symbol} (da thu {', '.join(da_thu)}). "
            "Symbol nay co trong Market Watch cua Client khong?")

    @staticmethod
    def _doc_symbol(dialog: NewOrderDialog) -> str:
        """Symbol hộp thoại đang hiện. Đọc hỏng thì đóng hộp thoại trước khi ném lỗi lên."""
        try:
            return ten_symbol(dialog.read_back().symbol)
        except DialogError:
            dialog.cancel()
            dialog.wait_closed()
            raise

    def _log_thoi_gian_mo(self) -> None:
        m = getattr(self, "_moc", {})
        moc = [m.get(k) for k in ("bat_dau", "probe", "mo", "dien", "doc_lai", "bam", "dong")]
        if any(v is None for v in moc):
            return
        buoc = [moc[i + 1] - moc[i] for i in range(len(moc) - 1)]
        log.info("Mo lenh: probe %.2f | mo hop thoai %.2f | dien %.2f | doc lai %.2f | "
                 "bam %.2f | cho dong sau bam %.2f | tong %.2f", *buoc, moc[-1] - moc[0])

    def _commit(self, dialog: NewOrderDialog, request: OpenRequest) -> Outcome:
        """Điền, **đọc lại**, so, rồi mới bấm. Không có đường nào tới nút gửi mà vòng qua đây."""
        def bo_cuoc(ly_do: str) -> Outcome:
            dialog.cancel()
            dialog.wait_closed()
            return Outcome("rejected", ly_do, clicked=False)

        try:
            # Chốt cuối: `_mo_new_order` đã chọn đúng dòng Market Watch, nhưng giữa lúc đó và cú bấm
            # vẫn phải đọc lại. Sai thì từ chối — không bao giờ tự đổi symbol trong hộp thoại.
            hien_tai = ten_symbol(dialog.read_back().symbol)
            if hien_tai != request.symbol:
                return bo_cuoc(f"Hop thoai dang o symbol {hien_tai!r}, "
                               f"khong phai {request.symbol!r}")

            dialog.set_volume(request.volume)
            dialog.set_comment(request.comment)
            time.sleep(self.settle_sec)
            self._moc_dat("dien")

            doc_lai = dialog.read_back()
            lech = []
            if doc_lai.volume_as_float() != request.volume:
                lech.append(f"volume {doc_lai.volume!r} thay vi {request.volume}")
            if doc_lai.comment != request.comment:
                lech.append(f"comment {doc_lai.comment!r} thay vi {request.comment!r}")
            if lech:
                return bo_cuoc("Doc lai lech: " + "; ".join(lech))

            # Ném `DialogError` nếu nút không đúng — vẫn còn ở phía an toàn của cú bấm.
            button = dialog.button(request.direction)
        except DialogError as exc:
            return bo_cuoc(f"Hop thoai khong dung hinh dang: {exc}")
        self._moc_dat("doc_lai")

        # ==== TỪ ĐÂY TRỞ ĐI KHÔNG CÒN ĐƯỜNG LÙI ====
        if self.on_before_click is not None:
            self.on_before_click()
        if not win32.post_click(button.hwnd):
            # `PostMessage` chỉ xếp message vào hàng đợi. Thất bại ở đây gần như chắc chắn là
            # chưa bấm, nhưng "gần như chắc chắn" không đủ để cho phép thử lại.
            return Outcome("unknown", "PostMessage that bai, khong ro da bam hay chua")
        self._moc_dat("bam")

        dong = dialog.wait_closed(self.close_timeout_sec)
        self._moc_dat("dong")
        self._log_thoi_gian_mo()
        if not dong:
            return Outcome("unknown", "Hop thoai khong dong sau khi bam", clicked=True)
        return Outcome("ok", f"{request.direction} {request.volume:g} {request.symbol}",
                       clicked=True)

    def _moc_dat(self, ten: str) -> None:
        moc = getattr(self, "_moc", None)
        if moc is not None:
            moc[ten] = time.monotonic()

    # -- đóng lệnh -------------------------------------------------------------------------

    def close(self, request: CloseRequest) -> Outcome:
        """Tìm đúng vị thế trong danh sách rồi đóng nó. Xem phần đầu file về vì sao là phép tìm."""
        health = probe.probe(self.terminal_title, self.account_login)
        if not health or health.hwnd is None:
            return Outcome("rejected", f"Canary do: {health.detail}", clicked=False)
        pid = win32.get_process_id(health.hwnd)

        bat_dau = time.monotonic()
        try:
            list_hwnd = tradetab.tim_danh_sach(health.hwnd)
        except tradetab.TradeTabError as exc:
            return Outcome("rejected", str(exc), clicked=False)
        log.info("Tim danh sach Trade: %.2fs", time.monotonic() - bat_dau)

        # Hộp thoại còn sót — từ lần trước, hoặc do người vận hành mở. Phải huỷ: MT5 đang ở vòng
        # lặp modal thì cú double-click kế tiếp không đi tới đâu cả.
        con_lai = ClosePositionDialog.find(pid)
        if con_lai is not None:
            con_lai.cancel()
            con_lai.wait_closed()

        so_dong = tradetab.so_dong(list_hwnd)
        if so_dong is None:
            return Outcome("rejected", "Danh sach vi the khong tra loi", clicked=False)
        if so_dong == 0:
            return Outcome("rejected", "Danh sach vi the rong", clicked=False)

        da_gap: list[int | None] = []
        mo_duoc_it_nhat_mot = False
        #: Lý do khiến "đã quét hết" không còn đáng tin: một lần dò bị treo, một hộp thoại sót, một
        #: ticket hiện ở hai dòng. Tìm bẩn mà không thấy thì KHÔNG được nói `already_closed` — kết
        #: luận đó làm Bridge ghi cặp thành `CLOSED` trong khi vị thế có thể vẫn đang mở.
        tim_ban: list[str] = []
        #: ticket → dòng nơi nó được đọc trong **lần tìm này**.
        thay_o: dict[int, int] = {}
        # Chỉ quyết định THỨ TỰ mở dòng — mọi dòng vẫn bị đọc ngược ticket bên dưới (D-30).
        phep_do = timdong.PhepDo(so_dong, request.position_id, self._ban_do,
                                 bo_cuoi=self._so_dong_cuoi_khong_mo)
        while (row := phep_do.tiep_theo()) is not None:
            # Hộp thoại sót lại từ vòng trước — kể cả một cái mở **chậm hơn** thời gian chờ. MT5
            # lúc đó đang ở vòng lặp modal và cú double-click kế tiếp sẽ không đi tới đâu cả, nên
            # bỏ qua bước này là để cả phần còn lại của vòng lặp dò trong vô vọng.
            sot = tim_so_bo(pid)
            if sot is not None:
                # Ghi lại TRƯỚC khi huỷ. Một hộp thoại sót là hộp thoại mở trễ của một dòng nào đó,
                # và nếu nó là đích thì dòng của đích có thể đã bị ghi nhận với ticket khác.
                tim_ban.append(f"hop thoai sot #{sot.ticket} (hwnd {sot.hwnd:#x})")
                sot.cancel()
                sot.wait_closed()

            so_bo = self._mo_dong(pid, list_hwnd, row)
            if self._vua_treo:
                tim_ban.append(f"dong {row} bi treo")
                # Message của lần dò treo vẫn được MT5 giao **muộn**. Không mở dòng kế khi chúng
                # chưa chạy xong — hộp thoại sau có thể nhận nhầm cú nhấp của dòng trước.
                if not win32.cho_xu_ly_xong(list_hwnd):
                    if so_bo is not None:
                        so_bo.cancel()
                        so_bo.wait_closed()
                    return Outcome("rejected", f"MT5 khong xu ly xong hang doi sau lan do treo "
                                               f"o dong {row}", clicked=False)
            ticket = so_bo.ticket if so_bo is not None else None
            if so_bo is not None:
                log.info("Dong %d mo hop thoai #%s (hwnd %#x)", row, ticket, so_bo.hwnd)

            if so_bo is not None and ticket is not None and thay_o.get(ticket, row) != row:
                # Cùng một ticket ở hai dòng: một trong hai lần đọc là hộp thoại MỞ TRỄ của dòng
                # khác. Không tin lần nào — cho mở lại cả hai, không ghi bản đồ.
                dong_cu = thay_o.pop(ticket)
                tim_ban.append(f"ticket #{ticket} hien o ca dong {dong_cu} va dong {row}")
                self._ban_do.pop(ticket, None)
                so_bo.cancel()
                so_bo.wait_closed()
                phep_do.ghi_nhan(row, None)
                phep_do.mo_lai(row)
                phep_do.mo_lai(dong_cu)
                continue

            phep_do.ghi_nhan(row, ticket)
            if ticket is not None:
                thay_o[ticket] = row
            timdong.ghi_ban_do(self._ban_do, row, ticket)
            if so_bo is None:
                # Dòng này không mở hộp thoại nào. Bình thường: danh sách có dòng phụ và dòng tổng
                # kết Balance ở cuối. Đi tiếp chứ không coi là lỗi — và nhớ lại nếu nó nằm ở đuôi,
                # để lần sau phép nhị phân không lấy nó làm điểm giữa.
                if not self._vua_treo:
                    self._hoc_dong_cuoi(so_dong, row)
                continue
            mo_duoc_it_nhat_mot = True
            da_gap.append(so_bo.ticket)
            if so_bo.ticket != request.position_id:
                # Loại bằng đúng một lần đọc tiêu đề, **không** đọc 55 control của hộp thoại này.
                so_bo.cancel()
                so_bo.wait_closed()
                continue

            self._log_tim(request.position_id, phep_do)
            doc_tu = time.monotonic()
            hop = ClosePositionDialog.tu_hwnd(so_bo.hwnd)
            log.info("Doc control hop thoai dong (dong %d): %.2fs", row,
                     time.monotonic() - doc_tu)
            if hop is None:
                so_bo.cancel()
                so_bo.wait_closed()
                return Outcome("rejected", "Hop thoai dong khong dung hinh dang", clicked=False)
            ket_qua = self._commit_close(hop, request, list_hwnd)
            if ket_qua.status == "ok" and request.volume is None:
                # Đóng hẳn: MT5 bỏ dòng này, mọi dòng bên dưới dịch lên một. Đóng một phần thì
                # dòng còn nguyên chỗ.
                timdong.bo_dong(self._ban_do, request.position_id, row)
                self._cho_xoa_dong(list_hwnd, so_dong)
            elif ket_qua.status != "ok":
                # `unknown` / `rejected`: không biết danh sách giờ ra sao. Bỏ mục của vị thế này
                # thay vì giữ một gợi ý có thể đã sai.
                self._ban_do.pop(request.position_id, None)
            return ket_qua

        self._log_tim(request.position_id, phep_do)
        self._ban_do.pop(request.position_id, None)
        if not mo_duoc_it_nhat_mot:
            # **Không một dòng nào mở được hộp thoại.** Không được kết luận "vị thế đã đóng" từ
            # đây: nó cũng là hình dạng của một giao diện đã ngừng điều khiển được — hộp thoại
            # kẹt, terminal treo, danh sách đổi hình dạng trên bản MT5 khác.
            #
            # Phân biệt này quan trọng vì hai kết luận đi về hai hướng ngược nhau:
            # `already_closed` làm Bridge ghi cặp thành `CLOSED` — nếu sai thì sổ sách nói vị thế
            # đã đóng trong khi nó vẫn đang mở và vẫn đang lỗ. `rejected` thì chứng minh được là
            # chưa bấm gì, nên Bridge còn đường rơi về EA.
            return Outcome(
                "rejected",
                f"Khong dong nao trong {so_dong} dong mo duoc hop thoai — khong ket luan duoc "
                f"vi the {request.position_id} con hay het",
                clicked=False,
            )

        if tim_ban:
            # Không thấy, nhưng phép tìm không sạch: có lần đọc có thể thuộc về dòng khác.
            # `already_closed` ở đây có thể là nói sai — và Bridge sẽ ghi cặp `CLOSED` trong khi vị
            # thế vẫn đang mở. `rejected` thì đúng (chưa bấm gì), Bridge rơi về EA, và EA đóng
            # theo đúng ticket, trả `already_closed` thật nếu vị thế đã đóng.
            return Outcome(
                "rejected",
                f"Quet {so_dong} dong khong thay vi the {request.position_id}, nhung phep tim "
                f"khong sach ({'; '.join(tim_ban)}) — khong ket luan da dong",
                clicked=False,
            )

        # Đã quét **hết** danh sách, ít nhất một dòng mở được hộp thoại (nên cơ chế dò đang chạy),
        # và không có vị thế đó. `LVM_GETITEMCOUNT` đếm mọi dòng bất kể cuộn tới đâu, và
        # `tim_danh_sach` đã bắt buộc đúng danh sách của tab Trade — nên đây không phải "tìm chưa
        # kỹ", mà là vị thế **không còn mở trên terminal này**.
        #
        # Trả `rejected` ở đây sẽ khiến Bridge cho cặp sang `ORPHANED` kèm alert CRITICAL, tức là
        # báo động cho đúng thứ đáng lẽ phải xảy ra: vị thế đã đóng rồi. `already_closed` là kết
        # quả bình thường của việc hai bên cùng đóng gần như đồng thời (FR-18).
        return Outcome(
            "already_closed",
            f"Khong con vi the {request.position_id} trong {so_dong} dong (gap: {da_gap})",
            clicked=False,
        )

    def _cho_xoa_dong(self, list_hwnd: int, so_dong_truoc: int) -> None:
        """Chờ MT5 xoá dòng của vị thế vừa đóng hẳn, để lệnh kế tiếp không dò trúng dòng đó.

        Không phải điều kiện đúng/sai: hết hạn thì chỉ log và đi tiếp. Dòng "xác chết" nếu còn thì
        phép dò sau vẫn bỏ qua đúng (không ra hộp thoại), chỉ tốn thêm `CHO_KHONG_TREO_SEC`.
        """
        bat_dau = time.monotonic()
        het = bat_dau + self.CHO_XOA_DONG_SEC
        while time.monotonic() < het:
            hien = tradetab.so_dong(list_hwnd)
            if hien is None or hien < so_dong_truoc:
                break
            time.sleep(0.03)
        log.info("Cho MT5 xoa dong vua dong: %.2fs", time.monotonic() - bat_dau)

    @staticmethod
    def _log_tim(position_id: int, phep_do: timdong.PhepDo) -> None:
        """Một dòng log mỗi lần tìm — để đo trên VPS bằng log, không bằng đoán (bài học B-15)."""
        log.info("Tim vi the %s: %d lan mo / %d dong (%s)", position_id, phep_do.so_lan_mo,
                 phep_do.so_dong, phep_do.che_do)

    def _so_bo_du_phong(self, pid: int) -> HopThoaiDongSoBo | None:
        """Đường dự phòng khi tiêu đề không nhận ra được: quét đầy đủ control **một lần**.

        Tiêu đề `Position: #<ticket>` đo được trên Connext-Demo, nhưng nó là chuỗi của MT5 chứ không
        phải hợp đồng. Sàn khác đặt tiêu đề khác thì phép dò nhanh mù hẳn — và mù ở đây nghĩa là
        `rejected`, tức mất đường đóng qua giao diện mà không ai hiểu vì sao.
        """
        day_du = ClosePositionDialog.find(pid)
        if day_du is None:
            return None
        try:
            ticket = day_du.read_back().ticket()
        except DialogError:
            ticket = None
        return HopThoaiDongSoBo(hwnd=day_du.hwnd, ticket=ticket)

    def _mo_dong(self, pid: int, list_hwnd: int, row: int) -> HopThoaiDongSoBo | None:
        """Mở hộp thoại đóng cho một dòng, **nhấp lại một lần** nếu cú nhấp đầu bị treo.

        Đo trên VPS ngày 2026-09-11 (Connext-Demo): thỉnh thoảng cú double-click làm
        `SendMessageTimeout` **chặn đúng hết hạn 2 giây** mà không có hộp thoại nào; nhấp lại ngay
        thì mở trong khoảng 0,4 giây. Lần đóng thật đầu tiên trên VPS hỏng đúng kiểu đó — dò hết
        danh sách không mở được gì, trả `rejected`, Bridge rơi về EA và deal đóng mang `EXPERT`.
        Laptop chưa từng gặp. Chưa tìm ra cơ chế: đã loại trừ focus, MT5 nghỉ lâu, bước chọn dòng.

        Chỉ nhấp lại khi **message bị treo** (`mo_hop_thoai_dong` trả `False`). Dòng tổng kết Balance
        trả `True` ngay mà không mở gì — nhấp lại nó chỉ tốn thời gian. Nhấp lại là an toàn: mở rồi
        huỷ hộp thoại không đặt lệnh nào (D-30).

        Không coi giá trị trả về là bằng chứng: `SendMessage` của cú double-click mở một hộp thoại
        **modal**, nên nó có thể hết hạn trong khi hộp thoại vẫn mở ra. Bằng chứng duy nhất là hộp
        thoại có xuất hiện hay không — giá trị trả về chỉ quyết định **có đáng nhấp lại** không.
        """
        so_lan = 1 + self.NHAP_LAI_KHI_TREO
        #: Có cú nhấp nào của dòng này bị treo không. `close()` đọc cờ này: message của một cú nhấp
        #: treo vẫn được MT5 giao muộn, nên phép tìm sau đó không còn "sạch" (xem `close`).
        self._vua_treo = False
        for lan in range(1, so_lan + 1):
            if lan > 1:
                sot = tim_so_bo(pid)
                if sot is not None:
                    sot.cancel()
                    sot.wait_closed()
            bat_dau = time.monotonic()
            # Lần đầu dùng cách gửi không treo; lần nhấp lại dùng đường cũ đã đo kỹ. Hai cơ chế
            # khác nhau, nên một cái hỏng trên bản MT5 lạ thì cái kia vẫn còn.
            gui = tradetab.mo_hop_thoai_dong(list_hwnd, row, nhanh=(lan == 1))
            if not gui:
                self._vua_treo = True
            if not gui:
                cho = self.CHO_SAU_KHI_TREO_SEC if lan < so_lan else self.PROBE_CLOSE_SEC
            else:
                cho = self.CHO_KHONG_TREO_SEC
            so_bo = cho_so_bo(pid, cho) or self._so_bo_du_phong(pid)
            log.info("Do dong %d lan %d: gui=%s, hop thoai %s sau %.2fs", row, lan, gui,
                     "MO" if so_bo is not None else "KHONG mo", time.monotonic() - bat_dau)
            if so_bo is not None or gui:
                return so_bo
        return None

    def _hoc_dong_cuoi(self, so_dong: int, row: int) -> None:
        tu_cuoi = so_dong - row
        if self._so_dong_cuoi_khong_mo < tu_cuoi <= self.TRAN_DONG_CUOI:
            self._so_dong_cuoi_khong_mo = tu_cuoi
            log.info("Hoc: %d dong cuoi danh sach khong phai vi the (dong %d/%d khong ra hop thoai)",
                     tu_cuoi, row, so_dong)

    def _commit_close(self, hop: ClosePositionDialog, request: CloseRequest,
                      list_hwnd: int | None = None) -> Outcome:
        """Điền volume, xả hàng đợi của MT5, **đọc lại ticket và volume từ mọi nguồn**, rồi mới bấm.

        Kiểm ticket **lần thứ hai** ở đây chứ không tin lần kiểm lúc tìm: giữa hai thời điểm có
        một lần gõ phím vào hộp thoại, và thứ đắt nhất có thể xảy ra là đóng nhầm vị thế.

        Và kiểm **sau khi xả hàng đợi** (bổ sung 2026-09-15). `BM_CLICK` là message post: nó chỉ
        chạy khi luồng giao diện MT5 tới lượt, tức là **sau** mọi message còn tồn — kể cả
        `SendMessageTimeout` đã hết hạn của một lần dò trước, vốn vẫn được giao muộn. Kiểm ticket
        trong lúc những thứ đó chưa chạy là kiểm một trạng thái có thể đổi ngay trước cú bấm.
        `win32.cho_xu_ly_xong` thu hẹp khe hở đó, không đóng được hẳn — xem giới hạn ở đó.
        """
        def bo_cuoc(ly_do: str) -> Outcome:
            hop.cancel()
            hop.wait_closed()
            return Outcome("rejected", ly_do, clicked=False)

        try:
            if request.volume is not None:
                hop.set_volume(request.volume)
                time.sleep(self.settle_sec)

            xa_tu = time.monotonic()
            for hwnd in (list_hwnd, hop.hwnd):
                if hwnd is not None and not win32.cho_xu_ly_xong(hwnd):
                    # Chưa bấm gì nên `rejected` là sự thật; Bridge còn đường EA đóng theo đúng
                    # ticket. Bấm vào một giao diện đang tồn message là đặt cược vào thứ tự xử lý.
                    return bo_cuoc("MT5 khong xu ly xong hang doi truoc cu bam — khong bam khi "
                                   "giao dien con message ton")
            xa_ms = (time.monotonic() - xa_tu) * 1000

            doc_lai = hop.read_back()
            if doc_lai.ticket() != request.position_id:
                return bo_cuoc(f"Hop thoai dang o vi the {doc_lai.ticket()}, "
                               f"khong phai {request.position_id}")
            if request.volume is not None and doc_lai.volume_as_float() != request.volume:
                return bo_cuoc(f"Doc lai lech: volume {doc_lai.volume!r} "
                               f"thay vi {request.volume}")
            lech = doc_lai.lech_nut_dong(request.position_id, request.volume)
            if lech is not None:
                return bo_cuoc(lech)

            # Ném `DialogError` nếu nút không đúng hình dạng — vẫn ở phía an toàn của cú bấm.
            button = hop.close_button()
        except DialogError as exc:
            return bo_cuoc(f"Hop thoai dong khong dung hinh dang: {exc}")

        log.info("Bam Close ticket %s (hwnd %#x, xa hang doi %.0f ms)", request.position_id,
                 hop.hwnd, xa_ms)
        # ==== TỪ ĐÂY TRỞ ĐI KHÔNG CÒN ĐƯỜNG LÙI ====
        if self.on_before_click is not None:
            self.on_before_click()
        if not win32.post_click(button.hwnd):
            return Outcome("unknown", "PostMessage that bai, khong ro da bam hay chua")

        cho_tu = time.monotonic()
        dong = hop.wait_closed(self.close_timeout_sec)
        log.info("Dong lenh %s: cho dong sau bam %.2fs", request.position_id,
                 time.monotonic() - cho_tu)
        if not dong:
            return Outcome("unknown", "Hop thoai dong khong dong sau khi bam", clicked=True)
        phan = "toan bo" if request.volume is None else f"{request.volume:g}"
        return Outcome("ok", f"dong {phan} cua vi the {request.position_id}", clicked=True)

    # -- canary ----------------------------------------------------------------------------

    def dry_probe(self) -> Outcome:
        """Probe khô: mở hộp thoại, đọc lại, đóng. Chứng minh toàn tuyến sống mà không đặt lệnh."""
        health = probe.probe(self.terminal_title, self.account_login)
        if not health or health.hwnd is None:
            return Outcome("rejected", f"Canary do: {health.detail}", clicked=False)
        try:
            dialog = NewOrderDialog.open(health.hwnd)
            state = dialog.read_back()
            dialog.button("BUY")
            dialog.button("SELL")
        except DialogError as exc:
            return Outcome("rejected", f"Probe kho hong: {exc}", clicked=False)
        dialog.cancel()
        dialog.wait_closed()
        return Outcome("rejected", f"Probe kho sach, hop thoai o {state.symbol[:20]!r}",
                       clicked=False)
