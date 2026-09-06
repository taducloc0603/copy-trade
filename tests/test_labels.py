"""Test bảng nhãn tiếng Việt (D-16).

Yêu cầu quan trọng nhất: thiếu một nhãn thì dashboard vẫn phải sống.
"""

from __future__ import annotations

import logging

import pytest

from bridge import labels_vi
from bridge.labels_vi import ALL_GROUPS, ENUM_GROUPS, PAIR_STATUS, RUN_MODE, label


@pytest.mark.parametrize("group_name", sorted(ALL_GROUPS))
def test_moi_nhan_la_chuoi_khong_rong(group_name: str) -> None:
    group = ALL_GROUPS[group_name]
    assert group, f"Nhóm {group_name} rỗng"
    for key, value in group.items():
        assert isinstance(key, str) and key, f"{group_name}: key không hợp lệ {key!r}"
        assert isinstance(value, str), f"{group_name}[{key}] không phải chuỗi"
        assert value.strip(), f"{group_name}[{key}] là chuỗi rỗng"


@pytest.mark.parametrize("group_name", sorted(ENUM_GROUPS))
def test_key_enum_la_tieng_anh_khong_dau_viet_hoa(group_name: str) -> None:
    """Key phải là enum tiếng Anh không dấu, viết hoa — đúng dạng lưu trong DB.

    Chỉ áp cho nhóm ánh xạ từ enum. Nhóm `UI` (phase 9) có key là id chuỗi giao diện chứ không
    phải enum, nên nó nằm ngoài phép kiểm này.
    """
    for key in ENUM_GROUPS[group_name]:
        assert key.isascii(), f"{group_name}: key {key!r} có ký tự ngoài ASCII"
        assert key == key.upper(), f"{group_name}: key {key!r} phải viết hoa"


def test_label_tra_ve_nhan_dung() -> None:
    assert label(PAIR_STATUS, "ORPHANED") == "Mất hedge"
    assert label(RUN_MODE, "PAUSED") == "Đã dừng"


def test_label_thieu_key_tra_ve_chinh_key_va_ghi_warning(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger=labels_vi.__name__)
    assert label(PAIR_STATUS, "BANANA") == "BANANA"
    assert any(record.levelno == logging.WARNING for record in caplog.records)


def test_label_khong_bao_gio_nem_exception() -> None:
    for group in ALL_GROUPS.values():
        assert label(group, "KHONG_TON_TAI") == "KHONG_TON_TAI"
    assert label({}, "") == ""


def test_moi_nhom_co_du_trang_thai_cot_loi() -> None:
    """Chốt lại các enum mà phase sau chắc chắn sẽ dùng, tránh xoá nhầm."""
    assert {"PENDING_OPEN", "OPEN", "CLOSED", "ORPHANED", "OPEN_FAILED"} <= set(PAIR_STATUS)
    assert {"RUNNING", "PAUSE_NEW_ENTRIES", "PAUSED", "EMERGENCY"} <= set(RUN_MODE)
