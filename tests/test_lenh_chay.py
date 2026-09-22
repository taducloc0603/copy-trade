"""Chạy lệnh từ dashboard — `bridge/web/lenh.py`.

Dashboard **không còn xác thực** (D-39), nên một endpoint chạy lệnh là một đường thực thi mã cho
bất kỳ ai chạm tới cổng 8080. Cả file này tồn tại để khoá lại đúng một điều: trình duyệt gửi MÃ,
không bao giờ gửi câu lệnh.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import httpx
import pytest

from bridge.db.repo import Database
from bridge.web import views
from bridge.web.app import Dashboard, tao_app
from bridge.web.lenh import GIOI_HAN_DONG, LENH_CHAY_DUOC, _cat, chay


def test_moi_ma_chay_cua_buoc_deu_nam_trong_danh_sach_trang() -> None:
    """Bước khai một mã lệnh không có trong danh sách trắng = nút hiện ra rồi báo lỗi khi bấm."""
    for b in views.BUOC_LAN_DAU + views.BUOC_SAU_UPDATE:
        for ma in b.ma_chay:
            assert ma in LENH_CHAY_DUOC, f"{b.ma} khai ma_chay={ma!r} khong co trong danh sach"


def test_khong_ham_nao_dung_shell() -> None:
    """`create_subprocess_exec`, không phải `_shell`.

    Qua shell thì mọi ký tự đặc biệt trong một đường dẫn đều thành một chỗ chen chuỗi. Đường dẫn ở
    đây do Bridge dựng chứ không do trình duyệt gửi, nhưng khoảng cách giữa hai điều đó chỉ là một
    lần sửa cẩu thả.
    """
    nguon = Path(inspect.getfile(chay)).read_text(encoding="utf-8")
    assert "create_subprocess_shell" not in nguon
    assert "shell=True" not in nguon
    assert "os.system" not in nguon


def test_chay_chi_nhan_ma_va_thu_muc() -> None:
    """`chay` không có tham số nào để nhét một câu lệnh vào.

    Đây là phép chặn thật sự: dù endpoint có sơ hở thì cũng không có đường nào truyền được argv.
    """
    tham_so = list(inspect.signature(chay).parameters)
    assert tham_so == ["ma", "goc"]


async def test_api_tu_choi_ma_la_va_khong_chay_gi(db: Database) -> None:
    transport = httpx.ASGITransport(app=tao_app(Dashboard(db)))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        for ma in ("LA", "../../x", "liet-ke", "LIET_KE; whoami", ""):
            r = await c.post(f"/api/chay/{ma}")
            assert r.status_code in (400, 404), (ma, r.status_code)
            if r.status_code == 400:
                assert r.json()["error"] == "LENH_KHONG_CHAY_DUOC", ma


@pytest.mark.parametrize("ma", sorted(LENH_CHAY_DUOC))
def test_moi_lenh_dung_duoc_argv_va_co_han_gio(ma: str, tmp_path: Path) -> None:
    lenh = LENH_CHAY_DUOC[ma]
    argv = lenh.dung_argv(tmp_path)
    assert isinstance(argv, list) and argv, ma
    assert all(isinstance(x, str) for x in argv), ma
    # Han gio bat buoc: mot lenh treo ma khong co han gio la mot dashboard treo theo.
    assert 0 < lenh.han_giay <= 600, ma


def test_cat_giu_phan_CUOI_cua_output() -> None:
    """Kết luận của mọi lệnh ở đây nằm ở CUỐI, không phải đầu — nên cắt thì phải bỏ đầu."""
    dai = "\n".join(str(i) for i in range(GIOI_HAN_DONG * 2))
    ra = _cat(dai)
    assert ra.startswith("...")
    assert ra.rstrip().endswith(str(GIOI_HAN_DONG * 2 - 1))
    assert len(ra.split("\n")) == GIOI_HAN_DONG + 1
    # Ngan thi giu nguyen, khong them gi.
    assert _cat("mot\nhai") == "mot\nhai"
