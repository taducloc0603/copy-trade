"""Bộ canh vòng sự kiện: ghi lại **đúng dòng code** đang chặn vòng asyncio của Bridge.

Sinh ra từ một phép đo thật trên VPS (2026-09-16): clicker bấm xong trong 0,7 giây, nhưng Bridge
ghi nhận ack của nó muộn 1,3–1,8 giây — và trong **cùng một mili giây** ghi luôn event của Master
lẫn event của Client, ba nguồn độc lập. Tức vòng sự kiện đứng yên rồi đọc dồn. Đổi SQLite sang
`synchronous = NORMAL` không đổi gì. Đoán tiếp là lãng phí; công cụ này trả lời thẳng.

Cách làm: một task trong vòng sự kiện cứ mỗi `nhip_sec` ghi lại mốc "tôi còn chạy". Một **thread**
riêng — không bị vòng sự kiện chặn — thấy mốc đó cũ quá `nguong_sec` thì chụp stack của luồng
chính (`sys._current_frames`) và ghi log WARNING. Mỗi lần bị chặn chỉ ghi **một** stack, cộng một
dòng tổng kết thời gian khi vòng chạy lại.

Chi phí: một `asyncio.sleep` mỗi 50 ms và một thread ngủ. Không đụng vào đường giao dịch.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import traceback

from bridge.logging_setup import get_logger

log = get_logger(__name__)

NHIP_SEC = 0.05
NGUONG_SEC = 0.3
#: Số khung stack ghi lại — đủ thấy từ hàm gọi SQLite lên tới handler nghiệp vụ.
SO_KHUNG = 14


class CanhVongSuKien:
    def __init__(self, nhip_sec: float = NHIP_SEC, nguong_sec: float = NGUONG_SEC) -> None:
        self.nhip_sec = nhip_sec
        self.nguong_sec = nguong_sec
        self._moc = time.monotonic()
        self._task: asyncio.Task[None] | None = None
        self._thread: threading.Thread | None = None
        self._dung = threading.Event()
        self._luong_chinh = threading.get_ident()
        #: Số lần đã phát hiện bị chặn — để test và để đọc.
        self.so_lan_chan = 0

    async def start(self) -> None:
        self._luong_chinh = threading.get_ident()
        self._moc = time.monotonic()
        self._task = asyncio.create_task(self._nhip())
        self._thread = threading.Thread(target=self._canh, name="canh-vong-su-kien", daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        self._dung.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1)

    async def _nhip(self) -> None:
        while True:
            self._moc = time.monotonic()
            await asyncio.sleep(self.nhip_sec)

    def _canh(self) -> None:
        dang_chan_tu: float | None = None
        while not self._dung.wait(self.nhip_sec):
            tre = time.monotonic() - self._moc
            if tre > self.nguong_sec + self.nhip_sec:
                if dang_chan_tu is None:
                    dang_chan_tu = self._moc
                    self.so_lan_chan += 1
                    khung = sys._current_frames().get(self._luong_chinh)
                    stack = ("".join(traceback.format_stack(khung, limit=SO_KHUNG))
                             if khung is not None else "(khong lay duoc stack)")
                    log.warning("Vong su kien Bridge bi chan %.2fs, dang o:\n%s", tre, stack)
            elif dang_chan_tu is not None:
                log.warning("Vong su kien Bridge chay lai sau %.2fs bi chan",
                            time.monotonic() - dang_chan_tu)
                dang_chan_tu = None
