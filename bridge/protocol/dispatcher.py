"""Outbox command: ghi vào DB trước, gửi socket sau.

Thứ tự này là bất di bất dịch:

1. `INSERT INTO command ... status = 'PENDING'`
2. gửi qua socket
3. `UPDATE command SET status = 'SENT'`

**Không bao giờ gửi một command chưa có trong DB.** Nếu Bridge chết ngay sau khi gửi mà trước
khi kịp ghi, ta sẽ có một lệnh đã đặt ngoài sàn mà sổ sách không biết — đúng loại sai lệch mà
đối chiếu ở phase 8 không thể tự sửa vì nó không biết là phải tìm cái gì.

Agent đang offline thì command **ở lại `PENDING`**, không bị đánh `TIMEOUT`. Phân biệt "chưa
gửi được" với "đã gửi mà không có phản hồi" là điều kiện cần để phase 8 xử lý đúng.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import timedelta
from typing import Any

from bridge.clock import to_iso, utc_now, utc_now_iso
from bridge.db.repo import Database
from bridge.logging_setup import get_logger
from bridge.protocol.messages import CommandMessage
from bridge.protocol.server import BridgeServer

log = get_logger(__name__)

#: Hạn mặc định cho một command khi nơi gọi không chỉ định.
DEFAULT_DEADLINE_MS = 5000

COMMAND_ID_PREFIX = "CMD"


def new_command_id() -> str:
    """Sinh `command_id` mới.

    Khác Pair ID, `command_id` không cần đọc bằng mắt nên dùng UUID cho gọn và không cần bộ đếm
    trong DB.
    """
    return f"{COMMAND_ID_PREFIX}-{uuid.uuid4().hex}"


class CommandDispatcher:
    """Tạo, gửi và theo dõi hạn của command."""

    def __init__(self, db: Database, server: BridgeServer) -> None:
        self.db = db
        self.server = server
        #: Đặt bởi `EventProcessor` (phase 6): gọi cho từng command bị đánh TIMEOUT.
        self.on_timeout: Any = None
        # Agent vừa bắt tay xong thì đẩy ngay các command còn tồn.
        server.on_agent_online = self.on_agent_online

    # -- tạo và gửi ------------------------------------------------------------------------

    async def dispatch(self, target_agent_id: str, command_type: str, *,
                       pair_id: str | None = None, payload: dict[str, Any] | None = None,
                       deadline_ms: int = DEFAULT_DEADLINE_MS,
                       command_id: str | None = None) -> str:
        """Ghi một command vào outbox rồi gửi ngay nếu agent đang kết nối.

        Trả về `command_id`. Agent offline thì command nằm lại `PENDING` và sẽ được gửi khi
        agent nối lại — hàm này **không** báo lỗi trong trường hợp đó.
        """
        command_id = command_id or new_command_id()
        payload = payload or {}
        deadline_at = to_iso(utc_now() + timedelta(milliseconds=deadline_ms))

        self.db.create_command(
            command_id, target_agent_id, command_type, pair_id=pair_id,
            payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            deadline_at=deadline_at,
        )
        log.info("Tao command %s type=%s cho agent %s", command_id, command_type,
                 target_agent_id, extra={"agent_id": target_agent_id, "pair_id": pair_id,
                                         "command_id": command_id})
        await self._send(command_id, target_agent_id, command_type, pair_id, payload,
                         deadline_at)
        return command_id

    async def _send(self, command_id: str, target_agent_id: str, command_type: str,
                    pair_id: str | None, payload: dict[str, Any],
                    deadline_at: str | None) -> bool:
        message = CommandMessage(
            command_id=command_id, type=command_type, pair_id=pair_id, payload=payload,
            deadline_ts=deadline_at, ts=utc_now_iso(),
        )
        sent = await self.server.send_to(target_agent_id, message)
        if sent:
            self.db.mark_command_sent(command_id)
        else:
            log.warning("Agent %s dang offline, command %s nam lai PENDING",
                        target_agent_id, command_id,
                        extra={"agent_id": target_agent_id, "command_id": command_id,
                               "pair_id": pair_id})
        return sent

    async def send_existing(self, command_id: str) -> bool:
        """Gửi một command **đã có sẵn trong DB**.

        Phase 6 tạo `pair` và `command` trong cùng một giao dịch rồi mới gửi, nên nó cần tách
        bước gửi ra khỏi bước ghi — khác `dispatch()` vốn làm cả hai.
        """
        row = self.db.get_command(command_id)
        if row is None:
            log.error("Khong tim thay command %s de gui", command_id,
                      extra={"command_id": command_id})
            return False
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        return await self._send(command_id, row["target_agent_id"], row["type"], row["pair_id"],
                                payload, row["deadline_at"])

    async def on_agent_online(self, agent_id: str) -> None:
        """Agent vừa kết nối: yêu cầu snapshot rồi đẩy nốt các command còn tồn."""
        agent = self.db.get_agent(agent_id)
        # Agent role CLICKER không có vị thế nào để báo cáo — nó chỉ bấm nút.
        if agent is not None and agent["role"] in ("MASTER", "CLIENT"):
            await self.request_snapshot(agent_id)
        await self.flush_pending(agent_id)

    async def request_snapshot(self, agent_id: str) -> str:
        """Yêu cầu agent gửi toàn bộ vị thế hiện có.

        Phase này chỉ lưu lại kết quả; đối chiếu là việc của phase 8.
        """
        return await self.dispatch(agent_id, "REQUEST_SNAPSHOT")

    async def flush_pending(self, agent_id: str) -> int:
        """Gửi mọi command đang `PENDING` của một agent, theo đúng thứ tự tạo.

        **Command quá hạn thì HUỶ chứ không gửi.** Agent offline mười phút rồi nối lại mà nhận
        được một lệnh mở đã cũ là tình huống mất tiền. Lưu ý `scan_deadlines()` cố ý chỉ quét
        `SENT` — nó phân biệt "chưa gửi được" với "đã gửi mà không có phản hồi" — nên command
        `PENDING` không bao giờ tự hết hạn ở đó. Phải kiểm ngay tại chỗ gửi bù này.
        """
        now = utc_now_iso()
        rows = [
            row for row in self.db.list_inflight_commands()
            if row["target_agent_id"] == agent_id and row["status"] == "PENDING"
        ]
        sent = 0
        for row in rows:
            if row["deadline_at"] and row["deadline_at"] < now:
                self.cancel_expired(row)
                continue
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            if await self._send(row["command_id"], agent_id, row["type"], row["pair_id"],
                                payload, row["deadline_at"]):
                sent += 1
        if sent:
            log.info("Da gui bu %d command ton dong cho agent %s", sent, agent_id,
                     extra={"agent_id": agent_id})
        return sent

    def cancel_expired(self, command: sqlite3.Row) -> None:
        """Huỷ một command chưa kịp gửi thì đã quá hạn."""
        command_id = command["command_id"]
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE command SET status = 'CANCELLED', updated_at = ? WHERE command_id = ?",
                (utc_now_iso(), command_id),
            )
        self.db.create_alert(
            "WARNING", "COMMAND_EXPIRED_BEFORE_SEND",
            f"Command {command_id} type {command['type']} qua han truoc khi gui duoc, da huy",
            pair_id=command["pair_id"], agent_id=command["target_agent_id"],
        )
        log.warning("Command %s qua han truoc khi gui duoc, huy thay vi gui lenh cu",
                    command_id, extra={"command_id": command_id, "pair_id": command["pair_id"],
                                       "agent_id": command["target_agent_id"]})

    # -- hạn -------------------------------------------------------------------------------

    def scan_deadlines(self) -> int:
        """Chuyển các command `SENT` quá hạn sang `TIMEOUT` và tạo alert.

        Chỉ quét `SENT`. Command `PENDING` là chưa gửi được vì agent offline — đánh `TIMEOUT`
        cho nó là trộn lẫn hai tình huống khác hẳn nhau.
        """
        now = utc_now_iso()
        rows = self.db.query_all(
            "SELECT * FROM command WHERE status = 'SENT' AND deadline_at IS NOT NULL "
            "AND deadline_at < ?",
            (now,),
        )
        for row in rows:
            command_id = row["command_id"]
            with self.db.transaction() as conn:
                conn.execute(
                    "UPDATE command SET status = 'TIMEOUT', updated_at = ? WHERE command_id = ?",
                    (now, command_id),
                )
            self.db.create_alert(
                "ERROR", "COMMAND_TIMEOUT",
                f"Command {command_id} type {row['type']} khong nhan duoc ack truoc han",
                pair_id=row["pair_id"], agent_id=row["target_agent_id"],
            )
            log.error("Command %s qua han ma chua co ack, chuyen TIMEOUT", command_id,
                      extra={"command_id": command_id, "pair_id": row["pair_id"],
                             "agent_id": row["target_agent_id"]})
            if self.on_timeout is not None:
                self.on_timeout(self.db.get_command(command_id))
        return len(rows)
