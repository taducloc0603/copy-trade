# Phase 3 — Giao thức và TCP server

## Mục tiêu

Bridge nhận kết nối, xác thực agent, trao đổi message NDJSON, theo dõi heartbeat và phát hiện
lỗ hổng chuỗi sự kiện. Cuối phase này Bridge chưa hiểu gì về giao dịch — nó chỉ là một
đường ống đáng tin cậy.

## Điều kiện đầu vào

Phase 2 xong. Toàn bộ test database xanh.

---

## Việc cần làm

### 3.1 Khung message

NDJSON trên TCP: mỗi message là một dòng JSON kết thúc bằng `\n` (D-02).

An toàn về cú pháp vì JSON hợp lệ luôn escape newline thành hai ký tự `\` và `n`,
nên byte `0x0A` thô không bao giờ xuất hiện giữa một message.

Yêu cầu cài đặt:
- Bộ đệm nhận phải chịu được message bị cắt thành nhiều mảnh tuỳ ý.
- Giới hạn độ dài một dòng (đề xuất 256 KB). Vượt thì đóng kết nối và ghi ERROR —
  không để một agent lỗi làm cạn bộ nhớ.
- Encode/decode UTF-8. Dòng không parse được thì bỏ qua, ghi ERROR kèm 200 ký tự đầu, không sập.

### 3.2 Schema message (pydantic v2)

`bridge/protocol/messages.py`. Envelope chung: `v` (số phiên bản, hiện tại 1), `kind`, `ts`.

**Agent → Bridge**

| kind | Trường chính |
|---|---|
| `hello` | `token`, `role`, `account_login`, `broker_server`, `terminal_build`, `magic`, `seq` (seq hiện tại của agent) |
| `symbol_specs` | `symbols[]` với đầy đủ trường của bảng `symbol_spec` |
| `event` | `id` (event_id), `seq`, `type`, `caused_by_command_id`, `data{}` |
| `snapshot` | `positions[]`: position_id, ticket, symbol, type, volume, price_open, magic |
| `ack` | `command_id`, `status`, `retcode`, `retmsg`, `executed_volume`, `result_position_id`, `attempt` |
| `heartbeat` | `seq`, `broker_connected`, `equity`, `margin_level`, `positions_count`, `ts_agent` |

**Bridge → Agent**

| kind | Trường chính |
|---|---|
| `hello_ack` | `agent_id`, `last_seq` (seq cao nhất Bridge đã nhận), `config{}` |
| `command` | `command_id`, `type`, `pair_id`, `payload{}`, `deadline_ts` |
| `config` | tham số nóng: `max_deviation_points`, `max_spread_points`, `heartbeat_interval_ms` |
| `resend` | `from_seq` |

Các loại `event.type`: `position_opened`, `position_closed`, `position_changed`, `order_rejected`.

Với `position_closed` và `position_changed`, bắt buộc có `volume_after` (D-14).
Bridge **không** tự tính bằng phép trừ.

Với mọi event sinh từ deal, bắt buộc có `deal_entry` nhận một trong `IN`, `OUT`, `INOUT`, `OUT_BY`.

Mọi message không hợp lệ schema → trả về một message `error` và ghi WARNING, không đóng kết nối
(trừ trường hợp `hello` sai, xem dưới).

### 3.3 TCP server

`bridge/protocol/server.py`, dùng `asyncio.start_server`.

Luồng bắt tay:
1. Agent kết nối. Bridge cho tối đa 5 giây để gửi `hello`. Quá hạn → đóng.
2. Xác thực `token` bằng cách so hash với `agent.token_hash`. Sai → gửi `error`, đóng, ghi WARNING
   kèm địa chỉ IP. **Không ghi token vào log.**
3. Kiểm tra `account_login` khớp với bản ghi agent. Lệch → từ chối. Một token chỉ dùng cho
   đúng một tài khoản MT5.
4. Nếu `agent_id` đó đã có kết nối đang mở: đóng kết nối cũ, nhận kết nối mới. Terminal khởi động lại
   là chuyện thường; kết nối cũ chỉ là xác chết.
5. Gửi `hello_ack` kèm `last_seq` đã lưu trong DB.
6. Cập nhật `agent.status = ONLINE`, `last_seen_at`.

Sau bắt tay:
- Nhận `symbol_specs` và ghi đè bảng `symbol_spec` cho agent đó.
- Yêu cầu `snapshot` ngay (gửi command `REQUEST_SNAPSHOT`). Phase này chỉ lưu lại, chưa xử lý.

### 3.4 Chuỗi sự kiện và gửi bù

- Với mỗi `event`, kiểm tra `seq`. Nếu `seq > last_seq + 1` → có lỗ hổng.
  Gửi `resend` với `from_seq = last_seq + 1` và ghi WARNING.
- Nếu `seq <= last_seq` → event đã có, bỏ qua nhưng vẫn phải trả về ack xử lý cũ.
- Ghi mọi event vào DB **trước** khi làm bất cứ việc gì khác với nó.
- `last_seq` chỉ tăng khi event đã ghi thành công vào DB.

### 3.5 Heartbeat và trạng thái agent

- Agent gửi heartbeat mỗi `heartbeat_interval_ms` (mặc định 1000).
- Bridge có một task nền quét: agent quá `heartbeat_timeout_ms` (mặc định 5000) không có tin
  → `status = OFFLINE`, tạo alert mức WARNING.
- Nếu heartbeat có `broker_connected = false` → `status = DEGRADED`, alert mức ERROR.
  **Đây là trạng thái nguy hiểm nhất** vì nhìn từ ngoài hệ thống có vẻ vẫn khoẻ.
- Đo `latency_ms` bằng chênh lệch giữa `ts_agent` và thời điểm nhận, có tính tới lệch đồng hồ.
  Ghi nhận, không tin tuyệt đối.

### 3.6 Gửi command

`bridge/protocol/dispatcher.py`:
- Ghi command vào bảng `command` với `status = PENDING` **trước**, rồi mới gửi qua socket,
  rồi cập nhật `SENT`. Không bao giờ gửi một command chưa có trong DB.
- Agent offline → command ở lại `PENDING`, gửi khi nối lại.
- Task nền quét command `SENT` quá `deadline_at` mà chưa có ack → chuyển `TIMEOUT`, tạo alert.

### 3.7 Mock agent

`tests/mock_agent.py`. Đây là công cụ dùng lại cho mọi phase sau, đầu tư cho tử tế.

Một TCP client Python giả lập EA, hỗ trợ:
- Bắt tay đúng giao thức, cấu hình được token và role.
- Bơm event theo kịch bản, kiểm soát được `seq` (kể cả cố tình tạo lỗ hổng hoặc gửi trùng).
- Nhận command và trả ack với `retcode` chỉ định — bao gồm cả các mã lỗi.
- Mô phỏng ngắt kết nối đột ngột, kết nối lại, gửi bù.
- Giữ một danh sách vị thế trong bộ nhớ để trả lời `snapshot`.

---

## Kiểm tra lại phần cũ

- [ ] Toàn bộ test phase 1 và 2 vẫn xanh.
- [ ] Các ràng buộc DB vẫn được tôn trọng: thử ghi hai event trùng `event_id` qua đường mạng,
      DB phải chỉ có một bản ghi.
- [ ] `ruff check .` sạch.

## Kiểm tra phần mới

- [ ] Bắt tay thành công với token đúng.
- [ ] Token sai → bị từ chối, không có dòng log nào chứa token.
- [ ] `account_login` lệch → bị từ chối.
- [ ] Không gửi `hello` trong 5 giây → bị đóng kết nối.
- [ ] Kết nối thứ hai cùng `agent_id` → kết nối cũ bị đóng, kết nối mới hoạt động.
- [ ] Một message JSON bị cắt làm 3 mảnh TCP → vẫn ghép lại và parse đúng.
- [ ] Hai message dính trong một gói TCP → tách đúng thành hai.
- [ ] Dòng rác không phải JSON → ghi ERROR, kết nối vẫn sống, message kế tiếp vẫn xử lý được.
- [ ] Dòng dài hơn giới hạn → đóng kết nối, không tăng bộ nhớ vô hạn.
- [ ] Gửi event với `seq` nhảy cóc → Bridge phát `resend` đúng `from_seq`.
- [ ] Gửi lại event có `seq` cũ → không tạo bản ghi thứ hai.
- [ ] Agent ngừng heartbeat 6 giây → `status = OFFLINE`, có alert.
- [ ] Heartbeat với `broker_connected = false` → `status = DEGRADED`, có alert ERROR.
- [ ] Command gửi cho agent offline → nằm `PENDING`, agent nối lại thì được gửi.
- [ ] Command quá `deadline_at` không có ack → `TIMEOUT` và có alert.
- [ ] Event thiếu `volume_after` trên `position_closed` → bị schema từ chối.

## Tiêu chí hoàn thành

Mock agent kết nối, bơm 1000 event với vài lần ngắt kết nối chen giữa, và DB có đúng
1000 bản ghi event với `seq` liên tục không lỗ hổng.

## Không làm ở phase này

Không xử lý ý nghĩa nghiệp vụ của event. Không tính volume. Không tạo pair.
Bridge ở phase này chỉ là đường ống.
