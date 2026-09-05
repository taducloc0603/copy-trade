"""Mock clicker: giả lập tiến trình bấm nút giao diện MT5, không cần MT5.

Nó cố tình **không** biết `position_id` — vì hộp thoại New Order không trả về gì. Đó chính là
điều kiện khó của phase 6b, và mock này phải giữ nguyên điều kiện đó chứ không được làm dễ đi.

Vị thế thật do `MockAgent` đóng vai EA Client sinh ra, bằng `emit_ui_open()`. Việc tách đôi này
là cố ý: nó cho test điều khiển **thứ tự đến** của ack và event, thứ mà thiết kế không được
phép phụ thuộc vào.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from bridge.clock import utc_now_iso
from tests.mock_agent import MockAgent

#: Ngưỡng comment của MT5. Thẻ tương quan phải sống sót qua đây.
MT5_COMMENT_LIMIT = 31


@dataclass
class MockClicker(MockAgent):
    """Agent role ``CLICKER``. Chỉ nhận `OPEN_UI`, và ack của nó không mang `position_id`."""

    role: str = "CLICKER"

    #: Trạng thái ack cho `OPEN_UI` kế tiếp: ok / rejected / failed / unknown.
    next_status: str = "ok"
    #: Chuỗi trạng thái ép theo thứ tự. Hết chuỗi thì quay về `next_status`.
    status_sequence: list[str] = field(default_factory=list)
    #: Nuốt ack: mô phỏng clicker chết sau khi bấm nhưng trước khi báo về.
    swallow_ack: bool = False
    #: Cắt comment còn bao nhiêu ký tự khi "gõ" vào hộp thoại. None nghĩa là giữ nguyên.
    truncate_comment: int | None = None

    #: Nhật ký giữ chỗ, tương ứng `clicker_commands.ndjson` của bản thật.
    journal: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Payload của các `OPEN_UI` đã thực sự "bấm", theo thứ tự.
    clicked: list[dict[str, Any]] = field(default_factory=list)

    def _next_status(self) -> str:
        return self.status_sequence.pop(0) if self.status_sequence else self.next_status

    def typed_comment(self, tag: str | None) -> str | None:
        """Comment thực sự đi vào lệnh, sau khi bị hộp thoại và sàn cắt."""
        if tag is None:
            return None
        limit = self.truncate_comment if self.truncate_comment is not None else MT5_COMMENT_LIMIT
        return tag[:limit]

    async def _execute(self, command: dict[str, Any]) -> dict[str, Any]:
        command_id = command["command_id"]
        payload = command.get("payload") or {}

        def ack(status: str, **fields: Any) -> dict[str, Any]:
            base = {"v": 1, "kind": "ack", "ts": utc_now_iso(), "command_id": command_id,
                    "status": status, "attempt": 1}
            base.update({k: v for k, v in fields.items() if v is not None})
            return base

        # Clicker chỉ biết đúng một loại command. Mọi thứ khác bị từ chối — kể cả `OPEN`, để
        # một lỗi định tuyến không bao giờ biến thành một lệnh `EXPERT` lặng lẽ.
        if command["type"] != "OPEN_UI":
            return ack("rejected", retmsg=f"Clicker khong nhan command loai {command['type']}")

        # Bất biến: đã biết + có ack → gửi lại nguyên văn; đã biết + ack rỗng → "unknown".
        if command_id in self.journal:
            self.duplicate_commands.append(command_id)
            done = self.journal[command_id]
            if done.get("ack") is not None:
                return dict(done["ack"])
            return ack("unknown", retmsg="Da giu cho nhung khong biet da bam hay chua")

        # Giữ chỗ TRƯỚC phím đầu tiên. Thiếu lệnh an toàn hơn thừa lệnh.
        self.journal[command_id] = {"reserved_at": utc_now_iso(), "ack": None}
        self.executed_commands.append(command_id)

        if self.enforce_guards:
            # `magic` không đặt được qua giao diện, nên payload `OPEN_UI` không được mang nó.
            if "magic" in payload:
                return self._finish(command_id, ack(
                    "rejected", retmsg="Payload OPEN_UI khong duoc co magic"))
            for name in ("symbol", "direction", "volume"):
                if payload.get(name) in (None, ""):
                    return self._finish(command_id, ack(
                        "rejected", retmsg=f"Payload OPEN_UI thieu {name}"))
            if self.known_symbols is not None and payload["symbol"] not in self.known_symbols:
                return self._finish(command_id, ack(
                    "rejected", retmsg=f"Symbol khong co tren terminal: {payload['symbol']}"))

        status = self._next_status()
        if status == "rejected":
            # Đọc lại thấy lệch → huỷ trước khi bấm. Chưa gửi gì đi.
            return self._finish(command_id, ack("rejected", retmsg="Doc lai lech, da huy"))

        self.clicked.append(dict(payload))
        if status == "failed":
            return self._finish(command_id, ack("failed", retcode=10019,
                                                retmsg="San tu choi"))
        if status == "unknown":
            return self._finish(command_id, ack("unknown", retmsg="Khong doc duoc ket qua"))

        # `ok` = "tôi đã bấm", KHÔNG kèm `result_position_id`.
        return self._finish(command_id, ack("ok"))

    def _finish(self, command_id: str, ack: dict[str, Any]) -> dict[str, Any]:
        self.journal[command_id]["ack"] = dict(ack)
        if self.swallow_ack:
            return {}
        return ack

    async def _auto_ack(self, message: dict[str, Any]) -> None:
        if self.execution_delay_sec:
            await asyncio.sleep(self.execution_delay_sec)
        reply = await self._execute(message)
        if reply:
            await self.send_raw(reply)

    def restart_journal(self) -> None:
        """Mô phỏng khởi động lại: nhật ký còn nguyên trên đĩa, ack trong bộ nhớ thì không."""
        for entry in self.journal.values():
            entry["ack"] = None
