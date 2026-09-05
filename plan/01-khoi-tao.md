# Phase 1 — Khởi tạo dự án

## Mục tiêu

Dựng khung thư mục, môi trường, công cụ và bộ tài liệu nền. Kết thúc phase này chưa có
chức năng nghiệp vụ nào, nhưng mọi phase sau đều dựa vào cấu trúc dựng ở đây.

## Điều kiện đầu vào

Thư mục trống. Đã đọc `plan/00-README.md`.

---

## Việc cần làm

### 1.1 Cấu trúc thư mục

```
mt5-copy-bridge/
├── bridge/
│   ├── __init__.py
│   ├── config.py            đọc cấu hình từ file + DB
│   ├── db/                  phase 2
│   ├── protocol/            phase 3
│   ├── engine/              phase 6, 7, 8
│   ├── web/                 phase 9
│   └── labels_vi.py         bảng nhãn tiếng Việt (D-16)
├── ea/
│   ├── CopyBridgeCommon.mqh phase 4
│   ├── CopyBridgeMaster.mq5 phase 4
│   └── CopyBridgeClient.mq5 phase 5
├── tests/
│   ├── conftest.py
│   └── mock_agent.py        phase 3
├── data/                    SQLite, archive. Trong .gitignore
├── logs/                    Trong .gitignore
├── plan/                    bộ file này
├── docs/
├── pyproject.toml
├── .gitignore
├── README.md
└── PROGRESS.md
```

### 1.2 Môi trường

- Tạo virtualenv, cài `pydantic`, `fastapi`, `uvicorn`, `pytest`, `pytest-asyncio`, `ruff`.
- `pyproject.toml`: cấu hình ruff (line-length 110), pytest (`asyncio_mode = "auto"`), metadata dự án.
- `.gitignore`: `data/`, `logs/`, `.venv/`, `__pycache__/`, `*.ex5`, `*.db`, `*.db-wal`, `*.db-shm`.
- `git init` và commit đầu tiên.

### 1.3 Logging

Viết `bridge/logging_setup.py`:

- Bốn mức theo đặc tả: INFO, WARNING, ERROR, CRITICAL.
- Ghi đồng thời ra console và file xoay vòng trong `logs/`.
- Định dạng có timestamp ISO 8601 kèm mili giây, tên module, mức, nội dung.
- Mọi log liên quan tới một cặp lệnh phải mang `pair_id`; liên quan tới một sự kiện phải mang `event_id`.
  Dùng `extra={}` và một formatter tự động chèn các trường này khi có.
- **Không log token, không log mật khẩu.**

### 1.4 Tài liệu nền

Tạo các file sau trong `docs/` (trừ `PROGRESS.md` và `README.md` ở gốc).

**`README.md`** — tổng quan ngắn: hệ thống làm gì, cách chạy, cách chạy test. Dưới 60 dòng.

**`docs/ARCHITECTURE.md`** — chép lại mục 1, 2, 3 của `plan/00-README.md`, có thể mở rộng thêm.
Vẽ sơ đồ luồng bằng ASCII. Ghi rõ các vai trò và ranh giới trách nhiệm.

**`docs/DECISIONS.md`** — chép **nguyên văn** bảng 20 quyết định D-01…D-20 ở mục 4 của
`plan/00-README.md`. Mỗi quyết định thêm một dòng "Lý do" ngắn nếu suy ra được từ ngữ cảnh.
File này là hợp đồng: khi lập trình mà thấy mâu thuẫn, quay lại đây trước.

**`docs/GLOSSARY.md`** — chép mục 5 của `plan/00-README.md`, bổ sung dần khi gặp thuật ngữ mới.

**`docs/CONVENTIONS.md`** — quy ước code:
- Tiếng Anh cho tên biến, hàm, enum, log, message giao thức.
- Tiếng Việt chỉ xuất hiện trong `bridge/labels_vi.py` và các template giao diện.
- Đặt tên: `snake_case` cho Python, `PascalCase` cho lớp, `UPPER_SNAKE` cho hằng và enum.
- Mọi hàm chạm vào tiền (tính volume, gửi lệnh) phải có docstring nêu rõ đơn vị và điều kiện biên.
- Không dùng `float` cho so sánh volume. Luôn so sánh với epsilon hoặc dùng số nguyên đơn vị bước.

**`PROGRESS.md`** — nhật ký tiến độ. Khởi tạo với khung sau:

```markdown
# Tiến độ

## Trạng thái các phase
| Phase | Tên | Trạng thái | Ngày |
|---|---|---|---|
| 1 | Khởi tạo | chưa bắt đầu | |
| 2 | Database | chưa bắt đầu | |
... (đủ 10 dòng)

## Nhật ký
### Phase 1
- Đã làm:
- Lệch so với plan:
- Vấn đề còn treo:
- Phát hiện sớm (ghi lại, không xử lý ở phase này):
```

### 1.5 File nhãn tiếng Việt

Tạo `bridge/labels_vi.py` với một dict duy nhất ánh xạ enum sang nhãn hiển thị.
Đây là **nơi duy nhất** trong toàn dự án được chứa chuỗi tiếng Việt hướng tới người dùng.

```python
PAIR_STATUS = {
    "PENDING_OPEN": "Chờ mở",
    "OPEN": "Đang hedge",
    "PARTIALLY_CLOSED": "Đóng một phần",
    "CLOSING": "Đang đóng",
    "CLOSED": "Đã đóng",
    "OPEN_FAILED": "Mở thất bại",
    "ORPHANED": "Mất hedge",
}
RUN_MODE = {
    "RUNNING": "Đang chạy",
    "PAUSE_NEW_ENTRIES": "Tạm dừng lệnh mới",
    "PAUSED": "Đã dừng",
    "EMERGENCY": "Khẩn cấp",
}
AGENT_STATUS = {"ONLINE": "Kết nối", "OFFLINE": "Mất kết nối", "DEGRADED": "Mất kết nối sàn"}
COPY_MODE = {"SAME": "Cùng chiều", "OPPOSITE": "Khác chiều"}
CLOSE_SOURCE = {"MASTER": "Từ Master", "CLIENT": "Từ Client", "BOT": "Bot đồng bộ",
                "BROKER": "Sàn đóng", "MANUAL": "Thủ công"}
ALERT_LEVEL = {"INFO": "Thông tin", "WARNING": "Cảnh báo",
               "ERROR": "Lỗi", "CRITICAL": "Nghiêm trọng"}
MASTER_POSITION_STATUS = {"OPEN": "Đang mở", "CLOSED": "Đã đóng", "UNPAIRED": "Chưa ghép cặp"}
```

Viết thêm hàm `label(group: dict, key: str) -> str` trả về nhãn, hoặc trả về chính `key`
kèm log WARNING nếu thiếu. Không được ném exception — thiếu một nhãn không đáng làm sập dashboard.

Giữ BUY, SELL và tên symbol nguyên gốc, không dịch.

### 1.6 Cấu hình

`bridge/config.py` đọc từ `config.toml` ở gốc dự án (tạo luôn file mẫu `config.example.toml`):

```toml
[bridge]
host = "0.0.0.0"
port = 8787
web_port = 8080
db_path = "data/bridge.db"

[security]
# Token thật đặt trong config.toml, file này nằm trong .gitignore
```

Thêm `config.toml` vào `.gitignore`. `config.example.toml` thì commit.

---

## Kiểm tra lại phần cũ

Không có phase trước. Bỏ qua.

## Kiểm tra phần mới

- [ ] `ruff check .` sạch.
- [ ] `pytest` chạy được (0 test cũng được, miễn không lỗi cấu hình).
- [ ] `python -c "import bridge.labels_vi"` chạy được.
- [ ] Viết một test nhỏ `tests/test_labels.py`: mọi giá trị trong mọi dict đều là chuỗi không rỗng,
      và `label()` với key không tồn tại thì trả về chính key chứ không ném exception.
- [ ] Mở từng file trong `docs/` và xác nhận không còn placeholder nào chưa điền.
- [ ] `docs/DECISIONS.md` có đủ 20 mục D-01 đến D-20.

## Tiêu chí hoàn thành

Một người mới clone repo về, đọc `README.md`, chạy được test, và đọc `docs/DECISIONS.md`
là hiểu được vì sao hệ thống được thiết kế như vậy — mà không cần hỏi ai.

## Không làm ở phase này

Không viết schema database. Không viết code mạng. Không viết MQL5.
