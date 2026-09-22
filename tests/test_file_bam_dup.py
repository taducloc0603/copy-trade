"""Hai file bấm đúp: `CAI-DAT.cmd` và `CAP-NHAT.cmd`.

Vì sao `.cmd` chứ không `.ps1`: Windows mặc định **mở `.ps1` bằng Notepad** khi bấm đúp. Một file
bảo người dùng "bấm đúp để chạy" mà bấm đúp ra Notepad là một file hỏng.

Cả hai file **không chứa logic** nào — chúng gọi `scripts/cai-dat.ps1`. Chép logic sang đó là tạo
bản thứ hai sẽ lệch với bản thật. Các test dưới đây khoá đúng điều đó, và khoá những đường dẫn
chúng trỏ tới: một lần đổi tên file là bootstrap hỏng trên **máy chưa cài gì**, nơi không có gì để
gỡ lỗi.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

HAI_FILE = ("CAI-DAT.cmd", "CAP-NHAT.cmd")


@pytest.mark.parametrize("ten", HAI_FILE)
def test_bam_dup_khong_bay_mat_cua_so(project_root: Path, ten: str) -> None:
    """Phải có `pause`, nếu không cửa sổ đóng ngay và người dùng không đọc được gì.

    Đây là cách hỏng đặc trưng của một `.cmd` bấm đúp: nó chạy xong, cửa sổ biến mất, và người
    dùng không biết nó đã làm gì hay hỏng ở đâu.
    """
    noi = (project_root / ten).read_text(encoding="utf-8")
    assert re.search(r"^pause\s*$", noi, re.M), f"{ten}: thieu `pause`"


@pytest.mark.parametrize("ten", HAI_FILE)
def test_tu_xin_quyen_administrator(project_root: Path, ten: str) -> None:
    """Thiếu quyền thì script thất bại ở giữa chừng, để lại một bản cài dở dang.

    Tệ hơn là không bắt đầu: cài Python, git và đăng ký dịch vụ đều cần Administrator, và chúng
    nằm rải khắp `cai-dat.ps1` chứ không dồn ở đầu.
    """
    noi = (project_root / ten).read_text(encoding="utf-8")
    assert "net session" in noi, f"{ten}: khong kiem quyen Administrator"
    assert "RunAs" in noi, f"{ten}: khong tu xin quyen"


@pytest.mark.parametrize("ten", HAI_FILE)
def test_khong_chep_logic_cai_dat_sang_file_bam_dup(project_root: Path, ten: str) -> None:
    """Hai file này chỉ được **gọi** `cai-dat.ps1`, không tự làm việc của nó.

    Một bản thứ hai của cùng một quy trình là một bản sẽ lệch — và lệch ở đường cài đặt thì lộ ra
    trên máy người dùng, không lộ ra ở đây.
    """
    noi = (project_root / ten).read_text(encoding="utf-8")
    assert "cai-dat.ps1" in noi, f"{ten}: khong goi cai-dat.ps1"
    # Chỉ xét dòng LÀM VIỆC: `rem`, `echo` và `Write-Host` là chữ cho người đọc, và một câu hướng
    # dẫn "cài git: winget install ..." không phải là tự đi cài git.
    for dong in noi.splitlines():
        cau = dong.strip()
        if not cau or cau.lower().startswith(("rem ", "echo", "::")) or "Write-Host" in cau:
            continue
        for cam in ("winget install", "python -m venv", "nssm ", "git clone"):
            assert cam not in cau, f"{ten}: dang tu lam viec cua cai-dat.ps1 ({cam!r}): {cau[:60]}"


def test_moi_duong_dan_trong_file_bam_dup_deu_co_that(project_root: Path) -> None:
    r"""Mọi `scripts\*.ps1` mà hai file nhắc tới phải tồn tại trong kho.

    `CAI-DAT.cmd` chạy trên một máy **chưa có gì**: sai một đường dẫn ở đó là hỏng đúng lúc không
    có gì để gỡ lỗi, và thông báo sẽ là một lỗi tải 404 chứ không phải "thiếu file".
    """
    for ten in HAI_FILE:
        noi = (project_root / ten).read_text(encoding="utf-8")
        for duong in set(re.findall(r"scripts[\/][\w-]+\.ps1", noi)):
            that = project_root / duong.replace("\\", "/")
            assert that.exists(), f"{ten} tro toi {duong} nhung file do khong co"


def test_url_bootstrap_tro_dung_nhanh_va_dung_file(project_root: Path) -> None:
    """URL raw trong `CAI-DAT.cmd` phải trỏ đúng nhánh `main` và đúng file có thật."""
    noi = (project_root / "CAI-DAT.cmd").read_text(encoding="utf-8")
    url = re.findall(r"https://raw\.githubusercontent\.com/\S+", noi)
    assert url, "CAI-DAT.cmd khong co URL bootstrap nao"
    for u in url:
        u = u.rstrip("^\"' \r\n")
        assert "/main/" in u, f"URL khong tro nhanh main: {u}"
        duoi = u.split("/main/", 1)[1]
        assert (project_root / duoi).exists(), f"URL tro toi {duoi} nhung file do khong co"
