"""Schema message của giao thức Bridge ↔ Agent (pydantic v2).

Envelope chung cho mọi message: ``v`` (số phiên bản, hiện tại 1), ``kind``, ``ts``.

Đây là **hợp đồng giữa Python và MQL5**. EA ở phase 4 và 5 phải nói đúng những gì mô tả ở đây;
mock agent trong `tests/mock_agent.py` cũng vậy. Nếu phải sửa giao thức để EA thật chạy được,
sửa cả ba nơi: file này, mock agent, và test.

Hai ràng buộc quan trọng nhất của file này, cả hai đều bảo vệ D-14:

* ``position_closed`` và ``position_changed`` **bắt buộc** có ``volume_after``. Bridge không
  bao giờ tự tính trạng thái sau sự kiện bằng phép trừ.
* Mọi event sinh từ deal **bắt buộc** có ``deal_entry``. Chỉ ``order_rejected`` được miễn,
  vì nó không sinh từ deal nào.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PROTOCOL_VERSION = 1

#: `CLICKER` là tiến trình mở lệnh qua giao diện MT5 (D-22). Nó không có vị thế nào, không
#: sinh event, và chỉ nhận `OPEN_UI`.
AgentRole: TypeAlias = Literal["MASTER", "CLIENT", "CLICKER"]
Direction: TypeAlias = Literal["BUY", "SELL"]
DealEntry: TypeAlias = Literal["IN", "OUT", "INOUT", "OUT_BY"]
EventType: TypeAlias = Literal[
    "position_opened", "position_closed", "position_changed", "order_rejected"
]
#: `OPEN_UI` là loại RIÊNG, cố ý không tái dùng `OPEN`. Nếu định tuyến sai mà EA nhận `OPEN`,
#: nó sẽ **lặng lẽ đặt lệnh `EXPERT`** — đúng thứ phase 6b tồn tại để làm cho bất khả thi.
#: Với `OPEN_UI`, EA rơi vào nhánh mặc định và trả `rejected` (D-22).
CommandType: TypeAlias = Literal[
    "OPEN", "OPEN_UI", "CLOSE", "CLOSE_PARTIAL", "REQUEST_SNAPSHOT"
]
#: Trạng thái ack. ``unknown`` là trường hợp đặc biệt và nguy hiểm nhất: EA đã **giữ chỗ**
#: `command_id` trước khi đặt lệnh rồi terminal chết giữa chừng, nên nó không biết lệnh đã khớp
#: hay chưa. EA cố ý KHÔNG thực thi lại. Bridge phải coi đây là "chưa biết", không phải "thất
#: bại" — coi là thất bại thì chính sách retry sẽ mở lệnh thứ hai.
AckStatus: TypeAlias = Literal["ok", "failed", "already_closed", "rejected", "unknown"]

#: Event bắt buộc phải mang `volume_after` (D-14).
NEEDS_VOLUME_AFTER: frozenset[str] = frozenset({"position_closed", "position_changed"})

#: Event sinh từ deal, bắt buộc phải mang `deal_entry`.
DEAL_DERIVED: frozenset[str] = frozenset(
    {"position_opened", "position_closed", "position_changed"}
)

__all__ = [
    "PROTOCOL_VERSION",
    "AckMessage",
    "AgentMessage",
    "BridgeMessage",
    "CommandMessage",
    "ConfigMessage",
    "ErrorMessage",
    "EventData",
    "EventMessage",
    "HeartbeatMessage",
    "HelloAckMessage",
    "HelloMessage",
    "ResendMessage",
    "SnapshotMessage",
    "SnapshotPosition",
    "SymbolSpec",
    "SymbolSpecsMessage",
    "ValidationError",
    "parse_agent_message",
]


class _Base(BaseModel):
    """Nền chung: cấm trường lạ để lỗi chính tả ở EA lộ ra ngay thay vì bị nuốt."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Envelope(_Base):
    v: int = PROTOCOL_VERSION
    ts: str | None = None


# =============================================================================================
# Agent → Bridge
# =============================================================================================


class HelloMessage(_Envelope):
    """Bắt tay. Bridge tra agent theo hash của `token`, không tra theo `agent_id` agent tự khai."""

    kind: Literal["hello"] = "hello"
    token: str = Field(min_length=1, repr=False)
    role: AgentRole
    account_login: int
    broker_server: str | None = None
    terminal_build: int | None = None
    magic: int
    #: `seq` cao nhất agent đã sinh. Bridge so với `last_seq` của mình để biết có phải gửi bù.
    seq: int = Field(ge=0, default=0)

    def __repr__(self) -> str:
        # Không bao giờ để token lọt vào log qua repr của message.
        return (f"HelloMessage(role={self.role!r}, account_login={self.account_login!r}, "
                f"magic={self.magic!r}, seq={self.seq!r})")

    __str__ = __repr__


class SymbolSpec(_Base):
    """Thông số một symbol trên terminal của agent. Tên trường khớp bảng `symbol_spec`."""

    symbol: str = Field(min_length=1)
    digits: int | None = None
    point: float | None = None
    volume_min: float | None = None
    volume_max: float | None = None
    volume_step: float | None = None
    contract_size: float | None = None
    tick_value: float | None = None
    tick_size: float | None = None
    filling_mode: int | None = None
    trade_mode: int | None = None


class SymbolSpecsMessage(_Envelope):
    kind: Literal["symbol_specs"] = "symbol_specs"
    symbols: list[SymbolSpec]


class EventData(_Base):
    """Phần dữ liệu của một event giao dịch.

    `volume_delta` và `volume_after` tính bằng **lot của sàn agent đó**. `volume_after` là
    trạng thái thật do EA đọc lại từ vị thế, không phải kết quả phép trừ (D-14).
    """

    position_id: int | None = None
    deal_id: int | None = None
    deal_entry: DealEntry | None = None
    symbol: str | None = None
    #: Chiều của vị thế. Đặt tên `direction` thay vì `type` để không lẫn với `type` của event.
    direction: Direction | None = None
    volume_delta: float | None = Field(default=None, ge=0)
    volume_after: float | None = Field(default=None, ge=0)
    price: float | None = None
    magic: int | None = None
    ticket: int | None = None

    #: `DEAL_COMMENT`. Mang thẻ tương quan của lệnh mở qua giao diện (D-23).
    comment: str | None = None
    #: `ORDER_COMMENT` của order sinh ra deal. Gửi **cả hai** vì nhiều sàn thay `DEAL_COMMENT`
    #: bằng chữ của mình trong khi `ORDER_COMMENT` vẫn giữ nguyên chữ người dùng gõ.
    order_comment: str | None = None
    #: `DEAL_ORDER` — ticket của order sinh ra deal này.
    order_id: int | None = None
    #: `DEAL_REASON` do **máy chủ broker** gán: 0 CLIENT, 1 MOBILE, 2 WEB, 3 EXPERT, 4 SL,
    #: 5 TP, 6 SO. Đây là con số biến mục tiêu của phase 6b thành thứ **đo được** thay vì
    #: một niềm tin — pair mở qua giao diện mà khác `CLIENT` là alert CRITICAL.
    reason: int | None = None

    #: Chỗ cho thông tin phụ của broker (ví dụ retcode khi `order_rejected`).
    extra: dict[str, Any] | None = None


class EventMessage(_Envelope):
    kind: Literal["event"] = "event"
    #: `event_id`, sinh tại EA dạng ``EVT-<agent>-<seq>``. Là khoá dedup ở Bridge.
    id: str = Field(min_length=1)
    seq: int = Field(ge=0)
    type: EventType
    #: Khác NULL nghĩa là chính bot gây ra sự kiện này, và nó KHÔNG được lan truyền (D-08).
    caused_by_command_id: str | None = None
    data: EventData = Field(default_factory=EventData)

    @model_validator(mode="after")
    def _kiem_tra_rang_buoc_cua_tung_loai(self) -> EventMessage:
        if self.type in NEEDS_VOLUME_AFTER and self.data.volume_after is None:
            raise ValueError(
                f"Event {self.type} bắt buộc có data.volume_after (D-14): "
                "Bridge không tự suy diễn trạng thái bằng phép trừ"
            )
        if self.type in DEAL_DERIVED and self.data.deal_entry is None:
            raise ValueError(f"Event {self.type} sinh từ deal nên bắt buộc có data.deal_entry")
        if self.type in DEAL_DERIVED and self.data.position_id is None:
            raise ValueError(
                f"Event {self.type} bắt buộc có data.position_id — tra cứu luôn theo "
                "position_id, không bao giờ theo symbol"
            )
        return self


class SnapshotPosition(_Base):
    """Một vị thế thật trên terminal. Gồm cả vị thế không mang magic của bot (FR-12)."""

    position_id: int
    ticket: int | None = None
    symbol: str
    direction: Direction
    volume: float = Field(gt=0)
    price_open: float | None = None
    magic: int | None = None
    #: `POSITION_COMMENT`. Đối chiếu ở phase 8 dùng để nhận ra vị thế của bot khi `magic = 0`
    #: (D-07b) — vị thế mở qua giao diện không đặt được magic.
    comment: str | None = None
    #: `POSITION_REASON`, lấy từ deal mở vị thế.
    reason: int | None = None


class SnapshotMessage(_Envelope):
    kind: Literal["snapshot"] = "snapshot"
    #: `command_id` của lệnh REQUEST_SNAPSHOT đã kích hoạt, nếu có.
    command_id: str | None = None
    positions: list[SnapshotPosition] = Field(default_factory=list)


class AckMessage(_Envelope):
    """Kết quả thực thi một command.

    `retcode` là mã nguyên bản từ `MqlTradeResult`, **không dịch, không gộp nhóm** — Bridge
    phân loại ở phase 6.
    """

    kind: Literal["ack"] = "ack"
    command_id: str = Field(min_length=1)
    status: AckStatus
    retcode: int | None = None
    retmsg: str | None = None
    executed_volume: float | None = Field(default=None, ge=0)
    result_position_id: int | None = None
    attempt: int = Field(default=1, ge=1)


class HeartbeatMessage(_Envelope):
    """Nhịp sống của agent.

    `broker_connected` là **bắt buộc**: trạng thái "agent còn sống nhưng terminal mất kết nối
    sàn" trông giống hệt trạng thái khoẻ mạnh nếu chỉ nhìn heartbeat.
    """

    kind: Literal["heartbeat"] = "heartbeat"
    seq: int = Field(ge=0, default=0)
    broker_connected: bool
    equity: float | None = None
    margin_level: float | None = None
    positions_count: int | None = Field(default=None, ge=0)
    ts_agent: str | None = None


AgentMessage: TypeAlias = Annotated[
    HelloMessage | SymbolSpecsMessage | EventMessage | SnapshotMessage | AckMessage
    | HeartbeatMessage,
    Field(discriminator="kind"),
]


# =============================================================================================
# Bridge → Agent
# =============================================================================================


class HelloAckMessage(_Envelope):
    kind: Literal["hello_ack"] = "hello_ack"
    agent_id: str
    #: `seq` cao nhất Bridge đã ghi thành công. Agent gửi bù từ `last_seq + 1`.
    last_seq: int = Field(ge=0)
    config: dict[str, Any] = Field(default_factory=dict)


class CommandMessage(_Envelope):
    kind: Literal["command"] = "command"
    command_id: str
    type: CommandType
    pair_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    #: Quá hạn thì EA phải từ chối. Lệnh cũ không được thực thi muộn.
    deadline_ts: str | None = None


class ConfigMessage(_Envelope):
    """Tham số sửa nóng đẩy xuống agent."""

    kind: Literal["config"] = "config"
    max_deviation_points: int | None = None
    max_spread_points: int | None = None
    heartbeat_interval_ms: int | None = None


class ResendMessage(_Envelope):
    kind: Literal["resend"] = "resend"
    from_seq: int = Field(ge=0)


class ErrorMessage(_Envelope):
    kind: Literal["error"] = "error"
    code: str
    message: str


BridgeMessage: TypeAlias = Annotated[
    HelloAckMessage | CommandMessage | ConfigMessage | ResendMessage | ErrorMessage,
    Field(discriminator="kind"),
]


# =============================================================================================
# Giải mã
# =============================================================================================

_AGENT_MESSAGES: dict[str, type[_Envelope]] = {
    "hello": HelloMessage,
    "symbol_specs": SymbolSpecsMessage,
    "event": EventMessage,
    "snapshot": SnapshotMessage,
    "ack": AckMessage,
    "heartbeat": HeartbeatMessage,
}


def parse_agent_message(payload: dict[str, Any]) -> Any:
    """Dựng message của agent từ dict đã giải mã JSON.

    Ném `pydantic.ValidationError` khi sai schema. Nơi gọi trả về một message ``error`` và ghi
    WARNING, **không đóng kết nối** — trừ trường hợp `hello` sai, xem `server.py`.
    """
    kind = payload.get("kind")
    model = _AGENT_MESSAGES.get(kind) if isinstance(kind, str) else None
    if model is None:
        raise ValueError(f"kind không hợp lệ: {kind!r}")
    return model.model_validate(payload)
