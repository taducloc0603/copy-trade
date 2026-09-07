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

## Cài đặt (cần Python 3.11 trở lên)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy config.example.toml config.toml   # rồi điền giá trị thật
```

`config.toml` chứa bí mật và nằm trong `.gitignore`.

Triển khai lên VPS Windows bằng script: xem
[docs/HUONG-DAN-CUNG-VPS-SCRIPT.html](docs/HUONG-DAN-CUNG-VPS-SCRIPT.html) (chi tiết, kèm quy
trình cập nhật) hoặc [docs/CAI-DAT-VPS.md](docs/CAI-DAT-VPS.md) (bản ngắn).

## Chạy test

```powershell
pytest
ruff check .
```

Phase 1–3 và 6–9 test được không cần MT5 (dùng mock agent). Phase 4, 5, 10 cần terminal MT5
ở chế độ **demo**.

## Chạy Bridge

Chưa chạy được — mới xong phase 1 (khung dự án). Xem [PROGRESS.md](PROGRESS.md).
Khi chạy được, Bridge luôn khởi động ở `PAUSED` và chỉ sang `RUNNING` khi có người bấm nút.

## Tài liệu

- [docs/HUONG-DAN-CUNG-VPS-SCRIPT.html](docs/HUONG-DAN-CUNG-VPS-SCRIPT.html) — cài, vận hành
  và **cập nhật** trên một VPS bằng bộ script `scripts/`. Chi tiết nhất.
- [docs/CAI-DAT-VPS.md](docs/CAI-DAT-VPS.md) — bản rút gọn của tài liệu trên
- [docs/DECISIONS.md](docs/DECISIONS.md) — 20 quyết định thiết kế và lý do. **Đọc trước tiên.**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — kiến trúc, ranh giới ba vai trò, luồng dữ liệu
- [docs/CONVENTIONS.md](docs/CONVENTIONS.md) — quy ước code
- [docs/GLOSSARY.md](docs/GLOSSARY.md) — thuật ngữ
- [plan/](plan/) — kế hoạch triển khai chi tiết, 10 phase

> **Cảnh báo:** đây là phần mềm giao dịch. Không dùng trên tài khoản thật trước khi chạy ổn định
> trên demo ít nhất một tuần và đọc hết mục "Trước khi chuyển sang tài khoản thật" ở
> `plan/10-dong-goi-nghiem-thu.md`.
