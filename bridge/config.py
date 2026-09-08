"""Đọc cấu hình khởi động của Bridge từ ``config.toml``.

Phân biệt hai loại cấu hình, đừng trộn lẫn:

* **Cấu hình khởi động** — host, port, đường dẫn DB, bí mật. Nằm ở ``config.toml``, đọc bằng
  file này, đổi thì phải khởi động lại tiến trình.
* **Cấu hình nghiệp vụ sửa nóng** — ``run_mode``, ``cascade_wait_master_ms``, ... Nằm ở bảng
  ``system_config`` trong DB (phase 2), sửa được từ dashboard mà không cần khởi động lại.

``config.toml`` nằm trong ``.gitignore`` vì nó chứa token thật. Bản mẫu là
``config.example.toml`` và được commit.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_FILENAME = "config.toml"
EXAMPLE_CONFIG_FILENAME = "config.example.toml"


class ConfigError(Exception):
    """Cấu hình thiếu hoặc sai. Bridge không được khởi động khi gặp lỗi này."""


@dataclass(frozen=True)
class BridgeSection:
    """Mục ``[bridge]`` trong ``config.toml``."""

    #: Mac dinh chi nghe loopback. Mo ra ngoai la mot quyet dinh phai co y thuc, va khi do
    #: `parse_config` bat buoc phai co `dashboard_password` (F-02).
    host: str = "127.0.0.1"
    port: int = 8787
    web_port: int = 8080
    db_path: str = "data/bridge.db"


class SecretSection(Mapping[str, Any]):
    """Mục ``[security]`` — bọc lại để giá trị không bao giờ lọt ra log.

    ``repr()`` và ``str()`` chỉ cho biết có bao nhiêu khoá, không cho biết nội dung.
    Muốn lấy giá trị thì phải gọi tường minh, ví dụ ``config.security["dashboard_password"]``.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(data or {})

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"<SecretSection: {len(self._data)} khoá, giá trị được che>"

    __str__ = __repr__


@dataclass(frozen=True)
class Config:
    """Toàn bộ cấu hình khởi động đã được kiểm tra."""

    bridge: BridgeSection
    security: SecretSection
    source_path: Path
    project_root: Path
    #: Mục ``[clicker]`` — tham số của tiến trình clicker, kể cả token bắt tay. Dùng
    #: ``SecretSection`` chứ không phải dict thường vì token nằm trong đó: mục đích của mục này
    #: là để token **không** phải đi qua dòng lệnh, nên nó cũng không được rơi vào log.
    clicker: SecretSection = field(default_factory=SecretSection)

    @property
    def db_path(self) -> Path:
        """Đường dẫn tuyệt đối tới file SQLite, tính từ gốc dự án nếu là đường dẫn tương đối."""
        raw = Path(self.bridge.db_path)
        return raw if raw.is_absolute() else (self.project_root / raw)


def find_project_root(start: Path | None = None) -> Path:
    """Tìm gốc dự án: thư mục gần nhất đi lên có chứa ``pyproject.toml``."""
    current = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return current


def _require_port(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(f"bridge.{field} phải là số nguyên, nhận được {value!r}")
    if not 1 <= value <= 65535:
        raise ConfigError(f"bridge.{field} phải nằm trong 1..65535, nhận được {value}")
    return value


#: Địa chỉ chỉ máy này chạm được. Nghe ngoài phạm vi này thì bắt buộc phải có mật khẩu.
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def _la_loopback(host: str) -> bool:
    return host.strip().lower() in LOOPBACK


def parse_config(raw: Mapping[str, Any], source_path: Path, project_root: Path) -> Config:
    """Kiểm tra và dựng ``Config`` từ dict đã parse. Tách riêng để test không cần file thật."""
    bridge_raw = raw.get("bridge", {})
    if not isinstance(bridge_raw, Mapping):
        raise ConfigError("Mục [bridge] phải là một bảng TOML")

    defaults = BridgeSection()
    host = bridge_raw.get("host", defaults.host)
    if not isinstance(host, str) or not host:
        raise ConfigError(f"bridge.host phải là chuỗi không rỗng, nhận được {host!r}")
    db_path = bridge_raw.get("db_path", defaults.db_path)
    if not isinstance(db_path, str) or not db_path:
        raise ConfigError(f"bridge.db_path phải là chuỗi không rỗng, nhận được {db_path!r}")

    port = _require_port(bridge_raw.get("port", defaults.port), "port")
    web_port = _require_port(bridge_raw.get("web_port", defaults.web_port), "web_port")
    if port == web_port:
        raise ConfigError(f"bridge.port và bridge.web_port không được trùng nhau ({port})")

    security_raw = raw.get("security", {})
    if not isinstance(security_raw, Mapping):
        raise ConfigError("Mục [security] phải là một bảng TOML")

    # Không mật khẩu thì `Dashboard.hop_le()` cho qua MỌI request, kể cả không cookie — đó là
    # lựa chọn có ý thức khi chỉ nghe loopback. Nhưng mặc định cũ là `host = "0.0.0.0"` cộng mật
    # khẩu rỗng, tức làm đúng theo RUNBOOK sẽ ra một nút đóng khẩn cấp không khoá. Kiểm toán
    # 2026-09-06 gọi thẳng `/api/emergency` không cookie và nó đóng 3 cặp (F-02).
    if not _la_loopback(host) and not str(security_raw.get("dashboard_password") or "").strip():
        raise ConfigError(
            f"bridge.host = {host!r} nghe tren moi interface nhung "
            "security.dashboard_password de trong, nghia la dashboard KHONG co xac thuc: ai "
            "cham duoc toi cong web deu bam duoc nut dong khan cap va doi duoc run_mode. "
            "Sua mot trong hai: dat security.dashboard_password, hoac doi bridge.host thanh "
            "127.0.0.1"
        )

    clicker_raw = raw.get("clicker", {})
    if not isinstance(clicker_raw, Mapping):
        raise ConfigError("Mục [clicker] phải là một bảng TOML")

    return Config(
        bridge=BridgeSection(host=host, port=port, web_port=web_port, db_path=db_path),
        security=SecretSection(security_raw),
        source_path=source_path,
        project_root=project_root,
        clicker=SecretSection(clicker_raw),
    )


def load_config(path: Path | str | None = None) -> Config:
    """Đọc cấu hình từ ``config.toml`` ở gốc dự án, hoặc từ ``path`` chỉ định.

    Không tìm thấy file thì ném ``ConfigError`` kèm hướng dẫn — im lặng chạy bằng giá trị mặc
    định là cách để một cấu hình sai trôi tới tận lúc gửi lệnh.
    """
    project_root = find_project_root()
    config_path = Path(path) if path is not None else project_root / DEFAULT_CONFIG_FILENAME
    if not config_path.is_file():
        raise ConfigError(
            f"Không tìm thấy {config_path}. Hãy sao chép {EXAMPLE_CONFIG_FILENAME} "
            f"thành {DEFAULT_CONFIG_FILENAME} rồi điền giá trị thật."
        )
    try:
        with config_path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        # Chỗ hay gặp nhất: chỗ giữ chỗ dạng `<so-tai-khoan-Client>` trong tài liệu chưa được
        # thay bằng giá trị thật. Để lỗi này nổi lên thì người dùng nhận một traceback tomllib.
        raise ConfigError(
            f"{config_path} không phải TOML hợp lệ: {exc}. "
            "Chỗ nào còn để nguyên dạng <...> là chỗ đó chưa điền giá trị thật."
        ) from exc
    except OSError as exc:
        raise ConfigError(f"Không đọc được {config_path}: {exc}") from exc
    root = config_path.parent if path is not None else project_root
    return parse_config(raw, source_path=config_path, project_root=root)
