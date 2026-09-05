# Kiến trúc

Tài liệu này mở rộng các mục 1, 2, 3 của `plan/00-README.md`.

---

## 1. Hệ thống làm gì

Đồng bộ lệnh giữa hai tài khoản MetaTrader 5 để tạo và quản lý các vị thế hedge theo cặp.

- Master mở lệnh → Client mở lệnh tương ứng. Chiều mở lệnh **chỉ đi một chiều** Master → Client.
- Client có thể cùng chiều (BUY→BUY) hoặc ngược chiều (BUY→SELL) tuỳ cấu hình.
- `Client Volume = Master Volume × Hệ số`, sau đó chuẩn hoá theo quy định của sàn Client.
- Master đóng → Client luôn đóng đúng cặp.
- Client đóng → Master đóng hay không tuỳ công tắc, mặc định TẮT (D-20).
- Mỗi cặp lệnh có Pair ID riêng. **Không bao giờ đóng lệnh dựa trên tên symbol.**

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

## 3. Sơ đồ hệ thống

```
   ┌────────────────────┐
   │  MT5 Master        │
   │  + CopyBridge EA   │──────┐
   └────────────────────┘      │
                               │  TCP / NDJSON
   ┌────────────────────┐      │  127.0.0.1:8787  (cùng VPS)
   │  MT5 Client #1     │      │  100.x.y.z:8787  (khác VPS, qua Tailscale)
   │  + CopyBridge EA   │──────┤
   └────────────────────┘      │
              ...              │
   ┌────────────────────┐      │
   │  MT5 Client #N     │──────┤
   └────────────────────┘      │
                               │
   ┌────────────────────┐      │
   │  clicker (Python)  │──────┘
   │  cạnh MT5 Client   │      │
   └─────────┬──────────┘      │
             │ PostMessage     │
             ▼                 │
     hộp thoại New Order       │
     của MT5 Client            │
     (chỉ lệnh MỞ, D-21)       │
                               ▼
                    ┌─────────────────────────┐
                    │   BRIDGE  (Python)      │
                    │                         │
                    │  protocol/  TCP server  │      ┌──────────────────┐
                    │  engine/    nghiệp vụ   │─────►│ SQLite           │
                    │  db/        repository  │      │ WAL              │
                    │  web/       dashboard   │      │ synchronous=FULL │
                    └─────────────────────────┘      └──────────────────┘
                               │
                               │  HTTP + WebSocket, cổng 8080
                               ▼
                    ┌─────────────────────────┐
                    │  Dashboard web          │
                    │  (trình duyệt, có thể   │
                    │   ở xa qua Tailscale)   │
                    └─────────────────────────┘
```

## 4. Bốn vai trò và ranh giới trách nhiệm

| Vai trò | Là gì | Được làm gì |
|---|---|---|
| EA (MQL5) | Agent mỏng gắn vào chart mỗi terminal | Bắt sự kiện, thực thi lệnh, gửi heartbeat |
| Bridge (Python) | Tiến trình độc lập, nguồn sự thật duy nhất | Toàn bộ logic nghiệp vụ, ghi DB |
| Dashboard | Web phục vụ bởi chính Bridge | Hiển thị và điều khiển |
| Clicker | Tiến trình Python cạnh terminal Client | **Chỉ** mở lệnh qua giao diện MT5 (D-21) |

### EA được làm

- Bắt `OnTradeTransaction`, lọc lấy đúng `TRADE_TRANSACTION_DEAL_ADD`, gửi event lên Bridge.
- Ghi event vào hàng đợi cục bộ **trước** khi gửi socket, để không mất sự kiện khi Bridge chết.
- Thực thi command `OPEN` / `CLOSE` / `CLOSE_PARTIAL` / `REQUEST_SNAPSHOT` với đúng thông số
  Bridge gửi xuống, và trả ack kèm `retcode` nguyên bản.
- Gửi heartbeat kèm `broker_connected`, `equity`, `margin_level`.
- Đẩy `symbol_specs` của terminal mình lên Bridge.
- Từ chối command hết hạn, sai magic, volume ≤ 0, hoặc symbol không tồn tại.

### Clicker được làm

Đúng một việc: nhận `OPEN_UI`, điền hộp thoại New Order của MT5, đọc lại để xác nhận, rồi
bấm. Nó tồn tại vì `DEAL_REASON` do máy chủ broker gán theo *kênh* gửi lệnh, mà `OrderSend`
của EA luôn cho ra `EXPERT` (D-21).

Ba chi tiết đã **đo trên terminal thật**, không suy ra, và cả ba đều phản trực giác:

- **Ô volume phải gõ bằng `WM_CHAR` từng ký tự.** `WM_SETTEXT` đổi chữ hiển thị nhưng không cập
  nhật trạng thái nội bộ của MT5; lệnh gửi đi mang volume cũ. Và vì MT5 giữ volume nội bộ qua
  các lần mở hộp thoại, hỏng kiểu này gửi đi kích thước của **lệnh trước** chứ không phải một
  giá trị mặc định dễ nhận ra.
- **Đọc lại chữ trong ô không chứng minh được gì** về giá trị MT5 sẽ dùng. Việc đọc lại vẫn cần
  — nó bắt ô sai, hộp thoại sai, symbol sai — nhưng bằng chứng duy nhất là deal thật.
- **Mở hộp thoại bằng `PostMessage(WM_COMMAND, 32848)`**, chính là `Tools → New Order`. Không
  cần focus, không cần bàn phím, không cần desktop tương tác — đó là điều kiện để sống qua
  phiên RDP đã ngắt.

Không dùng One Click Trading dù nó nhanh hơn: bảng OCT không có ô Comment, mà thẻ trong comment
là cơ chế tương quan duy nhất (D-26).

Clicker **không** đọc database, **không** sinh event, **không** nhận lệnh đóng, và **không**
tính toán gì. Nó không biết `pair` là gì. Việc ghép vị thế vừa mở vào cặp lệnh do Bridge làm,
bằng cách tương quan với event `position_opened` mà EA báo lên (D-23).

### EA **không** được làm

- Không tính volume, không làm tròn theo `volume_step`.
- Không ánh xạ symbol giữa hai sàn.
- Không biết Pair ID là gì ngoài việc echo lại.
- Không biết database tồn tại.
- Không quyết định có copy hay không copy.

> **Ngoại lệ duy nhất:** EA tự chọn filling mode theo `SYMBOL_FILLING_MODE`, vì đó là chi tiết
> kỹ thuật của broker chứ không phải quy tắc nghiệp vụ (D-01).

### Bridge được làm

Tất cả phần còn lại: lọc điều kiện copy, ánh xạ symbol, tính và chuẩn hoá volume, khoá
`effective_multiplier`, tạo pair và Pair ID, sinh command, xử lý ack và retcode, cascade có
kiểm soát, chống vòng lặp, đối chiếu, cảnh báo, lưu trữ.

### Dashboard được làm

Chỉ hiển thị và gọi API của tầng `engine`. Nếu thấy mình đang viết SQL cập nhật `pair` trong
tầng web thì đó là dấu hiệu sai.

## 5. Nguyên tắc kết nối

- **Các EA không bao giờ nói chuyện trực tiếp với nhau.** Mọi thứ đi qua Bridge.
- TCP socket, một giao thức duy nhất cho cả hai kịch bản triển khai.
  Cùng VPS thì `127.0.0.1:8787`. Khác VPS thì địa chỉ Tailscale `100.x.y.z:8787`.
- Không dùng shared memory, không dùng DLL, không dùng WebRequest.
- Bridge là TCP server, EA là TCP client (D-03).

## 6. Luồng dữ liệu chính

### Mở lệnh

```
Master khớp lệnh
   → EA Master: DEAL_ADD, entry=IN
   → event `position_opened` (kèm seq, volume_after, ts_agent)
   → Bridge: ghi `event` vào DB TRƯỚC
   → engine: lọc điều kiện copy → ánh xạ symbol → tính volume → khoá effective_multiplier
   → một giao dịch DB: upsert `master_position` + insert `pair` (PENDING_OPEN) + insert `command` (PENDING)
   → gửi command qua socket

   Đường EA (open_route = 'EA'):
   → EA Client: kiểm tra command_id đã xử lý chưa → ghi vào file → OrderSend → ack
   → Bridge: ack thành công, có result_position_id → pair.status = OPEN

   Đường giao diện (open_route = 'UI', phase 6b):
   → clicker: giữ chỗ command_id + fsync → điền hộp thoại kèm thẻ → đọc lại → bấm → ack "ok"
   → EA Client vẫn thấy deal và gửi event `position_opened` kèm position_id thật + thẻ
   → Bridge: khớp thẻ → pair.status = OPEN
   Ack của clicker KHÔNG mang position_id; event của EA mới là nguồn sự thật (D-23).
```

**Số đo trên demo Connext, BTCUSD.s** (phase 6b bước 5, n = 5): độ trễ copy Master khớp → Client
có vị thế là min 553 / trung vị 616 / max 648 / **trung bình 604 ms**. Đường EA ở phase 6 là
~300 ms, nên cái giá của việc đổi kênh là khoảng gấp đôi — thấp hơn nhiều mức 1–3 s dự kiến khi
lập kế hoạch. Cổng một-lệnh-đang-bay cho thông lượng khoảng **một lệnh mỗi giây mỗi Client**.

Đã diễn tập và xác nhận: ack không bao giờ về thì pair vẫn mở được bằng tương quan; gửi lại cùng
`command_id` sau khi clicker chết thì **không** phát sinh lệnh thứ hai; và một lệnh mở tay trùng
symbol/chiều/volume đặt **đúng lúc** `OPEN_UI` đang bay thì không bị ghép nhầm.

> **Giới hạn hiện tại:** hộp thoại New Order lấy symbol theo chart đang mở, và driver chỉ *kiểm
> tra* symbol chứ không đổi. Vì vậy mỗi terminal Client hiện chỉ copy được **một symbol** — đúng
> cái chart đang mở. Đổi symbol qua ComboBox chưa được đo. Đây là món nợ phải trả trước khi dùng
> nhiều symbol, vốn nằm trong phạm vi MVP ở mục 2.

### Đóng lệnh

```
Một bên đóng
   → event `position_closed` kèm volume_after thật (D-14) và caused_by_command_id
   → caused_by_command_id khác NULL  → do chính bot gây ra, chỉ cập nhật trạng thái,
                                       KHÔNG lan truyền tiếp (D-08)
   → caused_by_command_id là NULL    → do người hoặc broker gây ra, kích hoạt đồng bộ
   → tra cứu pair LUÔN theo position_id, không bao giờ theo symbol
```

## 7. Cấu trúc thư mục

```
bridge/
  config.py         cấu hình khởi động, đọc từ config.toml
  logging_setup.py  logging có ngữ cảnh pair_id / event_id
  labels_vi.py      bảng nhãn tiếng Việt — nơi duy nhất có tiếng Việt hướng người dùng
  db/               schema, migration, repository            (phase 2)
  protocol/         NDJSON, TCP server, dispatcher           (phase 3)
  engine/           processor, sizing, reconcile             (phase 6, 7, 8)
  web/              FastAPI + WebSocket                      (phase 9)
ea/                 CopyBridgeCommon.mqh, Master, Client     (phase 4, 5)
clicker/            mở lệnh qua giao diện MT5, chạy cạnh terminal Client  (phase 6b)
tests/              conftest.py, mock_agent.py               (mock agent: phase 3)
data/               SQLite và archive — trong .gitignore
logs/               log xoay vòng theo ngày — trong .gitignore
docs/               tài liệu nền
plan/               kế hoạch triển khai theo phase
```

## 8. Ngăn xếp kỹ thuật

- Python 3.11+, `asyncio`, `pydantic` v2, `aiosqlite` hoặc `sqlite3` với executor,
  `FastAPI`, `uvicorn`, `pytest`, `pytest-asyncio`, `ruff`.
- MQL5, biên dịch bằng MetaEditor. Không dùng thư viện ngoài, không import DLL.
  Ràng buộc này áp cho **MQL5**; `clicker` là Python và gọi `user32.dll` qua `ctypes`.
- Không dùng ORM. Viết SQL trực tiếp — schema nhỏ và các ràng buộc là phần quan trọng nhất.
