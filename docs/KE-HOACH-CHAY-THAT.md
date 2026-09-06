# Kế hoạch chuyển sang chạy thật — kiến trúc một VPS

*Lập ngày 2026-09-06, sau khi B-09 đóng. Trạng thái mã nguồn: 518 test xanh, 3 test tải, `ruff`
sạch, `data/bridge.db` ở schema version 3.*

Tài liệu này chỉ có một việc: liệt kê **thứ còn thiếu** giữa hiện trạng và lúc đưa tiền thật vào,
theo đúng thứ tự nên làm. Nó không lặp lại `RUNBOOK.md` — cách chạy nằm ở đó.

---

## Kết luận hiện tại: **chưa GO**

Không còn lỗi nào đã biết trong code. Cái còn thiếu là **bằng chứng**: bốn cơ chế quan trọng chưa
từng được quan sát trong điều kiện thật, và một trong số đó (B-08) là điều kiện vận hành bình
thường của VPS chứ không phải tình huống hiếm.

---

## Giai đoạn 1 — Đóng nốt phần làm được trên máy hiện tại

Làm xong giai đoạn này rồi mới dựng VPS; sửa trên laptop rẻ hơn sửa trên VPS.

### 1.1 Nghiệm thu B-09 đầu-cuối *(cần bạn: ~2 phút)*

Mã đã viết và **biên dịch sạch**, nhưng terminal vẫn chạy bản EA cũ và cơ chế chưa từng chạy thật.

1. Gỡ EA khỏi chart rồi gắn lại trên **cả hai** terminal (đổi khung thời gian **không** đủ — MT5
   không đọc lại `.ex5`; xem `RUNBOOK.md` mục 2).
2. Tôi bật stack, xác nhận `agent.trade_allowed = 1` cho cả hai EA.
3. **Tắt** nút Algo Trading trên terminal Client → phải thấy alert `TRADE_NOT_ALLOWED` (ERROR),
   và lệnh Master tiếp theo **không** sinh `OPEN_UI`, kèm `CLIENT_TRADE_NOT_ALLOWED`.
4. Bật lại → `TRADE_ALLOWED_AGAIN`, copy chạy lại bình thường.

Chi phí: ~2 lệnh demo.

### 1.2 Gửi được một tin Telegram thật *(cần bạn: bot token + chat id)*

Đường gửi có test với sender giả, nhưng **chưa tin nào từng tới điện thoại**. Trên VPS đây là
kênh duy nhất báo cho bạn khi có sự cố — nếu nó không chạy thì mọi alert ERROR/CRITICAL ở các
phase trước đều vô nghĩa.

Cần: tạo bot qua `@BotFather`, lấy `telegram_token` và `telegram_chat_id`, điền vào `config.toml`.
Sau đó ép một alert CRITICAL và xác nhận tin tới nơi trong vài giây.

### 1.3 Chạy lại toàn bộ nghiệm thu sau khi EA đổi

EA Client đã bị **chuyển 190 dòng** sang file dùng chung ở phase 11, và EA Master có thêm khả
năng đóng lệnh. Cả hai đều nằm trên đường đi của mọi lệnh thật.

Chạy lại tối thiểu: TEST-02 (copy khác chiều), TEST-03 (đóng đúng cặp), TEST-06 (đóng một phần),
TEST-21 (đóng khẩn cấp), TEST-23 (`kiem-reason`). Chi phí: ~6 lệnh demo.

---

## Giai đoạn 2 — Dựng VPS và đo những thứ chỉ VPS mới đo được

### 2.1 B-08 — Phiên RDP đã ngắt **(chặn)**

Rủi ro lớn nhất còn lại. Toàn bộ đường mở lệnh dựa vào clicker `PostMessage`; lập luận "không cần
desktop tương tác" có từ phase 6b và **chưa bao giờ được đo**. Bản gần đúng duy nhất là 5/5 probe
với cửa sổ minimized.

Cách đo: RDP vào VPS, chạy stack, đặt một lệnh (phải copy được), rồi **ngắt phiên RDP bằng cách
đóng cửa sổ** (không Sign out), đợi vài phút, đặt lệnh thứ hai, rồi RDP vào lại đọc database.

Phân biệt hai chế độ hỏng, vì chúng khác nhau hoàn toàn:

| Quan sát | Nghĩa |
|---|---|
| Canary đỏ, không có `OPEN_UI` | **An toàn** — Bridge tự dừng copy, D-25 làm đúng việc |
| Canary xanh nhưng không có vị thế Client | **Nguy hiểm** — hệ thống tưởng mình đang copy mà không |

Nếu rơi vào ô thứ hai thì **dừng hẳn kế hoạch chạy thật** cho tới khi giải xong.

### 2.2 B-02 / TEST-19 — Mất điện đột ngột

Trên VPS việc này **làm được** (khác laptop): dùng nút *force stop* / *hard reset* của nhà cung
cấp, đúng lúc có lệnh đang bay. Sau khi bật lại: không mất event, và bộ đối chiếu bắt đúng sai
lệch. Đây là lý do `synchronous = FULL` tồn tại, và tới giờ nó vẫn chỉ là *cấu hình đúng* chứ
chưa phải *quan sát*.

### 2.3 B-03 — Chạy 24 giờ liên tục

Rò rỉ bộ nhớ và tốc độ tăng DB chỉ lộ sau nhiều giờ. Ghi lại RAM của bốn tiến trình lúc bắt đầu
và lúc kết thúc, cùng kích thước `bridge.db` và file WAL.

### 2.4 Cấu hình máy và tự khởi động

- `host = "127.0.0.1"` nếu không cần xem dashboard từ xa (xem `RUNBOOK.md` mục 5b).
- Autologon, tắt sleep/hibernate, **tắt khoá màn hình tự động**.
- Bridge chạy Windows Service; clicker chạy **Scheduled Task theo phiên đăng nhập**.
- Kiểm: giết tiến trình Bridge → tự bật lại, và bật lại ở `PAUSED`.
- `bao-tri` chạy hằng ngày bằng Scheduled Task.

---

## Giai đoạn 3 — Điều kiện không phải kỹ thuật

Ba mục này không có test nào chứng minh được, và bỏ qua chúng thì phần kỹ thuật ở trên vô nghĩa.

1. **Đọc điều khoản của cả hai broker.** Hai tài khoản, vị thế ngược chiều, cùng symbol, cách
   nhau dưới một giây, **cùng một IP** — nhiều broker cấm hoặc huỷ lợi nhuận từ mô hình này. Rủi
   ro này không hiện ra trong bất kỳ log nào cho tới lúc tài khoản bị xử lý.
2. **Chạy ổn định trên demo ít nhất một tuần liên tục** sau khi xong giai đoạn 1 và 2.
3. **Bấm thử nút dừng khẩn cấp một lần trên demo**, để biết cảm giác trước khi cần dùng thật.

---

## Bắt đầu bằng cấu hình nhỏ nhất

Khi đã qua cả ba giai đoạn:

- **Một symbol duy nhất** — đây không phải lựa chọn thận trọng mà là **giới hạn kỹ thuật hiện
  tại** (B-01): hộp thoại New Order lấy symbol theo chart đang mở, và đổi symbol qua ComboBox
  chưa đo lần nào.
- **Volume nhỏ nhất sàn cho phép**, mở rộng sau khi quan sát vài chục lệnh.
- `can_close_master = 0` (mặc định) — cascade chưa từng chạy trên demo (B-06).
- Kiểm `python -m bridge.admin kiem-reason` mỗi ngày trong tuần đầu.

---

## Những gì đã có bằng chứng, để khỏi kiểm lại

| Cơ chế | Bằng chứng |
|---|---|
| Không mở trùng lệnh | Khởi động lại EA rồi gửi lại cùng `command_id` → không có lệnh thứ hai |
| Đóng đúng cặp, không theo symbol | Cặp đối chứng cùng symbol không bị đụng; có test cấu trúc khoá |
| `DEAL_REASON_CLIENT` cho mọi vị thế bot | `kiem-reason` → 27/27 trên dữ liệu thật |
| Nút dừng khẩn cấp đóng **cả hai** phía | 2026-09-06: `master_position` OPEN = 0, hai lệnh đóng Master `ACK_OK`, Client trước Master sau, 1.125 ms |
| Chống vòng lặp đóng | Event đóng phía Client bị `IGNORED` với lý do `Do bot gay ra` |
| Migration nâng cấp được | version 1 → 2 → 3 trên database có dữ liệu thật, cấu trúc khớp DB tạo mới |
| Dashboard có xác thực | Mật khẩu sai → 401; không cookie → 401 trên `/api/emergency` |
| Sao lưu khôi phục được | `VACUUM INTO` + tự kiểm chứng, chạy trong `bao-tri` hằng ngày |
