# Phase 4 — EA phía Master

## Mục tiêu

Viết agent MQL5 gắn vào terminal Master: bắt sự kiện giao dịch, đẩy lên Bridge, không mất
sự kiện nào kể cả khi Bridge chết. Phase này cũng dựng file include dùng chung cho cả EA Client.

## Điều kiện đầu vào

Phase 3 xong. Bridge chạy được và mock agent kết nối được. Cần một terminal MT5 với
**tài khoản demo**.

---

## Việc cần làm

### 4.1 File dùng chung `ea/CopyBridgeCommon.mqh`

Chứa mọi thứ cả hai EA đều cần:

**Socket client.** `SocketCreate`, `SocketConnect`, `SocketSend`, `SocketIsReadable`, `SocketRead`.
- Kết nối lại tự động với backoff: 1s, 2s, 5s, 10s, rồi giữ ở 10s.
- Không bao giờ chặn luồng chính quá vài chục mili giây.

**Xử lý chuỗi UTF-8.** Đây là cái bẫy lớn nhất của MQL5:
```mql5
StringToCharArray(s, arr, 0, -1, CP_UTF8)   // khi gửi
CharArrayToString(arr, 0, len, CP_UTF8)      // khi nhận
```
Bỏ qua `CP_UTF8` thì mọi tên symbol hoặc comment ngoài ASCII sẽ hỏng. Viết hàm bọc và
**chỉ dùng hàm bọc**, không gọi trực tiếp ở nơi khác.

**Bộ đệm nhận.** Gom byte tới khi gặp `\n` rồi mới parse một dòng.

**JSON.** MQL5 không có thư viện JSON. Viết một bộ serialize/parse tối giản đủ dùng cho
schema ở phase 3. Không cần tổng quát, chỉ cần đúng. Escape đầy đủ `"`, `\`, và các ký tự
điều khiển — đặc biệt là newline, vì newline lọt vào chuỗi sẽ phá vỡ khung NDJSON.

**Hàng đợi cục bộ.** Ghi ra file NDJSON append-only trong `MQL5\Files\copybridge\outbox.ndjson`.

> Thứ tự thao tác quan trọng: **ghi file trước, gửi socket sau.** Nếu làm ngược lại, một cú
> crash giữa hai bước sẽ nuốt mất sự kiện mà không ai biết. Ghi trước thì tệ nhất là gửi trùng,
> và trùng thì `event_id` ở Bridge đã lo.

- Mỗi dòng một event kèm `seq`.
- Khi Bridge xác nhận qua `hello_ack.last_seq`, cắt bỏ phần đã được xác nhận.
- `seq` phải bền qua khởi động lại terminal: lưu trong file, đọc lại ở `OnInit`.

**Bộ nhớ command đã thực thi.** Danh sách `command_id` đã xử lý, lưu cả trong mảng và file.
Nhận lại command trùng → trả về ack cũ, **không thực thi lần hai**. Giữ 24 giờ.

**Timer.** `EventSetMillisecondTimer(100)`. Không dựa vào `OnTick` — khi thị trường đóng cửa
hoặc symbol không có tick, `OnTick` không chạy nhưng ta vẫn cần đọc socket và gửi heartbeat.

**Tham số đầu vào EA:** `BridgeHost`, `BridgePort`, `AgentToken`, `AgentRole`, `MagicNumber`.

### 4.2 Bắt sự kiện giao dịch

`OnTradeTransaction()`. **Đây là phần dễ sai nhất của cả dự án.**

MQL5 bắn hàm này **nhiều lần** cho một hành động giao dịch: `ORDER_ADD`, `ORDER_UPDATE`,
`DEAL_ADD`, `HISTORY_ADD`. Xử lý hết thì sẽ copy trùng 3–4 lần.

**Chỉ xử lý `TRADE_TRANSACTION_DEAL_ADD`.** Bỏ qua tất cả loại còn lại.

Sau đó phân nhánh theo `deal.entry`:

| `deal.entry` | Ý nghĩa | Event gửi lên |
|---|---|---|
| `DEAL_ENTRY_IN` | Vị thế mới | `position_opened` |
| `DEAL_ENTRY_OUT` | Đóng toàn phần hoặc một phần | `position_closed` hoặc `position_changed` |
| `DEAL_ENTRY_INOUT` | Chỉ có ở tài khoản Netting | Gửi `order_rejected` kèm ghi chú, tạo alert CRITICAL |
| `DEAL_ENTRY_OUT_BY` | Close-by | `position_closed` với `deal_entry = OUT_BY` |

Phân biệt đóng toàn phần với một phần: sau khi nhận deal, gọi `PositionSelectByTicket()`
với `position_id`. Còn chọn được → một phần, `volume_after` lấy từ vị thế. Không chọn được
→ toàn phần, `volume_after = 0`.

**Luôn gửi `volume_after` thật, không tính bằng phép trừ** (D-14).

Mỗi event mang: `event_id` (sinh tại EA, dạng `EVT-<agent>-<seq>`), `seq`, `position_id`,
`deal_id`, `deal_entry`, `symbol`, `type`, `volume_delta`, `volume_after`, `price`, `magic`,
`ts_agent`, và `caused_by_command_id` nếu deal này phát sinh từ một command của Bridge.

> Cách xác định `caused_by_command_id`: khi EA thực thi một command, nó ghi nhớ
> `(command_id, position_id, thời điểm)`. Deal phát sinh trong vòng vài giây sau đó trên đúng
> position đó thì gắn `command_id` vào. Đây là toàn bộ cơ chế chống vòng lặp (D-08),
> nên phải chắc chắn. Ở phía Master của phase này chỉ cần cài sẵn khung; nó sẽ dùng thật
> khi Master nhận lệnh đóng ở phase 7.

### 4.3 Heartbeat và snapshot

Mỗi giây gửi `heartbeat` gồm:
- `seq` hiện tại
- `broker_connected` = `TerminalInfoInteger(TERMINAL_CONNECTED)` — **bắt buộc**
- `equity`, `margin_level`, `positions_count`, `ts_agent`

Khi nhận command `REQUEST_SNAPSHOT`, duyệt toàn bộ vị thế bằng `PositionsTotal()` /
`PositionGetTicket()` và gửi `snapshot` đầy đủ. Gửi cả vị thế không mang magic của bot —
Bridge cần biết để phân biệt lệnh mở tay (FR-12).

### 4.4 Đẩy symbol specs

Sau `hello_ack`, gửi `symbol_specs` cho toàn bộ symbol trong Market Watch. Với mỗi symbol lấy:
`SYMBOL_DIGITS`, `SYMBOL_POINT`, `SYMBOL_VOLUME_MIN`, `SYMBOL_VOLUME_MAX`, `SYMBOL_VOLUME_STEP`,
`SYMBOL_TRADE_CONTRACT_SIZE`, `SYMBOL_TRADE_TICK_VALUE`, `SYMBOL_TRADE_TICK_SIZE`,
`SYMBOL_FILLING_MODE`, `SYMBOL_TRADE_MODE`.

Gửi lại mỗi khi khởi động, và mỗi 6 giờ (broker có thể đổi thông số).

### 4.5 `ea/CopyBridgeMaster.mq5`

EA mỏng dùng include ở trên, đặt `AgentRole = MASTER`. Ở phase này EA Master **chỉ gửi**,
chưa thực thi command nào ngoài `REQUEST_SNAPSHOT`.

Hiển thị trên chart một dòng trạng thái gọn: đã kết nối Bridge hay chưa, `seq` hiện tại,
số event đang tồn trong hàng đợi. Người dùng cần nhìn thấy EA còn sống mà không phải mở log.

---

## Kiểm tra lại phần cũ

- [ ] Toàn bộ test Python của phase 1–3 vẫn xanh.
- [ ] Mock agent vẫn hoạt động — EA thật và mock agent phải cùng nói được một giao thức.
      Nếu phải sửa giao thức để EA chạy được, **sửa cả mock agent và test phase 3**.
- [ ] Chạy lại kịch bản 1000 event của phase 3.

## Kiểm tra phần mới

Trên tài khoản **demo**:

- [ ] EA kết nối được Bridge, `hello_ack` nhận đúng, dashboard log thấy agent ONLINE.
- [ ] Mở tay một lệnh BUY → Bridge nhận **đúng một** event `position_opened`. Không phải 2, không phải 4.
- [ ] Đóng tay lệnh đó → **đúng một** event `position_closed` với `volume_after = 0`.
- [ ] Đóng một phần 30% → một event với `volume_after` bằng phần còn lại thật.
- [ ] Mở lệnh có SL, để lệnh chạm SL → vẫn nhận đúng một event đóng.
- [ ] Tắt Bridge, mở và đóng vài lệnh, bật Bridge lại → toàn bộ event được gửi bù, đúng thứ tự,
      không thiếu, không trùng.
- [ ] Tắt EA giữa chừng rồi bật lại → `seq` tiếp tục từ giá trị cũ, không reset về 0.
- [ ] Ngắt mạng terminal khỏi broker → heartbeat có `broker_connected = false`, Bridge chuyển DEGRADED.
- [ ] Đẩy symbol có ký tự ngoài ASCII trong tên hoặc comment → Bridge nhận đúng, không hỏng mã.
- [ ] Nếu tài khoản demo cho phép: mở BUY và SELL cùng symbol rồi dùng Close By
      → nhận event có `deal_entry = OUT_BY`. Ghi lại chính xác hành vi của broker
      (đóng cả hai và tạo vị thế mới, hay đóng một phần vị thế lớn) vào `PROGRESS.md`.
      **Thông tin này cần cho phase 7.**

## Tiêu chí hoàn thành

Giao dịch tay 30 phút trên demo với đủ loại thao tác, và số event Bridge nhận được khớp
chính xác với lịch sử giao dịch trong terminal — không thiếu một cái nào, không thừa một cái nào.

## Không làm ở phase này

EA Master chưa thực thi lệnh mở hay đóng. Chưa có logic copy. Bridge vẫn chưa tạo pair.
