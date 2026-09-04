-- Schema của file archive `data/archive/YYYY-MM.db`.
--
-- Cố tình KHÔNG có khoá ngoại và không có CHECK: archive là kho đọc để tra cứu, không phải
-- nơi thực thi ràng buộc. Các bảng nó tham chiếu tới (pair, agent) vẫn nằm nguyên trong DB nóng
-- vì `pair` và `master_position` không bao giờ bị xoá theo thời gian (D-17).
--
-- Khoá chính vẫn giữ, và chỉ giữ để `INSERT OR IGNORE` làm cho việc chạy lại retention sau một
-- lần gián đoạn không sinh bản ghi trùng. Điều này quan trọng vì DB nóng chạy WAL, mà SQLite
-- không cam kết giao dịch nguyên tử xuyên qua nhiều database khi có WAL — nên bước "chép sang
-- archive" và bước "xoá khỏi DB nóng" là hai giao dịch tách rời.

CREATE TABLE IF NOT EXISTS event (
    id                   INTEGER,
    event_id             TEXT PRIMARY KEY,
    agent_id             TEXT,
    seq                  INTEGER,
    type                 TEXT,
    position_id          INTEGER,
    pair_id              TEXT,
    caused_by_command_id TEXT,
    deal_entry           TEXT,
    volume_delta         REAL,
    volume_after         REAL,
    price                REAL,
    payload_json         TEXT,
    ts_agent             TEXT,
    received_at          TEXT,
    processed_at         TEXT,
    process_status       TEXT,
    process_error        TEXT
);

CREATE TABLE IF NOT EXISTS command (
    command_id         TEXT PRIMARY KEY,
    target_agent_id    TEXT,
    pair_id            TEXT,
    type               TEXT,
    payload_json       TEXT,
    status             TEXT,
    attempt            INTEGER,
    retcode            INTEGER,
    retmsg             TEXT,
    executed_volume    REAL,
    result_position_id INTEGER,
    deadline_at        TEXT,
    sent_at            TEXT,
    acked_at           TEXT,
    created_at         TEXT,
    updated_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_arch_event_pair ON event(pair_id);
CREATE INDEX IF NOT EXISTS idx_arch_event_time ON event(received_at);
CREATE INDEX IF NOT EXISTS idx_arch_cmd_pair   ON command(pair_id);
