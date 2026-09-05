"""Hợp đồng của driver mở lệnh, bản `--dry-run`, và driver thật.

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
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from clicker.ui import probe, win32
from clicker.ui.dialog import DialogError, NewOrderDialog


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
class OpenOutcome:
    """Kết quả một lần mở lệnh, theo đúng bốn trạng thái của hợp đồng ack (plan 6b mục 6b.3)."""

    status: str
    reason: str
    #: `True` chỉ khi driver **biết chắc** đã bấm nút gửi. `None` nghĩa là không biết.
    clicked: bool | None = None

    def __post_init__(self) -> None:
        if self.status not in ("ok", "failed", "rejected", "unknown"):
            raise ValueError(f"Trang thai khong hop le: {self.status!r}")


class OpenDriver(Protocol):
    """Thứ duy nhất clicker cần biết về giao diện."""

    def open(self, request: OpenRequest) -> OpenOutcome:
        ...

    def dry_probe(self) -> OpenOutcome:
        """Probe khô: mở hộp thoại, đọc lại các field, bấm ESC. Không đặt lệnh nào."""
        ...


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
        self.seen: list[OpenRequest] = []

    def open(self, request: OpenRequest) -> OpenOutcome:
        self.seen.append(request)
        return OpenOutcome(
            "rejected",
            f"{self.REASON}: che do chay thu, khong cham vao giao dien "
            f"({request.direction} {request.volume} {request.symbol})",
            clicked=False,
        )

    def dry_probe(self) -> OpenOutcome:
        return OpenOutcome("rejected", f"{self.REASON}: khong chay probe kho", clicked=False)


class Mt5UiDriver:
    """Driver thật: điền hộp thoại New Order của MT5 rồi bấm.

    Trình tự dưới đây **được đo chứ không suy ra** (2026-09-05, Connext-Demo, build 5.00):
    10/10 lệnh cho ra deal đúng volume, đúng chiều, comment nguyên vẹn, `DEAL_REASON = CLIENT`.
    Lặp lại 5/5 với cửa sổ minimized.

    Đường sống của cả lớp này là **thứ tự**: mọi thứ có thể hỏng đều phải hỏng **trước** cú bấm,
    vì trước cú bấm thì `rejected` là sự thật chứng minh được, còn sau cú bấm thì không còn gì
    chứng minh được nữa.
    """

    def __init__(self, terminal_title: str,
                 on_before_click: Callable[[], None] | None = None,
                 settle_sec: float = 0.05, close_timeout_sec: float = 5.0) -> None:
        self.terminal_title = terminal_title
        #: Gọi ngay TRƯỚC cú bấm. `link.py` dùng nó để ghi "đã bấm" xuống đĩa trước khi bấm —
        #: nếu mất điện đúng lúc này, lần khởi động lại phải giả định là đã bấm.
        self.on_before_click = on_before_click
        self.settle_sec = settle_sec
        self.close_timeout_sec = close_timeout_sec

    def open(self, request: OpenRequest) -> OpenOutcome:
        health = probe.probe(self.terminal_title)
        if not health or health.hwnd is None:
            return OpenOutcome("rejected", f"Canary do: {health.detail}", clicked=False)
        try:
            dialog = NewOrderDialog.open(health.hwnd)
        except DialogError as exc:
            return OpenOutcome("rejected", f"Khong mo duoc hop thoai: {exc}", clicked=False)
        return self._commit(dialog, request)

    def _commit(self, dialog: NewOrderDialog, request: OpenRequest) -> OpenOutcome:
        """Điền, **đọc lại**, so, rồi mới bấm. Không có đường nào tới nút gửi mà vòng qua đây."""
        def bo_cuoc(ly_do: str) -> OpenOutcome:
            dialog.cancel()
            dialog.wait_closed()
            return OpenOutcome("rejected", ly_do, clicked=False)

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
            return OpenOutcome("unknown", "PostMessage that bai, khong ro da bam hay chua")

        if not dialog.wait_closed(self.close_timeout_sec):
            return OpenOutcome("unknown", "Hop thoai khong dong sau khi bam", clicked=True)
        return OpenOutcome("ok", f"{request.direction} {request.volume:g} {request.symbol}",
                           clicked=True)

    def dry_probe(self) -> OpenOutcome:
        """Probe khô: mở hộp thoại, đọc lại, đóng. Chứng minh toàn tuyến sống mà không đặt lệnh."""
        health = probe.probe(self.terminal_title)
        if not health or health.hwnd is None:
            return OpenOutcome("rejected", f"Canary do: {health.detail}", clicked=False)
        try:
            dialog = NewOrderDialog.open(health.hwnd)
            state = dialog.read_back()
            dialog.button("BUY")
            dialog.button("SELL")
        except DialogError as exc:
            return OpenOutcome("rejected", f"Probe kho hong: {exc}", clicked=False)
        dialog.cancel()
        dialog.wait_closed()
        return OpenOutcome("rejected", f"Probe kho sach, hop thoai o {state.symbol[:20]!r}",
                           clicked=False)
