-- 007 — Index cho vòng quét hạn command mỗi giây.
--
-- Đo trên VPS 2026-09-16 bằng bộ canh vòng sự kiện (`bridge/watchdog.py`): vòng asyncio của Bridge
-- bị chặn ~0,6–1 giây **mỗi giây**, stack luôn dừng ở `dispatcher.scan_deadlines` →
-- `SELECT * FROM command WHERE status = 'SENT' AND deadline_at IS NOT NULL AND deadline_at < ?`.
-- Hệ quả: ack của clicker và event của EA bị đọc dồn trễ 1,3–1,8 giây, vào lệnh liên tục cách nhau
-- ~3 giây dù clicker chỉ mất 0,7 giây.
--
-- `EXPLAIN QUERY PLAN` ra `SCAN command`: index một phần `idx_cmd_inflight ... WHERE status IN
-- ('PENDING','SENT')` **không dùng được**, vì SQLite chỉ dùng index một phần khi điều kiện của
-- truy vấn khớp đúng điều kiện của index — nó không suy `status = 'SENT'` ra `status IN (...)`.
-- Bảng `command` trên VPS có hàng trăm nghìn dòng (lũ `REQUEST_SNAPSHOT` 2026-09-12→15), nên quét
-- toàn bảng mỗi giây là đủ để đóng băng Bridge.
--
-- Index đầy đủ (không có WHERE) trên (status, deadline_at) thì truy vấn dùng thẳng, và thu hẹp luôn
-- theo `deadline_at`.

CREATE INDEX IF NOT EXISTS idx_cmd_status_han ON command(status, deadline_at);

-- Hai truy vấn cùng họ, đo cùng lúc bằng `EXPLAIN QUERY PLAN`, cũng `SCAN command`:
-- `processor.scan_correlation_deadlines` (chạy mỗi giây, cùng nhịp với `scan_deadlines`) và
-- `processor._open_ui_candidates` (mỗi event mở lệnh phía Client). Cả hai lọc `c.type = 'OPEN_UI'`
-- rồi nối sang `pair` theo `pair_id`. Dòng `OPEN_UI` chỉ là một phần nhỏ của bảng, nên index theo
-- (type, pair_id) biến quét toàn bảng thành tra cứu.
CREATE INDEX IF NOT EXISTS idx_cmd_type_pair ON command(type, pair_id);
