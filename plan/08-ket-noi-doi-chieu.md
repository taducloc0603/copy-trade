# Phase 8 — Mất kết nối và đối chiếu

## Mục tiêu

Hệ thống sống sót qua mọi kiểu đứt kết nối, không mất sự kiện, và sau khi khôi phục thì phát hiện
được mọi sai lệch giữa sổ sách và thực tế.

## Điều kiện đầu vào

Phase 7 xong. Luồng mở và đóng chạy ổn định trong điều kiện bình thường.

---

## Việc cần làm

### 8.1 Ba loại đứt kết nối

Phải phân biệt được, vì cách xử lý khác hẳn nhau.

| Loại | Biểu hiện | Phát hiện bằng |
|---|---|---|
| Agent mất kết nối với Bridge | Terminal vẫn khớp lệnh, Bridge không nghe thấy gì | Heartbeat timeout |
| Terminal mất kết nối với broker | Heartbeat vẫn đều, nhưng mọi lệnh đều hỏng | `broker_connected = false` |
| Bridge chết | Cả hai agent mồ côi | Agent không kết nối được |

Loại thứ hai nguy hiểm nhất vì hệ thống **trông vẫn khoẻ**. Nếu không có `broker_connected`
thì không phát hiện được. Đây là lý do nó bắt buộc có trong heartbeat từ phase 4.

### 8.2 Hành vi khi mất kết nối (FR-28)

- Tạm dừng gửi command cho agent đang mất kết nối. Command ở lại `PENDING`, không đánh `TIMEOUT`
  vội — phân biệt "chưa gửi được" với "đã gửi mà không có phản hồi".
- Alert theo mức: Master offline là CRITICAL, Client offline là ERROR.
- Client offline: các cặp đang mở vẫn giữ `OPEN`. Không tự đóng Master.
- Master offline: **không** tự đóng Client. Không biết Master đang thế nào thì đóng Client
  là tăng rủi ro (D-13).
- Sự kiện tồn ở phía agent, không mất (đã cài ở phase 4).

### 8.3 Gửi bù sau khi nối lại

Cơ chế đã có ở phase 3 và 4. Phase này kiểm chứng dưới tải và tình huống xấu:

- Agent gửi `hello` kèm `seq` hiện tại. Bridge trả `last_seq`.
- Chênh lệch → agent gửi bù từ `last_seq + 1`, đúng thứ tự.
- Bridge xử lý các event bù **tuần tự theo `seq`**, không song song.
- Event bù phải được đánh dấu là đến muộn, và bộ xử lý phải biết kiểm tra `max_event_age_ms`
  trước khi hành động (không copy lệnh cũ 20 phút).

### 8.4 Đối chiếu (FR-29, FR-33)

`bridge/engine/reconcile.py`. Chạy khi: Bridge khởi động, agent nối lại, nhận event `OUT_BY`,
và định kỳ mỗi `reconcile_interval_sec`.

So **ba nguồn**: bảng `pair` trong DB, snapshot Master, snapshot Client.

Ma trận sai lệch — cài đặt đúng từng dòng:

| Pair trong DB | Master thực | Client thực | `kind` | `severity` | Hành động đề xuất |
|---|---|---|---|---|---|
| OPEN | có | có | — | — | Khớp, không làm gì |
| OPEN | không | có | `MASTER_CLOSED_OFFLINE` | SAFE | Đóng Client |
| OPEN | có | không | `CLIENT_CLOSED_OFFLINE` | DECISION | `ORPHANED`, **không** tự đóng Master |
| OPEN | không | không | `BOTH_CLOSED` | SAFE | Cập nhật sổ sách sang `CLOSED` |
| PENDING_OPEN | có | có | `ACK_LOST` | SAFE | Ghép lại theo magic, chuyển `OPEN` |
| PENDING_OPEN | có | không | `CLIENT_NOT_OPENED` | DECISION | Áp `offline_reopen_policy` |
| Không có | có | — | `UNPAIRED_MASTER` | DECISION | Cảnh báo, **không** copy |
| Không có | — | có, magic bot | `UNPAIRED_CLIENT` | DECISION | Cảnh báo, **không** tự đóng |
| Không có | — | có, không magic | — | — | Lệnh mở tay, bỏ qua (FR-12) |
| bất kỳ | volume lệch tỷ lệ | | `VOLUME_MISMATCH` | DECISION | Cảnh báo |

Quy luật xuyên suốt cột hành động, nâng thành luật cứng của hệ thống:

> **Được tự động ĐÓNG, không được tự động MỞ.** (D-13)
> Đóng làm giảm phơi nhiễm, mở làm tăng. Khi không chắc chuyện gì đã xảy ra,
> hành động an toàn luôn là đóng hoặc dừng lại chờ người.

Chú ý dòng `CLIENT_CLOSED_OFFLINE`: **không cascade dù `can_close_master` đang bật.**
Cascade là phản ứng tức thời với sự kiện vừa xảy ra. Sau vài phút offline, giá đã trôi và
bối cảnh đã khác — đóng Master lúc này là một quyết định giao dịch mới, không phải đồng bộ.
Để người quyết định.

Mọi sai lệch ghi vào `reconcile_finding` với `evidence_json` chứa **cả ba nguồn dữ liệu**,
không chỉ kết luận. Người vận hành phải thấy được bằng chứng để tự phán đoán.

### 8.5 Chính sách mở bù (FR-30)

`offline_reopen_policy` trong `system_config`:

| Giá trị | Hành vi |
|---|---|
| `NONE` (mặc định) | Không mở bù. Ghi finding, chờ người. |
| `IF_STILL_OPEN` | Mở bù nếu vị thế Master còn mở **và** thoả cả hai điều kiện dưới. |
| `CLOSE_MASTER` | Client không nối lại trong thời gian cấu hình thì đóng Master. |

Với `IF_STILL_OPEN`, bắt buộc **hai** điều kiện đồng thời:
1. Tuổi sự kiện chưa vượt `max_event_age_ms`.
2. Giá hiện tại lệch không quá `max_reopen_slippage_points` so với giá Master đã mở.

> Chỉ dùng điều kiện thời gian là không đủ. Vàng có thể nhảy 200 điểm trong 10 giây khi ra tin;
> một sự kiện "mới 8 giây" vẫn có thể khiến bạn hedge ở mức giá vô nghĩa.

Mặc định giữ `NONE`. Chỉ bật khi người vận hành hiểu rõ rủi ro.

### 8.6 Thứ tự khởi động

Cứng, không có đường tắt (D-15):

1. Bridge lên với `run_mode = PAUSED`.
2. Agent kết nối, đẩy `symbol_specs` và `snapshot`.
3. Chạy đối chiếu, tạo `reconcile_finding` với `run_id` mới.
4. Dashboard hiển thị danh sách sai lệch (phase 9).
5. Người vận hành xử lý từng dòng.
6. Người vận hành bấm Start → `RUNNING`.

Không có cơ chế nào tự chuyển sang `RUNNING`. Sau một sự cố, thứ tệ nhất là hệ thống tự hồi sinh
và bắt đầu vào lệnh trong khi chưa ai kịp nhìn màn hình.

### 8.7 API xử lý finding

Các hàm cho phase 9 gọi:
- `accept_finding(id)` — thực hiện hành động đề xuất, ghi `resolution = ACCEPTED`.
- `skip_finding(id, note)` — `resolution = SKIPPED` và **tạo một alert tồn tại**.
  Bỏ qua không có nghĩa là quên.
- `accept_all_safe(run_id)` — chỉ áp dụng cho `severity = SAFE`. Không có hàm nào chấp nhận
  hàng loạt các finding `DECISION`.
- `manual_action(id, action)` — cho các lựa chọn ở finding `DECISION`.

---

## Kiểm tra lại phần cũ

- [ ] Toàn bộ test phase 1–3 xanh.
- [ ] **Chạy lại toàn bộ test phase 6 và phase 7.** Đây là phase dễ phá vỡ logic cũ nhất
      vì nó chạm vào cùng những bảng.
- [ ] Kiểm tra lại đặc biệt: cascade và chống vòng lặp ở 7.5 vẫn đúng sau khi thêm đối chiếu.
      Đối chiếu không được vô tình tạo command trùng với command cascade đang chạy.
- [ ] Test bất biến phase 5 vẫn xanh.

## Kiểm tra phần mới

- [ ] Ngắt Client 2 phút, Master mở 5 lệnh, Client nối lại → với `offline_reopen_policy = NONE`:
      5 finding `CLIENT_NOT_OPENED`, không có lệnh nào được mở tự động.
- [ ] Cùng vậy với `IF_STILL_OPEN` và giá không đổi → mở bù đủ 5.
- [ ] Cùng vậy với giá đã lệch quá `max_reopen_slippage_points` → **không** mở bù, có finding.
- [ ] Ngắt Client, đóng vài lệnh Master, Client nối lại → finding `MASTER_CLOSED_OFFLINE`
      mức SAFE, `accept` xong thì Client đóng đúng các lệnh đó.
- [ ] Ngắt Client, đóng vài lệnh Client, nối lại → finding `CLIENT_CLOSED_OFFLINE` mức DECISION.
      **Master không bị đóng dù `can_close_master = 1`.**
- [ ] Tạo vị thế Master không có trong DB → `UNPAIRED_MASTER`, không có command OPEN nào sinh ra.
- [ ] Tạo vị thế Client mở tay không mang magic bot → **không** xuất hiện trong danh sách finding.
- [ ] Giết Bridge giữa lúc đang gửi command OPEN, khởi động lại → finding `ACK_LOST`,
      ghép lại đúng, không mở lệnh thứ hai.
- [ ] Bridge khởi động luôn ở `PAUSED`, không tự sang `RUNNING` dù không có finding nào.
- [ ] `accept_all_safe` không động tới bất kỳ finding `DECISION` nào.
- [ ] `skip_finding` tạo alert tồn tại, alert đó không tự biến mất.
- [ ] Ngắt terminal khỏi broker (không ngắt khỏi Bridge) → `status = DEGRADED`,
      Bridge ngừng gửi command cho agent đó, alert ERROR.
- [ ] Chạy đối chiếu định kỳ khi mọi thứ khớp → không tạo finding rác.
- [ ] Đối chiếu chạy đồng thời với một cascade đang chờ Master → không tạo command trùng.

## Tiêu chí hoàn thành

Kịch bản hỗn loạn: chạy 30 phút với việc ngẫu nhiên ngắt Bridge, ngắt từng EA, ngắt mạng broker,
đồng thời giao dịch tay trên cả hai terminal. Sau khi mọi thứ ổn định và xử lý hết finding,
bảng `pair` khớp chính xác với vị thế thực trên cả hai terminal, và không có sự kiện nào bị mất.

## Không làm ở phase này

Chưa có giao diện. Xử lý finding ở phase này gọi qua script hoặc test.
