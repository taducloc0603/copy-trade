# MT5 Copy Bridge

Đồng bộ lệnh giữa hai tài khoản MetaTrader 5 để tạo và quản lý vị thế hedge theo cặp.

- **Mở:** Master mở lệnh thì Client mở lệnh tương ứng — cùng chiều hoặc ngược chiều (`copy_mode`),
  volume theo hệ số đã làm tròn về bước lot của sàn Client. Chiều mở **chỉ đi Master → Client**.
- **Đóng:** Master đóng thì Client luôn đóng đúng cặp. Client đóng thì Master đóng theo khi bật
  `can_close_master` (mặc định tắt).
- Lệnh mở và đóng phía Client đi qua **giao diện MT5** (clicker), nên deal mang
  `DEAL_REASON_CLIENT` (*Placed by manual*). Phía Master có thể bật tương tự cho lệnh đóng.
- Mỗi cặp có Pair ID riêng, tra theo `position_id`, không bao giờ theo tên symbol.
- Luật cứng: hệ thống được tự động **ĐÓNG**, không được tự động **MỞ** lại.

Chỉ hỗ trợ tài khoản **Hedging**, Market Order BUY/SELL, Windows, tất cả trên một VPS.

```
MT5 Master + EA ──┐                    ┌── Clicker Client (mở/đóng qua giao diện)
                  ├── TCP ── BRIDGE ───┤
MT5 Client + EA ──┘   (Python, SQLite) └── Clicker Master (đóng qua giao diện, tuỳ chọn)
                              └── Dashboard web
```

EA (MQL5) là agent mỏng: báo sự kiện, thực thi lệnh, gửi heartbeat. Toàn bộ logic nằm ở Bridge.

## Cài đặt

**[docs/CAI-DAT-VPS.md](docs/CAI-DAT-VPS.md)** — tài liệu cài đặt duy nhất:

- **Phần A** — VPS chưa có hệ thống: **một lệnh** (`scripts\cai-dat.ps1`, tự chạy tiếp `tro-ly.ps1`) rồi khai nốt cấu hình trên dashboard — trình duyệt tự mở.
- **Phần B** — VPS đã có hệ thống: cập nhật (`cai-dat.ps1 -CapNhat`), lùi bản, bật thêm tính năng,
  đổi tài khoản, chuyển VPS, và **gỡ sạch** (`scripts\go-bo.ps1`, B7).
- **Phần C** — vận hành hằng ngày.

## Trạng thái

Phase 1–12 xong, chạy trên **demo** (VPS). Bộ test tự động: `pytest` (~907 test) + `ruff check .`.

> **Chưa dùng cho tiền thật** cho tới khi xong các điều kiện ở [RUNBOOK.md](docs/RUNBOOK.md) mục 8
> — đáng kể nhất là đo **phiên RDP ngắt** (B-08) và **mất điện đột ngột** (TEST-19).

## Phát triển trên máy cá nhân

Cần Python 3.11+:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy config.example.toml config.toml   # rồi điền giá trị thật; file này nằm trong .gitignore
pytest
ruff check .
```

Phần lớn logic test được bằng mock agent, không cần MT5. EA và clicker cần terminal MT5 **demo**.

Cấu hình nghiệp vụ (agent, client, ánh xạ symbol, khoá hệ thống) nằm trong database và **sửa
trên dashboard**, tab Cấu hình (D-32). `config.toml` chỉ giữ thứ cần trước khi Bridge chạy — cổng,
đường dẫn DB, token clicker — và cũng sửa được trên trang đó, nhưng phải khởi
động lại dịch vụ mới có hiệu lực.

## Tài liệu

| Tài liệu | Dùng khi |
|---|---|
| [docs/CAI-DAT-VPS.md](docs/CAI-DAT-VPS.md) | Cài đặt, cập nhật, vận hành hằng ngày |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Giải thích cấu hình, lệnh vận hành, **xử lý sự cố** (mục 7), điều kiện chạy thật (mục 8) |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Thuật ngữ dùng trong dashboard và tài liệu |

Các tài liệu **nội bộ** dưới đây **không đi kèm bản cài**: `scripts/cai-dat.ps1` xoá chúng khỏi thư
mục cài sau mỗi lần cài hoặc cập nhật, nên liên kết ở đây trỏ thẳng lên GitHub (D-42).

| Tài liệu nội bộ | Dùng khi |
|---|---|
| [DECISIONS.md](https://github.com/taducloc0603/copy-trade/blob/main/docs/DECISIONS.md) | Các quyết định thiết kế D-01…D-42 và lý do — **đọc trước khi sửa hành vi** |
| [ARCHITECTURE.md](https://github.com/taducloc0603/copy-trade/blob/main/docs/ARCHITECTURE.md) | Kiến trúc, ranh giới vai trò, luồng dữ liệu |
| [ACCEPTANCE.md](https://github.com/taducloc0603/copy-trade/blob/main/docs/ACCEPTANCE.md) | Bảng nghiệm thu TEST-01…TEST-32 và nguồn bằng chứng |
| [BACKLOG.md](https://github.com/taducloc0603/copy-trade/blob/main/docs/BACKLOG.md) | Giới hạn đã biết và việc còn nợ (B-xx) |
| [CONVENTIONS.md](https://github.com/taducloc0603/copy-trade/blob/main/docs/CONVENTIONS.md) | Quy ước code |
| [NOI-BO-nhieu-client.md](https://github.com/taducloc0603/copy-trade/blob/main/docs/NOI-BO-nhieu-client.md) | Mở phần 1 Master × N Client |
| [plan/](https://github.com/taducloc0603/copy-trade/tree/main/plan) | Kế hoạch triển khai theo phase (hồ sơ thiết kế, code có trích dẫn) |
| [PROGRESS.md](https://github.com/taducloc0603/copy-trade/blob/main/PROGRESS.md) | Nhật ký tiến độ và các lần đo |
