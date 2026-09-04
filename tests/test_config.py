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
)


def _parse(raw: dict, root: Path) -> object:
    return parse_config(raw, source_path=root / "config.toml", project_root=root)


def test_doc_duoc_file_mau(project_root: Path) -> None:
    example = project_root / EXAMPLE_CONFIG_FILENAME
    assert example.is_file(), "Thiếu config.example.toml"
    with example.open("rb") as fh:
        raw = tomllib.load(fh)
    cfg = _parse(raw, project_root)
    assert cfg.bridge == BridgeSection(host="0.0.0.0", port=8787, web_port=8080,
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
