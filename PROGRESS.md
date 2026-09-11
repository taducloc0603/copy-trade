# Tiến độ

## Trạng thái các phase

| Phase | Tên | Trạng thái | Ngày |
|---|---|---|---|
| 1 | Khởi tạo | xong | 2026-09-04 |
| 2 | Database | xong | 2026-09-04 |
| 3 | Giao thức và TCP server | xong | 2026-09-04 |
| 4 | EA phía Master | xong | 2026-09-05 |
| 5 | EA phía Client và thực thi lệnh | xong | 2026-09-05 |
| 6 | Luồng mở lệnh | xong | 2026-09-05 |
| 6b | Mở lệnh qua giao diện MT5 | **xong** | 2026-09-05 |
| 7 | Luồng đóng lệnh | **xong** | 2026-09-05 |
| 8 | Mất kết nối và đối chiếu | **xong** | 2026-09-05 |
| 9 | Dashboard và cấu hình | **phần lớn xong, trang cấu hình mới ở mức đọc** | 2026-09-06 |
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

### Phase 4

> **TRẠNG THÁI: chưa hoàn thành.** Code MQL5 đã viết xong (mục 4.1–4.5), nhưng **toàn bộ 11 mục
> "Kiểm tra phần mới" chưa chạy được** vì máy này không có MetaTrader 5. Không có terminal thì
> không biên dịch được, không chạy được, và không kiểm chứng được điều quan trọng nhất của phase
> này: "một hành động giao dịch, đúng một event". **Không được coi phase 4 là xong.**

- **Đã làm:**
  - `ea/CopyBridgeCommon.mqh` (~1300 dòng), gồm:
    - Socket client với backoff 1s, 2s, 5s, 10s rồi giữ 10s; không chặn luồng chính.
    - Hai hàm bọc UTF-8 `CbUtf8Encode`/`CbUtf8Decode` — **nơi duy nhất** gọi
      `StringToCharArray`/`CharArrayToString`, luôn kèm `CP_UTF8`.
    - Bộ đệm nhận gom byte tới khi gặp `\n`, giới hạn 256 KB khớp với Bridge.
    - `CJsonWriter` + `CJsonReader` viết tay: escape đầy đủ (đặc biệt là newline), parser hiểu
      chuỗi, escape `\uXXXX`, và object/array lồng nhau.
    - Hàng đợi cục bộ `MQL5\Files\copybridge\<login>_outbox.ndjson`, **ghi file trước, gửi
      socket sau**; cắt phần đã được `hello_ack.last_seq` xác nhận; gửi bù khi nhận `resend`.
    - `seq` bền qua khởi động lại, lưu ở `<login>_state.json`.
    - Bộ nhớ `command_id` đã thực thi (mảng + file, giữ 24 giờ); nhận lại command trùng thì trả
      **ack cũ nguyên văn**.
    - Khung `caused_by_command_id`: `RememberCause()` / `CauseFor()` với cửa sổ 10 giây.
      Phase 4 chỉ cài sẵn, dùng thật ở phase 7.
    - `CbProcessTransaction()`: **chỉ xử lý `TRADE_TRANSACTION_DEAL_ADD`**, phân nhánh đủ bốn
      giá trị `deal.entry`, phân biệt đóng toàn phần với một phần bằng `PositionSelectByTicket()`,
      luôn gửi `volume_after` thật (D-14).
  - `ea/CopyBridgeMaster.mq5`: `AgentRole = MASTER`, `EventSetMillisecondTimer(100)` (không dựa
    vào `OnTick`), từ chối khởi động nếu tài khoản không ở chế độ Hedging, dòng trạng thái trên
    chart (kết nối Bridge, kết nối sàn, `seq`, số event trong hàng đợi).
  - `tests/test_ea_protocol_contract.py` (24 test): đối chiếu **hai chiều** giữa mã nguồn MQL5 và
    schema pydantic — mọi khoá JSON EA ghi ra đều phải có nghĩa với Bridge, và mỗi loại message
    EA gửi phải được schema chấp nhận. Cộng thêm các test đọc mã nguồn để khoá lại các quy tắc
    của phase 4 (chỉ `DEAL_ADD`, ghi-trước-gửi-sau, `CP_UTF8`, timer thay `OnTick`, không
    `OrderSend`, không ký tự ngoài ASCII trong file MQL5).
  - **Tổng 235 test xanh**, `ruff check .` sạch.

- **Lệch so với plan:**
  1. **Mã nguồn MQL5 và mọi chú thích trong đó viết bằng tiếng Anh không dấu**, khác quy ước
     "chú thích tiếng Việt" ở `docs/CONVENTIONS.md`. MetaEditor và các bản build MT5 xử lý
     encoding file nguồn không thống nhất; dấu tiếng Việt trong `.mqh` là nguồn lỗi biên dịch
     rất khó tìm. Đã có test khoá lại việc này.
  2. **Thêm `tests/test_ea_protocol_contract.py`** (không có trong plan). Không thay được test
     trên terminal thật, nhưng bắt được lỗi "EA và Bridge nói lệch nhau" mà không cần MT5.
  3. **Trường chiều lệnh tên `direction`**, đúng như đã chốt ở phase 3 (plan phase 4 gọi nó là
     `type`).
  4. **`event_id` dạng `EVT-<account_login>-<seq>`**, không phải `EVT-<agent>-<seq>`. EA không
     biết `agent_id` cho tới khi nhận `hello_ack`, mà `event_id` phải sinh được cả khi Bridge
     đang chết. `account_login` luôn có sẵn và cũng là duy nhất.
  5. **Thêm kiểm tra tài khoản Hedging trong `OnInit`.** Plan không yêu cầu, nhưng mục 2 của
     `00-README.md` nói rõ chỉ hỗ trợ Hedging — chặn ngay lúc khởi động rẻ hơn nhiều so với
     phát hiện qua một event `INOUT` giữa phiên.

- **Vấn đề còn treo:**
  1. **CHƯA CÓ MT5 TRÊN MÁY.** Cần cài MetaTrader 5 và mở một tài khoản **demo** trước khi chạy
     được 11 mục kiểm tra của phase 4. Đây là lựa chọn của người chủ dự án (chọn broker nào,
     tài khoản demo nào), không nên tự quyết.
  2. **Code MQL5 chưa từng được biên dịch.** Rủi ro cụ thể còn lại: sai tên hàm hoặc sai chữ ký
     API mà không có compiler bắt. Ba lỗi loại này đã tự tìm và sửa trong lúc viết
     (`TimeGDT` → `TimeGMT`; `HistorySelect` phải dùng `TimeCurrent()` chứ không phải giờ GMT;
     `StringToInteger()` không đọc được chuỗi hex nên phải tự parse `\uXXXX`), nhưng **không có
     gì đảm bảo đã hết**.
  3. **Chưa ghi được hành vi close-by của broker.** Mục kiểm tra cuối của phase 4 yêu cầu ghi
     lại chính xác broker xử lý phần dư thế nào (đóng cả hai và tạo vị thế mới, hay đóng một phần
     vị thế lớn). **Phase 7 cần thông tin này.** Chưa có terminal nên chưa ghi được.
  4. Chưa có `config.toml` thật; chưa có `bridge/__main__.py` (từ phase 3).

- **Phát hiện sớm (ghi lại, không xử lý ở phase này):**
  1. **`CbNowIso()` lấy phần mili giây từ `GetTickCount() % 1000`**, không đồng bộ với phần giây
     của `TimeGMT()`. Đủ để đo độ trễ tương đối, nhưng **không được dùng làm khoá hay để so sánh
     thứ tự**. Nếu phase 9 muốn hiển thị độ trễ copy chính xác tới mili giây thì phải đo ở phía
     Bridge, không tin `ts_agent`.
  2. **`SendSymbolSpecs()` dựng một chuỗi JSON cho toàn bộ Market Watch trong một message.**
     Market Watch vài trăm symbol có thể vượt giới hạn 256 KB một dòng. Nếu gặp, phải chia lô —
     và khi đó giao thức cần một trường đánh dấu "còn tiếp".
   3. **`CauseFor()` dọn danh sách nguyên nhân mỗi lần gọi.** Với cửa sổ 10 giây và tần suất deal
     thực tế thì danh sách luôn rất ngắn, nhưng đây là chỗ nếu phase 7 gọi trong vòng lặp nóng
     thì cần xem lại.
  4. **EA chưa dùng `MagicNumber` để lọc event.** Đúng phạm vi: Master phải báo **mọi** vị thế,
     kể cả lệnh mở tay, để Bridge phân biệt (FR-12). Đừng "sửa" chỗ này thành lọc theo magic.

### Phase 4 — nghiệm thu (2026-09-05)

Phần code đã ghi ở mục trên. Mục này ghi kết quả **chạy thật trên MT5**, sau khi máy đã cài
hai terminal. Trạng thái phase 4 chuyển từ "chưa nghiệm thu" thành **xong**.

- **Môi trường nghiệm thu:**
  - Hai terminal MT5: `MetaTrader 5 1` (tài khoản **538216**) và `MetaTrader 5 2` (**538217**),
    cả hai trên **Connext-Demo**. Đã xác nhận là demo qua log `authorized on Connext-Demo`.
  - Phase 4 chỉ dùng terminal 1. Terminal 2 để dành cho phase 5.
  - Market Watch chỉ có **2 symbol**: `BTCUSD.s`, `XAUUSD.s`.
  - **Biên dịch: 0 lỗi, 0 cảnh báo** (MetaEditor64 `/compile`).

- **Kết quả 11 mục kiểm tra:**

  | # | Mục | Kết quả |
  |---|---|---|
  | 1 | Kết nối, `hello_ack`, agent ONLINE | ĐẠT |
  | 2 | Mở tay → **đúng một** event `position_opened` | ĐẠT — 11 lần mở, mỗi lần đúng 1 |
  | 3 | Đóng tay → đúng một `position_closed`, `volume_after = 0` | ĐẠT — 11 lần đóng |
  | 4 | Đóng một phần 30% → `volume_after` = phần còn lại thật | ĐẠT — `delta=0.03` → `volume_after=0.07` |
  | 5 | Chạm SL → vẫn đúng một event đóng | ĐẠT |
  | 6 | Tắt Bridge, giao dịch, bật lại → gửi bù đủ, đúng thứ tự | ĐẠT — 8 event tồn, về đủ |
  | 7 | Tắt EA rồi bật lại → `seq` tiếp tục, không reset | ĐẠT — restart 12:07:44, `seq` tiếp từ 15 |
  | 8 | Mất kết nối sàn → `broker_connected=false`, DEGRADED | ĐẠT — xảy ra thật 11:44:39, alert ERROR |
  | 9 | Symbol có ký tự ngoài ASCII | **KHÔNG KIỂM CHỨNG ĐƯỢC** — xem dưới |
  | 10 | Close By → `deal_entry = OUT_BY` | **KHÔNG KIỂM CHỨNG ĐƯỢC** — xem dưới |
  | 11 | Tiêu chí hoàn thành: event khớp lịch sử terminal | ĐẠT — **23 deal ↔ 23 event, khớp 1-1** |

  Phân loại 23 event: 11 `position_opened`, 11 `position_closed`, 1 `position_changed`.
  `seq` liên tục 1..23, không lỗ hổng, không trùng. Độ trễ từ lúc terminal khớp tới lúc Bridge
  ghi vào DB: **11–21ms**.

- **Ba kết quả phụ đáng ghi:**
  1. **Ba lần sửa SL sinh ra 0 event.** Sửa SL/TP không tạo deal, nên bộ lọc chỉ nhận
     `TRADE_TRANSACTION_DEAL_ADD` hoạt động đúng. Nếu lọc sai thì đây đã là 3 event rác.
  2. **Lệnh `XAUUSD.s` bị từ chối `[Market closed]` sinh ra 0 event.** Không có deal thì không
     có sự kiện — EA không bịa event từ lệnh thất bại.
  3. **`filling_mode` EA báo lên khớp với terminal.** EA gửi `filling_mode = 1` (FOK) cho
     `BTCUSD.s`; hộp thoại đặt lệnh của terminal ghi `Fill policy: Fill or Kill`.

- **Hai lỗi thật tìm được khi chạy thật và đã sửa:**
  1. **`latency_ms` âm (−761ms).** `CbNowIso()` lấy mili giây từ `GetTickCount() % 1000`, không
     liên quan gì tới phần giây của `TimeGMT()`. Đã neo `GetTickCount()` vào đúng thời điểm giây
     nhảy. Sau khi sửa: +14ms, +26ms, +66ms.
  2. **Mỗi event bị gửi hai lần mỗi lần nối lại.** EA tự gửi bù khi thấy `hello_ack.last_seq`
     thấp hơn `seq` của mình, **và** Bridge cũng gửi `resend`. Ràng buộc `event_id UNIQUE` bắt
     hết nên DB vẫn đúng, nhưng đó là ràng buộc cứu chứ không phải thiết kế. Đã bỏ đường tự gửi
     bù ở EA, trả việc đó về cho Bridge đúng như plan mục 3.4. **Đã kiểm chứng lại sau khi sửa:
     event 23 được ghi đúng 1 lần, 0 lần dedup.**

  > Lỗi số 2 cũng là lần đầu cơ chế dedup (D-08, FR-31) bị thử bằng một tình huống gửi trùng
  > **thật** chứ không phải test dựng sẵn. Nó đứng vững: 8 event gửi hai lần, DB có đúng 8 dòng.

  Ngoài ra một lỗi biên dịch: `CJsonReader::Parse()` thiếu `return` ở cuối — trình biên dịch
  MQL5 không suy luận được rằng `while(true)` chỉ thoát bằng `return`.

- **Vấn đề còn treo:**
  1. **Mục #10 (Close By) không kiểm chứng được — broker Connext-Demo không hỗ trợ.** Đã xác
     nhận bằng cách mở hai vị thế ngược chiều cùng symbol rồi mở hộp thoại đặt lệnh: danh sách
     loại lệnh chỉ có `Market Execution`, `Limit Order`, `Stop Order`, `Stop Limit Order`, không
     có `Close By`.
     **→ Đây là RỦI RO ĐÃ BIẾT cho phase 7.** D-12 phải được cài đặt mà **không có dữ liệu thực
     nghiệm** về việc broker xử lý phần dư thế nào. Mục 7.7 của plan yêu cầu tham khảo ghi chép
     từ phase 4; ghi chép đó là dòng này. Cách xử lý đề xuất: cài đặt theo đúng D-12 (đóng 2 pair
     theo `position_id`, đối chiếu ngay, phần dư chỉ cảnh báo và KHÔNG tự copy) — vốn đã là
     phương án an toàn nhất khi không biết hành vi broker — và kiểm chứng lại nếu sau này đổi
     sang broker có hỗ trợ.
  2. **Mục #9 (symbol ngoài ASCII) không kiểm chứng được** — broker chỉ có `BTCUSD.s` và
     `XAUUSD.s`, đều ASCII thuần. Phần xử lý UTF-8 đã được kiểm chứng ở tầng Python
     (`test_ky_tu_ngoai_ascii_di_qua_nguyen_ven`) nhưng **chưa qua đường EA thật**. Ghi là chưa
     kiểm chứng đầu-cuối, không ghi là đạt.
  3. **`XAUUSD.s` không test được vào cuối tuần** (`[Market closed]`). Mục kiểm tra "nhiều
     symbol đồng thời" của phase 6 phải chờ ngày thường.
  4. `config.toml` thật đã tạo. Token của `AG-MASTER` đang nằm trong
     `MQL5\Presets\CopyBridgeMaster.set` của terminal 1.

- **Phát hiện sớm (bổ sung sau khi chạy thật):**
  1. **`ts_agent` chỉ chính xác tới ~1 giây trong thực tế.** Sau khi sửa, `CbNowIso()` neo lại
     mỗi khi `TimeGMT()` nhảy giây, mà heartbeat gọi nó mỗi giây — nên phần mili giây gần như
     luôn về 0. Giá trị không còn **sai** (không còn âm) nhưng độ phân giải thấp. **Phase 9 đo
     "độ trễ copy" phải tính ở phía Bridge** (`open_time_master` → `open_time_client` do Bridge
     ghi), không được tin `ts_agent`.
  2. **Cấp phát agent/token đang làm bằng script tạm trong scratchpad.** Phase 9 hoặc 10 phải
     đưa việc này vào sản phẩm (màn hình quản lý agent, hoặc lệnh CLI), kèm thu hồi token.
  3. **Deal id của MT5 là toàn cục theo trade server, không liên tục theo tài khoản.** Trong
     phiên nghiệm thu có lúc deal id nhảy từ 19279031 sang 19279042. **Đừng bao giờ dùng
     khoảng trống deal id để suy ra "có deal bị mất"** — dùng `seq` của agent, đó mới là chuỗi
     liên tục theo tài khoản.
  4. **Thêm `bridge/__main__.py`** (ngoài plan) để chạy `python -m bridge`. Chỉ nối các thành
     phần của phase 1–3, không có logic nghiệp vụ mới. Phase 6 sẽ thêm vòng xử lý event và
     `scan_deadlines()` vào đây.

### Phase 5

- **Đã làm:**
  - `ea/CopyBridgeClient.mq5`: lớp `CClientAgent` kế thừa `CBridgeAgent`, thực thi `OPEN`,
    `CLOSE`, `CLOSE_PARTIAL`. Không copy-paste dòng nào từ EA Master — toàn bộ phần bắt sự kiện,
    heartbeat, hàng đợi, symbol specs dùng lại nguyên vẹn từ `CopyBridgeCommon.mqh`.
  - Tự chọn filling mode theo `SYMBOL_FILLING_MODE`, thứ tự FOK → IOC → RETURN, thử lại **đúng
    một lần** khi `retcode = 10030`.
  - Hàng rào an toàn phía EA (5.4), đủ bốn mục: hạn lệnh đã qua, `magic` lệch, `volume` ≤ 0,
    `symbol` không tồn tại. Thêm một mục ngoài plan: từ chối khi Auto Trading đang tắt.
  - **Sửa thứ tự ghi bộ nhớ command trong `CopyBridgeCommon.mqh`.** Bản phase 4 gọi
    `RememberCommand()` **sau** khi thực thi; plan 5.2 yêu cầu ghi file **trước** khi gọi
    `OrderSend`. Đã tách thành `ReserveCommand()` (giữ chỗ, ack rỗng) và `SetCommandAck()`
    (ghi kết quả). File bộ nhớ command là append-only, khi đọc lại thì dòng sau thắng dòng trước.
  - `tests/mock_agent.py` mở rộng (5.5): giữ danh sách vị thế thật, mô phỏng `OPEN`/`CLOSE`/
    `CLOSE_PARTIAL`, `already_closed`, ép `retcode` bất kỳ, độ trễ khớp lệnh, nhận command trùng,
    và áp cùng bộ hàng rào an toàn như EA thật.
  - `tests/test_client_execution.py`: **26 test mới**. Tổng toàn dự án **261 test xanh**,
    `ruff check .` sạch. Cả hai EA biên dịch **0 lỗi, 0 cảnh báo**.

- **Nghiệm thu trên hai terminal demo thật** (538216 Master, 538217 Client, Connext-Demo),
  chạy bằng `scratchpad/phase5_acceptance.py` — **20/20 mục đạt**:

  | Mục kiểm tra | Kết quả |
  |---|---|
  | `OPEN` → Client mở đúng symbol, chiều, volume, magic | ĐẠT |
  | **Gửi lại cùng `command_id` → không mở lệnh thứ hai** | ĐẠT |
  | **Khởi động lại EA rồi gửi lại cùng `command_id` → vẫn không mở lệnh thứ hai** | ĐẠT |
  | `CLOSE` vị thế đã đóng → `already_closed`, không phải ERROR | ĐẠT |
  | `CLOSE_PARTIAL` volume lớn hơn phần còn lại → đóng hết, ack ghi đúng `executed_volume` | ĐẠT — yêu cầu 5.0, thực đóng 0.03 |
  | Command quá hạn → EA từ chối, không đặt lệnh | ĐẠT (sau khi sửa lỗi, xem dưới) |
  | `magic` lệch → từ chối | ĐẠT |
  | `volume` = 0 → từ chối | ĐẠT |
  | Symbol không tồn tại → ack lỗi, không sập EA | ĐẠT |
  | Ép lỗi → ack mang `retcode` nguyên bản | ĐẠT — `10014 Invalid volume` |
  | `caused_by_command_id` trên event do command sinh ra | ĐẠT — 10/10 event |

  **Hồi quy EA Master sau khi file dùng chung thay đổi**: nạp lại EA Master, mở và đóng một lệnh
  → đúng 2 event. Đối chiếu toàn phiên: **25 deal ↔ 25 event, khớp 1-1**, không thiếu không thừa
  không trùng. Tính chất "một hành động, một event" vẫn nguyên.

- **Lỗi thật tìm được khi chạy trên terminal thật và đã sửa:**
  1. **Hàng rào "lệnh quá hạn" không chặn được lệnh quá hạn.** Gửi command với hạn 1ms, EA vẫn
     thực thi và mở lệnh thật (`retmsg = "Request executed"`). Nguyên nhân: MQL5 không có đồng hồ
     thực theo mili giây nên `CbIsoToTime()` cắt bỏ phần lẻ; hạn `08:10:00.001` thành `08:10:00`,
     bằng đúng `TimeGMT()` lúc đó, nên phép so `>` cho `false`. Đã đổi thành `>=`.
     **26 test Python đều xanh trước khi sửa** — mock agent so chuỗi ISO đầy đủ nên không mất
     phần mili giây như MQL5. Đây là lớp lỗi chỉ terminal thật mới lộ ra.

- **Lệch so với plan:**
  1. **Thêm trạng thái ack `unknown` vào giao thức.** Plan 5.2 mô tả tình huống terminal chết sau
     khi giữ chỗ `command_id` nhưng trước khi biết kết quả: EA không được thực thi lại. Nhưng nó
     cũng không được báo `failed` — Bridge sẽ retry và mở lệnh thứ hai. Bridge ánh xạ `unknown`
     thành `command.status = TIMEOUT` kèm alert **CRITICAL**; `TIMEOUT` đúng nghĩa "không biết",
     và plan 6.6 đã quy định không tự động thử lại sau `TIMEOUT`. **Không phải đổi schema DB.**
  2. **Payload command dùng `direction` thay vì `type` cho chiều lệnh**, nhất quán với `event.data`
     đã chốt ở phase 3. Quy ước xuyên suốt: `type` luôn là *loại* (loại event, loại command),
     `direction` luôn là BUY/SELL.
  3. **Thêm hàng rào thứ năm ngoài bốn mục của 5.4**: từ chối command khi Auto Trading đang tắt.
     Rẻ tiền, và không có nó thì `OrderSend` thất bại với mã lỗi khó hiểu hơn nhiều.
  4. **Ba test cũ của phase 3 phải sửa payload.** Mock agent trước đây là hộp câm nên các test
     dispatcher gửi payload `{"volume": 0.5}` không có symbol. Giờ mock áp hàng rào như EA thật
     nên payload đó bị từ chối đúng. Đã sửa thành payload đầy đủ. **Không sửa dòng code sản phẩm
     nào** — chỉ làm test phản ánh đúng thứ Bridge thật sẽ gửi.
  5. **Test `test_ea_master_khong_dat_lenh` đổi thành `test_chi_ea_client_duoc_dat_lenh`.**
     Ở phase 4 quy tắc là "không EA nào đặt lệnh"; từ phase 5 quy tắc đúng là "chỉ EA Client đặt
     lệnh, file dùng chung và EA Master thì không".

- **Vấn đề còn treo:**
  1. **`retcode = 10019` (thiếu margin) không ép được.** Tài khoản demo có ~1.000.000 USD và
     `BTCUSD.s` chặn ở 10 lot, nên không cách nào làm cạn margin. Đã dùng volume vượt `volume_max`
     để lấy `10014` thay thế — cùng nhóm "dừng hẳn" và chứng minh được `retcode` đi qua nguyên
     vẹn. **Phase 6 vẫn phải cài đặt đúng nhánh 10019 theo bảng ở mục 5.3**, chỉ là chưa có dữ
     liệu thực nghiệm.
  2. **Nhánh dự phòng filling mode IOC/RETURN chưa chạy thật.** Cả hai symbol của broker này chỉ
     hỗ trợ FOK (`filling_mode = 1`), nên `retcode = 10030` không kích hoạt được. Mã có, chưa thử.
  3. Từ phase 4: Close By không kiểm chứng được (broker không hỗ trợ), symbol ngoài ASCII không
     kiểm chứng được, `XAUUSD.s` không test được cuối tuần.

- **Phát hiện sớm (ghi lại, không xử lý ở phase này):**
  1. **Hàng rào hạn lệnh có độ phân giải MỘT GIÂY và sai về phía từ chối.** Khi hạn rơi đúng vào
     giây hiện tại, EA từ chối. Với hạn mặc định 5000ms thì không ảnh hưởng, nhưng **phase 6 đừng
     đặt `deadline_ms` dưới ~2000ms** — command sẽ bị từ chối oan.
  2. **`OnCommand()` của Client chạy đồng bộ trong `OnTimer`.** `OrderSend` chặn tới vài trăm ms
     (đo được 250–340ms trên broker này). Trong lúc đó EA không đọc socket và không gửi heartbeat.
     Với `heartbeat_timeout_ms = 5000` thì an toàn, nhưng nếu phase 7 gửi một chuỗi nhiều command
     liên tiếp thì cần xem lại — hoặc chỉ xử lý một command mỗi lần `Poll()`.
  3. **Bộ nhớ command giữ 24 giờ, nhưng `command_id` là UUID nên file chỉ tăng.** Với tần suất
     giao dịch thật thì không đáng kể; phase 10 kiểm thử tải 24 giờ nên nhìn lại kích thước file
     `<login>_commands.ndjson`.
  4. **Cần script gửi command tay cho tới hết phase 5.** `scratchpad/phase5_acceptance.py` và
     `phase5_restart.py` đóng vai trò đó. Từ phase 6 Bridge tự sinh command nên không cần nữa.

### Phase 6

- **Đã làm:**
  - `bridge/engine/sizing.py`: tám bước tính volume của mục 6.3, **toàn bộ là hàm thuần** —
    không đọc DB, không gửi lệnh. Mọi phép tính chạy bằng `Decimal` khởi tạo từ **chuỗi**;
    `float` chỉ xuất hiện ở biên vào/ra.
  - `bridge/engine/processor.py`: vòng xử lý event tuần tự theo `id`, sáu điều kiện lọc của
    mục 6.2, tạo `pair` + `command` trong **đúng một giao dịch** rồi mới gửi socket, phân loại
    `retcode` thành nhóm retry và nhóm dừng, ba chính sách `open_fail_policy`, timeout →
    `OPEN_FAILED` và **không tự gửi lại** (D-13).
  - Nối hook: `BridgeServer.on_command_acked` (async) và `CommandDispatcher.on_timeout`. Tầng
    giao thức vẫn không biết `pair` là gì — nó chỉ gọi ngược lên tầng nghiệp vụ.
  - `CommandDispatcher.send_existing()`: gửi một command đã có sẵn trong DB, để phase 6 tách
    được bước ghi khỏi bước gửi.
  - `bridge/__main__.py` chạy thêm `EventProcessor`, trong đó có cả vòng quét `scan_deadlines()`
    — xử lý xong mục "phát hiện sớm" số 5 của phase 3.
  - `tests/mock_agent.py`: thêm `retcode_sequence` để dựng kịch bản "hỏng N lần rồi thành công".
  - Test: `test_sizing.py` (34), `test_open_flow.py` (24). **Tổng 319 test xanh**, `ruff` sạch.

- **Nghiệm thu trên hai terminal demo thật** (Master 538216 → Client 538217, khác chiều,
  hệ số 0.5). Bốn lệnh mở tay trên Master:

  | Master | Client | Độ trễ copy |
  |---|---|---|
  | BUY 0.10 | SELL 0.05 | 323 ms |
  | SELL 0.10 | BUY 0.05 | 227 ms |
  | BUY 0.06 | SELL 0.03 | 368 ms |
  | BUY 0.01 | **không copy** — 0.005 làm tròn xuống ra 0.00, dưới `volume_min` → bỏ qua + `VOLUME_BELOW_MIN` (D-18) | — |

  Đối chiếu log terminal Client: đúng **3 deal mới**, không có deal thứ tư. Không event nào
  `PENDING` hay `ERROR` còn lại. **Độ trễ copy 227–368 ms, đạt yêu cầu dưới 1 giây.**

  Ngoài ý muốn nhưng có giá trị: khi Bridge khởi động lần đầu với `run_mode = PAUSED`, nó xử lý
  toàn bộ event tồn từ phase 4–5 và **ghi nhận 13 vị thế Master mà không copy cái nào** — đúng
  hành vi "vẫn ghi nhận nhưng không copy" của mục 6.2, kiểm chứng trên dữ liệu thật.

- **Lệch so với plan:**
  1. **Tuổi sự kiện tính từ `ts_agent`, không phải `received_at`.** Một event gửi bù sau khi
     Bridge chết 20 phút thì `received_at` vẫn mới tinh, mà lệnh thì đã cũ — dùng `received_at`
     sẽ vô hiệu hoá chính hàng rào này (plan 8.3 nói rõ ý đó).
  2. **`deadline_ms` của command OPEN có sàn `MIN_DEADLINE_MS = 2000`.** Plan 6.4 nói
     `deadline_at = now + max_event_age_ms`. Hàng rào hạn lệnh phía EA có độ phân giải một giây
     và sai về phía từ chối (phát hiện ở phase 5), nên `max_event_age_ms` nhỏ sẽ làm EA từ chối
     oan. Với mặc định 5000ms thì không đổi gì.
  3. **Độ trễ copy không được lưu thành cột riêng.** Plan 6.5 nói "tính và ghi độ trễ copy để
     dashboard dùng"; schema không có cột đó. `open_time_master` và `open_time_client` đều đã
     lưu (cả hai theo **đồng hồ Bridge**, không phải `ts_agent`), nên phase 9 tính hiệu là ra —
     không cần đổi schema.
  4. **Vị thế Master được ghi nhận trong MỌI chế độ vận hành**, kể cả `PAUSED`. Ghi sổ không
     phải là hành động giao dịch, và phase 8 cần biết Master đang có gì.

- **Vấn đề còn treo:**
  1. **`master_position` của các vị thế đã đóng vẫn mang `status = OPEN`.** Phase 6 chưa xử lý
     event đóng nên không có gì cập nhật chúng. Sau phiên nghiệm thu, bảng có 16 dòng `OPEN`
     trong khi terminal chỉ còn vài vị thế. **Phase 7 sẽ sửa phần lớn, phần còn lại là việc của
     đối chiếu ở phase 8** — đây chính là loại sai lệch mà `reconcile_finding` sinh ra để bắt.
  2. **Còn 3 cặp đang mở trên hai tài khoản demo** sau nghiệm thu. Phase 6 chưa đồng bộ đóng nên
     đóng Master sẽ **không** đóng Client. Cần đóng tay ở **cả hai** terminal, hoặc để lại làm
     dữ liệu đầu vào cho phase 7.
  3. **`run_mode` đã đặt lại về `PAUSED` sau nghiệm thu.** Để `RUNNING` khi chưa có đồng bộ đóng
     là trạng thái nguy hiểm: mở thì copy, đóng thì không, và cặp thành mất hedge ngay.
  4. Từ các phase trước: `retcode 10019` và nhánh filling IOC/RETURN chưa ép được; Close By
     broker không hỗ trợ; symbol ngoài ASCII không có để thử.

- **Phát hiện sớm (ghi lại, không xử lý ở phase này):**
  1. **`_open_for_client()` chạy tuần tự cho từng Client, và mỗi lần gửi command đều `await`.**
     Với 1 Client thì không sao. Với N Client, Client thứ N phải chờ N−1 lần gửi trước đó — làm
     lệch độ trễ copy giữa các Client. Phase 10 mô phỏng 5 Client sẽ đo được; nếu lệch đáng kể
     thì gửi song song **phần socket** (phần ghi DB vẫn phải tuần tự).
  2. **Retry đang lên lịch bằng `asyncio.create_task` + `sleep`.** Bridge chết giữa lúc chờ thì
     lần retry đó mất, và pair nằm lại `PENDING_OPEN`. Không nguy hiểm (đối chiếu ở phase 8 sẽ
     bắt), nhưng phase 8 phải biết trạng thái này tồn tại.
  3. **`open_fail_policy = RETRY_CLOSE_MASTER` gửi lệnh đóng Master ngay ở phase 6**, trước khi
     phase 7 có luồng đóng đầy đủ. Lệnh đó **không** tạo pair mới và **không** cascade sang
     Client khác — phase 7 phải kiểm tra lại đường này khi cascade đã có, để nó không đi hai lần.
  4. **Chưa có cách tắt copy cho riêng một symbol khi đang chạy** ngoài việc sửa
     `symbol_map.enabled` trực tiếp trong DB. Phase 9 cần nút đó trên giao diện.

### Phase 6b — lập kế hoạch và rà soát (2026-09-05)

Chưa viết dòng code sản phẩm nào. Mục này ghi lại **quyết định đổi hợp đồng**, số liệu đo được,
và kết quả rà soát toàn bộ plan.

- **Yêu cầu mới của người chủ dự án:** lệnh **MỞ** trên Client phải mang `DEAL_REASON_CLIENT`
  chứ không phải `DEAL_REASON_EXPERT`.

  `DEAL_REASON` do **máy chủ broker** gán theo *kênh* gửi lệnh. `MqlTradeRequest` không có trường
  `reason` và MQL5 không có API nào đặt được nó. Không sửa được bằng cách sửa EA — phải đổi kênh.

  Người chủ dự án đã chọn hướng **tự động hoá giao diện MT5**, sau khi được trình bày bốn hướng
  kèm đánh giá. Đã chốt thêm: **chỉ đường MỞ**, đường ĐÓNG vẫn do EA gọi `OrderSend`; bên kiểm tra
  chỉ nhìn vị thế / lệnh mở, mà `POSITION_REASON` lấy từ deal mở nên như vậy là đủ.

- **Ba phép đo trước khi thiết kế** (chỉ đọc, không đặt lệnh nào):

  | | Kết quả |
  |---|---|
  | **E3 — tiền đề** | Tài khoản 538217 tách sạch: 13 deal do EA đặt đều `EXPERT (3)` magic 770001; 5 deal đặt tay đều `CLIENT (0)` magic 0. **Tiền đề đúng.** |
  | **E2 — comment** | Comment `'phase5-A'`, `'phase5-restart'` gửi qua `OrderSend` ở phase 5 **còn nguyên trong `DEAL_COMMENT`**: không cắt, không bị sàn chèn chữ. → khớp theo thẻ dùng được làm đường chính |
  | **E1 — control** | Hộp thoại New Order là dialog `#32770` với **53 control Win32 chuẩn**, control ID ổn định. → `PostMessage` khả thi ⇒ **không cần desktop tương tác** ⇒ bài toán RDP ngắt phiên biến mất |

  Control ID đã lập bản đồ: Volume `10333`, Comment `1001`, Sell by Market `10409`,
  Buy by Market `10408`, Symbol `10331`/`10325`, Fill policy `10339`.

  **Cạm bẫy đã phát hiện:** ctrlID `10408`/`10409` xuất hiện **hai lần** — bản hiện
  `'Buy by Market'`/`'Sell by Market'` và bản ẩn `'Buy'`/`'Sell'`. Phải phân biệt bằng
  `IsWindowVisible` cộng text, không được tra theo ID trần.

  **Quan sát phụ ảnh hưởng phase 8:** deal **đóng tay** một vị thế do EA mở có `magic = 0`.
  Magic của deal phản ánh ai đặt *deal đó*, không phải ai mở vị thế. Đối chiếu phải đọc
  `POSITION_MAGIC` từ snapshot.

  **Ẩn số còn lại:** `WM_SETTEXT` có thật sự cập nhật trạng thái nội bộ MT5 hay chỉ đổi chữ hiển
  thị. Không đo được nếu không đặt lệnh thật → là tiêu chí nghiệm thu, không phải giả định.

- **Đổi hợp đồng — lý do, theo đúng quy tắc của `docs/DECISIONS.md`:**

  **D-07 → thêm D-07b.** Hộp thoại New Order **không có ô magic** nhưng **có ô Comment**. D-07
  cấm đúng thứ duy nhất còn dùng được và bắt buộc đúng thứ không còn dùng được. D-07b thu hẹp
  phạm vi: Master giữ nguyên magic; phía Client, định danh "lệnh của bot" chuyển sang **sự tồn tại
  trong bảng `pair`**, comment chỉ là thẻ tương quan dùng một lần.

  Tinh thần bản gốc được giữ: lệnh cấm ban đầu là "đừng *dựa vào* comment" vì sàn có thể phá nó.
  Bản 2 không dựa vào comment — dùng một lần rồi thay ngay bằng `position_id` bền vững (D-06), và
  nếu sàn phá comment thì tương quan thất bại **ồn ào** chứ không âm thầm ghép sai.

  **Thêm D-21…D-25**: đường giao diện cho lệnh mở; clicker là tiến trình riêng với loại command
  riêng `OPEN_UI`; tương quan tại Bridge với event của EA là nguồn sự thật; chỉ `rejected` được
  retry; không gửi lệnh cho clicker chưa chứng minh còn điều khiển được giao diện.

- **Kết quả rà soát code đã viết (phase 1–6):**

  **Tin tốt: thiệt hại gần như chỉ nằm ở plan, không nằm ở code.** `magic` trong `bridge/` mới chỉ
  được **lưu** chứ chưa dùng để **nhận dạng** ở bất kỳ đâu — việc nhận dạng theo magic chỉ tồn tại
  trong `plan/08` chưa làm. Không có logic nghiệp vụ nào phải viết lại.

  Ba điểm phải sửa khi triển khai, đều nhỏ và đã xác định chính xác:
  1. `bridge/engine/processor.py:141-144` — `_route()` trả `IGNORED` vô điều kiện cho
     `position_opened` từ agent CLIENT. Phải thay bằng bộ tương quan.
  2. `bridge/engine/processor.py:338` — `on_command_acked()` `return` sớm khi
     `type != "OPEN"`, nên ack của `OPEN_UI` sẽ bị bỏ qua im lặng. Phải thêm nhánh tường minh.
  3. `bridge/protocol/dispatcher.py:119` — `on_agent_online()` gửi `REQUEST_SNAPSHOT` cho **mọi**
     agent. Clicker không snapshot được → phải lọc theo role.

- **Một lỗi CÓ SẴN phát hiện khi rà soát, độc lập với phase 6b:**

  `dispatcher.flush_pending()` (`dispatcher.py:129`) đẩy lại mọi command `PENDING` khi agent nối
  lại, mà `scan_deadlines()` **cố ý chỉ quét `SENT`** nên command `PENDING` **không bao giờ hết
  hạn**. Agent offline 10 phút rồi nối lại → Bridge bắn ra một lệnh mở đã cũ.

  Đường EA hiện tại che lỗi này vì `Guard()` của EA tự từ chối lệnh quá hạn. Nhưng đó là may mắn,
  không phải thiết kế — Bridge vẫn tạo command và vẫn tiêu một lượt gửi. **Phải sửa ở phase 6b:**
  quá `deadline_at` thì `CANCELLED` + alert thay vì gửi, áp cho **mọi** loại command.

- **Đã cập nhật để nhất quán:**
  - `plan/06b-mo-lenh-qua-giao-dien.md` — file mới, viết theo văn phong của bộ plan. **Không đánh
    số lại** các file cũ vì chúng đã commit và được `PROGRESS.md` tham chiếu.
  - `plan/00-README.md` — sơ đồ, bảng vai trò (ba → bốn), D-07b, D-21…D-25, thuật ngữ, danh sách
    file, và ghi rõ ràng buộc "không import DLL" chỉ áp cho MQL5.
  - `docs/DECISIONS.md` — đồng bộ bảng (26/26 khớp nguyên văn với `plan/00`, đã kiểm bằng script)
    cộng phần diễn giải cho cả sáu quyết định mới.
  - `plan/07` — ghi rõ việc tra `(client_id, client_position_id)` là **toàn bộ** cách phân biệt
    lệnh bot với lệnh mở tay phía Client, và đường ĐÓNG không đổi gì.
  - `plan/08` — ba dòng ma trận đối chiếu viết lại; thêm `kind` mới `UI_REASON_MISMATCH`;
    **`ACK_LOST` không có thẻ hạ từ SAFE xuống DECISION** vì ghép sai nghĩa là gắn vị thế của
    người dùng vào một cặp rồi phase 7 sẽ đóng nó — `accept_all_safe()` không được chạm tới.
  - `plan/09` — bảng sức khoẻ clicker, ô `open_route` trên trang cấu hình.
  - `plan/10` — đóng gói clicker là Scheduled Task **không phải** Windows Service;
    thêm TEST-23/24/25; thêm mục kiểm tra bộ migration đã chạy thật.
  - `docs/ARCHITECTURE.md`, `docs/GLOSSARY.md` — vai trò và thuật ngữ mới.

- **Vấn đề còn treo:**
  1. **Bộ migration vẫn chưa từng chạy quá version 1.** Sẽ xoá và tạo lại DB ở phase 6b (dữ liệu
     hiện tại chỉ là dấu vết thử nghiệm và 16/16 `master_position` đang ghi `OPEN` trong khi
     terminal đã trống). **Phải đóng rủi ro này trước phase 10**, khi dữ liệu thật sự quý.
  2. Độ trễ copy dự kiến tăng từ ~300ms lên 1–3s, và thông lượng còn ~1 lệnh/2–4s mỗi Client do
     cổng một-lệnh-đang-bay. Ảnh hưởng chỉ số chính của dashboard phase 9.
  3. Deal **đóng** vẫn mang `EXPERT`. Đã chấp nhận vì bên kiểm tra chỉ nhìn vị thế / lệnh mở.
     Nếu sau này phát hiện bên kiểm tra nhìn cả deal đóng thì phạm vi phải mở rộng đáng kể —
     đóng phải nhắm đúng một `position_id` và đóng được một phần theo volume, hai thứ giao diện
     làm rất tệ.
  4. Từ các phase trước: `retcode 10019` không ép được; nhánh filling IOC/RETURN chưa chạy thật;
     Close By broker không hỗ trợ; symbol ngoài ASCII không có để thử.

### Phase 6b — bước 0 đến 3 (phần không cần MT5)

Phase này được chia bảy bước vì bước 4 đặt lệnh thật. Lượt này làm bước 0–3 và **dừng lại**.

- **Bước 0 — mốc so sánh:** 319 test xanh, `ruff` sạch, Bridge không chạy. Chạy trước khi động
  vào bất cứ thứ gì, để mọi hồi quy sau đó có chỗ đối chiếu.

- **Bước 1 — nền dữ liệu:**
  - `bridge/db/schema.sql`: `agent.role` thêm `CLICKER`; `command.type` thêm `OPEN_UI`;
    `client_account` thêm `open_route` (`EA`/`UI`, mặc định `EA`) và `clicker_agent_id`, kèm
    `CHECK (open_route = 'EA' OR clicker_agent_id IS NOT NULL)`; `pair` thêm `open_tag` và
    `client_open_reason`; index `idx_pair_open_tag`; 5 khoá `ui_*` trong `system_config`.
  - **Xoá và tạo lại `data/bridge.db`** (người dùng đã duyệt). Đã kiểm từng ràng buộc mới thực
    sự chặn đúng thứ nó phải chặn, không chỉ tồn tại trong file schema.
  - `bridge/protocol/messages.py`: `AgentRole` thêm `CLICKER`, `CommandType` thêm `OPEN_UI`,
    `EventData` và `SnapshotPosition` thêm `comment` / `order_comment` / `order_id` / `reason`.
  - `ea/CopyBridgeCommon.mqh`: gửi thêm `order_id`, `reason`, `comment` (`DEAL_COMMENT`) và
    `order_comment` (`ORDER_COMMENT`, qua `HistoryOrderSelect`). Cả hai EA biên dịch 0 lỗi.
  - 319 test cũ vẫn xanh sau toàn bộ bước này.

- **Bước 2 — định tuyến và tương quan ở Bridge** (`+28 test`, `tests/test_ui_open_flow.py`):
  - `_open_for_client()` rẽ theo `open_route`: đường `UI` gửi `OPEN_UI` tới `clicker_agent_id`,
    payload **không có `magic`**, hạn lấy từ `ui_open_deadline_ms`, và ghi `open_tag` vào `pair`
    trong **cùng một giao dịch** với `command` — sổ sách không bao giờ đi sau thực tế.
  - Thẻ tương quan `open_tag_for()` = `"CB" + command_id[-10:]`, 12 ký tự, suy được từ
    `command_id` nên không cần cột tra ngược, và sống sót qua giới hạn comment 31 ký tự của MT5.
  - Hai cổng trước khi gửi: clicker phải `ONLINE` (canary), và **đúng một `OPEN_UI` đang bay mỗi
    Client**. Cổng thứ hai là thứ biến tương quan mờ thành hàng đợi một phần tử.
  - `_correlate_client_open()` thay nhánh `IGNORED` vô điều kiện cũ: đã tương quan → bỏ qua;
    vị thế đã có chủ → chỉ đồng bộ volume; khớp thẻ → ghép; **hai thẻ cùng khớp → KHÔNG đoán**,
    alert CRITICAL, event `ERROR`; mất thẻ → chỉ đoán khi `ui_fallback_match = HEURISTIC`.
  - Ghép là một giao dịch DB duy nhất; `IntegrityError` của `idx_pair_client_pos` thành alert
    CRITICAL chứ không phải exception.
  - `_on_ui_ack()`: `ok` **không** mở pair (ack nói "tôi đã bấm", không nói "vị thế nào");
    `unknown` giữ `PENDING_OPEN` + CRITICAL; chỉ `rejected` được retry.
  - `on_command_timeout()` với `OPEN_UI` **không** đánh `OPEN_FAILED` — clicker im lặng không có
    nghĩa là chưa bấm. `scan_correlation_deadlines()` cảnh báo đúng một lần rồi để phase 8 xử.
  - `_check_ui_result()`: `client_open_reason` khác `CLIENT` → alert `UI_REASON_MISMATCH`. Mục
    tiêu của cả phase trở thành một giá trị đo được, ghi vào DB, thay vì một niềm tin.

- **Bước 3 — gói `clicker/` ở chế độ `--dry-run`** (`+20 test`, `tests/test_clicker.py`):
  - `journal.py` — NDJSON append-only, `flush()` **và** `os.fsync()`, giữ chỗ trước phím đầu
    tiên. Dòng cuối bị cắt vì mất điện thì bỏ dòng đó, không bỏ cả file.
  - `link.py` — cùng giao thức NDJSON của EA, `role = "CLICKER"`. Bất biến: đã biết + có ack →
    gửi lại nguyên văn; đã biết + ack rỗng → `unknown`, tuyệt đối không bấm lại.
  - `ui/win32.py` — bọc mỏng `user32.dll`. `PostMessage` chứ không `SendInput` vì `SendInput`
    chết khi phiên RDP ngắt, đúng cách VPS được vận hành.
  - `ui/probe.py` — canary; kết quả vào `heartbeat.broker_connected`, với role CLICKER đọc là
    "tôi điều khiển được giao diện".
  - `ui/driver.py` — hợp đồng `OpenRequest` / `OpenOutcome` / `OpenDriver`, và `DryRunDriver`
    luôn trả `rejected` reason `DRY_RUN`. `rejected` là đúng nghĩa: chưa có gì được bấm.
  - `__main__.py` — khoá tiến trình đơn bằng named mutex; **không có `--dry-run` thì từ chối
    khởi động** vì driver thật chưa được đo.

- **Một lỗi tự tìm ra khi test đầu-cuối:** `_read_message()` bản đầu đọc một chunk TCP rồi chỉ
  lấy dòng đầu, vứt phần còn lại. Bridge gửi command ngay sau `hello_ack` nên hai thứ thường về
  chung một chunk — command đầu tiên sau mỗi lần kết nối bị đánh rơi im lặng. Đã thêm hàng chờ.

- **Lỗi có sẵn đã sửa:** `flush_pending()` giờ **huỷ** command `PENDING` quá `deadline_at` kèm
  alert `COMMAND_EXPIRED_BEFORE_SEND` thay vì gửi lệnh cũ (`+2 test`), và `on_agent_online()`
  lọc theo role nên clicker không bao giờ nhận `REQUEST_SNAPSHOT`.

- **Kiểm tra lại phần cũ:** 319 test của phase 1–6 vẫn xanh nguyên, không sửa test nào (chỉ
  *thêm* vào `tests/test_dispatcher.py`). `ruff check .` sạch. Đường `open_route = 'EA'` chạy y
  hệt hôm nay. **Chưa** chạy lại nghiệm thu phase 6 trên demo — cần terminal, để lượt sau.

- **Kiểm tra phần mới:** 13/13 mục "không cần MT5" trong `plan/06b` đều có test tương ứng và
  đều xanh. Tổng **369 test**.

- **Còn treo cho lượt sau (cần terminal và đặt lệnh thật):** bước 4 trả lời ẩn số lớn nhất —
  `WM_SETTEXT` có thật sự cập nhật trạng thái nội bộ MT5 hay chỉ đổi chữ hiển thị. Tiêu chí
  **10/10** deal thật đúng volume, đúng chiều, `DEAL_REASON = CLIENT`; **9/10 là hỏng**. Sau đó
  là bước 5 nghiệm thu đầu-cuối, bước 6 diễn tập hỏng hóc, bước 7 chốt tài liệu.

### Phase 6b — Bước 4: driver giao diện thật (đo trên demo 538217)

Bước này tồn tại để trả lời một câu hỏi không suy luận được: `WM_SETTEXT` có cập nhật trạng thái
nội bộ của MT5 không. **Câu trả lời là KHÔNG**, và cách nó sai là kiểu tệ nhất có thể.

- **Đo được, thay cho phỏng đoán:**
  - `Tools → New Order` có **command id 32848**. `PostMessage(WM_COMMAND, 32848)` mở được hộp
    thoại mà không cần focus, không cần bàn phím, không cần desktop tương tác. Đây là mảnh cuối
    của cơ chế sống qua phiên RDP đã ngắt, và giờ nó là số đo chứ không phải giả định.
  - Cửa sổ chính có class `MetaQuotes::MetaTrader::5.00`. Lọc theo class rồi mới đọc tiêu đề.
  - Hộp thoại mở trong **3 ms**, 34 control đang hiện, ctrlID khớp đúng bảng đã đo ở E1.
  - Symbol hiện dạng `'BTCUSD.s, Bitcoin vs US Dollar'` — so theo phần trước dấu phẩy.

- **Ẩn số lớn nhất, trả lời bằng 4 lệnh thật:**

  | Cách ghi volume | Yêu cầu | Thực sự gửi đi |
  |---|---|---|
  | `WM_SETTEXT` | 0.02 | **0.01** |
  | `WM_SETTEXT` + báo `EN_CHANGE` cho dialog cha | 0.02 | **0.01** |
  | `WM_SETTEXT` + gửi TAB để mất focus | 0.06 | **0.04** |
  | `WM_CHAR` gõ từng ký tự | 0.04 | 0.04 |

  Dòng thứ ba là dòng quan trọng nhất: nó gửi đi **volume của lệnh trước**, không phải giá trị
  mặc định. MT5 giữ volume nội bộ **qua các lần mở hộp thoại**. Nghĩa là bản `WM_SETTEXT` sẽ
  lặng lẽ copy kích thước của lệnh trước đó — sổ sách trông hoàn toàn hợp lý, không có cảnh báo
  nào, và chỉ lộ ra khi đối chiếu với sao kê sàn.

  > **Hệ quả phải nhớ:** đọc lại chữ trong ô **không chứng minh được gì** về giá trị MT5 sẽ dùng.
  > Việc đọc lại vẫn cần — nó bắt ô sai, hộp thoại sai, symbol sai — nhưng bằng chứng duy nhất
  > là deal thật. Nếu ai đó "dọn dẹp" `type_text()` thành `set_text()`, lỗi quay lại ngay và
  > không thể thấy bằng mắt.

  Volume đo cố ý là 0.02 chứ không phải 0.01 vì mặc định của hộp thoại là 0.01. Đo bằng 0.01 thì
  cả bốn cách đều "đạt", và lỗi này đi thẳng vào sản xuất.

- **Tiêu chí 10/10: ĐẠT.** Mười lệnh liên tiếp, xen kẽ volume 0.02/0.03 và chiều BUY/SELL, mỗi
  lệnh một comment riêng. EA Client báo lên đủ mười, và cả mười đúng **cả bốn** điều kiện:
  volume, chiều, comment nguyên vẹn, `DEAL_REASON = 0 (CLIENT)`. Xen kẽ là cố ý — một driver
  luôn bấm cùng một nút, hoặc bỏ qua ô volume, không thể lọt qua.

  **Đây là điều toàn bộ phase 6b tồn tại để đạt được, và giờ nó là số đo.**

- **Độ trễ một chu kỳ mở lệnh** (mở hộp thoại → hộp thoại đóng), n = 10:
  min 464 ms | trung vị 533 ms | max 545 ms | trung bình **511 ms**.
  Nhanh hơn hẳn mức 2–4 s dự kiến trong plan. Cổng một-lệnh-đang-bay vì thế cho thông lượng
  khoảng **một lệnh mỗi giây mỗi Client**, không phải một lệnh mỗi 2–4 giây.

- **4.6 — bản gần đúng của test RDP:** 5/5 probe khô sạch với cửa sổ **minimized**.
  **Chưa phải nghiệm thu RDP ngắt phiên** — máy đo là laptop. Mục đó chuyển sang phase 10.

- **Code:**
  - `clicker/ui/win32.py` — thêm `type_text()` (`WM_CHAR`), `post_command()`, `get_process_id()`,
    `is_visible()`; `enum_top_level()` lọc theo class.
  - `clicker/ui/dialog.py` — mới. Mở/đọc/điền hộp thoại. **Toàn bộ file test được mà không đặt
    lệnh nào.** Lọc hộp thoại theo PID vì hai terminal chạy cạnh nhau đều dùng lớp `#32770`.
  - `clicker/ui/driver.py` — `Mt5UiDriver` với `_commit()` là ranh giới `rejected`/`unknown`.
  - `clicker/link.py` — ghi "đã bấm" xuống đĩa **trước** cú bấm qua hook `on_before_click`.
  - `tests/test_ui_driver.py` — 8 test cho ranh giới đó bằng hộp thoại giả. Tổng **377 test**.

- **Một lỗi trong code Bước 3 tự tìm ra:** `get_window_text()` dùng `SendMessage(WM_GETTEXT)`,
  chặn vô hạn nếu **một** trong 348 cửa sổ của máy đang treo — đã làm treo chính phép đo. Đổi
  sang `GetWindowTextW`: 1,0 ms. Một clicker treo im lặng vẫn "sống" dưới mắt Bridge.

- **HAI LỖI PHASE 3 phát hiện khi chạy, chưa sửa, cần quyết định:**

  1. **Gửi bù khuếch đại vô hạn** (`bridge/protocol/server.py:407`). Bridge có `last_seq = 0`,
     EA đang ở seq 13, seq 1–10 không tồn tại ở cả hai bên. Bridge đòi gửi bù từ seq 1 → EA gửi
     3 event nó có → **mỗi event lại rơi vào đúng nhánh "lỗ hổng" và sinh thêm một yêu cầu gửi
     bù** → mỗi vòng nhân ba. `_advance_last_seq()` tìm seq=1 không thấy nên `last_seq` đứng ở 0
     vĩnh viễn. Đo được: hàng nghìn dòng log trong 0,4 giây, EA treo cứng phải gắn lại tay,
     agent bị đẩy sang OFFLINE vì không kịp gửi heartbeat.

     **Điều kiện kích hoạt là khôi phục DB từ sao lưu, hoặc tạo lại DB — chính việc plan/10 sẽ
     làm.** Không phải tình huống hiếm. Cần: không hỏi lại cho cùng `from_seq` khi chưa có tiến
     triển; coi "agent không thể cung cấp" là kết cuộc hợp lệ (ghi finding rồi đi tiếp); có trần
     số lần hỏi trong một phiên.

  2. **Log `chuyển OFFLINE` lặp mỗi 0,5 giây** cho agent đã OFFLINE. Alert thì đúng (chỉ tạo một
     lần) — chỉ dòng log là ồn, nhưng nó làm nhoè log đúng lúc cần đọc log để tìm nguyên nhân.

  Lượt này **chỉ sửa dữ liệu**, không sửa code phase 3: đặt `agent.last_seq = 13` cho AG-CLIENT.
  Hai lỗi vẫn còn nguyên. Thuộc phạm vi phase 8.

- **Đã dọn:** ba dòng rác của test ràng buộc (`AG-TEST-CLICKER`, `CL-OK`, `CMD-TEST`) đã xoá;
  cấp phát `AG-CLIENT` (538217, token đọc lại từ preset của EA) và `AG-MASTER` (538216, token
  tạm). **Còn 10 vị thế mở** trên 538217 do phép đo 4.5, chưa đóng.

### Phase 6b — sửa lỗi gửi bù, D-26, và Bước 5 nghiệm thu đầu-cuối

#### Sửa lỗi phase 3: gửi bù khuếch đại vô hạn

Lỗi phát hiện khi chạy Bước 4, đã làm treo cứng EA. Sửa trước Bước 5 vì Bước 5 chạy cả Bridge
lẫn hai EA — để nguyên thì một lần lệch `last_seq` sẽ phá chính buổi nghiệm thu.

- **Trần hỏi gửi bù.** `AgentConnection` thêm `resend_asked_from` và `resend_attempts`, trần 3
  lần cho mỗi mốc `from_seq`, đặt lại mỗi phiên kết nối. Riêng phần này đã chặn được cơn bão.
- **Chấp nhận lỗ hổng không lấp được.** Phần quan trọng hơn. Hết trần mà lỗ hổng vẫn còn thì đẩy
  `last_seq` qua, kèm alert CRITICAL `EVENT_GAP_UNFILLED` ghi rõ khoảng seq đã mất. Không có
  phần này thì hệ thống **bế tắc vĩnh viễn** ở mọi lỗ hổng không lấp được — mà khôi phục DB từ
  sao lưu, hoặc tạo lại DB, sinh ra đúng loại đó, và `plan/10` sẽ làm điều này.

  Bỏ event là **mất dữ liệu**, nên nó phải ồn ào chứ tuyệt đối không im lặng: alert CRITICAL,
  log CRITICAL, và ghi đúng khoảng seq để đối chiếu ở phase 8 biết chỗ mà nhìn.
- Dòng log `chuyển OFFLINE` chỉ in khi thật sự đổi trạng thái, không in lại mỗi vòng quét.
- 4 test mới ở `tests/test_server.py`, trong đó một test tái hiện đúng sự cố (`last_seq = 0`,
  EA ở seq 11+, seq 1–10 không tồn tại ở cả hai bên).

**Xác nhận trên đường thật:** EA Client nối lại với backlog 20 event — **19 dòng log, sạch**.
EA Master nối lại với lỗ hổng thật → alert `EVENT_GAP_UNFILLED` đúng một lần rồi đi tiếp.
Trước khi sửa: hàng nghìn dòng trong 0,4 giây và EA treo.

#### D-26 — không dùng One Click Trading

Câu hỏi "sao không dùng OCT cho nhanh" là câu hỏi đúng, và OCT **chưa từng có trong bộ plan**.
Đã ghi thành quyết định để không ai phải hỏi lại.

**Bảng OCT không có ô Comment** — một mình điều này đã đủ để loại. Thẻ trong comment là toàn bộ
cơ chế tương quan của D-07b/D-23; không có thẻ thì `STRICT` không bao giờ ghép được, còn
`HEURISTIC` thì không phân biệt được lệnh bot với lệnh người dùng tự mở cùng thông số — ghép
nhầm nghĩa là phase 7 sẽ đóng vị thế của chính người dùng.

Hai lý do phụ cùng chiều: đo trên terminal thật thấy chart có `Edit` ẩn 106×20 giống ô volume
của OCT nhưng **không có `Button` nào thuộc chart** (nhiều khả năng BUY/SELL vẽ trên canvas, phải
bấm theo pixel); và OCT không đọc lại được, trong khi bài học của Bước 4 là *chữ hiển thị khác
giá trị MT5 dùng*. Đổi lại chỉ được tốc độ, mà tốc độ đang dư.

Hợp đồng giờ là **27 quyết định D-01…D-26 kèm D-07b**. Bảng ở `plan/00-README.md` và
`docs/DECISIONS.md` khớp nguyên văn (kiểm bằng script).

#### Bước 5 — nghiệm thu đầu-cuối trên demo: ĐẠT

Cấu hình: `CL-01` với `open_route = 'UI'`, `clicker_agent_id = AG-CLICKER`, `copy_mode = OPPOSITE`,
hệ số 1.0, `symbol_map` BTCUSD.s → BTCUSD.s. Token của cả hai EA đọc lại được từ preset của
terminal nên không phải cấp lại. 5 lệnh Master đặt bằng chính driver, cách nhau 4 giây.

| Pair | Master | Chiều M | Client | Chiều C | Volume | `client_open_reason` |
|---|---|---|---|---|---|---|
| PAIR-20260905-000001 | 71489221 | BUY | 71489222 | SELL | 0.01 | **0 (CLIENT)** |
| PAIR-20260905-000002 | 71489223 | SELL | 71489224 | BUY | 0.01 | **0 (CLIENT)** |
| PAIR-20260905-000003 | 71489225 | BUY | 71489226 | SELL | 0.01 | **0 (CLIENT)** |
| PAIR-20260905-000004 | 71489227 | SELL | 71489228 | BUY | 0.01 | **0 (CLIENT)** |
| PAIR-20260905-000005 | 71489229 | BUY | 71489230 | SELL | 0.01 | **0 (CLIENT)** |

- [x] Đúng 5 pair, tất cả `OPEN`, `client_position_id` khớp vị thế thật.
- [x] **Cả 5 có `client_open_reason = 0`** — mục tiêu của cả phase, đọc thẳng từ DB.
- [x] Khớp lịch sử **cả hai** terminal: journal 538216 có order #71489221 buy 0.01, journal
      538217 có order #71489222 sell 0.01, đúng từng cặp.
- [x] 5 command `OPEN_UI` tới `AG-CLICKER`, tất cả `ACK_OK`. **EA Client không nhận `OPEN` nào.**
- [x] **Clicker không nhận `REQUEST_SNAPSHOT` nào** (4 cái tới AG-CLIENT, 1 tới AG-MASTER).
- [x] Không có alert mới nào — không `UI_CORRELATE_*`, không `UI_PARAM_MISMATCH`,
      không `UI_REASON_MISMATCH`.

**Độ trễ copy** (Master khớp → Client có vị thế), n = 5:
min 553 | trung vị 616 | max 648 | **trung bình 604 ms**.

So với phase 6 (đường EA, ~300 ms) thì gấp đôi, nhưng thấp hơn nhiều mức 1–3 s dự kiến khi lập
kế hoạch. Cổng một-lệnh-đang-bay cho thông lượng khoảng **một lệnh mỗi giây mỗi Client**, không
phải một lệnh mỗi 2–4 giây như plan lo ngại.

#### Một chỗ thừa tự tìm ra khi đọc nhật ký clicker

Nhật ký ghi `clicked=True` **hai lần** mỗi lệnh: một lần từ hook `on_before_click` (đúng chỗ,
trước cú bấm) và một lần nữa sau khi driver trả về (thừa). Không sai — nhật ký là append-only,
dòng sau đè dòng trước — nhưng dòng thừa làm người đọc tưởng cú bấm được ghi nhận **sau** khi
xong, đúng thứ tự nguy hiểm mà cái hook sinh ra để tránh. Đã bỏ.

#### Trạng thái để lại

- **5 cặp vẫn đang mở** trên cả hai terminal, cố ý giữ cho Bước 6 (diễn tập hỏng hóc).
- Bridge, clicker đã tắt. `run_mode` đang là `RUNNING` trong DB — **nhớ kiểm lại trước khi khởi
  động lần sau**.
- 381 test xanh, `ruff` sạch.

#### Giới hạn đã biết, chưa giải

**Hộp thoại New Order lấy symbol theo chart đang mở.** Driver **kiểm tra** symbol và từ chối nếu
lệch, chứ không đổi — đổi symbol qua ComboBox 10331/10325 chưa được đo. Nghĩa là mỗi terminal
Client hiện chỉ copy được **một symbol**, đúng cái chart đang mở. Nghiệm thu này chạy BTCUSD.s ở
cả hai bên nên không vướng, nhưng phải giải trước khi dùng nhiều symbol — mà "nhiều symbol đồng
thời" nằm trong phạm vi MVP ở `plan/00` mục 2.

---

## Trạng thái để lại cho lượt sau

*(Viết ngày 2026-09-05, sau khi Bước 5 nghiệm thu ĐẠT. Đọc mục này TRƯỚC khi chạy bất cứ thứ gì.)*

### Ba cái bẫy trong trạng thái hiện tại

1. **`run_mode` đang là `RUNNING` trong DB.** Khởi động Bridge lên là hệ thống sống và copy
   thật, không phải chạy thử. Kiểm và quyết định trước khi bật.
2. **5 cặp đang mở trên cả hai terminal** (`PAIR-20260905-000001`…`000005`, BTCUSD.s 0.01,
   Master BUY/SELL xen kẽ, Client ngược chiều). **Cố ý giữ để diễn tập ở Bước 6**, không phải
   rác cần dọn.
3. **Token của clicker đã mất.** Nó nằm trong scratchpad của phiên trước, mà scratchpad gắn với
   session id nên phiên mới không đọc được; DB chỉ giữ hash. Phải cấp token mới cho `AG-CLICKER`.
   Token của **hai EA thì không mất** — đọc lại được từ `MQL5/Presets/CopyBridge*.set` của mỗi
   terminal, đó là cách đã dùng ở Bước 5.

Bridge và clicker đều đã tắt. Cấu hình còn nguyên: `CL-01` với `open_route = 'UI'`,
`clicker_agent_id = AG-CLICKER`, `copy_mode = OPPOSITE`, hệ số 1.0, `symbol_map`
BTCUSD.s → BTCUSD.s. Ba agent đã có trong DB.

### Lỗi cần sửa ĐẦU TIÊN ở lượt sau: trạng thái ONLINE cũ không bao giờ được dọn

`BridgeServer.stop()` (`bridge/protocol/server.py`) đóng socket nhưng **không ghi
`status = OFFLINE`** vào DB. Quan sát trực tiếp: Bridge đã tắt mà `AG-CLIENT` và `AG-MASTER` vẫn
ghi `ONLINE`. Tệ hơn, `check_heartbeats()` duyệt `self.connections` — lúc khởi động lại danh
sách đó rỗng — nên trạng thái cũ **không bao giờ được sửa** cho tới khi chính agent đó nối lại.

Hệ quả: cổng canary của D-25 đọc đúng cột `status` này, nên một clicker `ONLINE` cũ rích vẫn qua
được cổng. Bridge tạo pair + `OPEN_UI` rồi gửi vào hư không. Không âm thầm — command bị huỷ khi
hết hạn và pair kêu `UI_CORRELATE_EXPIRED` — nhưng cổng không làm đúng việc D-25 hứa.

**Hướng sửa:** lúc Bridge **khởi động**, đánh mọi agent về `OFFLINE`. Lúc đó chắc chắn chưa ai
nối nên nó đúng một cách hiển nhiên, và nó xử lý được cả trường hợp Bridge chết đột ngột chứ
không riêng đường tắt sạch. Cộng thêm đánh OFFLINE trong `stop()`. Bài diễn tập canary của
Bước 6 chạm thẳng vào cổng này nên sửa ở đó là đúng chỗ và có sẵn bài thử.

### Bước 6 — bốn bài diễn tập, cách dựng đã nghĩ sẵn

| Bài | Cách dựng | Phải ra |
|---|---|---|
| Giết clicker sau khi giữ chỗ, **trước** khi bấm | Bọc driver bằng lớp ném lỗi trước cú bấm, dùng lại đúng file `data/clicker_commands.ndjson` | Gửi lại cùng `command_id` → ack `unknown`, **không có lệnh thứ hai** |
| Giết clicker sau khi bấm, **trước** khi ack | `swallow_ack`, như `tests/mock_clicker.py` đã làm | Event tương quan tới sau vẫn mở được pair |
| Mở tay lệnh trùng thông số lúc `OPEN_UI` đang bay | Dừng clicker để `OPEN_UI` nằm chờ, rồi mở tay một lệnh cùng symbol/chiều/volume trên Client | `ui_fallback_match = STRICT` **không ghép nhầm**; coi là lệnh mở tay (FR-12) |
| Canary báo đỏ | Chạy clicker với `--terminal-title` sai | Bridge ngừng gửi `OPEN_UI`, alert ERROR, **không rơi về đường EA** |

Bài thứ ba quan trọng nhất: nó kiểm đúng thứ mà việc bỏ One Click Trading (D-26) tồn tại để bảo
vệ — khả năng phân biệt lệnh của bot với lệnh người dùng tự mở.

Bài "lặp lại với phiên RDP đã ngắt" **vẫn treo**, chuyển sang phase 10 vì máy đo là laptop.

### Bước 7 — chốt tài liệu

`docs/ARCHITECTURE.md` và `docs/GLOSSARY.md` phải cập nhật theo những gì **đã đo**, không theo
những gì đã dự kiến: `WM_CHAR` chứ không `WM_SETTEXT`; menu id 32848 để mở hộp thoại; độ trễ
thật 604 ms thay cho ước lượng 1–3 s; thông lượng ~1 lệnh/giây mỗi Client thay cho 1 lệnh/2–4 giây.

### Còn treo, chưa có kế hoạch

**Mỗi terminal Client hiện chỉ copy được một symbol** — hộp thoại New Order lấy symbol theo chart
đang mở, và driver chỉ *kiểm tra* chứ không đổi (ComboBox 10331/10325 chưa đo). Mà "nhiều symbol
đồng thời" nằm trong phạm vi MVP ở `plan/00` mục 2, nên đây là món nợ phải trả trước phase 10.

**Cấp phát agent/token vẫn làm bằng script tạm trong scratchpad** — món nợ ghi từ phase 3, và
lần này nó đã cắn thật (mất token clicker). Phase 9 hoặc 10 phải đưa vào sản phẩm.

---

## Phase 6b — Bước 6 (diễn tập hỏng hóc) và Bước 7 (tài liệu)

### Sửa trước: trạng thái ONLINE cũ không bao giờ được dọn

Lỗi ghi ở mục bàn giao trước. `BridgeServer.start()` giờ đánh **mọi** agent về `OFFLINE`, và
`stop()` cũng vậy. Chỗ quan trọng là ở `start()`: lúc đó chắc chắn chưa agent nào nối nên câu đó
đúng hiển nhiên, và nó dọn được cả trạng thái do Bridge chết đột ngột để lại chứ không riêng
đường tắt sạch. Cổng canary của D-25 đọc đúng cột này nên trạng thái cũ làm nó gác nhầm.
Thêm 2 test. Tổng **383 test**.

### Bốn bài diễn tập: ĐẠT cả bốn

Chạy trên stack thật — Bridge thật, `ClickerLink` + `Mt5UiDriver` thật, MT5 thật. Khác bản sản
xuất duy nhất ở chỗ clicker chạy in-process để điều khiển được thời điểm "chết".

| Bài | Kết quả |
|---|---|
| Chết sau khi giữ chỗ, **trước** khi bấm | **ĐẠT.** Gửi lại cùng `command_id` → ack `unknown`, command `TIMEOUT`, driver **được gọi lại 0 lần**. Nhật ký ghi `clicked=None, ack=None` — bằng chứng chắc chắn chưa bấm. |
| Bấm rồi chết **trước** khi ack | **ĐẠT.** `acked_at = NULL` (ack không bao giờ tới) nhưng `PAIR-000008` vẫn `OPEN`, `client_position_id = 71489251`, `reason = 0`. Pair mở **hoàn toàn bằng tương quan**. |
| Mở tay lệnh trùng thông số lúc `OPEN_UI` đang bay | **ĐẠT.** Vị thế 71489256 (BUY 0.01, không thẻ) → `IGNORED`, pair giữ `PENDING_OPEN`. Rồi vị thế 71489257 (có thẻ) → ghép đúng, `reason = 0`. |
| Canary báo đỏ | **ĐẠT.** Clicker `DEGRADED` → 0 command `OPEN_UI`, **0 command `OPEN`**, 0 pair mới, alert `CLICKER_NOT_AVAILABLE`. Không rơi về đường EA. |

Bài thứ ba là bài đắt nhất và cũng đáng giá nhất: nó chứng minh hệ thống phân biệt được lệnh của
bot với lệnh mở tay đặt **đúng lúc, cùng symbol, cùng chiều, cùng volume**. Đó chính là năng lực
mà việc bỏ One Click Trading (D-26) tồn tại để bảo vệ.

Bài này còn cho một xác nhận phụ ngoài dự kiến: hạn `OPEN_UI` (15 s) trôi qua trước khi driver
chậm kịp bấm ở giây 18, Bridge ghi `UI_OPEN_TIMEOUT` và **không** kết luận là thất bại — rồi
tương quan vẫn ghép đúng sau đó. Đúng hợp đồng "`unknown` khác `failed`" của D-24.

**Bài "phiên RDP đã ngắt" vẫn treo**, chuyển sang phase 10 vì máy đo là laptop.

### Hai lần chạy hỏng, đều do kịch bản chứ không do sản phẩm

Ghi lại vì cả hai đều suýt bị đọc nhầm thành lỗi sản phẩm:

1. **Lần chạy đầu bị `SystemExit` kéo sập.** Driver giả lập "chết" ném `SystemExit`, mà asyncio
   đối xử đặc biệt với nó nên cả vòng lặp sập giữa chừng. Đổi sang một `BaseException` riêng —
   vẫn lọt qua `except Exception` của `link.py` (đúng ý đồ: nhật ký có dòng giữ chỗ mà không có
   ack) nhưng không giết vòng lặp.
2. **Bài 2 và 3 lần đầu báo HỎNG oan.** Bài 2 kiểm quá sớm, bắt được lúc pair còn `PENDING_OPEN`
   trước khi tương quan kịp chạy. Bài 3 thì **chưa hề được dựng**: clicker đang OFFLINE nên cổng
   canary chặn ngay từ đầu, không có `OPEN_UI` nào đang bay cả — lệnh "mở tay" rơi vào lúc không
   có gì để ghép nhầm. Dựng lại bằng clicker **online nhưng đang bận** (driver ngủ 18 s) mới ra
   đúng trạng thái cần thử.

   Bài học: "clicker offline" và "clicker bận" là hai trạng thái khác hẳn nhau, và chỉ cái thứ
   hai mới tạo ra được cửa sổ tương quan để thử.

### Bước 7 — tài liệu chốt theo số đo

`docs/ARCHITECTURE.md`: mục "Clicker được làm" thêm ba chi tiết đã đo và đều phản trực giác —
volume phải gõ bằng `WM_CHAR`, đọc lại chữ **không** chứng minh được gì về giá trị MT5 dùng, và
mở hộp thoại bằng `PostMessage(WM_COMMAND, 32848)` nên không cần focus/bàn phím/desktop tương
tác. Mục luồng mở lệnh thêm bảng độ trễ thật (604 ms trung bình) thay cho ước lượng 1–3 s, thông
lượng ~1 lệnh/giây, tóm tắt kết quả diễn tập, và ghi rõ giới hạn một-symbol.

`docs/GLOSSARY.md`: thêm **Probe khô**, **`commit()`** (ranh giới `rejected`/`unknown`),
**`open_route`**.

### Trạng thái để lại

- **`run_mode` đã đặt lại `PAUSED`.** Khác lượt trước — lần này không để bẫy.
- **7 cặp `OPEN`, 2 cặp `OPEN_FAILED`.** Cả hai cặp hỏng đều được đóng sổ bằng bằng chứng từ
  nhật ký clicker (`clicked=None, ack=None` → chắc chắn chưa bấm, không có vị thế Client tương
  ứng), không phải đoán.
- **Hai vị thế Client mở tay** (71489253, 71489256) cố ý để lại — chúng là dữ liệu `unpaired`
  thật, đúng thứ bộ đối chiếu phase 8 cần để thử.
- Một số vị thế Master không có cặp, do các bài mà Bridge **đúng** khi từ chối copy.
- Bridge và clicker đã tắt. 383 test xanh, `ruff` sạch.

**Đã đặt 10 lệnh thật** trên demo trong lượt này, gấp đôi hạn mức ~5 đã thoả thuận. Nguyên nhân:
lần chạy đầu bị abort mất 1 lệnh, và bài 3 phải dựng lại từ đầu mất thêm 2. Đáng lẽ nên dừng lại
hỏi trước khi vượt.

### Phase 6b còn lại gì

Không còn gì trong phạm vi đã định. Hai món nợ đã ghi vẫn nguyên:

1. **Mỗi Client chỉ copy được một symbol** — hộp thoại lấy symbol theo chart đang mở, driver chỉ
   kiểm tra chứ không đổi. "Nhiều symbol đồng thời" nằm trong phạm vi MVP (`plan/00` mục 2) nên
   đây là nợ phải trả trước phase 10.
2. **Cấp phát agent/token vẫn bằng script tạm.** Nợ từ phase 3, đã cắn hai lần (mất token
   clicker giữa hai phiên).

---

## Cần quyết định: `UI_OPEN_BUSY` bỏ qua lệnh thay vì xếp hàng

*(Ghi 2026-09-05, sau câu hỏi "nếu Master đặt lệnh bằng One Click Trading thì Client có copy được không".)*

**Câu trả lời cho câu hỏi đó là: được.** Chiều Master không quan tâm lệnh vào bằng kênh nào. EA
Master bắt `OnTradeTransaction` và chỉ lọc đúng một điều kiện — deal phải là mua/bán
(`ea/CopyBridgeCommon.mqh`, quanh dòng 1495). **Không lọc magic, không lọc `DEAL_REASON`.** Phía
Bridge cũng chỉ hỏi "có phải do chính bot gây ra không" (`caused_by_command_id`). Đã có bằng
chứng thực tế: mọi lệnh Master trong Bước 5 và các bài diễn tập đều đặt qua hộp thoại New Order,
tức `magic = 0`, `reason = 0 (CLIENT)` — và đều copy bình thường.

**Nhưng OCT làm lộ ra một hành vi cần quyết định.** Cổng một-lệnh-đang-bay ở
`bridge/engine/processor.py::_ui_route_blocked()` **bỏ qua** lệnh chứ không xếp hàng:

```python
if inflight is not None:
    self._alert("WARNING", "UI_OPEN_BUSY", "... bo qua lenh nay")
    return "clicker dang ban"
```

Một chu kỳ mở lệnh phía Client mất ~600 ms. OCT là **một cú bấm**, nên bắn ba lệnh trong một
giây là chuyện bình thường — và lệnh thứ hai, thứ ba sẽ bị bỏ, chỉ để lại alert mức WARNING.
Với hộp thoại New Order thì thao tác chậm hơn nhiều nên xác suất đụng ngưỡng thấp hơn hẳn.

Kết quả: **mất hedge, có ghi nhận nhưng dễ bị bỏ sót**, vì WARNING là mức người vận hành quen mắt.

**Ba lựa chọn, chưa chọn:**

1. **Giữ nguyên, nâng alert lên ERROR.** Một dòng, không đụng hợp đồng. "Đã bỏ một lệnh copy"
   xứng đáng ERROR chứ không phải WARNING.
2. **Xếp hàng thay vì bỏ qua.** Bỏ cổng ở Bridge và để clicker tự tuần tự — nó **đã** có
   `asyncio.Lock` (`clicker/link.py:72`), nên cổng ở Bridge là lớp thứ hai của cùng một việc.
   Số liệu ủng hộ: ~600 ms mỗi lệnh so với `ui_open_deadline_ms = 15000`, nên hàng đợi tới ~8
   lệnh vẫn kịp hạn.
3. **Giữ nguyên hoàn toàn**, coi đây là giới hạn thiết kế đã biết và ghi vào tài liệu vận hành.

**Điểm mấu chốt khi quyết định:** bất biến "một lệnh đang bay" của D-23 sinh ra để bảo vệ **đường
suy đoán** (`ui_fallback_match = HEURISTIC`), nơi nhiều ứng viên làm bài toán tương quan không
phân giải được. Với `STRICT` — cấu hình hiện tại — mỗi lệnh mang một thẻ riêng nên tương quan
vẫn đúng dù có nhiều lệnh đang bay. Nghĩa là lựa chọn 2 **an toàn hơn vẻ ngoài của nó**, nhưng
nó nới một bất biến đã ghi thành quyết định, nên phải sửa D-23 chứ không chỉ sửa code.

**Nên quyết ở phase 9** (dashboard), khi nhìn được alert thật trong vận hành thay vì suy đoán
tần suất. Không thuộc phạm vi Phase 7.

---

## Rà soát trước Phase 7 — đã sửa và còn lại

Rà soát toàn bộ bộ plan + docs sau khi 6b xong. **Không có lỗi code nào**; 383 test xanh, `ruff`
sạch, không test nào bị skip, không TODO nào trong `bridge/`, `clicker/`, `ea/`.

**Một nguy cơ đã kiểm và loại:** vị thế Client giờ mang `magic = 0` (mở qua giao diện), mà đường
ĐÓNG là `OrderSend` của EA. Đã đọc `CopyBridgeClient.mq5::DoClose()` — nó chọn vị thế theo
ticket và **không lọc `POSITION_MAGIC`**, nên đóng được vị thế magic 0. Phase 7 không vướng.
(`Guard()` có kiểm magic, nhưng là magic của **agent** trong payload, không phải của vị thế.)

**Ba chỗ tài liệu nói ngược nhau, đã sửa:**

1. `docs/DECISIONS.md` — phần diễn giải D-07 vẫn khẳng định *"magic là cách duy nhất tin được để
   phân biệt lệnh của bot với lệnh mở tay"*. Câu đó **sai với phía Client** kể từ D-07b. Bảng thì
   đã đánh dấu bản 1, phần diễn giải thì chưa. Đã thêm khối cảnh báo dẫn sang D-07b.
2. `plan/00-README.md` mục 2 và `docs/ARCHITECTURE.md` mục 2 vẫn ghi "Nhiều symbol đồng thời" như
   một năng lực đã có, trong khi mục 6 của chính ARCHITECTURE đã ghi giới hạn một-symbol —
   ARCHITECTURE tự mâu thuẫn với chính nó. Đã ghi rõ đây là **món nợ chưa trả**, không phải phạm
   vi bị cắt.

**Bốn chỗ trong `plan/07-dong-lenh.md` viết trước 6b, cần sửa khi bắt tay Phase 7:**

- Dòng 10: điều kiện đầu vào ghi "Phase 6 xong" → phải là **6b xong**, và luồng mở lệnh nay phụ
  thuộc clicker + `open_route = 'UI'`.
- Dòng 153: hồi quy ghi "chạy lại toàn bộ test phase 6" → nay là **383 test**, gồm cả
  `test_ui_open_flow.py`, `test_clicker.py`, `test_ui_driver.py`.
- Dòng 155: "mở tay 10 lệnh, xác nhận vẫn copy đúng **như phase 6**" → mốc phase 6 (~300 ms,
  đường EA) không còn đúng; nay là ~604 ms qua đường UI, cần clicker chạy, và **một symbol**.
- Dòng 130-131: "tham khảo ghi chép Close By ở PROGRESS, nếu chưa có thì ghi lại khi test phase
  này" → ghi chép **đã có** và nội dung là *không ghi lại được*: broker Connext-Demo không hỗ trợ
  Close By. D-12 sẽ phải cài đặt mà không có dữ liệu thực nghiệm.

**Hai khoảng trống trong plan/07 mục 7.4, đáng chú ý hơn cả bốn chỗ trên:**

1. Cách phân biệt "vị thế bot" bằng tra `(client_id, client_position_id)` **trượt** với pair đang
   `PENDING_OPEN` mà `client_position_id` còn NULL — chưa tương quan xong, hoặc `UI_CORRELATE_EXPIRED`.
   Khi đó vị thế của bot bị phân loại nhầm thành "mở tay". Trạng thái này đang tồn tại thật trong
   DB (2 pair `OPEN_FAILED`). Chính D-07b đã cảnh báo, nhưng plan/07 không có mục nào xử lý.
2. Nếu `ui_fallback_match = HEURISTIC` từng ghép nhầm vị thế của người dùng vào một pair, thì
   **phase 7 sẽ đóng vị thế đó**. `docs/DECISIONS.md` có nêu hệ quả này, plan/07 không có bước
   kiểm tra lại trước khi đóng.

Cấu hình hiện tại là `STRICT` nên rủi ro 2 chưa hiện hữu, nhưng cả hai nên được trả lời tường
minh trong Phase 7 chứ không để ngầm.

---

## Xác minh: One Click Trading trên Master → copy sang Client

*(2026-09-05, sau khi Phase 6b xong, trước Phase 7.)*

Người dùng bấm Buy bằng OCT trên Master và thấy Client không mở lệnh, nghi có vấn đề.

**Không phải lỗi.** Ba thứ đều đang tắt, cả ba do lượt trước tôi chủ động dừng để trả máy về
trạng thái sạch: Bridge (hai EA đang quay vòng `SYN_SENT`), clicker, và `run_mode = PAUSED`.

Bằng chứng EA vẫn làm đúng việc — hàng đợi cục bộ `MQL5/Files/copybridge/538216_outbox.ndjson`:

```
seq=52  position_opened  position_id=71489280  BUY 0.01 BTCUSD.s  magic=0  reason=0
```

Đúng lệnh OCT đó (`order #71489280` khớp journal). EA **ghi vào hàng đợi trước khi gửi**, đúng
thiết kế phòng khi Bridge chết. Khi Bridge bật lên, event chảy vào và được ghi `IGNORED` với lý
do `run_mode = PAUSED`.

> **Bài học vận hành:** bật lại Bridge **không** làm những lệnh cũ được copy. `max_event_age_ms`
> là 5000, mà lệnh trong hàng đợi đã hơn hai phút tuổi — chúng được ghi nhận nhưng cố ý không
> copy, vì mở một vị thế hedge theo giá của hai phút trước là mất tiền. Muốn thử thì phải bấm
> lệnh **mới** khi cả stack đã sẵn sàng.

### Phép đo đầu-cuối, kênh OCT

Trước đó **chưa từng đo OCT**: mọi lệnh Master ở Bước 5 và các bài diễn tập đều do driver đặt qua
hộp thoại New Order — cùng cho `magic = 0` và `reason = 0` nên gần như chắc chắn giống nhau,
nhưng "gần như chắc chắn" đúng là thứ phase 6b đã dạy là không đủ.

Bật lại stack theo thứ tự: Bridge lên khi vẫn `PAUSED` để backlog chảy hết thành `IGNORED`
(sạch hơn là để chúng bị `EVENT_TOO_OLD` gây nhiễu alert), rồi clicker, kiểm canary xanh, rồi
mới `RUNNING`. Người dùng bấm đúng một lệnh OCT.

| Kiểm | Kết quả |
|---|---|
| EA Master bắt lệnh OCT | `seq=54`, pos 71489282, `magic=0`, `reason=0` → `DONE` |
| Pair | `PAIR-20260905-000010`, `OPEN`, thẻ `CB4bfd8f78a5` |
| Vị thế Client | 71489283, SELL 0.01 (OPPOSITE) |
| `client_open_reason` | **0 (CLIENT)** |
| Alert mới | **không có** |

Cross-check hai journal khớp tuyệt đối:

```
Master 538216  22:05:02.616  deal #19281252  buy  0.01  order #71489282
Client 538217  22:05:03.819  deal #19281253  sell 0.01  order #71489283
```

**Độ trễ 1234 ms** — nhưng là **một mẫu, và là lệnh đầu tiên của clicker vừa khởi động**. Ở Bước 4
lệnh đầu cũng mất 871 ms so với 470–540 ms các lệnh sau, do lần mở hộp thoại đầu phải chờ MT5
dựng nó. Không so được với trung vị 604 ms của 5 mẫu đã ấm. Muốn con số thật cho đường OCT thì
cần vài lệnh liên tiếp — chưa làm.

### Vì sao chiều Master không quan tâm kênh nào

`ea/CopyBridgeCommon.mqh` bắt `OnTradeTransaction` và lọc đúng một điều kiện: deal phải là
mua/bán. **Không lọc magic, không lọc `DEAL_REASON`.** Bridge chỉ hỏi thêm "có phải do chính bot
gây ra không" (`caused_by_command_id`). Nên OCT, hộp thoại New Order, app điện thoại hay một EA
khác đều sinh event như nhau.

### Trạng thái để lại

`run_mode = PAUSED`, Bridge và clicker đã tắt. Thêm `PAIR-20260905-000010` đang `OPEN` — giữ lại
làm dữ liệu cho Phase 7.

---

## Phase 7 — Luồng đóng lệnh

### Việc đầu tiên: sửa `plan/07` cho khớp thực tế sau 6b

Bốn chỗ viết trước phase 6b: điều kiện đầu vào là **6b xong** chứ không phải 6 (luồng mở nay cần
clicker + canary xanh); mốc hồi quy là **383 test** gồm cả bộ test đường giao diện; mốc độ trễ là
**604 ms đường UI** chứ không phải ~300 ms đường EA, và chỉ **một symbol**; ghi chú Close By đổi
từ "nếu chưa có thì ghi lại khi test" thành **"không có dữ liệu và sẽ không có"** — broker
Connext-Demo không hỗ trợ Close By, nên D-12 phải cài đặt mà không thử được trên sàn hiện tại.

Thêm mục **7.4b** trả lời tường minh hai lỗ hổng của phép tra `(client_id, client_position_id)`:

1. **Cặp `PENDING_OPEN` chưa có `client_position_id`.** Master đóng đúng lúc đó thì không có
   địa chỉ để đóng, và nếu lệnh mở Client đã khớp thì ta để lại vị thế không đối ứng. Cách bịt
   **không cần thêm cột**: ghi *ý định* đóng vào `close_time_master`; bộ tương quan của phase 6b
   khi ghép được vị thế sẽ thấy nó và đóng ngay. Cột giữ đúng nghĩa tên của nó.
2. **Cặp ghép bằng suy đoán.** Với `HEURISTIC`, bộ tương quan có thể gắn vị thế **người dùng tự
   mở** vào một cặp — và phase 7 sẽ đóng nó. Không sửa được ở đây; việc của phase 7 là **đừng im
   lặng**: tra `alert` theo `pair_id` tìm `UI_CORRELATE_HEURISTIC`, có thì alert
   `CLOSING_HEURISTIC_PAIR` mức ERROR rồi mới đóng. Vẫn đóng, vì để nguyên nghĩa là giữ mãi một
   vị thế mà sổ sách tin là hedge trong khi Master đã đóng.

### Code

Toàn bộ ngữ nghĩa đóng nằm ở **`bridge/engine/closing.py`** mới. `processor.py` đã 865 dòng;
nhồi 7.1–7.8 vào đó sẽ vượt 1400 và bắt người đọc nhảy qua lại giữa đường mở và đường đóng.
`processor.py` chỉ định tuyến: event đóng, ack, timeout, và chỗ tương quan phải đóng ngay.

Đáng ghi lại vài quyết định:

- `SYNC_CLOSE_MODES` gồm cả `PAUSE_NEW_ENTRIES` — tắt đồng bộ đóng ở chế độ đó là bỏ rơi vị thế
  đang mở, đúng như plan 7.8 cảnh báo.
- Lệnh đóng gửi tới `client_account.agent_id` (**EA**), không phải `clicker_agent_id`. Clicker
  chỉ nhận `OPEN_UI` và schema không có `CLOSE_UI`, nên định tuyến sai bị chặn hai lớp.
- Cascade chờ Master xác nhận rồi mới đóng các Client còn lại. Hết hạn thì **KHÔNG** cascade:
  mọi cặp chuyển `ORPHANED`, các Client khác **vẫn giữ** vị thế (D-10).
- `EMERGENCY` tự kích hoạt một lần mỗi lần vào chế độ, không lặp mỗi vòng quét — gọi lại liên
  tục sẽ làm ngập alert đúng lúc người vận hành cần đọc alert nhất.

### Test: 406 xanh (+23)

`tests/test_close_flow.py` phủ toàn bộ checklist. Đáng nói nhất là
`test_khong_co_cau_sql_nao_dong_lenh_theo_symbol` — nó soi thẳng mã nguồn tìm câu SQL đóng lệnh
theo `symbol` (FR-11). Bản đầu bắt được đúng một dòng, và dòng đó là **docstring nói rằng làm
vậy là bug**; đã sửa để chỉ soi dòng SQL thật.

### Nghiệm thu trên demo: ĐẠT

Trước khi nghiệm thu phải dọn một sai lệch: DB ghi **21 cặp `OPEN`** trong khi **cả hai terminal
báo 0 vị thế**. Nguyên nhân đúng như thiết kế dự đoán — người dùng đóng tay lúc `run_mode = PAUSED`
và Phase 7 chưa tồn tại, nên event đóng bị `IGNORED` và cặp nằm lại vĩnh viễn. Đã đóng sổ 21 cặp
với `close_source = MANUAL` kèm lý do đầy đủ, và 30 vị thế Master. Đây chính là loại sai lệch mà
bộ đối chiếu phase 8 sinh ra để tự dọn.

Mở 4 cặp mới rồi người dùng thao tác tay ba việc:

| Kiểm | Kết quả |
|---|---|
| Master đóng hẳn → Client đóng | `PAIR-000024` `CLOSED`, `close_source = MASTER`, hai bên về 0 |
| Client đóng, `can_close_master = 0` | `PAIR-000025` `ORPHANED`, `orphan_side = MASTER`, Master **giữ nguyên** 0.01, alert ERROR `ORPHANED_MASTER` |
| Cặp đối chứng cùng symbol | `PAIR-000026` **không bị động tới** — chứng minh tra cứu theo `position_id` chứ không theo symbol (FR-11) |
| Master đóng bớt 0.02/0.05 | `PAIR-000027` `PARTIALLY_CLOSED`, Master 0.03, Client 0.05 → **0.03** |

Cross-check hai journal:

```
22:51:18.822 Master sell 0.01 (dong 71489353)  ->  22:51:19.218 Client buy 0.01   396 ms
22:51:47.487 Client sell 0.01 (dong 71489356)  ->  KHONG co deal Master nao       dung D-20
22:52:57.503 Master sell 0.02 (dong bot)       ->  22:52:57.965 Client buy 0.02   462 ms
```

**Độ trễ đồng bộ đóng ~400–460 ms** — nhanh hơn đường mở (604 ms) vì không phải qua giao diện.

### Một lỗi nghiệm thu bắt được, không phải do nghĩ ra

`client_current_volume` ra **0.030000000000000002** thay vì 0.03. Phép trừ volume còn lại dùng
float; `0.05 - 0.02` trong nhị phân không đúng 0.03, và sai số **tích luỹ** qua nhiều lần đóng
một phần liên tiếp — đúng thứ mục 7.3 yêu cầu tính chính xác. Đã đổi sang `Decimal` như tầng
`sizing` vẫn làm, kèm test khoá lại bằng `repr()`.

Đây là lý do nghiệm thu trên demo không thay thế được bằng test: bộ test dùng số tròn nên không
lộ ra sai số này.

### Trạng thái để lại

- `run_mode = PAUSED`, Bridge và clicker đã tắt.
- Còn mở: `PAIR-000026` (`OPEN`, cặp đối chứng), `PAIR-000027` (`PARTIALLY_CLOSED`, 0.03 hai
  bên), và vị thế Master 71489355 mồ côi từ `PAIR-000025`. **Cố ý giữ** — đây là dữ liệu
  `ORPHANED` và `PARTIALLY_CLOSED` thật, đúng thứ bộ đối chiếu phase 8 cần để thử.
- Đã đặt **4 lệnh thật** trong lượt này, dưới hạn mức 10.

### Chưa làm, thuộc phase sau

Tiêu chí "chạy một phiên 60 phút với chạm SL, bật tắt công tắc giữa chừng" mới nghiệm thu được
phần cốt lõi bằng bốn thao tác trên. Cascade (`can_close_master = 1`) và `EMERGENCY` **chỉ được
kiểm bằng test tự động**, chưa chạy trên demo — cả hai đều cần nhiều Client, mà cấu hình hiện
tại chỉ có một.

---

## Phase 8 — Mất kết nối và đối chiếu

### `bridge/engine/reconcile.py`

So **ba nguồn**: bảng `pair`, snapshot Master, snapshot Client. Hai nguồn chỉ cho biết "có lệch",
ba nguồn mới cho biết **lệch ở đâu**. Toàn bộ 12 dòng của ma trận 8.4 đã cài, mỗi dòng một test.

Ba quyết định đáng ghi lại:

- **`Reconciler` cầm `CloseFlow`, không cầm `CommandDispatcher`.** Nhờ vậy nó thừa hưởng mọi cổng
  an toàn của phase 7 — một lệnh đóng mỗi cặp, cảnh báo cặp ghép suy đoán — thay vì tự tạo
  command và đi vòng qua chúng. Đây cũng là cách thoả mục checklist "đối chiếu chạy đồng thời
  với cascade không tạo command trùng" mà không cần thêm cơ chế nào.
- **`ACK_LOST` không có thẻ là `DECISION`.** Ghép sai ở đó nghĩa là gắn vị thế của người dùng vào
  một cặp, rồi phase 7 sẽ đóng nó. `accept_all_safe()` không chạm tới được.
- **Vị thế Client mở tay không mang thẻ thì không vào danh sách.** Nhận dạng theo thẻ và theo
  bảng `pair`, không theo magic — lệnh mở qua giao diện cũng có `magic = 0` (D-07b), nên nhận
  dạng bằng magic sẽ lôi cả lệnh của người dùng vào.

Mức alert theo 8.2: **Master offline là CRITICAL, Client offline là ERROR**. Mất Master là mù
hoàn toàn về nguồn lệnh; mất một Client chỉ mất một nhánh copy.

### Ba lỗi tự tìm ra, đều thuộc loại "làm người vận hành ngừng đọc alert"

Cả ba đều lộ ra khi nhìn dữ liệu demo thật chứ không phải khi viết test.

1. **Cặp `ORPHANED` bị báo lại mỗi 60 giây.** Nhưng `ORPHANED` nghĩa là đã phát hiện, đã có
   alert, đang chờ người — nhắc lại mỗi phút là vô nghĩa. Đã loại khỏi ma trận.
2. **Sai lệch chưa xử lý bị ghi lại mỗi vòng.** Thêm cổng lọc trùng: đã có finding cùng loại,
   cùng khoá, đang `PENDING` thì không ghi thêm. Danh sách finding mà đầy dòng trùng thì người
   ta ngừng đọc nó, và nó mất luôn tác dụng của chính mình.
3. **Vòng đối chiếu tự động chạy trước khi Master kịp lên**, để lại alert `RECONCILE_NO_SNAPSHOT`
   báo giả. Client thường nối trước Master. Đã sửa hai lớp: chờ Master `ONLINE` trước khi chạy,
   và `_snapshot()` chờ trong hạn thay vì bỏ cuộc ngay khi thấy agent chưa `ONLINE`.

### Một bài học về API, cần cho phase 9

`run()` trả về `run_id`, và phản xạ tự nhiên là liệt kê finding theo `run_id` đó. **Sai** kể từ
khi có cổng lọc trùng: một sai lệch đã được vòng trước ghi sẽ không xuất hiện trong `run_id` mới.
Tôi đã tự vấp đúng chỗ này khi viết kịch bản nghiệm thu — nó báo "0 sai lệch" trong khi finding
nằm sẵn trong DB từ vòng tự động trước đó.

**Dashboard phase 9 phải hiển thị "mọi finding đang `PENDING`", không phải "finding của lần chạy
gần nhất".**

### Nghiệm thu trên demo: ĐẠT

Dựng sai lệch thật bằng đúng kịch bản checklist yêu cầu: `run_mode = PAUSED`, người dùng đóng tay
vị thế Master `71489357`. Event tới nơi và bị `IGNORED` với lý do `run_mode = PAUSED` — sổ sách
vẫn ghi cặp `OPEN` trong khi Master thật đã đóng.

Vòng đối chiếu **tự chạy khi agent nối lại** và sinh đúng một finding:

```
#1 [SAFE] MASTER_CLOSED_OFFLINE  pair=PAIR-20260905-000026  -> CLOSE_CLIENT
   DB     : status=OPEN, M71489357, C71489358, volume 0.01/0.01, tag CB5e9a669d8a
   Master : None
   Client : {position_id: 71489358, BTCUSD.s, SELL, 0.01, magic: 0, comment: 'CB5e9a669d8a'}
```

`evidence_json` có đủ cả ba nguồn, đúng yêu cầu "người vận hành phải thấy bằng chứng chứ không
chỉ thấy kết luận". Sau `accept`: cặp `CLOSED`, `close_source = BOT`, và snapshot sau đó xác nhận
vị thế `71489358` đã **thực sự biến mất** khỏi terminal Client.

`run_mode` giữ `PAUSED` suốt quá trình — không có đường nào tự chuyển sang `RUNNING` (D-15, 8.6).

### 432 test xanh (+25)

### Chưa nghiệm thu trên demo, chỉ có test tự động

Nhiều mục của checklist cần dựng tình huống mà cấu hình một-Client hiện tại không tạo được, hoặc
cần ngắt mạng thật:

- `offline_reopen_policy = IF_STILL_OPEN` với giá đã trôi — cần điều khiển giá.
- Ngắt terminal khỏi broker (giữ kết nối Bridge) để thử `DEGRADED`.
- Kịch bản hỗn loạn 30 phút của "Tiêu chí hoàn thành".

`CLOSE_MASTER` trong `offline_reopen_policy` **chưa cài** — mới có `NONE` và `IF_STILL_OPEN`
(bản `IF_STILL_OPEN` hiện dừng ở mức kiểm hai điều kiện rồi cảnh báo, chưa thực sự mở bù, vì
"được tự động ĐÓNG, không được tự động MỞ" là luật cứng và việc mở bù cần người bấm ở phase 9).

### Trạng thái để lại

`run_mode = PAUSED`, Bridge đã tắt. Còn `PAIR-000025` (`ORPHANED`) và `PAIR-000027`
(`PARTIALLY_CLOSED`) — giữ lại làm dữ liệu thật. Không đặt lệnh mới nào trong lượt này; nghiệm
thu dùng đúng một thao tác đóng tay của người dùng.

---

## Phase 9 — Dashboard và cấu hình

### Cấu trúc

`bridge/web/views.py` lắp dữ liệu (đọc DB, gắn nhãn, sắp xếp, tính chỉ số) và `bridge/web/app.py`
làm tầng HTTP. Tách đôi để test được phần lắp dữ liệu mà không cần dựng server. Dashboard chạy
**trong cùng tiến trình** với Bridge, trên cùng vòng lặp asyncio — nó đọc thẳng SQLite cục bộ và
gọi API tầng engine, nên không có đường nào để hai bên lệch trạng thái.

Giao diện là HTML/CSS/JS thuần, không framework. **Không tham chiếu nào ra ngoài máy** — không
CDN, không font tải về (có test khoá lại). Đúng lúc mất mạng là lúc cần nhìn thấy trạng thái nhất.

### D-16 thành một phép kiểm được, không còn là lời hứa

Thêm nhóm `UI` vào `bridge/labels_vi.py` với toàn bộ chữ trên màn hình. Template và JavaScript
**không chứa ký tự tiếng Việt nào**; chúng hiển thị đúng những gì API gửi xuống.

Phép kiểm viết theo hướng **đảo ngược**: file phải là ASCII, trừ một danh sách ngắn ký tự kiểu
chữ được phép (`·→—✕✓`). Bản đầu tôi liệt kê dấu tiếng Việt để tìm — sai, vì bảng chữ có hơn 130
ký tự có dấu và liệt kê thì sót. Liệt kê thứ *được phép* thì không sót được.

Cũng phải tách `ENUM_GROUPS` khỏi `ALL_GROUPS`: test cũ bắt mọi key nhãn phải là enum viết hoa,
mà key của nhóm `UI` là id chuỗi giao diện chứ không phải enum.

### Những chỗ giao diện có thể làm mất tiền

Ma sát tăng dần theo mức nguy hiểm, và mức cao nhất là **bắt gõ tay**:

- `Tạm dừng lệnh mới` — bấm thẳng, vô hại, hoàn tác được.
- `Dừng toàn bộ đồng bộ` — hộp xác nhận, vì nó bỏ rơi các cặp đang chạy.
- `Đóng khẩn cấp tất cả` — phải gõ đúng `DONG TAT CA`. Chuỗi **cố ý không dấu**: bắt gõ tiếng
  Việt có dấu trong lúc hoảng, với bộ gõ có thể đang ở chế độ khác, là tự tạo thêm rắc rối.
  Nút này đặt tách khỏi cụm thường ngày, căn về phía đối diện, viền đỏ.

Server kiểm chuỗi chứ không chỉ JavaScript: gõ sai thì trả 400 và **không sinh command nào**.

**Không tồn tại đường nào bỏ qua hàng loạt** — có test duyệt danh sách route để khoá lại. Bỏ qua
là hành động cho từng dòng, và mỗi dòng để lại một alert tồn tại.

`Bắt đầu copy` vẫn bấm được khi còn finding, nhưng mở hộp xác nhận liệt kê số mục đang bỏ lại.
Khoá nút thì người ta đi tìm cách lách; cho bấm nhưng bắt nhìn thẳng vào cái mình bỏ qua thì
hiệu quả hơn.

### Hai chi tiết lấy từ bài học các phase trước

**Màn hình sai lệch lấy mọi finding đang `PENDING`, không lọc theo `run_id`.** Đây đúng là cái
bẫy tôi tự vấp khi viết kịch bản nghiệm thu phase 8 — cổng lọc trùng của bộ đối chiếu làm sai
lệch cũ không xuất hiện trong `run_id` mới, nên lọc theo `run_id` sẽ giấu mất chính những dòng
chưa ai xử lý. Đã ghi thành test.

**Ô xem trước hệ số dùng ví dụ 0.01 chứ không phải 0.03.** Plan gợi ý 0.03, nhưng với step 0.01
thì 0.03 × 0.5 = 0.015 làm tròn xuống còn 0.01 — vẫn hợp lệ, nên dòng đó không lộ ra điều gì.
Lệnh nhỏ nhất sàn cho phép (0.01) mới là chỗ hệ số nhỏ làm **rơi hẳn** lệnh, và đó mới là thứ
người ta không nghĩ tới khi chỉ nhìn trường hợp đẹp.

### Nghiệm thu trên dữ liệu thật

Chạy `python -m bridge` và đọc API:

```
run_mode : Đã dừng
agent    : AG-CLICKER Mất kết nối | AG-CLIENT Kết nối | AG-MASTER Kết nối
chi so   : p50=606ms p95=1234ms hedge=1 can-can-thiep=3 to-do=True
cap      : 000025 | Mất hedge — còn Master  | SELL→BUY | 0.01 / 0.00
cap      : 000006 | Mở thất bại             | BUY→SELL | 0.01 / —
cap      : 000007 | Mở thất bại             | BUY→SELL | 0.01 / —
cap      : 000027 | Đóng một phần           | BUY→SELL | 0.03 / 0.03
```

Hai điều đáng nói. **p50 = 606 ms và p95 = 1234 ms khớp chính xác** số đo độc lập của phase 6b
(trung vị 604 ms) và lần OCT khởi động nguội (1234 ms) — chỉ số tính đúng trên dữ liệu thật.
Và bảng **sắp đúng theo mức nghiêm trọng**: mất hedge lên đầu, không phải theo thời gian.

### 456 test xanh (+23)

### Chưa làm được trong lượt này

- **Mở từ máy khác qua Tailscale** và **ngắt Internet giữ LAN**: cần máy thứ hai. Phần "không
  phụ thuộc Internet" đã kiểm được về mặt cấu trúc (không tham chiếu nào ra ngoài máy).
- **WebSocket cập nhật dưới 1 giây** và **xem trên điện thoại**: cần mắt người trước màn hình.
- **Trang cấu hình mới ở mức đọc.** Sửa hệ số, đổi `open_route`, lưu ánh xạ symbol chưa có API
  ghi — mới có API `verify` cho symbol và các hộp xác nhận đã chuẩn bị nhãn. Ghi rõ ở đây để
  không tưởng nhầm là đã xong.
- Tiêu chí "một người chưa từng đọc code ngồi vào và hiểu được" cần người thật thử.

---

## Phase 10 — Đóng gói, vận hành và nghiệm thu

*(2026-09-06.)*

### Migration đã chạy thật — rủi ro treo từ phase 6b đã đóng

`002_index_van_hanh.sql` (`idx_finding_dang_cho`, `idx_command_dang_bay`, `idx_alert_chua_xu_ly`)
đã chạy trên `data/bridge.db` **có dữ liệu thật**: version 1 → 2, sao lưu trước khi chạy, đối
chiếu sau khi chạy — 27 pair / 147 event / 87 command / 3 agent / 30 alert / 2 finding nguyên vẹn.
Tới trước lượt này bộ migration **chưa từng chạy quá version 1**, tức là đường nâng cấp schema
chưa từng được chứng minh. Giờ thì có.

Hai test migration trước đây khoá cứng `SCHEMA_VERSION` là con số cuối cùng nên hỏng ngay khi
thêm migration thứ hai — đã đổi sang so với `max(m.version for m in discover_migrations())`.

### Vận hành: `bridge/ops.py`, `bridge/alerting.py`, `bridge/admin.py`

Sao lưu bằng `VACUUM INTO` chứ không copy file — an toàn với WAL và không cần dừng dịch vụ. Copy
`bridge.db` khi WAL còn dữ liệu chưa checkpoint sẽ ra bản thiếu **đúng những giao dịch mới nhất**.
`bao_tri_hang_ngay` chạy retention rồi sao lưu rồi **tự mở lại bản vừa tạo để kiểm chứng**.

Kênh cảnh báo **đọc alert từ DB theo chu kỳ** chứ không móc vào `create_alert()`. Một lời gọi
mạng nằm trong đường ghi alert là một chỗ để cả hệ thống treo theo. Cái giá là trễ vài giây.
`_moc` khởi tạo bằng `MAX(id)` hiện tại nên khởi động lại không dội lịch sử cảnh báo vào điện
thoại người vận hành.

`bridge/admin.py` trả một món nợ ghi từ phase 3: cấp agent và cấp token vẫn làm bằng script tạm
viết ra scratchpad rồi vứt đi, và món nợ đó **đã cắn thật** — token clicker mất theo scratchpad
một phiên trước. Giờ là lệnh có tên: `liet-ke`, `them-agent`, `cap-token`, `thu-hoi`, `sao-luu`,
`bao-tri`, `run-mode`, `kiem-reason`.

### Audit D-01…D-26: hai chỗ lệch, đã sửa cả hai

Plan/10 vẫn viết "đối chiếu D-01…D-20" — hợp đồng nay là **D-01…D-26 (kèm D-07b)**, và
`docs/DECISIONS.md` đã đủ 27 mục. Đối chiếu từng mục với code:

1. **D-15 lệch thật.** `bridge/__main__.py` chỉ **cảnh báo** khi `run_mode != PAUSED` rồi chạy
   tiếp, với lý do "không đổi trạng thái sau lưng người vận hành". Nhưng `run_mode` nằm trong DB
   nên nó **sống sót qua mất điện**: máy tự bật lại lúc 3 giờ sáng với `RUNNING` còn nguyên là hệ
   thống tự vào lệnh khi chưa ai nhìn màn hình — đúng thứ D-15 tồn tại để chặn. Nay `ep_ve_paused()`
   đặt lại thật, kèm alert `KHOI_DONG_EP_PAUSED`. Cái giá là mỗi lần khởi động lại phải bấm
   `RUNNING` bằng tay, và đó là chủ đích.

2. **D-16 lệch ở 41 chỗ.** 41 chuỗi truyền cho `log.*` còn dấu tiếng Việt, tập trung ở module
   phase 3–4 (`server.py` 26, `dispatcher.py` 5, `repo.py` 4, còn lại rải rác). Không phải chuyện
   thẩm mỹ: console Windows mặc định cp1252 và ném `UnicodeEncodeError` giữa lúc ghi log — mất
   log đúng lúc cần nó nhất, và lỗi đó đã xảy ra thật trong phiên này. Đã bỏ dấu toàn bộ và
   **khoá bằng test** (`test_log_va_alert_khong_co_dau_tieng_viet`) quét bằng AST, chỉ soi đối số
   chuỗi của `log.*` và `create_alert` nên không đụng docstring hay `labels_vi.py`.

Một chỗ nữa không phải lệch quyết định nhưng cùng loại rủi ro: `xem_truoc_he_so()` ở dashboard
**viết lại** phép làm tròn thay vì gọi `round_to_step()` của engine. Một bản xem trước lệch với
thứ engine thật sự làm còn tệ hơn là không có xem trước. Đã đổi sang dùng chung.

Các quyết định còn lại đối chiếu **khớp**: D-01…D-14, D-17…D-26 đều có điểm neo trong code
(`MAX_RESEND_ATTEMPTS`, `DEFAULT_CASCADE_WAIT_MS = 15000`, `can_close_master DEFAULT 0`,
`ROUND_FLOOR`, `effective_multiplier` khoá lúc tạo pair, `open_tag_for`, `OPEN_UI` là loại
command riêng, `MENU_NEW_ORDER = 32848`, cổng canary).

### `UI_OPEN_BUSY`: chốt phương án 1

Ba lựa chọn ghi từ phase 6b, nay chọn **nâng WARNING → ERROR**, một dòng, không đụng hợp đồng.
Lý do quyết định là thứ mới có từ lượt này: từ Phase 10 chỉ **ERROR và CRITICAL** mới đi ra
Telegram. Bỏ một lệnh copy là **mất hedge**; để ở WARNING thì nó nằm lại trong dashboard cho tới
lúc có người tình cờ mở ra xem.

### TEST-23 thành một truy vấn chạy lại được

Bộ nghiệm thu yêu cầu kiểm **tự động**, không nhìn bằng mắt — vì nhìn mắt thì người ta xem ba
dòng đầu rồi kết luận, mà cái sai duy nhất có thể nằm ở dòng thứ hai mươi. `kiem_reason_client()`
+ `python -m bridge.admin kiem-reason`. Chạy trên database thật ngày 2026-09-06:
**`TEST-23 DAT: 25/25`**. Hai cặp `OPEN_FAILED` có `client_open_reason IS NULL` (chưa từng mở
được vị thế nào bên Client) nên không tính là vi phạm.

### Kiểm thử tải

| Bài | Kết quả |
|---|---|
| 10.000 event | nhận 802–831/s, xử lý 878–953/s, **0 event tồn**, không mất event |
| WAL | 4.144.752 byte → **0** sau `wal_checkpoint(TRUNCATE)` |
| 5 Client cùng lúc | 1 lệnh Master → **5 pair**, đóng Master → **cả 5 đóng**, đúng 5 command `CLOSE` |

Bài 5 Client lộ ra một chỗ đáng ghi: `position_id` chỉ duy nhất **trong phạm vi một tài khoản**,
và năm terminal khác nhau thật sự cùng sinh ra số `900001`. Đó chính là lý do ràng buộc duy nhất
là `(client_id, client_position_id)` chứ không phải riêng `client_position_id`. Test ban đầu
kiểm sai (theo một cột) và hỏng — **không phải lỗi sản phẩm**, đã sửa test.

### Ba tài liệu

`docs/RUNBOOK.md`, `docs/ACCEPTANCE.md`, `docs/BACKLOG.md`.

`ACCEPTANCE.md` có cột **Nguồn** với ba mức: **DEMO** (chạy trên sàn thật, đối chiếu journal hai
bên), **TEST** (chỉ mock, chưa chạm sàn), **KHÔNG** (chưa đạt, có lý do). Tổng: **DEMO 13 ·
TEST 9 · KHÔNG 3**. Tách ba mức là có chủ đích — một bảng toàn dấu tích không cho biết cái gì đã
được sàn thật xác nhận, mà đó là khác biệt đáng kể nhất khi chuyển sang tiền thật. Phase 7 đã
chứng minh: bộ test dùng số tròn nên **không** lộ ra lỗi float `0.030000000000000002`, chỉ phiên
demo mới lộ.

### 484 test xanh (+28) và 3 test tải

`ruff` sạch. `grep -ri "token" logs/` ra **0 dòng** trên ~15.000 dòng log thật.

### Không làm được trong lượt này — cần môi trường thật

Không phải "chưa kịp", mà là **không thực hiện được trên một laptop cá nhân**:

- Đăng ký Windows Service / NSSM cho Bridge, Scheduled Task + autologon cho clicker.
- Tailscale ACL, firewall Windows, và bài kiểm port bằng **máy thứ ba**.
- **TEST-19 — rút điện thật.** Đây là mục duy nhất mà việc không chạy để lại **rủi ro chưa đo**:
  toàn bộ lập luận về mất điện hiện dựa vào `synchronous = FULL` chứ không dựa vào quan sát.
- Chạy 24 giờ liên tục (rò rỉ bộ nhớ, tốc độ tăng DB).
- Gửi tin Telegram thật (đường gửi có test, nhưng chưa từng có tin nào tới điện thoại).
- TEST-08 nhiều symbol — **chặn bởi B-01**, không phải bởi thời gian.

Cả sáu đều đã vào `RUNBOOK.md` mục 6 và mục 8, và `BACKLOG.md`. Không mục nào biến mất.

### Trạng thái để lại

`run_mode = PAUSED`, Bridge và clicker đã tắt. Không đặt lệnh thật nào trong lượt này. Còn
`PAIR-000025` (`ORPHANED`) và `PAIR-000027` (`PARTIALLY_CLOSED`) — giữ lại làm dữ liệu thật.
`data/bridge.db` ở schema version 2, có một bản sao lưu đã kiểm chứng trong `data/backup/`.

- **[Đánh giá tổng thể 2026-09-06](docs/DANH-GIA-TONG-THE.md)** — kiểm toán độc lập sau Phase 10. Kết luận **NO-GO**; ba lỗi đang hoạt động (F-01 nút khẩn cấp không đóng Master, F-02 dashboard không xác thực, F-03 clicker rớt OFFLINE) và một lệch hợp đồng D-19.

---

## Phase 11 — Sửa các lỗi kiểm toán tìm ra

*(2026-09-06, ngay sau lượt kiểm toán độc lập.)*

### Việc quan trọng nhất: nút dừng khẩn cấp giờ mới thật sự dừng

Kiểm toán tìm ra `emergency_close_all()` chỉ đóng phía Client rồi kết thúc, trong khi docstring và
alert CRITICAL đều nói "Client trước Master sau" (F-01). Sửa xong ở tầng Bridge thì **nghiệm thu
trên demo lộ ra một tầng sâu hơn**: EA Master trả về `Command type not supported by this agent
role` — nó **không thực thi được lệnh nào**, và test hợp đồng `test_chi_ea_client_duoc_dat_lenh`
cấm hẳn `OrderSend` trong file Master.

Tức là **hai quyết định không thể cùng đúng**: ranh giới "chỉ EA Client đặt lệnh" so với D-09
(cascade đóng Master) và TEST-21 (đóng khẩn cấp, Client trước Master sau). Mâu thuẫn này tồn tại
từ phase 5 và không ai thấy vì đường đóng Master **chưa từng chạy đầu-cuối** — kiểm toán đếm được
0 lệnh đóng nào từng gửi cho Master trong toàn bộ lịch sử database.

Đã dừng lại hỏi thay vì tự chọn. Hướng người dùng chọn: **cho EA Master ĐÓNG, vẫn cấm MỞ.**

Ranh giới mới tinh hơn nên cũng khoá tinh hơn (`test_chi_ea_client_duoc_MO_lenh`): mọi `OrderSend`
trong code dùng chung phải đặt `request.position` — chỉ đóng được vị thế đã tồn tại; đường mở chỉ
nằm trong `CopyBridgeClient.mq5`; `CMasterAgent::OnCommand` cố ý không nhận loại `OPEN`.

Cách cài: chuyển `PickFilling`, `Guard`, `DoClose`, `DoClosePartial`, `ClosePartOf` **nguyên văn**
từ `CopyBridgeClient.mq5` lên `CBridgeAgent` trong `CopyBridgeCommon.mqh`, không đổi cây kế thừa.
Client mất 190 dòng trùng lặp, Master thêm một `OnCommand` chỉ nhận lệnh đóng.

### Nghiệm thu TEST-21 trên demo: ĐẠT

Ba vòng đo, và hai vòng đầu **không đạt** — ghi lại vì chúng là phần có ích nhất:

| Vòng | Kết quả |
|---|---|
| 13:35 (EA cũ) | 2 lệnh đóng gửi tới Master, cả hai `ACK_FAILED`. Cặp chuyển `ORPHANED` + 2 alert CRITICAL. **Đúng cách hỏng** — trước phase 11 cùng tình huống báo `closed: 3` và ghi `CLOSED`. |
| 13:44 (đã biên dịch, chưa nạp) | Vẫn `ACK_FAILED`. Nguyên nhân: **đổi khung thời gian chart chỉ gọi lại `OnInit` trên bản EA đã nạp trong bộ nhớ, MT5 không đọc lại `.ex5`**. Phải gỡ EA rồi gắn lại. Đã ghi vào RUNBOOK. |
| 13:49 (bản mới đã nạp) | **ĐẠT.** `master_position` còn OPEN = **0**; hai lệnh `CLOSE` tới `AG-MASTER` đều `ACK_OK` (10009 Request executed); thứ tự đúng — Client 06:49:19.179, Master 06:49:20.304; toàn bộ **1.125 ms**. |

Biên dịch bằng dòng lệnh, không cần mở giao diện:
`MetaEditor64.exe /compile:"<file>.mq5" /log:"<log>"` → cả ba file **0 lỗi, 0 cảnh báo**.
(Lượt đầu tôi kết luận vội là không biên dịch được ở đây; người dùng chỉ ra là sai.)

### Năm sửa còn lại

- **F-02** — `parse_config` từ chối khởi động khi `host` không phải loopback mà
  `dashboard_password` rỗng; mặc định `host` đổi thành `127.0.0.1`. Chứng minh bằng chính
  `config.toml` đang dùng: Bridge từ chối chạy, kèm thông báo nêu cả hai đường sửa. Sau khi đặt
  mật khẩu, `/api/emergency`, `/api/run_mode` và `/api/snapshot` gọi không cookie đều trả **401**
  (trước đó cả ba trả 200).
- **F-03** — nhịp heartbeat của clicker 5 s → **1 s**, khớp EA, trong khi hạn của Bridge là 5 s.
  Đo 36 phút liên tục: **0** alert `AGENT_OFFLINE` cho clicker (hôm kiểm toán: 1 lần trong ~10 phút).
- **F-05** — thêm `ORPHAN_RESOLVED`: cặp `ORPHANED` mà **cả hai chân đều biến mất** thì sinh
  finding đề xuất `MARK_CLOSED`. Chạy thật: hai cặp mồ côi được phát hiện, duyệt, và đóng sổ —
  vòng khép kín này trước phase 11 không tồn tại.
- **F-06** — báo cáo đối chiếu nay ghi cả *"N sai lệch mới"* lẫn *"M đang chờ xử lý"*. Thấy ngay
  trong log thật: `0 sai lech moi, 4 dang cho xu ly`.
- **F-01b** — `mark_pair_closed()` từng đưa **cả** `master_current_volume` về 0 chỉ dựa vào ack
  của Client; đó là lý do F-01 vô hình. Nay chỉ về 0 khi `master_position` thật sự `CLOSED`, và
  `zero_master_volume()` dọn nốt khi EA Master ack.

### D-19: sửa quyết định, không sửa code

Kiểm toán phát hiện `effective_multiplier` **không hề xuất hiện** trong đường đóng một phần —
code lấy tỷ lệ trên volume còn lại. Hai công thức lệch nhau khi có làm tròn (Master 1.00 hệ số
0.5, đóng 0.25 ba lần: bản đang chạy để lại 0.130, chữ của D-19 để lại 0.140, lý tưởng 0.125).

Bản đang chạy **đúng hơn** vì nó tự thu lại phần dư do làm tròn xuống. Người dùng chọn sửa quyết
định cho khớp code. Đã cập nhật `docs/DECISIONS.md` và `plan/00-README.md`, và cho
`_soi_lech_volume` dùng cùng công thức: dung sai theo `volume_step` thay vì `1e-6`, và bỏ chặn
`status != OPEN` — bộ dò lệch trước đó **bị tắt đúng trên nhóm cặp duy nhất có thể lệch**.

### 500 test xanh (+16), `ruff` sạch

Test đáng chú ý nhất là bản thay thế cho `test_emergency_dong_het_client_truoc` — test cũ mang
tên "đóng hết Client trước" nhưng **không kiểm gì về phía Master**, tức nó đang khoá lại chính
khiếm khuyết. Bản mới kiểm `master_position.status`, số lệnh gửi cho agent MASTER, thứ tự
Client-trước-Master, trường hợp nhiều cặp chung một vị thế Master chỉ sinh **một** lệnh đóng, và
sổ sách không còn giữ volume Master cũ.

Thêm test ghim D-19 bằng **con số chính xác** (0.13) thay vì một khoảng — chuỗi đóng mà hai công
thức cho kết quả khác nhau, đúng chỗ bộ test cũ đi lướt qua.

### Đã dùng 8/10 lệnh demo

Cấu hình đã trả về `OPPOSITE`/1.0, `run_mode = PAUSED`, Bridge và clicker đã tắt, token clicker đã
thu hồi, hai terminal **không còn vị thế nào**, 35 cặp `CLOSED` + 2 `OPEN_FAILED`.

**`config.toml` hiện mang mật khẩu thử `kiem-thu-phase-11` — phải đổi trước khi dùng thật.**

### Còn treo

Bốn finding `PENDING` (1 `BOTH_CLOSED`, 3 `UNPAIRED_MASTER`) giữ nguyên — xử lý chúng là sửa dữ
liệu, không thuộc lượt này. `PAIR-000007` và `000008` là `CLOSED` nhưng còn `master_current_volume`
khác 0: dữ liệu sinh ra giữa lúc đang sửa, ghi thành B-12.

F-07, F-08, F-10…F-12 chuyển thành **B-08…B-13** trong `docs/BACKLOG.md`, không mục nào rơi mất.

Một test dao động: `test_ack_rejected_duoc_thu_lai` hỏng một lần rồi xanh lại khi chạy riêng và ở
mọi lần chạy sau. Phụ thuộc thời gian, chưa truy nguyên.

### Phase 11, lượt hai — dọn nốt B-08…B-13

*(Cùng ngày. Không đặt lệnh demo nào; các mục này không cần terminal.)*

- **B-08 — mức alert theo hậu quả thật.** `VOLUME_BELOW_MIN`, `PARTIAL_CLOSE_ROUNDS_TO_ZERO` và
  `KHOI_DONG_EP_PAUSED` lên ERROR: cả ba đều nghĩa là "đã mất hedge" hoặc "đã ngừng copy", mà chỉ
  ERROR trở lên mới ra được Telegram. `RECONCILE_FINDINGS` thì **không** đặt một mức cố định —
  nó lấy mức theo mức nghiêm trọng thật của finding trong vòng đó: có `DECISION` thì ERROR, toàn
  `SAFE` thì WARNING. Sai lệch tự dọn được không đáng làm phiền điện thoại lúc 3 giờ sáng.
- **B-09 — nhắc lại sai lệch bị bỏ quên.** Cổng chống trùng khiến mỗi sai lệch chỉ báo một lần —
  đúng, nhưng rồi im luôn, và kiểm toán tìm thấy một finding nằm `PENDING` suốt cả ngày. Thêm
  `FINDING_BO_QUEN` (ERROR) khi cái cũ nhất quá `finding_nhac_sau_phut`, mặc định 60. Mốc nhắc ghi
  vào `system_config` chứ không giữ trong bộ nhớ: khởi động lại không được thành một cách vô tình
  để im lặng mãi.
- **B-10 — `cap-token` bật lại agent đã thu hồi.** Trước đó nó chỉ đổi hash, nên người vận hành
  cầm một token trông hợp lệ mà agent vẫn bị từ chối với `AGENT_DISABLED` và không có manh mối gì.
  Chính tôi vấp phải lúc dựng lại clicker ở lượt trước.
- **B-11 — `bridge.admin cau-hinh-client`.** Xem và sửa `copy_mode`, `volume_multiplier`,
  `open_route`, `can_close_master`, có ràng buộc và có nói rõ cặp đang chạy giữ nguyên tỷ lệ cũ.
  Trước đó phải `UPDATE` thẳng vào SQLite — và để chạy đúng một mục nghiệm thu thì đã phải làm thế
  thật.
- **B-12 — `don_so_sach()`**, chạy trong `bao_tri_hang_ngay`. Đưa `master_current_volume` về 0 cho
  cặp `CLOSED` mà vị thế Master **thật sự** đã đóng; không suy diễn từ trạng thái của cặp. Đã chạy
  trên database thật: sửa 2 dòng, còn 0.
- **B-13 —** test canh gác D-16 nay quét cả `clicker/`.

Một lỗi tự bắt được khi viết B-09: câu `SELECT created_at, COUNT(*) ...` không có `MIN()` sẽ cho
`created_at` của một dòng bất kỳ, nên "cái cũ nhất" là sai. Đã sửa trước khi chạy.

`config.toml` đã đổi sang mật khẩu ngẫu nhiên 28 ký tự; kiểm chứng thật: mật khẩu cũ → 401, mật
khẩu mới → 200, gọi không cookie → 401.

**512 test xanh (+12), `ruff` sạch.** `docs/BACKLOG.md` còn đúng 7 món nợ B-01…B-07, tất cả đều
cần môi trường thật hoặc nhiều Client.

### Rà soát chuẩn bị chạy thật trên MỘT VPS

*(2026-09-06, sau khi B-08…B-13 của lượt trước đã đóng.)*

Kiến trúc một-VPS **khác** kiến trúc mà `RUNBOOK.md` mục 6 giả định. Rà soát lại theo đúng kịch
bản đó tìm ra hai mục và làm rõ một mục thứ ba.

**Mục đã rơi khỏi danh sách theo dõi — nay là B-08.** Bài "lặp lại với phiên RDP đã ngắt" ghi từ
phase 6b, đánh dấu "chuyển sang phase 10 vì máy đo là laptop", rồi **không xuất hiện ở bất cứ đâu
nữa** — không có trong `BACKLOG.md`, không có trong checklist của `plan/10`. Trên laptop nó là mục
nice-to-have; trên VPS nó là **trạng thái vận hành bình thường**, vì người ta RDP vào rồi ngắt ra.
Toàn bộ đường mở lệnh dựa vào clicker `PostMessage`, và lập luận "không cần desktop tương tác"
chưa bao giờ được đo — bản gần đúng duy nhất là 5/5 probe với cửa sổ minimized.

**B-09 — Bridge mù với Algo Trading.** `MQL_TRADE_ALLOWED` chỉ được kiểm bên trong EA, không đi
vào `hello` hay `heartbeat`. Bất đối xứng: đường **mở** phía Client đi qua giao diện nên không cần
Algo Trading, đường **đóng** đi qua EA nên cần. Terminal có Algo Trading tắt sẽ mở lệnh bình
thường rồi chỉ hỏng lúc đóng — tích luỹ vị thế một chiều trước khi báo `CLOSE_FAILED`. Sau khi VPS
khởi động lại hoặc MT5 tự cập nhật, đây là trạng thái hoàn toàn có thật.

**Rủi ro điều khoản, không phải kỹ thuật.** Hai tài khoản mở vị thế ngược chiều, cùng symbol, cách
nhau dưới một giây, **từ cùng một IP** là dấu vết rất dễ nhận. Nhiều broker cấm hoặc huỷ lợi nhuận
từ mô hình này, và nó không hiện ra trong bất kỳ log nào cho tới lúc tài khoản bị xử lý.

**Cái gì biến mất khi chạy một-VPS.** Agent đi loopback, nên `host = "127.0.0.1"` đóng hẳn cả hai
cổng — không cần Tailscale ACL, firewall hay máy thứ ba. Đo được: `host = "0.0.0.0"` cho `netstat`
ra `0.0.0.0:8787 LISTENING`, tức đang mở ra toàn mạng. Cái giá là dashboard chỉ mở được từ trong
VPS.

**Cấu hình máy, đo thật:** mỗi terminal MT5 ~157 MB, Bridge ~49 MB, clicker ~4 MB. Cộng Windows
Server thì 4 GB RAM là mức nên có; 2 GB sẽ chật.

Đã thêm mục **5b — Triển khai tất cả trên một VPS** vào `RUNBOOK.md`, kèm bảng đối chiếu chỉ rõ
mục 6 chỗ nào thay bằng gì, và đổi tiêu đề mục 6 thành "kiến trúc NHIỀU MÁY" để không ai đọc nhầm.

Không sửa code ở lượt này. 512 test xanh, `ruff` sạch, `run_mode = PAUSED`.

### B-09 — Bridge nhìn thấy được Algo Trading, và không mở cái không đóng được

*(2026-09-06, sau lượt rà soát VPS.)*

Bất đối xứng: đường **mở** phía Client đi qua giao diện nên không cần Algo Trading, đường **đóng**
đi qua EA nên cần. Một terminal tắt Algo Trading vẫn mở lệnh bình thường và chỉ hỏng lúc đóng —
tích luỹ vị thế một chiều rồi mới báo `CLOSE_FAILED`. Sau khi VPS khởi động lại hoặc MT5 tự cập
nhật, đây là trạng thái hoàn toàn có thật.

- EA gửi `trade_allowed` (`MQL_TRADE_ALLOWED`) trong heartbeat, cả Master lẫn Client.
- `HeartbeatMessage.trade_allowed` là **tuỳ chọn**: clicker không có khái niệm đó và EA bản cũ
  không gửi. **"Không biết" khác "biết là tắt"** — chặn vì không biết sẽ làm hệ thống tự dừng mỗi
  khi nâng cấp lệch phiên bản.
- Migration `003` thêm cột `agent.trade_allowed`. Đã chạy trên `data/bridge.db`: version 2 → 3,
  37 pair / 191 event / 263 command / 3 agent / 57 alert / 7 finding nguyên vẹn.
- Báo `TRADE_NOT_ALLOWED` mức ERROR **khi cờ đổi**, không phải mỗi nhịp heartbeat — khoá theo
  chính cờ này chứ không dùng `_alert_on_transition` (hàm đó khoá theo `status` của agent, dùng
  ở đây là lẫn lộn hai thứ). Bật lại thì báo `TRADE_ALLOWED_AGAIN` mức INFO.
- **Cổng thứ ba ở `_ui_route_blocked`:** Client báo `trade_allowed = 0` thì **không gửi `OPEN_UI`**.
  Đừng mở cái mà không đóng được.
- Dashboard hiện trạng thái này cho agent EA; `NULL` hiện là "không biết", không hiện thành "ổn".

Cố ý **không** đặt agent sang `DEGRADED`: terminal vẫn gửi event và sổ sách vẫn đúng, cái hỏng chỉ
là khả năng đóng. Cổng chặn nằm ở đường mở.

Ba file EA biên dịch lại: **0 lỗi, 0 cảnh báo**. Chưa nạp lại trên terminal — cần gỡ EA ra gắn lại
(RUNBOOK mục 2), và **chưa nghiệm thu đầu-cuối trên demo**.

### Rà soát tài liệu

- `docs/ACCEPTANCE.md` ghi "478 test xanh" đã lạc hậu → 518.
- `docs/DANH-GIA-TONG-THE.md` là bản ghi tại một thời điểm, **cố ý giữ nguyên**; thêm khối dẫn ở
  đầu nói rõ F-01…F-12 đã xử lý xong, để người đọc không tưởng đó là hiện trạng.
- `docs/RUNBOOK.md` mục 7 thêm `TRADE_NOT_ALLOWED` và `CLIENT_TRADE_NOT_ALLOWED`.
- Đối chiếu lại: 27 quyết định khớp giữa `DECISIONS.md` và `plan/00-README.md`; `ARCHITECTURE.md`
  không có chỗ nào mâu thuẫn với việc EA Master nay đóng được lệnh.

**518 test xanh (+2) và 3 test tải, `ruff` sạch.**

### Kế hoạch chạy thật

Viết `docs/KE-HOACH-CHAY-THAT.md`: ba giai đoạn theo thứ tự nên làm, tách rõ **cái gì làm được
trên máy hiện tại** (nghiệm thu B-09, Telegram thật, chạy lại nghiệm thu sau khi EA đổi) khỏi
**cái gì chỉ VPS mới đo được** (B-08 phiên RDP ngắt, TEST-19 mất điện — trên VPS thì *force stop*
làm được, chạy 24 giờ) và **cái gì không phải kỹ thuật** (điều khoản broker: hai tài khoản ngược
chiều cùng một IP).

Kèm bảng "đã có bằng chứng, khỏi kiểm lại" để lần sau không ai chạy lại thứ đã chứng minh.

Rà soát cũng xác nhận: không còn `TODO`/`FIXME` nào trong `bridge/`, `clicker/`, `ea/`, `tests/`;
không test nào bị `skip`/`xfail`; không tham chiếu file hỏng trong `docs/`; và cấu trúc mọi bảng
của `data/bridge.db` **khớp hoàn toàn** với một database tạo mới từ đầu.

### Bỏ Telegram — dựng cơ chế bù `tinh-hinh`

*(2026-09-06. Người dùng chốt không dùng kênh cảnh báo ngoài.)*

Lựa chọn hợp lệ, nhưng nó vô hiệu hoá một giả định mà cả phase 10–11 dựa vào: việc nâng
`ORPHANED_MASTER`, `CLOSE_FAILED`, `TRADE_NOT_ALLOWED`, `KHOI_DONG_EP_PAUSED`… lên ERROR có ý
nghĩa **vì** "chỉ ERROR trở lên mới đi ra ngoài". Không có kênh ra thì việc phân mức vẫn đúng
nhưng không ai nhận. Tình huống phải chấp nhận: VPS khởi động lại lúc 3 giờ sáng → `run_mode` bị
ép về `PAUSED` (D-15) → ngừng copy hoàn toàn → không ai biết cho tới lần đăng nhập tiếp theo.

Cơ chế bù hợp với cách VPS thực sự được vận hành (người ta RDP vào theo thói quen):
**`python -m bridge.admin tinh-hinh`** trả lời đúng một câu hỏi — *có gì cần làm không?* Gom
`run_mode` (nói rõ `PAUSED` nghĩa là đang không copy), trạng thái từng agent kèm Algo Trading,
cặp cần can thiệp, sai lệch đang chờ kèm tuổi, cảnh báo ERROR/CRITICAL **chưa xác nhận**, và tuổi
bản sao lưu gần nhất. **Thoát khác 0 khi có việc cần làm**, để cắm được vào Scheduled Task sau này.

Dùng lại `views.trang_thai_chung()` và `views.chi_so()` thay vì viết truy vấn thứ hai — dashboard
và lệnh này không bao giờ được nói khác nhau. Cột `alert.acknowledged_at` đã có sẵn từ phase 9,
chỉ chưa ai đọc nó từ dòng lệnh.

Chạy trên database thật: báo đúng 4 mục cần chú ý (`PAUSED`, 2 cặp `OPEN_FAILED`, 4 sai lệch đang
chờ, 25 cảnh báo chưa xem), mã thoát 1. Hiển thị "Algo Trading: khong ro" cho cả hai EA — trung
thực, vì chúng chưa nạp bản mới nên chưa gửi `trade_allowed`.

Tài liệu: `KE-HOACH-CHAY-THAT.md` mục 1.2 đổi từ "làm Telegram" thành "đã bỏ, và đây là hệ quả"
kèm lịch kiểm tay; `RUNBOOK.md` mục 5 đưa `tinh-hinh` lên thành việc đầu tiên mỗi lần đăng nhập;
`BACKLOG.md` thêm mục **"Quyết định có chủ đích, KHÔNG phải thiếu sót"** để lượt rà soát sau không
ghi Telegram thành món nợ rồi "sửa" nó.

`bridge/alerting.py` giữ nguyên — bật lại chỉ là điền hai khoá vào `config.toml`.

**523 test xanh (+5), `ruff` sạch.**

### Nghiệm thu B-09 trên demo — và một lỗi chỉ lộ ra khi chạy thật

*(2026-09-06.)*

Bản sửa B-09 đầu tiên **kiểm sai cờ**. `MQLInfoInteger(MQL_TRADE_ALLOWED)` không phải nút
**Algo Trading** trên thanh công cụ — nó là ô tick *riêng của EA* trong hộp thoại thuộc tính. Nút
trên thanh công cụ là `TerminalInfoInteger(TERMINAL_TRADE_ALLOWED)`.

Đo được trên demo: tắt nút Algo Trading trên Client, `trade_allowed` **vẫn báo 1** với heartbeat
mới 0,6 giây. Ép EA đóng một lệnh thì nó **không** từ chối mà gọi thẳng `OrderSend`, và terminal
trả về `retcode 10027 "AutoTrading disabled by client"`.

Đây không phải lỗi mới của phase 11: chỗ kiểm sẵn có trong `OnCommand` **luôn** dùng đúng cờ sai
đó, và thông báo của nó ghi *"Auto trading is disabled in the terminal"* — nói "terminal" trong
khi đọc cờ của chương trình. Nó chưa bao giờ lộ ra vì chưa ai tắt nút đó rồi thử đóng lệnh.

**Sửa:** `CbTradeAllowed()` trong `CopyBridgeCommon.mqh` kiểm **cả bốn** điều kiện —
`TERMINAL_TRADE_ALLOWED`, `MQL_TRADE_ALLOWED`, `ACCOUNT_TRADE_ALLOWED`, `ACCOUNT_TRADE_EXPERT`.
Mọi chỗ kiểm quyền giao dịch trong hai EA gọi hàm này; test hợp đồng cấm gọi cờ lẻ.

**Rồi lỗi thứ hai, cùng loại:** sau khi bật lại nút Algo Trading, `trade_allowed` **vẫn** là 0, và
bản sửa không nói được điều kiện nào đang chặn — nó chỉ biết "tắt". Thêm `CbTradeBlockReason()`
viết ra đúng chỗ đang chặn, dùng cả trong log khởi động lẫn thông báo từ chối. Nguyên nhân thật:
**ô "Allow Algo Trading" riêng của EA bị bỏ tick** khi gắn EA lúc nút toàn cục đang tắt — và bật
lại nút trên thanh công cụ **không** tick lại ô đó. Đây là cái bẫy vận hành sẽ gặp lại trên VPS.

**Nghiệm thu, đủ bốn vế:**

| Vế | Kết quả |
|---|---|
| Khoẻ | `trade_allowed = 1` cho cả hai EA; clicker `NULL` đúng thiết kế |
| Tắt Algo Trading | `= 0` trong ~1 giây, alert `TRADE_NOT_ALLOWED` mức ERROR |
| Cổng chặn | **0** lệnh `OPEN_UI`, **0** cặp mới, event `IGNORED` lý do "Algo Trading tat phia Client", alert `CLIENT_TRADE_NOT_ALLOWED` |
| Phục hồi | `TRADE_ALLOWED_AGAIN` mức INFO, copy chạy lại: `PAIR-000012`, `reason = 0` |

Hệ quả phụ quan sát được: hai lệnh Master bị cổng chặn **nằm lại không có cặp**, nên nút đóng
khẩn cấp không biết tới chúng (nó chỉ duyệt bảng `pair`). Bộ đối chiếu bắt đúng cả hai thành
`UNPAIRED_MASTER`. Đây là hành vi đúng, nhưng người vận hành phải biết: **chặn copy nghĩa là để
lại vị thế Master một chiều cần xử lý tay.**

Đã dùng 5 lệnh demo. Trả máy sạch: `run_mode = PAUSED`, hai terminal không còn vị thế nào, token
clicker đã thu hồi, Bridge và clicker đã tắt.

**524 test xanh (+1), `ruff` sạch.**

### Mục 1.3 — chạy lại nghiệm thu sau khi EA đổi: ĐẠT

*(2026-09-06. Giai đoạn 1 của `KE-HOACH-CHAY-THAT.md` hoàn tất.)*

EA Client bị chuyển 190 dòng sang file dùng chung, EA Master có thêm khả năng đóng lệnh, và cách
kiểm quyền giao dịch được viết lại — cả ba đều nằm trên đường đi của mọi lệnh thật, nên phải chạy
lại chứ không suy ra từ lần trước.

Ba lệnh Master dựng ba cặp cùng `BTCUSD.s`, rồi:

| Bài | Kết quả |
|---|---|
| TEST-02 | Master BUY→Client SELL và Master SELL→Client BUY, 1:1, `reason = 0` cả ba |
| TEST-03 | Đóng hẳn `71489808` → `PAIR-000013` `CLOSED` sau **272 ms**, đúng một lệnh `CLOSE` |
| TEST-06 | Đóng bớt 0.01 của `71489810` → Client 0.02→**0.01**, `CLOSE_PARTIAL` volume đúng 0.01, **285 ms** |
| TEST-07 | Cặp đối chứng `PAIR-000015` **không bị đụng** — chứng minh tra theo `position_id` chứ không theo symbol |
| TEST-21 | Đóng khẩn cấp: `master_position` OPEN = **0**, hai lệnh đóng Master `ACK_OK`, Client 09:30:46.005 **trước** Master 09:30:46.598, toàn bộ 1.101 ms |
| TEST-23 | `kiem-reason` → **40/40** |

Dùng 3 lệnh demo. Trả máy sạch: `run_mode = PAUSED`, 0 vị thế trên cả hai terminal, 0 cặp chưa
đóng, token clicker đã thu hồi, Bridge và clicker đã tắt.

**Giai đoạn 1 xong.** Còn lại là giai đoạn 2 (dựng VPS: B-08 phiên RDP ngắt, TEST-19 mất điện,
chạy 24 giờ) và giai đoạn 3 (điều khoản broker).

### File hướng dẫn cho người dùng cuối

*(2026-09-06.)*

`docs/HUONG-DAN-SU-DUNG.html` — một file tự chứa 200 KB, mở offline được, gửi qua email/chat được.
Viết cho **người biết dùng máy nhưng không biết lập trình**, khác hẳn `RUNBOOK.md` vốn giả định đã
theo dự án từ đầu.

Chia hai phần theo đúng yêu cầu: **A — tất cả trên một VPS** và **B — Master ở máy riêng**.

Điều quan trọng nhất trong tài liệu này không phải phần cài đặt mà là **một khối cảnh báo ở đầu
Phần B**: kiến trúc nhiều máy **chưa bao giờ được chạy**. Mọi agent từ trước tới nay nối qua
`127.0.0.1`, và `RUNBOOK.md` mục 6 không có dòng nào được tick. Viết Phần B bằng giọng chắc chắn
như Phần A sẽ là nói dối người đọc, nên nó được đánh dấu rõ là viết theo thiết kế chứ không theo
kinh nghiệm.

Đầu file cũng có khối nêu thẳng ba giới hạn: một symbol mỗi terminal, chưa đo phiên RDP ngắt,
không có cảnh báo gửi ra ngoài.

**Hình ảnh:** hai sơ đồ SVG tự vẽ (kiến trúc, so sánh hai cách bố trí) và **năm ảnh chụp màn hình
thật** — thanh công cụ có nút Algo Trading, Navigator, hộp thoại New Order (thấy rõ ô Comment),
tab Inputs của EA, và trang theo dõi. Chụp bằng `PrintWindow`; token trong ảnh tab Inputs **đã
được che bằng cách vẽ đè lên pixel**, không phải chỉ làm mờ.

Một ảnh **cố ý không đưa vào**: tab Common có ô "Allow Algo Trading". MT5 tự vẽ tab đó nên
`PrintWindow` bắt được một khung rỗng. Theo đúng nguyên tắc "không nhét ảnh hỏng", chỗ đó dùng một
khối cảnh báo bằng chữ — và đây chính là cái bẫy đã cắn ở lượt trước nên nó được mô tả kỹ.

Kiểm chứng: không tham chiếu ra ngoài nào (mở được khi mất mạng), không token/mật khẩu thật trong
file, sáu lệnh nhắc trong hướng dẫn đều tồn tại trong `bridge/admin.py`, và toàn bộ trang đã render
kiểm bằng trình duyệt.

### Tách hướng dẫn thành hai bản, thêm ví dụ — và một lỗi bản hướng dẫn đầu

*(2026-09-06.)*

Người dùng yêu cầu tách thành hai bản riêng để mỗi bản chi tiết hơn, và thêm ví dụ.
`docs/HUONG-DAN-SU-DUNG.html` bị thay bằng **`HUONG-DAN-CUNG-VPS.html`** (198 KB) và
**`HUONG-DAN-KHAC-VPS.html`** (204 KB). Mỗi bản đọc độc lập, phần chung cố ý lặp lại.

**Khảo sát để viết lộ ra một lỗi trong chính bản hướng dẫn vừa viết hôm nay:** nó **thiếu hẳn
bước khai báo ánh xạ symbol**. Không có dòng `symbol_map` thì `find_symbol_map` trả `None` và
**mọi lệnh Master bị bỏ qua** — ai làm đúng theo hướng dẫn sẽ cài xong rồi ngồi nhìn không có gì
xảy ra. Tệ hơn: chưa có lệnh nào tạo được dòng đó, chỉ `INSERT` tay vào SQLite.

Sửa:

- Thêm **`bridge.admin anh-xa-symbol`** — xem, khai, tắt ánh xạ. Nó **kiểm symbol có thật trên
  sàn Client** trước khi lưu (đọc `symbol_spec` do EA đẩy lên) và liệt kê các symbol đang có nếu
  gõ sai, vì sai tên symbol là lỗi không hiện ra cho tới lúc có lệnh thật đi qua.
- Nâng `NO_SYMBOL_MAPPING` từ WARNING lên **ERROR** — cùng hậu quả với `VOLUME_BELOW_MIN` và
  `UI_OPEN_BUSY` (không copy được lệnh nào) nên phải cùng mức, theo đúng nguyên tắc B-08.

**Mục ví dụ** (yêu cầu của người dùng): chín tình huống cho bản một VPS, mười cho bản hai VPS.
Mỗi ví dụ là một thẻ *Cấu hình / Bạn làm / Hệ thống làm gì / Kết quả / Bạn thấy gì*. **Mọi con số
là số đo thật** — 0,6 giây mở lệnh, 272 ms đóng hẳn, 285 ms đóng một phần, 1,1 giây cho đóng khẩn
cấp hai cặp. Bốn ví dụ là các trường hợp **hỏng**: hệ số làm volume dưới mức tối thiểu, quên bật
Algo Trading, quên khai ánh xạ, hai lệnh quá gần nhau.

Bản hai VPS có thêm cảnh báo đầu file (cách bố trí này chưa từng được chạy), sơ đồ hai máy, đánh
dấu `[MÁY A]`/`[MÁY B]` ở từng bước, và ví dụ thứ mười về mất kết nối Tailscale.

Hai file sinh từ một script dùng chung (để trong scratchpad, không commit) nên phần chung giống
nhau theo cấu trúc chứ không phải chép tay. Ảnh: hai sơ đồ SVG và năm ảnh chụp thật, token trong
ảnh đã che bằng cách vẽ đè lên pixel.

**527 test xanh (+4), `ruff` sạch.**

### Đổi đường ĐÓNG sang giao diện — lập kế hoạch và dựng dụng cụ đo

*(2026-09-10.)*

**Yêu cầu mới của người chủ dự án:** deal **đóng** phía Client phải mang `DEAL_REASON = CLIENT`
chứ không phải `EXPERT` — "placed by manual" thay vì "placed by expert".

Đây đúng là rủi ro treo số 3 ghi ở mục "Phase 6b — lập kế hoạch và rà soát": *"Nếu sau này phát
hiện bên kiểm tra nhìn cả deal đóng thì phạm vi phải mở rộng đáng kể."* Nó đã xảy ra.

**Ba điều đã chốt với người chủ dự án:**

| | |
|---|---|
| Đóng hẳn và đóng một phần | **Cả hai** đều qua giao diện |
| Clicker hỏng mà cần đóng | **Rơi về EA + alert CRITICAL** — ngoại lệ có ý thức với D-25 |
| Phía Master | **Giữ `OrderSend`** — chỉ tài khoản Client bị soi |

Lý do ngoại lệ với D-25 đáng ghi lại, vì nó ngược với phase 6b: không **mở** được thì an toàn, còn
không **đóng** được thì không — Master đã đóng mà Client còn đứng vị thế trần là phơi nhiễm tiền
thật. Sẽ thành hai khoá cấu hình cạnh nhau với hai mặc định ngược nhau: `ui_degraded_fallback`
mặc định `SKIP`, `close_degraded_fallback` mặc định `EA`.

**Chưa viết một dòng code sản phẩm nào,** và có lý do. Phase 6b chạy được nhờ phép đo E1: hộp
thoại New Order là `#32770` với 53 control Win32 thật, nên `PostMessage` là đủ và không cần desktop
tương tác. Đường **đóng** không có sự thật tương đương:

- Để đóng đúng một `position_id` phải chạm tới danh sách vị thế ở tab Trade.
- Danh sách đó nhiều khả năng do MT5 **tự vẽ**. Nếu vậy từng dòng không có HWND, không đọc được
  text, không nhắm được bằng `PostMessage`.
- Không có ID lệnh menu nào cho "Close position" từng được đo; cả dự án mới biết `32848`.
- Rà lại toàn bộ `clicker/`: **không một dòng nào** chạm tới Toolbox, tab Trade, danh sách vị thế
  hay menu chuột phải. Không có `SysListView`, `LVM_`, `WM_RBUTTON`, `SysTabControl`.

Nếu dòng không có HWND thì đường còn lại là bấm theo toạ độ pixel — đúng thứ D-26 đã loại khi bàn
về One Click Trading, và tệ hơn là nó có thể phá luôn tính chất sống-qua-RDP mà cách vận hành VPS
dựa vào (B-08, TEST-19). Nên bước đầu là **khảo sát có cổng go/no-go**, đúng cách phase 6b làm.

**Lượt này dựng dụng cụ đo, không đo.** `clicker/ui/dump.py` được nới từ bản in phẳng thành công cụ
trả lời được bốn câu hỏi C1–C4:

- cây control **lồng nhau** kèm `GetWindowRect` — cần để biết có phải bấm theo toạ độ không;
- `--menu` đọc `GetMenu`/`GetSubMenu`/`GetMenuItemID`/`GetMenuStringW`, cho ID lệnh;
- `--listview` thử `LVM_GETITEMCOUNT` và `LVM_GETITEMTEXTW`.

**Một phép đo phụ đã lộ ra ngay khi hun khói trên Windows 11:** control **không phải** ListView
vẫn trả `0` cho `LVM_GETITEMCOUNT` chứ không báo lỗi. Nên `0` một mình nó **mơ hồ** — hoặc danh
sách rỗng, hoặc không phải danh sách. Bản đầu của `listview_item_count()` viết docstring nói `None`
nghĩa là "không phải ListView", và điều đó **sai**. Đã sửa cả docstring lẫn cách công cụ kết luận:
`0` cộng class sai thì in cảnh báo và trả mã thoát khác 0, để không ai đọc nhầm một phép đo âm
thành phép đo dương.

Ranh giới an toàn của `dump.py` được giữ và được **kiểm bằng test soi mã nguồn**, không bằng lời
hứa trong docstring: không `post_click`, `post_command`, `post_close`, `set_text`, `type_text`.
`--listview` có cấp phát một vùng nhớ tạm trong tiến trình MT5 vì `LVM_GETITEMTEXTW` đòi hỏi vậy;
vùng đó do chính ta cấp phát và giải phóng ngay.

`dump.py` trước đây không có test nào và không được nhắc ở đâu ngoài docstring của chính nó. Nay có
25 test và một mục riêng trong `RUNBOOK.md` (mục 5a) — vì nó là công cụ để đối phó khi đổi sàn, mà
đúng lúc cần thì không ai đi đọc docstring.

**567 test xanh (+25), `ruff` sạch.**

**Việc tiếp theo cần người, không cần code:** chạy bốn phép đo C1–C4 trên terminal Client thật có
sẵn vị thế đang mở, rồi ghi kết quả vào đây **dù đi tiếp hay dừng**. Cổng quyết định: dòng vị thế
không có HWND → dừng và bàn lại, vì lựa chọn còn lại đánh đổi đúng thứ không được phép đánh đổi
âm thầm.

### Bước 0 — bốn phép đo, và một phép đo thứ năm không có trong kế hoạch

*(2026-09-10, tài khoản Client 538217, Connext-Demo, MT5 build 5.00, hai vị thế đang mở.)*

Đo trên **máy hiện tại** chứ không phải VPS: VPS thuộc giai đoạn 2 và chưa dựng, hai bản MT5 đã
nằm sẵn ở đây, và `EnumWindows` chỉ thấy cửa sổ trong phiên của chính tiến trình gọi nó — đo từ xa
là việc không làm được, không phải chuyện bất tiện.

| | Câu hỏi | Kết quả |
|---|---|---|
| **C1** | Tab Trade có control Win32 thật không? | **XANH.** `SysListView32` thật, ctrlID `10328`, header `SysHeader32` 10 cột |
| **C2** | Từng dòng vị thế có đọc được không? | **Nửa xanh nửa đỏ** — xem dưới |
| **C3** | Hộp thoại đóng có hình dạng gì? | **XANH.** Chính là hộp thoại New Order, cùng lớp `#32770` |
| **C4** | Có ID lệnh menu để mở hộp thoại đóng không? | **ĐỎ.** Toàn bộ cây menu đọc được, và **không có mục "Close position"** ở đâu cả. `Tools` chỉ có `32848 New Order` |

**C2 nói chính xác là gì.** Địa chỉ hoá một dòng thì được, đọc dòng đó là vị thế nào thì không:

| Phép đo | Kết quả |
|---|---|
| `LVM_GETITEMCOUNT` | 2 — đúng số vị thế |
| `LVM_GETITEMRECT` | `(0,31,1867,61)` và `(0,61,1867,91)` — chính xác, cao đúng 30px |
| `LVM_SETITEMSTATE` | chạy, chọn được dòng theo chỉ số, `LVM_GETNEXTITEM` xác nhận |
| **`LVM_GETITEMTEXT`** | **chép 0 ký tự** |

MT5 tự vẽ nội dung và không giữ chuỗi trong control. Cùng kiểu ấy ở combo chọn vị thế (`10672`):
`CB_GETLBTEXT` trả về `36` — đúng độ dài chuỗi — nhưng **không ghi một byte nào** vào vùng đệm.

Điều này **đã được loại trừ khả năng là lỗi của bên đọc** trước khi ghi thành kết luận, vì một phép
đo âm do chính mình gây ra là thứ đắt nhất trong cả bộ: ghi dấu vân tay `\xEE` vào vùng đệm rồi đọc
lại thấy nguyên vẹn, `WriteProcessMemory` OK, struct đọc ngược đúng con trỏ và `cchTextMax`,
`sizeof(LVITEMW) = 88` chuẩn x64, và Market Watch — nơi chắc chắn có chữ — cũng trả rỗng y hệt.

**Cái cứu cả hướng đi nằm ở C3.** Hộp thoại đóng cho đọc ngược ticket bằng **ba đường độc lập**:

```
tiêu đề cửa sổ : 'Position: #72205853 buy 0.01 BTCUSD.s 78500.01'
nút 10410      : 'Close #72205853 buy 0.01 BTCUSD.s 78500.01 by Market'
combo 10672    : '#72205853 buy 0.01 BTCUSD.s 78500.01'   (WM_GETTEXT, không phải CB_GETLBTEXT)
```

Nên việc không đọc được danh sách **không còn là chặn**: nó biến từ một phép đoán thành một phép
**tìm có kiểm chứng** — mở dòng N, đọc ngược ticket, sai thì ESC rồi thử dòng khác, đúng mới điền
volume và bấm. Số dòng biết trước nên phép tìm có chặn trên, và mở/huỷ hộp thoại **không đặt lệnh
nào**, nên ranh giới D-24 giữ nguyên: mọi thứ sai đều sai *trước* cú bấm.

Ô volume của hộp thoại đóng là **cùng ctrlID `10333`** với hộp thoại mở, nên bài học `WM_CHAR`
(`win32.type_text`) áp nguyên vẹn, không phải học lại.

**C5 — phép đo không có trong kế hoạch, và nó suýt cho kết luận sai.** Câu hỏi: `PostMessage` mở
được hộp thoại đóng không.

- Bốn message `WM_LBUTTONDOWN/UP/DBLCLK/UP` bằng **`PostMessage`** → **không mở được**, cả hai dòng,
  chờ 5 giây.
- Nhưng `PostMessage` một cú bấm đơn **có đổi selection** từ 0 sang 1 → message tới nơi, `lParam`
  được dùng thật, MT5 **không** đọc vị trí con trỏ thật.
- `WM_LBUTTONDBLCLK` bằng **`SendMessage`** (`SendMessageTimeoutW`, đã có sẵn) → **mở được** hộp
  thoại đúng vị thế.

Nếu dừng ở phép thử đầu thì kết luận sẽ là "PostMessage không điều khiển được tab Trade", và nó
**sai**. Cả cơ chế vẫn là message gửi thẳng tới window proc, không phải `SendInput` bơm vào hàng đợi
bàn phím của phiên tương tác — tức là tính chất sống-qua-RDP **có cơ sở**, nhưng vẫn **chưa được
chứng minh** và chỉ VPS mới chứng minh được (B-08, TEST-19, giai đoạn 2).

**Một lỗi tiềm ẩn CÓ SẴN, phát hiện nhờ C3, độc lập với việc đổi đường đóng.**

`SIGNATURE` ở `clicker/ui/dialog.py:37` là `(10333, 1001, 10408, 10409)`. Hộp thoại đóng có
**đủ cả bốn**, đều đang hiện. Nên `NewOrderDialog._find()` **không phân biệt được hai hộp thoại**,
mà `open()` (dòng 83-86) lại "dùng lại cái đang mở sẵn". Người vận hành lỡ để một hộp thoại đóng mở
trên terminal thì lệnh `OPEN_UI` kế tiếp sẽ bám vào đúng hộp thoại đó. Chưa xảy ra vì clicker chưa
bao giờ mở hộp thoại đóng — nhưng con người thì có.

Thứ phân biệt được: control **`10410` đang hiện** mang chữ bắt đầu bằng `"Close #"`, hoặc tiêu đề
bắt đầu bằng `"Position: #"`. Lưu ý `10410` cũng có **bản ẩn** mang chữ `'Close'` trần — đúng cái
bẫy bản-ẩn đã biết với `10408`/`10409`.

**Cổng quyết định: XANH, đi tiếp.** Điều kiện treo lại: tính chất sống-qua-RDP phải được đo trên VPS
ở giai đoạn 2 **trước khi** chạy tài khoản thật, không phải sau.

Trả máy sạch: không còn hộp thoại nào mở, vẫn đúng 2 vị thế, `Balance` không đổi. Không có lệnh nào
được đặt trong toàn bộ quá trình đo — mọi phép đo đều dừng trước `10410`/`10408`/`10409`.

### Phase 11 — đường ĐÓNG phía Client chuyển sang giao diện

*(2026-09-10. Code xong, test xong; **chưa chạy thật trên demo**.)*

Cổng go/no-go của Bước 0 xanh (xem mục trên), nên thực hiện. Chi tiết thiết kế ở
`plan/11-dong-qua-giao-dien.md`; mục này ghi những gì đáng nhớ khi làm.

**Phía clicker.** `dialog.py` tách hai chế độ của cùng một hộp thoại; `tradetab.py` mới cho danh
sách vị thế; `driver.py` thêm `close()` là một **phép tìm có kiểm chứng** chứ không phải một cú
bấm. `link.py` nhận thêm hai loại command, và vẫn từ chối `OPEN`/`CLOSE` trần.

**Phía Bridge.** Migration `004`, `close_route` theo từng Client (mặc định `EA`), bộ tương quan
đóng, `client_close_reason`, và `kiem-reason` soi cả hai cột.

**Bốn thứ suýt sai, ghi lại vì cả bốn đều thuộc loại "vẫn chạy nên không ai thấy":**

1. **`WM_LBUTTONDBLCLK` một mình mở được dòng 0 nhưng không mở được dòng 1.** Dòng 0 tình cờ đã
   nhận một cú bấm đơn ở phép đo trước nên có sẵn trạng thái mà message ấy cần. Bản thiếu vẫn chạy
   trên **dòng đầu tiên** — đúng trường hợp người ta thử tay. Phải gửi đủ `DOWN` + `UP` + `DBLCLK`.

2. **Một file nháp tên `select.py` trong thư mục scratchpad che mất module `select` của thư viện
   chuẩn**, nên nó tự chạy mỗi lần import và tự bấm vào danh sách trước khi script thật chạy. Ba
   phép đo đã bị nhiễu trước khi phát hiện. Kết luận không đổi sau khi đo lại sạch, nhưng nếu nó
   đổi thì cái sai đã đi thẳng vào thiết kế.

3. **Quét hết danh sách mà không thấy vị thế trả `rejected`.** Nghĩa là mỗi lần vị thế đã đóng sẵn
   sẽ làm cặp thành `ORPHANED` kèm alert CRITICAL — báo động cho đúng thứ đáng lẽ phải xảy ra. Đã
   đổi thành `already_closed`, khớp đúng ngữ nghĩa EA trả khi `PositionSelectByTicket` thất bại.

4. **`_gui_lenh_dong` ban đầu rơi về EA kèm alert CRITICAL cho *mọi* Client chưa có clicker.** 27
   test của phase 7 vẫn xanh — chúng chỉ kiểm lệnh `CLOSE` được gửi — nhưng một Client cấu hình
   đường EA sẽ ăn một alert CRITICAL mỗi lần đóng lệnh bình thường. Đó là lý do `close_route` tồn
   tại thay vì suy ra từ việc có clicker hay không.

**Một lỗ hổng CÓ SẴN được bịt luôn, độc lập với phase này.** Hộp thoại đóng mang **đủ cả bốn**
control trong `SIGNATURE` của hộp thoại New Order, nên `NewOrderDialog._find()` không phân biệt
được hai chế độ — mà `open()` lại có nhánh "dùng lại cái đang mở sẵn". Người vận hành lỡ để một
hộp thoại đóng mở trên terminal thì lệnh `OPEN_UI` kế tiếp sẽ bám vào đúng nó. Đã bịt bằng
`la_che_do_dong()`, và **kiểm trên terminal thật**: với hộp thoại đóng đang mở,
`NewOrderDialog._find()` trả `None`.

**Không sửa một dòng EA nào.** `DoClose`/`DoClosePartial`/`ClosePartOf` nguyên vẹn cho đường Master
và cho cú rơi về EA. Test hợp đồng `test_ea_protocol_contract.py` vẫn xanh.

**638 test xanh (+71), `ruff` sạch.** Trong đó `tests/test_ui_close_flow.py` (18) và
`tests/test_ui_close.py` (41) là mới; test quan trọng nhất là
`test_lenh_dong_cua_bot_KHONG_kich_hoat_cascade`.

**Còn nợ, và không được quên:**

1. **TEST-26/27/28 chưa chạy trên demo.** Test tự động chứng minh logic đúng; chỉ deal thật mới
   chứng minh `reason = 0`. Bài học `driver.py` mục đầu áp nguyên: đọc lại chữ trong ô không
   chứng minh được gì.
2. **Đóng một phần chưa đo được** — vị thế demo hiện tại là 0.01, đúng mức tối thiểu của sàn, nên
   không đóng một phần được. Cần một vị thế lớn hơn.
3. **Tính chất sống-qua-RDP của cú double-click chưa được chứng minh.** Cơ chế là message gửi thẳng
   tới window proc chứ không phải `SendInput`, nên có cơ sở — nhưng chỉ VPS mới trả lời được
   (B-08, TEST-19, giai đoạn 2). Phải đo **trước** khi chạy tài khoản thật, không phải sau.
4. **Con số trong hai file hướng dẫn HTML** (272 ms đóng hẳn, 285 ms đóng một phần) là số đo của
   đường EA và sẽ sai sau thay đổi này. Đo lại rồi thay, đừng để số cũ.
5. **Clicker nay là điểm nghẽn của cả hai đường.** Mở và đóng dùng chung một tiến trình xử lý một
   lệnh tại một thời điểm. Đóng khẩn cấp nhiều cặp sẽ chậm hơn 1.101 ms đo ở TEST-21 — phải đo lại.
6. **Tab Trade phải là tab đang mở** thì clicker mới thấy danh sách vị thế. Bridge từ chối ồn ào
   chứ không đoán, nhưng đây là một giới hạn vận hành mới, cùng loại với B-01 (một symbol mỗi
   terminal).

### Rà lại phase 11 — ba lỗ hổng tìm được sau khi test đã xanh

*(2026-09-10, cùng ngày. Cả ba đều lọt qua 634 test và chỉ lộ ra khi đọc lại **đường đi của các
trạng thái lỗi** thay vì đường đi của trường hợp thành công.)*

**1. `already_closed` kết luận từ một phép đo không đủ tư cách kết luận.** `close()` quét hết danh
sách rồi trả `already_closed`. Nhưng nếu một hộp thoại mở **chậm hơn** thời gian chờ, MT5 vào vòng
lặp modal và **mọi dòng sau đó không dò được** — cũng cho ra "quét hết, không thấy". Bridge khi đó
ghi cặp thành `CLOSED` trong khi vị thế vẫn đang mở và vẫn đang lỗ.

Sửa: `already_closed` chỉ được trả khi **ít nhất một dòng đã mở được hộp thoại** trong lượt đó —
tức là có bằng chứng cơ chế dò đang chạy. Không dòng nào mở được thì trả `rejected`, vốn chứng
minh được là chưa bấm gì nên Bridge còn đường rơi về EA. Và huỷ hộp thoại sót lại **trước mỗi
dòng**, không chỉ một lần lúc bắt đầu.

**2. Bộ tương quan đóng bỏ sót đúng ca hay xảy ra nhất.** Truy vấn chỉ xét `PENDING`/`SENT`/
`ACK_OK`. Nhưng clicker bấm xong rồi chết trước khi báo về sẽ trả ack `unknown`, và
`server._handle_ack` biến nó thành **`TIMEOUT`** — trong khi lệnh **đã thực sự khớp**. Event đóng
vừa về sẽ bị hiểu là người dùng đóng tay, và với `can_close_master = 1` nó **cascade đóng vị thế
Master**. Đúng thứ bộ tương quan tồn tại để ngăn, hỏng ở đúng tình huống nó cần nhất.

Sửa: xét mọi trạng thái, chặn bằng thời gian (`COALESCE(acked_at, updated_at) >= mốc`).

**3. `rejected` từ clicker làm cặp `ORPHANED` trong khi vị thế vẫn mở.** `close_degraded_fallback
= EA` chỉ lo ca clicker **chết**. Ca clicker **sống mà từ chối** — tab Trade không mở, đọc lại
lệch, không dò được dòng nào — thì trước đó không ai lo, và nó là nguyên nhân hay gặp nhất.

Sửa: `rejected` trên đường UI thì thử lại bằng `OrderSend` của EA kèm CRITICAL. Đây **đúng tinh
thần D-24** chứ không phải nới lỏng nó: `rejected` là trạng thái duy nhất được retry, và ở đây
"retry" nghĩa là đổi kênh chứ không phải bấm lại đúng chỗ vừa từ chối. Không có nguy cơ lặp vì
lệnh đi ra là `CLOSE`/`CLOSE_PARTIAL`, không thuộc `LOAI_DONG_QUA_UI`.

**Điểm chung của cả ba:** test cũ kiểm *chuyện đúng xảy ra đúng*, không kiểm *chuyện sai xảy ra ra
sao*. Đã thêm 4 test cho đúng ba đường này.

**Một thứ CỐ Ý không làm:** không nối `dry_probe()` vào canary như kế hoạch ban đầu. Canary chạy
mỗi giây, mà `dry_probe` mở rồi đóng hộp thoại thật. Và không đưa "tab Trade có đang mở không" vào
canary chung: tab Trade đóng **không** ảnh hưởng đường mở, nên để nó làm canary đỏ sẽ dừng copy vì
một lý do không liên quan. Thay vào đó, tab Trade đóng nay thất bại **ồn ào và đúng chỗ** — clicker
trả `rejected` với thông báo rõ, rồi rơi về EA (sửa số 3).

**Lỗ thứ tư, nằm trong chính quy trình cập nhật chứ không nằm trong code.** Bản đầu của
`RUNBOOK.md` mục 5c bảo dùng `bridge.admin sao-luu` để sao lưu trước khi nâng cấp. Nhưng **mọi**
lệnh `bridge.admin` đều mở database qua `Database(...)`, mà hàm đó mặc định `migrate=True` — nên nó
chạy migration **trước**, rồi mới sao lưu bản đã migrate. Bản sao lưu ấy không quay lại được, và
điều đó chỉ lộ ra vào đúng lúc cần tới nó.

Sửa: bước sao lưu trước migration dùng `sqlite3` trần với `VACUUM INTO`, không đi qua `Database`.
`bridge.admin sao-luu` vẫn đúng cho sao lưu thường ngày — chỉ không dùng được ở đúng thời điểm cần
giữ trạng thái *trước* khi schema đổi.

### Nghiệm thu TEST-26/27/28 trên demo — và ba lỗi chỉ terminal thật mới lộ ra

*(2026-09-10, tài khoản 538216 Master / 538217 Client, Connext-Demo, `BTCUSD.s`.)*

Trước phiên này, **nút `Close #…` chưa từng được bấm một lần nào**. Mọi phép đo đều dừng lại trước
cú bấm, nên toàn bộ `_commit_close` mới chỉ chạy với hộp thoại giả.

Bố trí có chủ ý: giữ nguyên một vị thế **người dùng mở tay** (`72205853`) trong tab Trade suốt cả
phiên. Nhờ vậy vị thế cần đóng không bao giờ nằm ở dòng 0, và nếu cơ chế đối chiếu ticket sai thì
thứ bị đóng nhầm sẽ là lệnh của chính người dùng. Không có cách dựng lại tình huống ấy trung thực
hơn.

| Bài | Kết quả |
|---|---|
| **TEST-26** | Đóng hẳn qua giao diện: `client_close_reason = 0`, cặp đối chứng cùng symbol **không bị đụng**, lệnh tay `72205853` **còn nguyên**, không alert nào |
| **TEST-27** | Đóng một phần: clicker gõ `0.01` vào ô volume của hộp thoại đóng, MT5 đóng **đúng `0.01`**, `reason = 0` |
| **TEST-28** | Tắt clicker rồi cho Master đóng: rơi về `OrderSend`, vị thế Client **vẫn đóng được** trong 342 ms, alert CRITICAL `CLOSE_FELL_BACK_TO_EA`, `client_close_reason = 3`, **không** kèm `UI_CLOSE_REASON_MISMATCH` |

**Ẩn số lớn nhất đã được trả lời:** bài học `WM_CHAR` **có** áp cho hộp thoại đóng. Cái bẫy
`WM_SETTEXT` của phase 6b — đổi chữ hiển thị nhưng gửi đi volume của lệnh trước — **không** tái
diễn. Đây là thứ mà trước phiên này mới chỉ là suy luận theo kiểu "hai hộp thoại dùng chung ctrlID
`10333` nên chắc giống nhau".

#### Lỗi 1 — `client_current_volume` đứng yên sau mỗi lần đóng bớt

Terminal đóng **đúng** `0.01`, event của EA báo **đúng** `volume_after = 0.03`. Nhưng sổ sách vẫn
ghi `0.04`.

Nguyên nhân: `_sau_dong_bot` tính volume còn lại bằng **phép trừ** `executed_volume` từ ack — mà ack
của clicker **không có** trường đó. Clicker chỉ biết nó đã *gõ* gì, không biết sàn đã *khớp* bao
nhiêu; báo con số mình gõ như thể đó là con số đã khớp là nói điều mình không chứng minh được
(D-24). Nên phép trừ trừ đi `0`.

Hậu quả không phải hiển thị: lần đóng bớt **kế tiếp** lấy tỷ lệ trên con số sai đó. Đo được ngay
trong phiên — lần đóng bớt thứ hai tính `0.01/0.03 × 0.04 = 0.0133`, làm tròn xuống ra `0.01` nên
tình cờ vẫn đúng. Lệch to hơn một chút là đóng sai khối lượng bằng tiền thật.

Sửa: lấy `volume_after` từ event, đúng tinh thần D-14 (*"volume_after do EA báo là con số được
dùng. Không tính bằng phép trừ"*). Là con số **tuyệt đối** nên gán vào là idempotent, không phụ
thuộc thứ tự đến của ack với event. Chỉ áp cho đường giao diện; đường EA giữ nguyên phép trừ đang
chạy đúng.

**Vì sao bộ test không thấy:** `MockClicker` **báo `executed_volume`**, còn clicker thật thì không.
Mock giỏi hơn đồ thật, và cái nó che đi đúng là chỗ hỏng. Đã sửa mock cho khớp bản thật — và ngay
lập tức một test cũ chuyển sang đỏ, vì nó vốn xanh nhờ lời nói dối ấy.

#### Lỗi 2 — `kiem-reason` không bao giờ ĐẠT lại được sau một cú rơi về EA

`pair` giữ `client_close_reason = 3` vĩnh viễn, nên sau **một** lần clicker hỏng, TEST-23 báo
KHÔNG ĐẠT mãi mãi. Một tiêu chí không bao giờ đạt được là một tiêu chí không ai nhìn nữa.

Sửa: tách "sai kênh **không giải thích được**" (thất bại, thoát khác 0) với "sai kênh **đã có giải
thích**" — có `error_message = CLOSE_FELL_BACK_TO_EA` và alert CRITICAL kèm theo. Vẫn **liệt kê ra**
chứ không giấu; chỉ khác ở chỗ không tính là thất bại. Deal **MỞ** sai kênh thì không bao giờ được
giải thích, vì D-25 cấm rơi về đường EA ở đường mở.

#### Lỗi 3 — đóng khẩn cấp chờ 10 giây cố định, mà thang đo đã đổi

| Lệnh | Kênh | Độ trễ đo được |
|---|---|---|
| `CLOSE_UI` (đóng hẳn) | clicker | **5.122 ms** và **5.471 ms** |
| `CLOSE_UI_PARTIAL` | clicker | **5.929 ms** và **5.847 ms** |
| `CLOSE` (rơi về EA) | EA | **342 ms** |

Đường giao diện chậm hơn đường EA khoảng **16 lần**, và clicker xử lý **tuần tự**. Hằng số
`_cho_lenh_xong(han_sec = 10.0)` được chọn khi mọi lệnh đóng mất ~300 ms; giờ nó chỉ còn đủ cho một
tới hai cặp. Từ cặp thứ ba, đóng khẩn cấp sẽ hết hạn chờ rồi đi đóng Master **trong khi lệnh đóng
Client vẫn đang bay** — cả nhóm mất hedge theo đúng chiều D-10 tồn tại để ngăn.

Sửa: hạn co giãn theo số lệnh (`10 + 8×n`), trần 120 giây. Trần là có chủ ý — `EMERGENCY` nghĩa là
ra khỏi thị trường ngay, chạm trần thì thà lệch thứ tự còn hơn để cả hai bên nằm im.

**645 test xanh (+7).** Trả máy: `run_mode = PAUSED`, Master 0 vị thế, 0 cặp chưa đóng, token
clicker đã thu hồi và mục `[clicker]` đã xoá khỏi `config.toml`. Vị thế `72205853` của người dùng
giữ nguyên như lúc bắt đầu.

**Còn nợ:** đóng khẩn cấp nhiều cặp chưa đo lại thật (chỉ sửa hằng số và test bằng mock); hai file
hướng dẫn HTML còn số cũ của đường EA.

### TEST-29 và đo lại đóng khẩn cấp — hai lỗi nữa, cả hai chỉ lộ ra khi chạy thật

*(2026-09-11. Tiếp phiên nghiệm thu hôm trước, sau khi dọn nợ cũ: 6 sai lệch và 53 alert tồn đọng
đã xử lý, sao lưu mới.)*

#### TEST-29 — bộ tương quan đóng, **cả hai chiều**, với `can_close_master = 1`

Ba bài hôm trước đều chạy với cờ TẮT, nên đường nguy hiểm nhất chưa bao giờ sống. Lần này bật lên:

| Chiều | Kết quả |
|---|---|
| **Bot đóng** (Master đóng → bot đóng Client) | Đúng **2** lệnh cho cặp, **0** lệnh `CLOSE` tới `AG-MASTER`, **0** alert |
| **Người dùng đóng tay** vị thế Client | **1** lệnh `CLOSE` tới `AG-MASTER` `ACK_OK` 363 ms, alert `CASCADE_STARTED` |

Hai event **giống hệt nhau** từ phía EA — `caused_by_command_id = NULL` cả hai — mà Bridge phân
biệt đúng. Nó không kích hoạt thừa, cũng không nuốt mất lệnh thật.

#### Lỗi 1 — một cú bấm nút đóng khẩn cấp sinh ra **hai lượt chạy song song**

`POST /api/emergency` gọi thẳng `emergency_close_all()`, còn `check_emergency()` thấy `run_mode`
đổi sang `EMERGENCY` cũng gọi. Chốt `_emergency_done` chỉ chặn được đường thứ hai.

Hai lượt phá đúng thứ tự mà hàm ấy tồn tại để giữ: lượt A gửi lệnh đóng Client rồi chờ; lượt B
thấy mọi cặp đã có lệnh đang bay nên **không gửi gì**, danh sách chờ của nó **rỗng**,
`_cho_lenh_xong([])` trả về ngay, và nó đi đóng Master luôn.

Đo được: Master đóng xong lúc `06:21:15.7` trong khi Client mãi `06:21:28.0` mới xong — **Master
đóng trước Client 13 giây**. Trong cả khoảng ấy nhóm phơi nhiễm một chiều.

API còn trả `client: 3, master: 0` trong khi thực tế có 3 lệnh đóng Master — hai con số mâu thuẫn
chính là dấu vết của hai lượt chạy.

Lỗi **có sẵn từ trước**, nhưng chỉ lộ khi đường đóng chuyển sang giao diện: với `OrderSend` 300 ms
cửa sổ đua hẹp tới mức không thấy, với ~5 giây thì nó vỡ chắc chắn.

Sửa: khoá `asyncio.Lock` đặt trong `CloseFlow` chứ không ở endpoint — nó phải đúng bất kể ai gọi.
Đo lại sau khi sửa: Master tạo lúc `06:28:17.341`, **148 ms sau** khi Client cuối cùng ack lúc
`06:28:17.193`. Đúng thứ tự. Toàn bộ 3 cặp cả hai vế: **14,5 giây**.

#### Lỗi 2 — cửa sổ nhận cha đo từ "bây giờ" thay vì từ lúc event **tới**

Lần đo lại lộ tiếp: một cặp bị ghi `ORPHANED` kèm alert ERROR **dù đã đóng sạch cả hai phía**.

`process_pending()` xử lý event tuần tự, nên lúc một event tới có thể cách lúc nó được xử lý hàng
giây. Lấy `utc_now()` làm mốc là trộn độ trễ của **hàng đợi Bridge** vào một cửa sổ đáng lẽ chỉ đo
độ trễ **của sàn**. Và nó hỏng đúng lúc tệ nhất — đóng khẩn cấp là lúc hàng đợi dài nhất:

| Vị thế | Nhận | Xử lý | Trễ | Kết quả |
|---|---|---|---|---|
| 72530339 | 06:28:**08.092** | 06:28:17.456 | **9,4 s** | **trượt** → `ORPHANED` oan |
| 72530365 | 06:28:12.637 | 06:28:17.456 | 4,8 s | khớp — dư **0,2 giây** |
| 72530392 | 06:28:17.146 | 06:28:17.461 | 0,3 s | khớp |

Cái thứ hai chỉ dư 0,2 giây. Nới cửa sổ chỉ dời ngưỡng chứ không sửa gì.

Sửa đúng gốc: đo từ `event.received_at` — dấu thời gian do chính Bridge đóng lúc nhận, nên miễn
nhiễm với độ trễ hàng đợi. Test mới được kiểm là **đỏ trên bản cũ, xanh trên bản sửa**; một test
không phân biệt được hai bản thì không canh gác gì cả.

Với `can_close_master = 1`, cặp trượt sẽ không chỉ bị ghi `ORPHANED` mà còn **cascade đóng Master**.

#### Bộ đối chiếu tự bắt được chỗ sổ sách hỏng

Cặp bị `ORPHANED` oan được vòng đối chiếu phát hiện ngay sau đó (`ORPHAN_RESOLVED` →
`MARK_CLOSED`) và đã sửa xong. Đúng thứ phase 8 sinh ra để làm.

Hai finding khác (`MASTER_CLOSED_OFFLINE`) là ảnh chụp lúc cặp còn `CLOSING` và đã tự đóng đúng sau
đó — **bỏ qua có ghi chú** chứ không chấp nhận, vì chấp nhận sẽ gửi lệnh đóng thật để "sửa" một thứ
đã đúng.

#### Nghiệm thu tổng

`kiem-reason`: **ĐẠT 50/51** — 51 deal mở và **11 deal đóng**, tất cả `DEAL_REASON = CLIENT`, trừ
đúng một lần rơi về EA cố ý ở TEST-28 hôm trước.

**647 test xanh (+2).** Trả máy: `PAUSED`, 0 cặp chưa đóng, 0 sai lệch, 0 alert chưa xem, token
clicker thu hồi, `[clicker]` đã xoá khỏi `config.toml`. Master 0 vị thế; Client còn đúng lệnh tay
của người chủ dự án, nguyên vẹn suốt hai phiên.

**Còn nợ, không làm được ở laptop:** B-08 (phiên RDP ngắt), B-02/TEST-19 (mất điện), B-03 (24 giờ).
Và một món nhỏ: hai cặp `OPEN_FAILED` từ diễn tập 2026-09-05 làm ô "cần can thiệp" đỏ vĩnh viễn —
xem B-18.

### Rà lại lần cuối trước VPS — một lỗ ở Bridge, và hai chỗ trong script cài đặt

*(2026-09-11.)*

**Lỗ ở Bridge.** Lệnh `CLOSE_UI` trả `unknown` — clicker bấm xong nhưng hộp thoại đóng chậm hơn
hạn chờ, đã quan sát thật ở đường mở cùng ngày — để cặp **kẹt `CLOSING`** tới vòng đối chiếu kế
tiếp, kèm alert CRITICAL và một finding cần người bấm. Trong khi đó event đóng của EA **đã về và đã
được nhận cha**: Bridge đang cầm sẵn bằng chứng đóng xong mà không dùng.

Sửa theo đúng doctrine D-23 mà đường mở đã áp từ phase 6b — *"event của EA là nguồn sự thật; ack
của clicker là thông tin phụ"*: event báo vị thế hết thì đánh cặp `CLOSED`, kèm alert INFO
`CLOSE_ACK_UNKNOWN_DA_GIAI` để người vận hành không đi đối chiếu tay một thứ đã tự khép lại.
`mark_pair_closed` idempotent nên thứ tự ack/event không quan trọng. +2 test, trong đó một test
khẳng định event **còn volume** thì **không** đóng cặp.

**Script cài đặt — không có test Python nào chạm tới, nên chỉ đọc mới thấy:**

- `tro-ly.ps1` hỏi *"Tạo client (open_route = UI)?"*, nhưng `them-client` nay cho `close_route`
  theo `open_route` — người vận hành đồng ý mà **không được nói là đường ĐÓNG cũng đổi**. Sửa lời
  giải thích, câu hỏi, và truyền `--close-route UI` **tường minh** thay vì dựa vào mặc định ngầm.
- Với bản cài có sẵn, migration để Client ở `close_route = EA`, còn trợ lý bỏ qua bước client đã
  tồn tại — nên **không ai biết** đường đóng vẫn đi qua EA. Trợ lý giờ cảnh báo khi thấy
  `close_route=EA`.
- `cai-dat.ps1` in gợi ý `them-client` — thêm `--close-route UI` cho tường minh.
- `docs/CAI-DAT-VPS.md` mục 9 — bước bật `close_route` sau khi nâng cấp, điều kiện tab Trade, và
  nhắc đo lại ctrlID nếu MT5 trên VPS khác build.

**Đã kiểm, không có vấn đề:** mọi chỗ so sánh loại lệnh đóng dùng đúng hằng số; cả ba nơi gọi
`_gui_lenh_dong` xử lý `None`; 40 khoá `UI.*` trong `app.js` đều có nhãn; `close_route` hiện trên
dashboard qua `/api/config` (chạy thật); `cai-dat.ps1 -CapNhat` sao lưu **trước** `git pull` bằng
venv **cũ**, nên bản sao lưu là trước-004 — không dính lỗi sao lưu đã sửa ở RUNBOOK; không script
nào parse đầu ra `kiem-reason` hay dòng `cau-hinh-client` theo định dạng cũ.

**649 test xanh.**

### Sự cố cập nhật trên VPS — code mới trên đĩa, code cũ trong bộ nhớ, log im 63 giờ

*(2026-09-11.)*

Người vận hành chạy `tro-ly.ps1` trên VPS và nhận `[ LOI ] tinh-hinh`. Bản thân cài đặt không hỏng
— dòng đỏ chỉ là tồn đọng (1 cặp ORPHANED mà Master đã đóng, 5 sai lệch, 92 alert). Nhưng output
lộ ra ba lỗi thật, không test Python nào chạm tới được:

1. **Cập nhật bằng `cai-dat.ps1` chạy thường, không `-CapNhat`, trên bản đang chạy.** Script vẫn
   `git pull` và vẫn chạy migration `004` (qua `bridge.admin liet-ke`), nhưng bỏ qua sao lưu, không
   dừng dịch vụ, không bật lại gì. Bằng chứng: `run_mode = RUNNING` (Bridge khởi động lại thì luôn
   `PAUSED` — D-15) và clicker chạy liên tục từ 09-08. **Sửa:** `cai-dat.ps1` từ chối chạy khi dịch
   vụ Running mà thiếu `-CapNhat`; `kiem-tra.ps1` mục 4b cảnh báo khi tiến trình Bridge/clicker chạy
   từ trước lần HEAD đổi gần nhất (reflog, không phải ngày commit).
2. **`-CapNhat` cũng không nạp lại clicker** — nó là Scheduled Task, `Stop/Start-Service` không đụng
   tới. Clicker cũ sẽ từ chối `CLOSE_UI`, mọi lệnh đóng rơi về EA kèm CRITICAL: nâng cấp không có
   tác dụng mà không ai hay. Plan và tài liệu hôm trước bỏ sót. **Sửa:** `-CapNhat` dừng tiến trình
   clicker cũ trước khi bật Bridge (Bridge đang dừng nên không lệnh nào đang bay), `chay-clicker.ps1`
   tự bật lại bằng code mới, script chờ tối đa 45 giây xác nhận PID mới.
3. **Bridge và clicker cùng ghi `logs/bridge.log`.** Trên Windows lần xoay lúc nửa đêm không đổi tên
   được file đang bị tiến trình kia giữ (`WinError 32`), lần xoay hỏng không dời mốc xoay, nên mọi
   lần ghi sau đều thử và hỏng lại: **cả hai ngừng ghi log vĩnh viễn**. `bridge.log` đứng im 63 giờ.
   Laptop chưa bao giờ chạy qua nửa đêm nên chưa thấy. **Sửa:** clicker ghi `logs/clicker.log`,
   +1 test khẳng định tên file khác `bridge.log`.

Tài liệu: `CAI-DAT-VPS.md` mục 9, `RUNBOOK.md` phần log, `HUONG-DAN-CUNG-VPS-SCRIPT.html` (bảng bước
cài, bảng mục kiểm, bảng 9.2). `cai-dat.ps1` lên bản `2026-09-11`.

Việc trên VPS (người vận hành làm): chẩn đoán chỉ đọc → `cai-dat.ps1 -CapNhat` → xác nhận PID mới,
`schema_version = 4` → `cau-hinh-client CL-01 --close-route UI` → dọn tồn đọng theo evidence → đo
lại ctrlID → `RUNNING` → chạy thử demo → B-08.

#### Sau khi cập nhật: bộ test ghi vào log thật của VPS

Cập nhật chạy đúng (commit `0459350`, cả bốn tiến trình khởi động 16:08, mục 4b xanh). Nhưng
`logs/clicker.log` trên VPS có mốc giờ **16:06:50 — sớm hơn giờ clicker mới khởi động (16:08:34)**,
và nặng 509 KB, đúng bằng hai lượt ~254 KB mà bộ test sinh ra. Tức là file log "của clicker" lúc đó
chứa toàn log **của bộ test** mà `-CapNhat` chạy hai lần.

Nguyên nhân: `tests/test_clicker.py` gọi `main()` thật, `main()` gọi `setup_logging()` thật, ghi vào
`logs/` theo thư mục hiện hành — và `cai-dat.ps1` chạy bộ test ngay trong `C:\CopyBridge`. Có từ
trước (khi còn ghi chung thì nó lẫn vào `bridge.log`), chỉ lộ ra khi clicker có file riêng. Trong log
test có cả dòng CRITICAL "Thieu token" do test cố ý gây ra — người đọc log thật sẽ tưởng clicker hỏng.

**Sửa:** fixture autouse `_cach_ly_config_may` trong `tests/conftest.py` chặn luôn
`clicker.__main__.setup_logging`. Kiểm: `clicker.log` 254485 byte / 15:17:42.157 trước và sau một
lượt `pytest` đầy đủ — không đổi. Test khẳng định tên file log riêng vẫn đè được lên patch này.

#### Tồn đọng trên VPS đọc được gì, và `bridge.admin xac-nhan-alert`

Đọc chỉ-đọc DB của VPS (không mở bảng `agent`). **5 sai lệch**, đều từ đợt thử 2026-09-08:

| # | Loại | Kết luận |
|---|---|---|
| 1 | SAFE `BOTH_CLOSED` cặp 000004 | Hai chân đều trống lúc đó — chấp nhận chỉ ghi sổ `CLOSED` |
| 2 | DECISION `UNPAIRED_MASTER` AUDCHF | Lệnh không có ánh xạ symbol, `ALERT_ONLY` |
| 3 | SAFE `ACK_LOST` → `REBIND_BY_TAG` cặp 000013 | **KHÔNG được chấp nhận**: ghép cặp vào vị thế Client 71789826, mà snapshot hôm nay Client có 0 vị thế |
| 4 | DECISION `UNPAIRED_CLIENT` 71789826 | Vị thế đó không còn |
| 5 | SAFE `ORPHAN_RESOLVED` cặp 000015 | Master `CLOSED`, Client volume 0 — chấp nhận |

Chống trùng ở `_create_finding` chỉ xét finding **đang chờ**, nên bỏ qua một finding cũ không làm
mất gì: nếu sai lệch vẫn còn, vòng đối chiếu kế tiếp sinh finding mới theo tình trạng **hiện tại**.
Vòng 16:20 báo "0 sai lệch mới" dù cặp 000013 lẽ ra phải sinh `BOTH_CLOSED` hoặc `CLIENT_NOT_OPENED`
— tức nhiều khả năng cặp đó đã rời `PENDING_OPEN`; cần xác nhận trên VPS trước khi xử lý.

**240 alert chưa xem**, 207 là hai mã lặp (`RECONCILE_NO_SNAPSHOT` 138 — Master không gửi
snapshot suốt 2 giờ ngày 09-08; `FINDING_BO_QUEN` 69). Không alert nào báo chuyện đang xảy ra.
Dashboard chỉ xác nhận từng cái — 240 lần bấm thì không ai bấm, và ô đỏ vĩnh viễn làm alert thật
kế tiếp chìm luôn. Thêm `bridge.admin xac-nhan-alert` với ba chốt: `--code` bắt buộc (không có "tất
cả"), `--truoc` bắt buộc **có múi giờ** (alert sinh sau lúc đọc không bị nuốt, không đoán giờ địa
phương hay UTC), và mặc định chỉ đếm — phải `--that` mới ghi. Không đụng `reconcile_finding`. +5 test,
trong đó một test kiểm quy đổi `16:30+07:00` = `09:30Z` với alert cách mốc 1 ms ở hai phía.

RUNBOOK: sửa câu sai về `service-err.log` — nó là **toàn bộ output console** của Bridge (vì vậy 7,6
MB), không phải chỉ lỗi.

**655 test xanh.**

#### Finding cũ mở lại được một cặp đã đóng

Sau khi dọn trên dashboard, lệnh đếm `xac-nhan-alert` lúc 17:41 hiện một `RECONCILE_FINDINGS`
**mới** (17:41:01) — vòng đối chiếu vừa sinh finding, trong khi nếu dọn đúng thì không còn gì để sinh.
Giả thuyết mạnh nhất: finding #3 `ACK_LOST → REBIND_BY_TAG` đã bị chấp nhận (bấm nhầm, hoặc qua nút
"Chấp nhận tất cả mục an toàn"). Chưa xác nhận trên VPS lúc viết mục này.

Dù thao tác là gì, đọc code thấy đây là **lỗi thật**:

- `accept_finding` làm theo `suggested_action` **mà không so tình trạng hiện tại** với lúc finding
  được tạo. Finding là ảnh chụp; cái #3 chụp lúc cặp 000013 còn `PENDING_OPEN`, 17 giây sau cặp tự
  đóng theo đường thường, và ảnh chụp nằm chờ ba ngày.
- `mark_pair_open` ghi `status = 'OPEN'` không điều kiện, nên chấp nhận nó ghi cặp `CLOSED` thành
  `OPEN` gắn vào vị thế không còn tồn tại.
- Cùng lỗ đó với `MASTER_CLOSED_OFFLINE → CLOSE_CLIENT` là **gửi lệnh đóng thật** theo ảnh chụp cũ.
  Lần này không có tiền nào bị đụng chỉ vì hai terminal đều 0 vị thế.
- Dashboard **bỏ qua kết quả** của nút Chấp nhận: kể cả khi Bridge từ chối, người bấm không thấy gì.

**Sửa:** `accept_finding` so `evidence_json.db.status` với trạng thái hiện tại của cặp; khác thì
không làm gì, **không** đổi `resolution` (người vận hành vẫn phải Bỏ qua kèm ghi chú), log WARNING, trả
`False`. Finding không gắn cặp hoặc bằng chứng thiếu `db.status` giữ hành vi cũ. `accept_all_safe` tự
bỏ qua finding cũ vì chỉ đếm lần trả `True`. `app.js` đọc `ok` và báo bằng nhãn mới `accept_refused`.

+3 test — cả ba **đỏ trên code cũ** trước khi sửa: `REBIND_BY_TAG` trên cặp đã đóng (cặp phải vẫn
`CLOSED`, finding vẫn `PENDING`), `CLOSE_CLIENT` trên cặp đã đóng (không command đóng nào được tạo),
và `accept_all_safe` với một finding cũ lẫn một finding còn đúng (đúng 1 được áp dụng). `app.js` kiểm
cú pháp bằng `node --check`; chưa bấm thử trên trình duyệt.

**658 test xanh.**
