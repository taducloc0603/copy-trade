# MT5 Copy Bridge

Đồng bộ lệnh giữa hai tài khoản MetaTrader 5 để tạo và quản lý vị thế hedge theo cặp.
Master mở lệnh thì Client mở lệnh tương ứng (cùng chiều hoặc ngược chiều, volume theo hệ số đã
chuẩn hoá về bước lot của sàn Client); Master đóng thì Client luôn đóng đúng cặp. Chiều Client
đóng ngược Master là tuỳ chọn, mặc định TẮT. Mỗi cặp có Pair ID riêng và tra cứu luôn theo
`position_id`, không bao giờ theo tên symbol. Luật cứng: hệ thống được tự động **ĐÓNG**,
không được tự động **MỞ**.

Chỉ hỗ trợ tài khoản MT5 chế độ **Hedging**, chỉ Market Order BUY/SELL. Chạy trên Windows.

```
MT5 Master + EA ──TCP/NDJSON──┐
                              ├──► BRIDGE (Python) ──► SQLite
MT5 Client + EA ──TCP/NDJSON──┘        │
                                       └──► Dashboard web (FastAPI + WebSocket)
```

EA (MQL5) là agent mỏng: bắt sự kiện, thực thi lệnh, gửi heartbeat. Toàn bộ logic nghiệp vụ
nằm ở Bridge.

## Cài đặt lên VPS — dùng script

Đây là đường cài chính thức. Script tự cài Python và git, lấy mã nguồn, tạo `.venv`, tạo
`config.toml` với mật khẩu ngẫu nhiên, khởi tạo database và chạy bộ test:

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest "https://raw.githubusercontent.com/taducloc0603/copy-trade/main/scripts/cai-dat.ps1" `
  -OutFile "$env:USERPROFILE\Desktop\cai-dat.ps1" -UseBasicParsing
& "$env:USERPROFILE\Desktop\cai-dat.ps1" -ThuMuc C:\CopyBridge
```

Rồi chạy trợ lý, nó hỏi xác nhận từng bước cho tới lúc chạy được:

```powershell
C:\CopyBridge\scripts\tro-ly.ps1 -ThuMuc C:\CopyBridge
```

Chọn tài liệu phù hợp trong [bảng ở đầu docs/CAI-DAT-VPS.md](docs/CAI-DAT-VPS.md).

## Cài tay để phát triển trên máy cá nhân

Chỉ dùng khi bạn sửa mã nguồn, **không** phải đường cài lên VPS (cần Python 3.11 trở lên):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy config.example.toml config.toml   # rồi điền giá trị thật
```

`config.toml` chứa bí mật và nằm trong `.gitignore`.

## Chạy test

```powershell
pytest
ruff check .
```

Phase 1–3 và 6–9 test được không cần MT5 (dùng mock agent). Phase 4, 5, 10 cần terminal MT5
ở chế độ **demo**.

## Chạy Bridge

Chạy được trên **demo**. Phase 1–8 xong, phase 9 (dashboard) phần lớn xong, phase 10
(đóng gói và nghiệm thu) chưa bắt đầu — bảng trạng thái ở [PROGRESS.md](PROGRESS.md).

Bridge luôn khởi động ở `PAUSED` và chỉ sang `RUNNING` khi có người bấm nút.

> **Chưa dùng được cho tiền thật.** Kiểm toán độc lập 2026-09-06
> ([docs/DANH-GIA-TONG-THE.md](docs/DANH-GIA-TONG-THE.md)) kết luận **NO-GO**.
> Xem [docs/BACKLOG.md](docs/BACKLOG.md) để biết còn lại những gì.

## Tài liệu

Bốn tài liệu cài đặt, chọn một:

- [docs/HUONG-DAN-CUNG-VPS-SCRIPT.html](docs/HUONG-DAN-CUNG-VPS-SCRIPT.html) — **khuyến
  nghị.** Cài, vận hành và **cập nhật** trên một VPS bằng bộ script `scripts/`. Chi tiết nhất.
- [docs/CAI-DAT-VPS.md](docs/CAI-DAT-VPS.md) — bản tra cứu ngắn của tài liệu trên, chỉ các
  lệnh cần gõ. Đây là bản các script in ra khi có sự cố.
- [docs/HUONG-DAN-CUNG-VPS.html](docs/HUONG-DAN-CUNG-VPS.html) — cài trên một VPS **bằng
  tay**, kèm ví dụ và ảnh chụp màn hình. Đọc khi muốn hiểu từng bước đang làm gì.
- [docs/HUONG-DAN-KHAC-VPS.html](docs/HUONG-DAN-KHAC-VPS.html) — Master và Client ở **hai**
  VPS khác nhau, qua Tailscale. **Cách bố trí này chưa bao giờ được chạy thử.**

Còn lại:

- [docs/DECISIONS.md](docs/DECISIONS.md) — 20 quyết định thiết kế và lý do. **Đọc trước tiên.**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — kiến trúc, ranh giới ba vai trò, luồng dữ liệu
- [docs/CONVENTIONS.md](docs/CONVENTIONS.md) — quy ước code
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — thuật ngữ
- [plan/](plan/) — kế hoạch triển khai chi tiết, 10 phase

> **Cảnh báo:** đây là phần mềm giao dịch. Không dùng trên tài khoản thật trước khi chạy ổn định
> trên demo ít nhất một tuần và đọc hết mục "Trước khi chuyển sang tài khoản thật" ở
> `plan/10-dong-goi-nghiem-thu.md`.
