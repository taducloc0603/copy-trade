"""Test tính volume (plan mục 6.3).

Đây là chỗ tiền bị tính sai mà không ai để ý. Trọng tâm là sai số dấu phẩy động và các
điều kiện biên quanh `volume_min`.
"""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from bridge.engine.sizing import (
    SKIP_BELOW_MIN,
    SKIP_MAX_OPEN_PAIRS,
    SKIP_MAX_TOTAL_VOLUME,
    SKIP_MAX_VOLUME_PER_ORDER,
    SKIP_ZERO_AFTER_ROUNDING,
    SizingInputs,
    compute_client_volume,
    inherit,
    resolve_direction,
    round_to_step,
)


def codes(result) -> set[str]:
    return {code for _, code, _ in result.alerts}


# ---------------------------------------------------------------------------------------------
# Bước 2 — chiều lệnh
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("master", "mode", "expected"),
    [("BUY", "SAME", "BUY"), ("SELL", "SAME", "SELL"),
     ("BUY", "OPPOSITE", "SELL"), ("SELL", "OPPOSITE", "BUY")],
)
def test_chieu_lenh(master: str, mode: str, expected: str) -> None:
    assert resolve_direction(master, mode) == expected


def test_chieu_lenh_master_khong_hop_le_bi_chan() -> None:
    with pytest.raises(ValueError):
        resolve_direction("LONG", "SAME")


def test_ke_thua_tu_client_account_khi_symbol_map_null() -> None:
    assert inherit(None, "OPPOSITE") == "OPPOSITE"
    assert inherit("SAME", "OPPOSITE") == "SAME"
    assert inherit(None, 0.5) == 0.5
    assert inherit(0.3, 0.5) == 0.3


# ---------------------------------------------------------------------------------------------
# Bước 5 — làm tròn và sai số dấu phẩy động
# ---------------------------------------------------------------------------------------------


def test_khong_bi_sai_so_dau_phay_dong_kinh_dien() -> None:
    """`0.3 / 0.1` trong float cho 2.9999...; làm tròn xuống ra 2 bước thay vì 3."""
    assert float(0.3 / 0.1) < 3.0, "Tien de cua test nay: float that su sai"
    assert round_to_step(Decimal("0.3"), Decimal("0.1"), "DOWN") == Decimal("0.3")


@pytest.mark.parametrize(
    ("raw", "step", "mode", "expected"),
    [
        ("0.0231", "0.01", "DOWN", "0.02"),
        ("0.0231", "0.01", "NEAREST", "0.02"),
        ("0.029", "0.01", "NEAREST", "0.03"),
        ("0.029", "0.01", "DOWN", "0.02"),
        ("0.005", "0.01", "NEAREST", "0.01"),
        ("0.005", "0.01", "DOWN", "0.00"),
        ("1.0", "1.0", "DOWN", "1.0"),
        ("7.7", "0.1", "DOWN", "7.7"),
    ],
)
def test_lam_tron_theo_buoc(raw: str, step: str, mode: str, expected: str) -> None:
    assert round_to_step(Decimal(raw), Decimal(step), mode) == Decimal(expected)


def test_200_to_hop_ngau_nhien_luon_ra_boi_so_chinh_xac_cua_step() -> None:
    """Kiểm tra bằng `Decimal`, không phải bằng float — nếu không thì chính test cũng sai."""
    rng = random.Random(20260906)
    steps = ["0.01", "0.1", "0.001", "1", "0.05", "0.25"]
    for _ in range(200):
        step = Decimal(rng.choice(steps))
        master_volume = round(rng.uniform(0.01, 50.0), 2)
        multiplier = round(rng.uniform(0.01, 3.0), 4)
        result = compute_client_volume(SizingInputs(
            master_volume=master_volume, multiplier=multiplier,
            volume_min=float(step), volume_max=1e9, volume_step=float(step),
        ))
        if result.skipped:
            continue
        value = Decimal(str(result.volume))
        assert value % step == 0, (
            f"volume {value} khong phai boi so cua step {step} "
            f"(master={master_volume} x {multiplier})"
        )


# ---------------------------------------------------------------------------------------------
# Ví dụ trong plan
# ---------------------------------------------------------------------------------------------


def test_vi_du_trong_plan_master_007_he_so_033() -> None:
    """Plan mục 6.3: Master 0.07, hệ số 0.33 → Client 0.02, tỷ lệ thật 0.2857 chứ không phải 0.33."""
    result = compute_client_volume(SizingInputs(
        master_volume=0.07, multiplier=0.33, volume_step=0.01, volume_min=0.01,
    ))
    assert result.volume == 0.02
    assert result.effective_multiplier == pytest.approx(0.2857, abs=1e-4)
    assert result.effective_multiplier != pytest.approx(0.33, abs=1e-4)


def test_master_100_he_so_050() -> None:
    result = compute_client_volume(SizingInputs(master_volume=1.0, multiplier=0.5))
    assert result.volume == 0.5
    assert result.effective_multiplier == pytest.approx(0.5)


# ---------------------------------------------------------------------------------------------
# Bước 6 — dưới mức tối thiểu (D-18)
# ---------------------------------------------------------------------------------------------


def test_duoi_muc_toi_thieu_thi_bo_qua_khong_tu_nang_volume() -> None:
    """D-18: không bao giờ tự nâng volume. Hedge thừa là vị thế không ai yêu cầu."""
    result = compute_client_volume(SizingInputs(
        master_volume=0.01, multiplier=0.5, volume_min=0.01, volume_step=0.01,
    ))
    assert result.skipped
    assert result.volume is None
    assert result.skip_reason in (SKIP_BELOW_MIN, SKIP_ZERO_AFTER_ROUNDING)
    assert "VOLUME_BELOW_MIN" in codes(result)


def test_duoi_muc_toi_thieu_voi_use_min_thi_mo_bang_muc_toi_thieu() -> None:
    result = compute_client_volume(SizingInputs(
        master_volume=0.01, multiplier=0.5, volume_min=0.01, volume_step=0.01,
        below_min_policy="USE_MIN",
    ))
    assert result.volume == 0.01
    assert "VOLUME_RAISED_TO_MIN" in codes(result)
    assert [level for level, code, _ in result.alerts if code == "VOLUME_RAISED_TO_MIN"] == ["INFO"]
    assert result.effective_multiplier == pytest.approx(1.0), "Ty le hedge bi lech, va phai ghi nhan"


def test_bo_qua_luon_kem_canh_bao() -> None:
    """"Không copy" mà không biết vì sao là tình huống tệ nhất khi vận hành."""
    for inputs in (
        SizingInputs(master_volume=0.01, multiplier=0.01),
        SizingInputs(master_volume=1.0, multiplier=1.0, max_volume_per_order=0.5),
        SizingInputs(master_volume=1.0, multiplier=1.0, max_total_volume=0.5),
        SizingInputs(master_volume=1.0, multiplier=1.0, max_open_pairs=1, current_open_pairs=1),
    ):
        result = compute_client_volume(inputs)
        assert result.skipped
        assert result.alerts, "Bo qua ma khong canh bao"


# ---------------------------------------------------------------------------------------------
# Bước 5 — kẹp theo volume_max
# ---------------------------------------------------------------------------------------------


def test_vuot_volume_max_thi_kep_va_canh_bao() -> None:
    result = compute_client_volume(SizingInputs(
        master_volume=100.0, multiplier=1.0, volume_max=50.0, volume_step=0.01,
    ))
    assert result.volume == 50.0
    assert "VOLUME_CLAMPED" in codes(result)


# ---------------------------------------------------------------------------------------------
# Bước 4 — quy đổi contract size
# ---------------------------------------------------------------------------------------------


def test_contract_size_bang_nhau_thi_khong_quy_doi() -> None:
    result = compute_client_volume(SizingInputs(
        master_volume=1.0, multiplier=1.0,
        master_contract_size=100.0, client_contract_size=100.0,
    ))
    assert result.volume == 1.0
    assert result.notes == [], "Khong duoc quy doi khi hai san giong nhau"


def test_contract_size_khac_nhau_thi_quy_doi_va_ghi_chu() -> None:
    """Giữ nguyên giá trị danh nghĩa: 1 lot x 100 = 100 lot x 1."""
    result = compute_client_volume(SizingInputs(
        master_volume=1.0, multiplier=1.0, volume_max=1000.0,
        master_contract_size=100.0, client_contract_size=1.0,
    ))
    assert result.volume == 100.0
    assert result.notes, "Quy doi contract size phai duoc ghi lai, vi no de gay bat ngo"


def test_thieu_contract_size_thi_khong_quy_doi() -> None:
    result = compute_client_volume(SizingInputs(
        master_volume=1.0, multiplier=1.0, master_contract_size=None, client_contract_size=1.0,
    ))
    assert result.volume == 1.0


# ---------------------------------------------------------------------------------------------
# Bước 7 — hạn mức rủi ro
# ---------------------------------------------------------------------------------------------


def test_vuot_han_muc_moi_lenh() -> None:
    result = compute_client_volume(SizingInputs(
        master_volume=1.0, multiplier=1.0, max_volume_per_order=0.5,
    ))
    assert result.skip_reason == SKIP_MAX_VOLUME_PER_ORDER


def test_vuot_tong_volume() -> None:
    result = compute_client_volume(SizingInputs(
        master_volume=1.0, multiplier=1.0, max_total_volume=5.0, current_total_volume=4.5,
    ))
    assert result.skip_reason == SKIP_MAX_TOTAL_VOLUME


def test_vua_du_tong_volume_thi_van_cho_qua() -> None:
    result = compute_client_volume(SizingInputs(
        master_volume=0.5, multiplier=1.0, max_total_volume=5.0, current_total_volume=4.5,
    ))
    assert not result.skipped
    assert result.volume == 0.5


def test_cham_han_so_cap_dang_mo() -> None:
    result = compute_client_volume(SizingInputs(
        master_volume=1.0, multiplier=1.0, max_open_pairs=3, current_open_pairs=3,
    ))
    assert result.skip_reason == SKIP_MAX_OPEN_PAIRS


def test_khong_dat_han_muc_thi_khong_chan_gi() -> None:
    result = compute_client_volume(SizingInputs(master_volume=1.0, multiplier=1.0))
    assert not result.skipped
    assert result.alerts == []


# ---------------------------------------------------------------------------------------------
# Thông số hỏng
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "inputs",
    [
        SizingInputs(master_volume=0.0, multiplier=1.0),
        SizingInputs(master_volume=-1.0, multiplier=1.0),
        SizingInputs(master_volume=1.0, multiplier=1.0, volume_step=0.0),
        SizingInputs(master_volume=1.0, multiplier=1.0, volume_min=0.0),
    ],
)
def test_thong_so_hong_thi_bo_qua_va_canh_bao_chu_khong_sap(inputs: SizingInputs) -> None:
    result = compute_client_volume(inputs)
    assert result.skipped
    assert result.alerts
