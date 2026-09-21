"""Test đọc cấu hình khởi động.

Trọng tâm: cấu hình sai phải **dừng ngay**, và giá trị trong mục ``[security]`` không lọt ra
``repr()`` — vì ``repr()`` là thứ hay bị đưa vào log nhất.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from bridge.config import (
    EXAMPLE_CONFIG_FILENAME,
    BridgeSection,
    ConfigError,
    SecretSection,
    load_config,
    parse_config,
    sua_config_toml,
)


def _parse(raw: dict, root: Path) -> object:
    return parse_config(raw, source_path=root / "config.toml", project_root=root)


def test_doc_duoc_file_mau(project_root: Path) -> None:
    example = project_root / EXAMPLE_CONFIG_FILENAME
    assert example.is_file(), "Thiếu config.example.toml"
    with example.open("rb") as fh:
        raw = tomllib.load(fh)
    cfg = _parse(raw, project_root)
    assert cfg.bridge == BridgeSection(host="127.0.0.1", port=8787, web_port=8080,
                                       db_path="data/bridge.db")


def test_thieu_truong_thi_dung_gia_tri_mac_dinh(tmp_path: Path) -> None:
    cfg = _parse({"bridge": {"port": 9000}}, tmp_path)
    assert cfg.bridge.port == 9000
    assert cfg.bridge.host == BridgeSection().host
    assert cfg.bridge.web_port == BridgeSection().web_port


def test_db_path_tuong_doi_duoc_quy_ve_goc_du_an(tmp_path: Path) -> None:
    cfg = _parse({"bridge": {"db_path": "data/bridge.db"}}, tmp_path)
    assert cfg.db_path == tmp_path / "data" / "bridge.db"


def test_db_path_tuyet_doi_duoc_giu_nguyen(tmp_path: Path) -> None:
    absolute = tmp_path / "o_khac" / "bridge.db"
    cfg = _parse({"bridge": {"db_path": str(absolute)}}, tmp_path)
    assert cfg.db_path == absolute


@pytest.mark.parametrize(
    "raw",
    [
        {"bridge": {"port": 0}},
        {"bridge": {"port": 65536}},
        {"bridge": {"port": -1}},
        {"bridge": {"port": "8787"}},
        {"bridge": {"port": True}},
        {"bridge": {"web_port": 0}},
        {"bridge": {"host": ""}},
        {"bridge": {"host": 123}},
        {"bridge": {"db_path": ""}},
        {"bridge": {"port": 8787, "web_port": 8787}},
        {"bridge": "khong-phai-bang"},
        {"security": "khong-phai-bang"},
    ],
)
def test_cau_hinh_sai_bi_tu_choi(raw: dict, tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        _parse(raw, tmp_path)


def test_thieu_config_toml_thi_bao_loi_ro_rang(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path / "khong-ton-tai.toml")
    assert EXAMPLE_CONFIG_FILENAME in str(exc.value)


def test_load_config_doc_duoc_file_that(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[bridge]\nhost = "127.0.0.1"\nport = 7000\nweb_port = 7001\n'
        'db_path = "data/x.db"\n\n[security]\ndashboard_password = "abc"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.bridge.host == "127.0.0.1"
    assert cfg.bridge.port == 7000
    assert cfg.security["dashboard_password"] == "abc"
    assert cfg.db_path == tmp_path / "data" / "x.db"


def test_secret_section_khong_lo_gia_tri_qua_repr() -> None:
    secrets = SecretSection({"token": "sieu-bi-mat", "password": "cung-bi-mat"})
    assert "sieu-bi-mat" not in repr(secrets)
    assert "cung-bi-mat" not in repr(secrets)
    assert "sieu-bi-mat" not in str(secrets)
    assert "sieu-bi-mat" not in f"{secrets}"
    assert secrets["token"] == "sieu-bi-mat"
    assert len(secrets) == 2
    assert sorted(secrets) == ["password", "token"]


# -- F-02: khong duoc phoi dashboard ra ngoai ma khong co mat khau ------------------------------

def test_nghe_moi_interface_ma_khong_mat_khau_thi_tu_choi_khoi_dong(tmp_path: Path) -> None:
    """Kiểm toán 2026-09-06 gọi `/api/emergency` không cookie và nó đóng 3 cặp (đường đó nay đã
    gỡ — D-33 — nhưng lý do bắt buộc mật khẩu thì không đổi).

    Cơ chế "không mật khẩu thì không bắt đăng nhập" là có chủ đích và giữ nguyên; thứ phải chặn
    là **tổ hợp** nghe ra ngoài + không mật khẩu.
    """
    with pytest.raises(ConfigError) as loi:
        _parse({"bridge": {"host": "0.0.0.0"}}, tmp_path)
    # Thong bao phai chi ra ca hai duong sua, khong chi bao "sai".
    assert "dashboard_password" in str(loi.value) and "127.0.0.1" in str(loi.value)


def test_nghe_moi_interface_co_mat_khau_thi_chay_duoc(tmp_path: Path) -> None:
    cfg = _parse({"bridge": {"host": "0.0.0.0"},
                  "security": {"dashboard_password": "mot-mat-khau-that"}}, tmp_path)
    assert cfg.bridge.host == "0.0.0.0"


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "  127.0.0.1  "])
def test_loopback_thi_khong_bat_buoc_mat_khau(host: str, tmp_path: Path) -> None:
    assert _parse({"bridge": {"host": host}}, tmp_path) is not None


def test_mat_khau_toan_khoang_trang_khong_tinh_la_co(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        _parse({"bridge": {"host": "0.0.0.0"}, "security": {"dashboard_password": "   "}},
               tmp_path)


def test_muc_clicker_doc_duoc_va_khong_lot_ra_repr(tmp_path: Path) -> None:
    """Mục ``[clicker]`` chứa token, nên nó phải được che giống hệt ``[security]``."""
    cfg = _parse({"clicker": {"token": "bi-mat", "account_login": 538217}}, tmp_path)
    assert cfg.clicker["token"] == "bi-mat"
    assert cfg.clicker["account_login"] == 538217
    assert "bi-mat" not in repr(cfg.clicker)
    assert "bi-mat" not in repr(cfg)


def test_thieu_muc_clicker_thi_rong(tmp_path: Path) -> None:
    assert dict(_parse({"bridge": {}}, tmp_path).clicker) == {}


def test_muc_clicker_khong_phai_bang_thi_loi(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"\[clicker\]"):
        _parse({"clicker": "khong-phai-bang"}, tmp_path)


# -- ghi lại config.toml ------------------------------------------------------------------------
#
# Một `config.toml` hỏng là một Bridge không khởi động được, và lúc đó không còn dashboard nào để
# sửa lại. Nên mỗi test dưới đây chốt một cách hỏng cụ thể.

MAU_CONFIG = '''# Cau hinh Bridge. Dong chu thich nay PHAI con nguyen sau khi sua.
[bridge]
host = "127.0.0.1"   # chi may nay cham duoc
port = 8787
web_port = 8080
db_path = "data/bridge.db"

[security]
dashboard_password = "cu"
telegram_token   = ""

[clicker]
token = "tok-cu"
'''


def _config(tmp_path: Path) -> Path:
    duong_dan = tmp_path / "config.toml"
    duong_dan.write_text(MAU_CONFIG, encoding="utf-8")
    return duong_dan


def test_sua_giu_nguyen_chu_thich_va_thu_tu(tmp_path: Path) -> None:
    duong_dan = _config(tmp_path)
    sua_config_toml(duong_dan, {"bridge.web_port": 8090}, project_root=tmp_path)
    moi = duong_dan.read_text(encoding="utf-8")
    assert "web_port = 8090" in moi
    assert "# Cau hinh Bridge. Dong chu thich nay PHAI con nguyen sau khi sua." in moi
    assert "# chi may nay cham duoc" in moi
    assert moi.index("[bridge]") < moi.index("[security]") < moi.index("[clicker]")


def test_gia_tri_sai_thi_khong_cham_vao_file(tmp_path: Path) -> None:
    """Kiểm **trước khi** ghi: cổng trùng nhau là Bridge không khởi động được."""
    duong_dan = _config(tmp_path)
    with pytest.raises(ConfigError):
        sua_config_toml(duong_dan, {"bridge.web_port": 8787}, project_root=tmp_path)
    assert duong_dan.read_text(encoding="utf-8") == MAU_CONFIG


def test_mo_host_ra_ngoai_ma_khong_co_mat_khau_bi_tu_choi(tmp_path: Path) -> None:
    """Đúng phép kiểm F-02, chạy ở đây chứ không đợi tới lần khởi động sau."""
    duong_dan = _config(tmp_path)
    with pytest.raises(ConfigError):
        sua_config_toml(duong_dan, {"bridge.host": "0.0.0.0", "security.dashboard_password": ""},
                        project_root=tmp_path)
    assert duong_dan.read_text(encoding="utf-8") == MAU_CONFIG


def test_khoa_ngoai_danh_sach_bi_tu_choi(tmp_path: Path) -> None:
    duong_dan = _config(tmp_path)
    with pytest.raises(ConfigError):
        sua_config_toml(duong_dan, {"bridge.db_path_khac": "x"}, project_root=tmp_path)
    with pytest.raises(ConfigError):
        sua_config_toml(duong_dan, {"bridge.port": "8787"}, project_root=tmp_path)
    assert duong_dan.read_text(encoding="utf-8") == MAU_CONFIG


def test_gia_tri_co_dau_nhay_bi_tu_choi_thay_vi_ghi_ra_toml_sai(tmp_path: Path) -> None:
    duong_dan = _config(tmp_path)
    with pytest.raises(ConfigError):
        sua_config_toml(duong_dan, {"security.dashboard_password": 'co"nhay'},
                        project_root=tmp_path)
    assert duong_dan.read_text(encoding="utf-8") == MAU_CONFIG


def test_tao_ban_sao_luu_truoc_khi_thay(tmp_path: Path) -> None:
    duong_dan = _config(tmp_path)
    ban_sao = sua_config_toml(duong_dan, {"bridge.port": 8788}, project_root=tmp_path)
    assert ban_sao.exists()
    assert ban_sao.read_text(encoding="utf-8") == MAU_CONFIG
    assert "port = 8788" in duong_dan.read_text(encoding="utf-8")


def test_them_khoa_chua_co_vao_dung_muc(tmp_path: Path) -> None:
    duong_dan = _config(tmp_path)
    sua_config_toml(duong_dan, {"security.telegram_chat_id": "12345",
                                "clicker_master.token": "tok-master"},
                    project_root=tmp_path)
    doc = tomllib.loads(duong_dan.read_text(encoding="utf-8"))
    assert doc["security"]["telegram_chat_id"] == "12345"
    assert doc["security"]["dashboard_password"] == "cu"
    assert doc["clicker_master"]["token"] == "tok-master"
    assert doc["clicker"]["token"] == "tok-cu"


def test_khong_ghi_bom_vi_tomllib_mo_file_o_che_do_nhi_phan(tmp_path: Path) -> None:
    duong_dan = _config(tmp_path)
    sua_config_toml(duong_dan, {"bridge.port": 8788}, project_root=tmp_path)
    assert not duong_dan.read_bytes().startswith(b"\xef\xbb\xbf")
    # Và đọc lại được bằng đúng đường Bridge dùng lúc khởi động.
    assert load_config(duong_dan).bridge.port == 8788


def test_khoa_moi_chen_ngay_sau_khoa_cuoi_cua_muc_khong_dinh_vao_muc_sau(tmp_path: Path) -> None:
    """Đúng TOML thôi chưa đủ: file này người ta còn đọc bằng mắt."""
    duong_dan = _config(tmp_path)
    sua_config_toml(duong_dan, {"security.telegram_chat_id": "12345"}, project_root=tmp_path)
    dong = duong_dan.read_text(encoding="utf-8").splitlines()
    vi_tri = dong.index('telegram_chat_id = "12345"')
    assert dong[vi_tri - 1].startswith("telegram_token")
    assert dong[vi_tri + 1].strip() == ""


def test_chi_giu_nam_ban_sao_luu_config_moi_nhat(tmp_path: Path) -> None:
    """Mỗi bản sao lưu là **bản rõ** của mật khẩu và token: để chúng tích lại là rải bí mật ra đĩa."""
    duong_dan = _config(tmp_path)
    for cong in range(8):
        sua_config_toml(duong_dan, {"bridge.port": 8800 + cong}, project_root=tmp_path)
    ban = sorted(tmp_path.glob("config.toml.bak-*"))
    assert len(ban) <= 5, [b.name for b in ban]
