"""TCP server nhận kết nối từ các agent.

Bridge là server, EA là client (D-03) — MQL5 không listen được, nên chiều kết nối do ngôn ngữ
quyết định chứ không phải do lựa chọn thiết kế.

Cuối phase 3, Bridge **chưa hiểu gì về giao dịch**. Nó nhận sự kiện, ghi vào DB đúng thứ tự,
phát hiện lỗ hổng chuỗi, theo dõi nhịp sống của agent, và gửi command xuống. Ý nghĩa nghiệp vụ
của event là việc của `bridge/engine/` ở phase 6.

**Về đồng thời và database:** `Database` giữ một kết nối SQLite duy nhất với bộ đếm giao dịch
lồng nhau. Nếu một tác vụ async `await` giữa `BEGIN` và `COMMIT`, một tác vụ khác có thể chen
vào giữa và làm hỏng bộ đếm đó. Vì vậy **mọi lời gọi database ở tầng này đều đồng bộ** và
không có `await` nào nằm trong một giao dịch. SQLite cục bộ ghi dưới một mili giây nên cái giá
phải trả là không đáng kể; đổi lại ta không có cả một lớp lỗi khó tái hiện.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from bridge.clock import parse_iso, utc_now, utc_now_iso
from bridge.db.repo import Database
from bridge.logging_setup import get_logger
from bridge.protocol.auth import verify_token
from bridge.protocol.framing import (
    MAX_LINE_BYTES,
    LineBuffer,
    LineTooLong,
    ProtocolDecodeError,
    decode_line,
    encode_line,
)
from bridge.protocol.messages import (
    AckMessage,
    ConfigMessage,
    ErrorMessage,
    EventMessage,
    HeartbeatMessage,
    HelloAckMessage,
    HelloMessage,
    ResendMessage,
    SnapshotMessage,
    SymbolSpecsMessage,
    parse_agent_message,
)

log = get_logger(__name__)

#: Số lần tối đa hỏi gửi bù cho cùng một mốc `from_seq` trong một phiên kết nối. Quá số này thì
#: coi như agent không còn giữ những event đó — hỏi thêm chỉ tạo thêm tải, không tạo thêm dữ liệu.
MAX_RESEND_ATTEMPTS = 3

DEFAULT_HELLO_TIMEOUT_SEC = 5.0
DEFAULT_MONITOR_INTERVAL_SEC = 0.5
DEFAULT_HEARTBEAT_TIMEOUT_MS = 5000
DEFAULT_HEARTBEAT_INTERVAL_MS = 1000

#: Mã lỗi gửi kèm message `error`. Tiếng Anh không dấu như mọi enum khác (D-16).
ERR_BAD_TOKEN = "BAD_TOKEN"
ERR_ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"
ERR_ROLE_MISMATCH = "ROLE_MISMATCH"
ERR_AGENT_DISABLED = "AGENT_DISABLED"
ERR_BAD_MESSAGE = "BAD_MESSAGE"
ERR_HELLO_TIMEOUT = "HELLO_TIMEOUT"
ERR_HELLO_EXPECTED = "HELLO_EXPECTED"


@dataclass
class ServerConfig:
    """Tham số vận hành của server. Tách ra để test chạy được với thời gian chờ rất ngắn."""

    host: str = "0.0.0.0"
    port: int = 8787
    hello_timeout_sec: float = DEFAULT_HELLO_TIMEOUT_SEC
    max_line_bytes: int = MAX_LINE_BYTES
    monitor_interval_sec: float = DEFAULT_MONITOR_INTERVAL_SEC
    #: None nghĩa là lấy từ `system_config` trong DB.
    heartbeat_timeout_ms: int | None = None


@dataclass
class AgentConnection:
    """Một kết nối đang mở của một agent."""

    agent_id: str
    role: str
    writer: asyncio.StreamWriter
    peer: str
    buffer: LineBuffer
    last_seen_monotonic: float = field(default_factory=time.monotonic)
    closing: bool = False
    #: `from_seq` của yêu cầu gửi bù gần nhất, và số lần đã hỏi cho đúng mốc đó. Nằm trên kết
    #: nối chứ không nằm trong DB: hỏi lại là chuyện của một phiên, nối lại thì đếm từ đầu.
    resend_asked_from: int | None = None
    resend_attempts: int = 0

    async def send(self, message: BaseModel) -> None:
        """Gửi một message xuống agent. Lỗi socket được nuốt và ghi log, không lan lên trên."""
        try:
            self.writer.write(encode_line(message.model_dump(exclude_none=True)))
            await self.writer.drain()
        except (ConnectionError, RuntimeError) as exc:
            log.warning("Không gửi được message tới agent: %s", exc,
                        extra={"agent_id": self.agent_id})

    def close(self) -> None:
        self.closing = True
        with contextlib.suppress(Exception):
            self.writer.close()


class BridgeServer:
    """Server NDJSON/TCP cho các agent MT5."""

    def __init__(self, db: Database, config: ServerConfig | None = None) -> None:
        self.db = db
        self.config = config or ServerConfig()
        self.connections: dict[str, AgentConnection] = {}
        self._server: asyncio.Server | None = None
        self._monitor_task: asyncio.Task[None] | None = None
        self._client_tasks: set[asyncio.Task[None]] = set()
        #: Snapshot gần nhất của từng agent. Phase này chỉ lưu lại, xử lý là việc phase 8.
        self.latest_snapshots: dict[str, SnapshotMessage] = {}
        #: Đặt bởi `CommandDispatcher` để server gửi command tồn đọng ngay sau khi bắt tay.
        self.on_agent_online: Any = None
        #: Đặt bởi `EventProcessor` (phase 6). Được await sau khi ack đã ghi vào DB.
        self.on_command_acked: Any = None

    # -- vòng đời --------------------------------------------------------------------------

    @property
    def port(self) -> int:
        """Cổng thật đang lắng nghe. Test dùng port 0 rồi hỏi lại số thật."""
        if self._server is None or not self._server.sockets:
            return self.config.port
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        self._mark_all_offline("Bridge vua khoi dong")
        self._server = await asyncio.start_server(
            self._handle_client, self.config.host, self.config.port
        )
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        log.info("Bridge lắng nghe trên %s:%d", self.config.host, self.port)

    async def stop(self) -> None:
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task
            self._monitor_task = None
        for connection in list(self.connections.values()):
            connection.close()
        self.connections.clear()
        for task in list(self._client_tasks):
            task.cancel()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None
        self._mark_all_offline("Bridge dung")

    def _mark_all_offline(self, ly_do: str) -> None:
        """Đánh mọi agent về `OFFLINE`.

        Gọi lúc **khởi động** chứ không chỉ lúc dừng, và đó mới là chỗ quan trọng: lúc khởi động
        thì chắc chắn chưa agent nào nối, nên câu này đúng một cách hiển nhiên — và nó dọn được
        cả trạng thái cũ do Bridge chết đột ngột để lại, không riêng đường tắt sạch.

        Vì sao cần: `check_heartbeats()` chỉ duyệt `self.connections`, mà danh sách đó rỗng lúc
        khởi động, nên một dòng `ONLINE` cũ sẽ **không bao giờ** được sửa cho tới khi chính agent
        đó nối lại. Cổng canary của D-25 đọc đúng cột này, nên trạng thái cũ làm nó gác nhầm:
        Bridge tưởng clicker còn sống, tạo pair và gửi `OPEN_UI` vào hư không.
        """
        with self.db.transaction() as conn:
            so = conn.execute(
                "UPDATE agent SET status = 'OFFLINE', updated_at = ? WHERE status <> 'OFFLINE'",
                (utc_now_iso(),),
            ).rowcount
        if so:
            log.info("%s: dat %d agent ve OFFLINE", ly_do, so)

    async def __aenter__(self) -> BridgeServer:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    # -- gửi -------------------------------------------------------------------------------

    def is_online(self, agent_id: str) -> bool:
        connection = self.connections.get(agent_id)
        return connection is not None and not connection.closing

    async def send_to(self, agent_id: str, message: BaseModel) -> bool:
        """Gửi message tới một agent. Trả về False nếu agent đang không kết nối."""
        connection = self.connections.get(agent_id)
        if connection is None or connection.closing:
            return False
        await connection.send(message)
        return True

    # -- bắt tay ---------------------------------------------------------------------------

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        peer_info = writer.get_extra_info("peername")
        peer = f"{peer_info[0]}:{peer_info[1]}" if peer_info else "?"
        buffer = LineBuffer(self.config.max_line_bytes)
        connection: AgentConnection | None = None
        try:
            connection = await asyncio.wait_for(
                self._handshake(reader, writer, buffer, peer), self.config.hello_timeout_sec
            )
            if connection is None:
                return
            await self._read_loop(reader, connection)
        except TimeoutError:
            log.warning("Agent tại %s không gửi hello trong %.1fs, đóng kết nối",
                        peer, self.config.hello_timeout_sec)
            await _send_error(writer, ERR_HELLO_TIMEOUT, "Khong gui hello dung han")
        except (ConnectionError, asyncio.IncompleteReadError):
            log.info("Agent tại %s ngắt kết nối", peer)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Lỗi không lường trước khi phục vụ agent tại %s", peer)
        finally:
            if connection is not None:
                self._unregister(connection)
            with contextlib.suppress(Exception):
                writer.close()

    async def _handshake(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                         buffer: LineBuffer, peer: str) -> AgentConnection | None:
        """Đọc `hello` và xác thực. Trả về None nếu bị từ chối (kết nối sẽ bị đóng)."""
        hello: HelloMessage | None = None
        while hello is None:
            chunk = await reader.read(65536)
            if not chunk:
                return None
            for line in buffer.feed(chunk):
                try:
                    message = parse_agent_message(decode_line(line))
                except (ProtocolDecodeError, ValidationError, ValueError) as exc:
                    log.warning("Message đầu tiên từ %s không hợp lệ: %s", peer, exc)
                    await _send_error(writer, ERR_BAD_MESSAGE, "Message dau tien khong hop le")
                    return None
                if not isinstance(message, HelloMessage):
                    log.warning("Agent tại %s gửi %r trước khi hello", peer, message.kind)
                    await _send_error(writer, ERR_HELLO_EXPECTED, "Phai gui hello truoc")
                    return None
                hello = message
                break

        agent = self._find_agent_by_token(hello.token)
        if agent is None:
            # Không bao giờ ghi token vào log, kể cả token sai.
            log.warning("Từ chối agent tại %s: token không khớp agent nào", peer)
            await _send_error(writer, ERR_BAD_TOKEN, "Token khong hop le")
            return None

        agent_id = agent["agent_id"]
        if not agent["enabled"]:
            log.warning("Từ chối agent %s tại %s: đã bị vô hiệu hoá", agent_id, peer)
            await _send_error(writer, ERR_AGENT_DISABLED, "Agent da bi vo hieu hoa")
            return None
        if agent["role"] != hello.role:
            log.warning("Từ chối agent %s tại %s: role khai báo %s, DB ghi %s",
                        agent_id, peer, hello.role, agent["role"])
            await _send_error(writer, ERR_ROLE_MISMATCH, "Role khong khop")
            return None
        if agent["account_login"] is not None and agent["account_login"] != hello.account_login:
            # Một token chỉ dùng cho đúng một tài khoản MT5.
            log.warning("Từ chối agent %s tại %s: account_login %s không khớp %s trong DB",
                        agent_id, peer, hello.account_login, agent["account_login"])
            await _send_error(writer, ERR_ACCOUNT_MISMATCH, "account_login khong khop")
            return None

        # Terminal khởi động lại là chuyện thường; kết nối cũ chỉ là xác chết.
        existing = self.connections.get(agent_id)
        if existing is not None:
            log.info("Agent %s mở kết nối mới từ %s, đóng kết nối cũ tại %s",
                     agent_id, peer, existing.peer)
            existing.close()

        connection = AgentConnection(agent_id=agent_id, role=hello.role, writer=writer,
                                     peer=peer, buffer=buffer)
        self.connections[agent_id] = connection

        last_seq = int(agent["last_seq"] or 0)
        self.db.upsert_agent(
            agent_id, role=agent["role"], token_hash=agent["token_hash"],
            magic_number=hello.magic, account_login=hello.account_login,
            broker_server=hello.broker_server, terminal_build=hello.terminal_build,
            status="ONLINE", last_seen_at=utc_now_iso(),
        )
        await connection.send(HelloAckMessage(
            agent_id=agent_id, last_seq=last_seq, config=self._agent_config(),
            ts=utc_now_iso(),
        ))
        log.info("Agent %s (%s) đã kết nối từ %s, last_seq = %d",
                 agent_id, hello.role, peer, last_seq)

        if hello.seq > last_seq:
            await self._ask_resend(connection, last_seq + 1,
                                   f"agent khai seq {hello.seq}, Bridge mới có {last_seq}")

        if self.on_agent_online is not None:
            await self.on_agent_online(agent_id)
        return connection

    def _find_agent_by_token(self, token: str) -> Any:
        for row in self.db.query_all("SELECT * FROM agent"):
            if verify_token(token, row["token_hash"]):
                return row
        return None

    def _agent_config(self) -> dict[str, Any]:
        return {
            "heartbeat_interval_ms": self.db.get_config_int(
                "heartbeat_interval_ms", DEFAULT_HEARTBEAT_INTERVAL_MS
            ),
            "heartbeat_timeout_ms": self._heartbeat_timeout_ms(),
        }

    def _heartbeat_timeout_ms(self) -> int:
        if self.config.heartbeat_timeout_ms is not None:
            return self.config.heartbeat_timeout_ms
        return self.db.get_config_int("heartbeat_timeout_ms", DEFAULT_HEARTBEAT_TIMEOUT_MS)

    def _unregister(self, connection: AgentConnection) -> None:
        connection.closing = True
        if self.connections.get(connection.agent_id) is connection:
            del self.connections[connection.agent_id]
            self._set_status(connection.agent_id, "OFFLINE",
                             "Agent ngat ket noi khoi Bridge")

    # -- vòng đọc --------------------------------------------------------------------------

    async def _read_loop(self, reader: asyncio.StreamReader,
                         connection: AgentConnection) -> None:
        while not connection.closing:
            chunk = await reader.read(65536)
            if not chunk:
                log.info("Agent %s đóng kết nối", connection.agent_id,
                         extra={"agent_id": connection.agent_id})
                return
            try:
                lines = connection.buffer.feed(chunk)
            except LineTooLong as exc:
                # Không để một agent lỗi làm cạn bộ nhớ Bridge.
                log.error("Agent %s gửi dòng quá dài, đóng kết nối: %s",
                          connection.agent_id, exc, extra={"agent_id": connection.agent_id})
                connection.close()
                return
            for line in lines:
                await self._handle_line(connection, line)

    async def _handle_line(self, connection: AgentConnection, line: bytes) -> None:
        """Xử lý đúng một dòng. Dòng hỏng chỉ bị bỏ qua — kết nối vẫn sống."""
        try:
            payload = decode_line(line)
        except ProtocolDecodeError as exc:
            log.error("Agent %s gửi dòng không giải mã được: %s", connection.agent_id, exc,
                      extra={"agent_id": connection.agent_id})
            return
        try:
            message = parse_agent_message(payload)
        except (ValidationError, ValueError) as exc:
            log.warning("Agent %s gửi message sai schema: %s", connection.agent_id, exc,
                        extra={"agent_id": connection.agent_id})
            await connection.send(ErrorMessage(code=ERR_BAD_MESSAGE, message="Message sai schema",
                                               ts=utc_now_iso()))
            return

        connection.last_seen_monotonic = time.monotonic()
        if isinstance(message, HeartbeatMessage):
            self._handle_heartbeat(connection, message)
        elif isinstance(message, EventMessage):
            await self._handle_event(connection, message)
        elif isinstance(message, AckMessage):
            await self._handle_ack(connection, message)
        elif isinstance(message, SymbolSpecsMessage):
            self._handle_symbol_specs(connection, message)
        elif isinstance(message, SnapshotMessage):
            self._handle_snapshot(connection, message)
        elif isinstance(message, HelloMessage):
            log.warning("Agent %s gửi hello lần hai trên cùng kết nối, bỏ qua",
                        connection.agent_id, extra={"agent_id": connection.agent_id})

    # -- từng loại message -----------------------------------------------------------------

    def _handle_heartbeat(self, connection: AgentConnection, message: HeartbeatMessage) -> None:
        latency_ms = _latency_ms(message.ts_agent)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE agent SET broker_connected = ?, last_seen_at = ?, "
                "latency_ms = COALESCE(?, latency_ms), equity = COALESCE(?, equity), "
                "margin_level = COALESCE(?, margin_level), updated_at = ? WHERE agent_id = ?",
                (int(message.broker_connected), utc_now_iso(), latency_ms,
                 message.equity, message.margin_level, utc_now_iso(), connection.agent_id),
            )
        # Cố ý KHÔNG đặt `status` trong câu UPDATE trên: `_alert_on_transition()` cần đọc được
        # trạng thái CŨ để biết đây có phải một lần chuyển trạng thái không.
        if not message.broker_connected:
            # Đây là trạng thái nguy hiểm nhất: nhìn từ ngoài hệ thống có vẻ vẫn khoẻ.
            self._alert_on_transition(
                connection.agent_id, "DEGRADED", "ERROR", "AGENT_DEGRADED",
                f"Agent {connection.agent_id} mat ket noi voi broker",
            )
        else:
            self._clear_transition(connection.agent_id, "ONLINE")

    async def _handle_event(self, connection: AgentConnection,
                            message: EventMessage) -> None:
        agent_id = connection.agent_id
        last_seq = self._last_seq(agent_id)

        if message.seq <= last_seq:
            # Event đã có. `record_event()` dedup theo `event_id`, không tạo bản ghi thứ hai.
            log.info("Agent %s gửi lại event seq=%d (last_seq=%d), bỏ qua",
                     agent_id, message.seq, last_seq,
                     extra={"agent_id": agent_id, "event_id": message.id})
            self._record(message, agent_id)
            return

        if message.seq > last_seq + 1:
            con_hoi = await self._ask_resend(
                connection, last_seq + 1,
                f"nhan seq {message.seq} nhung last_seq moi la {last_seq}",
            )
            if not con_hoi:
                self._accept_gap(connection, last_seq + 1, message.seq - 1)

        # Ghi vào DB TRƯỚC khi làm bất cứ việc gì khác với event.
        self._record(message, agent_id)
        self._advance_last_seq(agent_id)

    def _record(self, message: EventMessage, agent_id: str) -> None:
        data = message.data
        payload = message.model_dump(exclude_none=True)
        _, created = self.db.record_event(
            message.id, agent_id, message.seq, message.type,
            position_id=data.position_id,
            caused_by_command_id=message.caused_by_command_id,
            deal_entry=data.deal_entry,
            volume_delta=data.volume_delta,
            volume_after=data.volume_after,
            price=data.price,
            payload_json=_json_text(payload),
            ts_agent=message.ts,
        )
        if created:
            log.info("Ghi event %s type=%s seq=%d", message.id, message.type, message.seq,
                     extra={"agent_id": agent_id, "event_id": message.id})

    def _advance_last_seq(self, agent_id: str) -> None:
        """Đẩy `last_seq` lên tới `seq` liên tục cao nhất đã ghi được.

        Chỉ tăng khi event đã nằm trong DB. Event tới lệch thứ tự (do gửi bù) vì thế không làm
        `last_seq` nhảy cóc qua một lỗ hổng chưa được lấp.
        """
        last_seq = self._last_seq(agent_id)
        while True:
            row = self.db.query_one(
                "SELECT 1 FROM event WHERE agent_id = ? AND seq = ?", (agent_id, last_seq + 1)
            )
            if row is None:
                break
            last_seq += 1
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE agent SET last_seq = ?, updated_at = ? WHERE agent_id = ? "
                "AND last_seq < ?",
                (last_seq, utc_now_iso(), agent_id, last_seq),
            )

    def _last_seq(self, agent_id: str) -> int:
        row = self.db.query_one("SELECT last_seq FROM agent WHERE agent_id = ?", (agent_id,))
        return int(row["last_seq"] or 0) if row is not None else 0

    async def _ask_resend(self, connection: AgentConnection, from_seq: int,
                          reason: str) -> bool:
        """Hỏi gửi bù, có đếm. Trả về ``False`` khi đã quá trần cho đúng mốc `from_seq` này.

        Không có bộ đếm này thì mỗi event tới lệch thứ tự lại sinh một yêu cầu gửi bù, mà mỗi
        yêu cầu lại kéo về nhiều event lệch thứ tự — **mỗi vòng nhân lên**. Đo được ngày
        2026-09-05: hàng nghìn message trong 0,4 giây, EA treo cứng phải gắn lại tay.
        """
        if connection.resend_asked_from != from_seq:
            connection.resend_asked_from = from_seq
            connection.resend_attempts = 0
        connection.resend_attempts += 1
        if connection.resend_attempts > MAX_RESEND_ATTEMPTS:
            return False
        await self._request_resend(connection, from_seq, reason)
        return True

    def _accept_gap(self, connection: AgentConnection, from_seq: int, to_seq: int) -> None:
        """Chấp nhận một lỗ hổng agent không lấp được, để hệ thống đi tiếp.

        Nghe như đầu hàng, nhưng lựa chọn còn lại tệ hơn: `last_seq` đứng im vĩnh viễn và **mọi**
        event sau đó bị coi là lệch thứ tự. Lỗ hổng không lấp được là chuyện có thật — khôi phục
        DB từ bản sao lưu, hoặc tạo lại DB, sinh ra đúng loại đó, và `plan/10` sẽ làm điều này.

        Bỏ event là **mất dữ liệu**, nên nó phải ồn ào: alert CRITICAL kèm đúng khoảng seq đã
        mất, để đối chiếu ở phase 8 biết chỗ mà nhìn. Tuyệt đối không được im lặng.
        """
        agent_id = connection.agent_id
        connection.resend_asked_from = None
        connection.resend_attempts = 0
        if to_seq < from_seq:
            return
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE agent SET last_seq = ?, updated_at = ? WHERE agent_id = ? "
                "AND last_seq < ?",
                (to_seq, utc_now_iso(), agent_id, to_seq),
            )
        self.db.create_alert(
            "CRITICAL", "EVENT_GAP_UNFILLED",
            f"Agent {agent_id} khong cung cap duoc event seq {from_seq}..{to_seq} sau "
            f"{MAX_RESEND_ATTEMPTS} lan hoi. Bo qua khoang nay de he thong di tiep. "
            "CAN DOI CHIEU de biet da mat nhung gi.",
            agent_id=agent_id,
        )
        log.critical("Bo qua lo hong seq %d..%d cua agent %s, khong lap duoc sau %d lan hoi",
                     from_seq, to_seq, agent_id, MAX_RESEND_ATTEMPTS,
                     extra={"agent_id": agent_id})

    async def _request_resend(self, connection: AgentConnection, from_seq: int,
                              reason: str) -> None:
        log.warning("Lỗ hổng chuỗi sự kiện của agent %s (%s), yêu cầu gửi bù từ seq=%d",
                    connection.agent_id, reason, from_seq,
                    extra={"agent_id": connection.agent_id})
        await connection.send(ResendMessage(from_seq=from_seq, ts=utc_now_iso()))

    async def _handle_ack(self, connection: AgentConnection,
                          message: AckMessage) -> None:
        command = self.db.get_command(message.command_id)
        if command is None:
            log.warning("Agent %s ack command %s không có trong DB", connection.agent_id,
                        message.command_id, extra={"agent_id": connection.agent_id,
                                                   "command_id": message.command_id})
            return
        if message.status == "unknown":
            # EA khong biet lenh da khop hay chua. Danh TIMEOUT chu KHONG danh
            # ACK_FAILED: ACK_FAILED se kich hoat chinh sach retry o phase 6 va co
            # the mo lenh thu hai. TIMEOUT dung nghia "khong biet", va phase 6 da
            # quy dinh khong tu dong thu lai sau TIMEOUT (D-13).
            status = "TIMEOUT"
            self.db.create_alert(
                "CRITICAL", "ACK_UNKNOWN",
                f"Agent {connection.agent_id} khong biet ket qua cua command "
                f"{message.command_id}. Can doi chieu truoc khi lam gi tiep.",
                pair_id=command["pair_id"], agent_id=connection.agent_id,
            )
            log.critical(
                "Command %s tra ve unknown: agent da giu cho nhung khong biet ket qua",
                message.command_id,
                extra={"agent_id": connection.agent_id, "command_id": message.command_id,
                       "pair_id": command["pair_id"]},
            )
        else:
            status = "ACK_OK" if message.status in ("ok", "already_closed") else "ACK_FAILED"
        self.db.mark_command_acked(
            message.command_id, status, retcode=message.retcode, retmsg=message.retmsg,
            executed_volume=message.executed_volume,
            result_position_id=message.result_position_id,
        )
        log.info("Command %s nhận ack %s (retcode=%s)", message.command_id, message.status,
                 message.retcode, extra={"agent_id": connection.agent_id,
                                         "command_id": message.command_id,
                                         "pair_id": command["pair_id"]})

        # Tầng nghiệp vụ quyết định làm gì tiếp. Tầng giao thức không biết `pair` là gì.
        if self.on_command_acked is not None:
            await self.on_command_acked(self.db.get_command(message.command_id), message)

    def _handle_symbol_specs(self, connection: AgentConnection,
                             message: SymbolSpecsMessage) -> None:
        specs = [spec.model_dump(exclude_none=True) for spec in message.symbols]
        written = self.db.replace_symbol_specs(connection.agent_id, specs)
        log.info("Agent %s đẩy lên %d symbol spec", connection.agent_id, written,
                 extra={"agent_id": connection.agent_id})

    def _handle_snapshot(self, connection: AgentConnection, message: SnapshotMessage) -> None:
        # Phase này chỉ lưu lại, chưa xử lý. Đối chiếu là việc của phase 8.
        self.latest_snapshots[connection.agent_id] = message
        log.info("Agent %s gửi snapshot với %d vị thế", connection.agent_id,
                 len(message.positions), extra={"agent_id": connection.agent_id})

    # -- theo dõi nhịp sống ----------------------------------------------------------------

    async def _monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.monitor_interval_sec)
            try:
                self.check_heartbeats()
            except Exception:
                log.exception("Lỗi trong vòng quét heartbeat")

    def check_heartbeats(self) -> None:
        """Đánh dấu OFFLINE các agent quá hạn heartbeat. Tách riêng để test gọi thẳng."""
        timeout_sec = self._heartbeat_timeout_ms() / 1000.0
        now = time.monotonic()
        for connection in list(self.connections.values()):
            if now - connection.last_seen_monotonic <= timeout_sec:
                continue
            # Master offline là CRITICAL, Client offline là ERROR (plan 8.2). Mất Master
            # nghĩa là mù hoàn toàn về nguồn lệnh; mất một Client chỉ mất một nhánh copy.
            muc = "CRITICAL" if connection.role == "MASTER" else "ERROR"
            doi = self._alert_on_transition(
                connection.agent_id, "OFFLINE", muc, "AGENT_OFFLINE",
                f"Agent {connection.agent_id} khong gui heartbeat qua han",
            )
            if doi:
                # Vòng quét chạy mỗi vài trăm ms; in mỗi vòng cho một agent **đã** OFFLINE làm
                # nhoè log đúng lúc cần đọc log để tìm nguyên nhân.
                log.warning("Agent %s im lặng quá %dms, chuyển OFFLINE",
                            connection.agent_id, self._heartbeat_timeout_ms(),
                            extra={"agent_id": connection.agent_id})

    def _alert_on_transition(self, agent_id: str, status: str, level: str, code: str,
                             message: str) -> bool:
        """Đặt trạng thái và chỉ tạo alert khi trạng thái **đổi**. Trả về có đổi hay không.

        Tạo alert mỗi vòng quét sẽ làm ngập bảng alert và làm người vận hành quen với màu đỏ.
        """
        row = self.db.get_agent(agent_id)
        if row is not None and row["status"] == status:
            self._touch_status(agent_id, status)
            return False
        self._touch_status(agent_id, status)
        self.db.create_alert(level, code, message, agent_id=agent_id)
        log.warning("Alert %s cho agent %s: %s", code, agent_id, message,
                    extra={"agent_id": agent_id})
        return True

    def _clear_transition(self, agent_id: str, status: str) -> None:
        self._touch_status(agent_id, status)

    def _touch_status(self, agent_id: str, status: str) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE agent SET status = ?, updated_at = ? WHERE agent_id = ?",
                (status, utc_now_iso(), agent_id),
            )

    def _set_status(self, agent_id: str, status: str, message: str) -> None:
        self._alert_on_transition(agent_id, status, "WARNING", "AGENT_OFFLINE", message)

    # -- tiện ích --------------------------------------------------------------------------

    async def broadcast_config(self) -> None:
        """Đẩy tham số sửa nóng xuống mọi agent đang kết nối."""
        message = ConfigMessage(
            heartbeat_interval_ms=self.db.get_config_int("heartbeat_interval_ms",
                                                        DEFAULT_HEARTBEAT_INTERVAL_MS),
            ts=utc_now_iso(),
        )
        for connection in list(self.connections.values()):
            await connection.send(message)


async def _send_error(writer: asyncio.StreamWriter, code: str, message: str) -> None:
    with contextlib.suppress(Exception):
        writer.write(encode_line(
            ErrorMessage(code=code, message=message, ts=utc_now_iso()).model_dump(exclude_none=True)
        ))
        await writer.drain()


def _latency_ms(ts_agent: str | None) -> int | None:
    """Chênh lệch giữa `ts_agent` và thời điểm nhận.

    Ghi nhận, **không tin tuyệt đối**: đồng hồ của terminal có thể lệch, và một giá trị âm chỉ
    nói rằng đồng hồ hai bên không khớp chứ không nói mạng nhanh hơn ánh sáng.
    """
    if not ts_agent:
        return None
    try:
        sent = parse_iso(ts_agent)
    except ValueError:
        return None
    return int((utc_now() - sent).total_seconds() * 1000)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
