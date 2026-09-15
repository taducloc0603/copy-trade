-- 006 — Hàng đợi lệnh mở qua giao diện (D-31).
--
-- Cổng "đúng MỘT `OPEN_UI` đang bay cho mỗi Client" là đúng và được giữ: nó biến bài toán tương
-- quan mờ thành hàng đợi một phần tử luôn phân giải được. Cái sai là cách xử lý khi bận — trước
-- bản này nó **bỏ hẳn** lệnh, mà bỏ một lệnh copy nghĩa là MẤT HEDGE. Vào 10 lệnh liên tiếp trên
-- Master thì Client chỉ copy được lệnh đầu (một vòng bấm giao diện mất ~0,8 giây).
--
-- Bảng này là chỗ chờ tới lượt. Nó nằm trong DB chứ không trong bộ nhớ vì hai lý do:
-- `tinh-hinh` phải thấy được hàng đợi đang dài bao nhiêu, và Bridge khởi động lại giữa chừng thì
-- những gì đang chờ phải hết hạn có tiếng chứ không biến mất im lặng.
--
-- Không lưu payload: `event_id` trỏ tới dòng `event` vốn đã giữ nguyên payload gốc. Lưu bản sao
-- thứ hai là tạo chỗ cho hai bản lệch nhau.
--
-- `UNIQUE (client_id, master_position_id)` chặn xếp trùng khi event lặp. Nó BỔ SUNG cho phép kiểm
-- "đã có pair chưa" ở `_open_for_client`, không thay thế: cái kia chặn trùng sau khi đã mở, cái
-- này chặn trùng trong lúc còn đang chờ.

CREATE TABLE IF NOT EXISTS ui_open_queue (
    queue_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id          TEXT    NOT NULL REFERENCES client_account(client_id),
    event_id           TEXT    NOT NULL REFERENCES event(event_id),
    master_position_id INTEGER NOT NULL,
    created_at         TEXT    NOT NULL,
    UNIQUE (client_id, master_position_id)
);

CREATE INDEX IF NOT EXISTS idx_ui_open_queue_client ON ui_open_queue(client_id, queue_id);

-- Trần tuổi RIÊNG cho hàng đợi, không dùng chung `client_account.max_event_age_ms` (5000ms).
-- Lệnh nằm chờ tới lượt thì đương nhiên cũ hơn giới hạn của đường thường; 15 giây là mức đã chốt
-- — quá đó giá đã chạy đủ xa để việc mở thành mở sai giá, và huỷ tốt hơn mở.
INSERT OR IGNORE INTO system_config (key, value, updated_at)
VALUES ('ui_open_queue_max_age_ms', '15000', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at)
VALUES ('ui_open_queue_max_len', '20', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
