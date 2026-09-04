"""Test khung NDJSON (D-02).

Ba tình huống TCP luôn xảy ra thật và phải chịu được: message bị cắt, message dính nhau,
và một agent hỏng bơm ra dòng vô tận.
"""

from __future__ import annotations

import pytest

from bridge.protocol.framing import (
    LineBuffer,
    LineTooLong,
    ProtocolDecodeError,
    decode_line,
    encode_line,
)


def test_mot_message_cat_lam_ba_manh_van_ghep_dung() -> None:
    data = encode_line({"kind": "heartbeat", "seq": 7})
    buffer = LineBuffer()
    a, b = len(data) // 3, 2 * len(data) // 3

    assert buffer.feed(data[:a]) == []
    assert buffer.feed(data[a:b]) == []
    lines = buffer.feed(data[b:])

    assert len(lines) == 1
    assert decode_line(lines[0]) == {"kind": "heartbeat", "seq": 7}


def test_hai_message_dinh_trong_mot_goi_duoc_tach_dung() -> None:
    data = encode_line({"kind": "a"}) + encode_line({"kind": "b"})
    lines = LineBuffer().feed(data)

    assert [decode_line(line)["kind"] for line in lines] == ["a", "b"]


def test_nhieu_message_va_mot_manh_do_dang() -> None:
    buffer = LineBuffer()
    data = encode_line({"kind": "a"}) + encode_line({"kind": "b"}) + b'{"kind":"c"'

    lines = buffer.feed(data)
    assert len(lines) == 2
    assert len(buffer) == len(b'{"kind":"c"')

    lines = buffer.feed(b"}\n")
    assert [decode_line(line)["kind"] for line in lines] == ["c"]


def test_dong_rong_bi_bo_qua() -> None:
    """Vài EA gửi thừa `\\n`. Dòng rỗng không phải lỗi, chỉ là không có gì."""
    assert LineBuffer().feed(b"\n\n\n") == []


def test_dong_qua_dai_thi_bao_loi_va_khong_giu_bo_nho() -> None:
    buffer = LineBuffer(max_line_bytes=100)
    with pytest.raises(LineTooLong):
        buffer.feed(b"x" * 200)
    assert len(buffer) == 0, "Bộ đệm phải được giải phóng, không giữ dữ liệu rác"


def test_dong_dai_bang_dung_gioi_han_van_duoc() -> None:
    buffer = LineBuffer(max_line_bytes=100)
    buffer.feed(b"y" * 100)
    assert len(buffer) == 100


def test_newline_trong_chuoi_khong_pha_vo_khung() -> None:
    """JSON hợp lệ escape newline, nên byte 0x0A thô không bao giờ nằm giữa một message."""
    payload = {"kind": "event", "retmsg": "dong mot\ndong hai"}
    data = encode_line(payload)

    assert data.count(b"\n") == 1, "Chỉ được có đúng một newline: ký tự kết thúc dòng"
    lines = LineBuffer().feed(data)
    assert decode_line(lines[0])["retmsg"] == "dong mot\ndong hai"


def test_ky_tu_ngoai_ascii_di_qua_nguyen_ven() -> None:
    payload = {"kind": "event", "symbol": "XAUUSD€", "note": "Tiếng Việt có dấu"}
    lines = LineBuffer().feed(encode_line(payload))
    assert decode_line(lines[0]) == payload


@pytest.mark.parametrize(
    "line",
    [
        b"khong phai json",
        b"{thieu ngoac}",
        b"[1, 2, 3]",
        b'"chi la mot chuoi"',
        b"42",
        b"\xff\xfe khong phai utf8",
    ],
)
def test_dong_hong_bao_loi_ro_rang(line: bytes) -> None:
    with pytest.raises(ProtocolDecodeError):
        decode_line(line)


def test_thong_bao_loi_khong_kem_ca_dong_dai() -> None:
    """Dòng hỏng có thể rất dài — log chỉ được lấy phần đầu."""
    with pytest.raises(ProtocolDecodeError) as exc:
        decode_line(b"x" * 100000)
    assert len(str(exc.value)) < 500
