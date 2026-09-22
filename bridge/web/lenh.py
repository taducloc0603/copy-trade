"""Chạy một **danh sách trắng cố định** các lệnh chẩn đoán, từ dashboard.

Vì sao có module này: tab Hướng dẫn in ra những câu lệnh như ``.\\scripts\\kiem-tra.ps1`` và bảo
người dùng mở PowerShell chạy. Người vận hành hệ thống này không phải dân kỹ thuật — mở PowerShell,
đứng đúng thư mục, dán đúng dòng, rồi tự đọc output là bốn chỗ hỏng được.

Vì sao nó nguy hiểm, và cách chặn: dashboard **không còn xác thực** (D-39), nên một endpoint chạy
lệnh là một đường thực thi mã cho bất kỳ ai chạm tới cổng 8080. Nên:

* Trình duyệt chỉ gửi **mã hành động**. Nó KHÔNG BAO GIỜ gửi câu lệnh, tham số, đường dẫn hay tên
  file. Mã lạ thì từ chối, không đoán.
* Mỗi lệnh là một `argv` **dựng sẵn trong file này**, chạy không qua shell (`create_subprocess_exec`
  chứ không phải `_shell`), nên không có chỗ nào để một chuỗi lạ chen vào.
* Chỉ những lệnh **chỉ đọc** (liệt kê, kiểm tra, tình hình) và lệnh **biên dịch EA**. Không lệnh nào
  sửa cấu hình, chạm database hay đụng tới vị thế — những việc đó đã có nút riêng trên trang.
* Có hạn giờ. Một lệnh treo mà không có hạn giờ là một dashboard treo theo.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

#: Cắt bớt output trước khi đẩy xuống trình duyệt. `kiem-tra.ps1` in vài trăm dòng, và một khối
#: chữ dài hơn màn hình thì người dùng bỏ qua — đúng thứ ta đang cố sửa.
GIOI_HAN_DONG = 120


@dataclass(frozen=True)
class LenhChay:
    """Một lệnh chạy được từ dashboard."""

    #: Cách dựng `argv`. Nhận thư mục gốc, trả về danh sách tham số.
    dung_argv: object
    #: Hạn giờ, giây.
    han_giay: int = 120
    #: Lệnh này có ghi ra đĩa không. Chỉ để ghi log cho đúng, không đổi hành vi.
    ghi_dia: bool = False


def _venv_python(goc: Path) -> Path:
    return goc / ".venv" / "Scripts" / "python.exe"


def _powershell() -> str:
    # `powershell.exe` chứ không phải `pwsh`: mọi script trong `scripts/` viết cho Windows
    # PowerShell 5.1 và đã có những chỗ dựa vào đúng bản đó.
    return shutil.which("powershell.exe") or "powershell.exe"


def _admin(goc: Path, *tham_so: str) -> list[str]:
    return [str(_venv_python(goc)), "-m", "bridge.admin", *tham_so]


def _script_ps1(goc: Path, ten: str) -> list[str]:
    # `-ThuMuc` TƯỜNG MINH. Mọi script trong `scripts/` mặc định `C:\\CopyBridge`, và trên VPS thật
    # thư mục đó đúng bằng `project_root` — nên bỏ qua tham số này vẫn chạy đúng, vì một sự trùng
    # hợp. Dựa vào trùng hợp là hỏng ở bản cài đặt ở ổ khác, và triệu chứng sẽ là "không thấy
    # .venv" chứ không phải "sai thư mục".
    return [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(goc / "scripts" / ten), "-ThuMuc", str(goc)]


def _bien_dich(goc: Path) -> list[str]:
    # Biên dịch CẢ HAI EA trong một lần bấm. Câu lệnh in trên trang chỉ biên dịch Master rồi bảo
    # người dùng "chạy lại, đổi Master thành Client" — đúng loại việc người ta làm sót một nửa.
    return [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(goc / "scripts" / "bien-dich-ea.ps1"), "-ThuMuc", str(goc)]


#: Danh sách trắng. Thêm gì vào đây là mở rộng bề mặt tấn công — đọc lại docstring đầu file trước.
LENH_CHAY_DUOC: dict[str, LenhChay] = {
    "LIET_KE": LenhChay(lambda goc: _admin(goc, "liet-ke"), han_giay=60),
    "TINH_HINH": LenhChay(lambda goc: _admin(goc, "tinh-hinh"), han_giay=60),
    "KIEM_REASON": LenhChay(lambda goc: _admin(goc, "kiem-reason"), han_giay=60),
    "KIEM_DONG_SAI": LenhChay(lambda goc: _admin(goc, "kiem-dong-sai"), han_giay=60),
    "KIEM_TRA": LenhChay(lambda goc: _script_ps1(goc, "kiem-tra.ps1"), han_giay=180),
    "BIEN_DICH_EA": LenhChay(_bien_dich, han_giay=300, ghi_dia=True),
    # Lệnh GHI duy nhất trong danh sách, và nó **không mở thêm quyền gì**: `/api/run_mode` đã làm
    # đúng việc này từ trước, cũng không xác thực. Có ở đây để câu lệnh in trên tab Hướng dẫn có
    # nút Chạy như mọi câu lệnh khác — một ô lệnh không có nút là một câu hỏi, và người dùng đã
    # hỏi đúng câu đó ngày 2026-09-22.
    "RUN_MODE_RUNNING": LenhChay(lambda goc: _admin(goc, "run-mode", "RUNNING"),
                                 han_giay=60, ghi_dia=True),
}


def _cat(chu: str) -> str:
    dong = chu.replace("\r\n", "\n").rstrip("\n").split("\n")
    if len(dong) <= GIOI_HAN_DONG:
        return "\n".join(dong)
    # Giữ phần CUỐI: kết luận của mọi lệnh ở đây đều nằm ở cuối, không phải đầu.
    return "\n".join(["...", *dong[-GIOI_HAN_DONG:]])


async def chay(ma: str, goc: Path) -> dict[str, object]:
    """Chạy một lệnh trong danh sách trắng. Ném `KeyError` nếu mã lạ."""
    lenh = LENH_CHAY_DUOC[ma]
    argv = lenh.dung_argv(goc)  # type: ignore[operator]
    log.info("Dashboard chay lenh %s%s", ma, " (ghi dia)" if lenh.ghi_dia else "")
    bat_dau = time.monotonic()
    try:
        tt = await asyncio.create_subprocess_exec(
            *argv, cwd=str(goc),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    except OSError as exc:
        # Thiếu `.venv` hay thiếu chính script: nói ra thứ KHÔNG chạy được, chứ đừng nói "lỗi".
        log.warning("Khong chay duoc lenh %s: %s", ma, exc)
        return {"ma": ma, "chay_duoc": False, "ma_thoat": None, "ra": str(exc), "giay": 0.0}

    try:
        ra, _ = await asyncio.wait_for(tt.communicate(), timeout=lenh.han_giay)
    except TimeoutError:
        tt.kill()
        await tt.wait()
        giay = round(time.monotonic() - bat_dau, 1)
        log.warning("Lenh %s qua han %d giay, da giet", ma, lenh.han_giay)
        return {"ma": ma, "chay_duoc": True, "ma_thoat": None, "qua_han": lenh.han_giay,
                "ra": "", "giay": giay}

    return {
        "ma": ma,
        "chay_duoc": True,
        "ma_thoat": tt.returncode,
        # `errors="replace"`: output của PowerShell trên máy tiếng Việt có thể không phải UTF-8
        # sạch, và một dashboard chết vì một byte lạ trong log là chuyện không đáng.
        "ra": _cat(bytes(ra or b"").decode("utf-8", errors="replace")),
        "giay": round(time.monotonic() - bat_dau, 1),
    }
