"""Bộ canh vòng sự kiện phải chỉ đúng chỗ đang chặn, và im lặng khi không có gì chặn."""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from bridge.watchdog import CanhVongSuKien


def ham_chan_vong_su_kien() -> None:
    time.sleep(0.5)


async def test_ghi_stack_cua_ham_dang_chan(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="bridge.watchdog")
    canh = CanhVongSuKien(nhip_sec=0.02, nguong_sec=0.15)
    await canh.start()
    try:
        await asyncio.sleep(0.1)
        ham_chan_vong_su_kien()
        await asyncio.sleep(0.15)
    finally:
        await canh.stop()

    assert canh.so_lan_chan == 1
    loi = "\n".join(r.getMessage() for r in caplog.records)
    assert "bi chan" in loi
    assert "ham_chan_vong_su_kien" in loi, "Phai chi ra dung ham dang chan"
    assert "chay lai sau" in loi


async def test_khong_bao_khi_vong_chay_binh_thuong(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="bridge.watchdog")
    canh = CanhVongSuKien(nhip_sec=0.02, nguong_sec=0.15)
    await canh.start()
    try:
        for _ in range(10):
            await asyncio.sleep(0.03)
    finally:
        await canh.stop()
    assert canh.so_lan_chan == 0
    assert not caplog.records
