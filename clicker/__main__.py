"""Điểm khởi động của clicker: ``python -m clicker``.

Hai chế độ. ``--dry-run`` không chạm vào giao diện và trả `rejected` cho mọi lệnh — dùng để thử
đường dây với Bridge. Chế độ thật cần ``--terminal-title`` để biết lái terminal nào, và **không
tự rơi về chạy thử** nếu thiếu: một clicker im lặng không mở lệnh nào là thứ đúng ra phải ồn ào.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import os
import sys
from pathlib import Path

from bridge.config import ConfigError, load_config
from bridge.logging_setup import get_logger, setup_logging
from clicker.journal import CommandJournal
from clicker.link import DEFAULT_HEARTBEAT_SEC, ClickerLink, LinkConfig
from clicker.ui.driver import DryRunDriver, Mt5UiDriver

log = get_logger(__name__)

DEFAULT_JOURNAL = "data/clicker_commands.ndjson"

#: Biến môi trường thay cho ``--token``. Có mặt để Scheduled Task đặt được token mà không phải
#: ghi nó vào XML của task; mục ``[clicker]`` trong ``config.toml`` vẫn là đường chính.
ENV_TOKEN = "COPYBRIDGE_CLICKER_TOKEN"

#: Mã lỗi Win32 khi mutex cùng tên đã tồn tại.
ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Khoá tiến trình đơn.

    Hai clicker cùng lái một terminal là thảm hoạ: cả hai điền vào cùng một hộp thoại, và không
    ai biết cú bấm cuối cùng mang thông số của lệnh nào. Không lấy được khoá thì **thoát ngay**,
    không thử lại — thử lại chỉ làm cái chết chậm hơn chứ không an toàn hơn.
    """

    def __init__(self, name: str) -> None:
        self.name = f"Global\\CopyBridgeClicker-{name}"
        self._handle: int | None = None
        self._lock_file = None

    def acquire(self) -> bool:
        if sys.platform.startswith("win"):
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._handle = kernel32.CreateMutexW(None, True, self.name)
            return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
        # Ngoài Windows chỉ có test chạy; một file khoá là đủ để giữ đúng ngữ nghĩa.
        path = Path(f"/tmp/{self.name.replace(chr(92), '-')}.lock")
        try:
            self._lock_file = path.open("x")
        except FileExistsError:
            return False
        return True

    def release(self) -> None:
        if self._lock_file is not None:
            self._lock_file.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m clicker",
        description="Mo lenh tren terminal MT5 Client qua giao dien (phase 6b).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Dia chi Bridge")
    parser.add_argument("--port", type=int, default=8787, help="Cong Bridge")
    parser.add_argument("--token", default="",
                        help=f"Token bat tay. Thieu thi lay tu bien {ENV_TOKEN}, roi tu muc "
                             "[clicker] trong config.toml")
    parser.add_argument("--account-login", type=int, default=0,
                        help="So tai khoan cua terminal Client (hoac muc [clicker] config.toml)")
    parser.add_argument("--terminal-title", default="",
                        help="Mau tieu de cua so terminal, thuong chua so tai khoan "
                             "(hoac muc [clicker] config.toml)")
    parser.add_argument("--journal", default=DEFAULT_JOURNAL,
                        help=f"Duong dan nhat ky append-only (mac dinh {DEFAULT_JOURNAL})")
    parser.add_argument("--heartbeat-sec", type=float, default=DEFAULT_HEARTBEAT_SEC)
    parser.add_argument("--dry-run", action="store_true",
                        help="Khong cham vao giao dien; moi OPEN_UI deu tra rejected DRY_RUN")
    return parser


def doc_muc_clicker() -> dict[str, object]:
    """Trả về mục ``[clicker]`` của ``config.toml``, hoặc rỗng nếu không đọc được.

    Không ném: clicker chạy được hoàn toàn bằng tham số dòng lệnh, và một máy chỉ chạy clicker
    thì không nhất thiết có ``config.toml``. Thiếu giá trị thật sự cần thì `bo_sung_tham_so`
    mới là chỗ báo lỗi, và ở đó thông báo nói rõ cả ba đường.
    """
    try:
        return dict(load_config().clicker)
    except ConfigError as exc:
        log.info("Khong doc duoc config.toml (%s). Chi dung tham so dong lenh va bien moi truong.",
                 exc)
        return {}


def bo_sung_tham_so(args: argparse.Namespace) -> None:
    """Điền `token`, `account_login`, `terminal_title` còn thiếu từ môi trường và ``config.toml``.

    Thứ tự: tham số dòng lệnh → biến môi trường (chỉ token) → mục ``[clicker]``.

    Dòng lệnh vẫn thắng vì gỡ lỗi tại chỗ cần nó, **nhưng đường chạy thường phải là
    ``config.toml``**: dòng lệnh của một tiến trình là thứ mọi tài khoản trên cùng máy đọc được
    (``Get-CimInstance Win32_Process``), nên `--token` trong một Scheduled Task chạy 24/7 là token
    phơi ra suốt ngày. `config.toml` thì siết được bằng ACL.
    """
    thieu = not (args.token and args.account_login and args.terminal_title)
    muc = doc_muc_clicker() if thieu else {}

    if not args.token:
        args.token = str(os.environ.get(ENV_TOKEN) or "") or str(muc.get("token") or "")
    if not args.account_login:
        tu_muc = muc.get("account_login")
        args.account_login = int(tu_muc) if isinstance(tu_muc, int) else 0
    if not args.terminal_title:
        args.terminal_title = str(muc.get("terminal_title") or "")


def build_link(args: argparse.Namespace) -> ClickerLink:
    driver = (DryRunDriver() if args.dry_run
              else Mt5UiDriver(terminal_title=args.terminal_title))
    return ClickerLink(
        config=LinkConfig(
            host=args.host, port=args.port, token=args.token,
            account_login=args.account_login, terminal_title=args.terminal_title,
            heartbeat_sec=args.heartbeat_sec,
        ),
        journal=CommandJournal(args.journal),
        driver=driver,
        dry_run=args.dry_run,
    )


#: File log riêng của clicker, **không** được trùng `bridge.log` của Bridge.
#:
#: Hai tiến trình chạy lâu cùng giữ một file mở thì trên Windows lần xoay lúc nửa đêm không đổi
#: tên được file (`WinError 32`). Lần xoay hỏng không cập nhật mốc xoay kế tiếp, nên mọi lần ghi
#: sau đó lại thử xoay, lại hỏng — **cả hai tiến trình ngừng ghi log vĩnh viễn** mà vẫn chạy bình
#: thường. Đã xảy ra thật trên VPS: `bridge.log` đứng im 63 giờ (2026-09-08 → 09-11).
LOG_FILENAME = "clicker.log"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(filename=LOG_FILENAME)
    bo_sung_tham_so(args)

    if not args.token:
        log.critical("Thieu token. Dat mot trong ba: --token, bien %s, hoac muc [clicker] trong "
                     "config.toml. Cap token bang: python -m bridge.admin cap-token <AGENT_ID>",
                     ENV_TOKEN)
        return 2
    if not args.account_login:
        log.critical("Thieu so tai khoan. Dat --account-login hoac clicker.account_login trong "
                     "config.toml.")
        return 2

    if not args.dry_run and not args.terminal_title:
        # Không đoán terminal. Lái nhầm terminal là mất tiền ở một tài khoản mà sổ sách không
        # hề biết tới, và đó là loại lỗi không tự lộ ra.
        log.critical("Che do that bat buoc phai co --terminal-title. Khong tu doan terminal, "
                     "va khong tu rot ve --dry-run.")
        return 2

    lock = SingleInstance(str(args.account_login))
    if not lock.acquire():
        log.critical("Da co mot clicker khac dang lai terminal %s. Thoat.", args.account_login)
        return 3

    link = build_link(args)
    log.info("Clicker khoi dong o che do %s, nhat ky %s, %d command da biet",
             "CHAY THU" if args.dry_run else "THAT",
             link.journal.path, len(link.journal))
    try:
        asyncio.run(link.run())
    except KeyboardInterrupt:
        log.info("Nhan tin hieu dung, thoat")
    finally:
        lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
