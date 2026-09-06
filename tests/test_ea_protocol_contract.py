"""Đối chiếu EA (MQL5) với schema giao thức của Bridge.

Không thay thế được việc chạy EA thật trên terminal MT5 — nhưng bắt được đúng loại lỗi hay xảy
ra nhất khi sửa giao thức: **EA và Bridge nói lệch nhau**. Vì `_Base` đặt `extra="forbid"`, chỉ
cần EA gửi thừa hoặc thiếu một trường là Bridge từ chối message, và trên terminal thật thì lỗi
đó chỉ hiện ra dưới dạng "không hiểu sao Bridge không nhận sự kiện".

Kiểm tra hai chiều:

1. Mọi khoá JSON mà mã nguồn EA ghi ra đều phải có nghĩa với Bridge (hoặc nằm trong danh sách
   khoá của file cục bộ mà EA tự dùng).
2. Mỗi loại message EA gửi, khi dựng đúng bằng bộ trường mô tả ở đây, phải được schema chấp nhận.

Khi phase 5 mở rộng EA, test này sẽ đỏ cho tới khi cập nhật cả hai phía — đúng như plan yêu cầu:
sửa giao thức thì sửa cả EA, mock agent và test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bridge.protocol.messages import (
    AckMessage,
    EventData,
    EventMessage,
    HeartbeatMessage,
    HelloMessage,
    SnapshotMessage,
    SnapshotPosition,
    SymbolSpec,
    SymbolSpecsMessage,
    parse_agent_message,
)

EA_DIR = Path(__file__).resolve().parent.parent / "ea"

#: Khoá JSON EA dùng cho file trạng thái cục bộ của chính nó, Bridge không bao giờ thấy.
LOCAL_FILE_KEYS = {
    "seq",          # <login>_state.json
    "command_id",   # <login>_commands.ndjson
    "at",
    "ack",
}

#: Trường bọc ngoài mà EA tự đặt tên khi build message.
ENVELOPE_KEYS = {"v", "kind", "ts"}

#: Khoá nằm BÊN TRONG `EventData.extra` — đó là `dict[str, Any]` nên nhận khoá tuỳ ý.
EXTRA_DICT_KEYS = {"reason"}

JSON_KEY_RE = re.compile(r'\.(?:Str|Int|Dbl|Bool|Null|Raw)\(\s*"([^"]+)"')
COMMENT_RE = re.compile(r"//.*$")


def _code_only(path: Path) -> str:
    """Mã nguồn đã bỏ chú thích.

    Nhiều test dưới đây khẳng định EA *không* gọi một hàm nào đó. Nếu soi cả chú thích thì một
    câu giải thích vì sao không được gọi hàm đó sẽ làm test đỏ — dương tính giả đúng nghĩa.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    return chr(10).join(COMMENT_RE.sub("", line) for line in lines)


def _schema_fields() -> set[str]:
    models = (HelloMessage, SymbolSpecsMessage, EventMessage, SnapshotMessage, AckMessage,
              HeartbeatMessage, EventData, SnapshotPosition, SymbolSpec)
    fields: set[str] = set(ENVELOPE_KEYS) | set(LOCAL_FILE_KEYS) | set(EXTRA_DICT_KEYS)
    for model in models:
        fields |= set(model.model_fields)
    return fields


def _ea_sources() -> list[Path]:
    files = sorted(EA_DIR.glob("*.mqh")) + sorted(EA_DIR.glob("*.mq5"))
    assert files, "Không tìm thấy file MQL5 nào trong ea/"
    return files


# ---------------------------------------------------------------------------------------------
# Chiều 1: mọi khoá EA ghi ra đều phải có nghĩa
# ---------------------------------------------------------------------------------------------


def test_moi_khoa_json_ea_ghi_ra_deu_co_trong_schema() -> None:
    known = _schema_fields()
    unknown: dict[str, str] = {}
    for path in _ea_sources():
        for match in JSON_KEY_RE.finditer(path.read_text(encoding="utf-8")):
            key = match.group(1)
            if key not in known:
                unknown[key] = path.name
    assert not unknown, (
        f"EA ghi ra khoá JSON mà Bridge không biết: {unknown}. "
        "Vì schema đặt extra='forbid', Bridge sẽ từ chối message."
    )


def test_ea_dung_ten_direction_khong_phai_type_cho_chieu_lenh() -> None:
    """Chiều lệnh trong `event.data` tên là `direction` — `type` đã là loại event rồi."""
    source = (EA_DIR / "CopyBridgeCommon.mqh").read_text(encoding="utf-8")
    assert 'data.Str("direction"' in source


def test_ea_khong_bao_gio_ghi_token_ra_log() -> None:
    """Token thô chỉ được đưa vào message `hello`, không bao giờ vào `Print`/`CbLog`."""
    for path in _ea_sources():
        for line_no, line in enumerate(_code_only(path).splitlines(), 1):
            if "CbLog(" in line or "Print(" in line:
                # Nhắc tên tham số trong một câu thông báo là vô hại; nối GIÁ TRỊ vào thì không.
                assert "m_token" not in line, f"{path.name}:{line_no} có vẻ đang log token"
                assert "+ AgentToken" not in line, f"{path.name}:{line_no} có vẻ đang log token"


# ---------------------------------------------------------------------------------------------
# Chiều 2: mỗi loại message EA gửi phải hợp lệ với schema
# ---------------------------------------------------------------------------------------------


def test_hello_cua_ea_hop_le() -> None:
    message = parse_agent_message({
        "v": 1, "kind": "hello", "ts": "2026-09-04T09:00:00.000Z",
        "token": "token-that", "role": "MASTER", "account_login": 111111,
        "broker_server": "DemoServer", "terminal_build": 4200, "magic": 770001, "seq": 12,
    })
    assert isinstance(message, HelloMessage)


def test_heartbeat_cua_ea_hop_le() -> None:
    message = parse_agent_message({
        "v": 1, "kind": "heartbeat", "ts": "2026-09-04T09:00:00.000Z", "seq": 12,
        "broker_connected": True, "equity": 10000.0, "margin_level": 500.0,
        "positions_count": 3, "ts_agent": "2026-09-04T09:00:00.000Z",
    })
    assert isinstance(message, HeartbeatMessage)
    assert message.broker_connected is True


def test_symbol_specs_cua_ea_hop_le() -> None:
    message = parse_agent_message({
        "v": 1, "kind": "symbol_specs", "ts": "2026-09-04T09:00:00.000Z",
        "symbols": [{
            "symbol": "XAUUSD", "digits": 2, "point": 0.01, "volume_min": 0.01,
            "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0,
            "tick_value": 1.0, "tick_size": 0.01, "filling_mode": 1, "trade_mode": 4,
        }],
    })
    assert isinstance(message, SymbolSpecsMessage)
    assert message.symbols[0].contract_size == 100.0


def test_snapshot_cua_ea_hop_le() -> None:
    message = parse_agent_message({
        "v": 1, "kind": "snapshot", "ts": "2026-09-04T09:00:00.000Z",
        "command_id": "CMD-abc",
        "positions": [{
            "position_id": 4242, "ticket": 4242, "symbol": "XAUUSD", "direction": "BUY",
            "volume": 1.0, "price_open": 2650.5, "magic": 770001,
        }],
    })
    assert isinstance(message, SnapshotMessage)


def test_ack_cua_ea_hop_le() -> None:
    message = parse_agent_message({
        "v": 1, "kind": "ack", "ts": "2026-09-04T09:00:00.000Z", "command_id": "CMD-abc",
        "status": "ok", "retcode": 10009, "attempt": 1,
    })
    assert isinstance(message, AckMessage)


@pytest.mark.parametrize(
    ("event_type", "deal_entry", "volume_after"),
    [
        ("position_opened", "IN", 1.0),
        ("position_changed", "OUT", 0.7),
        ("position_closed", "OUT", 0.0),
        ("position_closed", "OUT_BY", 0.0),
    ],
)
def test_bon_nhanh_deal_entry_cua_ea_deu_hop_le(event_type: str, deal_entry: str,
                                                volume_after: float) -> None:
    """Bốn nhánh trong bảng phân nhánh `deal.entry` của phase 4."""
    message = parse_agent_message({
        "v": 1, "kind": "event", "ts": "2026-09-04T09:00:00.000Z",
        "id": "EVT-111111-7", "seq": 7, "type": event_type,
        "data": {
            "position_id": 4242, "deal_id": 99, "deal_entry": deal_entry,
            "symbol": "XAUUSD", "direction": "BUY", "volume_delta": 0.3,
            "volume_after": volume_after, "price": 2650.5, "magic": 770001,
        },
    })
    assert isinstance(message, EventMessage)
    assert message.data.volume_after == volume_after


def test_nhanh_inout_cua_ea_hop_le() -> None:
    """`DEAL_ENTRY_INOUT` chỉ có ở tài khoản Netting — EA gửi `order_rejected` kèm ghi chú."""
    message = parse_agent_message({
        "v": 1, "kind": "event", "ts": "2026-09-04T09:00:00.000Z",
        "id": "EVT-111111-8", "seq": 8, "type": "order_rejected",
        "data": {
            "position_id": 4242, "deal_id": 99, "symbol": "XAUUSD", "volume_delta": 0.3,
            "price": 2650.5, "magic": 770001,
            "extra": {"reason": "DEAL_ENTRY_INOUT_ON_NETTING_ACCOUNT"},
        },
    })
    assert isinstance(message, EventMessage)
    assert message.data.extra["reason"] == "DEAL_ENTRY_INOUT_ON_NETTING_ACCOUNT"


def test_event_co_caused_by_command_id_hop_le() -> None:
    """Nền tảng chống vòng lặp (D-08) — dùng thật khi Master nhận lệnh đóng ở phase 7."""
    message = parse_agent_message({
        "v": 1, "kind": "event", "ts": "2026-09-04T09:00:00.000Z",
        "id": "EVT-111111-9", "seq": 9, "type": "position_closed",
        "caused_by_command_id": "CMD-abc",
        "data": {"position_id": 4242, "deal_entry": "OUT", "volume_after": 0.0},
    })
    assert message.caused_by_command_id == "CMD-abc"


# ---------------------------------------------------------------------------------------------
# Các quy tắc của phase 4 phải nhìn thấy được trong mã nguồn
# ---------------------------------------------------------------------------------------------


def test_chi_xu_ly_deal_add() -> None:
    """Một hành động, một event. Xử lý cả ORDER_ADD/HISTORY_ADD sẽ copy trùng 3-4 lần."""
    source = _code_only(EA_DIR / "CopyBridgeCommon.mqh")
    assert "if(trans.type != TRADE_TRANSACTION_DEAL_ADD)" in source
    for ignored in ("TRADE_TRANSACTION_ORDER_ADD", "TRADE_TRANSACTION_ORDER_UPDATE",
                    "TRADE_TRANSACTION_HISTORY_ADD"):
        assert ignored not in source, f"EA không được xử lý {ignored}"


def test_ghi_file_truoc_gui_socket_sau() -> None:
    """Crash giữa hai bước: ghi trước thì tệ nhất là gửi trùng, gửi trước thì mất hẳn event."""
    source = (EA_DIR / "CopyBridgeCommon.mqh").read_text(encoding="utf-8")
    body = source[source.index("void              SendEvent("):]
    body = body[:body.index("//| Goi moi 100ms")]
    assert body.index("CbFileAppendLine") < body.index("SendLine(line)")


def test_dung_cp_utf8_o_dung_hai_ham_boc() -> None:
    """Bỏ qua CP_UTF8 thì mọi tên symbol ngoài ASCII sẽ hỏng."""
    source = _code_only(EA_DIR / "CopyBridgeCommon.mqh")
    assert source.count("StringToCharArray(") == 1
    assert source.count("CharArrayToString(") == 1
    assert source.count("CP_UTF8") == 2


def test_dung_timer_khong_dua_vao_ontick() -> None:
    """Thị trường đóng cửa thì `OnTick` không chạy, nhưng vẫn phải đọc socket và gửi heartbeat."""
    master = _code_only(EA_DIR / "CopyBridgeMaster.mq5")
    assert "EventSetMillisecondTimer(100)" in master
    assert "void OnTick(" not in master


def test_heartbeat_luon_mang_broker_connected() -> None:
    source = (EA_DIR / "CopyBridgeCommon.mqh").read_text(encoding="utf-8")
    assert 'writer.Bool("broker_connected"' in source
    assert "TERMINAL_CONNECTED" in source


def test_chi_ea_client_duoc_MO_lenh() -> None:
    """Ranh giới an toàn, bản phase 11: **Master được ĐÓNG, không bao giờ được MỞ.**

    Bản trước là "chỉ EA Client đặt lệnh", khoá bằng cách cấm `OrderSend` trong file Master và
    file dùng chung. Ranh giới đó đơn giản nhưng **mâu thuẫn với chính hợp đồng**: D-09 (cascade
    đóng vị thế Master) và TEST-21 (đóng khẩn cấp, Client trước Master sau) đều đòi hỏi Master
    đóng được. Nghiệm thu trên demo 2026-09-06 bấm nút thật và nhận về `Command type not
    supported by this agent role` — hai quyết định không thể cùng đúng.

    Hướng đã chọn: cho Master **đóng**, vẫn cấm **mở**. Ranh giới mới tinh hơn nên cũng phải
    khoá tinh hơn: mọi `OrderSend` trong code dùng chung phải đặt `request.position`, tức nó chỉ
    có thể đóng một vị thế **đã tồn tại**. Đường mở — `OrderSend` không có `request.position` —
    chỉ được phép nằm trong EA Client.
    """
    master = _code_only(EA_DIR / "CopyBridgeMaster.mq5")
    assert "OrderSend(" not in master, "EA Master không được tự đặt lệnh; nó kế thừa đường đóng"
    assert '"OPEN"' not in master, "EA Master không được nhận command loại OPEN"

    # Code dùng chung: mọi lời gọi OrderSend đều phải nằm sau một `request.position = ...`
    # trong cùng một lần dựng request (`ZeroMemory(request)` đánh dấu đầu mỗi lần dựng).
    common = _code_only(EA_DIR / "CopyBridgeCommon.mqh")
    for khuc in common.split("ZeroMemory(request);")[1:]:
        truoc_ordersend = khuc.split("OrderSend(")[0]
        if "OrderSend(" in khuc:
            assert "request.position" in truoc_ordersend, (
                "CopyBridgeCommon.mqh có một OrderSend không đặt request.position — "
                "tức là một đường MỞ lọt vào code dùng chung"
            )

    # Duong MO chi duoc o EA Client.
    client = _code_only(EA_DIR / "CopyBridgeClient.mq5")
    assert "OrderSend(" in client, "EA Client phải mở được lệnh"
    assert "ORDER_TYPE_BUY" in client and "ORDER_TYPE_SELL" in client


def test_ea_chi_ho_tro_tai_khoan_hedging() -> None:
    master = (EA_DIR / "CopyBridgeMaster.mq5").read_text(encoding="utf-8")
    assert "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING" in master


def test_giu_bo_nho_command_da_thuc_thi() -> None:
    """Nhận lại command trùng phải trả ack cũ, không thực thi lần hai."""
    source = (EA_DIR / "CopyBridgeCommon.mqh").read_text(encoding="utf-8")
    assert "RememberCommand" in source
    assert "FindCommand" in source
    assert "COPYBRIDGE_CMD_MEMORY_SEC   86400" in source


def test_gioi_han_dong_khop_voi_bridge() -> None:
    from bridge.protocol.framing import MAX_LINE_BYTES

    source = (EA_DIR / "CopyBridgeCommon.mqh").read_text(encoding="utf-8")
    assert f"COPYBRIDGE_MAX_LINE         {MAX_LINE_BYTES}" in source


def test_ea_khong_chua_ky_tu_ngoai_ascii() -> None:
    """MetaEditor xử lý encoding file nguồn không thống nhất giữa các bản build."""
    for path in _ea_sources():
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            assert line.isascii(), f"{path.name}:{line_no} có ký tự ngoài ASCII"
