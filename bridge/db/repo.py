"""Tầng truy cập dữ liệu.

Không dùng ORM. SQL viết trực tiếp.

Ba quy tắc của tầng này:

1. **Mọi hàm ghi phải nằm trong một giao dịch.** Không có ghi lẻ. `Database.transaction()`
   lồng nhau được, nên phase 6 gói ba lệnh ghi (`master_position`, `pair`, `command`) vào đúng
   một giao dịch mà không phải viết lại hàm nào.
2. **Hàm đặt tên theo nghiệp vụ**, không phải CRUD chung chung: `create_pending_pair()`,
   không phải `insert_pair()`.
3. **Tầng này không chứa quy tắc nghiệp vụ.** Không tính volume, không quyết định có copy hay
   không, không cascade. Đó là việc của `bridge/engine/` ở phase 6-8.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from bridge.clock import day_key, utc_now_iso
from bridge.db.migrations import apply_migrations
from bridge.logging_setup import get_logger

log = get_logger(__name__)

PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous  = FULL",
    "PRAGMA foreign_keys = ON",
    "PRAGMA busy_timeout = 5000",
)

PAIR_ID_PREFIX = "PAIR"
PAIR_ID_DIGITS = 6
PAIR_ID_MAX_PER_DAY = 10**PAIR_ID_DIGITS - 1

#: Trạng thái pair cần người can thiệp, xếp theo mức nghiêm trọng giảm dần.
ATTENTION_STATUSES: tuple[str, ...] = ("ORPHANED", "OPEN_FAILED")


class RepoError(Exception):
    """Lỗi ở tầng dữ liệu mà nơi gọi phải xử lý, phân biệt với lỗi SQLite thô."""


class PairIdExhausted(RepoError):
    """Đã dùng hết 999999 Pair ID trong một ngày. Gần như chắc chắn là bug, không phải tải thật."""


def _now() -> str:
    return utc_now_iso()


class Database:
    """Giữ kết nối SQLite, áp pragma, và cung cấp giao dịch lồng nhau được.

    Kết nối là **đồng bộ**. Phase 3 sẽ gọi tầng này qua executor của asyncio; giữ nó đồng bộ
    làm cho test ở phase 2 đọc thẳng và không phải giả lập vòng lặp sự kiện.
    """

    def __init__(self, path: Path | str, *, migrate: bool = True) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: tắt hẳn việc tự mở giao dịch của Python, ta tự BEGIN/COMMIT.
        self.conn = sqlite3.connect(str(self.path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self._depth = 0
        self.apply_pragmas()
        if migrate:
            apply_migrations(self.conn)

    # -- vòng đời --------------------------------------------------------------------------

    def apply_pragmas(self) -> None:
        """Áp dụng pragma cho kết nối hiện tại.

        `foreign_keys` bị SQLite TẮT mặc định ở mỗi kết nối mới - quên gọi hàm này là mất toàn
        bộ ràng buộc khoá ngoại mà không có thông báo nào.
        """
        for pragma in PRAGMAS:
            self.conn.execute(pragma)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- giao dịch -------------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Giao dịch ghi. Lồng nhau được: chỉ lần ngoài cùng mới COMMIT hoặc ROLLBACK.

        Dùng `BEGIN IMMEDIATE` để giành khoá ghi ngay từ đầu. Với WAL và `busy_timeout`, cách
        này biến tranh chấp thành một lần chờ ngắn thay vì một lỗi `database is locked` giữa
        chừng giao dịch.
        """
        outermost = self._depth == 0
        if outermost:
            self.conn.execute("BEGIN IMMEDIATE")
        self._depth += 1
        try:
            yield self.conn
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.conn.execute("ROLLBACK")
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self.conn.execute("COMMIT")

    # -- truy vấn nhỏ ----------------------------------------------------------------------

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    # -- system_config ---------------------------------------------------------------------

    def get_config(self, key: str, default: str | None = None) -> str | None:
        """Đọc một giá trị cấu hình nghiệp vụ sửa nóng."""
        row = self.query_one("SELECT value FROM system_config WHERE key = ?", (key,))
        return row["value"] if row is not None else default

    def get_config_int(self, key: str, default: int) -> int:
        """Đọc cấu hình dạng số. Giá trị hỏng thì ghi WARNING và dùng mặc định, không sập."""
        raw = self.get_config(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            log.warning("system_config[%s] = %r khong phai so, dung mac dinh %d", key, raw, default)
            return default

    def set_config(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO system_config (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, value, _now()),
            )

    # -- agent -----------------------------------------------------------------------------

    def upsert_agent(self, agent_id: str, role: str, token_hash: str, magic_number: int,
                     **fields: Any) -> None:
        """Tạo hoặc cập nhật một agent.

        `token_hash` là hash, không bao giờ là token thô - xem mục bảo mật của phase 10.
        """
        now = _now()
        columns = {"agent_id": agent_id, "role": role, "token_hash": token_hash,
                   "magic_number": magic_number, "created_at": now, "updated_at": now, **fields}
        names = ", ".join(columns)
        holders = ", ".join("?" for _ in columns)
        updates = ", ".join(
            f"{c} = excluded.{c}" for c in columns if c not in ("agent_id", "created_at")
        )
        with self.transaction() as conn:
            conn.execute(
                f"INSERT INTO agent ({names}) VALUES ({holders}) "
                f"ON CONFLICT(agent_id) DO UPDATE SET {updates}",
                tuple(columns.values()),
            )

    def get_agent(self, agent_id: str) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM agent WHERE agent_id = ?", (agent_id,))

    def set_agent_status(self, agent_id: str, status: str,
                         broker_connected: int | None = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE agent SET status = ?, broker_connected = COALESCE(?, broker_connected), "
                "updated_at = ? WHERE agent_id = ?",
                (status, broker_connected, _now(), agent_id),
            )

    # -- client_account --------------------------------------------------------------------

    def upsert_client_account(self, client_id: str, agent_id: str, **fields: Any) -> None:
        now = _now()
        columns = {"client_id": client_id, "agent_id": agent_id,
                   "created_at": now, "updated_at": now, **fields}
        names = ", ".join(columns)
        holders = ", ".join("?" for _ in columns)
        updates = ", ".join(
            f"{c} = excluded.{c}" for c in columns if c not in ("client_id", "created_at")
        )
        with self.transaction() as conn:
            conn.execute(
                f"INSERT INTO client_account ({names}) VALUES ({holders}) "
                f"ON CONFLICT(client_id) DO UPDATE SET {updates}",
                tuple(columns.values()),
            )

    def get_client_account(self, client_id: str) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM client_account WHERE client_id = ?", (client_id,))

    def list_enabled_clients(self) -> list[sqlite3.Row]:
        return self.query_all("SELECT * FROM client_account WHERE enabled = 1 ORDER BY client_id")

    # -- symbol_spec -----------------------------------------------------------------------

    def replace_symbol_specs(self, agent_id: str, specs: Sequence[Mapping[str, Any]]) -> int:
        """Ghi đè toàn bộ spec của một agent. Trả về số dòng đã ghi.

        Ghi đè chứ không merge: broker đổi thông số thì bảng cũ phải biến mất, không để lại một
        dòng cũ nào đánh lừa phép tính volume ở phase 6.
        """
        now = _now()
        with self.transaction() as conn:
            conn.execute("DELETE FROM symbol_spec WHERE agent_id = ?", (agent_id,))
            written = 0
            for spec in specs:
                columns = {"agent_id": agent_id, **dict(spec), "updated_at": now}
                names = ", ".join(columns)
                holders = ", ".join("?" for _ in columns)
                conn.execute(
                    f"INSERT INTO symbol_spec ({names}) VALUES ({holders})",
                    tuple(columns.values()),
                )
                written += 1
        return written

    def get_symbol_spec(self, agent_id: str, symbol: str) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM symbol_spec WHERE agent_id = ? AND symbol = ?", (agent_id, symbol)
        )

    # -- symbol_map ------------------------------------------------------------------------

    def upsert_symbol_map(self, client_id: str, master_symbol: str, client_symbol: str,
                          **fields: Any) -> int:
        now = _now()
        columns = {"client_id": client_id, "master_symbol": master_symbol,
                   "client_symbol": client_symbol, "created_at": now, "updated_at": now, **fields}
        names = ", ".join(columns)
        holders = ", ".join("?" for _ in columns)
        updates = ", ".join(
            f"{c} = excluded.{c}" for c in columns
            if c not in ("client_id", "master_symbol", "created_at")
        )
        with self.transaction() as conn:
            cur = conn.execute(
                f"INSERT INTO symbol_map ({names}) VALUES ({holders}) "
                f"ON CONFLICT(client_id, master_symbol) DO UPDATE SET {updates}",
                tuple(columns.values()),
            )
            return int(cur.lastrowid or 0)

    def find_symbol_map(self, client_id: str, master_symbol: str) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM symbol_map WHERE client_id = ? AND master_symbol = ?",
            (client_id, master_symbol),
        )

    # -- master_position -------------------------------------------------------------------

    def upsert_master_position(self, master_position_id: int, agent_id: str, symbol: str,
                               direction: str, initial_volume: float, current_volume: float,
                               status: str = "OPEN", **fields: Any) -> None:
        """Ghi nhận một vị thế Master.

        `master_position_id` là `POSITION_IDENTIFIER`, KHÔNG phải ticket (D-06).
        Đơn vị của `initial_volume` và `current_volume` là **lot của sàn Master**.
        `initial_volume` không bị ghi đè khi upsert lại - nó là con số tại lúc mở.
        """
        now = _now()
        columns = {"master_position_id": master_position_id, "agent_id": agent_id,
                   "symbol": symbol, "direction": direction, "initial_volume": initial_volume,
                   "current_volume": current_volume, "status": status,
                   "created_at": now, "updated_at": now, **fields}
        names = ", ".join(columns)
        holders = ", ".join("?" for _ in columns)
        updates = ", ".join(
            f"{c} = excluded.{c}" for c in columns
            if c not in ("master_position_id", "created_at", "initial_volume")
        )
        with self.transaction() as conn:
            conn.execute(
                f"INSERT INTO master_position ({names}) VALUES ({holders}) "
                f"ON CONFLICT(master_position_id) DO UPDATE SET {updates}",
                tuple(columns.values()),
            )

    def get_master_position(self, master_position_id: int) -> sqlite3.Row | None:
        return self.query_one(
            "SELECT * FROM master_position WHERE master_position_id = ?", (master_position_id,)
        )

    def set_master_position_status(self, master_position_id: int, status: str,
                                   current_volume: float | None = None,
                                   close_time: str | None = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE master_position SET status = ?, "
                "current_volume = COALESCE(?, current_volume), "
                "close_time = COALESCE(?, close_time), updated_at = ? "
                "WHERE master_position_id = ?",
                (status, current_volume, close_time, _now(), master_position_id),
            )

    # -- Pair ID ---------------------------------------------------------------------------

    def next_pair_id(self, day: str | None = None) -> str:
        """Sinh Pair ID kế tiếp dạng ``PAIR-YYYYMMDD-NNNNNN``.

        Bộ đếm reset theo ngày (UTC) và lấy từ DB **trong cùng giao dịch** với việc tạo pair,
        nên hai luồng không thể nhận cùng một số. Cố ý không dùng UUID: Pair ID phải đọc được
        bằng mắt trên dashboard và trong log.
        """
        today = day or day_key()
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO pair_id_seq (day, last_number) VALUES (?, 1) "
                "ON CONFLICT(day) DO UPDATE SET last_number = last_number + 1",
                (today,),
            )
            row = conn.execute(
                "SELECT last_number FROM pair_id_seq WHERE day = ?", (today,)
            ).fetchone()
            number = int(row["last_number"])
            if number > PAIR_ID_MAX_PER_DAY:
                raise PairIdExhausted(
                    f"Đã dùng hết {PAIR_ID_MAX_PER_DAY} Pair ID trong ngày {today}"
                )
        return f"{PAIR_ID_PREFIX}-{today}-{number:0{PAIR_ID_DIGITS}d}"

    # -- pair ------------------------------------------------------------------------------

    def create_pending_pair(self, master_position_id: int, client_id: str, copy_mode: str,
                            master_initial_volume: float, effective_multiplier: float,
                            **fields: Any) -> str | None:
        """Tạo một pair ở trạng thái ``PENDING_OPEN``. Trả về Pair ID, hoặc ``None`` nếu đã có.

        `effective_multiplier` là tỷ lệ **thực tế sau làm tròn** và bị khoá tại đây cho tới hết
        vòng đời của cặp (D-19). Đơn vị của `master_initial_volume` là lot của sàn Master.

        Trả về ``None`` khi ràng buộc ``UNIQUE (master_position_id, client_id)`` chặn lại: đó là
        một event lặp, **không phải lỗi** - nơi gọi ghi INFO rồi bỏ qua.
        """
        now = _now()
        with self.transaction() as conn:
            # `BEGIN IMMEDIATE` đã giữ khoá ghi, nên kiểm tra trước ở đây không có khe hở đua
            # nhau. Kiểm tra trước để một event lặp không đốt mất một số Pair ID.
            if conn.execute(
                "SELECT 1 FROM pair WHERE master_position_id = ? AND client_id = ?",
                (master_position_id, client_id),
            ).fetchone() is not None:
                log.info(
                    "Da co pair cho (master_position_id=%s, client_id=%s), bo qua event lap",
                    master_position_id, client_id,
                )
                return None

            pair_id = self.next_pair_id()
            columns = {
                "pair_id": pair_id,
                "master_position_id": master_position_id,
                "client_id": client_id,
                "copy_mode": copy_mode,
                "master_initial_volume": master_initial_volume,
                "master_current_volume": fields.pop("master_current_volume",
                                                    master_initial_volume),
                "effective_multiplier": effective_multiplier,
                "status": "PENDING_OPEN",
                "created_at": now,
                "updated_at": now,
                **fields,
            }
            names = ", ".join(columns)
            holders = ", ".join("?" for _ in columns)
            try:
                conn.execute(
                    f"INSERT INTO pair ({names}) VALUES ({holders})", tuple(columns.values())
                )
            except sqlite3.IntegrityError:
                # Lưới an toàn cuối cùng. Không so khớp nội dung thông báo lỗi của SQLite —
                # nó đổi giữa các phiên bản. Hỏi thẳng DB xem đã có pair chưa.
                duplicate = conn.execute(
                    "SELECT 1 FROM pair WHERE master_position_id = ? AND client_id = ?",
                    (master_position_id, client_id),
                ).fetchone()
                if duplicate is None:
                    raise
                log.info(
                    "Da co pair cho (master_position_id=%s, client_id=%s), bo qua event lap",
                    master_position_id, client_id,
                )
                return None
        return pair_id

    def get_pair(self, pair_id: str) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM pair WHERE pair_id = ?", (pair_id,))

    def find_pair_by_client_position(self, client_id: str,
                                     client_position_id: int) -> sqlite3.Row | None:
        """Tra pair theo vị thế Client. Tra cứu theo `position_id`, không bao giờ theo symbol."""
        return self.query_one(
            "SELECT * FROM pair WHERE client_id = ? AND client_position_id = ?",
            (client_id, client_position_id),
        )

    def list_pairs_for_master_position(self, master_position_id: int,
                                       only_active: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM pair WHERE master_position_id = ?"
        if only_active:
            sql += " AND status NOT IN ('CLOSED', 'OPEN_FAILED')"
        return self.query_all(sql + " ORDER BY pair_id", (master_position_id,))

    def mark_pair_open(self, pair_id: str, client_position_id: int, client_ticket: int | None,
                       client_volume: float, open_time_client: str | None = None,
                       **fields: Any) -> None:
        """Chuyển pair sang ``OPEN`` sau khi Client báo mở lệnh thành công.

        `client_volume` tính bằng lot của **sàn Client**, là volume thực tế đã khớp.
        """
        columns = {
            "status": "OPEN",
            "client_position_id": client_position_id,
            "client_ticket": client_ticket,
            "client_initial_volume": client_volume,
            "client_current_volume": client_volume,
            "open_time_client": open_time_client or _now(),
            "updated_at": _now(),
            **fields,
        }
        assignments = ", ".join(f"{c} = ?" for c in columns)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE pair SET {assignments} WHERE pair_id = ?",
                (*columns.values(), pair_id),
            )

    def update_pair(self, pair_id: str, **fields: Any) -> None:
        """Cập nhật tuỳ ý một pair. Luôn tự đặt lại `updated_at`."""
        if not fields:
            return
        fields = {**fields, "updated_at": _now()}
        assignments = ", ".join(f"{c} = ?" for c in fields)
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE pair SET {assignments} WHERE pair_id = ?", (*fields.values(), pair_id)
            )

    def mark_pair_closed(self, pair_id: str, close_source: str,
                         close_time_client: str | None = None,
                         close_time_master: str | None = None,
                         master_da_dong: bool | None = None) -> None:
        """Chuyển pair sang ``CLOSED``.

        `client_current_volume` luôn về 0 — hàm này chỉ được gọi khi chân Client đã đóng xong.

        `master_current_volume` thì **không**: bản cũ đưa cả hai về 0 chỉ dựa vào ack của Client,
        nên sổ sách khẳng định Master đã phẳng trong khi chưa ai đụng tới nó. Đó là thứ làm cho
        lỗi "đóng khẩn cấp không đóng Master" trở nên vô hình suốt mười phase (kiểm toán
        2026-09-06, F-01). Nay chỉ về 0 khi biết chắc:

        * `master_da_dong=True` — người gọi có bằng chứng (đối chiếu thấy vị thế đã biến mất khỏi
          terminal);
        * để `None` — tự đọc `master_position.status`, nguồn sự thật do EA báo về.
        """
        now = _now()
        if master_da_dong is None:
            row = self.query_one(
                "SELECT mp.status FROM pair p JOIN master_position mp "
                "ON mp.master_position_id = p.master_position_id WHERE p.pair_id = ?", (pair_id,))
            master_da_dong = row is not None and row["status"] == "CLOSED"
        dat_master = "master_current_volume = 0, " if master_da_dong else ""
        with self.transaction() as conn:
            conn.execute(
                "UPDATE pair SET status = 'CLOSED', close_source = ?, "
                f"{dat_master}client_current_volume = 0, "
                "close_time_client = COALESCE(?, close_time_client, ?), "
                "close_time_master = COALESCE(?, close_time_master, ?), "
                "updated_at = ? WHERE pair_id = ?",
                (close_source, close_time_client, now, close_time_master, now, now, pair_id),
            )

    def zero_master_volume(self, master_position_id: int) -> None:
        """Đưa `master_current_volume` về 0 cho mọi cặp của một vị thế Master **đã đóng thật**.

        Tách riêng khỏi `mark_pair_closed` vì hai việc xảy ra ở hai thời điểm khác nhau: cặp
        được đóng sổ khi Client ack, còn chân Master chỉ chắc chắn phẳng khi chính EA Master ack.
        """
        with self.transaction() as conn:
            conn.execute(
                "UPDATE pair SET master_current_volume = 0, updated_at = ? "
                "WHERE master_position_id = ? AND master_current_volume <> 0",
                (_now(), master_position_id),
            )

    def list_pairs_needing_attention(self) -> list[sqlite3.Row]:
        """Các cặp cần người can thiệp, xếp theo mức nghiêm trọng chứ không theo thời gian.

        Khi có 40 cặp và 2 cặp mất hedge, sắp theo thời gian sẽ chôn hai cặp cần cứu xuống giữa
        danh sách.
        """
        holders = ", ".join("?" for _ in ATTENTION_STATUSES)
        order = " ".join(
            f"WHEN '{status}' THEN {index}" for index, status in enumerate(ATTENTION_STATUSES)
        )
        return self.query_all(
            f"SELECT * FROM pair WHERE status IN ({holders}) "
            f"ORDER BY CASE status {order} ELSE 99 END, created_at",
            ATTENTION_STATUSES,
        )

    # -- event -----------------------------------------------------------------------------

    def record_event(self, event_id: str, agent_id: str, seq: int, event_type: str,
                     **fields: Any) -> tuple[sqlite3.Row, bool]:
        """Ghi một event. Trả về ``(bản ghi, có phải bản ghi mới không)``.

        Gặp `event_id` đã tồn tại thì **trả về bản ghi cũ**, không ném exception - đây chính là
        cơ chế dedup (D-08, FR-31). Ngược lại, trùng ``(agent_id, seq)`` với `event_id` khác thì
        vẫn ném `IntegrityError`: hai sự kiện khác nhau mang cùng số thứ tự là dấu hiệu agent
        hỏng, phải nhìn thấy chứ không được nuốt.
        """
        columns = {
            "event_id": event_id,
            "agent_id": agent_id,
            "seq": seq,
            "type": event_type,
            "received_at": _now(),
            **fields,
        }
        names = ", ".join(columns)
        holders = ", ".join("?" for _ in columns)
        with self.transaction() as conn:
            try:
                conn.execute(
                    f"INSERT INTO event ({names}) VALUES ({holders})", tuple(columns.values())
                )
            except sqlite3.IntegrityError:
                existing = conn.execute(
                    "SELECT * FROM event WHERE event_id = ?", (event_id,)
                ).fetchone()
                if existing is None:
                    raise
                log.info("Event %s da co trong DB, bo qua ban trung", event_id,
                         extra={"event_id": event_id})
                return existing, False
            row = conn.execute("SELECT * FROM event WHERE event_id = ?", (event_id,)).fetchone()
        return row, True

    def get_event(self, event_id: str) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM event WHERE event_id = ?", (event_id,))

    def claim_next_pending_event(self, agent_id: str | None = None) -> sqlite3.Row | None:
        """Lấy event `PENDING` cũ nhất theo `id` tăng dần, tuỳ chọn giới hạn theo agent.

        Thứ tự là ràng buộc nghiệp vụ, không phải tiểu tiết: event của cùng một agent phải xử lý
        tuần tự. Schema không có trạng thái "đang xử lý", nên hàm này chỉ *chọn* chứ không đổi
        trạng thái - nơi gọi phải kết thúc bằng `mark_event_processed()`.
        """
        if agent_id is None:
            return self.query_one(
                "SELECT * FROM event WHERE process_status = 'PENDING' ORDER BY id LIMIT 1"
            )
        return self.query_one(
            "SELECT * FROM event WHERE process_status = 'PENDING' AND agent_id = ? "
            "ORDER BY id LIMIT 1",
            (agent_id,),
        )

    def mark_event_processed(self, event_id: str, status: str, error: str | None = None,
                             pair_id: str | None = None) -> None:
        """Đóng sổ một event: ``DONE``, ``IGNORED`` hoặc ``ERROR``."""
        with self.transaction() as conn:
            conn.execute(
                "UPDATE event SET process_status = ?, process_error = ?, "
                "pair_id = COALESCE(?, pair_id), processed_at = ? WHERE event_id = ?",
                (status, error, pair_id, _now(), event_id),
            )

    def set_event_cause(self, event_id: str, command_id: str) -> None:
        """Gắn `caused_by_command_id` cho một event **sau khi** nó đã được ghi.

        Bình thường EA gắn trường này lúc sinh event (`RememberCause`, D-08), và Bridge không
        đụng vào. Đường ĐÓNG qua giao diện là ngoại lệ: EA không gọi `OrderSend` nên không có gì
        để nhớ, và Bridge phải tự nhận cha cho event dựa trên lệnh đóng nó vừa gửi.

        Không gắn thì nhật ký event nói dối: một lệnh đóng do chính bot phát ra sẽ nằm đó với
        `caused_by_command_id = NULL`, tức là mang đúng dấu hiệu của một lệnh người dùng đóng tay.
        """
        with self.transaction() as conn:
            conn.execute(
                "UPDATE event SET caused_by_command_id = ? WHERE event_id = ?",
                (command_id, event_id),
            )

    def max_seq_for_agent(self, agent_id: str) -> int:
        """`seq` cao nhất đã ghi thành công của một agent. Dùng để phát hiện lỗ hổng ở phase 3."""
        row = self.query_one("SELECT MAX(seq) FROM event WHERE agent_id = ?", (agent_id,))
        value = row[0] if row is not None else None
        return int(value) if value is not None else 0

    # -- command ---------------------------------------------------------------------------

    def create_command(self, command_id: str, target_agent_id: str, command_type: str,
                       **fields: Any) -> None:
        """Ghi command vào outbox ở trạng thái ``PENDING``.

        Luôn ghi vào DB **trước** khi gửi qua socket. Không bao giờ gửi một command chưa có
        trong bảng này.
        """
        now = _now()
        columns = {"command_id": command_id, "target_agent_id": target_agent_id,
                   "type": command_type, "status": "PENDING",
                   "created_at": now, "updated_at": now, **fields}
        names = ", ".join(columns)
        holders = ", ".join("?" for _ in columns)
        with self.transaction() as conn:
            conn.execute(
                f"INSERT INTO command ({names}) VALUES ({holders})", tuple(columns.values())
            )

    def get_command(self, command_id: str) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM command WHERE command_id = ?", (command_id,))

    def mark_command_sent(self, command_id: str) -> None:
        with self.transaction() as conn:
            now = _now()
            conn.execute(
                "UPDATE command SET status = 'SENT', attempt = attempt + 1, sent_at = ?, "
                "updated_at = ? WHERE command_id = ?",
                (now, now, command_id),
            )

    def mark_command_acked(self, command_id: str, status: str, retcode: int | None = None,
                           retmsg: str | None = None, executed_volume: float | None = None,
                           result_position_id: int | None = None) -> None:
        """Ghi kết quả ack. `retcode` giữ nguyên bản từ `MqlTradeResult`, không dịch, không gộp."""
        now = _now()
        with self.transaction() as conn:
            conn.execute(
                "UPDATE command SET status = ?, retcode = ?, retmsg = ?, executed_volume = ?, "
                "result_position_id = ?, acked_at = ?, updated_at = ? WHERE command_id = ?",
                (status, retcode, retmsg, executed_volume, result_position_id, now, now,
                 command_id),
            )

    def list_inflight_commands(self, pair_id: str | None = None) -> list[sqlite3.Row]:
        """Command đang `PENDING` hoặc `SENT`.

        Phase 7 dùng hàm này để không tạo hai lệnh đóng cho cùng một cặp.
        """
        sql = "SELECT * FROM command WHERE status IN ('PENDING', 'SENT')"
        if pair_id is None:
            return self.query_all(sql + " ORDER BY created_at")
        return self.query_all(sql + " AND pair_id = ? ORDER BY created_at", (pair_id,))

    # -- reconcile_finding -----------------------------------------------------------------

    def create_finding(self, run_id: str, severity: str, kind: str,
                       suggested_action: str | None = None, **fields: Any) -> int:
        """Ghi một dòng sai lệch do đối chiếu phát hiện.

        `evidence_json` phải chứa **cả ba nguồn** (DB nói gì, Master thực tế, Client thực tế).
        Người vận hành cần thấy bằng chứng để tự phán đoán, không chỉ thấy kết luận.
        """
        columns = {
            "run_id": run_id, "severity": severity, "kind": kind,
            "suggested_action": suggested_action, "resolution": "PENDING",
            "created_at": _now(), **fields,
        }
        names = ", ".join(columns)
        holders = ", ".join("?" for _ in columns)
        with self.transaction() as conn:
            cur = conn.execute(
                f"INSERT INTO reconcile_finding ({names}) VALUES ({holders})",
                tuple(columns.values()))
            return int(cur.lastrowid or 0)

    def get_finding(self, finding_id: int) -> sqlite3.Row | None:
        return self.query_one("SELECT * FROM reconcile_finding WHERE id = ?", (finding_id,))

    def list_findings(self, run_id: str | None = None, resolution: str | None = None,
                      severity: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM reconcile_finding WHERE 1 = 1"
        params: list[Any] = []
        for cot, gia_tri in (("run_id", run_id), ("resolution", resolution),
                             ("severity", severity)):
            if gia_tri is not None:
                sql += f" AND {cot} = ?"
                params.append(gia_tri)
        return self.query_all(sql + " ORDER BY id", tuple(params))

    def resolve_finding(self, finding_id: int, resolution: str,
                        note: str | None = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE reconcile_finding SET resolution = ?, resolved_at = ?, "
                "resolved_note = ? WHERE id = ?",
                (resolution, _now(), note, finding_id))

    # -- alert -----------------------------------------------------------------------------

    def create_alert(self, level: str, code: str, message: str, **fields: Any) -> int:
        """Ghi một việc con người phải xử lý. Trả về id của alert."""
        columns = {"level": level, "code": code, "message": message,
                   "created_at": _now(), **fields}
        names = ", ".join(columns)
        holders = ", ".join("?" for _ in columns)
        with self.transaction() as conn:
            cur = conn.execute(
                f"INSERT INTO alert ({names}) VALUES ({holders})", tuple(columns.values())
            )
            return int(cur.lastrowid or 0)

    def list_open_alerts(self, level: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM alert WHERE acknowledged_at IS NULL"
        if level is None:
            return self.query_all(sql + " ORDER BY created_at DESC")
        return self.query_all(sql + " AND level = ? ORDER BY created_at DESC", (level,))

    def acknowledge_alert(self, alert_id: int) -> None:
        with self.transaction() as conn:
            conn.execute("UPDATE alert SET acknowledged_at = ? WHERE id = ?", (_now(), alert_id))

    def acknowledge_alerts_by_code(self, codes: list[str], before: str) -> int:
        """Xác nhận các alert chưa xem có mã thuộc `codes` và sinh ra **trước** `before`.

        Trả về số dòng thực sự đổi. Cố ý không có dạng "mọi mã" — xem `bridge.admin
        xac-nhan-alert`.
        """
        if not codes:
            return 0
        dau_hoi = ", ".join("?" for _ in codes)
        with self.transaction() as conn:
            cur = conn.execute(
                "UPDATE alert SET acknowledged_at = ? WHERE acknowledged_at IS NULL "
                f"AND created_at < ? AND code IN ({dau_hoi})",
                (_now(), before, *codes))
            return int(cur.rowcount)
