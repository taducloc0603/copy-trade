# Bot Copy MT5 — Kế hoạch triển khai

Tài liệu này là điểm vào. Đọc hết file này trước khi bắt đầu bất kỳ phase nào.

---

## 1. Hệ thống làm gì

Đồng bộ lệnh giữa hai tài khoản MetaTrader 5 để tạo và quản lý các vị thế hedge theo cặp.

- Master mở lệnh → Client mở lệnh tương ứng. Chiều mở lệnh **chỉ đi một chiều** Master → Client.
- Client có thể cùng chiều (BUY→BUY) hoặc ngược chiều (BUY→SELL) tuỳ cấu hình.
- `Client Volume = Master Volume × Hệ số`, sau đó chuẩn hoá theo quy định của sàn Client.
- Master đóng → Client luôn đóng đúng cặp.
- Client đóng → Master đóng hay không tuỳ công tắc, mặc định TẮT.
- Mỗi cặp lệnh có Pair ID riêng. Không bao giờ đóng lệnh dựa trên tên symbol.

## 2. Phạm vi MVP

- 1 Master, 1 Client. Nhưng **toàn bộ mô hình dữ liệu và routing phải viết cho N Client ngay từ đầu**.
- Chỉ tài khoản MT5 chế độ **Hedging**. Không hỗ trợ Netting.
- Chỉ Market Order BUY/SELL. Không copy Pending Order, không copy giá SL/TP.
  Khi một bên bị đóng bởi SL/TP, bot đồng bộ theo sự kiện đóng thực tế.
- Nhiều symbol đồng thời, có bảng ánh xạ symbol giữa hai sàn.
  **Chưa đạt kể từ phase 6b:** lệnh MỞ phía Client đi qua hộp thoại New Order, mà hộp
  thoại lấy symbol theo chart đang mở. Driver chỉ *kiểm tra* symbol chứ không đổi (đổi
  qua ComboBox chưa được đo), nên mỗi terminal Client hiện chỉ copy được **một symbol**.
  Đây là món nợ phải trả trước phase 10, không phải phạm vi đã bị cắt.
- Chạy trên Windows.

## 3. Kiến trúc

```
MT5 Master + EA  ──TCP/NDJSON──┐
                               ├──►  BRIDGE (Python)  ──►  SQLite
MT5 Client + EA  ──TCP/NDJSON──┤         │
                               │         └──►  Dashboard web (FastAPI + WebSocket)
clicker (Python) ──TCP/NDJSON──┘
   │
   └── PostMessage ──► MT5 Client   (chỉ lệnh MỞ, xem plan/06b)
```

**Bốn vai trò tách bạch:**

| Vai trò | Là gì | Được làm gì |
|---|---|---|
| EA (MQL5) | Agent mỏng gắn vào chart mỗi terminal | Bắt sự kiện, thực thi lệnh, gửi heartbeat |
| Bridge (Python) | Tiến trình độc lập, nguồn sự thật duy nhất | Toàn bộ logic nghiệp vụ, ghi DB |
| Dashboard | Web phục vụ bởi chính Bridge | Hiển thị và điều khiển |
| Clicker | Tiến trình Python cạnh terminal Client | **Chỉ** mở lệnh qua giao diện MT5 (D-21) |

**EA không chứa logic nghiệp vụ.** EA không tính volume, không ánh xạ symbol, không biết Pair ID
là gì ngoài việc echo lại, không biết database tồn tại. Ngoại lệ duy nhất: EA tự chọn filling mode
theo `SYMBOL_FILLING_MODE` vì đó là chi tiết kỹ thuật của broker.

**Các EA không bao giờ nói chuyện trực tiếp với nhau.** Mọi thứ đi qua Bridge.

**Kết nối:** TCP socket, một giao thức duy nhất cho cả hai kịch bản.
Cùng VPS thì `127.0.0.1:8787`. Khác VPS thì địa chỉ Tailscale `100.x.y.z:8787`.
Không dùng shared memory, không dùng DLL, không dùng WebRequest.

## 4. Các quyết định đã chốt

Những điều dưới đây đã được quyết định. Không tự ý đổi. Nếu phát hiện một quyết định
không khả thi khi lập trình, dừng lại và báo cáo thay vì tự chọn hướng khác.

| # | Quyết định |
|---|---|
| D-01 | EA mỏng bằng MQL5 + Bridge bằng Python. Logic nằm hết ở Bridge. |
| D-02 | Truyền tin bằng NDJSON trên TCP. Mỗi message một dòng kết thúc bằng `\n`. |
| D-03 | Bridge là TCP server, EA là TCP client. MQL5 không listen được. |
| D-04 | Database là SQLite chạy cục bộ trên máy Bridge, bật WAL, `synchronous=FULL`. |
| D-05 | Không dùng cloud database. Xem từ xa bằng cách vào dashboard qua Tailscale. |
| D-06 | Khoá định danh vị thế là `POSITION_IDENTIFIER`, không phải ticket. |
| D-07 | *(bản 1, đã thay bằng D-07b)* Lệnh do bot mở phải mang magic number cố định. Không dựa vào trường comment. |
| D-07b | Trên **Master**, lệnh của bot mang magic cố định. Trên **Client**, lệnh MỞ đi qua giao diện nên `magic = 0` và không đặt được. Định danh "lệnh của bot" phía Client là **sự tồn tại của `(client_id, client_position_id)` trong bảng `pair`**. Comment chỉ là thẻ tương quan tạm thời, dùng một lần trong cửa sổ chờ khớp lệnh, không bao giờ là nguồn sự thật lâu dài. |
| D-08 | Chống vòng lặp đóng bằng `caused_by_command_id` trên sự kiện, không bằng cờ trạng thái. |
| D-09 | Client đóng hoàn toàn (cờ bật) → đóng Master → **chờ xác nhận** → mới cascade sang các Client khác. |
| D-10 | Timeout chờ Master xác nhận trước khi cascade: cấu hình được, mặc định 15000ms. Hết hạn thì KHÔNG cascade. |
| D-11 | Client đóng **một phần** thì KHÔNG cascade. Chỉ cascade khi đóng hoàn toàn. |
| D-12 | Close-by (`DEAL_ENTRY_OUT_BY`): đóng đúng 2 pair theo position_id, chạy đối chiếu ngay, phần dư thì cảnh báo và KHÔNG tự copy. |
| D-13 | Luật cứng: hệ thống được tự động **ĐÓNG**, không được tự động **MỞ**. Mở bù chỉ khi có người bấm. |
| D-14 | Sự kiện chỉ là tín hiệu kích hoạt. Trạng thái sau sự kiện (`volume_after`) do EA báo, Bridge không tự suy diễn bằng phép trừ. |
| D-15 | Bridge khởi động ở chế độ `PAUSED`. Không có đường tự động chuyển sang `RUNNING`. |
| D-16 | Enum trong DB, log và message dùng tiếng Anh không dấu. Tiếng Việt chỉ ở tầng hiển thị, qua một file nhãn duy nhất. |
| D-17 | Giữ 30 ngày dữ liệu event/command trong SQLite nóng, cũ hơn thì xuất sang file archive. Không bao giờ xoá `pair` và `master_position` theo thời gian. |
| D-18 | Làm tròn volume mặc định là làm tròn **xuống**. Nếu kết quả dưới mức tối thiểu của sàn thì **bỏ qua lệnh và cảnh báo**, không tự nâng volume. |
| D-19 | `effective_multiplier` (tỷ lệ thực tế sau làm tròn) được khoá tại thời điểm mở cặp và dùng cho mọi phép tính đóng một phần về sau. |
| D-20 | Cờ `can_close_master` đặt theo từng Client, mặc định TẮT. |
| D-21 | Lệnh **MỞ** phía Client đi qua giao diện MT5 để mang `DEAL_REASON_CLIENT`. Đường **ĐÓNG** vẫn dùng `OrderSend` của EA. |
| D-22 | Kênh mở lệnh là tiến trình riêng `clicker`, cùng giao thức NDJSON/TCP, role `CLICKER`, token riêng. Loại command riêng `OPEN_UI` để EA không thể lặng lẽ đặt lệnh `EXPERT` khi định tuyến sai. |
| D-23 | `position_id` của vị thế Client xác định bằng **tương quan tại Bridge** giữa `OPEN_UI` và event `position_opened` của EA. Event của EA là nguồn sự thật, ack của clicker là thông tin phụ. Nhiều ứng viên thì KHÔNG đoán. |
| D-24 | Trên đường giao diện, **chỉ `rejected`** (chứng minh được là chưa bấm nút gửi) mới được retry. `failed` và `unknown` không bao giờ retry tự động. |
| D-25 | Không gửi `OPEN_UI` cho clicker chưa chứng minh được nó điều khiển được giao diện. Clicker `DEGRADED` thì **không copy**, không tự rơi về đường EA. |
| D-26 | Mở lệnh qua **hộp thoại New Order**, không dùng One Click Trading. OCT không có ô Comment, mà thẻ trong comment là cơ chế tương quan duy nhất (D-07b, D-23). Ô volume phải ghi bằng `WM_CHAR`, không phải `WM_SETTEXT`. |

## 5. Thuật ngữ

- **Master** — tài khoản phát sinh lệnh gốc.
- **Client** — tài khoản nhận lệnh copy.
- **Agent** — tiến trình EA gắn vào một terminal MT5.
- **Bridge** — tiến trình Python trung tâm.
- **Pair** — liên kết giữa một vị thế Master và một vị thế Client. Một vị thế Master sinh ra N pair (N = số Client).
- **Event** — sự kiện giao dịch do agent báo lên.
- **Command** — yêu cầu Bridge gửi xuống agent để thực thi.
- **Cascade** — chuỗi đóng lan truyền: Client A đóng → Master đóng → các Client khác đóng.
- **Reconciliation** — đối chiếu giữa DB, vị thế thực trên Master và vị thế thực trên Client.
- **Orphaned** — cặp lệnh mà một bên còn vị thế nhưng bên kia không còn.
- **Clicker** — tiến trình Python cạnh terminal Client, mở lệnh bằng cách điều khiển giao diện
  MT5 để lệnh mang `DEAL_REASON_CLIENT`.
- **Thẻ tương quan** — chuỗi ngắn Bridge sinh cho mỗi lệnh mở qua giao diện, clicker gõ vào ô
  Comment, EA đọc lại và báo lên để Bridge ghép được vị thế với cặp lệnh.

## 6. Cách dùng bộ plan này

Các file được đánh số theo thứ tự thực hiện. **Làm tuần tự, không nhảy phase.**

```
00-README.md                 file này
01-khoi-tao.md               dựng khung dự án, viết tài liệu nền
02-database.md               schema và tầng truy cập dữ liệu
03-giao-thuc-bridge.md       NDJSON, TCP server, xác thực, heartbeat
04-ea-master.md              EA phía Master
05-ea-client.md              EA phía Client, thực thi lệnh
06-mo-lenh.md                luồng mở lệnh đầu-cuối
06b-mo-lenh-qua-giao-dien.md mở lệnh Client qua giao diện MT5 (D-21…D-26)
07-dong-lenh.md              luồng đóng lệnh, cascade, chống vòng lặp
08-ket-noi-doi-chieu.md      mất kết nối, gửi bù, reconciliation
09-dashboard.md              giao diện web
10-dong-goi-nghiem-thu.md    đóng gói Windows, kịch bản nghiệm thu
```

### Quy tắc bắt buộc cho MỌI phase

1. **Đọc `PROGRESS.md` trước khi bắt đầu.** Nó ghi phase nào đã xong và có vấn đề gì còn treo.
2. **Chạy toàn bộ test hiện có trước khi viết code mới.** Nếu có test đỏ, sửa trước, không viết thêm.
3. **Mỗi phase kết thúc bằng ba bước bắt buộc:**
   - Chạy lại toàn bộ test của các phase trước (kiểm tra hồi quy).
   - Chạy test của phase vừa làm.
   - Cập nhật `PROGRESS.md` với những gì đã xong, những gì lệch so với plan, và vấn đề còn treo.
4. **Không viết code cho phase sau.** Nếu thấy cần, ghi vào `PROGRESS.md` mục "phát hiện sớm" rồi thôi.
5. **Không tự đổi quyết định ở mục 4.** Gặp mâu thuẫn thì dừng và báo cáo.
6. **Mọi tiền thật đều nguy hiểm.** Không có đoạn code nào được gửi lệnh thật cho tới phase 10,
   và ngay cả khi đó cũng chỉ trên tài khoản demo.

### Cách viết test

- Không cần MT5 thật cho phase 1–3 và 6–9. Dùng **mock agent** (một TCP client Python giả lập EA).
  Mock agent này được xây ở phase 3 và tái sử dụng cho mọi phase sau.
- Phase 4, 5 và 10 cần terminal MT5 thật ở chế độ demo.
- Ưu tiên test tình huống lỗi hơn test đường đi thuận lợi. Đường thuận lợi hiếm khi hỏng.

## 7. Ngăn xếp kỹ thuật

- Python 3.11+, `asyncio`, `pydantic` v2, `aiosqlite` hoặc `sqlite3` với executor, `FastAPI`, `uvicorn`, `pytest`, `pytest-asyncio`, `ruff`.
- MQL5, biên dịch bằng MetaEditor. Không dùng thư viện ngoài, không import DLL.
  Ràng buộc này áp cho **MQL5**; `clicker` là Python và được phép gọi `user32.dll` qua `ctypes`.
- Không dùng ORM. Viết SQL trực tiếp — schema nhỏ và các ràng buộc là phần quan trọng nhất.
