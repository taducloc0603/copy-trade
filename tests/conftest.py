"""Fixture dùng chung cho toàn bộ test.

Phase 3 sẽ bổ sung fixture cho mock agent, phase 2 bổ sung fixture database tạm.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project_root() -> Path:
    """Gốc dự án, dùng để mở các file tài liệu và cấu hình mẫu trong test."""
    return PROJECT_ROOT


@pytest.fixture
def caplog_bridge(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """``caplog`` đã bật sẵn mức WARNING cho toàn bộ logger của gói ``bridge``."""
    caplog.set_level(logging.WARNING, logger="bridge")
    return caplog
