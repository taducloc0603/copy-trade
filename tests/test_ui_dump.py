"""Test cho cong cu khao sat `clicker.ui.dump`.

Phan logic thuan tuy (doc HWND, dung cay tu danh sach phang) test duoc o moi nen tang. Phan cham
Win32 thi khong — nhung dieu quan trong nhat ve file do KHONG phai no in ra gi, ma la no **khong
bam gi**, va viec do kiem duoc bang cach soi ma nguon.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clicker.ui import dump

DUMP_SRC = Path(dump.__file__).read_text(encoding="utf-8")


# -- doc_hwnd -----------------------------------------------------------------------------------

@pytest.mark.parametrize(("text", "mong_doi"), [
    ("0x1A2B3C", 0x1A2B3C),
    ("0x1a2b3c", 0x1A2B3C),
    ("  0X10  ", 16),
    ("123456", 123456),
    (" 42 ", 42),
])
def test_doc_hwnd_nhan_ca_hex_lan_thap_phan(text: str, mong_doi: int) -> None:
    """Nguoi dung chep handle tu chinh ban in cua cong cu nay, von in ra dang 0x..."""
    assert dump.doc_hwnd(text) == mong_doi


def test_doc_hwnd_tu_choi_chuoi_khong_phai_so() -> None:
    with pytest.raises(ValueError):
        dump.doc_hwnd("khong-phai-so")


# -- cay_theo_thu_bac ---------------------------------------------------------------------------

def test_cay_giu_dung_quan_he_cha_con() -> None:
    """EnumChildWindows tra ve toan bo hau due, nen do sau phai duoc dung lai tu GetParent."""
    goc = 100
    cha = {10: goc, 11: 10, 12: 11, 20: goc}
    ket_qua = dump.cay_theo_thu_bac(cha, goc)

    do_sau = dict(ket_qua)
    assert do_sau == {10: 0, 11: 1, 12: 2, 20: 0}
    # Con phai di ngay sau cha cua no, khong bi tach ra cuoi danh sach.
    assert [h for h, _ in ket_qua][:3] == [10, 11, 12]


def test_moi_control_deu_xuat_hien_dung_mot_lan() -> None:
    goc = 1
    cha = {2: 1, 3: 2, 4: 2, 5: 4}
    ket_qua = dump.cay_theo_thu_bac(cha, goc)
    assert sorted(h for h, _ in ket_qua) == [2, 3, 4, 5]
    assert len(ket_qua) == len(set(h for h, _ in ket_qua))


def test_node_mo_coi_van_duoc_in_ra_o_goc() -> None:
    """Mat mot control khoi ban do nguy hiem hon nhieu so voi viec no hien sai cho mot bac."""
    goc = 1
    cha = {2: 1, 9: 777}  # 777 khong nam trong tap
    ket_qua = dump.cay_theo_thu_bac(cha, goc)
    assert dict(ket_qua) == {2: 0, 9: 0}


def test_vong_lap_cha_con_khong_lam_treo() -> None:
    """Quan he vong khong bao gio nen xay ra, nhung mot cong cu do bi treo thi vo dung."""
    goc = 1
    cha = {2: 3, 3: 2}
    ket_qua = dump.cay_theo_thu_bac(cha, goc)
    assert sorted(h for h, _ in ket_qua) == [2, 3]


def test_khong_co_control_nao_thi_tra_ve_rong() -> None:
    assert dump.cay_theo_thu_bac({}, 1) == []


# -- dong lenh ----------------------------------------------------------------------------------

def test_menu_can_title() -> None:
    """--menu ma khong biet terminal nao thi khong co gi de doc; phai bao ro chu khong doan."""
    args = dump.build_parser().parse_args(["--menu"])
    assert args.menu and not args.title


def test_mac_dinh_khong_in_control_an() -> None:
    args = dump.build_parser().parse_args([])
    assert not args.all_controls and not args.listview and args.title == ""


def test_khong_chay_duoc_win32_thi_tra_ma_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dump.win32, "is_available", lambda: False)
    assert dump.main([]) == 2


# -- doc ket qua ListView cho dung ---------------------------------------------------------------
#
# Do tren Windows 11 ngay 2026-09-10: mot control KHONG phai ListView van tra ve 0 cho
# LVM_GETITEMCOUNT chu khong bao loi. Nen "0" mot minh no khong bao gio duoc coi la thanh cong.

def _gia_lap_listview(monkeypatch: pytest.MonkeyPatch, lop: str, dem: int | None,
                      text: str = "") -> None:
    monkeypatch.setattr(dump.win32, "is_available", lambda: True)
    monkeypatch.setattr(dump.win32, "is_window", lambda _h: True)
    monkeypatch.setattr(dump.win32, "get_class_name", lambda _h: lop)
    monkeypatch.setattr(dump.win32, "get_process_id", lambda _h: 4242)
    monkeypatch.setattr(dump.win32, "listview_item_count", lambda _h: dem)
    monkeypatch.setattr(dump.win32, "listview_item_text",
                        lambda _h, _r, _c=0, **_kw: text)


def test_control_tu_ve_dem_ra_0_van_la_ket_qua_do(monkeypatch: pytest.MonkeyPatch,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    """Day la cau tra loi quan trong nhat cua Buoc 0 — no khong duoc phep doc nham thanh xanh."""
    _gia_lap_listview(monkeypatch, "MetaQuotes::Toolbox", 0)
    assert dump.main(["--listview", "0x1234"]) == 1
    ra = capsys.readouterr().out
    assert "CANH BAO" in ra
    assert "MT5 tu ve" in ra


def test_listview_that_nhung_rong_cung_la_ket_qua_do(monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    _gia_lap_listview(monkeypatch, dump.win32.LISTVIEW_CLASS, 0)
    assert dump.main(["--listview", "0x1234"]) == 1
    assert "CANH BAO" not in capsys.readouterr().out


def test_doc_duoc_dong_thi_in_ra_va_tra_ma_0(monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    _gia_lap_listview(monkeypatch, dump.win32.LISTVIEW_CLASS, 2, text="71489808")
    assert dump.main(["--listview", "0x1234"]) == 0
    assert "71489808" in capsys.readouterr().out


def test_control_treo_khong_bi_lan_voi_control_rong(monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    _gia_lap_listview(monkeypatch, dump.win32.LISTVIEW_CLASS, None)
    assert dump.main(["--listview", "0x1234"]) == 1
    assert "treo" in capsys.readouterr().out


def test_hwnd_khong_hop_le_tra_ma_2(monkeypatch: pytest.MonkeyPatch) -> None:
    _gia_lap_listview(monkeypatch, dump.win32.LISTVIEW_CLASS, 5)
    monkeypatch.setattr(dump.win32, "is_window", lambda _h: False)
    assert dump.main(["--listview", "0x1234"]) == 2


# -- bat bien: cong cu do khong duoc tac dong ---------------------------------------------------

@pytest.mark.parametrize("ham_tac_dong", [
    "post_click", "post_command", "post_close", "set_text", "type_text",
])
def test_dump_khong_goi_bat_ky_ham_tac_dong_nao(ham_tac_dong: str) -> None:
    """Bat bien cua ca file: chay `dump` trong luc co lenh that dang mo phai vo hai.

    Kiem bang cach soi ma nguon chu khong bang loi hua trong docstring — loi hua khong chan duoc
    ai do them mot cu bam vao day de "tien debug".
    """
    assert ham_tac_dong not in DUMP_SRC


def test_dump_khong_import_gi_ngoai_win32_va_probe() -> None:
    """Cong cu do khong duoc dung toi Bridge, DB hay driver — no phai chay duoc khi moi thu khac tat."""
    assert "from clicker.ui import probe, win32" in DUMP_SRC
    assert "driver" not in DUMP_SRC
    assert "bridge" not in DUMP_SRC.lower().replace("copybridge", "")
