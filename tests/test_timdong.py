"""Test thuần cho thứ tự dò tab Trade (`clicker/ui/timdong.py`) — không Win32, không giả lập giao diện."""

from __future__ import annotations

import pytest

from clicker.ui.timdong import BAN_DO, NHI_PHAN, TUAN_TU, PhepDo, bo_dong, ghi_ban_do


def _chay(tickets: list[int | None], dich: int,
          ban_do: dict[int, int] | None = None) -> tuple[list[int], PhepDo]:
    """Chạy một phép dò trên danh sách giả. Trả về thứ tự dòng đã mở."""
    phep = PhepDo(len(tickets), dich, ban_do)
    da_mo: list[int] = []
    while (row := phep.tiep_theo()) is not None:
        assert row not in da_mo, f"Mo lai dong {row} lan hai"
        assert 0 <= row < len(tickets)
        da_mo.append(row)
        phep.ghi_nhan(row, tickets[row])
    return da_mo, phep


#: 10 vị thế sắp theo thời gian mở, rồi dòng tổng kết Balance — hình dạng thật của tab Trade.
TANG = [*range(101, 111), None]
GIAM = [*range(110, 100, -1), None]


def test_dong_thu_chin_trong_muoi_khong_con_mo_tam_hop_thoai() -> None:
    """Bài của chính sự cố: bản cũ mở dòng 0..8 rồi mới tới dòng 8."""
    da_mo, phep = _chay(TANG, 109)
    assert phep.thay == 8
    assert len(da_mo) <= 4
    assert phep.che_do == NHI_PHAN


@pytest.mark.parametrize("dich", range(101, 111))
def test_sap_tang_moi_vi_the_toi_da_bon_lan_mo(dich: int) -> None:
    da_mo, phep = _chay(TANG, dich)
    assert phep.thay == TANG.index(dich)
    assert len(da_mo) <= 4, f"Dich {dich}: mo {da_mo}"


@pytest.mark.parametrize("dich", range(101, 111))
def test_sap_giam_tu_suy_ra_chieu(dich: int) -> None:
    """Chiều không giả định cứng. Điểm đọc đầu đoán tăng, sai thì tốn thêm đúng một lần mở."""
    da_mo, phep = _chay(GIAM, dich)
    assert phep.thay == GIAM.index(dich)
    assert len(da_mo) <= 5, f"Dich {dich}: mo {da_mo}"


def test_thu_tu_lon_xon_thi_chuyen_tuan_tu_va_van_tim_thay() -> None:
    """Người dùng bấm sắp theo Symbol/Profit: nhị phân sẽ loại oan cả nửa danh sách."""
    tickets = [105, 101, 109, 103, 110, 102, 108, 104, 107, 106, None]
    for dich in range(101, 111):
        _, phep = _chay(tickets, dich)
        assert phep.thay == tickets.index(dich), f"Khong tim thay {dich}"


def test_khong_co_dich_thi_mo_HET_moi_dong() -> None:
    """`already_closed` chỉ được kết luận sau khi mở hết. Suy từ nhị phân là đặt cược sổ sách."""
    da_mo, phep = _chay(TANG, 999)
    assert phep.thay is None
    assert sorted(da_mo) == list(range(len(TANG)))
    assert phep.che_do == TUAN_TU


def test_khong_co_dich_nam_giua_hai_ticket_van_mo_het() -> None:
    tickets = [100, 102, 104, 106, None]
    da_mo, phep = _chay(tickets, 103)
    assert phep.thay is None and sorted(da_mo) == list(range(5))


def test_ban_do_trung_thi_mot_lan_mo() -> None:
    da_mo, phep = _chay(TANG, 109, ban_do={109: 8})
    assert da_mo == [8]
    assert phep.che_do == BAN_DO


def test_ban_do_sai_van_tim_thay_bang_nhi_phan() -> None:
    da_mo, phep = _chay(TANG, 109, ban_do={109: 2})
    assert da_mo[0] == 2
    assert phep.thay == 8


def test_ban_do_tro_ra_ngoai_danh_sach_thi_bo_qua() -> None:
    _, phep = _chay(TANG, 109, ban_do={109: 40})
    assert phep.thay == 8 and phep.che_do == NHI_PHAN


def test_danh_sach_ngan_giu_nguyen_thu_tu_tu_tren_xuong() -> None:
    """Hai dòng: nhị phân không tiết kiệm được gì, và hành vi cũ đã được đo trên VPS."""
    assert _chay([None, 5], 5)[0] == [0, 1]
    assert _chay([4, 5], 5)[0] == [0, 1]
    assert _chay([5], 5)[0] == [0]
    assert _chay([], 5)[0] == []


def test_dong_khong_mo_hop_thoai_khong_lam_sai_thu_tu() -> None:
    """Dòng Balance ở giữa (danh sách lạ) bị bỏ khỏi phép so sánh, không bị hiểu là mâu thuẫn."""
    tickets = [101, 102, None, 104, 105, 106]
    _, phep = _chay(tickets, 105)
    assert phep.thay == 4 and phep.che_do == NHI_PHAN


def test_mo_lai_cho_xem_lai_dung_mot_lan() -> None:
    """Hộp thoại mở trễ làm một dòng bị ghi sai — dòng đó phải được xem lại, nhưng không vô hạn."""
    phep = PhepDo(2, 999)
    lan_mo: list[int] = []
    while (row := phep.tiep_theo()) is not None:
        lan_mo.append(row)
        phep.ghi_nhan(row, None)
        phep.mo_lai(row)
    assert sorted(lan_mo) == [0, 0, 1, 1]
    assert phep.so_lan_mo == 4
    assert phep.mo_lai(5) is False


def test_bo_dong_dich_cac_dong_ben_duoi_len_mot() -> None:
    ban_do = {101: 0, 105: 4, 109: 8, 110: 9}
    bo_dong(ban_do, 105, 4)
    assert ban_do == {101: 0, 109: 7, 110: 8}


def test_ghi_ban_do_xoa_muc_cu_tro_vao_cung_dong() -> None:
    ban_do = {101: 0, 109: 3}
    ghi_ban_do(ban_do, 3, 104)
    assert ban_do == {101: 0, 104: 3}
    ghi_ban_do(ban_do, 0, None)
    assert ban_do == {104: 3}
