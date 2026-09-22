# NỘI BỘ — Bản nhiều Client (1 Master × N Client)

> **Tài liệu nội bộ.** Bản giao cho khách cấu hình cho **1 Master + 1 Client** và **không nhắc một
> chữ nào** tới khả năng này — không trên dashboard, không trong `docs/CAI-DAT-VPS.md`. Xem
> **D-42** để biết vì sao, và biết giới hạn của việc "giấu" khi kho mã công khai.

## Mở giới hạn

```powershell
.\.venv\Scripts\python.exe -m bridge.admin gioi-han-client 2
```

Không tham số thì in giá trị hiện tại. Sau khi mở, khối **Thêm Client** hiện lại trên tab Cấu hình
và toàn bộ phần dưới đây áp dụng được.

Giới hạn **chỉ chặn ở giao diện**: `ops.tao_client`, `POST /api/client`, `POST /api/client_moi` và
`bridge.admin them-client` chưa bao giờ kiểm nó, nên năng lực nhiều Client vẫn nguyên vẹn bên dưới.

**Một Client = một terminal MT5 riêng.** Chuẩn bị trước: cài thêm một terminal MT5, đăng nhập tài
khoản demo riêng, chế độ **Hedging**, bật Algo Trading, mở Toolbox ở tab **Trade**, và mở sẵn chart
của symbol sẽ copy.

Rồi trên dashboard → tab **Cấu hình** → khối **Thêm Client** → bấm **Thêm Client**. Một lần bấm tạo
đủ (D-38):

| Sinh ra | Tên |
|---|---|
| Mã Client | `CL-02` (theo dãy đang có) |
| Agent của EA | `AG-CL02` |
| Agent clicker | `AG-CLICKER-CL02` |
| Mục token clicker trong `config.toml` | `[clicker_cl02]` — ghi thẳng, không phải dán tay |
| Dòng cấu hình copy | đường mở/đóng qua **giao diện** |

Còn đúng **hai việc**, và cả hai nằm ngoài trình duyệt — trang in sẵn cả token lẫn câu lệnh:

1. **Dán token EA** (hiện đúng một lần ngay sau khi bấm) vào tham số `AgentToken` của
   `CopyBridgeClient.ex5` trên terminal mới. Chép `.ex5` từ `C:\CopyBridge\ea\` như mục A2.
2. **Đăng ký tác vụ clicker** — PowerShell **Administrator**, tại `C:\CopyBridge`:

   ```powershell
   .\scripts\tao-dich-vu.ps1 -ChiTacVuClicker -TacVuClicker clicker_cl02
   Start-ScheduledTask -TaskPath "\CopyBridge\" -TaskName ClickerCl02
   ```

Sau đó khai **ánh xạ symbol** cho `CL-02` (khối Ánh xạ symbol, chọn từ danh sách). Số tài khoản và
tiêu đề cửa sổ của clicker **không phải khai**: Bridge tự suy từ EA chạy trên chính terminal đó.

Khối **Cần làm** ở đầu tab là thứ nói khi nào xong — hết mục CHẶN là copy được.

> **Ba clicker trên một VPS là bình thường** (`clicker`, `clicker_master`, `clicker_cl02`): mỗi cái
> một tiến trình, một khoá chống chạy trùng, một nhật ký, và mỗi cái chỉ chạm đúng terminal có số
> tài khoản đã khai. Cái **không** bình thường là hai clicker cùng một terminal — dashboard từ chối
> khai hai Client dùng chung một clicker.


## Bằng dòng lệnh

$py = ".\.venv\Scripts\python.exe"
& $py -m bridge.admin them-client CL-02 --agent AG-CLIENT-2 --open-route EA --close-route EA
# Hoac di duong giao dien ngay tu dau -- clicker_agent_id CHI dat duoc luc tao client:
& $py -m bridge.admin them-client CL-02 --agent AG-CLIENT-2 --clicker-agent AG-CLICKER-CL02 --open-route UI
