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
