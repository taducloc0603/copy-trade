"""Kênh cảnh báo ra ngoài — Telegram (plan mục 10.4).

Ràng buộc quan trọng nhất, và nó quyết định toàn bộ thiết kế file này:

> **Kênh cảnh báo hỏng không được ảnh hưởng tới luồng giao dịch.**

Nên: chạy ở task riêng, đọc alert từ DB theo chu kỳ chứ không móc vào đường ghi alert, và mọi
lỗi mạng chỉ ghi log rồi thôi. Telegram chết, mạng chết, token sai — luồng copy vẫn chạy y
nguyên. Đây là lý do nó **không** dùng `create_alert()` làm điểm móc: một lời gọi mạng nằm trong
đường ghi alert là một chỗ để cả hệ thống treo theo.

Gộp cảnh báo: cùng một mã lỗi lặp lại trong 60 giây chỉ gửi một tin kèm số lần. Một sự cố làm
ngập điện thoại là cách nhanh nhất để người ta tắt thông báo, và khi đó kênh này thành vô dụng.
**CRITICAL luôn gửi ngay, không gộp** — nếu phải chọn giữa làm phiền và bỏ sót, chọn làm phiền.
"""

from __future__ import annotations

import asyncio
import contextlib
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from bridge.clock import utc_now
from bridge.db.repo import Database
from bridge.logging_setup import get_logger

log = get_logger(__name__)

#: Mức được gửi ra ngoài. INFO và WARNING ở lại trong dashboard.
MUC_GUI = ("ERROR", "CRITICAL")

#: Cửa sổ gộp, tính bằng giây.
CUA_SO_GOP_SEC = 60

#: Mức không bao giờ gộp.
KHONG_GOP = ("CRITICAL",)

CHU_KY_QUET_SEC = 5.0
TIMEOUT_SEC = 8.0


@dataclass
class TinNhan:
    """Một tin chuẩn bị gửi."""

    level: str
    code: str
    text: str
    so_lan: int = 1

    def render(self) -> str:
        dau = "🔴" if self.level == "CRITICAL" else "🟠"
        lap = f" (x{self.so_lan})" if self.so_lan > 1 else ""
        return f"{dau} {self.level} {self.code}{lap}\n{self.text}"


@dataclass
class BoGop:
    """Gộp theo mã lỗi trong một cửa sổ thời gian."""

    cua_so_sec: float = CUA_SO_GOP_SEC
    _lan_cuoi: dict[str, float] = field(default_factory=dict)

    def nen_gui(self, level: str, code: str, bay_gio: float) -> bool:
        if level in KHONG_GOP:
            return True
        truoc = self._lan_cuoi.get(code)
        if truoc is not None and bay_gio - truoc < self.cua_so_sec:
            return False
        self._lan_cuoi[code] = bay_gio
        return True


class TelegramSender:
    """Gửi tin qua Telegram Bot API. Đồng bộ, chạy trong `to_thread`."""

    def __init__(self, token: str, chat_id: str) -> None:
        self.token = token
        self.chat_id = chat_id

    def gui(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        du_lieu = urllib.parse.urlencode(
            {"chat_id": self.chat_id, "text": text}).encode("utf-8")
        try:
            with urllib.request.urlopen(url, data=du_lieu, timeout=TIMEOUT_SEC) as r:
                return 200 <= r.status < 300
        except Exception as exc:
            # KHÔNG ném lên trên. Kênh cảnh báo hỏng không được ảnh hưởng tới giao dịch.
            log.warning("Khong gui duoc canh bao ra Telegram: %s", exc)
            return False


class AlertChannel:
    """Task nền: quét alert mới trong DB và đẩy ra kênh ngoài.

    Đọc theo chu kỳ thay vì móc vào `create_alert()`. Cái giá là trễ vài giây; đổi lại đường ghi
    alert không bao giờ phải chờ mạng, và một kênh hỏng không kéo theo thứ gì.
    """

    def __init__(self, db: Database, sender: Any = None,
                 chu_ky_sec: float = CHU_KY_QUET_SEC) -> None:
        self.db = db
        self.sender = sender
        self.chu_ky_sec = chu_ky_sec
        self.gop = BoGop()
        self._task: asyncio.Task[None] | None = None
        #: `id` alert cuối đã xét. Bắt đầu từ cái mới nhất: khởi động lại không nên dội lại
        #: toàn bộ lịch sử cảnh báo vào điện thoại người vận hành.
        self._moc = self._moc_hien_tai()
        #: Số tin đã gửi và đã nén, để test và để đọc log.
        self.da_gui = 0
        self.da_nen = 0

    def _moc_hien_tai(self) -> int:
        row = self.db.query_one("SELECT COALESCE(MAX(id), 0) n FROM alert")
        return int(row["n"]) if row else 0

    async def start(self) -> None:
        if self.sender is None:
            log.info("Chua cau hinh kenh canh bao ngoai, bo qua")
            return
        self._task = asyncio.create_task(self._vong())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _vong(self) -> None:
        while True:
            try:
                await self.quet_mot_lan()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Kể cả lỗi lập trình ở đây cũng không được kéo theo tiến trình.
                log.exception("Loi trong vong quet canh bao")
            await asyncio.sleep(self.chu_ky_sec)

    async def quet_mot_lan(self) -> int:
        """Quét alert mới và gửi. Trả về số tin đã gửi."""
        rows = self.db.query_all(
            "SELECT id, level, code, message FROM alert WHERE id > ? AND level IN (?, ?) "
            "ORDER BY id", (self._moc, *MUC_GUI))
        if not rows:
            return 0
        bay_gio = utc_now().timestamp()
        so = 0
        for row in rows:
            self._moc = max(self._moc, int(row["id"]))
            if not self.gop.nen_gui(row["level"], row["code"], bay_gio):
                self.da_nen += 1
                log.debug("Nen canh bao %s (trong cua so gop)", row["code"])
                continue
            tin = TinNhan(level=row["level"], code=row["code"], text=row["message"])
            if await asyncio.to_thread(self.sender.gui, tin.render()):
                so += 1
                self.da_gui += 1
        return so


def tao_kenh(db: Database, security: Any) -> AlertChannel:
    """Dựng kênh từ `config.toml`. Thiếu cấu hình thì trả về kênh im lặng, không lỗi."""
    token = None
    chat_id = None
    with contextlib.suppress(KeyError, TypeError):
        token = security["telegram_token"]
        chat_id = security["telegram_chat_id"]
    if not token or not chat_id:
        return AlertChannel(db, sender=None)
    return AlertChannel(db, sender=TelegramSender(str(token), str(chat_id)))
