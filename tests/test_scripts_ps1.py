"""Test các script PowerShell trong `scripts/` — phần không chạy được trong pytest.

Không test hành vi (chúng cần Windows service, NSSM, MT5), mà test **những bất biến đọc được từ
mã nguồn** — đúng những chỗ đã hỏng thật trên VPS và không có lưới nào đỡ:

* `PositionalBinding = $false`: xem docstring của test tương ứng. Một lần bind nhầm theo vị trí đã
  làm cả bước đăng ký dịch vụ gãy, và trước đó còn hỏng **trong im lặng** suốt nhiều bản.
* Không splat mảng vào một script `.ps1`: cùng gốc rễ, nhìn từ phía chỗ gọi.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _cac_script(project_root: Path) -> list[Path]:
    ds = sorted((project_root / "scripts").glob("*.ps1"))
    assert ds, "Khong tim thay script nao trong scripts/"
    return ds


def test_moi_script_tat_bind_theo_vi_tri(project_root: Path) -> None:
    """Mọi script có `param()` phải khai `PositionalBinding = $false`.

    Các script này có từ 5 tới 14 tham số, phần lớn `[string]`. Bind nhầm theo vị trí vì thế gần
    như luôn **thành công** và sai trong im lặng: `tro-ly.ps1` từng gọi `tao-dich-vu.ps1` bằng một
    splat **mảng**, nên `'-TacVuClickerMaster'` rơi gọn vào `$NguoiDung` như một chuỗi bình thường
    và tác vụ ClickerMaster **không bao giờ được đăng ký** — không một dòng lỗi nào. Lần sau nó
    mang hai phần tử thì `"clicker_master"` rơi vào `$AccountLogin` (kiểu int) và làm gãy cả bước
    đăng ký dịch vụ, phát hiện ra trong lần cài thật đầu tiên trên VPS (2026-09-21).

    Tắt bind theo vị trí biến mọi lần gọi sai thành một lỗi ồn ào ngay câu đầu tiên.
    """
    thieu = []
    for f in _cac_script(project_root):
        noi_dung = f.read_text(encoding="utf-8")
        if not re.search(r"^param\s*\(", noi_dung, re.M):
            continue
        if not re.search(r"\[CmdletBinding\([^)]*PositionalBinding\s*=\s*\$false", noi_dung):
            thieu.append(f.name)
    assert not thieu, f"Thieu PositionalBinding = $false: {thieu}"


@pytest.mark.parametrize("mau", [
    # `& $script ... @bien` với `$bien` là một MẢNG.
    r"\$(\w+)\s*=\s*@\(\s*['\"]-",
])
def test_khong_splat_mang_vao_mot_script_ps1(project_root: Path, mau: str) -> None:
    """Splat một **mảng** truyền các phần tử theo **vị trí**, không theo tên.

    `@('-TacVuClicker', 'clicker_master')` trông y hệt một lời gọi có tên nhưng không phải: muốn
    truyền theo tên thì phải splat một **hashtable**. Test này bắt biến nào được gán một mảng bắt
    đầu bằng chuỗi dạng `-TenThamSo` rồi bị splat vào một script `.ps1`.

    Splat mảng vào **file thực thi** (`python.exe`) thì đúng — đó chỉ là `argv` — nên chỉ soi các
    lời gọi tới `.ps1`.
    """
    for f in _cac_script(project_root):
        noi_dung = f.read_text(encoding="utf-8")
        for m in re.finditer(mau, noi_dung):
            bien = m.group(1)
            # Có bị splat vào một script .ps1 không? Tìm `& $<duong dan> ... @<bien>` trên cùng dòng
            # với một biến đường dẫn quen thuộc ($tao, $troLy, $caiDat, $kt...).
            for dong in noi_dung.splitlines():
                if f"@{bien}" in dong and re.search(r"&\s*\$(tao|troLy|caiDat|kt|goBo)\b", dong):
                    pytest.fail(
                        f"{f.name}: splat MANG `@{bien}` vao mot script .ps1 -- "
                        f"tham so se bind theo VI TRI. Dung hashtable.\n    {dong.strip()}")
