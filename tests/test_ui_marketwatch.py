"""Đường MỞ qua Market Watch — copy nhiều symbol trên một terminal Client (D-44, trả B-01).

Không cần MT5: Market Watch và hộp thoại đều giả, theo đúng hành vi đã đo ngày 2026-09-25 —
nhấp đúp một dòng thì mở New Order **cho symbol của dòng đó**, dòng "click to add" cuối thì không
mở gì. Thứ được khoá ở đây là **phép tìm có kiểm chứng**: dòng nào cũng phải đọc symbol trong hộp
thoại trước khi dùng, dòng sai thì huỷ, và không có đường nào tới cú bấm với symbol lệch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import clicker.ui.driver as driver_mod
from clicker.ui import marketwatch
from clicker.ui.dialog import DialogState
from clicker.ui.driver import Mt5UiDriver, OpenRequest
from clicker.ui.marketwatch import MarketWatchError
from clicker.ui.probe import ProbeResult

TEN_DAY_DU = {"XAUUSD.s": "XAUUSD.s, Gold vs US Dollar", "BTCUSD.s": "BTCUSD.s, Bitcoin vs US Dollar",
              "EURUSD.s": "EURUSD.s, Euro vs US Dollar"}


@dataclass
class HopThoaiGia:
    symbol: str
    so: MarketWatchGia
    comment_hien: str = ""
    volume_hien: str = "0.01"

    def read_back(self) -> DialogState:
        return DialogState(symbol=TEN_DAY_DU.get(self.symbol, self.symbol),
                           volume=self.volume_hien, comment=self.comment_hien, price="1 / 2")

    def cancel(self) -> None:
        self.so.nhat_ky.append(f"huy {self.symbol}")

    def wait_closed(self, timeout_sec: float = 2.0) -> bool:
        return True

    def set_volume(self, volume: float) -> bool:
        self.volume_hien = f"{volume:g}"
        return True

    def set_comment(self, comment: str) -> bool:
        self.comment_hien = comment
        return True

    def button(self, direction: str):
        return type("C", (), {"hwnd": 777})()


@dataclass
class MarketWatchGia:
    """`dong[i]` là symbol của dòng i; `None` là dòng "click to add"."""

    dong: list[str | None]
    #: Hộp thoại đang mở sẵn trước khi driver bắt đầu (người vận hành để lại).
    mo_san: str | None = None
    nhat_ky: list[str] = field(default_factory=list)
    _cho_mo: HopThoaiGia | None = None

    def nhap_dup(self, _hwnd: int, row: int) -> bool:
        self.nhat_ky.append(f"nhap {row}")
        sym = self.dong[row]
        self._cho_mo = HopThoaiGia(sym, self) if sym is not None else None
        return True

    def cho(self, _pid: int, timeout_sec: float) -> HopThoaiGia | None:
        if timeout_sec == 0:          # câu hỏi "có hộp thoại mở sẵn không"
            if self.mo_san is None:
                return None
            hop, self.mo_san = HopThoaiGia(self.mo_san, self), None
            return hop
        hop, self._cho_mo = self._cho_mo, None
        return hop

    @property
    def cac_dong_da_nhap(self) -> list[int]:
        return [int(x.split()[1]) for x in self.nhat_ky if x.startswith("nhap")]


@pytest.fixture
def mw(monkeypatch: pytest.MonkeyPatch):
    def dung(dong: list[str | None], mo_san: str | None = None) -> MarketWatchGia:
        gia = MarketWatchGia(dong=dong, mo_san=mo_san)
        monkeypatch.setattr(marketwatch, "tim_danh_sach", lambda hwnd: 4242)
        monkeypatch.setattr(marketwatch, "so_dong", lambda hwnd: len(gia.dong))
        monkeypatch.setattr(marketwatch, "mo_new_order", gia.nhap_dup)
        monkeypatch.setattr(marketwatch, "dong_o_them_symbol",
                            lambda hwnd: gia.nhat_ky.append("dong o go"))
        monkeypatch.setattr(driver_mod.NewOrderDialog, "cho", staticmethod(gia.cho))
        monkeypatch.setattr(driver_mod.win32, "get_process_id", lambda hwnd: 99)
        return gia
    return dung


@pytest.fixture
def driver() -> Mt5UiDriver:
    return Mt5UiDriver(terminal_title="538217", settle_sec=0)


# -- phép tìm -----------------------------------------------------------------------------------


def test_tim_dung_dong_va_huy_dong_sai(mw, driver: Mt5UiDriver) -> None:
    gia = mw(["XAUUSD.s", "BTCUSD.s", None])
    hop = driver._mo_new_order(1, "BTCUSD.s")

    assert hop.symbol == "BTCUSD.s"
    assert gia.nhat_ky == ["nhap 0", "huy XAUUSD.s", "nhap 1"]
    assert driver._mw_ban_do == {"XAUUSD.s": 0, "BTCUSD.s": 1}


def test_lan_sau_mo_thang_dong_da_nho(mw, driver: Mt5UiDriver) -> None:
    gia = mw(["XAUUSD.s", "BTCUSD.s", None])
    driver._mo_new_order(1, "BTCUSD.s")
    gia.nhat_ky.clear()

    driver._mo_new_order(1, "BTCUSD.s")
    assert gia.nhat_ky == ["nhap 1"], "Ban do da biet dong 1 thi mot lan mo la xong"


def test_ban_do_sai_van_bi_doc_lai_va_tim_tiep(mw, driver: Mt5UiDriver) -> None:
    """Người dùng kéo đổi thứ tự dòng mà số dòng không đổi: bản đồ sai, nhưng chỉ tốn một lần mở."""
    gia = mw(["XAUUSD.s", "BTCUSD.s", None])
    driver._mo_new_order(1, "BTCUSD.s")
    gia.dong = ["BTCUSD.s", "XAUUSD.s", None]
    gia.nhat_ky.clear()

    hop = driver._mo_new_order(1, "BTCUSD.s")
    assert hop.symbol == "BTCUSD.s"
    assert gia.nhat_ky == ["nhap 1", "huy XAUUSD.s", "nhap 0"]
    assert driver._mw_ban_do == {"XAUUSD.s": 1, "BTCUSD.s": 0}


def test_so_dong_doi_thi_bo_ban_do(mw, driver: Mt5UiDriver) -> None:
    gia = mw(["XAUUSD.s", "BTCUSD.s", None])
    driver._mo_new_order(1, "BTCUSD.s")
    gia.dong = ["EURUSD.s", "XAUUSD.s", "BTCUSD.s", None]
    gia.nhat_ky.clear()

    driver._mo_new_order(1, "BTCUSD.s")
    assert gia.cac_dong_da_nhap == [0, 1, 2], "So dong doi thi ban do cu khong con dang tin"


def test_khong_co_symbol_thi_loi_va_dong_o_go(mw, driver: Mt5UiDriver) -> None:
    gia = mw(["XAUUSD.s", "BTCUSD.s", None])
    with pytest.raises(MarketWatchError, match="EURUSD.s"):
        driver._mo_new_order(1, "EURUSD.s")

    assert gia.cac_dong_da_nhap == [0, 1, 2]
    assert "huy XAUUSD.s" in gia.nhat_ky and "huy BTCUSD.s" in gia.nhat_ky
    assert "dong o go" in gia.nhat_ky, "Nhap trung dong 'click to add' thi phai dong o go symbol"


def test_hop_thoai_mo_san_dung_symbol_thi_dung_lai(mw, driver: Mt5UiDriver) -> None:
    gia = mw(["XAUUSD.s", "BTCUSD.s", None], mo_san="BTCUSD.s")
    hop = driver._mo_new_order(1, "BTCUSD.s")

    assert hop.symbol == "BTCUSD.s"
    assert gia.cac_dong_da_nhap == []


def test_hop_thoai_mo_san_sai_symbol_thi_dong_roi_mo_qua_market_watch(mw, driver) -> None:
    """Trước D-44 trường hợp này là `rejected`: hộp thoại mở sẵn ở symbol khác nuốt mất lệnh."""
    gia = mw(["XAUUSD.s", "BTCUSD.s", None], mo_san="XAUUSD.s")
    hop = driver._mo_new_order(1, "BTCUSD.s")

    assert hop.symbol == "BTCUSD.s"
    assert gia.nhat_ky[0] == "huy XAUUSD.s"


def test_thu_tu_do_goi_y_truoc_roi_tu_tren_xuong() -> None:
    assert marketwatch.thu_tu_do(4, "B", {"B": 2}) == [2, 0, 1, 3]
    assert marketwatch.thu_tu_do(4, "B", {}) == [0, 1, 2, 3]
    assert marketwatch.thu_tu_do(2, "B", {"B": 5}) == [0, 1], "Goi y ngoai danh sach thi bo qua"


def test_ghi_ban_do_xoa_muc_cu_tro_vao_cung_dong() -> None:
    ban_do = {"A": 0, "B": 1}
    marketwatch.ghi_ban_do(ban_do, 1, "C")
    assert ban_do == {"A": 0, "C": 1}
    marketwatch.ghi_ban_do(ban_do, 0, None)
    assert ban_do == {"C": 1}


# -- trọn đường open(): không bao giờ bấm khi không tìm được symbol ----------------------------


@pytest.fixture
def bam(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    da_bam: list[int] = []
    monkeypatch.setattr(driver_mod.win32, "post_click", lambda hwnd: da_bam.append(hwnd) or True)
    monkeypatch.setattr(driver_mod.probe, "probe",
                        lambda *a, **k: ProbeResult(True, "ok", hwnd=1, title="538217"))
    return da_bam


def test_open_nhieu_symbol_xen_ke(mw, driver: Mt5UiDriver, bam: list[int]) -> None:
    gia = mw(["XAUUSD.s", "BTCUSD.s", None])
    for sym in ("XAUUSD.s", "BTCUSD.s", "XAUUSD.s", "BTCUSD.s"):
        kq = driver.open(OpenRequest(symbol=sym, direction="BUY", volume=0.01, comment="CBt"))
        assert kq.status == "ok", kq.reason
        assert sym in kq.reason
    assert bam == [777] * 4
    # Lượt 1 (XAU) mở 1 lần, lượt 2 (BTC) dò 2 lần, từ lượt 3 đi thẳng bằng bản đồ.
    assert gia.cac_dong_da_nhap == [0, 0, 1, 0, 1]


def test_open_symbol_khong_co_thi_rejected_va_khong_bam(mw, driver, bam: list[int]) -> None:
    mw(["XAUUSD.s", "BTCUSD.s", None])
    kq = driver.open(OpenRequest(symbol="EURUSD.s", direction="SELL", volume=0.01, comment="CBt"))

    assert kq.status == "rejected"
    assert kq.clicked is False
    assert "EURUSD.s" in kq.reason
    assert bam == []


def test_open_khong_co_market_watch_thi_rejected(monkeypatch, driver, bam: list[int]) -> None:
    def khong_co(hwnd: int) -> int:
        raise MarketWatchError("Khong thay Market Watch")

    monkeypatch.setattr(marketwatch, "tim_danh_sach", khong_co)
    monkeypatch.setattr(driver_mod.NewOrderDialog, "cho", staticmethod(lambda pid, t: None))
    monkeypatch.setattr(driver_mod.win32, "get_process_id", lambda hwnd: 99)
    kq = driver.open(OpenRequest(symbol="BTCUSD.s", direction="BUY", volume=0.01, comment="CBt"))

    assert kq.status == "rejected"
    assert "Market Watch" in kq.reason
    assert bam == []
