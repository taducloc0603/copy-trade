"""Kết nối clicker ↔ Bridge: cùng một giao thức NDJSON mà EA dùng, không thêm gì.

Clicker là TCP client, Bridge là TCP server (D-03) — giống hệt EA. Nó khai `role = "CLICKER"`,
và đó là toàn bộ khác biệt ở tầng giao thức.

Ba điều nó **không** làm, và đều là cố ý:

* Không gửi `event`. Vị thế do EA Client báo lên; clicker không nhìn thấy sổ lệnh.
* Không trả lời `REQUEST_SNAPSHOT`. Nó không có vị thế nào để báo cáo — Bridge cũng đã lọc theo
  role nên lệnh này không bao giờ tới.
* Không nhận `CLOSE`. Đường đóng vẫn là `OrderSend` của EA và không đổi ở phase 6b.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from typing import Any

from bridge.clock import utc_now_iso
from bridge.logging_setup import get_logger
from bridge.protocol.framing import LineBuffer, encode_line
from clicker.journal import CommandJournal
from clicker.ui import probe as ui_probe
from clicker.ui.driver import OpenDriver, OpenRequest

log = get_logger(__name__)

#: Loại command duy nhất clicker biết làm. Mọi loại khác bị từ chối — kể cả `OPEN`, để một lỗi
#: định tuyến không bao giờ biến thành một lệnh `EXPERT` lặng lẽ (plan 6b mục 6b.2).
SUPPORTED_COMMAND = "OPEN_UI"

DEFAULT_HEARTBEAT_SEC = 5.0
DEFAULT_RECONNECT_SEC = 3.0


@dataclass
class LinkConfig:
    """Cấu hình khởi động của clicker."""

    host: str
    port: int
    token: str
    account_login: int
    #: Mẩu tiêu đề để nhận ra đúng cửa sổ terminal. Chứa số tài khoản nên nó cũng là hàng rào
    #: chống gửi lệnh nhầm terminal.
    terminal_title: str = ""
    magic: int = 0
    heartbeat_sec: float = DEFAULT_HEARTBEAT_SEC
    reconnect_sec: float = DEFAULT_RECONNECT_SEC


@dataclass
class ClickerLink:
    """Vòng đời kết nối và xử lý command."""

    config: LinkConfig
    journal: CommandJournal
    driver: OpenDriver
    #: Ở chế độ chạy thử, canary luôn báo đỏ: một clicker không chạm vào giao diện thì **không**
    #: điều khiển được giao diện, và Bridge phải biết điều đó thay vì gửi lệnh vào hư không.
    dry_run: bool = True

    agent_id: str | None = None
    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    buffer: LineBuffer = field(default_factory=LineBuffer)
    #: Đúng một lệnh được xử lý tại một thời điểm. Bridge đã có cổng riêng, nhưng hai lớp độc
    #: lập cho cùng một sai lầm là đúng mức thận trọng khi hậu quả là một lệnh thừa.
    _gate: asyncio.Lock = field(default_factory=asyncio.Lock)
    #: Message đã tách dòng nhưng chưa xử lý.
    _pending: list[dict[str, Any]] = field(default_factory=list)
    _stopping: bool = False

    # -- sức khoẻ ----------------------------------------------------------------------------

    def health(self) -> ui_probe.ProbeResult:
        """Canary. Kết quả đi vào `heartbeat.broker_connected`, hiểu là "điều khiển được giao diện"."""
        if self.dry_run:
            return ui_probe.ProbeResult(False, "DRY_RUN: khong dieu khien giao dien")
        return ui_probe.probe(self.config.terminal_title)

    # -- vòng đời ----------------------------------------------------------------------------

    async def run(self) -> None:
        """Chạy mãi: kết nối, phục vụ, mất kết nối thì chờ rồi nối lại."""
        while not self._stopping:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Mat ket noi toi Bridge: %s", exc)
            if self._stopping:
                break
            await asyncio.sleep(self.config.reconnect_sec)

    async def run_once(self) -> None:
        """Một phiên kết nối, từ lúc bắt tay tới lúc đứt."""
        await self.connect()
        try:
            reply = await self.handshake()
            if reply.get("kind") != "hello_ack":
                raise RuntimeError(f"Bridge tu choi bat tay: {reply}")
            log.info("Da bat tay voi Bridge, agent_id = %s", self.agent_id)
            heartbeat = asyncio.create_task(self._heartbeat_loop())
            try:
                await self._read_loop()
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
        finally:
            await self.close()

    async def connect(self) -> None:
        self.reader, self.writer = await asyncio.open_connection(self.config.host,
                                                                 self.config.port)
        self.buffer = LineBuffer()
        self._pending.clear()

    async def close(self) -> None:
        if self.writer is not None:
            with contextlib.suppress(Exception):
                self.writer.close()
            with contextlib.suppress(Exception):
                await self.writer.wait_closed()
        self.reader = None
        self.writer = None

    def stop(self) -> None:
        self._stopping = True

    # -- gửi ---------------------------------------------------------------------------------

    async def send(self, message: dict[str, Any]) -> None:
        if self.writer is None:
            raise RuntimeError("Chua ket noi toi Bridge")
        self.writer.write(encode_line(message))
        await self.writer.drain()

    async def handshake(self) -> dict[str, Any]:
        await self.send({
            "v": 1, "kind": "hello", "ts": utc_now_iso(),
            "token": self.config.token, "role": "CLICKER",
            "account_login": self.config.account_login,
            "magic": self.config.magic, "seq": 0,
        })
        reply = await self._read_message()
        if reply.get("kind") == "hello_ack":
            self.agent_id = reply.get("agent_id")
        return reply

    async def send_heartbeat(self) -> None:
        health = self.health()
        await self.send({
            "v": 1, "kind": "heartbeat", "ts": utc_now_iso(), "seq": 0,
            "broker_connected": bool(health),
            "positions_count": 0, "ts_agent": utc_now_iso(),
        })
        if not health:
            log.warning("Canary bao do: %s", health.detail)

    async def _heartbeat_loop(self) -> None:
        while True:
            await self.send_heartbeat()
            await asyncio.sleep(self.config.heartbeat_sec)

    # -- nhận --------------------------------------------------------------------------------

    async def _read_message(self) -> dict[str, Any]:
        """Message kế tiếp, lấy từ hàng chờ trước rồi mới đọc thêm từ socket.

        Hàng chờ không phải tối ưu hoá: Bridge gửi command ngay khi bắt tay xong, nên `hello_ack`
        và một command thường về trong **cùng một chunk TCP**. Đọc chunk rồi chỉ lấy dòng đầu là
        đánh rơi command đó, và nó chỉ hiện ra dưới dạng một lệnh không bao giờ được thực thi.
        """
        assert self.reader is not None
        while True:
            if self._pending:
                return self._pending.pop(0)
            chunk = await self.reader.read(65536)
            if not chunk:
                raise ConnectionError("Bridge dong ket noi")
            self._pending.extend(json.loads(line.decode("utf-8"))
                                 for line in self.buffer.feed(chunk))

    async def _read_loop(self) -> None:
        while True:
            message = await self._read_message()
            if message.get("kind") == "command":
                await self.send(await self.handle_command(message))

    # -- xử lý command -------------------------------------------------------------------------

    async def handle_command(self, message: dict[str, Any]) -> dict[str, Any]:
        """Trả về ack cho một command. Đây là nơi tính bất biến được thực thi."""
        command_id = message.get("command_id") or ""

        def ack(status: str, retmsg: str) -> dict[str, Any]:
            return {"v": 1, "kind": "ack", "ts": utc_now_iso(), "command_id": command_id,
                    "status": status, "retmsg": retmsg[:500], "attempt": 1}

        if message.get("type") != SUPPORTED_COMMAND:
            return ack("rejected", f"Clicker khong nhan command loai {message.get('type')}")

        # Đã biết `command_id` này rồi thì TUYỆT ĐỐI không chạm vào giao diện lần nữa.
        known = self.journal.get(command_id)
        if known is not None:
            if known.ack is not None:
                log.warning("Nhan lai command %s, gui lai ack cu nguyen van", command_id,
                            extra={"command_id": command_id})
                return dict(known.ack)
            log.critical("Nhan lai command %s da giu cho nhung khong co ack. Tra unknown.",
                         command_id, extra={"command_id": command_id})
            return ack("unknown", "Da giu cho nhung khong biet da bam hay chua")

        async with self._gate:
            return await asyncio.to_thread(self._execute, message, command_id)

    def _execute(self, message: dict[str, Any], command_id: str) -> dict[str, Any]:
        """Phần đồng bộ: giữ chỗ, kiểm tra, rồi giao cho driver.

        Chạy trong thread riêng vì driver thật gọi Win32 và `fsync` — cả hai đều chặn, và chặn
        vòng lặp sự kiện thì heartbeat ngừng, Bridge tưởng clicker chết.
        """
        def ack(status: str, retmsg: str) -> dict[str, Any]:
            return {"v": 1, "kind": "ack", "ts": utc_now_iso(), "command_id": command_id,
                    "status": status, "retmsg": retmsg[:500], "attempt": 1}

        # GIỮ CHỖ TRƯỚC. Sau dòng này, một lần khởi động lại sẽ thấy `command_id` và từ chối
        # bấm lại — kể cả khi nó chưa kịp làm gì cả. Thiếu lệnh an toàn hơn thừa lệnh.
        self.journal.reserve(command_id)

        deadline = message.get("deadline_ts")
        if deadline and deadline <= utc_now_iso():
            result = ack("rejected", f"Command da qua han: {deadline}")
            self.journal.complete(command_id, result)
            return result

        try:
            request = OpenRequest.from_payload(message.get("payload") or {})
        except ValueError as exc:
            result = ack("rejected", f"Payload khong hop le: {exc}")
            self.journal.complete(command_id, result)
            return result

        # Ghi "đã bấm" xuống đĩa NGAY TRƯỚC cú bấm, không phải sau. Mất điện giữa hai việc đó
        # thì lần khởi động lại phải giả định là đã bấm — thiếu lệnh sửa được, thừa lệnh thì không.
        if hasattr(self.driver, "on_before_click"):
            self.driver.on_before_click = lambda: self.journal.mark_clicked(command_id)

        try:
            outcome = self.driver.open(request)
        except Exception as exc:
            # Driver ném ngoại lệ giữa chừng: KHÔNG được kết luận là chưa bấm.
            log.exception("Driver hong khi xu ly command %s", command_id)
            result = ack("unknown", f"Driver hong giua chung: {exc}")
            self.journal.complete(command_id, result)
            return result

        # KHÔNG ghi "đã bấm" ở đây. Việc đó đã do `on_before_click` làm, và làm **trước** cú bấm
        # — ghi lại lần nữa sau khi driver trả về là thừa, và tệ hơn là làm người đọc tưởng cú
        # bấm được ghi nhận sau khi xong, đúng thứ tự nguy hiểm mà cái hook sinh ra để tránh.
        result = ack(outcome.status, outcome.reason)
        self.journal.complete(command_id, result)
        log.info("Command %s -> %s (%s)", command_id, outcome.status, outcome.reason,
                 extra={"command_id": command_id})
        return result
