# Tiến độ

## Trạng thái các phase

| Phase | Tên | Trạng thái | Ngày |
|---|---|---|---|
| 1 | Khởi tạo | xong | 2026-09-04 |
| 2 | Database | xong | 2026-09-04 |
| 3 | Giao thức và TCP server | chưa bắt đầu | |
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
