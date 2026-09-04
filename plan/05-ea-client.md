# Phase 5 — EA phía Client và thực thi lệnh

## Mục tiêu

EA Client làm mọi thứ EA Master làm, cộng thêm việc thực thi command: mở lệnh, đóng toàn phần,
đóng một phần. Đây là lần đầu tiên hệ thống gửi lệnh giao dịch thật, nên tính bất biến khi
nhận command trùng là yêu cầu sống còn.

## Điều kiện đầu vào

Phase 4 xong. Cần **hai** terminal MT5, cả hai đều dùng tài khoản demo.

---

## Việc cần làm

### 5.1 `ea/CopyBridgeClient.mq5`

Dùng lại `CopyBridgeCommon.mqh`, đặt `AgentRole = CLIENT`. Toàn bộ phần bắt sự kiện, heartbeat,
hàng đợi, symbol specs giữ nguyên — nếu phải copy-paste từ EA Master thì có nghĩa là file
include chưa tách đủ, quay lại sửa phase 4.

### 5.2 Thực thi command

Ba loại: `OPEN`, `CLOSE`, `CLOSE_PARTIAL`.

**Quy tắc bất biến (idempotency) — đọc kỹ.**

Trước khi thực thi bất kỳ command nào:
1. Tra `command_id` trong bộ nhớ command đã xử lý.
2. Đã có → trả về **ack cũ nguyên văn**, không đặt lệnh, ghi log INFO.
3. Chưa có → ghi `command_id` vào file **trước khi** gọi `OrderSend`, rồi mới thực thi.

> Ghi trước khi gọi là cố ý. Nếu terminal crash ngay sau `OrderSend` mà trước khi ghi,
> ta sẽ mở lệnh hai lần khi Bridge gửi lại. Ghi trước thì tệ nhất là có một `command_id`
> được đánh dấu đã xử lý nhưng thực ra chưa — trường hợp này Bridge sẽ phát hiện qua
> đối chiếu ở phase 8, và một lệnh thiếu an toàn hơn nhiều so với một lệnh thừa.

**`OPEN`**

Payload từ Bridge đã chứa **tất cả** thông số cuối cùng: `symbol` (đã ánh xạ), `type`,
`volume` (đã chuẩn hoá), `deviation`, `magic`, `comment`. EA **không tính toán gì thêm**.

- Chọn filling mode tại chỗ từ `SYMBOL_FILLING_MODE`. Đây là ngoại lệ duy nhất của nguyên tắc
  "EA không có logic" (D-01), vì đây là chi tiết kỹ thuật broker chứ không phải quy tắc nghiệp vụ.
  Thứ tự thử: theo bitmask hỗ trợ, ưu tiên FOK, rồi IOC, rồi RETURN.
- Gọi `OrderSend`. Trả ack với `retcode`, `retmsg`, `executed_volume`, `result_position_id`.
- Ghi nhớ `(command_id, position_id, thời điểm)` để gắn `caused_by_command_id` cho deal
  sắp phát sinh.
- Nếu `retcode = 10030` (filling không hỗ trợ): thử filling mode kế tiếp **đúng một lần**,
  rồi mới báo thất bại.

**`CLOSE`**

Đóng toàn bộ vị thế theo `position_id` trong payload.
- Vị thế không tồn tại → trả ack `status = "already_closed"`, **không phải lỗi**.
  Đây là tình huống bình thường khi hai bên cùng đóng gần như đồng thời (FR-18).
- Dùng `PositionSelectByTicket(position_id)` rồi đặt lệnh ngược chiều đúng volume hiện tại.

**`CLOSE_PARTIAL`**

Đóng đúng `volume` trong payload.
- Volume yêu cầu lớn hơn volume còn lại → đóng toàn bộ phần còn lại, ack ghi rõ
  `executed_volume` thực tế. Không báo lỗi.
- Bridge chịu trách nhiệm chuẩn hoá volume theo `volume_step` trước khi gửi. EA không làm tròn.

### 5.3 Báo cáo mã lỗi

Ack phải mang `retcode` nguyên bản từ `MqlTradeResult`, không dịch, không gộp nhóm.
Bridge sẽ phân loại. Danh sách Bridge quan tâm (cài ở phase 6, ghi ở đây để tham chiếu):

| Retcode | Ý nghĩa | Bridge sẽ làm gì |
|---|---|---|
| 10009 | Thành công | — |
| 10004, 10006 | Requote, bị từ chối | Retry ngay, tối đa 3 lần, giãn 200ms |
| 10021, 10031 | Không có giá, mất kết nối | Đưa hàng đợi, retry theo backoff |
| 10018 | Thị trường đóng cửa | Giữ hàng đợi, retry khi mở cửa, có hạn tuổi sự kiện |
| 10030 | Filling mode không hỗ trợ | EA tự thử lại một lần, sau đó Bridge dừng |
| 10014 | Volume không hợp lệ | Dừng, cảnh báo — lỗi cấu hình |
| 10019 | Không đủ tiền | Dừng, cảnh báo, kích hoạt chính sách mở lệnh thất bại |
| 10013, 10015 | Request hoặc giá không hợp lệ | Dừng, cảnh báo — đây là bug |

Nhóm "dừng" quan trọng ngang nhóm "retry". Retry một lệnh thiếu margin 50 lần chỉ làm chậm
hệ thống và che mất cảnh báo thật.

### 5.4 Hàng rào an toàn phía EA

EA phải từ chối và trả ack lỗi, không thực thi, khi:
- `deadline_ts` trong command đã qua. Lệnh cũ không được thực thi muộn.
- `magic` trong payload khác `MagicNumber` cấu hình trên EA.
- `volume` bằng 0 hoặc âm.
- `symbol` không tồn tại trên terminal này.

Đây là các kiểm tra rẻ tiền chống lại lỗi lập trình ở Bridge. Chúng không thay thế
việc Bridge phải làm đúng.

### 5.5 Mở rộng mock agent

Bổ sung vào `tests/mock_agent.py`: thực thi command giả lập với `retcode` chỉ định được,
mô phỏng độ trễ khớp lệnh, mô phỏng nhận command trùng.

---

## Kiểm tra lại phần cũ

- [ ] Toàn bộ test Python phase 1–3 xanh.
- [ ] Chạy lại toàn bộ kiểm tra EA Master của phase 4 — đặc biệt là "một hành động, một event".
      Nếu việc tách include làm hỏng EA Master, phải phát hiện ở đây.
- [ ] Mock agent mở rộng vẫn tương thích với test cũ.

## Kiểm tra phần mới

Trên hai tài khoản demo:

- [ ] Bridge gửi command `OPEN` thủ công (qua script test) → Client mở đúng symbol, đúng chiều,
      đúng volume, đúng magic.
- [ ] Gửi lại **cùng `command_id`** → Client trả ack cũ, **không mở lệnh thứ hai**.
      Kiểm tra trong terminal chỉ có một vị thế. Đây là test quan trọng nhất của phase.
- [ ] Khởi động lại EA rồi gửi lại cùng `command_id` → vẫn không mở lệnh thứ hai
      (bộ nhớ command phải bền qua khởi động lại).
- [ ] `CLOSE` một vị thế đã bị đóng tay trước đó → ack `already_closed`, không phải ERROR.
- [ ] `CLOSE_PARTIAL` với volume lớn hơn phần còn lại → đóng hết, ack ghi đúng `executed_volume`.
- [ ] Ép lỗi thiếu margin (mở volume rất lớn) → ack mang `retcode = 10019`.
- [ ] Gửi command có `deadline_ts` đã qua → EA từ chối, không đặt lệnh.
- [ ] Gửi command với symbol không tồn tại → ack lỗi, không sập EA.
- [ ] Mở lệnh trên symbol mà broker chỉ hỗ trợ IOC → EA tự chọn đúng filling mode, lệnh khớp.
- [ ] Sau khi EA thực thi `CLOSE`, event `position_closed` sinh ra phải mang
      `caused_by_command_id` đúng bằng `command_id` của lệnh đóng đó.
      **Đây là nền tảng của chống vòng lặp ở phase 7 — không có nó thì phase 7 sẽ sai.**

## Tiêu chí hoàn thành

Có thể điều khiển tài khoản Client hoàn toàn qua command từ Bridge, và mọi command gửi lặp
đều không tạo ra lệnh thừa — kể cả khi EA bị khởi động lại giữa chừng.

## Không làm ở phase này

Bridge vẫn chưa tự động tạo command. Command ở phase này do script test gửi tay.
Chưa có logic ánh xạ symbol hay tính volume.
