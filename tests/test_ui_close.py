"""Test đường ĐÓNG qua giao diện, phía clicker.

Hai thứ được kiểm ở đây, và cả hai đều là chuyện mất tiền chứ không phải chuyện trạng thái:

1. **Không bao giờ bấm khi chưa chứng minh được đang ở đúng vị thế.** Danh sách vị thế không đọc
   được nội dung, nên `close()` là một phép *tìm*; mỗi lần dò trượt phải kết thúc bằng `cancel()`
   và tuyệt đối không bằng một cú bấm.
2. **`CLOSE_UI_PARTIAL` rơi mất `volume` phải nổ, không được lặng lẽ thành đóng hẳn.**

Không cần MT5: mọi thứ ở đây nói chuyện với hộp thoại giả và danh sách giả.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from clicker.ui import dialog as dialog_mod
from clicker.ui import driver as driver_mod
from clicker.ui.dialog import CloseState, DialogError, doc_ticket, la_che_do_dong
from clicker.ui.driver import CloseRequest, Mt5UiDriver, Outcome
from clicker.ui.win32 import ControlInfo

TICKET = 72205853
NUT = f"Close #{TICKET} buy 0.01 BTCUSD.s 78500.01 by Market"


# ---------------------------------------------------------------------------------------------
# doc_ticket + CloseState — đọc ticket từ ba nguồn
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("chu", "mong_doi"), [
    (NUT, TICKET),
    (f"Position: #{TICKET} buy 0.01 BTCUSD.s 78500.01", TICKET),
    (f"#{TICKET} buy 0.01 BTCUSD.s 78500.01", TICKET),
    ("Buy by Market", None),
    ("", None),
    ("Close # buy 0.01", None),
])
def test_doc_ticket(chu: str, mong_doi: int | None) -> None:
    assert doc_ticket(chu) == mong_doi


def _state(tieu_de: int | None = TICKET, nut: int | None = TICKET,
           combo: int | None = TICKET, volume: str = "0.01") -> CloseState:
    return CloseState(ticket_tieu_de=tieu_de, ticket_nut=nut, ticket_combo=combo,
                      volume=volume, symbol="BTCUSD.s, Bitcoin vs US Dollar", nut_text=NUT)


def test_ba_nguon_dong_y_thi_lay_duoc_ticket() -> None:
    assert _state().ticket() == TICKET


def test_nguon_khong_doc_duoc_thi_bo_qua_chu_khong_lam_hong() -> None:
    """Combo `10672` thường không `visible`, nên `None` ở đó là chuyện bình thường."""
    assert _state(combo=None).ticket() == TICKET


def test_cac_nguon_bat_dong_thi_KHONG_doan() -> None:
    """Bất đồng nghĩa là hộp thoại đang ở trạng thái ta không hiểu. `None` sẽ thành `rejected`."""
    assert _state(nut=999).ticket() is None


def test_khong_nguon_nao_doc_duoc_thi_tra_None() -> None:
    assert _state(None, None, None).ticket() is None


# ---------------------------------------------------------------------------------------------
# la_che_do_dong — lỗ hổng SIGNATURE
# ---------------------------------------------------------------------------------------------

def _ctrl(ctrl_id: int, text: str, visible: bool = True) -> ControlInfo:
    return ControlInfo(hwnd=ctrl_id * 10, ctrl_id=ctrl_id, class_name="Button",
                       text=text, visible=visible)


def test_nhan_ra_che_do_dong_qua_chu_tren_nut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dialog_mod.win32, "get_window_text", lambda _h: "")
    assert la_che_do_dong(1, {dialog_mod.CTRL_CLOSE: _ctrl(dialog_mod.CTRL_CLOSE, NUT)})


def test_nhan_ra_che_do_dong_qua_tieu_de(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hai dấu hiệu độc lập: một cái hỏng thì cái kia vẫn bắt được."""
    monkeypatch.setattr(dialog_mod.win32, "get_window_text",
                        lambda _h: f"Position: #{TICKET} buy 0.01 BTCUSD.s")
    assert la_che_do_dong(1, {})


def test_hop_thoai_mo_lenh_khong_bi_nham_la_che_do_dong(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dialog_mod.win32, "get_window_text", lambda _h: "Order")
    controls = {dialog_mod.CTRL_BUY: _ctrl(dialog_mod.CTRL_BUY, "Buy by Market")}
    assert not la_che_do_dong(1, controls)


def test_ban_an_cua_nut_dong_khong_bi_tinh_la_che_do_dong(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Bản ẩn của 10410 mang chữ `'Close'` trần — đúng cái bẫy đã biết với 10408/10409."""
    monkeypatch.setattr(dialog_mod.win32, "get_window_text", lambda _h: "Order")
    assert not la_che_do_dong(1, {dialog_mod.CTRL_CLOSE: _ctrl(dialog_mod.CTRL_CLOSE, "Close")})


def test_NewOrderDialog_bo_qua_hop_thoai_dang_o_che_do_dong(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Lỗ hổng có sẵn: `open()` dùng lại hộp thoại đang mở, mà chữ ký khớp cả hai chế độ.

    Không lọc ở đây thì một hộp thoại đóng người vận hành lỡ để mở sẽ được điền volume rồi bấm
    `'Buy by Market'` — tức là mở một lệnh mới trong khi tưởng mình đang mở lệnh bình thường.
    """
    monkeypatch.setattr(dialog_mod, "_quet", lambda _pid: [(1, {})])
    monkeypatch.setattr(dialog_mod, "la_che_do_dong", lambda _h, _c: True)
    assert dialog_mod.NewOrderDialog._find(123) is None

    monkeypatch.setattr(dialog_mod, "la_che_do_dong", lambda _h, _c: False)
    assert dialog_mod.NewOrderDialog._find(123) is not None


# ---------------------------------------------------------------------------------------------
# CloseRequest.from_payload — hai loại command soi lẫn nhau
# ---------------------------------------------------------------------------------------------

def test_dong_han_khong_mang_volume() -> None:
    yc = CloseRequest.from_payload({"position_id": TICKET}, "CLOSE_UI")
    assert yc.position_id == TICKET and yc.volume is None


def test_dong_bot_mang_volume() -> None:
    yc = CloseRequest.from_payload({"position_id": TICKET, "volume": 0.02}, "CLOSE_UI_PARTIAL")
    assert yc.volume == 0.02


def test_dong_bot_thieu_volume_thi_NO_chu_khong_thanh_dong_han() -> None:
    """Đây là lỗi mất tiền im lặng mà `from_payload` tồn tại để chặn."""
    with pytest.raises(ValueError, match="thieu volume"):
        CloseRequest.from_payload({"position_id": TICKET}, "CLOSE_UI_PARTIAL")


def test_dong_han_ma_co_volume_cung_bi_tu_choi() -> None:
    """Bên gọi nghĩ một đằng, loại command nói một nẻo — không được đoán bên nào đúng."""
    with pytest.raises(ValueError, match="khong duoc mang volume"):
        CloseRequest.from_payload({"position_id": TICKET, "volume": 0.01}, "CLOSE_UI")


@pytest.mark.parametrize(("payload", "loai", "khop"), [
    ({}, "CLOSE_UI", "thieu position_id"),
    ({"position_id": 0}, "CLOSE_UI", "phai duong"),
    ({"position_id": TICKET, "magic": 770001}, "CLOSE_UI", "magic"),
    ({"position_id": TICKET, "volume": -1}, "CLOSE_UI_PARTIAL", "phai duong"),
    ({"position_id": TICKET}, "CLOSE", "khong phai lenh dong"),
    ({"position_id": TICKET}, "OPEN_UI", "khong phai lenh dong"),
])
def test_payload_sai_bi_tu_choi(payload: dict, loai: str, khop: str) -> None:
    with pytest.raises(ValueError, match=khop):
        CloseRequest.from_payload(payload, loai)


# ---------------------------------------------------------------------------------------------
# _commit_close — ranh giới rejected / unknown
# ---------------------------------------------------------------------------------------------

@dataclass
class HopThoaiDongGia:
    ticket: int = TICKET
    volume_hien: str = "0.01"
    volume_doc_lai: str | None = None
    ticket_sau_khi_dien: int | None = None
    nut_hong: bool = False
    dong_duoc: bool = True
    ghi_lai: list[str] = field(default_factory=list)

    def read_back(self) -> CloseState:
        t = self.ticket if self.ticket_sau_khi_dien is None else self.ticket_sau_khi_dien
        return CloseState(ticket_tieu_de=t, ticket_nut=t, ticket_combo=None,
                          volume=self.volume_doc_lai or self.volume_hien,
                          symbol="BTCUSD.s, Bitcoin vs US Dollar", nut_text=NUT)

    def set_volume(self, volume: float) -> bool:
        self.ghi_lai.append(f"volume={volume:g}")
        self.volume_hien = f"{volume:g}"
        return True

    def close_button(self) -> Any:
        if self.nut_hong:
            raise DialogError("Nut mang chu 'Close' tran, co the dang bam vao ban an")
        return type("C", (), {"hwnd": 4242, "ctrl_id": dialog_mod.CTRL_CLOSE})()

    def cancel(self) -> None:
        self.ghi_lai.append("cancel")

    def wait_closed(self, timeout_sec: float = 2.0) -> bool:
        return self.dong_duoc


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> Mt5UiDriver:
    def bam(hwnd: int) -> bool:
        bam.da_bam.append(hwnd)
        return bam.thanh_cong

    bam.da_bam = []
    bam.thanh_cong = True
    monkeypatch.setattr(driver_mod.win32, "post_click", bam)
    d = Mt5UiDriver(terminal_title="538217", settle_sec=0)
    d._bam = bam
    return d


def test_dong_han_khong_go_lai_volume(driver: Mt5UiDriver) -> None:
    """`volume = None` thì giữ nguyên con số hộp thoại đã điền sẵn — terminal đúng hơn sổ sách."""
    hop = HopThoaiDongGia()
    kq = driver._commit_close(hop, CloseRequest(position_id=TICKET))

    assert kq.status == "ok" and kq.clicked is True
    assert driver._bam.da_bam == [4242]
    assert hop.ghi_lai == [], "Dong han thi khong duoc cham vao o volume"


def test_dong_bot_go_volume_va_doc_lai(driver: Mt5UiDriver) -> None:
    hop = HopThoaiDongGia(volume_hien="0.05")
    kq = driver._commit_close(hop, CloseRequest(position_id=TICKET, volume=0.02))

    assert kq.status == "ok"
    assert hop.ghi_lai == ["volume=0.02"]


def test_volume_doc_lai_lech_thi_huy_truoc_khi_bam(driver: Mt5UiDriver) -> None:
    hop = HopThoaiDongGia(volume_doc_lai="0.05")
    kq = driver._commit_close(hop, CloseRequest(position_id=TICKET, volume=0.02))

    assert kq.status == "rejected" and kq.clicked is False
    assert driver._bam.da_bam == [], "TUYET DOI khong duoc bam khi doc lai lech"
    assert "cancel" in hop.ghi_lai


def test_ticket_doi_giua_chung_thi_huy(driver: Mt5UiDriver) -> None:
    """Giữa lúc tìm và lúc bấm có một lần gõ phím. Kiểm ticket lần hai rẻ hơn việc phải tin."""
    hop = HopThoaiDongGia(ticket_sau_khi_dien=999999)
    kq = driver._commit_close(hop, CloseRequest(position_id=TICKET, volume=0.01))

    assert kq.status == "rejected" and driver._bam.da_bam == []
    assert "999999" in kq.reason


def test_ticket_khong_doc_duoc_thi_tu_choi_chu_khong_bam(driver: Mt5UiDriver) -> None:
    hop = HopThoaiDongGia(ticket_sau_khi_dien=None)
    hop.read_back = lambda: CloseState(None, None, None, "0.01", "BTCUSD.s", NUT)  # type: ignore[method-assign]
    kq = driver._commit_close(hop, CloseRequest(position_id=TICKET))

    assert kq.status == "rejected" and driver._bam.da_bam == []


def test_nut_sai_hinh_dang_thi_tu_choi_truoc_khi_bam(driver: Mt5UiDriver) -> None:
    hop = HopThoaiDongGia(nut_hong=True)
    kq = driver._commit_close(hop, CloseRequest(position_id=TICKET))

    assert kq.status == "rejected" and driver._bam.da_bam == []


def test_hop_thoai_khong_dong_sau_khi_bam_thi_unknown(driver: Mt5UiDriver) -> None:
    kq = driver._commit_close(HopThoaiDongGia(dong_duoc=False), CloseRequest(position_id=TICKET))

    assert kq.status == "unknown" and kq.clicked is True


def test_post_click_that_bai_van_la_unknown(driver: Mt5UiDriver) -> None:
    driver._bam.thanh_cong = False
    kq = driver._commit_close(HopThoaiDongGia(), CloseRequest(position_id=TICKET))

    assert kq.status == "unknown"


def test_ghi_nhat_ky_chay_TRUOC_cu_bam(driver: Mt5UiDriver) -> None:
    thu_tu: list[str] = []
    driver.on_before_click = lambda: thu_tu.append("ghi nhat ky")
    goc = driver_mod.win32.post_click
    driver_mod.win32.post_click = lambda hwnd: (thu_tu.append("bam"), goc(hwnd))[1]
    try:
        driver._commit_close(HopThoaiDongGia(), CloseRequest(position_id=TICKET))
    finally:
        driver_mod.win32.post_click = goc

    assert thu_tu == ["ghi nhat ky", "bam"]


# ---------------------------------------------------------------------------------------------
# close() — phép tìm có kiểm chứng
# ---------------------------------------------------------------------------------------------

def _gia_lap_tim(monkeypatch: pytest.MonkeyPatch, tickets: list[int | None],
                 hop_theo_dong: dict[int, HopThoaiDongGia] | None = None) -> list[str]:
    """Dựng một danh sách giả: `tickets[i]` là ticket mà dòng `i` mở ra, `None` = không mở."""
    nhat_ky: list[str] = []
    hop_theo_dong = hop_theo_dong or {}

    monkeypatch.setattr(driver_mod.probe, "probe",
                        lambda _t: type("P", (), {"healthy": True, "hwnd": 1, "detail": "",
                                                  "__bool__": lambda s: True})())
    monkeypatch.setattr(driver_mod.win32, "get_process_id", lambda _h: 4242)
    monkeypatch.setattr(driver_mod.tradetab, "tim_danh_sach", lambda _h: 777)
    monkeypatch.setattr(driver_mod.tradetab, "so_dong", lambda _h: len(tickets))
    monkeypatch.setattr(driver_mod.ClosePositionDialog, "find",
                        classmethod(lambda cls, _pid: None))

    trang_thai = {"dong": -1}

    def mo(_list_hwnd: int, row: int) -> bool:
        trang_thai["dong"] = row
        nhat_ky.append(f"mo dong {row}")
        return True

    def cho_mo(cls: Any, _pid: int, timeout_sec: float = 2.0) -> Any:
        row = trang_thai["dong"]
        if tickets[row] is None:
            nhat_ky.append(f"dong {row} khong mo hop thoai")
            return None
        hop = hop_theo_dong.get(row) or HopThoaiDongGia(ticket=tickets[row])
        hop_theo_dong[row] = hop
        return hop

    monkeypatch.setattr(driver_mod.tradetab, "mo_hop_thoai_dong", mo)
    monkeypatch.setattr(driver_mod.ClosePositionDialog, "cho_mo", classmethod(cho_mo))
    return nhat_ky


def test_tim_thay_o_dong_dau_thi_dung_lai(driver: Mt5UiDriver,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    nhat_ky = _gia_lap_tim(monkeypatch, [TICKET, 111, 222])
    kq = driver.close(CloseRequest(position_id=TICKET))

    assert kq.status == "ok"
    assert nhat_ky == ["mo dong 0"], "Tim thay roi thi khong duoc do tiep"


def test_do_tiep_khi_dong_dau_la_vi_the_khac(driver: Mt5UiDriver,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    hop = {0: HopThoaiDongGia(ticket=111)}
    _gia_lap_tim(monkeypatch, [111, TICKET], hop)
    kq = driver.close(CloseRequest(position_id=TICKET))

    assert kq.status == "ok"
    assert hop[0].ghi_lai == ["cancel"], "Do truot phai HUY, tuyet doi khong bam"
    assert driver._bam.da_bam == [4242], "Chi duoc bam dung mot lan, o dong dung"


def test_dong_khong_mo_hop_thoai_thi_di_tiep_chu_khong_phai_loi(
        driver: Mt5UiDriver, monkeypatch: pytest.MonkeyPatch) -> None:
    """Danh sách có cả dòng tổng kết Balance — nó không mở hộp thoại nào, và đó là bình thường."""
    nhat_ky = _gia_lap_tim(monkeypatch, [None, TICKET])
    kq = driver.close(CloseRequest(position_id=TICKET))

    assert kq.status == "ok"
    assert "dong 0 khong mo hop thoai" in nhat_ky


def test_quet_het_ma_khong_thay_thi_la_already_closed_chu_khong_phai_loi(
        driver: Mt5UiDriver, monkeypatch: pytest.MonkeyPatch) -> None:
    """Quet het danh sach ma khong co vi the do nghia la NO DA DONG ROI (FR-18).

    Tra `rejected` o day se khien Bridge cho cap sang ORPHANED kem alert CRITICAL — tuc la bao
    dong cho dung thu dang le phai xay ra.
    """
    hop = {0: HopThoaiDongGia(ticket=111), 1: HopThoaiDongGia(ticket=222)}
    _gia_lap_tim(monkeypatch, [111, 222], hop)
    kq = driver.close(CloseRequest(position_id=TICKET))

    assert kq.status == "already_closed" and kq.clicked is False
    assert driver._bam.da_bam == []
    assert all(h.ghi_lai == ["cancel"] for h in hop.values())
    assert "111" in kq.reason and "222" in kq.reason


def test_danh_sach_rong_thi_rejected(driver: Mt5UiDriver,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    _gia_lap_tim(monkeypatch, [])
    kq = driver.close(CloseRequest(position_id=TICKET))
    assert kq.status == "rejected" and "rong" in kq.reason


def test_tab_trade_khong_mo_thi_rejected_chu_khong_doan(
        driver: Mt5UiDriver, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bấm vào danh sách của tab khác không đóng nhầm gì — nhưng cũng không được lặng lẽ thử."""
    _gia_lap_tim(monkeypatch, [TICKET])

    def no(_h: int) -> int:
        raise driver_mod.tradetab.TradeTabError("Tab Trade cua Toolbox dang khong mo")

    monkeypatch.setattr(driver_mod.tradetab, "tim_danh_sach", no)
    kq = driver.close(CloseRequest(position_id=TICKET))

    assert kq.status == "rejected" and "Tab Trade" in kq.reason
    assert driver._bam.da_bam == []


def test_dry_run_luon_rejected_va_khong_cham_giao_dien() -> None:
    d = driver_mod.DryRunDriver()
    kq = d.close(CloseRequest(position_id=TICKET, volume=0.02))

    assert isinstance(kq, Outcome)
    assert kq.status == "rejected" and kq.clicked is False
    assert "DRY_RUN" in kq.reason
    assert d.seen == [CloseRequest(position_id=TICKET, volume=0.02)]


def test_khong_dong_nao_mo_duoc_hop_thoai_thi_KHONG_ket_luan_da_dong(
        driver: Mt5UiDriver, monkeypatch: pytest.MonkeyPatch) -> None:
    """Day la cho de doc nham nhat cua ca phep tim, va doc nham no la mat tien.

    "Quet het khong thay" va "khong quet duoc gi" nhin giong het nhau tu ben ngoai, nhung hai
    ket luan di ve hai huong nguoc nhau: `already_closed` lam Bridge ghi cap thanh CLOSED, con
    thuc te co the la hop thoai dang ket, terminal treo, hoac danh sach doi hinh dang tren mot
    ban MT5 khac — va vi the van dang mo, van dang lo.
    """
    _gia_lap_tim(monkeypatch, [None, None])
    kq = driver.close(CloseRequest(position_id=TICKET))

    assert kq.status == "rejected", "Khong duoc ket luan da dong khi chua do duoc gi"
    assert kq.clicked is False
    assert driver._bam.da_bam == []


def test_hop_thoai_sot_lai_duoc_huy_truoc_moi_dong(
        driver: Mt5UiDriver, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mot hop thoai mo cham hon thoi gian cho van lam MT5 vao vong lap modal.

    Khong huy no thi moi dong sau deu do trong vo vong, va ket qua se la mot ket luan sai ve
    trang thai cua vi the.
    """
    sot = HopThoaiDongGia(ticket=999)
    da_huy: list[int] = []
    monkeypatch.setattr(driver_mod.ClosePositionDialog, "find",
                        classmethod(lambda cls, _pid: sot if not da_huy else None))
    goc_cancel = sot.cancel

    def cancel() -> None:
        da_huy.append(1)
        goc_cancel()

    sot.cancel = cancel  # type: ignore[method-assign]
    _gia_lap_tim(monkeypatch, [TICKET])
    monkeypatch.setattr(driver_mod.ClosePositionDialog, "find",
                        classmethod(lambda cls, _pid: sot if not da_huy else None))

    kq = driver.close(CloseRequest(position_id=TICKET))

    assert da_huy, "Phai huy hop thoai sot lai truoc khi do dong tiep theo"
    assert kq.status == "ok"
