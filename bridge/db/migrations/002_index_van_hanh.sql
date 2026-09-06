-- Migration 002 — ba index cho ba truy vấn chạy lặp trong vận hành.
--
-- Cả ba đều nằm trên đường nóng và đều là quét bảng nếu thiếu index:
--
-- 1. `reconcile_finding`: cổng lọc trùng của phase 8 tra
--    (kind, resolution, pair_id, master_position_id, client_id) **mỗi lần** định ghi một sai
--    lệch, và vòng đối chiếu chạy mỗi 60 giây. Số finding chỉ tăng chứ không giảm.
-- 2. `command`: `list_inflight_commands(pair_id)` được gọi trước **mọi** lệnh đóng (plan 7.6,
--    một lệnh mỗi cặp) và trước mọi `OPEN_UI` (cổng một-lệnh-đang-bay của phase 6b).
-- 3. `alert`: trang nhật ký của dashboard lọc theo `acknowledged_at IS NULL` mỗi lần mở.
--
-- Không đổi cấu trúc dữ liệu, không mất mát nếu chạy lại. Đây cũng là migration ĐẦU TIÊN chạy
-- quá version 1 trên database có dữ liệu thật — rủi ro "bộ migration chưa từng chạy" ghi từ
-- phase 6b được đóng ở đây.

CREATE INDEX IF NOT EXISTS idx_finding_dang_cho
    ON reconcile_finding(kind, resolution, pair_id);

CREATE INDEX IF NOT EXISTS idx_command_dang_bay
    ON command(pair_id, status);

CREATE INDEX IF NOT EXISTS idx_alert_chua_xu_ly
    ON alert(acknowledged_at, id);
