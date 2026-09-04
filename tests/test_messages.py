"""Test schema message.

Trọng tâm: những ràng buộc bảo vệ D-14 — `volume_after` bắt buộc, `deal_entry` bắt buộc.
Đây là chỗ chặn một EA viết ẩu trước khi dữ liệu sai chạm vào database.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bridge.protocol.messages import (
    PROTOCOL_VERSION,
    EventMessage,
    HelloMessage,
    parse_agent_message,
)


def _event(event_type: str, **data: object) -> dict[str, object]:
    return {"kind": "event", "id": "EVT-1", "seq": 1, "type": event_type, "data": data}


# ---------------------------------------------------------------------------------------------
# Ràng buộc bảo vệ D-14
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("event_type", ["position_closed", "position_changed"])
def test_thieu_volume_after_bi_tu_choi(event_type: str) -> None:
    """Bridge không bao giờ tự suy diễn trạng thái sau sự kiện bằng phép trừ."""
    with pytest.raises(ValidationError) as exc:
        parse_agent_message(_event(event_type, position_id=1, deal_entry="OUT"))
    assert "volume_after" in str(exc.value)


@pytest.mark.parametrize("event_type", ["position_closed", "position_changed"])
def test_volume_after_bang_0_la_hop_le(event_type: str) -> None:
    """`volume_after = 0` nghĩa là đóng hoàn toàn — khác hẳn với thiếu trường."""
    message = parse_agent_message(_event(event_type, position_id=1, deal_entry="OUT",
                                         volume_after=0.0))
    assert message.data.volume_after == 0.0


@pytest.mark.parametrize(
    "event_type", ["position_opened", "position_closed", "position_changed"]
)
def test_event_sinh_tu_deal_bat_buoc_co_deal_entry(event_type: str) -> None:
    with pytest.raises(ValidationError) as exc:
        parse_agent_message(_event(event_type, position_id=1, volume_after=0.0))
    assert "deal_entry" in str(exc.value)


@pytest.mark.parametrize(
    "event_type", ["position_opened", "position_closed", "position_changed"]
)
def test_event_sinh_tu_deal_bat_buoc_co_position_id(event_type: str) -> None:
    """Tra cứu luôn theo position_id, không bao giờ theo symbol."""
    with pytest.raises(ValidationError) as exc:
        parse_agent_message(_event(event_type, deal_entry="IN", volume_after=1.0,
                                   symbol="XAUUSD"))
    assert "position_id" in str(exc.value)


def test_order_rejected_khong_can_deal_entry() -> None:
    """`order_rejected` không sinh từ deal nào nên được miễn."""
    message = parse_agent_message({
        "kind": "event", "id": "EVT-9", "seq": 9, "type": "order_rejected",
        "data": {"symbol": "XAUUSD", "extra": {"retcode": 10019}},
    })
    assert message.data.deal_entry is None
    assert message.data.extra == {"retcode": 10019}


@pytest.mark.parametrize("deal_entry", ["IN", "OUT", "INOUT", "OUT_BY"])
def test_bon_gia_tri_deal_entry_deu_hop_le(deal_entry: str) -> None:
    message = parse_agent_message(_event("position_closed", position_id=1,
                                         deal_entry=deal_entry, volume_after=0.0))
    assert message.data.deal_entry == deal_entry


def test_deal_entry_la_khong_hop_le_bi_chan() -> None:
    with pytest.raises(ValidationError):
        parse_agent_message(_event("position_closed", position_id=1, deal_entry="SIDEWAYS",
                                   volume_after=0.0))


def test_loai_event_la_bi_chan() -> None:
    with pytest.raises(ValidationError):
        parse_agent_message(_event("position_exploded", position_id=1, deal_entry="IN"))


def test_volume_am_bi_chan() -> None:
    with pytest.raises(ValidationError):
        parse_agent_message(_event("position_closed", position_id=1, deal_entry="OUT",
                                   volume_after=-1.0))


# ---------------------------------------------------------------------------------------------
# Bảo mật và envelope
# ---------------------------------------------------------------------------------------------


def test_token_khong_lot_ra_repr_cua_hello() -> None:
    """`repr()` hay bị đưa thẳng vào log — token không được có mặt ở đó."""
    hello = HelloMessage(token="sieu-bi-mat-123", role="MASTER", account_login=111, magic=7)
    assert "sieu-bi-mat-123" not in repr(hello)
    assert "sieu-bi-mat-123" not in str(hello)
    assert "sieu-bi-mat-123" not in f"{hello}"
    assert hello.token == "sieu-bi-mat-123"


def test_truong_la_bi_tu_choi() -> None:
    """Lỗi chính tả ở EA phải lộ ra ngay thay vì bị nuốt im lặng."""
    with pytest.raises(ValidationError):
        parse_agent_message({"kind": "heartbeat", "broker_connected": True,
                             "broker_conected": False})


def test_kind_khong_biet_bi_tu_choi() -> None:
    with pytest.raises(ValueError, match="kind"):
        parse_agent_message({"kind": "tu_nghi_ra", "abc": 1})


def test_kind_thieu_bi_tu_choi() -> None:
    with pytest.raises(ValueError, match="kind"):
        parse_agent_message({"abc": 1})


def test_phien_ban_mac_dinh_la_1() -> None:
    message = parse_agent_message({"kind": "heartbeat", "broker_connected": True})
    assert message.v == PROTOCOL_VERSION == 1


def test_heartbeat_bat_buoc_co_broker_connected() -> None:
    """Thiếu trường này thì "agent sống mà terminal mất sàn" trông y hệt trạng thái khoẻ."""
    with pytest.raises(ValidationError) as exc:
        parse_agent_message({"kind": "heartbeat", "seq": 1, "equity": 100.0})
    assert "broker_connected" in str(exc.value)


def test_hello_bat_buoc_co_token_khong_rong() -> None:
    with pytest.raises(ValidationError):
        parse_agent_message({"kind": "hello", "token": "", "role": "MASTER",
                             "account_login": 1, "magic": 1})


def test_role_la_bi_chan() -> None:
    with pytest.raises(ValidationError):
        parse_agent_message({"kind": "hello", "token": "t", "role": "BOSS",
                             "account_login": 1, "magic": 1})


def test_snapshot_volume_phai_duong() -> None:
    with pytest.raises(ValidationError):
        parse_agent_message({"kind": "snapshot", "positions": [
            {"position_id": 1, "symbol": "XAUUSD", "direction": "BUY", "volume": 0}
        ]})


def test_snapshot_giu_ca_vi_the_khong_mang_magic() -> None:
    """Bridge cần biết lệnh mở tay để phân biệt (FR-12)."""
    message = parse_agent_message({"kind": "snapshot", "positions": [
        {"position_id": 1, "symbol": "XAUUSD", "direction": "BUY", "volume": 0.1},
        {"position_id": 2, "symbol": "EURUSD", "direction": "SELL", "volume": 0.2,
         "magic": 770001},
    ]})
    assert [p.magic for p in message.positions] == [None, 770001]


def test_ack_giu_retcode_nguyen_ban() -> None:
    message = parse_agent_message({"kind": "ack", "command_id": "CMD-1", "status": "failed",
                                   "retcode": 10019, "retmsg": "No money"})
    assert message.retcode == 10019, "Không dịch, không gộp nhóm — Bridge tự phân loại"


def test_ack_already_closed_la_trang_thai_hop_le() -> None:
    """Hai bên cùng đóng gần như đồng thời là chuyện bình thường (FR-18)."""
    message = parse_agent_message({"kind": "ack", "command_id": "CMD-1",
                                   "status": "already_closed"})
    assert message.status == "already_closed"


def test_event_giu_caused_by_command_id() -> None:
    """Trường này là toàn bộ cơ chế chống vòng lặp (D-08)."""
    payload = _event("position_closed", position_id=1, deal_entry="OUT", volume_after=0.0)
    payload["caused_by_command_id"] = "CMD-abc"
    message = parse_agent_message(payload)
    assert message.caused_by_command_id == "CMD-abc"

    payload["caused_by_command_id"] = None
    assert parse_agent_message(payload).caused_by_command_id is None


def test_event_du_truong_thi_dung_het() -> None:
    message = EventMessage.model_validate(_event(
        "position_changed", position_id=4242, deal_id=99, deal_entry="OUT", symbol="XAUUSD",
        direction="BUY", volume_delta=0.3, volume_after=0.7, price=2650.5, magic=770001,
        ticket=555,
    ))
    assert message.data.volume_delta == 0.3
    assert message.data.volume_after == 0.7
    assert message.data.direction == "BUY"
