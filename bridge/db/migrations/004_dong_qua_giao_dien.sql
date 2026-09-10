-- 004 — duong DONG phia Client chuyen sang giao dien MT5.
--
-- Ly do: DEAL_REASON do may chu broker gan theo KENH gui lenh. Moi lenh qua OrderSend() deu ra
-- EXPERT; chi lenh qua giao dien desktop moi ra CLIENT. Phase 6b da doi duong MO vi ly do do
-- nhung co y de duong DONG lai tren OrderSend (D-21), voi lap luan rang ben kiem tra chi nhin
-- vi the / lenh mo. Lap luan do khong con dung: yeu cau moi la deal DONG cung phai la CLIENT.
--
-- Hai thay doi, va ca hai deu la thay doi HOP DONG chu khong phai them cho chua:
--
-- 1. `command.type` nhan them CLOSE_UI va CLOSE_UI_PARTIAL. SQLite khong sua duoc CHECK, nen
--    phai dung lai bang. Bang `command` khong duoc bang nao tham chieu toi (no chi tham chieu
--    RA agent va pair), nen viec nay an toan voi khoa ngoai dang bat.
--
--    Hai loai tach doi thay vi mot loai co volume tuy chon, va do la de chan mot loi mat tien
--    IM LANG: mot lenh dong mot phan roi mat truong volume ma van duoc chap nhan se thanh dong
--    han. Khong co gi trong hop thoai bao dong - no chi dong nhieu hon phan dang le phai dong.
--
-- 2. `pair.client_close_reason` — bien muc tieu thanh mot gia tri DO DUOC, dung cach
--    `client_open_reason` da lam cho duong mo. Khong co cot nay thi khong co cach nao chung
--    minh yeu cau da dat, chi co cach tin la da dat.

ALTER TABLE pair ADD COLUMN client_close_reason INTEGER;

CREATE TABLE command_moi (
    command_id         TEXT    PRIMARY KEY,
    target_agent_id    TEXT    NOT NULL REFERENCES agent(agent_id),
    pair_id            TEXT    REFERENCES pair(pair_id),
    type               TEXT    NOT NULL
                               CHECK (type IN ('OPEN', 'OPEN_UI', 'CLOSE', 'CLOSE_PARTIAL',
                                               'CLOSE_UI', 'CLOSE_UI_PARTIAL',
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

INSERT INTO command_moi (command_id, target_agent_id, pair_id, type, payload_json, status,
                         attempt, retcode, retmsg, executed_volume, result_position_id,
                         deadline_at, sent_at, acked_at, created_at, updated_at)
SELECT command_id, target_agent_id, pair_id, type, payload_json, status,
       attempt, retcode, retmsg, executed_volume, result_position_id,
       deadline_at, sent_at, acked_at, created_at, updated_at
FROM command;

DROP TABLE command;

ALTER TABLE command_moi RENAME TO command;

-- DROP TABLE xoa luon index cua no, nen phai dung lai ca ba: hai tu schema.sql va mot tu 002.
CREATE INDEX IF NOT EXISTS idx_cmd_inflight ON command(status)
    WHERE status IN ('PENDING', 'SENT');
CREATE INDEX IF NOT EXISTS idx_cmd_pair ON command(pair_id);
CREATE INDEX IF NOT EXISTS idx_command_dang_bay ON command(pair_id, status);

-- `close_route` la cot rieng chu khong tai dung `open_route`, va do KHONG phai cho du thua.
--
-- Hai duong co the o hai trang thai khac nhau mot cach hop ly: mot Client dang chay duong mo
-- qua giao dien co the tam thoi phai dong bang EA trong khi do lai hop thoai dong tren mot san
-- moi. Gop chung mot cot thi khong dien dat duoc trang thai do, va nguoi van hanh se phai tat
-- ca hai duong de tat mot duong.
--
-- Mac dinh 'EA' de viec nang cap khong tu doi hanh vi cua bat ky Client nao dang chay. Bat
-- duong moi la mot hanh dong co y thuc, dung cach `open_route` da lam o phase 6b.
ALTER TABLE client_account ADD COLUMN close_route TEXT NOT NULL DEFAULT 'EA'
    CHECK (close_route IN ('EA', 'UI'));

-- `close_degraded_fallback` mac dinh 'EA', NGUOC voi `ui_degraded_fallback` mac dinh 'SKIP'.
-- Su nguoc nhau do la co y va la cho dien dat mot khac biet that: khong MO duoc thi an toan
-- (mat mot co hoi, thay duoc, sua duoc), con khong DONG duoc thi khong an toan (vi the tran,
-- phoi nhiem tien that, khong tu het). Dat 'SKIP' o day nghia la chap nhan giu vi the tran khi
-- clicker hong, va do phai la lua chon co y thuc.
INSERT OR IGNORE INTO system_config (key, value, updated_at) VALUES
    ('close_degraded_fallback',      'EA',   '1970-01-01T00:00:00.000Z'),
    ('ui_close_correlate_grace_ms',  '5000', '1970-01-01T00:00:00.000Z');
