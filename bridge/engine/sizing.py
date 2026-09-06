"""Tính volume cho lệnh Client (plan mục 6.3).

Toàn bộ file này là **hàm thuần**: không đọc DB, không gửi lệnh. Nhận vào các con số đã tra
sẵn, trả ra kết quả và lý do. Nhờ vậy tám bước tính toán ở đây test được bằng bảng số liệu mà
không cần dựng cả hệ thống.

**Không dùng `float` cho phép tính volume.** `0.3 / 0.1` trong Python cho `2.9999999999999996`;
làm tròn xuống con số đó ra 2 bước thay vì 3, tức là lệch một bước volume trên mỗi lệnh. Mọi
phép tính ở đây chạy bằng `Decimal` khởi tạo từ **chuỗi**, và chỉ đổi về `float` ở đúng biên
ra ngoài.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal, InvalidOperation

from bridge.logging_setup import get_logger

log = get_logger(__name__)

#: Lý do bỏ qua một lệnh. Tiếng Anh không dấu như mọi enum khác (D-16).
SKIP_BELOW_MIN = "BELOW_MIN"
SKIP_ZERO_AFTER_ROUNDING = "ZERO_AFTER_ROUNDING"
SKIP_MAX_VOLUME_PER_ORDER = "MAX_VOLUME_PER_ORDER"
SKIP_MAX_TOTAL_VOLUME = "MAX_TOTAL_VOLUME"
SKIP_MAX_OPEN_PAIRS = "MAX_OPEN_PAIRS"
SKIP_BAD_SPEC = "BAD_SPEC"

#: Chiều lệnh theo `copy_mode`.
_OPPOSITE = {"BUY": "SELL", "SELL": "BUY"}


def to_decimal(value: float | int | str | Decimal) -> Decimal:
    """Đổi sang `Decimal` qua chuỗi, để `0.1` là đúng một phần mười chứ không phải xấp xỉ nhị phân."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class SizingInputs:
    """Mọi con số cần cho một phép tính volume. Người gọi tra DB rồi điền vào đây."""

    master_volume: float
    multiplier: float
    #: 'DOWN' hoặc 'NEAREST'. Mặc định của hệ thống là DOWN (D-18).
    rounding_mode: str = "DOWN"
    #: 'SKIP' hoặc 'USE_MIN'. Mặc định SKIP (D-18).
    below_min_policy: str = "SKIP"

    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01

    #: Chỉ quy đổi khi hai sàn khác nhau. Bằng nhau (trường hợp thường gặp) thì bỏ qua bước này.
    master_contract_size: float | None = None
    client_contract_size: float | None = None

    max_volume_per_order: float | None = None
    max_total_volume: float | None = None
    current_total_volume: float = 0.0
    max_open_pairs: int | None = None
    current_open_pairs: int = 0


@dataclass
class SizingResult:
    """Kết quả tính volume.

    `volume is None` nghĩa là **bỏ qua lệnh này**, và `skip_reason` cho biết vì sao. Bỏ qua
    không phải lỗi — nhưng luôn phải kèm cảnh báo, vì "không copy" mà không biết vì sao là
    tình huống tệ nhất khi vận hành.
    """

    volume: float | None = None
    #: Tỷ lệ THỰC TẾ sau làm tròn, khoá vào `pair` và dùng cho mọi phép đóng một phần (D-19).
    effective_multiplier: float | None = None
    skip_reason: str | None = None
    #: (level, code, message) — người gọi ghi vào bảng `alert`.
    alerts: list[tuple[str, str, str]] = field(default_factory=list)
    #: Ghi chú để log, ví dụ khi có quy đổi contract size.
    notes: list[str] = field(default_factory=list)

    @property
    def skipped(self) -> bool:
        return self.volume is None


def resolve_direction(master_direction: str, copy_mode: str) -> str:
    """Bước 2 — xác định chiều lệnh Client.

    `SAME`: BUY→BUY, SELL→SELL. `OPPOSITE`: BUY→SELL, SELL→BUY.
    """
    if master_direction not in _OPPOSITE:
        raise ValueError(f"Chiều lệnh Master không hợp lệ: {master_direction!r}")
    return master_direction if copy_mode == "SAME" else _OPPOSITE[master_direction]


def inherit(symbol_value, account_value):
    """Giá trị ở `symbol_map` là NULL nghĩa là **kế thừa** từ `client_account`."""
    return account_value if symbol_value is None else symbol_value


def round_to_step(raw: Decimal, step: Decimal, mode: str) -> Decimal:
    """Làm tròn về bội số của `step`.

    Phép chia và làm tròn đều bằng `Decimal`, nên kết quả là bội số **chính xác** của step,
    không phải một số thực gần đúng.
    """
    if step <= 0:
        raise ValueError(f"volume_step phải dương, nhận được {step}")
    steps = raw / step
    rounding = ROUND_HALF_UP if mode == "NEAREST" else ROUND_FLOOR
    return steps.quantize(Decimal(1), rounding=rounding) * step


def compute_client_volume(inputs: SizingInputs) -> SizingResult:
    """Tám bước tính volume của plan mục 6.3, từ bước 3 tới bước 8.

    Bước 1 (ánh xạ symbol) và bước 2 (xác định chiều) do người gọi làm trước, vì chúng cần DB.

    Đơn vị: `master_volume` là lot của **sàn Master**, kết quả là lot của **sàn Client**.
    Điều kiện biên quan trọng: kết quả nhỏ hơn `volume_min` thì mặc định **bỏ qua lệnh và cảnh
    báo**, không bao giờ tự nâng volume lên (D-18).
    """
    result = SizingResult()
    try:
        master_volume = to_decimal(inputs.master_volume)
        multiplier = to_decimal(inputs.multiplier)
        volume_min = to_decimal(inputs.volume_min)
        volume_max = to_decimal(inputs.volume_max)
        step = to_decimal(inputs.volume_step)
    except (InvalidOperation, ValueError) as exc:
        result.skip_reason = SKIP_BAD_SPEC
        result.alerts.append(("ERROR", "BAD_SYMBOL_SPEC", f"Thong so symbol khong doc duoc: {exc}"))
        return result

    if master_volume <= 0:
        result.skip_reason = SKIP_BAD_SPEC
        result.alerts.append(("ERROR", "BAD_MASTER_VOLUME",
                              f"Master volume phai duong, nhan duoc {inputs.master_volume}"))
        return result
    if step <= 0 or volume_min <= 0:
        result.skip_reason = SKIP_BAD_SPEC
        result.alerts.append((
            "ERROR", "BAD_SYMBOL_SPEC",
            f"volume_step={inputs.volume_step} volume_min={inputs.volume_min} khong hop le. "
            "Agent Client da day symbol spec len chua?",
        ))
        return result

    # -- Bước 3: volume thô -------------------------------------------------------------
    raw = master_volume * multiplier

    # -- Bước 4: quy đổi contract size ---------------------------------------------------
    master_cs = inputs.master_contract_size
    client_cs = inputs.client_contract_size
    if master_cs and client_cs and to_decimal(master_cs) != to_decimal(client_cs):
        # Giữ nguyên giá trị danh nghĩa: volume_client x cs_client = volume_master x cs_master.
        ratio = to_decimal(master_cs) / to_decimal(client_cs)
        raw = raw * ratio
        result.notes.append(
            f"Quy doi contract size {master_cs} -> {client_cs} (ty le {ratio})"
        )

    # -- Bước 5: chuẩn hoá theo sàn Client ------------------------------------------------
    volume = round_to_step(raw, step, inputs.rounding_mode)

    if volume > volume_max:
        volume = round_to_step(volume_max, step, "DOWN")
        result.alerts.append((
            "WARNING", "VOLUME_CLAMPED",
            f"Volume tinh ra vuot volume_max {inputs.volume_max}, kep ve {volume}",
        ))

    # -- Bước 6: kiểm tra tối thiểu -------------------------------------------------------
    if volume < volume_min:
        if inputs.below_min_policy == "USE_MIN":
            volume = round_to_step(volume_min, step, "NEAREST")
            result.alerts.append((
                "INFO", "VOLUME_RAISED_TO_MIN",
                f"Volume tho {raw} duoi muc toi thieu {inputs.volume_min}, mo bang muc toi "
                f"thieu {volume}. Ty le hedge bi lech.",
            ))
        else:
            result.skip_reason = (SKIP_ZERO_AFTER_ROUNDING if volume <= 0 else SKIP_BELOW_MIN)
            # ERROR chu khong phai WARNING (B-08): bo mot lenh copy la MAT HEDGE, va chi
            # ERROR tro len moi di ra kenh canh bao ngoai. Cung hau qua voi UI_OPEN_BUSY,
            # nen phai cung muc.
            result.alerts.append((
                "ERROR", "VOLUME_BELOW_MIN",
                f"Volume tinh ra {volume} duoi muc toi thieu {inputs.volume_min} cua san "
                f"Client, BO QUA lenh. Khong tu nang volume (D-18).",
            ))
            return result

    # -- Bước 7: hạn mức rủi ro ------------------------------------------------------------
    if inputs.max_volume_per_order is not None and volume > to_decimal(inputs.max_volume_per_order):
        result.skip_reason = SKIP_MAX_VOLUME_PER_ORDER
        result.alerts.append((
            "ERROR", "MAX_VOLUME_PER_ORDER",
            f"Volume {volume} vuot han muc moi lenh {inputs.max_volume_per_order}, bo qua lenh",
        ))
        return result

    if inputs.max_total_volume is not None:
        total_after = to_decimal(inputs.current_total_volume) + volume
        if total_after > to_decimal(inputs.max_total_volume):
            result.skip_reason = SKIP_MAX_TOTAL_VOLUME
            result.alerts.append((
                "ERROR", "MAX_TOTAL_VOLUME",
                f"Tong volume sau lenh nay la {total_after}, vuot han muc "
                f"{inputs.max_total_volume}, bo qua lenh",
            ))
            return result

    if inputs.max_open_pairs is not None and inputs.current_open_pairs >= inputs.max_open_pairs:
        result.skip_reason = SKIP_MAX_OPEN_PAIRS
        result.alerts.append((
            "ERROR", "MAX_OPEN_PAIRS",
            f"Dang co {inputs.current_open_pairs} cap mo, da cham han muc "
            f"{inputs.max_open_pairs}, bo qua lenh",
        ))
        return result

    # -- Bước 8: tỷ lệ thực tế --------------------------------------------------------------
    # KHÔNG phải hệ số cấu hình. Ví dụ Master 0.07 hệ số 0.33 cho Client 0.02, tỷ lệ thật là
    # 0.2857 chứ không phải 0.33. Con số này bị khoá vào `pair` và dùng cho mọi phép đóng
    # một phần về sau (D-19).
    result.volume = float(volume)
    result.effective_multiplier = float(volume / master_volume)
    return result
