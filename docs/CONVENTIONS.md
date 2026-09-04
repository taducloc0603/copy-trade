# Quy ước code

## 1. Ngôn ngữ

- **Tiếng Anh** cho: tên biến, tên hàm, tên lớp, tên bảng và cột DB, giá trị enum, nội dung log,
  message giao thức, tên file, tên nhánh git.
- **Tiếng Việt** chỉ xuất hiện ở hai nơi: `bridge/labels_vi.py` và các template giao diện (D-16).
- Enum luôn là tiếng Anh **không dấu, viết hoa**: `PENDING_OPEN`, `ORPHANED`, `PAUSE_NEW_ENTRIES`.
- Chú thích và docstring trong code viết bằng tiếng Việt. Đây không phải chuỗi hướng tới người
  dùng và không bao giờ bị so sánh, `grep` hay lưu vào DB, nên không thuộc phạm vi D-16.
  Tài liệu trong `docs/` cũng vậy.
- Chuỗi xác nhận nguy hiểm trên giao diện cố ý **không dấu** (`DONG TAT CA`): bắt gõ tiếng Việt
  có dấu trong lúc hoảng, với bộ gõ có thể đang ở chế độ khác, là tự tạo thêm rắc rối.

## 2. Đặt tên

| Loại | Quy ước | Ví dụ |
|---|---|---|
| Biến, hàm, module Python | `snake_case` | `effective_multiplier`, `record_event()` |
| Lớp Python | `PascalCase` | `Database`, `ContextFormatter` |
| Hằng và enum | `UPPER_SNAKE` | `DEFAULT_LOG_DIR`, `PARTIALLY_CLOSED` |
| Nội bộ, không phải API công khai | tiền tố `_` | `_require_port()` |
| Bảng và cột SQL | `snake_case`, bảng số ít | `master_position`, `client_position_id` |
| File MQL5 | `PascalCase` | `CopyBridgeCommon.mqh` |

## 3. Tiền thật

- **Mọi hàm chạm vào tiền** (tính volume, gửi lệnh, đóng lệnh) phải có docstring nêu rõ
  **đơn vị** và **điều kiện biên**: đơn vị là lot hay bước volume, giá trị nào bị từ chối,
  chuyện gì xảy ra khi kết quả nhỏ hơn `volume_min`.
- **Không dùng `float` cho so sánh volume.** Luôn so sánh với epsilon, hoặc tốt hơn là quy về
  số nguyên đơn vị bước (`volume / volume_step` làm tròn thành `int`) hoặc dùng `Decimal`.
  `0.3 / 0.1` trong Python cho `2.9999...` — đây là lỗi có thật, không phải lo xa.
- Không có đoạn code nào được gửi lệnh thật cho tới phase 10, và ngay cả khi đó cũng chỉ
  trên tài khoản demo.

## 4. Logging

- Lấy logger bằng `get_logger(__name__)`, không dùng `logging.info()` ở cấp module gốc.
- Bốn mức dùng trong dự án: INFO, WARNING, ERROR, CRITICAL. DEBUG chỉ để gỡ lỗi tại chỗ,
  không để lại trong code đã merge.
- Mọi log liên quan tới một cặp lệnh phải mang `pair_id`; liên quan tới một sự kiện phải mang
  `event_id`. Truyền qua `extra={}`:

  ```python
  log.warning("Volume dưới mức tối thiểu, bỏ qua lệnh", extra={"pair_id": pair_id})
  ```

- **Không log token, không log mật khẩu.** `RedactingFilter` là lưới an toàn cuối cùng,
  không phải lý do để viết code log token.
- Mỗi lý do bỏ qua một lệnh phải ghi log rõ ràng. "Không copy" mà không biết vì sao là
  tình huống tệ nhất khi vận hành.

## 5. Database

- Không dùng ORM. Viết SQL trực tiếp — schema nhỏ và các ràng buộc là phần quan trọng nhất.
- **Mọi hàm ghi phải nằm trong một giao dịch.** Không có ghi lẻ.
- Hàm repository đặt tên theo nghiệp vụ, không phải CRUD chung chung:
  `create_pending_pair()`, chứ không phải `insert_pair()`.
- Ràng buộc trong schema là cơ chế chống copy trùng cuối cùng — logic ứng dụng có thể sai,
  ràng buộc DB thì không.

## 6. Tra cứu vị thế

- Tra cứu **luôn theo `position_id`**, không bao giờ theo symbol.
  Câu SQL đóng lệnh có điều kiện `WHERE symbol = ?` là bug.
- Khoá định danh là `POSITION_IDENTIFIER`, không phải ticket (D-06).

## 7. Định dạng và lint

- `ruff check .` phải sạch trước mỗi commit. Line length 110.
- Import sắp xếp theo nhóm chuẩn (`ruff` rule `I`): thư viện chuẩn, thư viện ngoài, nội bộ.
- `from __future__ import annotations` ở đầu mọi module Python.

## 8. Test

- Ưu tiên test tình huống lỗi hơn test đường đi thuận lợi. Đường thuận lợi hiếm khi hỏng.
- Tên hàm test viết bằng tiếng Việt không dấu, mô tả hành vi mong đợi:
  `test_label_thieu_key_tra_ve_chinh_key_va_ghi_warning`.
- Không cần MT5 thật cho phase 1–3 và 6–9; dùng mock agent (xây ở phase 3, tái sử dụng về sau).
- Phase 4, 5 và 10 cần terminal MT5 thật ở chế độ demo.

## 9. Quy trình theo phase

- Đọc `PROGRESS.md` trước khi bắt đầu một phase.
- Chạy toàn bộ test hiện có **trước khi** viết code mới. Có test đỏ thì sửa trước.
- Kết thúc phase: chạy lại test các phase trước, chạy test phase vừa làm, cập nhật `PROGRESS.md`.
- Không viết code cho phase sau. Thấy cần thì ghi vào mục "Phát hiện sớm" của `PROGRESS.md`.
- Không tự đổi quyết định trong `docs/DECISIONS.md`. Gặp mâu thuẫn thì dừng và báo cáo.
