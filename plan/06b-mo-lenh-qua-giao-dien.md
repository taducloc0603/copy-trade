# Phase 6b — Mở lệnh Client qua giao diện MT5

## Mục tiêu

Lệnh **MỞ** trên Client mang `DEAL_REASON_CLIENT` thay vì `DEAL_REASON_EXPERT`, bằng cách để
lệnh đi qua đúng kênh của terminal desktop. Đường **ĐÓNG** không đổi một dòng nào.

## Điều kiện đầu vào

Phase 6 xong, luồng mở lệnh tự động chạy ổn định trên demo. Cần **hai** terminal MT5 demo và
một máy Windows chạy được tiến trình Python cạnh terminal Client.

## Vì sao có phase này

`DEAL_REASON` do **máy chủ broker** gán theo *kênh* gửi lệnh. `MqlTradeRequest` không có trường
`reason`, và MQL5 không có API nào đặt được nó. Mọi lệnh do `OrderSend()` trong EA gửi đều là
`EXPERT`. Muốn ra `CLIENT` thì phải đổi kênh, không phải đổi tham số.

---

## Số liệu đã đo trên Connext-Demo

Ba phép đo này đã chạy trước khi thiết kế. Không phỏng đoán chỗ nào.

**Tiền đề đúng.** Lịch sử tài khoản 538217 tách sạch: 13 deal do EA đặt đều `EXPERT (3)` và
magic 770001; 5 deal đặt tay đều `CLIENT (0)` và magic 0.

**Comment sống sót nguyên vẹn.** Comment `'phase5-A'`, `'phase5-restart'` gửi qua `OrderSend` ở
phase 5 còn nguyên trong `DEAL_COMMENT`: không cắt, không bị sàn chèn thêm chữ. Đây là điều
kiện cho phép dùng thẻ tương quan làm đường chính thay vì đường dự phòng.

**Hộp thoại New Order có control Win32 thật.** Dialog `#32770`, 53 control chuẩn, control ID
ổn định:

| Việc | ctrlID | Loại |
|---|---|---|
| Volume | **10333** | Edit (+ spinner 10350) |
| Comment | **1001** | Edit |
| Sell by Market | **10409** | Button |
| Buy by Market | **10408** | Button |
| Symbol | 10331 / 10325 | ComboBox + Edit |
| Fill policy | 10339 | ComboBox |
| Giá hiện tại | 10413 | Static — `'79 623.17 / 79 687.50'` |
| Gợi ý volume tối thiểu | 10881 | Static — `'0.01 BTCUSD.s'` |

Hệ quả lớn: `PostMessage` khả thi ⇒ **không cần desktop tương tác** ⇒ chạy được khi phiên RDP đã
ngắt. Không phải dùng `SendInput`, không phải giữ desktop sống bằng `tscon`.

**Hai cạm bẫy đã phát hiện khi đo:**

1. **ctrlID 10408 và 10409 xuất hiện HAI lần** — bản đang hiện là `'Buy by Market'`/
   `'Sell by Market'`, bản ẩn là `'Buy'`/`'Sell'`. Phải phân biệt bằng `IsWindowVisible` cộng
   text, **không được tra theo ID trần**.
2. Giá hiển thị dùng **dấu chấm thập phân**, nên rủi ro locale ở ô Volume thấp trên máy này.
   Không vì thế mà bỏ bước đọc lại — locale là thuộc tính của máy, không phải của sàn.

**Quan sát phụ, ảnh hưởng phase 8:** deal đóng tay một vị thế do EA mở có `magic = 0`. Magic của
deal phản ánh ai đặt *deal đó*, không phải ai mở vị thế. Đối chiếu phải đọc `POSITION_MAGIC`
từ snapshot, không phải magic của deal.

**Còn một ẩn số.** `WM_SETTEXT` có thật sự cập nhật trạng thái nội bộ của MT5 hay chỉ đổi chữ
hiển thị? Đây là kiểu nửa-thành-công nguy hiểm nhất. Không đo được nếu không đặt lệnh thật, nên
nó là tiêu chí nghiệm thu của mục 6b.5 chứ không phải giả định đầu vào.

---

## Việc cần làm

### 6b.1 Thành phần mới: `clicker`

Tiến trình Python chạy **trên máy có terminal Client**. Nói **đúng giao thức NDJSON/TCP đã có**,
không phát minh giao thức thứ hai.

```
clicker/__main__.py    vòng đời, đọc config, khoá tiến trình đơn
clicker/link.py        client NDJSON: hello / heartbeat / ack
clicker/journal.py     nhật ký command append-only + fsync
clicker/ui/driver.py   giao diện trừu tượng, và hàm commit() có đọc-lại
clicker/ui/win32.py    PostMessage tới control theo ctrlID
clicker/ui/probe.py    canary
```

Dùng lại `bridge.protocol.framing`, `bridge.protocol.messages`, `bridge.clock`,
`bridge.logging_setup`. Chỉ dùng `ctypes` + `user32.dll` — **không thêm phụ thuộc** `pywinauto`
hay `pywin32`.

- `role = "CLICKER"`, token riêng, `agent_id` riêng.
- `account_login` **đọc từ tiêu đề cửa sổ** (`'538217 - Connext-Demo: ...'`). Nhờ vậy kiểm tra
  `ACCOUNT_MISMATCH` sẵn có ở `bridge/protocol/server.py` trở thành hàng rào thật: clicker trỏ
  nhầm terminal thì Bridge từ chối bắt tay. Rẻ, và bắt đúng loại lỗi cấu hình nguy hiểm nhất.
- Chỉ nhận `OPEN_UI`. Không nhận `CLOSE`, `CLOSE_PARTIAL`, `REQUEST_SNAPSHOT`.
- Không đọc database, không sinh event.

Chạy như **Scheduled Task theo phiên đăng nhập**, không phải Windows Service — service chạy ở
session 0, không thấy cửa sổ của phiên người dùng.

### 6b.2 `OPEN_UI` là loại command RIÊNG

Không tái dùng `OPEN`. Lý do là an toàn chứ không phải thẩm mỹ: nếu định tuyến sai mà EA nhận
`OPEN`, nó sẽ **lặng lẽ đặt lệnh `EXPERT`** — đúng thứ phase này tồn tại để làm cho bất khả thi.
Với `OPEN_UI`, EA rơi vào nhánh mặc định của `CBridgeAgent::OnCommand` và trả `rejected`.

Payload `OPEN_UI` **cố ý không có khoá `magic`**, nên `Guard()` của EA cũng chặn — hai lớp
độc lập cho cùng một lỗi.

### 6b.3 Ngữ nghĩa ack trên đường giao diện

Đây là phần dễ làm sai nhất và phải viết ra thành hợp đồng:

| status | Nghĩa CHÍNH XÁC | Bridge làm gì |
|---|---|---|
| `rejected` | **Chứng minh được là chưa bấm nút gửi lệnh** | Trạng thái **duy nhất** được phép retry |
| `failed` | Đã bấm, và đọc được rõ ràng là sàn từ chối | `OPEN_FAILED`, không retry |
| `unknown` | Mọi trường hợp còn lại | `TIMEOUT` + alert CRITICAL, pair **giữ `PENDING_OPEN`** chờ tương quan muộn |
| `ok` | Chuỗi thao tác hoàn tất | **KHÔNG kèm `result_position_id`** |

`ok` nói *"tôi đã bấm"*, không nói *"vị thế nào"*. Việc mở pair do tương quan quyết định, không
do ack quyết định.

Ranh giới giữa `rejected` và `unknown` là **hàm `commit()`**: sau khi điền, đọc ngược
Symbol / Volume / Comment / chiều từ hộp thoại; lệch thì huỷ, đóng hộp thoại, trả `rejected`.
Phải gom vào một hàm duy nhất sao cho **không có đường nào tới nút gửi mà không đi qua nó**.
Toàn bộ chính sách retry dựa vào ranh giới này.

### 6b.4 Xác định `position_id` bằng tương quan

Giao diện không trả về gì. Nhưng **EA vẫn chạy trên terminal Client** và `OnTradeTransaction`
báo mọi deal kèm `POSITION_IDENTIFIER` thật trong 11–21ms (đo ở phase 4).

> **Event của EA là nguồn sự thật. Ack của clicker là thông tin phụ.**
> Thiết kế không được phụ thuộc vào thứ tự đến của hai thứ đó.

**Thẻ:** `tag = "CB" + command_id[-10:]`, 12 ký tự. Suy được từ `command_id` nên không cần cột
riêng để tra ngược. Ngắn để chịu được việc sàn cắt — giới hạn comment của MT5 là 31 ký tự.

**Luồng:**

```
Bridge: pair PENDING_OPEN + command OPEN_UI  (một giao dịch, như phase 6)
   │
   ├─► clicker: giữ chỗ + fsync → điền Symbol/Volume/Comment=tag → ĐỌC LẠI → bấm → ack "ok"
   │
   ├─► EA Client: OnTradeTransaction → event position_opened
   │        kèm position_id thật, magic=0, comment=tag, reason=CLIENT
   │
   └─► Bridge: khớp tag → mark_pair_open(client_position_id=...) → pair OPEN
```

**Thuật toán tương quan**, thay cho nhánh `IGNORED` vô điều kiện hiện tại của `_route()`:

1. `caused_by_command_id` khác NULL → đã tương quan rồi → `IGNORED`. Idempotent với event gửi bù.
2. Tra pair theo `(client_id, position_id)` — đã có → cập nhật volume, `DONE`, **không ghép lại**.
3. Lấy ứng viên: command `OPEN_UI` của clicker thuộc Client này, pair đang `PENDING_OPEN`, còn
   trong `deadline_at + ui_correlate_grace_ms`.
4. **Khớp thẻ**: tag là chuỗi con của `comment` hoặc `order_comment`.
   Đúng một → ghép. Không có → sang bước 5. **Từ hai trở lên → KHÔNG ĐOÁN**, alert CRITICAL,
   event `ERROR`, chờ người.
5. **Suy đoán** — chỉ khi `ui_fallback_match = HEURISTIC`: khớp (symbol, chiều, volume), đúng
   một ứng viên và vị thế chưa thuộc pair nào → ghép kèm WARNING ghi rõ là ghép bằng suy đoán.
   Còn lại → coi là lệnh mở tay, `IGNORED` (FR-12).

**Ghép** là **một giao dịch DB duy nhất**: cập nhật `event.caused_by_command_id` / `pair_id` /
`process_status`, cập nhật `command.status` / `result_position_id` / `executed_volume`, rồi
`mark_pair_open()`. Phải bắt `sqlite3.IntegrityError` từ `idx_pair_client_pos` và biến thành
alert CRITICAL — đó là lưới an toàn cuối cùng chống ghép một vị thế vào hai pair.

### 6b.5 Tính bất biến khi không có giá trị trả về

Lặp lại **đúng kỷ luật** của EA ở phase 5 (`ea/CopyBridgeCommon.mqh`, hàm `ReserveCommand`):

```
đã biết + có ack   → gửi lại ack cũ NGUYÊN VĂN, không bấm gì
đã biết + ack rỗng → trả "unknown", TUYỆT ĐỐI không bấm lại
chưa biết          → ghi dòng giữ chỗ + flush + os.fsync() TRƯỚC phím đầu tiên
```

Nhật ký `clicker_commands.ndjson` append-only, cùng ngữ nghĩa "dòng sau đè dòng trước".

**Bốn lớp bổ sung riêng của đường giao diện:**

1. **Khoá tiến trình đơn.** Hai clicker cùng lái một terminal là thảm hoạ. Không lấy được khoá
   thì thoát ngay, không thử lại.
2. **Một `OPEN_UI` đang bay tại một thời điểm, cho mỗi Client.** Đây là quyết định then chốt:
   nó biến bài toán tương quan mờ thành một hàng đợi có đúng một phần tử, luôn phân giải được.
   Cái giá là thông lượng còn khoảng **một lệnh mỗi 2–4 giây mỗi Client**.
3. **Đọc lại trước khi bấm** (mục 6b.3).
4. **Không retry ngoài `rejected`.** Retry một lệnh mà không chắc đã gửi hay chưa là mở lệnh
   thứ hai với xác suất khác không.

### 6b.6 Canary — không gửi lệnh vào hư không

> **Bridge không bao giờ được gửi `OPEN_UI` cho một clicker chưa chứng minh được nó đang điều
> khiển được giao diện.**

Clicker chạy probe mỗi chu kỳ heartbeat: cửa sổ còn đó, tiêu đề vẫn đúng login. Định kỳ thêm một
**probe khô**: mở hộp thoại, đọc lại các field, bấm ESC — chứng minh toàn tuyến còn sống mà
không đặt lệnh nào. Chỉ chạy khi không có `OPEN_UI` đang bay.

Kết quả đi vào `heartbeat.broker_connected`, **diễn giải lại cho role CLICKER** thành *"tôi điều
khiển được giao diện"*. False → `DEGRADED` (dùng đúng cơ chế sẵn có của phase 3) → luồng mở lệnh
bỏ qua Client đó kèm alert ERROR.

**Không tự rơi về đường EA khi clicker hỏng.** Rơi về đường EA là lặng lẽ vi phạm chính yêu cầu
mà phase này tồn tại để đáp ứng. Thà không copy.

Đây là bài học đã ghi ở `plan/08` mục 8.1 áp dụng lại: thứ nguy hiểm nhất là thành phần **trông
vẫn khoẻ** trong khi đã mất khả năng làm việc.

### 6b.7 Ghi lại `DEAL_REASON` để tự kiểm chứng

Thêm `reason` vào `EventData` và cột `pair.client_open_reason`.

Điều này biến mục tiêu của cả phase thành một **giá trị đo được, ghi vào DB, đối chiếu được**,
thay vì một niềm tin. Pair mở qua giao diện mà `client_open_reason` khác `CLIENT` → alert
CRITICAL. Hệ thống **tự phát hiện** khi thiết kế này ngừng hoạt động, chẳng hạn sau khi MT5 tự
cập nhật build hoặc khi đổi sàn.

---

## Kiểm tra lại phần cũ

- [ ] Toàn bộ test của phase 1–6 vẫn xanh. `open_route = 'EA'` phải chạy **y hệt** hôm nay.
- [ ] Chạy lại nghiệm thu phase 6 với một Client để đường EA cũ không bị hỏng.
- [ ] Test bất biến của phase 5 vẫn xanh.
- [ ] `ruff check .` sạch.

## Kiểm tra phần mới

**Không cần MT5** (mock clicker):

- [ ] Khớp thẻ thành công → pair `OPEN` với đúng `client_position_id`.
- [ ] Hai ứng viên cùng khớp → **KHÔNG ghép**, alert CRITICAL, event `ERROR`.
- [ ] Comment bị xoá, `ui_fallback_match = STRICT` → không ghép, `unknown`, không đoán bừa.
- [ ] Comment bị xoá, `HEURISTIC`, đúng một ứng viên → ghép kèm WARNING.
- [ ] Event `position_opened` gửi hai lần → chỉ ghép một lần.
- [ ] Ack tới **trước** event, và event tới **trước** ack → cả hai thứ tự đều ra kết quả đúng.
- [ ] Ack `unknown` rồi event tới muộn → pair vẫn mở được. Đường giao diện **tự khỏi** ở chỗ mà
      đường EA phải chờ người.
- [ ] Event tới sau `deadline_at + grace` → không ghép, sinh finding cho phase 8.
- [ ] Thông số thực tế lệch payload → alert theo `ui_mismatch_action`.
- [ ] `IntegrityError` của `idx_pair_client_pos` → alert CRITICAL, không phải exception.
- [ ] Chỉ `rejected` được retry; `failed` và `unknown` không bao giờ.
- [ ] Cổng một-lệnh-đang-bay: lệnh thứ hai bị xếp hàng, không gửi song song.
- [ ] EA **không bao giờ** nhận `OPEN_UI`; clicker **không bao giờ** nhận `REQUEST_SNAPSHOT`.
- [ ] Command `PENDING` quá `deadline_at` bị `CANCELLED` thay vì gửi khi agent nối lại.

**Trên demo thật:**

- [ ] Driver giao diện chạy độc lập: **10/10 lần** cho ra deal thật đúng volume, đúng chiều, và
      `DEAL_REASON = CLIENT`. **9/10 là hỏng.** Tiêu chí là deal thật, không phải chữ trên màn hình.
- [ ] Lặp lại với cửa sổ minimized.
- [ ] Lặp lại với phiên RDP đã ngắt.
- [ ] Giết clicker sau khi giữ chỗ nhưng trước khi bấm → khởi động lại → gửi lại cùng
      `command_id` → **không có lệnh thứ hai**, ack `unknown`, alert CRITICAL.
- [ ] Giết clicker sau khi bấm nhưng trước khi ack → event tương quan tới sau vẫn mở được pair.
- [ ] Mở tay một lệnh cùng symbol/chiều/volume trong lúc `OPEN_UI` đang bay → với `STRICT`
      không được ghép nhầm.
- [ ] Canary báo đỏ → Bridge ngừng gửi `OPEN_UI`, alert ERROR, **không** rơi về đường EA.

## Tiêu chí hoàn thành

Master mở tay 5 lệnh trên demo. Client có đúng 5 vị thế, **cả 5 đều `DEAL_REASON = CLIENT`**,
mỗi cặp có `client_position_id` đúng, và bảng `pair` khớp chính xác với lịch sử của cả hai
terminal.

Kèm bảng độ trễ copy mới, đo lại đúng cách phase 6 đã đo, để biết cái giá phải trả.

## Không làm ở phase này

Không đụng vào đường **ĐÓNG** — nó vẫn dùng `OrderSend` của EA và giữ nguyên `RememberCause`.
Không làm đối chiếu (phase 8). Không làm giao diện web (phase 9).
