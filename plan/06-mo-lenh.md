# Phase 6 — Luồng mở lệnh

## Mục tiêu

Master mở lệnh thì Client tự động mở lệnh tương ứng, đúng chiều, đúng volume, có Pair ID.
Đây là lần đầu hệ thống chạy tự động đầu-cuối.

## Điều kiện đầu vào

Phase 5 xong. Hai EA chạy được, Bridge điều khiển được Client bằng command tay.

---

## Việc cần làm

### 6.1 Vòng xử lý sự kiện

`bridge/engine/processor.py`. Một task nền lấy event `PENDING` theo thứ tự `id` tăng dần
và xử lý tuần tự **theo từng agent**. Không xử lý song song các event của cùng một agent —
thứ tự là ràng buộc nghiệp vụ, không phải tiểu tiết.

Mỗi event xử lý xong chuyển `process_status` sang `DONE`, `IGNORED` hoặc `ERROR`.
Event `ERROR` không chặn hàng đợi nhưng phải tạo alert.

### 6.2 Điều kiện lọc trước khi copy

Nhận `position_opened` từ Master. Bỏ qua (đánh `IGNORED`) nếu bất kỳ điều nào đúng:

- `run_mode` không phải `RUNNING`. Ở `PAUSE_NEW_ENTRIES` thì vẫn ghi nhận nhưng không copy.
- Symbol không có trong `symbol_map` của Client nào, hoặc mọi mapping đều `enabled = 0`.
- Đã tồn tại `pair` cho `(master_position_id, client_id)` — chống copy trùng.
- Tuổi sự kiện vượt `max_event_age_ms`. Ghi WARNING kèm tuổi thực tế.
- Client đang `OFFLINE` hoặc `DEGRADED`. Xử lý theo `offline_reopen_policy` (mặc định `NONE`
  nghĩa là bỏ qua và cảnh báo).

Mỗi lý do bỏ qua phải ghi log rõ ràng. "Không copy" mà không biết vì sao là tình huống tệ nhất
khi vận hành.

### 6.3 Tính toán lệnh Client

`bridge/engine/sizing.py`. Với mỗi Client đang bật, theo thứ tự:

**Bước 1 — ánh xạ symbol.** Tra `symbol_map`. Không có mapping → bỏ qua Client này, alert WARNING.
Tuyệt đối không mặc định hai sàn dùng cùng tên symbol.

**Bước 2 — xác định chiều.** `copy_mode` lấy từ `symbol_map` nếu có, ngược lại từ `client_account`.
- `SAME`: BUY→BUY, SELL→SELL
- `OPPOSITE`: BUY→SELL, SELL→BUY

**Bước 3 — volume thô.** `raw = master_volume × multiplier`, multiplier lấy theo cùng quy tắc
kế thừa như `copy_mode`.

**Bước 4 — quy đổi contract size.** Nếu `contract_size` của symbol trên hai sàn khác nhau,
quy đổi theo tỷ lệ. Nếu bằng nhau (trường hợp thường gặp), bỏ qua bước này.
Ghi rõ trong log khi có quy đổi, vì nó dễ gây bất ngờ.

**Bước 5 — chuẩn hoá theo sàn Client.** Lấy `volume_min`, `volume_max`, `volume_step` từ
`symbol_spec` của agent Client.
- Làm tròn theo `rounding_mode`, mặc định `DOWN` (D-18).
- Làm tròn xuống bội số của `volume_step`. Cẩn thận với sai số dấu phẩy động:
  `0.3 / 0.1` trong Python cho `2.9999...`. Dùng số nguyên đơn vị bước hoặc `Decimal`.
- Vượt `volume_max` → kẹp về `volume_max`, alert WARNING.

**Bước 6 — kiểm tra tối thiểu.** Kết quả nhỏ hơn `volume_min`:
- `below_min_policy = SKIP` (mặc định): **bỏ qua lệnh**, alert WARNING, không tạo pair.
- `below_min_policy = USE_MIN`: mở bằng `volume_min`, alert INFO ghi rõ tỷ lệ hedge bị lệch.

**Bước 7 — kiểm tra hạn mức rủi ro.** `max_volume_per_order`, `max_total_volume`,
`max_open_pairs`. Vi phạm → bỏ qua, alert ERROR.

**Bước 8 — tính `effective_multiplier`.**
```
effective_multiplier = client_volume_cuối_cùng / master_volume
```
Đây là tỷ lệ **thực tế sau làm tròn**, không phải hệ số cấu hình. Khoá lại trong `pair`
và dùng cho mọi phép tính đóng một phần về sau (D-19).

Ví dụ: Master 0.07, hệ số 0.33 → thô 0.0231 → làm tròn xuống theo step 0.01 → 0.02.
`effective_multiplier = 0.02 / 0.07 = 0.2857`, không phải 0.33.

### 6.4 Tạo pair và gửi command

Trong **một giao dịch DB**:
1. `INSERT` hoặc `UPDATE` `master_position`.
2. `INSERT` `pair` với `status = PENDING_OPEN`, đã có `effective_multiplier`.
3. `INSERT` `command` `OPEN` với `status = PENDING`, `deadline_at = now + max_event_age_ms`.

Rồi mới gửi command qua socket.

Nếu bước 2 gặp lỗi ràng buộc `UNIQUE (master_position_id, client_id)` → đã có pair rồi,
đây là event lặp. Bỏ qua toàn bộ, ghi INFO. **Không được coi là lỗi.**

### 6.5 Xử lý ack

**Thành công** (`retcode = 10009`): cập nhật `pair` sang `OPEN`, ghi `client_position_id`,
`client_ticket`, `client_initial_volume`, `client_current_volume`, `open_time_client`.
Tính và ghi độ trễ copy (từ `open_time_master` tới `open_time_client`) để dashboard dùng.

**Thất bại**: phân loại `retcode` theo bảng ở phase 5.

- Nhóm retry → tăng `attempt`, tạo command mới sau `retry_interval_ms`, tối đa `max_retry`.
- Nhóm dừng, hoặc hết số lần retry → áp `open_fail_policy` (FR-20):

| Policy | Hành vi |
|---|---|
| `ALERT_ONLY` | `pair.status = OPEN_FAILED`, alert ERROR. Master giữ nguyên. |
| `RETRY` | Đã retry ở trên. Hết lượt thì như `ALERT_ONLY`. |
| `RETRY_CLOSE_MASTER` | Hết lượt thì gửi command đóng Master, alert CRITICAL. |

> Với nhiều Client: `RETRY_CLOSE_MASTER` của một Client sẽ đóng Master và kéo theo mọi Client
> khác. Ở MVP một Client thì không thấy, nhưng **phải cài đặt đúng ngay**: trước khi đóng Master,
> kiểm tra xem còn Client nào đã hedge thành công cho vị thế này không. Nếu có, ghi alert CRITICAL
> nêu rõ hậu quả và **vẫn thực hiện** theo cấu hình — nhưng phải nhìn thấy được trên dashboard.

### 6.6 Timeout

Command `OPEN` quá `deadline_at` chưa có ack → `pair.status = OPEN_FAILED`, alert ERROR.
**Không tự động thử lại sau timeout** — không biết lệnh đã khớp hay chưa, và mở thêm
là hành động tăng rủi ro (D-13). Để đối chiếu ở phase 8 dọn.

---

## Kiểm tra lại phần cũ

- [ ] Toàn bộ test Python phase 1–3 xanh.
- [ ] Test bất biến của phase 5 vẫn xanh: gửi cùng `command_id` hai lần không mở hai lệnh.
- [ ] Test "một hành động, một event" của phase 4 vẫn đúng.
- [ ] Các ràng buộc DB của phase 2 vẫn chặn được: chạy lại toàn bộ test ràng buộc.

## Kiểm tra phần mới

Dùng mock agent cho phần lớn, hai terminal demo cho phần cuối.

- [ ] Master BUY XAUUSD 1.00, hệ số 0.50, chế độ khác chiều → Client SELL symbol đã ánh xạ 0.50 lot,
      pair `OPEN`, có Pair ID. (TEST-02 trong đặc tả gốc)
- [ ] Cùng vậy với chế độ cùng chiều → Client BUY. (TEST-01)
- [ ] Master mở ba lệnh XAUUSD → tạo đúng ba Pair ID khác nhau. (TEST-07)
- [ ] Master mở XAUUSD, EURUSD, GBPUSD → cả ba copy đúng theo mapping riêng. (TEST-08)
- [ ] Bơm cùng một event `position_opened` hai lần → chỉ một pair được tạo.
- [ ] Symbol không có trong mapping → không copy, có alert, không có pair.
- [ ] Master 0.01 lot, hệ số 0.50, `volume_min = 0.01` → **bỏ qua lệnh**, có alert, không có pair.
- [ ] Cùng vậy với `below_min_policy = USE_MIN` → mở 0.01, alert INFO.
- [ ] Master 0.07, hệ số 0.33, step 0.01 → Client 0.02, `effective_multiplier ≈ 0.2857`.
      Kiểm tra giá trị lưu trong DB, không phải 0.33.
- [ ] Kiểm tra sai số dấu phẩy động: chạy 200 tổ hợp volume và step ngẫu nhiên,
      kết quả luôn là bội số chính xác của step.
- [ ] Client trả `retcode = 10004` hai lần rồi thành công → có ba command, pair cuối cùng `OPEN`.
- [ ] Client trả `retcode = 10019` → hết retry, `pair.status = OPEN_FAILED`, alert ERROR,
      Master không bị đóng (policy `ALERT_ONLY`).
- [ ] Đổi policy sang `RETRY_CLOSE_MASTER`, lặp lại → Master nhận command đóng, alert CRITICAL.
- [ ] Client offline → không copy, alert, không có command treo vô hạn.
- [ ] `run_mode = PAUSE_NEW_ENTRIES` → event được ghi nhận nhưng không tạo pair.
- [ ] Event cũ hơn `max_event_age_ms` → bỏ qua, WARNING ghi rõ tuổi.
- [ ] Command `OPEN` không có ack tới hạn → `OPEN_FAILED`, không tự gửi lại.
- [ ] Trên hai demo thật: mở tay một lệnh trên Master, quan sát Client mở đúng trong dưới 1 giây.

## Tiêu chí hoàn thành

Mở tay 20 lệnh trên Master demo với nhiều symbol và volume khác nhau. Client có đúng 20 vị thế
tương ứng, đúng chiều, đúng tỷ lệ, mỗi cặp một Pair ID, không cặp nào trùng, không cặp nào thiếu.

## Không làm ở phase này

Chưa xử lý đóng lệnh. Nếu đóng lệnh Master lúc này thì Client sẽ không đóng — đó là đúng
với phạm vi phase. Đóng tay cả hai bên khi test xong.
