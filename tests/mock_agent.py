"""Mock agent: một TCP client Python giả lập EA.

Đây là **công cụ dùng lại cho mọi phase sau**, không phải đồ dùng một lần. Phase 5 sẽ mở rộng
nó để mô phỏng thực thi lệnh; phase 6–8 dùng nó thay cho terminal MT5 thật.

Nguyên tắc: mock agent nói **đúng** giao thức ở `bridge/protocol/messages.py`, không hơn không
kém. Nếu phải sửa giao thức để EA thật chạy được ở phase 4, phải sửa cả file này.

Nó cố tình cho phép làm sai:

* tự đặt `seq` để tạo lỗ hổng hoặc gửi trùng;
* gửi dòng rác, dòng quá dài, JSON không hợp lệ;
* ngắt kết nối đột ngột rồi nối lại và gửi bù;
* trả ack với `retcode` bất kỳ, kể cả mã lỗi.

Đường đi thuận lợi hiếm khi hỏng — cái cần test là những thứ trên.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bridge.clock import utc_now_iso
from bridge.protocol.framing import LineBuffer, encode_line

DEFAULT_TIMEOUT = 2.0


@dataclass
class MockPosition:
    """Một vị thế trong bộ nhớ của mock agent, dùng để trả lời `snapshot`."""

    position_id: int
    symbol: str
    direction: str
    volume: float
    ticket: int | None = None
    price_open: float | None = None
    magic: int | None = None

    def as_wire(self) -> dict[str, Any]:
        payload = {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "volume": self.volume,
        }
        for name in ("ticket", "price_open", "magic"):
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        return payload


@dataclass
class MockAgent:
    """Giả lập một EA gắn vào terminal MT5."""

    host: str
    port: int
    token: str
    role: str = "CLIENT"
    account_login: int = 222222
    magic: int = 770001
    broker_server: str | None = "DemoServer"
    terminal_build: int | None = 4200

    #: `seq` của event kế tiếp. Test đặt tay để tạo lỗ hổng hoặc gửi lại số cũ.
    seq: int = 0
    positions: dict[int, MockPosition] = field(default_factory=dict)
    #: `retcode` trả về cho command kế tiếp; None nghĩa là thành công (10009).
    next_retcode: int | None = None
    #: Trễ khớp lệnh giả lập, tính bằng giây.
    execution_delay_sec: float = 0.0
    #: Tự động trả ack khi nhận command. Tắt để test tình huống Bridge không nhận được ack.
    auto_ack: bool = True
    #: `command_id` đã xử lý, để mô phỏng tính bất biến của EA thật (phase 5).
    handled_commands: dict[str, dict[str, Any]] = field(default_factory=dict)

    reader: asyncio.StreamReader | None = None
    writer: asyncio.StreamWriter | None = None
    buffer: LineBuffer = field(default_factory=LineBuffer)
    inbox: list[dict[str, Any]] = field(default_factory=list)
    agent_id: str | None = None
    last_seq_from_bridge: int = 0
    _pump_task: asyncio.Task[None] | None = None
    #: Hàm tuỳ chọn để test can thiệp vào cách trả ack.
    on_command: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None

    # -- kết nối ---------------------------------------------------------------------------

    async def connect(self) -> None:
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        self.buffer = LineBuffer()

    async def handshake(self, *, token: str | None = None, role: str | None = None,
                        account_login: int | None = None,
                        seq: int | None = None) -> dict[str, Any]:
        """Gửi `hello` và chờ phản hồi. Trả về message nhận được (`hello_ack` hoặc `error`)."""
        await self.send_raw({
            "v": 1,
            "kind": "hello",
            "ts": utc_now_iso(),
            "token": token if token is not None else self.token,
            "role": role if role is not None else self.role,
            "account_login": (account_login if account_login is not None
                              else self.account_login),
            "broker_server": self.broker_server,
            "terminal_build": self.terminal_build,
            "magic": self.magic,
            "seq": seq if seq is not None else self.seq,
        })
        reply = await self.expect("hello_ack", "error")
        if reply["kind"] == "hello_ack":
            self.agent_id = reply["agent_id"]
            self.last_seq_from_bridge = reply["last_seq"]
        return reply

    async def start(self, **handshake_kwargs: Any) -> dict[str, Any]:
        """Kết nối, bắt tay, rồi bật vòng đọc nền tự trả ack."""
        await self.connect()
        reply = await self.handshake(**handshake_kwargs)
        if reply["kind"] == "hello_ack":
            self._pump_task = asyncio.create_task(self._pump())
            # Bridge gửi REQUEST_SNAPSHOT ngay trong lúc bắt tay, nên command đó có thể đã nằm
            # sẵn trong hộp thư trước khi vòng đọc nền kịp chạy. Xử lý nốt để không bỏ sót.
            if self.auto_ack:
                for message in list(self.inbox):
                    if message.get("kind") == "command":
                        await self._auto_ack(message)
        return reply

    async def close(self) -> None:
        """Đóng kết nối một cách bình thường."""
        await self.kill()

    async def kill(self) -> None:
        """Ngắt kết nối đột ngột, như khi terminal bị tắt hoặc mất mạng."""
        if self._pump_task is not None:
            self._pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pump_task
            self._pump_task = None
        if self.writer is not None:
            with contextlib.suppress(Exception):
                self.writer.close()
            with contextlib.suppress(Exception):
                await self.writer.wait_closed()
        self.reader = None
        self.writer = None

    async def __aenter__(self) -> MockAgent:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.kill()

    # -- gửi -------------------------------------------------------------------------------

    async def send_raw(self, payload: dict[str, Any]) -> None:
        """Gửi một message dưới dạng dict — cho phép gửi cả message sai schema."""
        assert self.writer is not None, "Chưa kết nối"
        self.writer.write(encode_line(payload))
        await self.writer.drain()

    async def send_bytes(self, raw: bytes) -> None:
        """Gửi byte thô. Dùng để cắt một message thành nhiều mảnh hoặc gửi dòng rác."""
        assert self.writer is not None, "Chưa kết nối"
        self.writer.write(raw)
        await self.writer.drain()

    async def send_symbol_specs(self, specs: list[dict[str, Any]]) -> None:
        await self.send_raw({"v": 1, "kind": "symbol_specs", "ts": utc_now_iso(),
                             "symbols": specs})

    async def send_heartbeat(self, *, broker_connected: bool = True, equity: float = 10000.0,
                             margin_level: float | None = 500.0,
                             ts_agent: str | None = None) -> None:
        await self.send_raw({
            "v": 1, "kind": "heartbeat", "ts": utc_now_iso(), "seq": self.seq,
            "broker_connected": broker_connected, "equity": equity,
            "margin_level": margin_level, "positions_count": len(self.positions),
            "ts_agent": ts_agent or utc_now_iso(),
        })

    async def send_snapshot(self, command_id: str | None = None) -> None:
        await self.send_raw({
            "v": 1, "kind": "snapshot", "ts": utc_now_iso(), "command_id": command_id,
            "positions": [p.as_wire() for p in self.positions.values()],
        })

    async def send_event(self, event_type: str, *, seq: int | None = None,
                         event_id: str | None = None,
                         caused_by_command_id: str | None = None,
                         **data: Any) -> str:
        """Gửi một event.

        `seq` mặc định là số kế tiếp. Truyền tay để tạo lỗ hổng (nhảy cóc) hoặc gửi trùng
        (số cũ). `event_id` mặc định theo mẫu của EA thật: ``EVT-<agent>-<seq>``.
        """
        used_seq = self.seq + 1 if seq is None else seq
        used_id = event_id or f"EVT-{self.agent_id or 'MOCK'}-{used_seq}"
        await self.send_raw({
            "v": 1, "kind": "event", "ts": utc_now_iso(), "id": used_id, "seq": used_seq,
            "type": event_type, "caused_by_command_id": caused_by_command_id,
            "data": {k: v for k, v in data.items() if v is not None},
        })
        self.seq = max(self.seq, used_seq)
        return used_id

    async def send_ack(self, command_id: str, *, status: str = "ok", retcode: int = 10009,
                       retmsg: str | None = None, executed_volume: float | None = None,
                       result_position_id: int | None = None, attempt: int = 1) -> None:
        await self.send_raw({
            "v": 1, "kind": "ack", "ts": utc_now_iso(), "command_id": command_id,
            "status": status, "retcode": retcode, "retmsg": retmsg,
            "executed_volume": executed_volume, "result_position_id": result_position_id,
            "attempt": attempt,
        })

    # -- nhận ------------------------------------------------------------------------------

    async def _read_once(self, timeout: float) -> dict[str, Any] | None:
        """Đọc thêm dữ liệu cho tới khi có ít nhất một message mới trong hộp thư."""
        assert self.reader is not None, "Chưa kết nối"
        while True:
            chunk = await asyncio.wait_for(self.reader.read(65536), timeout)
            if not chunk:
                return None
            lines = self.buffer.feed(chunk)
            if lines:
                for line in lines:
                    self.inbox.append(json.loads(line.decode("utf-8")))
                return self.inbox[-1]

    async def receive(self, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
        """Lấy message kế tiếp, đọc thêm từ socket nếu hộp thư rỗng."""
        if self.inbox:
            return self.inbox.pop(0)
        await self._read_once(timeout)
        assert self.inbox, "Không nhận được message nào"
        return self.inbox.pop(0)

    async def expect(self, *kinds: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
        """Chờ tới khi nhận được một message thuộc một trong các `kinds`.

        Các message khác loại đến trước vẫn được giữ lại trong `inbox`.
        """
        async def _wait() -> dict[str, Any]:
            while True:
                for index, message in enumerate(self.inbox):
                    if message.get("kind") in kinds:
                        return self.inbox.pop(index)
                if self._pump_task is not None:
                    # Vòng đọc nền đang giữ socket; chỉ cần chờ nó bỏ message vào hộp thư.
                    await asyncio.sleep(0.005)
                else:
                    await self._read_once(timeout)

        return await asyncio.wait_for(_wait(), timeout)

    async def wait_for_command(self, command_type: str | None = None,
                               timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
        """Chờ một command.

        Mặc định **bỏ qua `REQUEST_SNAPSHOT`** vì Bridge tự gửi nó ngay sau mỗi lần bắt tay —
        nó là hạ tầng, không phải thứ test đang chờ. Muốn bắt chính nó thì truyền tên vào.
        """
        wanted = command_type or ""
        while True:
            message = await self.expect("command", timeout=timeout)
            if command_type is not None:
                if message["type"] == wanted:
                    return message
                continue
            if message["type"] != "REQUEST_SNAPSHOT":
                return message

    # -- vòng đọc nền ----------------------------------------------------------------------

    async def _pump(self) -> None:
        """Đọc liên tục và tự trả ack cho command, giống EA thật đang chạy."""
        try:
            while self.reader is not None:
                chunk = await self.reader.read(65536)
                if not chunk:
                    return
                for line in self.buffer.feed(chunk):
                    message = json.loads(line.decode("utf-8"))
                    self.inbox.append(message)
                    if message.get("kind") == "command" and self.auto_ack:
                        await self._auto_ack(message)
        except (asyncio.CancelledError, ConnectionError):
            raise
        except Exception:
            return

    async def _auto_ack(self, command: dict[str, Any]) -> None:
        command_id = command["command_id"]
        if self.execution_delay_sec:
            await asyncio.sleep(self.execution_delay_sec)

        if command["type"] == "REQUEST_SNAPSHOT":
            await self.send_snapshot(command_id)
            await self.send_ack(command_id, status="ok", retcode=10009)
            return

        # Tính bất biến: command đã xử lý thì trả lại đúng ack cũ, không thực thi lần hai.
        if command_id in self.handled_commands:
            await self.send_raw(self.handled_commands[command_id])
            return

        override = self.on_command(command) if self.on_command is not None else None
        retcode = self.next_retcode if self.next_retcode is not None else 10009
        ack = {
            "v": 1, "kind": "ack", "ts": utc_now_iso(), "command_id": command_id,
            "status": "ok" if retcode == 10009 else "failed", "retcode": retcode,
            "executed_volume": command.get("payload", {}).get("volume"),
            "attempt": 1,
        }
        if override:
            ack.update(override)
        self.handled_commands[command_id] = ack
        await self.send_raw(ack)
