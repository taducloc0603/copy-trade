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
một **phép tìm có kiểm chứng** — mở dòng 0, đọc ngược ticket, sai thì huỷ và thử dòng 1, đúng mới
điền volume và bấm.

Điều làm phép tìm này an toàn: **mở và huỷ hộp thoại không đặt lệnh nào.** Mọi bước dò đều nằm ở
phía an toàn của ranh giới D-24, nên một lần dò trượt vẫn là `rejected` đúng nghĩa. Đây không phải
đoán rồi sửa sau — không có "sau".
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from bridge.logging_setup import get_logger
from clicker.ui import probe, tradetab, win32
from clicker.ui.dialog import (
    ClosePositionDialog,
    DialogError,
    HopThoaiDongSoBo,
    NewOrderDialog,
    cho_so_bo,
    tim_so_bo,
)

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

    def __init__(self, terminal_title: str,
                 on_before_click: Callable[[], None] | None = None,
                 settle_sec: float = 0.05, close_timeout_sec: float = 5.0) -> None:
        self.terminal_title = terminal_title
        #: Gọi ngay TRƯỚC cú bấm. `link.py` dùng nó để ghi "đã bấm" xuống đĩa trước khi bấm —
        #: nếu mất điện đúng lúc này, lần khởi động lại phải giả định là đã bấm.
        self.on_before_click = on_before_click
        self.settle_sec = settle_sec
        self.close_timeout_sec = close_timeout_sec
        #: Dòng của lần đóng trúng gần nhất. Chỉ là **thứ tự dò**, không phải kết luận — xem
        #: `_thu_tu_dong`.
        self._dong_gan_nhat: int | None = None

    # -- mở lệnh ---------------------------------------------------------------------------

    def open(self, request: OpenRequest) -> Outcome:
        health = probe.probe(self.terminal_title)
        if not health or health.hwnd is None:
            return Outcome("rejected", f"Canary do: {health.detail}", clicked=False)
        try:
            dialog = NewOrderDialog.open(health.hwnd)
        except DialogError as exc:
            return Outcome("rejected", f"Khong mo duoc hop thoai: {exc}", clicked=False)
        return self._commit(dialog, request)

    def _commit(self, dialog: NewOrderDialog, request: OpenRequest) -> Outcome:
        """Điền, **đọc lại**, so, rồi mới bấm. Không có đường nào tới nút gửi mà vòng qua đây."""
        def bo_cuoc(ly_do: str) -> Outcome:
            dialog.cancel()
            dialog.wait_closed()
            return Outcome("rejected", ly_do, clicked=False)

        try:
            # Đổi symbol qua ComboBox chưa được đo, nên ở đây chỉ **kiểm tra** chứ không đổi.
            # Hộp thoại hiện `'BTCUSD.s, Bitcoin vs US Dollar'`, so theo phần trước dấu phẩy.
            hien_tai = dialog.read_back().symbol.split(",")[0].strip()
            if hien_tai != request.symbol:
                return bo_cuoc(f"Hop thoai dang o symbol {hien_tai!r}, "
                               f"khong phai {request.symbol!r}")

            dialog.set_volume(request.volume)
            dialog.set_comment(request.comment)
            time.sleep(self.settle_sec)

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

        # ==== TỪ ĐÂY TRỞ ĐI KHÔNG CÒN ĐƯỜNG LÙI ====
        if self.on_before_click is not None:
            self.on_before_click()
        if not win32.post_click(button.hwnd):
            # `PostMessage` chỉ xếp message vào hàng đợi. Thất bại ở đây gần như chắc chắn là
            # chưa bấm, nhưng "gần như chắc chắn" không đủ để cho phép thử lại.
            return Outcome("unknown", "PostMessage that bai, khong ro da bam hay chua")

        if not dialog.wait_closed(self.close_timeout_sec):
            return Outcome("unknown", "Hop thoai khong dong sau khi bam", clicked=True)
        return Outcome("ok", f"{request.direction} {request.volume:g} {request.symbol}",
                       clicked=True)

    # -- đóng lệnh -------------------------------------------------------------------------

    def close(self, request: CloseRequest) -> Outcome:
        """Tìm đúng vị thế trong danh sách rồi đóng nó. Xem phần đầu file về vì sao là phép tìm."""
        health = probe.probe(self.terminal_title)
        if not health or health.hwnd is None:
            return Outcome("rejected", f"Canary do: {health.detail}", clicked=False)
        pid = win32.get_process_id(health.hwnd)

        try:
            list_hwnd = tradetab.tim_danh_sach(health.hwnd)
        except tradetab.TradeTabError as exc:
            return Outcome("rejected", str(exc), clicked=False)

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
        for row in self._thu_tu_dong(so_dong):
            # Hộp thoại sót lại từ vòng trước — kể cả một cái mở **chậm hơn** thời gian chờ. MT5
            # lúc đó đang ở vòng lặp modal và cú double-click kế tiếp sẽ không đi tới đâu cả, nên
            # bỏ qua bước này là để cả phần còn lại của vòng lặp dò trong vô vọng.
            sot = tim_so_bo(pid)
            if sot is not None:
                sot.cancel()
                sot.wait_closed()

            so_bo = self._mo_dong(pid, list_hwnd, row)
            if so_bo is None:
                # Dòng này không mở hộp thoại nào. Bình thường: danh sách có cả dòng tổng kết
                # Balance. Đi tiếp chứ không coi là lỗi.
                continue
            mo_duoc_it_nhat_mot = True
            da_gap.append(so_bo.ticket)
            if so_bo.ticket != request.position_id:
                # Loại bằng đúng một lần đọc tiêu đề, **không** đọc 55 control của hộp thoại này.
                so_bo.cancel()
                so_bo.wait_closed()
                continue

            hop = ClosePositionDialog.tu_hwnd(so_bo.hwnd)
            if hop is None:
                so_bo.cancel()
                so_bo.wait_closed()
                return Outcome("rejected", "Hop thoai dong khong dung hinh dang", clicked=False)
            self._dong_gan_nhat = row
            return self._commit_close(hop, request)

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

    def _thu_tu_dong(self, so_dong: int) -> list[int]:
        """Thứ tự dò: dòng đóng trúng lần trước đứng đầu, rồi tới các dòng còn lại theo thứ tự.

        Danh sách Trade thường giữ nguyên hình dạng giữa hai lần đóng, nên dòng trúng lần trước là
        phỏng đoán tốt nhất — mà mỗi dòng dò trượt tốn một lần mở/huỷ hộp thoại, còn dòng không mở gì
        (dòng tổng kết Balance) tốn trọn `PROBE_CLOSE_SEC`.

        Đây **chỉ là thứ tự**, không phải kết luận: dòng nào mở ra cũng bị đọc ngược ticket rồi mới
        bấm, nên đoán sai chỉ tốn thêm thời gian chứ không đóng nhầm vị thế.
        """
        thu_tu = list(range(so_dong))
        dau = self._dong_gan_nhat
        if dau is not None and 0 <= dau < so_dong:
            thu_tu.remove(dau)
            thu_tu.insert(0, dau)
        return thu_tu

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
            cho = (self.CHO_SAU_KHI_TREO_SEC if not gui and lan < so_lan
                   else self.PROBE_CLOSE_SEC)
            so_bo = cho_so_bo(pid, cho) or self._so_bo_du_phong(pid)
            log.info("Do dong %d lan %d: gui=%s, hop thoai %s sau %.2fs", row, lan, gui,
                     "MO" if so_bo is not None else "KHONG mo", time.monotonic() - bat_dau)
            if so_bo is not None or gui:
                return so_bo
        return None

    def _commit_close(self, hop: ClosePositionDialog, request: CloseRequest) -> Outcome:
        """Điền volume, **đọc lại cả ticket lẫn volume**, rồi mới bấm.

        Kiểm ticket **lần thứ hai** ở đây chứ không tin lần kiểm lúc tìm: giữa hai thời điểm có
        một lần gõ phím vào hộp thoại, và thứ đắt nhất có thể xảy ra là đóng nhầm vị thế. Kiểm lại
        một lần nữa rẻ hơn nhiều so với việc phải tin.
        """
        def bo_cuoc(ly_do: str) -> Outcome:
            hop.cancel()
            hop.wait_closed()
            return Outcome("rejected", ly_do, clicked=False)

        try:
            if request.volume is not None:
                hop.set_volume(request.volume)
                time.sleep(self.settle_sec)

            doc_lai = hop.read_back()
            if doc_lai.ticket() != request.position_id:
                return bo_cuoc(f"Hop thoai dang o vi the {doc_lai.ticket()}, "
                               f"khong phai {request.position_id}")
            if request.volume is not None and doc_lai.volume_as_float() != request.volume:
                return bo_cuoc(f"Doc lai lech: volume {doc_lai.volume!r} "
                               f"thay vi {request.volume}")

            # Ném `DialogError` nếu nút không đúng hình dạng — vẫn ở phía an toàn của cú bấm.
            button = hop.close_button()
        except DialogError as exc:
            return bo_cuoc(f"Hop thoai dong khong dung hinh dang: {exc}")

        # ==== TỪ ĐÂY TRỞ ĐI KHÔNG CÒN ĐƯỜNG LÙI ====
        if self.on_before_click is not None:
            self.on_before_click()
        if not win32.post_click(button.hwnd):
            return Outcome("unknown", "PostMessage that bai, khong ro da bam hay chua")

        if not hop.wait_closed(self.close_timeout_sec):
            return Outcome("unknown", "Hop thoai dong khong dong sau khi bam", clicked=True)
        phan = "toan bo" if request.volume is None else f"{request.volume:g}"
        return Outcome("ok", f"dong {phan} cua vi the {request.position_id}", clicked=True)

    # -- canary ----------------------------------------------------------------------------

    def dry_probe(self) -> Outcome:
        """Probe khô: mở hộp thoại, đọc lại, đóng. Chứng minh toàn tuyến sống mà không đặt lệnh."""
        health = probe.probe(self.terminal_title)
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
