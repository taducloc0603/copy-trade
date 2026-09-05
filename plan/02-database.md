# Phase 2 — Database và tầng truy cập dữ liệu

## Mục tiêu

Dựng schema SQLite hoàn chỉnh và tầng repository. Các ràng buộc trong schema là cơ chế
chống copy trùng cuối cùng — logic ứng dụng có thể sai, ràng buộc DB thì không.

## Điều kiện đầu vào

Phase 1 xong. `pytest` chạy sạch.

---

## Việc cần làm

### 2.1 Schema

Tạo `bridge/db/schema.sql`. Nội dung đầy đủ theo đặc tả dưới đây.

**Pragma bắt buộc**, đặt ngay đầu file và áp dụng lại mỗi lần mở kết nối:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous  = FULL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
```

`synchronous = FULL` là cố ý. Chậm hơn `NORMAL` nhưng đảm bảo giao dịch đã commit sống sót
qua mất điện đột ngột. Đây là tiền thật, không đánh đổi độ bền lấy tốc độ.

**Các bảng:**

`agent` — mỗi terminal MT5 một dòng.
`agent_id` TEXT PK, `role` CHECK IN ('MASTER','CLIENT','CLICKER'), `token_hash`, `account_login`,
`broker_server`, `terminal_build`, `magic_number` NOT NULL, `enabled`, `status`
CHECK IN ('OFFLINE','ONLINE','DEGRADED'), `broker_connected` INTEGER, `last_seen_at`,
`last_seq` DEFAULT 0, `latency_ms`, `equity`, `margin_level`, `created_at`, `updated_at`.

> `broker_connected` lấy từ `TerminalInfoInteger(TERMINAL_CONNECTED)`. Bắt buộc phải có,
> vì trạng thái "agent còn sống nhưng terminal mất kết nối sàn" trông giống hệt trạng thái
> khoẻ mạnh nếu chỉ nhìn heartbeat. `status = DEGRADED` chính là trường hợp này.

`client_account` — cấu hình nghiệp vụ từng Client.
`client_id` PK, `agent_id` FK, `display_name`, `enabled`,
`open_route` CHECK IN ('EA','UI') DEFAULT 'EA', `clicker_agent_id` FK NULL,
`copy_mode` CHECK IN ('SAME','OPPOSITE') DEFAULT 'OPPOSITE',
`volume_multiplier` REAL CHECK > 0 DEFAULT 1.0,
`rounding_mode` CHECK IN ('DOWN','NEAREST') DEFAULT 'DOWN',
`below_min_policy` CHECK IN ('SKIP','USE_MIN') DEFAULT 'SKIP',
`can_close_master` INTEGER DEFAULT 0,
`open_fail_policy` CHECK IN ('ALERT_ONLY','RETRY','RETRY_CLOSE_MASTER') DEFAULT 'RETRY',
`max_retry` DEFAULT 3, `retry_interval_ms` DEFAULT 200,
`max_volume_per_order`, `max_total_volume`, `max_open_pairs`, `max_spread_points`,
`max_deviation_points` DEFAULT 20, `max_event_age_ms` DEFAULT 5000,
`created_at`, `updated_at`.

`symbol_map` — ánh xạ symbol, có override cấp symbol.
`id` PK AUTOINCREMENT, `client_id` FK ON DELETE CASCADE, `master_symbol`, `client_symbol`,
`enabled`, `copy_mode` NULL nghĩa là kế thừa, `volume_multiplier` NULL nghĩa là kế thừa,
`verified_at` (chỉ cho lưu khi đã kiểm tra với sàn — xem phase 9), `created_at`, `updated_at`.
`UNIQUE (client_id, master_symbol)`.

`symbol_spec` — thông số broker do agent đẩy lên.
PK kép `(agent_id, symbol)`. Các cột: `digits`, `point`, `volume_min`, `volume_max`,
`volume_step`, `contract_size`, `tick_value`, `tick_size`, `filling_mode`, `trade_mode`, `updated_at`.

`master_position` — mỗi vị thế Master một dòng.
`master_position_id` INTEGER PK (là `POSITION_IDENTIFIER`, không phải ticket), `ticket`,
`agent_id` FK, `symbol`, `direction` CHECK IN ('BUY','SELL'), `initial_volume`,
`current_volume`, `open_price`, `open_time`, `close_time`, `magic`,
`status` CHECK IN ('OPEN','CLOSED','UNPAIRED'), `created_at`, `updated_at`.

`pair` — bảng trung tâm. Mỗi (vị thế Master, Client) một dòng.
`pair_id` TEXT PK dạng `PAIR-YYYYMMDD-NNNNNN`, `master_position_id` FK, `client_id` FK,
`client_position_id`, `client_ticket`, `client_symbol`, `client_direction`,
`copy_mode`, `master_initial_volume`, `client_initial_volume`,
`master_current_volume`, `client_current_volume`, `effective_multiplier`,
`status` CHECK IN ('PENDING_OPEN','OPEN','PARTIALLY_CLOSED','CLOSING','CLOSED','OPEN_FAILED','ORPHANED'),
`orphan_side` CHECK IN ('MASTER','CLIENT'),
`open_tag`, `client_open_reason`,
`open_time_master`, `open_time_client`, `close_time_master`, `close_time_client`,
`close_source`, `last_event_id`, `retry_count`, `error_code`, `error_message`,
`created_at`, `updated_at`.

Hai ràng buộc **quan trọng nhất trong toàn dự án**:

```sql
UNIQUE (master_position_id, client_id)

CREATE UNIQUE INDEX idx_pair_client_pos
    ON pair(client_id, client_position_id)
    WHERE client_position_id IS NOT NULL;
```

Cái thứ nhất chặn một vị thế Master sinh hai pair cho cùng một Client. Cái thứ hai chặn
một vị thế Client thuộc về hai pair. Cả hai đều bảo vệ khi khởi động lại giữa chừng hoặc
khi sự kiện đến hai lần.

`event` — nhật ký sự kiện, giữ 30 ngày.
`id` INTEGER PK AUTOINCREMENT, `event_id` TEXT UNIQUE, `agent_id` FK, `seq` INTEGER,
`type`, `position_id`, `pair_id` FK, `caused_by_command_id`, `deal_entry`,
`volume_delta`, `volume_after`, `price`, `payload_json`, `ts_agent`, `received_at`,
`processed_at`, `process_status` CHECK IN ('PENDING','DONE','IGNORED','ERROR'), `process_error`.
`UNIQUE (agent_id, seq)`.

> `event_id UNIQUE` chống xử lý hai lần. `UNIQUE (agent_id, seq)` giúp phát hiện lỗ hổng
> sau khi agent nối lại. `volume_after` là trạng thái do agent báo — Bridge không tự trừ (D-14).
> `caused_by_command_id` NULL nghĩa là người dùng hoặc broker gây ra, khác NULL nghĩa là
> do chính bot gây ra và **không được lan truyền** (D-08).

`command` — outbox.
`command_id` TEXT PK, `target_agent_id` FK, `pair_id` FK,
`type` CHECK IN ('OPEN','OPEN_UI','CLOSE','CLOSE_PARTIAL','REQUEST_SNAPSHOT'),
`payload_json`, `status` CHECK IN ('PENDING','SENT','ACK_OK','ACK_FAILED','TIMEOUT','CANCELLED'),
`attempt`, `retcode`, `retmsg`, `executed_volume`, `result_position_id`,
`deadline_at`, `sent_at`, `acked_at`, `created_at`, `updated_at`.

`reconcile_finding` — sai lệch phát hiện khi đối chiếu.
`id` PK AUTOINCREMENT, `run_id` TEXT, `severity` CHECK IN ('SAFE','DECISION'),
`kind` (ví dụ `MASTER_CLOSED_OFFLINE`, `CLIENT_CLOSED_OFFLINE`, `UNPAIRED_MASTER`,
`BOTH_CLOSED`, `ACK_LOST`), `pair_id`, `master_position_id`, `client_id`,
`evidence_json` (chứa cả ba nguồn: DB nói gì, Master thực tế, Client thực tế),
`suggested_action`, `resolution` CHECK IN ('PENDING','ACCEPTED','SKIPPED','MANUAL'),
`resolved_at`, `resolved_note`, `created_at`.

> Bảng này phải tồn tại vì danh sách sai lệch cần sống sót qua việc người vận hành
> đóng trình duyệt giữa chừng.

`alert` — việc con người phải xử lý.
`id` PK, `level` CHECK IN ('INFO','WARNING','ERROR','CRITICAL'), `code`, `message`,
`pair_id`, `agent_id`, `context_json`, `acknowledged_at`, `created_at`.

`system_config` — key/value, sửa nóng.
Giá trị khởi tạo:

```
run_mode                 = PAUSED
cascade_wait_master_ms   = 15000
cascade_on_partial_close = 0
closeby_remainder_action = ALERT
offline_reopen_policy    = NONE
max_reopen_slippage_points = 0
event_retention_days     = 30
heartbeat_interval_ms    = 1000
heartbeat_timeout_ms     = 5000
reconcile_interval_sec   = 60
```

**Index cần có:**
```sql
CREATE INDEX idx_mpos_status    ON master_position(status) WHERE status <> 'CLOSED';
CREATE INDEX idx_pair_open      ON pair(status) WHERE status NOT IN ('CLOSED','OPEN_FAILED');
CREATE INDEX idx_pair_master    ON pair(master_position_id);
CREATE INDEX idx_event_pending  ON event(process_status) WHERE process_status = 'PENDING';
CREATE INDEX idx_event_pair     ON event(pair_id);
CREATE INDEX idx_event_time     ON event(received_at);
CREATE INDEX idx_cmd_inflight   ON command(status) WHERE status IN ('PENDING','SENT');
CREATE INDEX idx_cmd_pair       ON command(pair_id);
CREATE INDEX idx_alert_open     ON alert(created_at) WHERE acknowledged_at IS NULL;
CREATE INDEX idx_finding_open   ON reconcile_finding(run_id) WHERE resolution = 'PENDING';
```

### 2.2 Migration runner

`bridge/db/migrations.py`. Bảng `schema_version(version INTEGER, applied_at TEXT)`.
Chạy tuần tự các file `migrations/NNN_*.sql`. Migration đầu tiên là toàn bộ schema ở trên.
Idempotent: chạy hai lần không lỗi.

### 2.3 Tầng repository

`bridge/db/repo.py`. Không dùng ORM, viết SQL trực tiếp.

Yêu cầu:
- Một lớp `Database` giữ kết nối, áp pragma, cung cấp context manager giao dịch.
- Hàm theo nghiệp vụ, không phải CRUD chung chung. Ví dụ:
  `create_pending_pair()`, `mark_pair_open()`, `record_event()`, `claim_next_pending_event()`,
  `find_pair_by_client_position()`, `list_pairs_needing_attention()`.
- **Mọi hàm ghi phải nằm trong một giao dịch.** Không có ghi lẻ.
- `record_event()` phải xử lý xung đột `event_id` bằng cách trả về bản ghi cũ, không ném exception.
  Đây là cách dedup (D-08, FR-31).

### 2.4 Sinh Pair ID

Hàm sinh `PAIR-YYYYMMDD-NNNNNN` với bộ đếm reset theo ngày, lấy từ DB trong cùng giao dịch
tạo pair để tránh đụng độ. Không dùng UUID — Pair ID phải đọc được bằng mắt trên dashboard và trong log.

### 2.5 Dọn dẹp

`bridge/db/retention.py`:
- Xuất `event` và `command` cũ hơn `event_retention_days` sang `data/archive/YYYY-MM.db`
  **trước khi** xoá khỏi DB nóng.
- Chỉ xoá `event` có `process_status IN ('DONE','IGNORED')` và `command` có
  `status IN ('ACK_OK','CANCELLED')`. Không bao giờ xoá bản ghi còn đang treo.
- **Không bao giờ xoá `pair` hoặc `master_position` theo thời gian** (D-17).

---

## Kiểm tra lại phần cũ

- [ ] `ruff check .` vẫn sạch.
- [ ] Test của phase 1 vẫn xanh.
- [ ] `docs/DECISIONS.md` vẫn khớp với những gì vừa cài đặt. Nếu lệch, sửa code chứ không sửa tài liệu.

## Kiểm tra phần mới

Viết test cho từng mục dưới đây. Đây là những test quan trọng nhất của cả dự án.

- [ ] Chạy migration hai lần liên tiếp không lỗi.
- [ ] `PRAGMA foreign_keys` thực sự bằng 1 sau khi mở kết nối (SQLite tắt mặc định — dễ quên).
- [ ] Chèn hai `pair` cùng `(master_position_id, client_id)` → **phải** lỗi ràng buộc.
- [ ] Chèn hai `pair` cùng `(client_id, client_position_id)` → **phải** lỗi.
- [ ] Chèn hai `pair` cùng `client_id` với `client_position_id = NULL` → **phải thành công**
      (hai cặp đang chờ mở thì chưa có position id).
- [ ] Chèn hai `event` cùng `event_id` → `record_event()` trả về bản ghi cũ, không ném exception.
- [ ] Chèn hai `event` cùng `(agent_id, seq)` → phải lỗi.
- [ ] Mọi giá trị enum sai đều bị `CHECK` chặn: thử `pair.status = 'BANANA'` phải lỗi.
- [ ] `volume_multiplier = 0` và `= -1` đều bị chặn.
- [ ] Sinh 1000 Pair ID liên tiếp: không trùng, đúng định dạng, đúng ngày.
- [ ] Retention: tạo event cũ và mới, chạy dọn dẹp, kiểm tra event cũ có trong file archive
      và đã biến mất khỏi DB nóng, event mới còn nguyên, `pair` không bị động tới.
- [ ] Retention không xoá event có `process_status = 'PENDING'` dù đã quá hạn.

## Tiêu chí hoàn thành

Có thể tạo một database trống, chạy migration, và bằng các hàm repository dựng lên một cặp lệnh
hoàn chỉnh từ trạng thái `PENDING_OPEN` tới `CLOSED` — toàn bộ trong test, chưa cần mạng.

## Không làm ở phase này

Không viết code mạng. Không viết logic tính volume. Không viết dashboard.
