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


def test_bang_kiem_may_sach_loc_hep_dung_nhu_luc_giet(project_root: Path) -> None:
    """Bảng kiểm "máy đã sạch" phải dùng **đúng** bộ lọc mà `go-bo.ps1` dùng để giết tiến trình.

    Bản cũ in `CommandLine -like '*CopyBridge*'`, và nó khớp cả `notepad.exe` đang mở một file
    trong thư mục cài — đã báo nhầm thật trên VPS 2026-09-22 khi người dùng kiểm sau lần gỡ. Một
    bảng kiểm kêu oan là bảng kiểm người ta thôi đọc, nên nó phải hẹp bằng đúng
    `tien_trinh_cua_tool` / `tien_trinh_wrapper`: `python.exe` chạy `-m bridge`/`-m clicker`, và
    `powershell.exe` chạy script **trong thư mục cài**.
    """
    cho = {
        "scripts/go-bo.ps1": (project_root / "scripts" / "go-bo.ps1"),
        "docs/CAI-DAT-VPS.md": (project_root / "docs" / "CAI-DAT-VPS.md"),
    }
    for ten, duong_dan in cho.items():
        noi_dung = duong_dan.read_text(encoding="utf-8")
        assert "-like '*CopyBridge*'" not in noi_dung, (
            f"{ten}: bo loc rong lai quay ve -- no khop ca notepad.exe mo file trong thu muc cai"
        )
        assert "-m (bridge|clicker)" in noi_dung, (
            f"{ten}: bang kiem phai loc python.exe theo '-m bridge'/'-m clicker'"
        )


def test_tai_lieu_khong_con_bao_dung_restart_service(project_root: Path) -> None:
    """Không chỗ nào trong `docs/` được **bảo người dùng chạy** `Restart-Service CopyBridge`.

    SCM báo dịch vụ đã dừng trước khi `python.exe` con thoát hẳn, nên bản mới lên có thể thấy cổng
    agent còn bị giữ và **cố ý không chạy**; Windows chỉ nói "Failed to start service" và không một
    chữ nào về cổng. Đã xảy ra thật trên VPS 2026-09-22 — đúng lúc người dùng làm theo tài liệu.
    `scripts/khoi-dong-lai.ps1` làm đủ thứ tự, nên tài liệu phải trỏ vào nó.

    Nhắc `Restart-Service` để **nói đừng dùng** thì được: dòng đó phải có chữ "đừng dùng".
    """
    for duong_dan in sorted((project_root / "docs").glob("*.md")):
        for so, dong in enumerate(duong_dan.read_text(encoding="utf-8").splitlines(), 1):
            if "Restart-Service" not in dong:
                continue
            assert "đừng dùng" in dong, (
                f"{duong_dan.name}:{so} con bao chay Restart-Service: {dong.strip()[:90]}"
            )


def test_ham_tra_ve_mang_luon_duoc_boc_o_cho_goi(project_root: Path) -> None:
    """Hàm `return @(...)` mà được **gán** vào biến thì phải bọc lại bằng `@(...)`.

    PowerShell trải phẳng giá trị trả về của hàm: mảng rỗng thành `$null`, một phần tử thành scalar.
    Với `Set-StrictMode` — mọi script ở đây đều bật — `$null.Count` nổ ngay:

        The property 'Count' cannot be found on this object.

    Đó là cách `khoi-dong-lai.ps1` chết ở lần chạy đầu trên VPS (2026-09-22), và nó chết đúng ở
    nhánh **mừng nhất**: cổng đã được nhả, không có tiến trình mồ côi nào. Tức nhánh hỏng thì chạy
    được, nhánh lành thì nổ — nên chạy thử một lần rất dễ kết luận là "đã kiểm rồi".

    Chỉ soi dạng **gán** `$x = ten ...`. Lời gọi trong một pipeline đã nằm trong `@(...)` của vế
    phải thì vô hại, và bắt cả chúng thì test kêu oan — mà một test kêu oan sẽ bị nới ra cho qua.
    """
    for duong_dan in _cac_script(project_root):
        noi_dung = duong_dan.read_text(encoding="utf-8")
        tra_mang = {
            ten
            for ten, than in re.findall(
                r"^function\s+([A-Za-z_][\w-]*)\s*(?:\([^)]*\))?\s*\{(.*?)^\}",
                noi_dung,
                re.DOTALL | re.MULTILINE,
            )
            if "return @(" in than
        }
        for so, dong in enumerate(noi_dung.splitlines(), 1):
            if dong.lstrip().startswith("#"):
                continue
            gan = re.match(r"\s*\$\w+\s*=\s*(.+)$", dong)
            if gan is None:
                continue
            ve_phai = gan.group(1).lstrip()
            ten = re.match(r"([A-Za-z_][\w-]*)\b", ve_phai)
            assert ten is None or ten.group(1) not in tra_mang, (
                f"{duong_dan.name}:{so}: gan truc tiep tu `{ten.group(1)}` (ham tra ve mang) ma "
                f"khong boc @() -- mang rong se thanh $null, va .Count nem duoi Set-StrictMode"
            )
