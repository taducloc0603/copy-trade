-- 005 — Đóng lệnh phía Master qua giao diện (phase 12, D-21c).
--
-- Hai thứ, và cả hai đều để trả lời cùng một câu hỏi: deal ĐÓNG trên tài khoản Master mang
-- `DEAL_REASON` nào.
--
-- 1. `master_position.close_reason` — đo được thay vì tin. Phía Client đã có
--    `pair.client_close_reason` từ migration 004; phía Master thì trước nay không lưu gì, nên câu
--    "Master nay cũng đóng bằng tay" sẽ không kiểm được bằng truy vấn.
--
-- 2. Hai khoá định tuyến trong `system_config`. Master **không có** dòng `client_account` để mang
--    cột `close_route`, mà `system_config` là key/value nên không phải đụng schema.
--
--    Mặc định `EA` — nâng cấp không đổi hành vi của bản đang chạy. Bật đường giao diện là một
--    hành động có chủ đích, và nó đòi thêm một clicker thứ hai lái terminal Master.

ALTER TABLE master_position ADD COLUMN close_reason INTEGER;

INSERT OR IGNORE INTO system_config (key, value, updated_at)
VALUES ('master_close_route', 'EA', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

INSERT OR IGNORE INTO system_config (key, value, updated_at)
VALUES ('master_clicker_agent_id', '', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
