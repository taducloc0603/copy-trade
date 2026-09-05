-- Schema đầy đủ của MT5 Copy Bridge.
--
-- File này là migration số 1 và là bản mô tả schema chính thức.
--
-- Cho tới lần triển khai thật đầu tiên (phase 10), sửa thẳng file này là hợp lệ — chưa có
-- database nào ngoài các file tạm của test. **Sau lần triển khai thật đầu tiên** thì file này
-- đóng băng, và mọi thay đổi phải đi qua `bridge/db/migrations/NNN_*.sql`.
--
-- Các ràng buộc ở đây là cơ chế chống copy trùng CUỐI CÙNG. Logic ứng dụng có thể sai,
-- ràng buộc DB thì không.

-- ---------------------------------------------------------------------------------------------
-- Pragma. Phải áp dụng lại mỗi lần mở kết nối — SQLite không nhớ `foreign_keys` giữa các phiên.
-- ---------------------------------------------------------------------------------------------
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = FULL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- ---------------------------------------------------------------------------------------------
-- agent — mỗi terminal MT5 một dòng.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent (
    agent_id         TEXT    PRIMARY KEY,
    -- CLICKER: tien trinh mo lenh qua giao dien MT5 (D-22). No khong co vi the nao,
    -- khong sinh event, va chi nhan command OPEN_UI.
    role             TEXT    NOT NULL CHECK (role IN ('MASTER', 'CLIENT', 'CLICKER')),
    token_hash       TEXT    NOT NULL,
    account_login    INTEGER,
    broker_server    TEXT,
    terminal_build   INTEGER,
    magic_number     INTEGER NOT NULL,
    enabled          INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    status           TEXT    NOT NULL DEFAULT 'OFFLINE'
                             CHECK (status IN ('OFFLINE', 'ONLINE', 'DEGRADED')),
    -- Lấy từ TerminalInfoInteger(TERMINAL_CONNECTED). Bắt buộc phải có: trạng thái "agent còn
    -- sống nhưng terminal mất kết nối sàn" trông giống hệt trạng thái khoẻ mạnh nếu chỉ nhìn
    -- heartbeat. status = DEGRADED chính là trường hợp này.
    broker_connected INTEGER CHECK (broker_connected IS NULL OR broker_connected IN (0, 1)),
    last_seen_at     TEXT,
    last_seq         INTEGER NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
    latency_ms       INTEGER,
    equity           REAL,
    margin_level     REAL,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------------------------
-- client_account — cấu hình nghiệp vụ từng Client.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS client_account (
    client_id            TEXT    PRIMARY KEY,
    agent_id             TEXT    NOT NULL REFERENCES agent(agent_id),
    display_name         TEXT,
    enabled              INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    copy_mode            TEXT    NOT NULL DEFAULT 'OPPOSITE'
                                 CHECK (copy_mode IN ('SAME', 'OPPOSITE')),
    volume_multiplier    REAL    NOT NULL DEFAULT 1.0 CHECK (volume_multiplier > 0),
    rounding_mode        TEXT    NOT NULL DEFAULT 'DOWN'
                                 CHECK (rounding_mode IN ('DOWN', 'NEAREST')),
    below_min_policy     TEXT    NOT NULL DEFAULT 'SKIP'
                                 CHECK (below_min_policy IN ('SKIP', 'USE_MIN')),
    -- Mặc định TẮT (D-20). Bật là cho phép Client đóng ngược Master và kéo theo cascade.
    can_close_master     INTEGER NOT NULL DEFAULT 0 CHECK (can_close_master IN (0, 1)),
    -- Kenh mo lenh (D-21). 'EA' la duong cu dung OrderSend, ra DEAL_REASON_EXPERT.
    -- 'UI' di qua giao dien MT5 de ra DEAL_REASON_CLIENT.
    open_route           TEXT    NOT NULL DEFAULT 'EA' CHECK (open_route IN ('EA', 'UI')),
    clicker_agent_id     TEXT    REFERENCES agent(agent_id),
    open_fail_policy     TEXT    NOT NULL DEFAULT 'RETRY'
                                 CHECK (open_fail_policy IN ('ALERT_ONLY', 'RETRY',
                                                             'RETRY_CLOSE_MASTER')),
    max_retry            INTEGER NOT NULL DEFAULT 3 CHECK (max_retry >= 0),
    retry_interval_ms    INTEGER NOT NULL DEFAULT 200 CHECK (retry_interval_ms >= 0),
    max_volume_per_order REAL    CHECK (max_volume_per_order IS NULL OR max_volume_per_order > 0),
    max_total_volume     REAL    CHECK (max_total_volume IS NULL OR max_total_volume > 0),
    max_open_pairs       INTEGER CHECK (max_open_pairs IS NULL OR max_open_pairs > 0),
    max_spread_points    INTEGER CHECK (max_spread_points IS NULL OR max_spread_points >= 0),
    max_deviation_points INTEGER NOT NULL DEFAULT 20 CHECK (max_deviation_points >= 0),
    max_event_age_ms     INTEGER NOT NULL DEFAULT 5000 CHECK (max_event_age_ms > 0),
    created_at           TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL,

    -- Bat duong giao dien ma khong chi dinh clicker la mot cau hinh vo nghia:
    -- lenh se khong bao gio gui duoc di dau. Chan tai DB.
    CHECK (open_route = 'EA' OR clicker_agent_id IS NOT NULL)
);

-- ---------------------------------------------------------------------------------------------
-- symbol_map — ánh xạ symbol giữa hai sàn, có override cấp symbol.
-- copy_mode và volume_multiplier NULL nghĩa là KẾ THỪA từ client_account.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS symbol_map (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id         TEXT    NOT NULL REFERENCES client_account(client_id) ON DELETE CASCADE,
    master_symbol     TEXT    NOT NULL,
    client_symbol     TEXT    NOT NULL,
    enabled           INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    copy_mode         TEXT    CHECK (copy_mode IS NULL OR copy_mode IN ('SAME', 'OPPOSITE')),
    volume_multiplier REAL    CHECK (volume_multiplier IS NULL OR volume_multiplier > 0),
    -- Chỉ cho lưu khi đã kiểm tra với sàn Client (phase 9). NULL = chưa kiểm tra.
    verified_at       TEXT,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    UNIQUE (client_id, master_symbol)
);

-- ---------------------------------------------------------------------------------------------
-- symbol_spec — thông số broker do agent đẩy lên.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS symbol_spec (
    agent_id      TEXT    NOT NULL REFERENCES agent(agent_id) ON DELETE CASCADE,
    symbol        TEXT    NOT NULL,
    digits        INTEGER,
    point         REAL,
    volume_min    REAL,
    volume_max    REAL,
    volume_step   REAL,
    contract_size REAL,
    tick_value    REAL,
    tick_size     REAL,
    filling_mode  INTEGER,
    trade_mode    INTEGER,
    updated_at    TEXT    NOT NULL,
    PRIMARY KEY (agent_id, symbol)
);

-- ---------------------------------------------------------------------------------------------
-- master_position — mỗi vị thế Master một dòng.
-- Khoá là POSITION_IDENTIFIER, KHÔNG phải ticket (D-06).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS master_position (
    master_position_id INTEGER PRIMARY KEY,
    ticket             INTEGER,
    agent_id           TEXT    NOT NULL REFERENCES agent(agent_id),
    symbol             TEXT    NOT NULL,
    direction          TEXT    NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    initial_volume     REAL    NOT NULL CHECK (initial_volume > 0),
    current_volume     REAL    NOT NULL CHECK (current_volume >= 0),
    open_price         REAL,
    open_time          TEXT,
    close_time         TEXT,
    magic              INTEGER,
    status             TEXT    NOT NULL CHECK (status IN ('OPEN', 'CLOSED', 'UNPAIRED')),
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------------------------
-- pair — bảng trung tâm. Mỗi (vị thế Master, Client) một dòng.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pair (
    pair_id               TEXT    PRIMARY KEY,
    master_position_id    INTEGER NOT NULL REFERENCES master_position(master_position_id),
    client_id             TEXT    NOT NULL REFERENCES client_account(client_id),
    client_position_id    INTEGER,
    client_ticket         INTEGER,
    client_symbol         TEXT,
    client_direction      TEXT    CHECK (client_direction IS NULL
                                         OR client_direction IN ('BUY', 'SELL')),
    copy_mode             TEXT    NOT NULL CHECK (copy_mode IN ('SAME', 'OPPOSITE')),
    master_initial_volume REAL    NOT NULL CHECK (master_initial_volume > 0),
    client_initial_volume REAL    CHECK (client_initial_volume IS NULL
                                         OR client_initial_volume > 0),
    master_current_volume REAL    NOT NULL CHECK (master_current_volume >= 0),
    client_current_volume REAL    CHECK (client_current_volume IS NULL
                                         OR client_current_volume >= 0),
    -- Tỷ lệ THỰC TẾ sau làm tròn, khoá tại thời điểm mở cặp và dùng cho mọi phép tính đóng
    -- một phần về sau (D-19). NOT NULL là cố ý: không có cặp nào được tồn tại mà chưa khoá tỷ lệ.
    effective_multiplier  REAL    NOT NULL CHECK (effective_multiplier > 0),
    status                TEXT    NOT NULL
                                  CHECK (status IN ('PENDING_OPEN', 'OPEN', 'PARTIALLY_CLOSED',
                                                    'CLOSING', 'CLOSED', 'OPEN_FAILED',
                                                    'ORPHANED')),
    orphan_side           TEXT    CHECK (orphan_side IS NULL
                                         OR orphan_side IN ('MASTER', 'CLIENT')),
    open_time_master      TEXT,
    open_time_client      TEXT,
    close_time_master     TEXT,
    close_time_client     TEXT,
    close_source          TEXT    CHECK (close_source IS NULL
                                         OR close_source IN ('MASTER', 'CLIENT', 'BOT',
                                                             'BROKER', 'MANUAL')),
    -- The tuong quan cho lenh mo qua giao dien (D-23). Tieu thu MOT LAN trong cua so cho
    -- khop lenh roi thoi; khong phai nguon su that lau dai (D-07b).
    open_tag              TEXT,
    -- DEAL_REASON cua deal mo vi the Client. Bien muc tieu cua phase 6b thanh mot gia tri
    -- DO DUOC va doi chieu duoc, thay vi mot niem tin. Khac CLIENT tren duong UI -> CRITICAL.
    client_open_reason    INTEGER,
    last_event_id         TEXT,
    retry_count           INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    error_code            INTEGER,
    error_message         TEXT,
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL,

    -- Ràng buộc quan trọng nhất số 1: một vị thế Master không được sinh hai pair cho cùng
    -- một Client. Bảo vệ khi khởi động lại giữa chừng hoặc khi sự kiện đến hai lần.
    UNIQUE (master_position_id, client_id)
);

-- Ràng buộc quan trọng nhất số 2: một vị thế Client không được thuộc về hai pair.
-- Index một phần vì client_position_id còn NULL trong lúc pair ở trạng thái PENDING_OPEN —
-- nhiều cặp đang chờ mở thì đều NULL và phải được phép cùng tồn tại.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pair_client_pos
    ON pair(client_id, client_position_id)
    WHERE client_position_id IS NOT NULL;

-- ---------------------------------------------------------------------------------------------
-- event — nhật ký sự kiện, giữ 30 ngày (D-17).
--
-- event_id UNIQUE chống xử lý hai lần. UNIQUE (agent_id, seq) giúp phát hiện lỗ hổng sau khi
-- agent nối lại. volume_after là trạng thái do agent báo — Bridge không tự trừ (D-14).
-- caused_by_command_id NULL nghĩa là người dùng hoặc broker gây ra, khác NULL nghĩa là do
-- chính bot gây ra và KHÔNG được lan truyền (D-08).
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id             TEXT    NOT NULL UNIQUE,
    agent_id             TEXT    NOT NULL REFERENCES agent(agent_id),
    seq                  INTEGER NOT NULL CHECK (seq >= 0),
    type                 TEXT    NOT NULL
                                 CHECK (type IN ('position_opened', 'position_closed',
                                                 'position_changed', 'order_rejected')),
    position_id          INTEGER,
    pair_id              TEXT    REFERENCES pair(pair_id),
    caused_by_command_id TEXT,
    -- NULL chỉ hợp lệ với `order_rejected` — event đó không sinh từ deal nào.
    deal_entry           TEXT    CHECK (deal_entry IS NULL
                                        OR deal_entry IN ('IN', 'OUT', 'INOUT', 'OUT_BY')),
    volume_delta         REAL,
    volume_after         REAL,
    price                REAL,
    payload_json         TEXT,
    ts_agent             TEXT,
    received_at          TEXT    NOT NULL,
    processed_at         TEXT,
    process_status       TEXT    NOT NULL DEFAULT 'PENDING'
                                 CHECK (process_status IN ('PENDING', 'DONE', 'IGNORED', 'ERROR')),
    process_error        TEXT,
    UNIQUE (agent_id, seq)
);

-- ---------------------------------------------------------------------------------------------
-- command — outbox. Không bao giờ gửi một command chưa có trong bảng này.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS command (
    command_id         TEXT    PRIMARY KEY,
    target_agent_id    TEXT    NOT NULL REFERENCES agent(agent_id),
    pair_id            TEXT    REFERENCES pair(pair_id),
    -- OPEN_UI la loai RIENG, khong tai dung OPEN. Neu dinh tuyen sai ma EA nhan OPEN,
    -- no se LANG LE dat lenh EXPERT - dung thu phase 6b ton tai de lam cho bat kha thi.
    -- Voi OPEN_UI, EA roi vao nhanh mac dinh va tra 'rejected' (D-22).
    type               TEXT    NOT NULL
                               CHECK (type IN ('OPEN', 'OPEN_UI', 'CLOSE', 'CLOSE_PARTIAL',
                                               'REQUEST_SNAPSHOT')),
    payload_json       TEXT,
    status             TEXT    NOT NULL DEFAULT 'PENDING'
                               CHECK (status IN ('PENDING', 'SENT', 'ACK_OK', 'ACK_FAILED',
                                                 'TIMEOUT', 'CANCELLED')),
    attempt            INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    retcode            INTEGER,
    retmsg             TEXT,
    executed_volume    REAL,
    result_position_id INTEGER,
    deadline_at        TEXT,
    sent_at            TEXT,
    acked_at           TEXT,
    created_at         TEXT    NOT NULL,
    updated_at         TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------------------------
-- reconcile_finding — sai lệch phát hiện khi đối chiếu.
-- Bảng này phải tồn tại vì danh sách sai lệch cần sống sót qua việc người vận hành đóng
-- trình duyệt giữa chừng.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reconcile_finding (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             TEXT    NOT NULL,
    severity           TEXT    NOT NULL CHECK (severity IN ('SAFE', 'DECISION')),
    kind               TEXT    NOT NULL,
    pair_id            TEXT    REFERENCES pair(pair_id),
    master_position_id INTEGER,
    client_id          TEXT,
    -- Chứa CẢ BA nguồn: DB nói gì, Master thực tế, Client thực tế. Người vận hành phải thấy
    -- được bằng chứng để tự phán đoán, không chỉ thấy kết luận.
    evidence_json      TEXT,
    suggested_action   TEXT,
    resolution         TEXT    NOT NULL DEFAULT 'PENDING'
                               CHECK (resolution IN ('PENDING', 'ACCEPTED', 'SKIPPED', 'MANUAL')),
    resolved_at        TEXT,
    resolved_note      TEXT,
    created_at         TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------------------------
-- alert — việc con người phải xử lý.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alert (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    level           TEXT    NOT NULL
                            CHECK (level IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    code            TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    pair_id         TEXT    REFERENCES pair(pair_id),
    agent_id        TEXT    REFERENCES agent(agent_id),
    context_json    TEXT,
    acknowledged_at TEXT,
    created_at      TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------------------------
-- system_config — key/value, sửa nóng từ dashboard.
-- Khác với config.toml: config.toml là cấu hình khởi động, đổi phải khởi động lại tiến trình.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- ---------------------------------------------------------------------------------------------
-- pair_id_seq — bộ đếm sinh Pair ID, reset theo ngày.
-- Lấy trong cùng giao dịch tạo pair để hai luồng không sinh trùng số.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pair_id_seq (
    day         TEXT    PRIMARY KEY,
    last_number INTEGER NOT NULL CHECK (last_number >= 0)
);

-- ---------------------------------------------------------------------------------------------
-- Index
-- ---------------------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_mpos_status   ON master_position(status) WHERE status <> 'CLOSED';
CREATE INDEX IF NOT EXISTS idx_pair_open     ON pair(status)
    WHERE status NOT IN ('CLOSED', 'OPEN_FAILED');
CREATE INDEX IF NOT EXISTS idx_pair_master   ON pair(master_position_id);
CREATE INDEX IF NOT EXISTS idx_pair_open_tag ON pair(open_tag) WHERE open_tag IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_event_pending ON event(process_status)
    WHERE process_status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_event_pair    ON event(pair_id);
CREATE INDEX IF NOT EXISTS idx_event_time    ON event(received_at);
CREATE INDEX IF NOT EXISTS idx_cmd_inflight  ON command(status)
    WHERE status IN ('PENDING', 'SENT');
CREATE INDEX IF NOT EXISTS idx_cmd_pair      ON command(pair_id);
CREATE INDEX IF NOT EXISTS idx_alert_open    ON alert(created_at) WHERE acknowledged_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_finding_open  ON reconcile_finding(run_id)
    WHERE resolution = 'PENDING';

-- ---------------------------------------------------------------------------------------------
-- Giá trị khởi tạo của system_config.
-- INSERT OR IGNORE để chạy lại migration không ghi đè giá trị người vận hành đã sửa.
-- run_mode = PAUSED là bắt buộc (D-15): không có đường tự động sang RUNNING.
-- ---------------------------------------------------------------------------------------------
INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
    ('run_mode',                   'PAUSED', '1970-01-01T00:00:00.000Z'),
    ('cascade_wait_master_ms',     '15000',  '1970-01-01T00:00:00.000Z'),
    ('cascade_on_partial_close',   '0',      '1970-01-01T00:00:00.000Z'),
    ('closeby_remainder_action',   'ALERT',  '1970-01-01T00:00:00.000Z'),
    ('offline_reopen_policy',      'NONE',   '1970-01-01T00:00:00.000Z'),
    ('max_reopen_slippage_points', '0',      '1970-01-01T00:00:00.000Z'),
    ('event_retention_days',       '30',     '1970-01-01T00:00:00.000Z'),
    ('heartbeat_interval_ms',      '1000',   '1970-01-01T00:00:00.000Z'),
    ('heartbeat_timeout_ms',       '5000',   '1970-01-01T00:00:00.000Z'),
    ('reconcile_interval_sec',     '60',     '1970-01-01T00:00:00.000Z'),
    -- Duong mo lenh qua giao dien (phase 6b)
    ('ui_open_deadline_ms',        '15000',  '1970-01-01T00:00:00.000Z'),
    ('ui_correlate_grace_ms',      '10000',  '1970-01-01T00:00:00.000Z'),
    ('ui_fallback_match',          'STRICT', '1970-01-01T00:00:00.000Z'),
    ('ui_degraded_fallback',       'SKIP',   '1970-01-01T00:00:00.000Z'),
    ('ui_mismatch_action',         'ALERT',  '1970-01-01T00:00:00.000Z');
