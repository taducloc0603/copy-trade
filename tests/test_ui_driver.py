"""Test ranh giới `rejected` / `unknown` của driver giao diện (plan 6b mục 6b.3, D-24).

Không cần MT5: `_commit()` chỉ nói chuyện với đối tượng hộp thoại, nên thay bằng hộp thoại giả
là đủ để kiểm đúng thứ quan trọng nhất — **cái gì xảy ra trước cú bấm và cái gì sau nó**.

`rejected` nghĩa là *chứng minh được là chưa bấm*, và nó là trạng thái DUY NHẤT Bridge được phép
thử lại. Một `rejected` sai sự thật sẽ thành lệnh thứ hai trên tài khoản thật.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from clicker.ui.dialog import CTRL_BUY, DialogError, DialogState
from clicker.ui.driver import Mt5UiDriver, OpenRequest

YEU_CAU = OpenRequest(symbol="BTCUSD.s", direction="BUY", volume=0.02, comment="CBtest000001")


@dataclass
class HopThoaiGia:
    """Hộp thoại giả. `ghi_lai` giữ đúng thứ tự các việc đã xảy ra."""

    symbol: str = "BTCUSD.s, Bitcoin vs US Dollar"
    volume_hien: str = "0.01"
    comment_hien: str = ""
    #: Volume/comment mà việc đọc lại sẽ trả về; None nghĩa là nhận đúng thứ vừa điền.
    volume_doc_lai: str | None = None
    button_hong: bool = False
    dong_duoc: bool = True
    ghi_lai: list[str] = field(default_factory=list)

    def read_back(self) -> DialogState:
        return DialogState(symbol=self.symbol,
                           volume=self.volume_doc_lai or self.volume_hien,
                           comment=self.comment_hien, price="1 / 2")

    def set_volume(self, volume: float) -> bool:
        self.ghi_lai.append(f"volume={volume:g}")
        self.volume_hien = f"{volume:g}"
        return True

    def set_comment(self, comment: str) -> bool:
        self.ghi_lai.append("comment")
        self.comment_hien = comment
        return True

    def button(self, direction: str) -> Any:
        if self.button_hong:
            raise DialogError("Nut mang chu 'Buy', co the dang bam vao ban an")
        return type("C", (), {"hwnd": 12345, "ctrl_id": CTRL_BUY})()

    def cancel(self) -> None:
        self.ghi_lai.append("cancel")

    def wait_closed(self, timeout_sec: float = 2.0) -> bool:
        return self.dong_duoc


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> Mt5UiDriver:
    """Driver với cú bấm được thay bằng bản ghi lại, để không cần cửa sổ thật."""
    import clicker.ui.driver as mod

    def bam(hwnd: int) -> bool:
        bam.da_bam.append(hwnd)
        return bam.thanh_cong

    bam.da_bam = []
    bam.thanh_cong = True
    monkeypatch.setattr(mod.win32, "post_click", bam)
    d = Mt5UiDriver(terminal_title="538217", settle_sec=0)
    d._bam = bam
    return d


def test_doc_lai_khop_thi_bam_va_tra_ok(driver: Mt5UiDriver) -> None:
    dialog = HopThoaiGia()
    ket_qua = driver._commit(dialog, YEU_CAU)

    assert ket_qua.status == "ok"
    assert ket_qua.clicked is True
    assert driver._bam.da_bam == [12345]
    assert "cancel" not in dialog.ghi_lai


def test_volume_doc_lai_lech_thi_huy_truoc_khi_bam(driver: Mt5UiDriver) -> None:
    """Đây là lý do `commit()` tồn tại: chữ trong ô không chứng minh được MT5 nhận đúng."""
    dialog = HopThoaiGia(volume_doc_lai="0.01")
    ket_qua = driver._commit(dialog, YEU_CAU)

    assert ket_qua.status == "rejected"
    assert ket_qua.clicked is False
    assert "volume" in ket_qua.reason
    assert driver._bam.da_bam == [], "TUYET DOI khong duoc bam khi doc lai lech"
    assert "cancel" in dialog.ghi_lai


def test_symbol_sai_thi_tu_choi_chu_khong_tu_doi(driver: Mt5UiDriver) -> None:
    """Đổi symbol qua ComboBox chưa được đo, nên từ chối là đúng — đoán mới là sai."""
    dialog = HopThoaiGia(symbol="EURUSD, Euro vs US Dollar")
    ket_qua = driver._commit(dialog, YEU_CAU)

    assert ket_qua.status == "rejected"
    assert "EURUSD" in ket_qua.reason
    assert dialog.ghi_lai == ["cancel"], "Khong duoc dien gi vao hop thoai sai symbol"


def test_nut_sai_hinh_dang_thi_tu_choi_truoc_khi_bam(driver: Mt5UiDriver) -> None:
    dialog = HopThoaiGia(button_hong=True)
    ket_qua = driver._commit(dialog, YEU_CAU)

    assert ket_qua.status == "rejected"
    assert ket_qua.clicked is False
    assert driver._bam.da_bam == []


def test_hop_thoai_khong_dong_sau_khi_bam_thi_unknown(driver: Mt5UiDriver) -> None:
    """Đã bấm rồi thì không còn `rejected` nữa, dù không đọc được kết quả."""
    dialog = HopThoaiGia(dong_duoc=False)
    ket_qua = driver._commit(dialog, YEU_CAU)

    assert ket_qua.status == "unknown"
    assert ket_qua.clicked is True
    assert driver._bam.da_bam == [12345]


def test_post_click_that_bai_van_la_unknown_khong_phai_rejected(driver: Mt5UiDriver) -> None:
    """"Gan nhu chac chan chua bam" khong du de cho phep thu lai."""
    driver._bam.thanh_cong = False
    ket_qua = driver._commit(HopThoaiGia(), YEU_CAU)

    assert ket_qua.status == "unknown"


def test_ghi_nhat_ky_chay_TRUOC_cu_bam(driver: Mt5UiDriver) -> None:
    """Mất điện giữa ghi và bấm thì phải giả định là đã bấm, nên thứ tự này là bắt buộc."""
    thu_tu: list[str] = []
    driver.on_before_click = lambda: thu_tu.append("ghi nhat ky")
    driver._bam.da_bam = []

    import clicker.ui.driver as mod
    goc = mod.win32.post_click
    mod.win32.post_click = lambda hwnd: (thu_tu.append("bam"), goc(hwnd))[1]
    try:
        driver._commit(HopThoaiGia(), YEU_CAU)
    finally:
        mod.win32.post_click = goc

    assert thu_tu == ["ghi nhat ky", "bam"]


def test_khong_bam_thi_khong_ghi_nhat_ky(driver: Mt5UiDriver) -> None:
    goi: list[str] = []
    driver.on_before_click = lambda: goi.append("ghi")
    driver._commit(HopThoaiGia(volume_doc_lai="0.99"), YEU_CAU)

    assert goi == []
