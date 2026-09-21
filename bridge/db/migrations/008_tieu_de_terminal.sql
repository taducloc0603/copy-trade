-- 008 — Tiêu đề cửa sổ terminal của clicker chuyển từ `config.toml` vào database.
--
-- Trước đây `account_login` và `terminal_title` của clicker nằm ở mục `[clicker]` /
-- `[clicker_master]` trong `config.toml`, nên đổi terminal hay đổi tài khoản MT5 là phải RDP vào
-- VPS sửa file rồi chạy lại tác vụ — và người cài phải biết cả hai giá trị **trước** khi hệ thống
-- chạy lần đầu. Đưa chúng vào bảng `agent` để sửa được trên dashboard: clicker nhận chúng lúc bắt
-- tay, cùng đường mà nó đã nhận `heartbeat_interval_ms`.
--
-- `account_login` đã có sẵn ở bảng này (nó là thứ Bridge đối chiếu khi bắt tay), nên chỉ thiếu
-- tiêu đề cửa sổ. Chỉ thêm cột, không dựng lại bảng: `ALTER TABLE ... ADD COLUMN` giữ nguyên dữ
-- liệu và không đụng khoá ngoại nào.
--
-- Giá trị trong `config.toml` vẫn **thắng** giá trị ở đây (thứ tự ưu tiên: tham số dòng lệnh >
-- config.toml > Bridge), nên một bản cài cũ nâng cấp lên không đổi hành vi.

ALTER TABLE agent ADD COLUMN terminal_title TEXT;
