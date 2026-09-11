"""Fixture dùng chung cho toàn bộ test.

Phase 3 sẽ bổ sung fixture cho mock agent.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from bridge.db.repo import Database

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Dữ liệu nền tối thiểu để một `pair` hợp lệ tồn tại được (FK bật nên phải có đủ).
MASTER_AGENT = "AG-MASTER"
CLIENT_AGENT = "AG-CLIENT"
CLIENT_ID = "CL-01"
MASTER_POSITION_ID = 900001


@pytest.fixture(autouse=True)
def _cach_ly_config_may(monkeypatch: pytest.MonkeyPatch) -> None:
    """Không test nào được đọc `config.toml` thật của máy đang chạy.

    Lý do có fixture này chứ không chỉ sửa từng test: `clicker.__main__.main()` tự điền
    tham số thiếu từ `config.toml`, nên một test gọi `main()` mà quên chặn sẽ **khởi động
    clicker thật** và treo ở vòng lặp kết nối lại vô hạn. Nó xanh trên máy chưa khai mục
    `[clicker]` và treo trên máy đã cài xong — nghĩa là nó hỏng đúng lúc không ai muốn, và
    hỏng bằng cách treo chứ không phải báo lỗi.

    Test nào cần giá trị cấu hình cụ thể vẫn `monkeypatch.setattr` đè lên được, vì lần đặt
    sau thắng.

    Cùng lý do, không test nào được ghi vào `logs/` **của máy đang chạy**. `main()` gọi
    `setup_logging()` thật, ghi theo thư mục hiện hành — mà `cai-dat.ps1 -CapNhat` chạy bộ test
    ngay trong `C:\\CopyBridge`. Trên VPS 2026-09-11, `logs/clicker.log` thật chứa ~500 KB log test,
    kể cả dòng CRITICAL "Thieu token" do test cố ý gây ra: người vận hành đọc log sẽ tưởng
    clicker thật đang hỏng. Lộ ra vì mốc giờ của file **sớm hơn** giờ clicker khởi động.
    """
    monkeypatch.setattr("clicker.__main__.doc_muc_clicker", dict, raising=False)
    monkeypatch.setattr("clicker.__main__.setup_logging", lambda **_kw: None, raising=False)
    monkeypatch.delenv("COPYBRIDGE_CLICKER_TOKEN", raising=False)


@pytest.fixture
def project_root() -> Path:
    """Gốc dự án, dùng để mở các file tài liệu và cấu hình mẫu trong test."""
    return PROJECT_ROOT


@pytest.fixture
def caplog_bridge(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """``caplog`` đã bật sẵn mức WARNING cho toàn bộ logger của gói ``bridge``."""
    caplog.set_level(logging.WARNING, logger="bridge")
    return caplog


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Đường dẫn tới một database chưa tồn tại, nằm trong thư mục tạm của test."""
    return tmp_path / "data" / "bridge.db"


@pytest.fixture
def db(db_path: Path) -> Iterator[Database]:
    """Database trống đã chạy migration.

    Dùng file thật chứ không phải `:memory:` vì WAL, `ATTACH` và retention chỉ có hành vi
    đúng trên file.
    """
    database = Database(db_path)
    try:
        yield database
    finally:
        database.close()


@pytest.fixture
def seeded(db: Database) -> Database:
    """Database đã có sẵn một Master, một Client và một vị thế Master đang mở.

    Đây là bối cảnh tối thiểu để tạo được `pair` — khoá ngoại đang bật nên không thể chèn
    pair vào một database trống.
    """
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash="hash-master", magic_number=770001,
                    account_login=111111)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash="hash-client", magic_number=770001,
                    account_login=222222)
    db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, display_name="Client thu nghiem")
    db.upsert_master_position(
        MASTER_POSITION_ID, agent_id=MASTER_AGENT, symbol="XAUUSD", direction="BUY",
        initial_volume=1.0, current_volume=1.0, status="OPEN", ticket=555001, magic=770001,
    )
    return db
