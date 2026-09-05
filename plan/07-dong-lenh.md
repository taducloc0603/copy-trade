# Phase 7 — Luồng đóng lệnh

## Mục tiêu

Đồng bộ đóng lệnh theo Pair ID, hỗ trợ đóng một phần, chống vòng lặp, và cascade có kiểm soát.
Đây là phase phức tạp nhất và cũng là phase dễ mất tiền nhất nếu sai.

## Điều kiện đầu vào

**Phase 6b xong** (không phải phase 6). Luồng mở lệnh chạy ổn định trên demo, và nó nay đi qua
`open_route = 'UI'`: cần clicker chạy và canary xanh thì Client mới mở được lệnh. Nghĩa là mọi
bài kiểm tra của phase này cần **ba** tiến trình, không phải hai: Bridge, hai EA, và clicker.

---

## Việc cần làm

### 7.1 Nguyên tắc nền

**Tra cứu luôn theo `position_id`, không bao giờ theo symbol** (FR-11). Nếu ở bất kỳ đâu trong
code có câu SQL đóng lệnh mà điều kiện là `WHERE symbol = ?`, đó là bug.

**Sự kiện là tín hiệu, không phải nguồn sự thật** (D-14). `volume_after` do EA báo là con số
được dùng. Không tính bằng phép trừ.

**Chống vòng lặp bằng `caused_by_command_id`** (D-08). Event có trường này khác NULL nghĩa là
do chính bot gây ra → cập nhật trạng thái, **không lan truyền tiếp**.

> Đường ĐÓNG **không đổi gì** so với phase 5–6: lệnh đóng vẫn do EA gọi `OrderSend`, nên
> `RememberCause` vẫn chạy và `caused_by_command_id` vẫn do EA gắn. Phase 6b chỉ đổi đường MỞ.
> Riêng event `position_opened` của Client thì `caused_by_command_id` do **Bridge** gắn lúc
> tương quan, không phải EA.

### 7.2 Master đóng hoàn toàn (FR-13)

Đây là chức năng bắt buộc, luôn bật khi bot chạy.

1. Nhận `position_closed` từ Master với `volume_after = 0`.
2. Nếu `caused_by_command_id` khác NULL → đây là hệ quả của cascade đang chạy, xử lý ở 7.5.
3. Tìm **tất cả** pair có `master_position_id` này và `status` chưa kết thúc.
4. Với mỗi pair: chuyển `CLOSING`, tạo command `CLOSE` cho Client tương ứng.
   > **Gửi tới `client_account.agent_id` (EA), không phải `clicker_agent_id`.** Phase 6b thêm
   > agent thứ hai cho mỗi Client, và clicker chỉ nhận `OPEN_UI`. Schema cũng không cho phép
   > loại `CLOSE_UI`, nên định tuyến sai sẽ bị chặn — nhưng viết ra để không ai phải suy luận.
5. Nhận ack thành công → `pair.status = CLOSED`, ghi `close_time_client`, `close_source = MASTER`.
6. Ack `already_closed` → cũng là `CLOSED`, không phải lỗi.
7. Ack thất bại → giữ `CLOSING`, retry theo bảng retcode, hết lượt thì `ORPHANED`
   với `orphan_side = CLIENT`, alert CRITICAL.

Quy tắc này áp dụng bất kể Master đóng do người dùng, do EA khác, do chạm SL/TP, do Stop Out,
hay do đóng một phần — không phụ thuộc lãi hay lỗ.

### 7.3 Đóng một phần (FR-17)

Nhận `position_closed` hoặc `position_changed` từ Master với `volume_after > 0`.

```
tỷ_lệ_đóng      = volume_delta / master_current_volume_trước_đó
client_đóng_thô = pair.client_current_volume × tỷ_lệ_đóng
client_đóng     = làm_tròn_xuống_theo_step(client_đóng_thô)
```

- Dùng `pair.effective_multiplier` đã khoá, **không** dùng hệ số cấu hình hiện tại.
  Người vận hành đổi hệ số giữa chừng không được làm lệch cặp đang chạy (FR-06, D-19).
- Kết quả làm tròn ra 0 → **không gửi command**, ghi WARNING, giữ nguyên `client_current_volume`.
  Phần lệch này tích luỹ và sẽ được đóng ở lần sau hoặc khi đóng hết.
- Cập nhật `master_current_volume` và `client_current_volume` sau khi có ack.
- `pair.status = PARTIALLY_CLOSED`.
- Đóng một phần nhiều lần liên tiếp phải tính đúng — mỗi lần lấy tỷ lệ trên volume **còn lại**,
  không phải volume ban đầu.

### 7.4 Client đóng, công tắc TẮT (FR-23)

Đây là mặc định (D-20).

1. Nhận `position_closed` từ Client, `caused_by_command_id = NULL`.
2. Tìm pair theo `(client_id, client_position_id)`.
3. Không tìm thấy → lệnh mở tay, bỏ qua hoàn toàn (FR-12). Không đóng gì cả.
   > Việc tra cứu này là **toàn bộ** cách phân biệt lệnh của bot với lệnh người dùng mở tay
   > ở phía Client. Không dùng magic: vị thế mở qua giao diện có `magic = 0` (D-07b).

#### 7.4b Hai lỗ hổng của phép tra cứu ở bước 2, và cách bịt

Phép tra `(client_id, client_position_id)` là đúng, nhưng nó có hai chỗ trượt mà phase 6b tạo ra.
Cả hai phải được xử lý tường minh, không để ngầm.

**Lỗ hổng 1 — pair `PENDING_OPEN` chưa có `client_position_id`.**

Trong cửa sổ tương quan (tới `ui_open_deadline_ms` + `ui_correlate_grace_ms`), cột
`client_position_id` còn NULL. Nếu Master đóng đúng lúc đó, bước 3 của **7.2** không có gì để
đóng, và nếu lệnh mở phía Client thực ra đã khớp thì ta để lại một vị thế Client **không có đối
ứng** — đúng thứ hệ thống tồn tại để tránh.

Cách xử lý, không cần thêm cột:

1. Master đóng mà pair đang `PENDING_OPEN` → **không** gửi `CLOSE` (chưa có `position_id`), giữ
   nguyên `PENDING_OPEN`, ghi `close_time_master` và `close_source = 'MASTER'`, alert **CRITICAL**
   mã `MASTER_CLOSED_WHILE_PENDING`.
2. Khi bộ tương quan của phase 6b ghép được vị thế vào cặp đó, nó phải kiểm `close_time_master`.
   Khác NULL nghĩa là Master đã đóng trong lúc chờ → **đóng ngay** vị thế vừa ghép.

`close_time_master` đóng vai "ý định đóng đang chờ địa chỉ". Dùng lại cột sẵn có thay vì thêm
cột mới, và ngữ nghĩa vẫn đúng nguyên văn tên cột.

**Lỗ hổng 2 — cặp được ghép bằng suy đoán.**

Với `ui_fallback_match = HEURISTIC`, bộ tương quan có thể gắn **vị thế người dùng tự mở** vào một
cặp. Khi đó phase này sẽ đóng vị thế đó — bot đóng lệnh của người dùng, không phải lệnh của mình.

Không có cách nào sửa việc ghép nhầm ở đây; nó phải được ngăn ở phase 6b. Việc của phase 7 là
**đừng làm nó im lặng**: trước khi tạo command đóng, kiểm xem cặp này có alert
`UI_CORRELATE_HEURISTIC` không (tra `alert` theo `pair_id`). Có → alert thêm mức **ERROR** mã
`CLOSING_HEURISTIC_PAIR` ghi rõ đang đóng một cặp ghép bằng suy đoán, rồi vẫn đóng.

Vẫn đóng chứ không dừng, vì lựa chọn còn lại — để nguyên — nghĩa là giữ mãi một vị thế mà sổ
sách tin là hedge trong khi Master đã đóng. Nhưng nó phải hiện lên đỏ.

> Đây là lý do `ui_fallback_match` mặc định là `STRICT`. Bật `HEURISTIC` là chấp nhận rủi ro
> này một cách có ý thức, không phải một tuỳ chọn vô hại.
4. `can_close_master = 0` → **không đóng Master**.
5. `pair.status = ORPHANED`, `orphan_side = MASTER`, `close_source = CLIENT`.
6. Alert mức ERROR: Master đang phơi nhiễm bao nhiêu lot trên symbol nào.

### 7.5 Client đóng, công tắc BẬT — cascade (FR-22, D-09, D-10)

**Phần nguy hiểm nhất của hệ thống.** Đọc kỹ trước khi viết.

Chuỗi bắt buộc, không được đi đường tắt:

1. Nhận `position_closed` từ Client A, `caused_by_command_id = NULL`, `volume_after = 0`.
2. `can_close_master` của Client A phải bằng 1. Nếu 0 → xử lý theo 7.4.
3. **Nếu là đóng một phần (`volume_after > 0`) → KHÔNG cascade** (D-11).
   Chỉ cập nhật `client_current_volume`, ghi WARNING vì cặp đã lệch tỷ lệ.
4. Tạo command `CLOSE` cho **Master**. `pair.status = CLOSING`.
5. **Chờ xác nhận Master đã đóng**, tối đa `cascade_wait_master_ms` (mặc định 15000).
6. Master xác nhận đóng → mới tạo command `CLOSE` cho **các Client còn lại** của cùng
   `master_position_id`.
7. Hết timeout mà Master chưa xác nhận → **KHÔNG cascade**. Mọi pair của vị thế Master này
   chuyển `ORPHANED`, alert CRITICAL. Cần người xử lý.

> Vì sao phải chờ: nếu Master từ chối lệnh đóng (requote liên tục, thị trường đóng cửa,
> mất kết nối), mà ta đã đóng B và C rồi thì cả nhóm mất hedge trong khi Master vẫn còn vị thế.
> Đóng trước hỏi sau ở đây là sai.

**Chống vòng lặp:** event `position_closed` từ Master ở bước 6 sẽ mang `caused_by_command_id`
bằng đúng command tạo ở bước 4. Bộ xử lý thấy trường này khác NULL thì biết đây là hệ quả
của cascade đang chạy, cập nhật trạng thái và tiếp tục bước 6 — **không** khởi động lại
quy trình "Master đóng thì Client đóng" từ đầu.

Tương tự, event đóng từ B và C ở bước 6 cũng mang `caused_by_command_id`, nên chúng không
kích hoạt lại cascade ngược lên Master.

### 7.6 Đóng đồng thời hai phía (FR-18)

Master và Client cùng đóng trong vài chục mili giây.

- Mỗi pair chỉ được có **một** command đóng đang chạy tại một thời điểm.
  Kiểm tra `command` có `pair_id` này và `status IN ('PENDING','SENT')` trước khi tạo mới.
- Ack `already_closed` là kết quả bình thường, không tạo alert.
- Trạng thái cuối cùng phải là `CLOSED`, không phải `ERROR`.
- `close_source` ghi bên phát sinh trước.

### 7.7 Close-by (D-12)

Nhận event có `deal_entry = OUT_BY`.

1. Xử lý **như hai sự kiện đóng độc lập**, mỗi cái theo `position_id` riêng của nó.
   Vì tra cứu luôn theo `position_id`, phần này chạy đúng mà không cần code đặc biệt.
2. Ngay sau đó, kích hoạt một lần đối chiếu Master (dùng cơ chế của phase 8; nếu phase 8
   chưa xong thì ở đây chỉ cần gửi `REQUEST_SNAPSHOT` và so sánh thô).
3. Tìm thấy vị thế Master không thuộc pair nào → `master_position.status = UNPAIRED`,
   alert ERROR mã `UNPAIRED_MASTER`. **Không tự copy sang Client.**

> **Không có dữ liệu thực nghiệm, và sẽ không có.** Ghi chép ở `PROGRESS.md` từ phase 4 đã trả
> lời: broker Connext-Demo **không hỗ trợ Close By** — menu chuột phải trên vị thế không có mục
> đó. Nên D-12 phải cài đặt mà không thử được trên sàn hiện tại.
>
> Hệ quả cho cách viết code: phần `OUT_BY` phải chạy đúng **nhờ nguyên tắc chung** (tra cứu theo
> `position_id`, xử lý như hai sự kiện đóng độc lập) chứ không nhờ một nhánh đặc biệt được tinh
> chỉnh theo hành vi quan sát được. Test bằng cách bơm event `OUT_BY` giả qua mock agent. Khi nào
> đổi sang sàn có hỗ trợ Close By thì phải kiểm lại thật.

### 7.8 Ba chế độ dừng

| `run_mode` | Mở lệnh mới | Đồng bộ đóng |
|---|---|---|
| `RUNNING` | Có | Có |
| `PAUSE_NEW_ENTRIES` | Không | **Có** |
| `PAUSED` | Không | Không |
| `EMERGENCY` | Không | Đóng toàn bộ cặp đang quản lý |

`PAUSE_NEW_ENTRIES` vẫn phải đồng bộ đóng. Đây là chế độ dùng khi muốn ngừng vào lệnh mới
nhưng vẫn bảo vệ các cặp đang chạy — tắt cả đồng bộ đóng ở đây là bỏ rơi vị thế đang mở.

`EMERGENCY` đóng theo thứ tự: Client trước, Master sau. Đóng Master trước sẽ kích hoạt
đồng bộ đóng thông thường và làm rối trạng thái.

---

## Kiểm tra lại phần cũ

- [ ] Toàn bộ test phase 1–3 xanh.
- [ ] **Chạy lại toàn bộ 383 test đang có.** Việc thêm logic đóng rất dễ làm hỏng luồng mở.
      Đặc biệt gồm `tests/test_ui_open_flow.py`, `tests/test_clicker.py`,
      `tests/test_ui_driver.py` — đường mở lệnh qua giao diện của phase 6b.
- [ ] Test bất biến phase 5 vẫn xanh.
- [ ] Mở tay 5 lệnh trên demo, xác nhận vẫn copy đúng. Mốc so sánh là **phase 6b**: độ trễ
      trung vị ~604 ms qua đường UI (không phải ~300 ms của đường EA ở phase 6), và **chỉ một
      symbol** — hộp thoại New Order lấy symbol theo chart đang mở.

## Kiểm tra phần mới

- [ ] Master đóng một lệnh → chỉ Client ticket cùng Pair ID bị đóng. Các cặp khác cùng symbol
      không bị động tới. (TEST-03)
- [ ] Ba lệnh XAUUSD cùng lúc, đóng lệnh giữa → chỉ một cặp bị ảnh hưởng. (TEST-07)
- [ ] Client đóng, công tắc TẮT → Master giữ nguyên, pair `ORPHANED`, alert. (TEST-04)
- [ ] Client đóng, công tắc BẬT → Master đóng, không phát sinh vòng lặp. (TEST-05)
      Đếm số command sinh ra: phải đúng 1, không phải 2 hay vô hạn.
- [ ] Master 1.00 / Client 0.50, Master đóng 25% → Client đóng 25% của 0.50 = 0.125,
      chuẩn hoá theo step. (TEST-06)
- [ ] Đóng một phần **ba lần liên tiếp** 20%, 30%, 50% → volume còn lại hai bên luôn đúng tỷ lệ.
- [ ] Đổi `volume_multiplier` giữa chừng rồi đóng một phần → dùng `effective_multiplier` cũ,
      tỷ lệ không đổi.
- [ ] Đóng một phần mà kết quả Client làm tròn ra 0 → không gửi command, WARNING, volume giữ nguyên.
- [ ] Client đóng **một phần** với công tắc BẬT → **không** cascade, chỉ WARNING. (D-11)
- [ ] Cascade với Master không phản hồi: chặn ack Master → sau 15s, toàn bộ pair `ORPHANED`,
      alert CRITICAL, **các Client khác không bị đóng**.
- [ ] Cascade với 3 Client mô phỏng: A đóng → Master đóng → B và C đóng. Đúng thứ tự,
      B và C chỉ đóng **sau khi** Master xác nhận.
- [ ] Master và Client cùng đóng trong 50ms → chỉ một command, kết thúc `CLOSED`, không có ERROR.
- [ ] Bơm event `OUT_BY` cho hai position thuộc hai pair → cả hai pair `CLOSED`.
- [ ] `OUT_BY` để lại vị thế dư → `UNPAIRED_MASTER`, alert, **không có command OPEN nào được tạo**.
- [ ] Đóng một vị thế Client mở tay (không có pair) → không có gì xảy ra với Master.
- [ ] `run_mode = PAUSE_NEW_ENTRIES`: Master đóng → Client vẫn đóng.
- [ ] `run_mode = PAUSED`: Master đóng → Client **không** đóng, event ghi `IGNORED`.
- [ ] `EMERGENCY`: 5 cặp đang mở → đóng hết, Client trước Master sau, không sinh cascade thừa.
- [ ] Kiểm tra không có câu SQL nào đóng lệnh theo symbol: `grep -rn "symbol" bridge/engine/`
      và soi thủ công mọi chỗ liên quan tới đóng lệnh.

## Tiêu chí hoàn thành

Chạy một phiên 60 phút trên hai demo với: mở nhiều lệnh, đóng tay từ cả hai phía, đóng một phần,
chạm SL, bật tắt công tắc giữa chừng. Kết thúc phiên, số vị thế còn lại trên hai terminal khớp
chính xác với bảng `pair`, và không có cặp nào ở trạng thái `ERROR` không giải thích được.

## Không làm ở phase này

Chưa xử lý mất kết nối kéo dài và đối chiếu đầy đủ — đó là phase 8. Chưa có dashboard.
