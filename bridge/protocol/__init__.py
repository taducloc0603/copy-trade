"""Tầng giao thức: khung NDJSON, schema message, TCP server, outbox command.

Ở phase này Bridge chưa hiểu gì về giao dịch — nó chỉ là một đường ống đáng tin cậy.
"""

from bridge.protocol.auth import generate_token, hash_token, verify_token
from bridge.protocol.framing import LineBuffer, LineTooLong, decode_line, encode_line

__all__ = [
    "LineBuffer",
    "LineTooLong",
    "decode_line",
    "encode_line",
    "generate_token",
    "hash_token",
    "verify_token",
]
