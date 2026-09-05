"""Nhật ký lệnh của clicker — nơi tính bất biến sống.

Giao diện MT5 **không trả về gì**. Một cú bấm đã đi rồi thì không có cách nào hỏi lại xem nó có
đi hay không. Nên toàn bộ an toàn của đường mở lệnh qua giao diện nằm ở đúng một kỷ luật, chép
nguyên từ `ea/CopyBridgeCommon.mqh` hàm `ReserveCommand` của phase 5:

```
đã biết + có ack   → gửi lại ack cũ NGUYÊN VĂN, không bấm gì
đã biết + ack rỗng → trả "unknown", TUYỆT ĐỐI không bấm lại
chưa biết          → ghi dòng giữ chỗ + flush + os.fsync() TRƯỚC phím đầu tiên
```

Dòng giữ chỗ phải nằm trên đĩa **trước** phím đầu tiên. Nếu tiến trình chết giữa chừng, một lệnh
thiếu là chuyện sửa được bằng tay; một lệnh thừa là mất tiền.

File là NDJSON append-only, ngữ nghĩa "dòng sau đè dòng trước" — không bao giờ sửa hay xoá dòng
cũ, vì viết đè tại chỗ là cơ hội để mất dữ liệu khi mất điện.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bridge.clock import utc_now_iso


@dataclass
class JournalEntry:
    """Những gì clicker biết về một `command_id`."""

    command_id: str
    reserved_at: str
    ack: dict[str, Any] | None = None
    #: Đã thực sự bấm nút gửi lệnh chưa. `None` nghĩa là **không biết** — trạng thái nguy hiểm
    #: nhất và cũng là trạng thái phải giả định khi mất điện giữa chừng.
    clicked: bool | None = None


class CommandJournal:
    """Nhật ký append-only, đọc lại toàn bộ khi khởi động."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: dict[str, JournalEntry] = {}
        self._load()

    # -- đọc ---------------------------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    # Dòng cuối bị cắt giữa chừng vì mất điện. Bỏ dòng hỏng, KHÔNG bỏ cả file:
                    # những dòng trước nó vẫn là bằng chứng hợp lệ về việc đã bấm.
                    continue
                command_id = row.get("command_id")
                if not command_id:
                    continue
                self._entries[command_id] = JournalEntry(
                    command_id=command_id,
                    reserved_at=row.get("reserved_at") or row.get("ts") or "",
                    ack=row.get("ack"),
                    clicked=row.get("clicked"),
                )

    def get(self, command_id: str) -> JournalEntry | None:
        return self._entries.get(command_id)

    def __contains__(self, command_id: object) -> bool:
        return command_id in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    # -- ghi ---------------------------------------------------------------------------------

    def _append(self, entry: JournalEntry) -> None:
        row = {
            "command_id": entry.command_id,
            "reserved_at": entry.reserved_at,
            "clicked": entry.clicked,
            "ack": entry.ack,
            "ts": utc_now_iso(),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            # `flush()` mới đẩy khỏi bộ đệm Python; `fsync()` mới đẩy khỏi bộ đệm hệ điều hành.
            # Thiếu dòng dưới thì cả cơ chế này chỉ đúng khi tiến trình chết mà máy còn sống.
            os.fsync(handle.fileno())
        self._entries[entry.command_id] = entry

    def reserve(self, command_id: str) -> JournalEntry:
        """Giữ chỗ cho một `command_id` mới. Gọi TRƯỚC khi chạm vào giao diện."""
        if command_id in self._entries:
            raise ValueError(f"command_id {command_id} da co trong nhat ky")
        entry = JournalEntry(command_id=command_id, reserved_at=utc_now_iso())
        self._append(entry)
        return entry

    def mark_clicked(self, command_id: str) -> None:
        """Ghi nhận đã bấm nút gửi lệnh. Gọi ngay sau cú bấm, trước khi đọc kết quả."""
        entry = self._entries[command_id]
        entry.clicked = True
        self._append(entry)

    def complete(self, command_id: str, ack: dict[str, Any]) -> None:
        """Chốt kết quả cuối cùng của một command."""
        entry = self._entries[command_id]
        entry.ack = dict(ack)
        if entry.clicked is None:
            entry.clicked = ack.get("status") != "rejected"
        self._append(entry)
