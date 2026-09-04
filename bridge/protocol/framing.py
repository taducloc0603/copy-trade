r"""Khung NDJSON trên TCP (D-02).

Mỗi message là một dòng JSON kết thúc bằng ``\n``.

An toàn về cú pháp vì JSON hợp lệ luôn escape newline thành hai ký tự ``\`` và ``n``, nên byte
``0x0A`` thô không bao giờ xuất hiện giữa một message. Khung dòng vì thế không cần header độ dài.

Ba tình huống bộ đệm phải chịu được, và cả ba đều xảy ra thật trên TCP:

* một message bị cắt thành nhiều mảnh tuỳ ý;
* nhiều message dính trong một gói;
* một agent hỏng bơm ra một dòng vô tận.

Trường hợp thứ ba là lý do có `max_line_bytes`: không để một agent lỗi làm cạn bộ nhớ Bridge.
"""

from __future__ import annotations

import json
from typing import Any

#: Giới hạn độ dài một dòng. Vượt thì đóng kết nối chứ không cắt bớt — một message bị cắt là
#: dữ liệu sai, nguy hiểm hơn một kết nối bị mất.
MAX_LINE_BYTES = 256 * 1024

#: Số ký tự đầu của dòng hỏng được ghi vào log. Đủ để nhận ra, không đủ để làm ngập log.
BAD_LINE_LOG_CHARS = 200

NEWLINE = b"\n"


class LineTooLong(Exception):
    """Một dòng vượt quá `max_line_bytes` mà chưa thấy ký tự xuống dòng."""


class ProtocolDecodeError(Exception):
    """Dòng không giải mã được thành JSON. Nơi gọi phải bỏ qua dòng, không được sập."""


class LineBuffer:
    """Gom byte từ socket và cắt ra từng dòng hoàn chỉnh."""

    __slots__ = ("_buffer", "max_line_bytes")

    def __init__(self, max_line_bytes: int = MAX_LINE_BYTES) -> None:
        self.max_line_bytes = max_line_bytes
        self._buffer = bytearray()

    def __len__(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[bytes]:
        """Nạp thêm byte, trả về các dòng đã hoàn chỉnh (không kèm ``\n``).

        Ném `LineTooLong` khi phần còn dang dở vượt giới hạn.
        """
        self._buffer.extend(chunk)
        lines: list[bytes] = []
        while True:
            index = self._buffer.find(NEWLINE)
            if index < 0:
                break
            line = bytes(self._buffer[:index])
            del self._buffer[: index + 1]
            if line:
                lines.append(line)
        if len(self._buffer) > self.max_line_bytes:
            overflow = len(self._buffer)
            self._buffer.clear()
            raise LineTooLong(f"Dòng dài {overflow} byte, vượt giới hạn {self.max_line_bytes}")
        return lines


def encode_line(payload: dict[str, Any]) -> bytes:
    """Đóng gói một message thành đúng một dòng NDJSON.

    `ensure_ascii=False` để tên symbol ngoài ASCII giữ nguyên; UTF-8 lo phần mã hoá.
    """
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text.encode("utf-8") + NEWLINE


def decode_line(line: bytes) -> dict[str, Any]:
    """Giải mã một dòng thành dict.

    Ném `ProtocolDecodeError` khi dòng không phải UTF-8 hợp lệ, không phải JSON, hoặc là JSON
    nhưng không phải một object. Thông báo lỗi kèm tối đa `BAD_LINE_LOG_CHARS` ký tự đầu để
    còn lần ra được nguồn — nhưng không kèm cả dòng, vì dòng hỏng có thể rất dài.
    """
    preview = line[: BAD_LINE_LOG_CHARS * 4].decode("utf-8", errors="replace")[:BAD_LINE_LOG_CHARS]
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolDecodeError(f"Dòng không phải UTF-8 hợp lệ: {preview!r}") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolDecodeError(f"Dòng không phải JSON hợp lệ: {preview!r}") from exc
    if not isinstance(payload, dict):
        raise ProtocolDecodeError(f"Message phải là JSON object, nhận được {type(payload).__name__}")
    return payload
