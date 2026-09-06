"""Điểm khởi động của clicker: ``python -m clicker``.

Hai chế độ. ``--dry-run`` không chạm vào giao diện và trả `rejected` cho mọi lệnh — dùng để thử
đường dây với Bridge. Chế độ thật cần ``--terminal-title`` để biết lái terminal nào, và **không
tự rơi về chạy thử** nếu thiếu: một clicker im lặng không mở lệnh nào là thứ đúng ra phải ồn ào.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import sys
from pathlib import Path

from bridge.logging_setup import get_logger, setup_logging
from clicker.journal import CommandJournal
from clicker.link import DEFAULT_HEARTBEAT_SEC, ClickerLink, LinkConfig
from clicker.ui.driver import DryRunDriver, Mt5UiDriver

log = get_logger(__name__)

DEFAULT_JOURNAL = "data/clicker_commands.ndjson"

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
    parser.add_argument("--token", required=True, help="Token bat tay, khop voi agent trong DB")
    parser.add_argument("--account-login", type=int, required=True,
                        help="So tai khoan cua terminal Client")
    parser.add_argument("--terminal-title", default="",
                        help="Mau tieu de cua so terminal, thuong chua so tai khoan")
    parser.add_argument("--journal", default=DEFAULT_JOURNAL,
                        help=f"Duong dan nhat ky append-only (mac dinh {DEFAULT_JOURNAL})")
    parser.add_argument("--heartbeat-sec", type=float, default=DEFAULT_HEARTBEAT_SEC)
    parser.add_argument("--dry-run", action="store_true",
                        help="Khong cham vao giao dien; moi OPEN_UI deu tra rejected DRY_RUN")
    return parser


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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging()

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
