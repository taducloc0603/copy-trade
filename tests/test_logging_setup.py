"""Test thiết lập logging.

Trọng tâm: định dạng có ngữ cảnh, và **không bao giờ lộ token hay mật khẩu**.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from bridge.logging_setup import REDACTED, get_logger, setup_logging

ISO_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{4} \| ")


@pytest.fixture
def log_file(tmp_path: Path):
    """Cấu hình logging ghi vào thư mục tạm, trả về hàm đọc lại nội dung file log."""
    setup_logging(log_dir=tmp_path, to_console=False)
    path = tmp_path / "bridge.log"

    def read() -> str:
        for handler in logging.getLogger().handlers:
            handler.flush()
        return path.read_text(encoding="utf-8")

    yield read

    for handler in list(logging.getLogger().handlers):
        if getattr(handler, "_copybridge", False):
            logging.getLogger().removeHandler(handler)
            handler.close()


def test_timestamp_iso8601_co_mili_giay(log_file) -> None:
    get_logger("bridge.test").info("dong dau tien")
    line = log_file().splitlines()[0]
    assert ISO_TIMESTAMP.match(line), f"Timestamp sai định dạng: {line!r}"


def test_dong_log_co_ten_module_va_muc(log_file) -> None:
    get_logger("bridge.engine.sizing").warning("volume duoi muc toi thieu")
    line = log_file().splitlines()[0]
    assert "WARNING" in line
    assert "bridge.engine.sizing" in line
    assert "volume duoi muc toi thieu" in line


def test_pair_id_va_event_id_duoc_chen_tu_dong(log_file) -> None:
    log = get_logger("bridge.test")
    log.info("co pair", extra={"pair_id": "PAIR-20260904-000001"})
    log.info("co event", extra={"event_id": "EVT-master-42"})
    log.info("co ca hai", extra={"pair_id": "PAIR-X", "event_id": "EVT-Y"})
    lines = log_file().splitlines()
    assert "[pair_id=PAIR-20260904-000001]" in lines[0]
    assert "[event_id=EVT-master-42]" in lines[1]
    assert "[pair_id=PAIR-X event_id=EVT-Y]" in lines[2]


def test_khong_co_ngu_canh_thi_khong_co_dau_ngoac(log_file) -> None:
    get_logger("bridge.test").info("khong ngu canh")
    assert "[" not in log_file().splitlines()[0].split("| ", 3)[3]


@pytest.mark.parametrize(
    "message",
    [
        "hello token=abcdef123456 world",
        'dang nhap password: "sieu-bi-mat"',
        "secret = xyz789",
        "api_key=AKIA1234567890",
    ],
)
def test_khong_bao_gio_log_token_hay_mat_khau_trong_message(log_file, message: str) -> None:
    get_logger("bridge.test").warning(message)
    content = log_file()
    assert REDACTED in content
    for leaked in ("abcdef123456", "sieu-bi-mat", "xyz789", "AKIA1234567890"):
        assert leaked not in content


def test_truong_nhay_cam_trong_extra_bi_che(log_file) -> None:
    get_logger("bridge.test").error("bat tay that bai", extra={"token": "raw-secret-value"})
    assert "raw-secret-value" not in log_file()


def test_goi_setup_nhieu_lan_khong_nhan_doi_handler(tmp_path: Path) -> None:
    setup_logging(log_dir=tmp_path, to_console=False)
    setup_logging(log_dir=tmp_path, to_console=False)
    setup_logging(log_dir=tmp_path, to_console=False)
    root = logging.getLogger()
    ours = [h for h in root.handlers if getattr(h, "_copybridge", False)]
    assert len(ours) == 1
    for handler in ours:
        root.removeHandler(handler)
        handler.close()


def test_tao_thu_muc_log_neu_chua_ton_tai(tmp_path: Path) -> None:
    target = tmp_path / "sau" / "vai" / "cap"
    setup_logging(log_dir=target, to_console=False)
    assert target.is_dir()
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_copybridge", False):
            root.removeHandler(handler)
            handler.close()
