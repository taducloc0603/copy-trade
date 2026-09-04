"""Xác thực agent bằng token.

Token thô chỉ tồn tại ở hai nơi: tham số của EA và `config.toml`. Trong database chỉ có hash.
Không có hàm nào ở đây ghi token ra log, và không được thêm hàm như vậy.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

#: Độ dài tối thiểu của token thô, tính bằng byte trước khi mã hoá hex.
TOKEN_BYTES = 32


def hash_token(token: str) -> str:
    """Băm token thô thành chuỗi hex để lưu vào `agent.token_hash`."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    """So token thô với hash đã lưu.

    Dùng `hmac.compare_digest` để thời gian so sánh không phụ thuộc nội dung — không phải vì
    kẻ tấn công qua Tailscale dễ đo được, mà vì so sánh chuỗi thường là thói quen xấu ở chỗ này.
    """
    if not token or not token_hash:
        return False
    return hmac.compare_digest(hash_token(token), token_hash)


def generate_token() -> str:
    """Sinh token ngẫu nhiên mới. Giá trị trả về chỉ được đưa cho người vận hành, không log."""
    return secrets.token_hex(TOKEN_BYTES)
