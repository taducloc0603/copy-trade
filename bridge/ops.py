"""Việc vận hành: sao lưu, bảo trì hàng ngày, cấp và thu hồi token (plan mục 10.2, 10.3).

Ba thứ ở đây đều là loại "không ai nhớ tới cho tới lúc cần", nên chúng phải chạy tự động và
phải **kiểm chứng được**. Một bản sao lưu chưa từng khôi phục thử thì không phải bản sao lưu.
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from bridge.clock import utc_now, utc_now_iso
from bridge.db.repo import Database
from bridge.db.retention import run_retention
from bridge.logging_setup import get_logger
from bridge.protocol.auth import generate_token, hash_token

log = get_logger(__name__)

#: Số bản sao lưu giữ lại. Mất một bản vì đĩa đầy còn hơn mất cả ổ vì không dọn.
SO_BAN_SAO_LUU = 14

BACKUP_DIR_NAME = "backup"


@dataclass
class KetQuaBaoTri:
    """Kết quả một lần bảo trì hàng ngày."""

    ban_sao_luu: Path | None
    da_xoa: list[Path]
    event_luu_tru: int
    command_luu_tru: int


def thu_muc_sao_luu(db_path: Path) -> Path:
    return db_path.parent / BACKUP_DIR_NAME


def sao_luu(db: Database, db_path: Path) -> Path:
    """Sao lưu bằng `VACUUM INTO`.

    Chọn `VACUUM INTO` chứ không phải copy file: nó **an toàn với WAL** và không cần dừng dịch
    vụ. Copy `bridge.db` khi WAL đang có dữ liệu chưa checkpoint sẽ ra một bản thiếu — và thiếu
    đúng những giao dịch mới nhất, tức những thứ quý nhất.
    """
    thu_muc = thu_muc_sao_luu(db_path)
    thu_muc.mkdir(parents=True, exist_ok=True)
    dich = thu_muc / f"bridge-{utc_now().strftime('%Y%m%d-%H%M%S')}.db"
    # `VACUUM INTO` **không chạy được bên trong một giao dịch** — SQLite từ chối thẳng. Nên gọi
    # trực tiếp trên kết nối, không bọc `db.transaction()`. Không mất an toàn: bản thân câu lệnh
    # này đã chụp một trạng thái nhất quán, đó chính là lý do chọn nó thay vì copy file.
    db.conn.execute("VACUUM INTO ?", (str(dich),))
    log.info("Da sao luu vao %s (%d byte)", dich, dich.stat().st_size)
    return dich


def don_ban_cu(db_path: Path, giu: int = SO_BAN_SAO_LUU) -> list[Path]:
    ban = sorted(thu_muc_sao_luu(db_path).glob("bridge-*.db"))
    thua = ban[:-giu] if len(ban) > giu else []
    for p in thua:
        p.unlink()
        log.info("Xoa ban sao luu cu %s", p.name)
    return thua


def kiem_chung_ban_sao_luu(duong_dan: Path) -> dict[str, int]:
    """Mở thử một bản sao lưu và đếm dữ liệu trong đó.

    **Một bản sao lưu chưa từng khôi phục thử thì không phải bản sao lưu.** Hàm này tồn tại để
    việc kiểm chứng là một dòng code chạy mỗi ngày chứ không phải một việc ai đó nhớ làm.
    """
    conn = sqlite3.connect(f"file:{duong_dan}?mode=ro", uri=True)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError(f"Ban sao luu {duong_dan.name} hong: integrity_check that bai")
        return {ten: conn.execute(f"SELECT COUNT(*) FROM {ten}").fetchone()[0]
                for ten in ("pair", "event", "command", "agent")}
    finally:
        conn.close()


def don_so_sach(db: Database) -> int:
    """Dọn các dòng `pair` mà sổ sách còn giữ số cũ. Trả về số dòng đã sửa (B-12).

    Một cặp đã `CLOSED` mà `master_current_volume` vẫn khác 0 là tàn dư của những lần sửa trước:
    con số đó chỉ được đưa về 0 khi EA Master ack, nên cặp nào đóng bằng đường khác sẽ giữ lại
    giá trị cũ mãi. Vô hại về nghiệp vụ — cặp đã đóng thì không ai đụng tới nữa — nhưng nó làm
    bẩn mọi báo cáo đọc từ bảng này.

    Chỉ dọn khi vị thế Master **thật sự** đã đóng; không suy diễn từ trạng thái của cặp.
    """
    with db.transaction() as conn:
        cur = conn.execute(
            "UPDATE pair SET master_current_volume = 0, updated_at = ? "
            "WHERE status = 'CLOSED' AND master_current_volume <> 0 "
            "AND master_position_id IN (SELECT master_position_id FROM master_position "
            "                           WHERE status = 'CLOSED')",
            (utc_now_iso(),))
        so = cur.rowcount
    if so:
        log.info("Don so sach: dua %d dong pair ve dung volume Master", so)
    return so


def bao_tri_hang_ngay(db: Database, db_path: Path,
                      retention_days: int | None = None) -> KetQuaBaoTri:
    """Chạy retention rồi sao lưu, theo đúng thứ tự đó.

    Sao lưu **sau** khi dọn: bản sao lưu nhỏ hơn, và nếu retention có lỗi thì ta còn bản của
    hôm qua chưa bị đụng tới.
    """
    don_so_sach(db)
    bao_cao = run_retention(db, retention_days=retention_days)
    ban = sao_luu(db, db_path)
    da_xoa = don_ban_cu(db_path)
    kiem_chung_ban_sao_luu(ban)
    return KetQuaBaoTri(ban_sao_luu=ban, da_xoa=da_xoa,
                        event_luu_tru=getattr(bao_cao, "events_archived", 0),
                        command_luu_tru=getattr(bao_cao, "commands_archived", 0))


# -- token (plan 10.2) -------------------------------------------------------------------------

def cap_token(db: Database, agent_id: str) -> str:
    """Cấp token mới cho một agent. Trả về **giá trị thô đúng một lần**.

    DB chỉ giữ hash. Giá trị thô đi thẳng vào tham số EA hoặc `config.toml`; không ghi log, không
    lưu lại ở đâu khác. Mất thì cấp lại, không có đường đọc lại.

    **Cấp token cũng bật lại agent đang bị vô hiệu hoá.** Bản đầu chỉ đổi hash, nên cấp token sau
    khi `thu_hoi_token` cho ra một token hợp lệ mà agent vẫn bị từ chối bắt tay với
    `AGENT_DISABLED` — không có manh mối nào ở phía người vận hành. Gặp thật khi dựng lại clicker
    ở phase 11 (B-10). Cấp token là hành động có chủ đích để agent nối lại được; nếu muốn nó nằm
    im thì đừng cấp token cho nó.
    """
    agent = db.get_agent(agent_id)
    if agent is None:
        raise LoiCauHinh("KHONG_CO_AGENT", agent_id=agent_id)
    token = generate_token()
    with db.transaction() as conn:
        conn.execute(
            "UPDATE agent SET token_hash = ?, enabled = 1, updated_at = ? WHERE agent_id = ?",
            (hash_token(token), utc_now_iso(), agent_id))
    if not agent["enabled"]:
        log.warning("Agent %s dang bi vo hieu hoa, cap token moi nen bat lai", agent_id,
                    extra={"agent_id": agent_id})
    log.info("Da cap token moi cho agent %s", agent_id, extra={"agent_id": agent_id})
    return token


def thu_hoi_token(db: Database, agent_id: str) -> bool:
    """Thu hồi token: agent không kết nối lại được nữa.

    Đặt hash thành một giá trị **không thể sinh ra từ bất kỳ token nào** thay vì xoá dòng agent.
    Xoá dòng sẽ kéo theo khoá ngoại và làm mất lịch sử; ta muốn agent còn đó nhưng vô hiệu.
    """
    agent = db.get_agent(agent_id)
    if agent is None:
        return False
    with db.transaction() as conn:
        conn.execute(
            "UPDATE agent SET token_hash = 'DA-THU-HOI', enabled = 0, updated_at = ? "
            "WHERE agent_id = ?", (utc_now_iso(), agent_id))
    log.warning("Da thu hoi token cua agent %s", agent_id, extra={"agent_id": agent_id})
    return True


def doi_login_agent(db: Database, agent_id: str, login: int) -> bool:
    """Đặt lại `account_login` của một agent đã có. `False` nếu không có agent đó.

    Tồn tại vì một lỗi thật trên VPS 2026-09-15: trợ lý tạo `AG-CLICKER-MASTER` với số tài khoản
    `0`, clicker gửi `538286`, và Bridge từ chối bắt tay mãi với `ACCOUNT_MISMATCH` (`server.py`
    so khớp khi cột này khác NULL). Không có lệnh nào sửa được, còn `UPDATE` tay vào SQLite là
    điều dự án cấm — nên phải có lệnh có tên.
    """
    if login <= 0:
        raise LoiCauHinh("LOGIN_KHONG_DUONG", login=login)
    if db.get_agent(agent_id) is None:
        return False
    with db.transaction() as conn:
        conn.execute("UPDATE agent SET account_login = ?, updated_at = ? WHERE agent_id = ?",
                     (login, utc_now_iso(), agent_id))
    log.warning("Doi account_login cua agent %s thanh %s", agent_id, login,
                extra={"agent_id": agent_id})
    return True


# -- dọn log (plan 10.1) -----------------------------------------------------------------------

def don_log_cu(logs_dir: Path, giu_ngay: int = 30) -> list[Path]:
    """Xoá file log cũ hơn `giu_ngay`. Giữ 30 ngày theo plan 10.1."""
    if not logs_dir.is_dir():
        return []
    han = utc_now() - timedelta(days=giu_ngay)
    da_xoa = []
    for p in sorted(logs_dir.glob("*.log*")):
        if p.stat().st_mtime < han.timestamp():
            p.unlink()
            da_xoa.append(p)
    if da_xoa:
        log.info("Xoa %d file log cu hon %d ngay", len(da_xoa), giu_ngay)
    return da_xoa


def khoi_phuc_thu(duong_dan: Path, dich: Path) -> Path:
    """Khôi phục một bản sao lưu ra thư mục khác để kiểm chứng, không đụng bản đang chạy."""
    dich.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(duong_dan, dich)
    kiem_chung_ban_sao_luu(dich)
    return dich


# -- nghiệm thu TEST-23 --------------------------------------------------------------------------

#: `DEAL_REASON_CLIENT`. Xem `bridge/web/views.py`.
REASON_CLIENT = 0


def kiem_reason_client(db: Database) -> list[dict[str, object]]:
    """TEST-23: **mọi deal** của bot trên Client phải mang `DEAL_REASON_CLIENT`.

    Bộ nghiệm thu yêu cầu rõ: kiểm **tự động bằng truy vấn**, không nhìn bằng mắt. Lý do là cỡ
    mẫu — nhìn mắt thì người ta xem ba dòng đầu rồi kết luận, mà cái sai duy nhất có thể nằm ở
    dòng thứ hai mươi.

    Soi **cả hai** cột, và đó là điểm khác so với bản đầu. Lúc chỉ đường MỞ đi qua giao diện thì
    một cột là đủ. Từ khi đường ĐÓNG cũng đi qua giao diện, chỉ soi `client_open_reason` sẽ cho
    một kết quả "ĐẠT" hoàn toàn thật mà vẫn bỏ sót đúng nửa số deal — nửa mà yêu cầu lần này
    nhắm tới.

    Trả về danh sách cặp **vi phạm**, mỗi dòng kèm `cot` cho biết vế nào sai. Rỗng nghĩa là đạt.

    Cột `NULL` không tính là vi phạm: cặp chưa mở được vị thế nào (`OPEN_FAILED`, hoặc còn
    `PENDING_OPEN`) thì không có deal nào để mà sai kênh, và cặp chưa đóng thì chưa có deal đóng.
    """
    rows = db.query_all(
        "SELECT pair_id, client_id, client_position_id, status, error_message, "
        "       client_open_reason, client_close_reason "
        "FROM pair WHERE (client_open_reason IS NOT NULL AND client_open_reason <> ?) "
        "           OR (client_close_reason IS NOT NULL AND client_close_reason <> ?) "
        "ORDER BY pair_id", (REASON_CLIENT, REASON_CLIENT))
    vi_pham = []
    for r in rows:
        cot = [ten for ten in ("client_open_reason", "client_close_reason")
               if r[ten] is not None and r[ten] != REASON_CLIENT]
        vi_pham.append({**dict(r), "cot": ", ".join(cot),
                        "da_giai_thich": _da_giai_thich(r, cot)})
    chua_ro = [v for v in vi_pham if not v["da_giai_thich"]]
    if chua_ro:
        log.error("TEST-23 KHONG DAT: %d cap co deal Client sai kenh khong giai thich duoc",
                  len(chua_ro))
    return vi_pham


def kiem_reason_master(db: Database) -> list[dict[str, object]]:
    """Phase 12: khi `master_close_route = UI`, mọi deal **đóng** trên Master phải là `CLIENT`.

    Chỉ kiểm khi đang bật đường giao diện cho Master. Với `EA` thì `EXPERT` là **đúng**, không
    phải vi phạm — kiểm nó ở đó chỉ tạo ra một tiêu chí không bao giờ đạt.

    Cùng cách xử lý "đã có giải thích" như phía Client: một lần rơi về `OrderSend` khi clicker của
    Master hỏng là hành vi cố ý, có alert CRITICAL, và con số `EXPERT` ấy nằm lại vĩnh viễn trong
    `master_position`. Gộp nó vào phần thất bại thì sau đúng một sự cố, TEST-30 báo KHÔNG ĐẠT mãi.
    """
    if (db.get_config("master_close_route", "EA") or "EA").upper() != "UI":
        return []
    # Chỉ chấm vị thế đóng SAU lúc bật `UI`. Trước mốc đó `EXPERT` là **đúng cấu hình**, và chấm nó
    # là tạo một tiêu chí không bao giờ đạt — đúng chuyện đã xảy ra trên VPS 2026-09-15: bật UI xong,
    # TEST-30 báo 6 vi phạm, cả 6 là lần đóng qua EA từ trước khi bật.
    # `close_time` NULL vẫn được tính: không biết thì không loại, để không che một vi phạm thật.
    moc = moc_bat_ui_master(db)
    rows = db.query_all(
        "SELECT master_position_id, symbol, close_reason, close_time FROM master_position "
        "WHERE close_reason IS NOT NULL AND close_reason <> ? "
        "  AND (close_time IS NULL OR ? IS NULL OR close_time >= ?) "
        "ORDER BY master_position_id",
        (REASON_CLIENT, moc, moc))
    vi_pham = []
    for r in rows:
        da_giai_thich = db.query_one(
            "SELECT 1 FROM alert a JOIN pair p ON p.pair_id = a.pair_id "
            "WHERE a.code = 'CLOSE_MASTER_FELL_BACK_TO_EA' AND p.master_position_id = ? LIMIT 1",
            (r["master_position_id"],)) is not None
        vi_pham.append({**dict(r), "da_giai_thich": da_giai_thich})
    chua_ro = [v for v in vi_pham if not v["da_giai_thich"]]
    if chua_ro:
        log.error("TEST-30 KHONG DAT: %d vi the Master dong sai kenh khong giai thich duoc",
                  len(chua_ro))
    return vi_pham


def moc_bat_ui_master(db: Database) -> str | None:
    """Lúc `master_close_route` được đặt lần gần nhất — tức lúc bật đường đóng Master qua giao diện.

    Lấy từ `system_config.updated_at`: `bridge.admin cau-hinh-master` ghi bằng `set_config`, và
    `set_config` luôn cập nhật cột đó.
    """
    row = db.query_one("SELECT updated_at FROM system_config WHERE key = 'master_close_route'")
    return row["updated_at"] if row is not None else None


# -- chẩn đoán "chốt sai" ------------------------------------------------------------------------

#: Loại deal làm giảm hoặc xoá một vị thế.
DEAL_DONG = ("OUT", "INOUT", "OUT_BY")

#: Cửa sổ quanh một lệnh đóng khi tìm deal nó gây ra: từ trước lúc gửi tới sau lúc ack.
CUA_SO_TRUOC_GUI_MS = 1000
CUA_SO_SAU_ACK_MS = 5000

#: Alert đáng xem khi nghi chốt sai. Không cái nào tự nó là bằng chứng — nhưng không có cái nào thì
#: nhánh ghép nhầm lúc mở gần như bị loại.
MA_ALERT_DONG_SAI = (
    "UI_CORRELATE_HEURISTIC", "UI_CORRELATE_AMBIGUOUS", "UI_CORRELATE_TAG_OUT_OF_WINDOW",
    "CLOSING_HEURISTIC_PAIR", "CLOSE_TIMEOUT", "CLOSE_ACK_UNKNOWN",
    "CLOSING_MASTER_AFTER_OPEN_FAILURE",
)


def kiem_dong_sai(db: Database, ngay: str | None = None) -> dict[str, Any]:
    """Chẩn đoán "bên kia chốt sai" từ dữ liệu có sẵn. **Chỉ đọc.** `ngay` là ngày UTC `YYYY-MM-DD`.

    Ba câu hỏi, mỗi câu ứng với một cơ chế đã rà được trong code (2026-09-15):

    * `ghep_nham` — cặp bị gắn nhầm vị thế lúc MỞ: vị thế Client của cặp **không mang thẻ** của cặp.
      Mọi lần đóng về sau sẽ "đúng id" mà sai lệnh.
    * `dong_nham` — một deal đóng vị thế X nằm trong đúng cửa sổ của lệnh đóng nhắm Y, và không lệnh
      nào nhắm X. Người dùng đóng tay đúng lúc đó cũng ra hình dạng này, nên đây là **chỗ phải đọc
      log**, không phải kết luận.
    * `bao_dong_nham` — cặp `CLOSED` mà vị thế Client **không có deal đóng nào**: dấu hiệu clicker báo
      `already_closed` sai trong khi vị thế vẫn mở.
    """
    import json

    from bridge.clock import parse_iso

    def trong_ngay(cot: str) -> tuple[str, tuple[str, ...]]:
        return ("1 = 1", ()) if ngay is None else (f"substr({cot}, 1, 10) = ?", (ngay,))

    dk, ts = trong_ngay("created_at")
    alert = {r["code"]: r["n"] for r in db.query_all(
        f"SELECT code, COUNT(*) n FROM alert WHERE {dk} AND code IN "
        f"({', '.join('?' for _ in MA_ALERT_DONG_SAI)}) GROUP BY code",
        (*ts, *MA_ALERT_DONG_SAI))}

    # -- C: ghép nhầm lúc mở -----------------------------------------------------------------
    dk, ts = trong_ngay("p.created_at")
    ghep_nham: list[dict[str, Any]] = []
    for p in db.query_all(
            "SELECT p.pair_id, p.client_id, p.client_position_id, p.open_tag, ca.agent_id "
            "FROM pair p JOIN client_account ca ON ca.client_id = p.client_id "
            f"WHERE p.open_tag IS NOT NULL AND p.client_position_id IS NOT NULL AND {dk} "
            "ORDER BY p.pair_id", ts):
        mo = db.query_all(
            "SELECT payload_json FROM event WHERE agent_id = ? AND position_id = ? "
            "AND type = 'position_opened'", (p["agent_id"], p["client_position_id"]))
        if mo and not any(p["open_tag"] in (e["payload_json"] or "") for e in mo):
            ghep_nham.append(dict(p))

    # -- A: deal đóng một vị thế không lệnh nào nhắm tới -------------------------------------
    master_agent = db.query_one("SELECT agent_id FROM agent WHERE role = 'MASTER' LIMIT 1")
    clicker_master = db.get_config("master_clicker_agent_id", "") or ""
    clicker_cua_client = {r["clicker_agent_id"]: r["agent_id"] for r in db.query_all(
        "SELECT clicker_agent_id, agent_id FROM client_account WHERE clicker_agent_id IS NOT NULL")}

    def terminal_cua(dich: str) -> str:
        """Lệnh gửi cho clicker thì deal hiện ra trên terminal mà clicker đó lái."""
        if clicker_master and dich == clicker_master and master_agent is not None:
            return master_agent["agent_id"]
        return clicker_cua_client.get(dich, dich)

    dk, ts = trong_ngay("created_at")
    cua_so: list[dict[str, Any]] = []
    for c in db.query_all(
            "SELECT command_id, type, target_agent_id, payload_json, sent_at, acked_at, deadline_at "
            f"FROM command WHERE type LIKE 'CLOSE%' AND sent_at IS NOT NULL AND {dk}", ts):
        try:
            position_id = int(json.loads(c["payload_json"] or "{}")["position_id"])
        except (KeyError, TypeError, ValueError):
            continue
        tu = parse_iso(c["sent_at"]).timestamp() - CUA_SO_TRUOC_GUI_MS / 1000
        den = parse_iso(c["acked_at"] or c["deadline_at"] or c["sent_at"]).timestamp() \
            + CUA_SO_SAU_ACK_MS / 1000
        cua_so.append({"agent": terminal_cua(c["target_agent_id"]), "tu": tu, "den": den,
                       "position_id": position_id, "command_id": c["command_id"],
                       "type": c["type"]})

    dk, ts = trong_ngay("received_at")
    dong_nham: list[dict[str, Any]] = []
    for e in db.query_all(
            "SELECT event_id, agent_id, position_id, deal_entry, received_at, caused_by_command_id "
            f"FROM event WHERE deal_entry IN ({', '.join('?' for _ in DEAL_DONG)}) AND {dk} "
            "ORDER BY id", (*DEAL_DONG, *ts)):
        luc = parse_iso(e["received_at"]).timestamp()
        gan = [w for w in cua_so if w["agent"] == e["agent_id"] and w["tu"] <= luc <= w["den"]]
        if not gan or any(w["position_id"] == e["position_id"] for w in gan):
            continue
        dong_nham.append({**dict(e),
                          "lenh_gan": [(w["command_id"], w["type"], w["position_id"]) for w in gan]})

    # -- B: cặp CLOSED mà vị thế Client không có deal đóng nào -------------------------------
    dk, ts = trong_ngay("p.updated_at")
    bao_dong_nham: list[dict[str, Any]] = []
    for p in db.query_all(
            "SELECT p.pair_id, p.client_position_id, p.updated_at, ca.agent_id "
            "FROM pair p JOIN client_account ca ON ca.client_id = p.client_id "
            f"WHERE p.status = 'CLOSED' AND p.client_position_id IS NOT NULL AND {dk} "
            "ORDER BY p.pair_id", ts):
        co_deal = db.query_one(
            "SELECT 1 FROM event WHERE agent_id = ? AND position_id = ? AND deal_entry IN "
            f"({', '.join('?' for _ in DEAL_DONG)}) LIMIT 1",
            (p["agent_id"], p["client_position_id"], *DEAL_DONG))
        if co_deal is None:
            bao_dong_nham.append(dict(p))

    return {
        "ui_fallback_match": (db.get_config("ui_fallback_match", "STRICT") or "STRICT").upper(),
        "alert": alert,
        "ghep_nham": ghep_nham,
        "dong_nham": dong_nham,
        "bao_dong_nham": bao_dong_nham,
    }


def _da_giai_thich(pair: Any, cot: list[str]) -> bool:
    """Deal sai kênh này đã có lời giải thích kèm alert hay chưa.

    Cú **rơi về đường EA** khi clicker hỏng là hành vi cố ý, có alert CRITICAL
    `CLOSE_FELL_BACK_TO_EA` và có ghi vào `pair.error_message`. Deal đóng lần ấy mang `EXPERT`, và
    đó là **sự thật phải báo cáo** — nên nó vẫn nằm trong danh sách chứ không bị giấu đi.

    Nhưng nó không được tính là *thất bại*, và lý do rất thực tế: `pair` giữ giá trị ấy vĩnh viễn.
    Gộp chung thì sau **một** lần clicker hỏng, TEST-23 sẽ báo KHÔNG ĐẠT mãi mãi — và một tiêu chí
    không bao giờ đạt được là một tiêu chí không ai nhìn nữa. Quan sát được ở phiên nghiệm thu
    2026-09-10, ngay lần chạy đầu sau TEST-28.

    Chỉ giải thích được cho **vế đóng**. Một deal MỞ sai kênh thì không có đường rơi về nào hợp lệ
    (D-25 cấm), nên nó luôn là thất bại.
    """
    return (cot == ["client_close_reason"]
            and (pair["error_message"] or "") == "CLOSE_FELL_BACK_TO_EA")


# -- cấu hình nghiệp vụ ------------------------------------------------------------------------
#
# Phần dưới đây là **cùng một bộ ràng buộc** cho cả hai đường vào: `bridge.admin` và dashboard.
# Trước đó chúng nằm lẫn với `print` trong `admin.py`, nên tầng web không gọi lại được và lựa chọn
# duy nhất là viết lại — tức là sớm muộn hai đường vào sẽ kiểm khác nhau, và cái lỏng hơn mới là
# cái thật. Ở đây không có `print`: lỗi là `LoiCauHinh` mang một MÃ, người gọi tự dịch (CLI dịch
# sang câu không dấu, dashboard dịch qua `labels_vi.py` — D-16).


class LoiCauHinh(Exception):
    """Cấu hình bị từ chối. `ma` là mã ASCII, `ngu_canh` là dữ liệu để dựng câu thông báo."""

    def __init__(self, ma: str, **ngu_canh: Any) -> None:
        super().__init__(ma)
        self.ma = ma
        self.ngu_canh = ngu_canh


VAI_TRO_AGENT = ("MASTER", "CLIENT", "CLICKER")

#: Khoá `system_config` cho phép sửa, kèm miền giá trị. Cố ý **hẹp**: mọi khoá ở đây đều được đọc
#: lại mỗi lần dùng (nên đổi là có hiệu lực ngay, không cần khởi động lại), và đổi sai thì chỉ làm
#: hệ thống chậm hoặc ồn, không làm mất dữ liệu. `run_mode` có nút riêng; `event_retention_days`,
#: `heartbeat_*` và `ui_fallback_match` **không** ở đây vì đổi sai là mất dữ liệu hoặc mất an toàn.
KHOA_SUA_DUOC: dict[str, tuple[str, Any, Any]] = {
    "cascade_wait_master_ms": ("int", 1000, 120_000),
    "ui_open_queue_max_age_ms": ("int", 1000, 120_000),
    "ui_open_queue_max_len": ("int", 1, 200),
    "ui_close_correlate_grace_ms": ("int", 500, 60_000),
    "reconcile_interval_sec": ("int", 10, 3600),
    "finding_nhac_sau_phut": ("int", 0, 10_080),
    "close_degraded_fallback": ("enum", ("EA", "SKIP"), None),
}


def _agent_phai_co(db: Database, agent_id: str, can_role: str | None = None) -> Any:
    agent = db.get_agent(agent_id)
    if agent is None:
        raise LoiCauHinh("KHONG_CO_AGENT", agent_id=agent_id)
    if can_role is not None and agent["role"] != can_role:
        raise LoiCauHinh("SAI_ROLE", agent_id=agent_id, role=agent["role"], can=can_role)
    return agent


def tao_agent(db: Database, agent_id: str, role: str, magic: int,
              login: int | None = None) -> str:
    """Tạo agent mới và cấp token đầu tiên. Trả token thô **đúng một lần**.

    Gộp hai việc là có chủ đích: một agent không token là một dòng vô dụng trong bảng, và tách hai
    bước ra chính là chỗ người ta quên bước thứ hai.
    """
    if role not in VAI_TRO_AGENT:
        raise LoiCauHinh("ROLE_LA", role=role)
    if db.get_agent(agent_id) is not None:
        raise LoiCauHinh("AGENT_DA_TON_TAI", agent_id=agent_id)
    token = generate_token()
    db.upsert_agent(agent_id, role=role, token_hash=hash_token(token), magic_number=magic,
                    account_login=login)
    log.info("Da tao agent %s (%s)", agent_id, role, extra={"agent_id": agent_id})
    return token


def tao_client(db: Database, client_id: str, agent_id: str, clicker_agent: str | None = None,
               open_route: str = "UI", close_route: str | None = None,
               ten: str | None = None) -> dict[str, Any]:
    """Tạo dòng `client_account`. Trả về các giá trị đã dùng, để người gọi in ra.

    `clicker_agent_id` chỉ đặt được ở đây; `sua_client` không tạo dòng mới.
    """
    if db.get_client_account(client_id) is not None:
        raise LoiCauHinh("CLIENT_DA_TON_TAI", client_id=client_id)
    _agent_phai_co(db, agent_id, "CLIENT")
    # Mặc định theo `open_route`: một Client đặt đường giao diện để MỞ thì cũng đặt nó để ĐÓNG.
    close_route = close_route or open_route
    for truong, gia_tri in (("open_route", open_route), ("close_route", close_route)):
        if gia_tri not in ("EA", "UI"):
            raise LoiCauHinh("DUONG_LA", truong=truong, gia_tri=gia_tri)
        if gia_tri == "UI" and not clicker_agent:
            raise LoiCauHinh("CAN_CLICKER", truong=truong)
    if clicker_agent:
        _agent_phai_co(db, clicker_agent, "CLICKER")
    db.upsert_client_account(client_id, agent_id=agent_id, display_name=ten or client_id,
                             open_route=open_route, close_route=close_route,
                             clicker_agent_id=clicker_agent)
    log.info("Da tao client %s -> agent %s (open %s, close %s)",
             client_id, agent_id, open_route, close_route)
    return {"client_id": client_id, "agent_id": agent_id, "open_route": open_route,
            "close_route": close_route, "clicker_agent_id": clicker_agent}


def sua_client(db: Database, client_id: str, copy_mode: str | None = None,
               volume_multiplier: float | None = None, open_route: str | None = None,
               close_route: str | None = None,
               can_close_master: bool | None = None) -> tuple[dict[str, Any], int]:
    """Sửa cấu hình giao dịch của một Client. Trả về `(giá trị đã đổi, số cặp đang chạy)`.

    **Chỉ đổi lệnh MỚI** (D-19): cặp đang chạy lấy tỷ lệ của chính nó và không đọc bảng này.
    """
    client = db.get_client_account(client_id)
    if client is None:
        raise LoiCauHinh("KHONG_CO_CLIENT", client_id=client_id)

    doi: dict[str, Any] = {}
    if copy_mode is not None:
        if copy_mode not in ("SAME", "OPPOSITE"):
            raise LoiCauHinh("CHIEU_COPY_LA", gia_tri=copy_mode)
        doi["copy_mode"] = copy_mode
    if volume_multiplier is not None:
        if volume_multiplier <= 0:
            raise LoiCauHinh("HE_SO_KHONG_DUONG", gia_tri=volume_multiplier)
        doi["volume_multiplier"] = volume_multiplier
    # Cùng ràng buộc cho hai đường và vì cùng một lý do: bật đường giao diện mà không có clicker là
    # cấu hình vô nghĩa — lệnh không bao giờ gửi được đi đâu. Bảng chỉ có CHECK cho `open_route`
    # (`schema.sql`), nên `close_route` chỉ được canh ở đây.
    for truong, gia_tri in (("open_route", open_route), ("close_route", close_route)):
        if gia_tri is None:
            continue
        if gia_tri not in ("EA", "UI"):
            raise LoiCauHinh("DUONG_LA", truong=truong, gia_tri=gia_tri)
        if gia_tri == "UI" and not client["clicker_agent_id"]:
            raise LoiCauHinh("CAN_CLICKER", truong=truong)
        doi[truong] = gia_tri
    if can_close_master is not None:
        doi["can_close_master"] = 1 if can_close_master else 0

    if not doi:
        return {}, 0
    dang_mo = db.query_one(
        "SELECT COUNT(*) n FROM pair WHERE client_id = ? "
        "AND status NOT IN ('CLOSED','OPEN_FAILED')", (client_id,))["n"]
    # `clicker_agent_id` đi kèm dù không đổi: `upsert_client_account` dựng một câu UPSERT, và
    # SQLite kiểm `CHECK (open_route = 'EA' OR clicker_agent_id IS NOT NULL)` trên **dòng sắp
    # chèn**, không phải trên dòng sau khi gộp. Thiếu nó thì đổi `open_route` sang UI cho một
    # Client đã có clicker vẫn ném IntegrityError — lỗi có sẵn từ trước, lộ ra khi bấm nút trên
    # dashboard.
    db.upsert_client_account(client_id, agent_id=client["agent_id"],
                             clicker_agent_id=client["clicker_agent_id"], **doi)
    log.info("Doi cau hinh client %s: %s", client_id, doi)
    return doi, int(dang_mo)


def dat_duong_dong_master(db: Database, clicker_agent: str | None = None,
                          close_route: str | None = None) -> dict[str, Any]:
    """Đường ĐÓNG phía Master (D-21c).

    Master không có dòng `client_account` nào, nên hai giá trị này nằm ở `system_config`.
    """
    clicker_id = (db.get_config("master_clicker_agent_id", "") or "").strip()
    doi: dict[str, Any] = {}

    if clicker_agent is not None:
        _agent_phai_co(db, clicker_agent, "CLICKER")
        # Một clicker lái ĐÚNG MỘT terminal. Dùng chung clicker của Client cho Master nghĩa là hai
        # terminal khác nhau chung một tiến trình — bất khả, và nếu để lọt thì lệnh đóng Master sẽ
        # bấm vào cửa sổ của Client.
        trung = db.query_one("SELECT client_id FROM client_account WHERE clicker_agent_id = ?",
                             (clicker_agent,))
        if trung is not None:
            raise LoiCauHinh("CLICKER_DA_DUNG", agent_id=clicker_agent,
                             client_id=trung["client_id"])
        clicker_id = clicker_agent
        db.set_config("master_clicker_agent_id", clicker_id)
        doi["master_clicker_agent_id"] = clicker_id

    if close_route is not None:
        if close_route not in ("EA", "UI"):
            raise LoiCauHinh("DUONG_LA", truong="master_close_route", gia_tri=close_route)
        if close_route == "UI" and not clicker_id:
            raise LoiCauHinh("CAN_CLICKER_MASTER")
        db.set_config("master_close_route", close_route)
        doi["master_close_route"] = close_route
    if doi:
        log.info("Doi duong dong Master: %s", doi)
    return doi


def khai_anh_xa(db: Database, client_id: str, master_symbol: str, client_symbol: str) -> Any:
    """Khai ánh xạ symbol, **sau khi đối chiếu với sàn Client**. Trả về `symbol_spec` đã khớp.

    Thiếu ánh xạ thì `find_symbol_map` trả `None` và mọi lệnh Master bị bỏ qua trong im lặng, nên
    đây là bước không được quên. Còn tên symbol sai một ký tự (hoặc chứa ký tự Cyrillic nhìn giống
    chữ Latin) chỉ lộ ra đúng lúc có lệnh thật đi qua — vì vậy phải kiểm với spec sàn đẩy lên chứ
    không kiểm chính tả.
    """
    client = db.get_client_account(client_id)
    if client is None:
        raise LoiCauHinh("KHONG_CO_CLIENT", client_id=client_id)
    if not master_symbol or not client_symbol:
        raise LoiCauHinh("THIEU_SYMBOL")
    spec = db.get_symbol_spec(client["agent_id"], client_symbol)
    if spec is None:
        co = [r["symbol"] for r in db.query_all(
            "SELECT symbol FROM symbol_spec WHERE agent_id = ? ORDER BY symbol",
            (client["agent_id"],))]
        raise LoiCauHinh("SAN_KHONG_CO_SYMBOL", client_symbol=client_symbol, co=co)
    db.upsert_symbol_map(client_id, master_symbol, client_symbol, enabled=1,
                         verified_at=utc_now_iso())
    log.info("Anh xa %s: %s -> %s (da kiem tren san)", client_id, master_symbol, client_symbol)
    return spec


def tat_anh_xa(db: Database, client_id: str, master_symbol: str) -> None:
    """Tắt một ánh xạ. **Chỉ** đặt `enabled = 0`.

    Bản trước đi qua `upsert_symbol_map(..., client_symbol or "")`, nên tắt mà không truyền tên
    symbol phía Client sẽ ghi rỗng vào cột đó — bật lại là ánh xạ tới một symbol không tồn tại.
    """
    if db.query_one("SELECT 1 FROM symbol_map WHERE client_id = ? AND master_symbol = ?",
                    (client_id, master_symbol)) is None:
        raise LoiCauHinh("KHONG_CO_ANH_XA", master_symbol=master_symbol)
    with db.transaction() as conn:
        conn.execute("UPDATE symbol_map SET enabled = 0, updated_at = ? "
                     "WHERE client_id = ? AND master_symbol = ?",
                     (utc_now_iso(), client_id, master_symbol))
    log.warning("Da TAT anh xa %s cua %s", master_symbol, client_id)


def dat_terminal_clicker(db: Database, agent_id: str, login: int | None = None,
                         terminal_title: str | None = None) -> dict[str, Any]:
    """Khai terminal mà một clicker phải lái: số tài khoản và mẩu tiêu đề cửa sổ.

    Hai giá trị này từng nằm ở `config.toml`, nên đổi terminal là phải sửa file trên VPS rồi chạy
    lại tác vụ. Ở đây chúng nằm trong DB, clicker nhận lại ở lần bắt tay kế tiếp.

    Mẩu tiêu đề phải chứa **số tài khoản**: cửa sổ MT5 mở đầu tiêu đề bằng số tài khoản, và chính
    nó là thứ clicker đối chiếu trước khi bấm. Một mẩu tiêu đề không chứa số tài khoản (ví dụ
    "MetaTrader 5") khớp cả hai terminal, và khi đó clicker từ chối lái — hoặc tệ hơn, lái nhầm.
    """
    agent = _agent_phai_co(db, agent_id, "CLICKER")
    doi: dict[str, Any] = {}
    if login is not None:
        if login <= 0:
            raise LoiCauHinh("LOGIN_KHONG_DUONG", login=login)
        doi["account_login"] = login
    if terminal_title is not None:
        tieu_de = terminal_title.strip()
        so = doi.get("account_login") or agent["account_login"]
        if tieu_de and so and str(so) not in tieu_de:
            raise LoiCauHinh("TIEU_DE_KHONG_CO_SO_TK", tieu_de=tieu_de, login=so)
        doi["terminal_title"] = tieu_de
    if not doi:
        return {}
    dat = ", ".join(f"{k} = ?" for k in doi)
    with db.transaction() as conn:
        conn.execute(f"UPDATE agent SET {dat}, updated_at = ? WHERE agent_id = ?",
                     (*doi.values(), utc_now_iso(), agent_id))
    log.warning("Khai terminal cho clicker %s: %s", agent_id, doi, extra={"agent_id": agent_id})
    return doi


def xoa_anh_xa(db: Database, client_id: str, master_symbol: str) -> None:
    """Xoá hẳn một ánh xạ khỏi bảng.

    Khác `tat_anh_xa`: tắt thì dòng còn đó (bật lại là chạy, và vẫn nhìn thấy mình từng khai gì),
    xoá thì không còn dấu vết. Dùng khi một symbol thôi không copy nữa — để lại một danh sách đầy
    dòng đã tắt thì cái đang bật khó tìm ra giữa đám đó.

    **Cặp đang mở không bị ảnh hưởng:** đường đóng nhắm theo `position_id` chứ không tra bảng này
    (D-30), nên cặp đã mở vẫn đóng được bình thường. Cái mất là lệnh MỚI của symbol đó không còn
    được copy.
    """
    if db.query_one("SELECT 1 FROM symbol_map WHERE client_id = ? AND master_symbol = ?",
                    (client_id, master_symbol)) is None:
        raise LoiCauHinh("KHONG_CO_ANH_XA", master_symbol=master_symbol)
    with db.transaction() as conn:
        conn.execute("DELETE FROM symbol_map WHERE client_id = ? AND master_symbol = ?",
                     (client_id, master_symbol))
    log.warning("Da XOA anh xa %s cua %s", master_symbol, client_id)


def sua_khoa_he_thong(db: Database, khoa: str, gia_tri: Any) -> str:
    """Sửa một khoá `system_config` trong danh sách trắng. Trả về giá trị đã ghi."""
    if khoa not in KHOA_SUA_DUOC:
        raise LoiCauHinh("KHOA_NGOAI_DANH_SACH", khoa=khoa)
    kieu, a, b = KHOA_SUA_DUOC[khoa]
    if kieu == "enum":
        if gia_tri not in a:
            raise LoiCauHinh("GIA_TRI_LA", khoa=khoa, gia_tri=gia_tri)
        moi = str(gia_tri)
    else:
        try:
            so = int(gia_tri)
        except (TypeError, ValueError):
            raise LoiCauHinh("GIA_TRI_LA", khoa=khoa, gia_tri=gia_tri) from None
        if so < a or so > b:
            raise LoiCauHinh("NGOAI_MIEN", khoa=khoa, gia_tri=so, tu=a, den=b)
        moi = str(so)
    db.set_config(khoa, moi)
    log.info("Doi khoa he thong %s = %s", khoa, moi)
    return moi
