# Tiến độ

## Trạng thái các phase

| Phase | Tên | Trạng thái | Ngày |
|---|---|---|---|
| 1 | Khởi tạo | xong | 2026-09-04 |
| 2 | Database | xong | 2026-09-04 |
| 3 | Giao thức và TCP server | xong | 2026-09-04 |
| 4 | EA phía Master | chưa bắt đầu | |
| 5 | EA phía Client và thực thi lệnh | chưa bắt đầu | |
| 6 | Luồng mở lệnh | chưa bắt đầu | |
| 7 | Luồng đóng lệnh | chưa bắt đầu | |
| 8 | Mất kết nối và đối chiếu | chưa bắt đầu | |
| 9 | Dashboard và cấu hình | chưa bắt đầu | |
| 10 | Đóng gói, vận hành và nghiệm thu | chưa bắt đầu | |

## Nhật ký

### Phase 1

- **Đã làm:**
  - Dựng cây thư mục: `bridge/` (kèm `db/ protocol/ engine/ web/` để trống, có `.gitkeep`),
    `ea/`, `tests/`, `docs/`, `data/`, `logs/`.
  - Môi trường: cài Python 3.12.10, tạo `.venv`, cài `pydantic`, `fastapi`, `uvicorn`,
    `pytest`, `pytest-asyncio`, `ruff` qua `pip install -e ".[dev]"`.
  - `pyproject.toml`: ruff line-length 110 (rule `E,F,W,I,UP,B`), pytest `asyncio_mode = "auto"`,
    `pythonpath = ["."]`, metadata dự án.
  - `.gitignore`: `data/`, `logs/`, `.venv/`, `__pycache__/`, `*.ex5`, `*.db`, `*.db-wal`,
    `*.db-shm`, `config.toml`.
  - `bridge/logging_setup.py`: 4 mức, console + `TimedRotatingFileHandler` theo ngày giữ 30 bản,
    timestamp ISO 8601 có mili giây kèm offset, formatter tự chèn `pair_id`/`event_id`,
    `RedactingFilter` che token/mật khẩu.
  - `bridge/labels_vi.py`: 7 nhóm nhãn theo đúng đặc tả + `ALL_GROUPS` + hàm `label()`
    không ném exception.
  - `bridge/config.py`: đọc `config.toml` bằng `tomllib`, kiểm tra port/host/db_path,
    `SecretSection` che giá trị `[security]` khi `repr()`. `config.example.toml` được commit.
  - Tài liệu: `README.md` (58 dòng, yêu cầu dưới 60), `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` (20 mục,
    đã đối chiếu nguyên văn với `plan/00-README.md` bằng script), `docs/GLOSSARY.md`,
    `docs/CONVENTIONS.md`, `PROGRESS.md`.
  - Test: `tests/conftest.py`, `tests/test_labels.py`, `tests/test_logging_setup.py`,
    `tests/test_config.py` — **48 test, tất cả xanh**. `ruff check .` sạch.

- **Lệch so với plan:**
  1. **Gốc dự án là thư mục hiện tại, không tạo thêm cấp `mt5-copy-bridge/`.** Plan vẽ cây
     thư mục có gốc tên `mt5-copy-bridge/` chứa `plan/` bên trong, nhưng `plan/` đã nằm sẵn ở
     thư mục làm việc nên tạo thêm một cấp là thừa. Đã được người chủ dự án xác nhận trước khi làm.
  2. **Phải cài Python trước.** Máy chưa có Python; đã cài 3.12.10 cho user hiện tại qua
     `winget install Python.Python.3.12 --scope user`. Plan giả định Python có sẵn.
  3. **Viết thêm hai file test ngoài yêu cầu:** `tests/test_logging_setup.py` và
     `tests/test_config.py`. Plan chỉ yêu cầu `tests/test_labels.py`, nhưng `logging_setup.py`
     và `config.py` cũng là code của phase 1 nên không để không có test — đặc biệt là hai hành vi
     "không log token" và "cấu hình sai thì dừng ngay".
  4. **`CONTEXT_FIELDS` có 4 trường, không phải 2.** Plan yêu cầu `pair_id` và `event_id`;
     đã thêm sẵn `command_id` và `agent_id` vì phase 3 và 6 chắc chắn cần. Không có chi phí gì
     nếu chưa dùng tới.
  5. **`docs/CONVENTIONS.md` nói rõ chú thích và docstring viết bằng tiếng Việt.** Plan nói
     "tiếng Việt chỉ xuất hiện trong `bridge/labels_vi.py` và các template giao diện" — đã diễn
     giải rằng D-16 chi phối chuỗi hướng tới người dùng và giá trị máy đọc (enum, log, message
     giao thức), không chi phối chú thích. Nếu ý ban đầu là chặt hơn thì báo lại, sửa sớm rẻ hơn.
  6. **Thư mục con của `bridge/` dùng `.gitkeep`, chưa có `__init__.py`.** Tránh tạo package
     rỗng cho phase chưa tới; phase 2 và 3 sẽ tự thêm `__init__.py` của mình.

- **Vấn đề còn treo:**
  - `config.toml` thật chưa được tạo (mới chỉ có `config.example.toml`). Chưa cần cho tới
    phase 3, khi Bridge bắt đầu mở socket.
  - Chưa có `docs/RUNBOOK.md`, `docs/ACCEPTANCE.md`, `docs/BACKLOG.md` — đúng phạm vi,
    ba file này thuộc phase 10.

- **Phát hiện sớm (ghi lại, không xử lý ở phase này):**
  1. **`config.toml` cần chỗ cho token của từng agent.** Phase 3 xác thực agent bằng cách so hash
     với `agent.token_hash` trong DB, nhưng phase 10 lại nói giá trị thô đặt trong `config.toml`.
     Cần chốt ở phase 3: `config.toml` giữ token thô để cấp phát/thu hồi, DB chỉ giữ hash.
     `SecretSection` đã sẵn sàng cho việc này.
  2. **`system_config` (phase 2) và `config.toml` dễ bị lẫn.** Đã ghi ranh giới vào docstring của
     `bridge/config.py`: `config.toml` là cấu hình khởi động (đổi phải restart), `system_config`
     là cấu hình nghiệp vụ sửa nóng. Giữ đúng ranh giới này khi làm phase 2.
  3. **Log xoay vòng theo ngày giữ 30 bản trùng con số với `event_retention_days = 30`.**
     Hai thứ độc lập; nếu phase 10 đổi một cái thì đừng đổi cái kia theo phản xạ.
  4. **Chưa có cách chạy Bridge như một tiến trình** (`bridge/__main__.py` hay entry point).
     Sẽ cần từ phase 3 trở đi; phase 10 mới đóng gói thành dịch vụ.
  5. **`pytest-asyncio` đã cài và `asyncio_mode = "auto"` đã bật nhưng chưa có test async nào.**
     Cấu hình mới thực sự được kiểm chứng ở phase 3.

### Phase 2

- **Đã làm:**
  - `bridge/db/schema.sql`: đủ 11 bảng nghiệp vụ (`agent`, `client_account`, `symbol_map`,
    `symbol_spec`, `master_position`, `pair`, `event`, `command`, `reconcile_finding`, `alert`,
    `system_config`) + `pair_id_seq`, đủ 10 index theo đặc tả, 4 pragma, và 10 giá trị khởi tạo
    của `system_config`.
  - Hai ràng buộc quan trọng nhất đã có và **đã được test là thật sự chặn**:
    `UNIQUE (master_position_id, client_id)` và index một phần
    `idx_pair_client_pos ON pair(client_id, client_position_id) WHERE client_position_id IS NOT NULL`.
  - `bridge/db/migrations.py`: runner idempotent, mỗi migration chạy trong một giao dịch,
    bảng `schema_version`.
  - `bridge/db/repo.py`: lớp `Database` (pragma + giao dịch **lồng nhau được**) và các hàm
    theo nghiệp vụ: `create_pending_pair`, `mark_pair_open`, `mark_pair_closed`, `record_event`,
    `claim_next_pending_event`, `find_pair_by_client_position`, `list_pairs_needing_attention`,
    `next_pair_id`, cùng các hàm upsert/đọc cho agent, client, symbol map/spec, command, alert,
    system_config.
  - `bridge/db/retention.py` + `bridge/db/archive_schema.sql`: xuất `event`/`command` quá hạn
    sang `data/archive/YYYY-MM.db` rồi mới xoá, tách file theo tháng.
  - `bridge/clock.py`: chuẩn thời gian dùng chung (UTC, ISO 8601, mili giây, hậu tố `Z`).
  - Test: `tests/test_db_schema.py` (40), `tests/test_repo.py` (26), `tests/test_retention.py` (9).
    **Tổng toàn dự án 123 test, tất cả xanh.** `ruff check .` sạch.

- **Lệch so với plan:**
  1. **`schema.sql` chính là migration version 1**, không tạo thêm bản chép ở
     `migrations/001_*.sql`. Plan yêu cầu cả hai; giữ một bản duy nhất vì hai bản chép tay
     chắc chắn sẽ lệch nhau. `migrations/` vẫn tồn tại và nhận file từ version 2 trở đi.
  2. **Thêm bảng `pair_id_seq`** ngoài danh sách bảng của plan. Cần một bộ đếm reset theo ngày
     đúng ngay cả khi `next_pair_id()` được gọi mà pair chưa được chèn.
  3. **Thêm module `bridge/clock.py`** (không có trong plan). Phase 2 cần một chuẩn timestamp
     duy nhất; để rải rác `datetime.now()` trong repo và retention là cách sinh lệch múi giờ.
  4. **Thêm `bridge/db/archive_schema.sql`** (không có trong plan). Bảng archive có khoá chính
     để `INSERT OR IGNORE` làm việc chạy lại retention an toàn.
  5. **`event.type` và `event.deal_entry` KHÔNG có `CHECK`.** Plan phase 2 ghi rõ `CHECK IN (...)`
     ở mọi cột nó muốn ràng buộc, và hai cột này không có. Danh sách giá trị hợp lệ nằm ở phase 3,
     nên siết ở đây là viết code cho phase sau. Xem mục "phát hiện sớm" số 1.
  6. **`Database` dùng `sqlite3` đồng bộ**, chưa dùng `aiosqlite`. Ngăn xếp ở plan cho phép cả
     hai; phase 3 sẽ gọi tầng này qua executor.
  7. **Retention chép và xoá bằng HAI giao dịch tách rời**, không phải một. SQLite không cam kết
     giao dịch nguyên tử xuyên nhiều database khi database chính chạy WAL — mà D-04 bắt buộc WAL.
     Thứ tự chép-trước-xoá-sau được giữ đúng, và bước xoá chỉ xoá dòng đã xác nhận có mặt trong
     archive, nên gián đoạn giữa chừng chỉ gây trùng chứ không gây mất.
  8. **Repo có nhiều hàm hơn sáu hàm plan nêu tên.** Plan chỉ liệt kê ví dụ, còn tiêu chí hoàn
     thành đòi dựng được một cặp lệnh từ `PENDING_OPEN` tới `CLOSED` — cần thêm các hàm cho
     command, alert, master_position, symbol spec/map.

- **Vấn đề còn treo:**
  - Chưa có `config.toml` thật (từ phase 1, chưa cần tới phase 3).
  - `bridge/protocol/`, `bridge/engine/`, `bridge/web/` vẫn trống — đúng phạm vi.

- **Phát hiện sớm (ghi lại, không xử lý ở phase này):**
  1. **`event.type` và `event.deal_entry` cần `CHECK` ở phase 3**, khi danh sách giá trị đã chốt:
     type ∈ (`position_opened`, `position_closed`, `position_changed`, `order_rejected`),
     deal_entry ∈ (`IN`, `OUT`, `INOUT`, `OUT_BY`). Thêm bằng `migrations/002_*.sql`.
  2. **`claim_next_pending_event()` là "xem trước", không phải "giành lấy" thật.** Schema không
     có trạng thái `IN_PROGRESS`, nên hàm chỉ chọn event `PENDING` cũ nhất; nơi gọi phải chốt
     bằng `mark_event_processed()`. Đúng với phase 6 (xử lý tuần tự theo từng agent), nhưng nếu
     sau này chạy nhiều worker thì phải thêm trạng thái.
  3. **`agent.account_login` chưa `UNIQUE`.** Phase 3 yêu cầu "một token chỉ dùng cho đúng một
     tài khoản MT5" và kiểm tra `account_login` khi bắt tay — cân nhắc thêm ràng buộc DB ở đó
     thay vì chỉ kiểm tra bằng code.
  4. **`pair.last_event_id` cố ý KHÔNG có khoá ngoại tới `event`.** Event bị dọn sau 30 ngày còn
     pair thì sống mãi (D-17); có FK thì retention sẽ không xoá được. Đừng "sửa" chỗ này ở phase sau.
  5. **Retention xoá dòng nhưng không thu nhỏ file.** File `bridge.db` sẽ không teo lại sau khi
     dọn. Phase 10 dùng `VACUUM INTO` cho sao lưu, việc đó xử lý luôn phần này.
  6. **Chưa có công việc định kỳ gọi `run_retention()`.** Hàm đã sẵn sàng, lịch chạy hàng ngày
     thuộc phase 10.

### Phase 3

- **Đã làm:**
  - `bridge/protocol/framing.py`: bộ đệm NDJSON chịu được message bị cắt, message dính nhau,
    giới hạn 256 KB một dòng, giải mã UTF-8, dòng hỏng chỉ bị bỏ qua.
  - `bridge/protocol/messages.py`: schema pydantic v2 cho 6 message agent→bridge và 5 message
    bridge→agent. Hai ràng buộc bảo vệ D-14 nằm ở đây: `position_closed`/`position_changed`
    bắt buộc có `volume_after`, mọi event sinh từ deal bắt buộc có `deal_entry` và `position_id`.
  - `bridge/protocol/auth.py`: băm token bằng SHA-256, so bằng `hmac.compare_digest`,
    sinh token 32 byte. Không hàm nào ở đây ghi token ra log.
  - `bridge/protocol/server.py`: `asyncio.start_server`, bắt tay 6 bước, phát hiện lỗ hổng `seq`
    và gửi `resend`, heartbeat + `broker_connected` → ONLINE/DEGRADED/OFFLINE, alert chỉ tạo
    khi **chuyển** trạng thái.
  - `bridge/protocol/dispatcher.py`: outbox ghi-trước-gửi-sau, command cho agent offline nằm lại
    `PENDING`, quét hạn chuyển `SENT` quá hạn sang `TIMEOUT` kèm alert.
  - `tests/mock_agent.py`: TCP client giả lập EA — bắt tay, bơm event với `seq` tự đặt (tạo lỗ
    hổng hoặc trùng), gửi byte thô, trả ack với `retcode` chỉ định, giữ vị thế trong bộ nhớ để
    trả lời `snapshot`, mô phỏng ngắt kết nối đột ngột, có sẵn bộ nhớ `command_id` đã xử lý
    cho phase 5.
  - Siết `CHECK` cho `event.type` và `event.deal_entry` trong `schema.sql` — xử lý xong mục
    "phát hiện sớm" số 1 của phase 2.
  - Test: `test_framing.py` (13), `test_messages.py` (34), `test_server.py` (26),
    `test_dispatcher.py` (13). **Tổng toàn dự án 211 test, tất cả xanh.** `ruff check .` sạch.

- **Lệch so với plan:**
  1. **Siết `CHECK` bằng cách sửa thẳng `schema.sql`, không tạo `migrations/002_*.sql`.**
     Chưa có database nào được triển khai thật nên chưa cần migration; đã sửa phần đầu
     `schema.sql` nói rõ file này đóng băng **sau** lần triển khai thật đầu tiên (phase 10).
  2. **Trường chiều lệnh trong `event.data` tên là `direction`, không phải `type`.** Phase 4
     của plan liệt kê trường `type` trong event, nhưng `type` đã là loại event rồi. Đặt tên
     `direction` để EA ở phase 4 không phải đoán. **EA phải theo tên này.**
  3. **Không có message ack cho event.** Plan mục 3.4 viết "seq cũ thì bỏ qua nhưng vẫn phải trả
     về ack xử lý cũ", nhưng bảng message ở 3.2 không có loại message nào để làm việc đó — chỉ
     command mới có ack. Đã hiểu là "không xử lý lại", và `record_event()` dedup lo phần đó.
     Nếu ý ban đầu là cần một message `event_ack` thật thì phải bổ sung vào giao thức ở phase 4.
  4. **Mọi lời gọi database ở tầng mạng đều đồng bộ**, không qua executor. `Database` giữ một
     kết nối với bộ đếm giao dịch lồng nhau; `await` giữa `BEGIN` và `COMMIT` sẽ làm hỏng bộ đếm
     khi có hai tác vụ chen nhau. Gọi đồng bộ loại bỏ hẳn lớp lỗi đó. Xem "phát hiện sớm" số 3.
  5. **`_advance_last_seq` đẩy `last_seq` theo chuỗi liên tục**, không chỉ gán bằng `seq` vừa
     nhận. Plan chỉ nói "`last_seq` chỉ tăng khi event đã ghi thành công"; cách này giữ đúng ý
     đó cả khi event tới lệch thứ tự do gửi bù.
  6. **Thêm hai mã từ chối ngoài plan**: `ROLE_MISMATCH` và `AGENT_DISABLED`. Cùng loại với
     `ACCOUNT_MISMATCH` mà plan đã yêu cầu.
  7. **`command_id` dùng UUID (`CMD-<hex>`), không có bộ đếm trong DB.** Khác Pair ID,
     `command_id` không cần đọc bằng mắt.

- **Vấn đề còn treo:**
  - Chưa có `config.toml` thật. Giờ đã cần: server lấy host/port từ đó khi chạy thật. Chưa chặn
    được test vì test truyền `ServerConfig` trực tiếp.
  - Chưa có cách chạy Bridge như một tiến trình (`bridge/__main__.py`). Vẫn đúng phạm vi —
    phase 6 mới có vòng xử lý nghiệp vụ để chạy.
  - `bridge/engine/` và `bridge/web/` vẫn trống.

- **Phát hiện sớm (ghi lại, không xử lý ở phase này):**
  1. **`_find_agent_by_token()` quét tuyến tính toàn bộ bảng `agent`** và băm một lần cho mỗi
     dòng. Với 1 Master + 1 Client thì không đáng kể; nếu số agent lên vài chục thì đánh index
     theo `token_hash` và tra thẳng.
  2. **`agent.account_login` vẫn chưa `UNIQUE`** (từ phase 2). Phase 3 đã kiểm tra bằng code khi
     bắt tay, nhưng ràng buộc DB vẫn nên có — cân nhắc ở phase 9 khi có màn hình quản lý agent.
  3. **Nếu phase 10 đo thấy DB đồng bộ làm nghẽn vòng lặp sự kiện**, cách sửa đúng là một luồng
     DB riêng với hàng đợi, **không phải** rải `asyncio.to_thread` — vì bộ đếm giao dịch lồng
     nhau của `Database` không an toàn khi nhiều luồng dùng chung.
  4. **`snapshot` mới chỉ được giữ trong bộ nhớ** (`server.latest_snapshots`), chưa ghi DB.
     Đúng phạm vi phase 3; phase 8 sẽ quyết định có cần lưu bền hay không.
  5. **Chưa có task nền gọi `dispatcher.scan_deadlines()`.** Hàm đã sẵn sàng và đã có test, nhưng
     chưa ai gọi định kỳ — gắn vào vòng nền ở phase 6 cùng với `processor.py`.
  6. **`ConfigMessage` và `broadcast_config()` đã có nhưng chưa nơi nào gọi.** Phase 9 sẽ gọi khi
     người vận hành đổi tham số nóng trên dashboard.
