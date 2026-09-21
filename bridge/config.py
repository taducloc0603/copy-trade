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

import contextlib
import os
import re
import subprocess
import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bridge.clock import utc_now
from bridge.logging_setup import get_logger

log = get_logger(__name__)

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
    #: Mục ``[clicker_master]`` — clicker **thứ hai**, lái terminal Master (phase 12). Cùng hình
    #: dạng với ``[clicker]`` và cùng lý do phải là ``SecretSection``: nó cũng chứa token riêng.
    #: Để trống là cấu hình bình thường — chỉ bản nào bật `master_close_route = UI` mới cần.
    clicker_master: SecretSection = field(default_factory=SecretSection)

    def muc_clicker(self, ten: str) -> SecretSection:
        """Mục cấu hình của một clicker theo tên (`clicker`, `clicker_master`).

        Tra theo tên thay vì thuộc tính để `clicker/__main__.py --muc` không phải biết trước có
        bao nhiêu mục: thêm terminal thứ ba chỉ là thêm một mục trong `config.toml`.
        """
        if ten == "clicker":
            return self.clicker
        if ten == "clicker_master":
            return self.clicker_master
        raise ConfigError(f"Khong co muc cau hinh [{ten}] duoc ho tro")

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
    # khẩu rỗng, tức làm đúng theo RUNBOOK sẽ ra một dashboard không khoá. Kiểm toán 2026-09-06
    # gọi thẳng `/api/emergency` không cookie và nó đóng 3 cặp (F-02). Endpoint đó nay đã gỡ
    # (D-33), nhưng `run_mode` và mọi nút Lưu cấu hình vẫn nằm sau cùng một cánh cửa.
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

    clicker_master_raw = raw.get("clicker_master", {})
    if not isinstance(clicker_master_raw, Mapping):
        raise ConfigError("Mục [clicker_master] phải là một bảng TOML")

    return Config(
        bridge=BridgeSection(host=host, port=port, web_port=web_port, db_path=db_path),
        security=SecretSection(security_raw),
        source_path=source_path,
        project_root=project_root,
        clicker=SecretSection(clicker_raw),
        clicker_master=SecretSection(clicker_master_raw),
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


# =============================================================================================
# Ghi lại `config.toml` (D-32, bổ sung 2026-09-21)
# =============================================================================================
#
# Dashboard sửa được file này, nhưng theo đúng ba điều kiện dưới đây — vì một `config.toml` hỏng
# là một Bridge **không khởi động được**, và lúc đó không còn dashboard nào để sửa lại:
#
# 1. **Kiểm trước khi ghi.** Nội dung mới được parse bằng `tomllib` rồi chạy qua `parse_config`
#    y như lúc khởi động. Không qua được thì file cũ **không bị đụng tới**.
# 2. **Sao lưu bản cũ** kèm dấu thời gian, trước khi thay.
# 3. **Sửa tại chỗ từng dòng**, giữ nguyên chú thích và thứ tự. Dựng lại file từ dict sẽ xoá sạch
#    phần chú thích — thứ duy nhất giải thích vì sao một giá trị được đặt như vậy.

#: Khoá `config.toml` sửa được từ dashboard: `kiểu`, `có phải bí mật không`.
#:
#: Bí mật (`True`) **không bao giờ đi ra** khỏi Bridge: API chỉ báo "có giá trị" hay không, và
#: chuỗi rỗng gửi lên nghĩa là "giữ nguyên" chứ không phải "xoá" — người ta để trống ô mật khẩu
#: vì không muốn đổi nó, không phải vì muốn bỏ mật khẩu.
KHOA_FILE_SUA_DUOC: dict[str, tuple[str, bool]] = {
    "bridge.host": ("str", False),
    "bridge.port": ("int", False),
    "bridge.web_port": ("int", False),
    "security.dashboard_password": ("str", True),
    "security.telegram_token": ("str", True),
    "security.telegram_chat_id": ("str", False),
    "clicker.token": ("str", True),
    "clicker_master.token": ("str", True),
}


def _dat_gia_tri_toml(dong: str, khoa: str, gia_tri: Any) -> str:
    """Một dòng `khoa = gia_tri` theo đúng cú pháp TOML."""
    if isinstance(gia_tri, bool):
        raise ConfigError(f"{khoa}: không nhận giá trị bool")
    if isinstance(gia_tri, int):
        return f"{dong}{khoa} = {gia_tri}"
    chu = str(gia_tri)
    if '"' in chu or "\\" in chu or "\n" in chu:
        # Không tự escape: một token hay mật khẩu chứa dấu nháy là chuyện hiếm tới mức thà từ
        # chối còn hơn ghi ra một file TOML sai mà người ta chỉ phát hiện lúc Bridge không lên.
        raise ConfigError(f"{khoa}: giá trị không được chứa dấu nháy kép, xuống dòng hay dấu \\")
    return f'{dong}{khoa} = "{chu}"'


def _sua_van_ban_toml(van_ban: str, doi: Mapping[str, Any]) -> str:
    """Thay giá trị của từng khoá **tại chỗ**, giữ nguyên chú thích và thứ tự.

    Khoá chưa có thì thêm vào cuối mục của nó; mục chưa có thì thêm mục mới ở cuối file.
    """
    dong_cu = van_ban.splitlines()
    con_lai = dict(doi)
    muc_hien_tai = ""
    ket_qua: list[str] = []
    #: Dòng cuối cùng thuộc về mỗi mục, để chèn khoá mới vào đúng chỗ.
    cuoi_muc: dict[str, int] = {}

    for dong in dong_cu:
        tieu_de = re.match(r"^\s*\[([^\]]+)\]\s*$", dong)
        if tieu_de:
            muc_hien_tai = tieu_de.group(1).strip()
        ket_qua.append(dong)
        # Chỉ nhớ dòng **có nội dung**: nhớ cả dòng trắng cuối mục thì khoá mới bị chèn sau dòng
        # trắng đó và dính vào tiêu đề mục kế tiếp — đúng TOML nhưng đọc thì như thể nó thuộc mục
        # sau.
        if muc_hien_tai and dong.strip():
            cuoi_muc[muc_hien_tai] = len(ket_qua) - 1
        if not tieu_de and muc_hien_tai:
            for khoa, gia_tri in list(con_lai.items()):
                muc, _, ten = khoa.rpartition(".")
                if muc != muc_hien_tai:
                    continue
                if re.match(rf"^\s*{re.escape(ten)}\s*=", dong):
                    dau = dong[: len(dong) - len(dong.lstrip())]
                    ket_qua[-1] = _dat_gia_tri_toml(dau, ten, gia_tri)
                    del con_lai[khoa]

    for khoa, gia_tri in con_lai.items():
        muc, _, ten = khoa.rpartition(".")
        if muc in cuoi_muc:
            ket_qua.insert(cuoi_muc[muc] + 1, _dat_gia_tri_toml("", ten, gia_tri))
            for m, vi_tri in cuoi_muc.items():
                if vi_tri > cuoi_muc[muc]:
                    cuoi_muc[m] = vi_tri + 1
            cuoi_muc[muc] += 1
        else:
            ket_qua.extend(["", f"[{muc}]", _dat_gia_tri_toml("", ten, gia_tri)])
            cuoi_muc[muc] = len(ket_qua) - 1

    return "\n".join(ket_qua) + "\n"


#: Số bản sao lưu `config.toml` giữ lại. Mỗi bản là **bản rõ** của mật khẩu dashboard và token
#: clicker, nên để chúng tích lại vô hạn trong thư mục dự án là tự rải bí mật ra đĩa.
SO_BAN_SAO_CONFIG = 5


def _siet_quyen(duong_dan: Path) -> None:
    """Cho bản sao lưu cùng mức quyền với `config.toml` (chỉ chủ máy và Administrators đọc được).

    `cai-dat.ps1` siết quyền cho `config.toml` bằng `icacls`, nhưng file mới tạo ở đây thì **thừa
    kế** quyền của thư mục — tức là một bản rõ của mật khẩu và token với quyền rộng hơn chính file
    gốc. Chạy được thì tốt, không chạy được cũng không chặn việc lưu: mất bản sao lưu còn tệ hơn.
    """
    if os.name != "nt":
        return
    nguoi_dung = os.environ.get("USERNAME", "")
    if not nguoi_dung:
        return
    with contextlib.suppress(OSError):
        subprocess.run(
            ["icacls", str(duong_dan), "/inheritance:r", "/grant:r",
             f"{nguoi_dung}:(R,W)", "*S-1-5-32-544:(F)", "*S-1-5-18:(F)"],
            capture_output=True, check=False, timeout=10)


def _don_ban_sao_cu(duong_dan: Path, giu: int = SO_BAN_SAO_CONFIG) -> list[Path]:
    """Giữ `giu` bản mới nhất, xoá phần còn lại. Trả về danh sách đã xoá."""
    # Chỉ dọn bản do chính hàm này tạo (`bak-YYYYmmdd-HHMMSS`). Người vận hành tự chép một bản
    # `config.toml.bak-truoc-khi-nang-cap` thì đó là thứ họ cố ý giữ.
    ban = sorted(duong_dan.parent.glob(duong_dan.name + ".bak-????????-??????"), reverse=True)
    da_xoa = []
    for cu in ban[giu:]:
        with contextlib.suppress(OSError):
            cu.unlink()
            da_xoa.append(cu)
    return da_xoa


def sua_config_toml(duong_dan: Path, doi: Mapping[str, Any],
                    project_root: Path | None = None) -> Path:
    """Sửa các khoá trong `config.toml`. Trả về đường dẫn bản sao lưu vừa tạo.

    Ném `ConfigError` **trước khi** chạm vào file nếu khoá lạ, kiểu sai, hoặc nội dung mới không
    qua được đúng phép kiểm mà Bridge chạy lúc khởi động.
    """
    if not doi:
        raise ConfigError("Không có khoá nào để sửa")
    for khoa, gia_tri in doi.items():
        if khoa not in KHOA_FILE_SUA_DUOC:
            raise ConfigError(f"Khoá {khoa} không sửa được ở đây")
        kieu, _ = KHOA_FILE_SUA_DUOC[khoa]
        if kieu == "int" and (isinstance(gia_tri, bool) or not isinstance(gia_tri, int)):
            raise ConfigError(f"{khoa} phải là số nguyên, nhận được {gia_tri!r}")
        if kieu == "str" and not isinstance(gia_tri, str):
            raise ConfigError(f"{khoa} phải là chuỗi, nhận được {gia_tri!r}")

    cu = duong_dan.read_text(encoding="utf-8")
    moi = _sua_van_ban_toml(cu, doi)

    # Phép kiểm y hệt lúc khởi động: cùng `tomllib`, cùng `parse_config`. Một file qua được
    # `tomllib` vẫn có thể làm Bridge từ chối khởi động (ví dụ mở `host` ra ngoài mà mật khẩu
    # trống), nên phải chạy cả hai chứ không chỉ parse.
    try:
        raw = tomllib.loads(moi)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Nội dung mới không phải TOML hợp lệ: {exc}") from exc
    goc = project_root or find_project_root()
    parse_config(raw, source_path=duong_dan, project_root=goc)

    ban_sao = duong_dan.with_name(
        f"{duong_dan.name}.bak-{utc_now().strftime('%Y%m%d-%H%M%S')}")
    ban_sao.write_text(cu, encoding="utf-8", newline="")
    _siet_quyen(ban_sao)
    _don_ban_sao_cu(duong_dan)
    # Ghi qua file tạm rồi đổi tên: mất điện giữa chừng để lại file cũ nguyên vẹn chứ không để
    # lại một `config.toml` cụt.
    tam = duong_dan.with_name(duong_dan.name + ".tam")
    tam.write_text(moi, encoding="utf-8", newline="")
    # Siết quyền TRƯỚC khi đổi tên: file mới thừa kế quyền của thư mục, nên nếu không làm thì lần
    # sửa đầu tiên từ dashboard sẽ **mở toang** đúng cái file mà `cai-dat.ps1` đã khoá lại — bản rõ
    # của mật khẩu dashboard và token clicker.
    _siet_quyen(tam)
    os.replace(tam, duong_dan)
    log.warning("Da sua %d khoa trong %s, ban cu o %s", len(doi), duong_dan.name, ban_sao.name)
    return ban_sao
