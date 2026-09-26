# Bước 0 — thử named pipe thay TCP (hướng A)

Bản thử, **không phải sản phẩm**. Mục đích: trả lời bốn câu hỏi trước khi viết lại tầng truyền.
Kết quả quyết định đi tiếp hướng A hay dừng.

| File | Vai trò |
|---|---|
| `pipe_server.py` | Pipe server tối thiểu (chỉ thư viện chuẩn). Trả `pong` cho `ping`, cứ 2 giây đẩy `tick` xuống, ghi log PID từng EA. |
| `PipeSpike.mq5` | EA thử. Không đặt lệnh. Tự đo và cứ 10 giây in một dòng `BAO CAO`. |
| `chay-bang-system.ps1` | Chạy server bằng LocalSystem, giống dịch vụ Bridge (câu 3). |

**Không** tick *Allow WebRequest* và **không** tick *Allow DLL imports* trong suốt bài thử. Chính
điều đó là thứ đang được kiểm.

## Đã kiểm trên máy dev (2026-09-24, không có MT5)

- Server tạo pipe với DACL riêng. Hai client Python nối cùng lúc, mỗi bên nhận đúng `hello_ack` và `tick`.
- Server phát hiện client ngắt (`BROKEN_PIPE`, err 109) và ghi được PID của client.
- **Phát hiện:** nếu chỉ có một vòng chờ, client thứ hai mở ngay sau client thứ nhất sẽ nhận
  `ERROR_PIPE_BUSY`. Server thử đã sửa bằng hai vòng chờ song song. Bản chính thức phải luôn giữ
  sẵn instance rảnh, và EA phải coi "pipe bận" là lỗi tạm thời rồi thử lại.
- `PipeSpike.mq5` biên dịch bằng MetaEditor: 0 lỗi, 0 cảnh báo.

## Chạy trên VPS có MT5

Chuẩn bị: chép `PipeSpike.mq5` vào `MQL5\Experts\` của **cả hai** terminal (File → Open Data
Folder), rồi biên dịch trong MetaEditor. Dừng dịch vụ Bridge nếu đang chạy. Bài thử dùng pipe tên
riêng nên không đụng Bridge, nhưng dừng thì log gọn hơn.

**Câu 1 — đọc pipe không treo `OnTimer`**
1. `python spike\pipe\pipe_server.py`
2. Gắn `PipeSpike` lên một chart (Role = `MASTER`). Góc chart phải hiện `DA NOI`.
3. Chờ 1 phút. Xem các dòng `BAO CAO` trong tab Experts:
   - `pump_max_us` luôn dưới ~5000 (5 ms) → **đạt**.
   - `pong` ≈ 10 mỗi báo cáo, `tick` ≈ 5.

**Câu 2 — server chết rồi sống lại**
1. Đóng cửa sổ server (hoặc Ctrl+C). Trong ≤ 1–2 giây, EA phải in `GHI LOI` hoặc `FileSize loi`,
   rồi `DONG pipe`, và góc chart đổi sang `CHUA NOI / DANG THU LAI`.
2. Chạy lại server. Trong ≤ 2 giây EA phải in `DA NOI pipe (lan 2)` và báo cáo tiếp.
3. Lặp 3 lần. **Đạt** nếu lần nào cũng tự nối lại, không phải gỡ EA.

**Câu 3 — server chạy bằng LocalSystem**
1. PowerShell *Run as administrator*: `spike\pipe\chay-bang-system.ps1`
2. Gỡ EA khỏi chart rồi gắn lại. `spike\pipe\system.log` phải có `HELLO` và `BAO CAO` → **đạt**.
3. `chay-bang-system.ps1 -DaclMacDinh`, gỡ và gắn lại EA. Dự đoán: EA mở không được, hoặc mở được
   mà ghi lỗi. Nếu vậy thì xác nhận DACL riêng là bắt buộc. Nếu vẫn chạy thì ghi lại, đó cũng là thông tin.
4. `chay-bang-system.ps1 -Go` để dọn.

**Câu 4 — hai EA cùng lúc**
1. Server chạy thường. Gắn `PipeSpike` lên chart của terminal Master (Role `MASTER`) **và** terminal
   Client (Role `CLIENT`).
2. Log server phải có hai dòng `HELLO` với hai `pid` khác nhau, và báo cáo của cả hai đều đều → **đạt**.
3. Tắt rồi bật lại server (như câu 2): cả hai phải tự nối lại.

## Ghi kết quả

| Câu | Đạt? | Số liệu / ghi chú |
|---|---|---|
| 1. Không treo | | `pump_max_us` lớn nhất = |
| 2. Nối lại | | thời gian phát hiện ≈ , số lần thử = |
| 3. LocalSystem | | DACL riêng: / DACL mặc định: |
| 4. Hai EA | | |

Cả bốn đạt → làm tiếp hướng A. Có câu hỏng mà không có cách vòng → dừng, xem lại C hoặc giữ bước tay.
