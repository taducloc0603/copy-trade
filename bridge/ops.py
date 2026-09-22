"""Việc vận hành: sao lưu, bảo trì hàng ngày, cấp và thu hồi token (plan mục 10.2, 10.3).

Ba thứ ở đây đều là loại "không ai nhớ tới cho tới lúc cần", nên chúng phải chạy tự động và
phải **kiểm chứng được**. Một bản sao lưu chưa từng khôi phục thử thì không phải bản sao lưu.
"""

from __future__ import annotations

import contextlib
import re
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

#: Giá trị **engine thật sự dùng** khi `system_config` chưa có khoá đó.
#:
#: `schema.sql` chỉ gieo hai trong bảy khoá trên, nên năm khoá còn lại chưa bao giờ nằm trong DB —
#: engine chạy bằng mặc định của chính nó, còn trang Cấu hình thì vẽ một **ô rỗng**. Một ô rỗng đọc
#: ra là "chưa đặt", và người vận hành không có cách nào biết hệ thống đang dùng số mấy.
#:
#: Để chúng ở ĐÂY, và bắt cả engine lẫn trang cùng đọc từ đây. Chép số ra hai chỗ là hai con số sẽ
#: lệch nhau, và lệch kiểu này thì im lặng: trang nói 15 giây, engine chờ 20, không ai sai rõ ràng.
MAC_DINH_KHOA: dict[str, Any] = {
    "cascade_wait_master_ms": 15_000,
    "ui_open_queue_max_age_ms": 15_000,
    "ui_open_queue_max_len": 20,
    "ui_close_correlate_grace_ms": 5_000,
    "reconcile_interval_sec": 60,
    "finding_nhac_sau_phut": 60,
    "close_degraded_fallback": "EA",
}


def gia_tri_khoa(db: Database, khoa: str) -> Any:
    """Giá trị **có hiệu lực** của một khoá `system_config`: đã lưu, hoặc mặc định của engine."""
    mac_dinh = MAC_DINH_KHOA[khoa]
    if isinstance(mac_dinh, int):
        return db.get_config_int(khoa, mac_dinh)
    return (db.get_config(khoa, mac_dinh) or mac_dinh)


def _clicker_con_trong(db: Database, clicker_agent: str, tru_client: str | None = None) -> None:
    """Một clicker lái ĐÚNG MỘT terminal, nên nó thuộc về đúng một Client (hoặc về Master).

    Không canh chỗ này thì `OPEN_UI` của Client B được bấm trên terminal của Client A hoặc của
    Master — tức là **mở lệnh trên tài khoản khác**, và không có gì trong sổ sách nói ra điều đó.
    """
    trung = db.query_one(
        "SELECT client_id FROM client_account WHERE clicker_agent_id = ? AND client_id <> ?",
        (clicker_agent, tru_client or ""))
    if trung is not None:
        raise LoiCauHinh("CLICKER_DA_DUNG", agent_id=clicker_agent, client_id=trung["client_id"])
    cua_master = (db.get_config("master_clicker_agent_id", "") or "").strip()
    if cua_master and cua_master == clicker_agent:
        raise LoiCauHinh("CLICKER_CUA_MASTER", agent_id=clicker_agent)


def _agent_client_con_trong(db: Database, agent_id: str, tru_client: str | None = None) -> None:
    """Một agent CLIENT (một terminal MT5) thuộc về đúng một dòng `client_account`.

    Hai dòng cùng trỏ vào một agent nghĩa là mỗi lệnh Master sinh **hai** lệnh mở trên cùng một
    terminal — nhân đôi volume một cách im lặng.
    """
    trung = db.query_one(
        "SELECT client_id FROM client_account WHERE agent_id = ? AND client_id <> ?",
        (agent_id, tru_client or ""))
    if trung is not None:
        raise LoiCauHinh("AGENT_DA_DUNG", agent_id=agent_id, client_id=trung["client_id"])


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
    if not agent_id.strip():
        raise LoiCauHinh("THIEU_MA")
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
    if not client_id.strip() or not agent_id.strip():
        raise LoiCauHinh("THIEU_MA")
    if db.get_client_account(client_id) is not None:
        raise LoiCauHinh("CLIENT_DA_TON_TAI", client_id=client_id)
    _agent_phai_co(db, agent_id, "CLIENT")
    _agent_client_con_trong(db, agent_id)
    # Mặc định theo `open_route`: một Client đặt đường giao diện để MỞ thì cũng đặt nó để ĐÓNG.
    close_route = close_route or open_route
    for truong, gia_tri in (("open_route", open_route), ("close_route", close_route)):
        if gia_tri not in ("EA", "UI"):
            raise LoiCauHinh("DUONG_LA", truong=truong, gia_tri=gia_tri)
        if gia_tri == "UI" and not clicker_agent:
            raise LoiCauHinh("CAN_CLICKER", truong=truong)
    if clicker_agent:
        _agent_phai_co(db, clicker_agent, "CLICKER")
        _clicker_con_trong(db, clicker_agent)
    db.upsert_client_account(client_id, agent_id=agent_id, display_name=ten or client_id,
                             open_route=open_route, close_route=close_route,
                             clicker_agent_id=clicker_agent)
    log.info("Da tao client %s -> agent %s (open %s, close %s)",
             client_id, agent_id, open_route, close_route)
    return {"client_id": client_id, "agent_id": agent_id, "open_route": open_route,
            "close_route": close_route, "clicker_agent_id": clicker_agent}


def sua_client(db: Database, client_id: str, copy_mode: str | None = None,
               volume_multiplier: float | None = None, open_route: str | None = None,
               close_route: str | None = None, can_close_master: bool | None = None,
               enabled: bool | None = None) -> tuple[dict[str, Any], int]:
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
    if enabled is not None:
        # Tắt một Client là **ngừng copy lệnh mới** cho nó, không đụng gì tới cặp đang mở: chúng
        # vẫn được đóng theo Master như thường. Đây là cách dừng một Client mà không mất lịch sử,
        # và là thứ nên dùng thay cho xoá.
        doi["enabled"] = 1 if enabled else 0

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
                         terminal_title: str | None = None) -> dict[str, Any]:  # noqa: D401
    """Khai terminal mà một clicker phải lái: số tài khoản và mẩu tiêu đề cửa sổ.

    Hai giá trị này từng nằm ở `config.toml`, nên đổi terminal là phải sửa file trên VPS rồi chạy
    lại tác vụ. Ở đây chúng nằm trong DB, clicker nhận lại ở lần bắt tay kế tiếp.

    Mẩu tiêu đề phải **mở đầu** bằng số tài khoản, không chỉ chứa nó ở đâu đó. Hai lý do, và cả
    hai đều đọc được trong `clicker/ui/probe.py`:

    * `account_login_from_title` lấy đúng **token đầu tiên** của tiêu đề cửa sổ và đòi nó toàn chữ
      số. Cửa sổ MT5 luôn mở đầu bằng số tài khoản, nên một mẩu như `"Connext 538216"` không bao
      giờ khớp được — mà phép kiểm cũ (`str(so) not in tieu_de`) lại **cho lưu** nó.
    * Mẩu tiêu đề là thứ dò bằng `in` trong tiêu đề thật, nên mọi ký tự thừa không có trên cửa sổ
      đều làm nó khớp **không gì cả**. Một tiêu đề `"538216 (2)"` cũng qua được phép kiểm cũ, rồi
      nằm im trong database cho tới lúc clicker báo canary đỏ không ai hiểu vì sao.

    Một mẩu không chứa số tài khoản (ví dụ `"MetaTrader 5"`) thì khớp cả hai terminal, và khi đó
    clicker từ chối lái — hoặc tệ hơn, lái nhầm.
    """
    agent = _agent_phai_co(db, agent_id, "CLICKER")
    doi: dict[str, Any] = {}
    if login is not None:
        if login <= 0:
            raise LoiCauHinh("LOGIN_KHONG_DUONG", login=login)
        doi["account_login"] = login
    if terminal_title is not None:
        doi["terminal_title"] = terminal_title.strip()

    # Kiểm **cặp giá trị sau khi sửa**, không chỉ cái vừa gõ: đổi riêng số tài khoản mà giữ tiêu đề
    # cũ cũng ra một cặp lệch, và cặp lệch nghĩa là clicker lái nhầm terminal.
    so = doi.get("account_login", agent["account_login"]) or 0
    tieu_de = doi.get("terminal_title", agent["terminal_title"]) or ""
    if doi and so and tieu_de and not tieu_de.startswith(str(so)):
        raise LoiCauHinh("TIEU_DE_KHONG_CO_SO_TK", tieu_de=tieu_de, login=so)
    if not doi:
        return {}
    dat = ", ".join(f"{k} = ?" for k in doi)
    with db.transaction() as conn:
        conn.execute(f"UPDATE agent SET {dat}, updated_at = ? WHERE agent_id = ?",
                     (*doi.values(), utc_now_iso(), agent_id))
    log.warning("Khai terminal cho clicker %s: %s", agent_id, doi, extra={"agent_id": agent_id})
    return doi


def xoa_client(db: Database, client_id: str) -> None:
    """Xoá hẳn một Client khỏi bảng.

    **Từ chối khi Client đã từng có cặp lệnh.** Khoá ngoại của `pair` trỏ vào đây, nên xoá đi là
    xoá luôn khả năng đọc lại lịch sử của những cặp đó — mà lịch sử là thứ duy nhất trả lời được
    "hôm ấy lệnh nào đã đi đâu" khi có tranh cãi về tiền. Muốn dừng một Client thì **tắt** nó:
    ngừng copy lệnh mới, giữ nguyên mọi thứ đã xảy ra.

    Ánh xạ symbol của Client thì đi theo (`ON DELETE CASCADE`) — chúng là cấu hình, không phải
    lịch sử.
    """
    if db.get_client_account(client_id) is None:
        raise LoiCauHinh("KHONG_CO_CLIENT", client_id=client_id)
    so_cap = db.query_one("SELECT COUNT(*) n FROM pair WHERE client_id = ?", (client_id,))["n"]
    if so_cap:
        raise LoiCauHinh("CLIENT_CON_LICH_SU", client_id=client_id, so_cap=int(so_cap))
    with db.transaction() as conn:
        conn.execute("DELETE FROM client_account WHERE client_id = ?", (client_id,))
    log.warning("Da XOA client %s", client_id)


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


# -- đặt lại hệ thống (D-33) --------------------------------------------------------------------
#
# Hai mức, vì chúng trả lời hai câu hỏi khác nhau:
#
# * **Đặt lại dữ liệu** — "sổ sách đang bẩn vì mấy lượt thử, tôi muốn bắt đầu đếm lại". Xoá lịch
#   sử giao dịch, giữ nguyên agent, client, ánh xạ symbol và khoá hệ thống, nên hệ thống chạy tiếp
#   ngay sau đó.
# * **Đặt lại toàn bộ** — "tôi muốn cấu hình lại từ đầu". Xoá thêm client, ánh xạ và các khoá hệ
#   thống (về mặc định). **Agent và token được giữ**: xoá chúng nghĩa là phải dán lại token vào cả
#   hai EA trong giao diện MT5, một việc tay chân chỉ để dọn sổ sách.
#
# Ba hàng rào cho cả hai mức, và không mức nào bỏ được:
#
# 1. **Sao lưu trước.** Một lệnh xoá không có đường lùi thì không phải lệnh vận hành.
# 2. **Không xoá khi còn cặp đang mở hoặc vị thế Master đang mở.** Xoá sổ sách trong lúc tiền còn
#    nằm trên sàn là cách chắc chắn nhất để không ai biết còn gì đang mở.
# 3. **Không xoá khi còn lệnh chưa xong** (`PENDING`/`SENT`) và **phải đang `PAUSED`**: xoá giữa
#    lúc một lệnh đang bay để lại một ack không còn chỗ để ghi.

#: Bảng lịch sử giao dịch, **theo đúng thứ tự xoá được** (khoá ngoại đang bật). `ui_open_queue`
#: trỏ vào `event`, `event` trỏ vào `pair`, `pair` trỏ vào `master_position` — xoá ngược thứ tự này
#: là SQLite từ chối, và từ chối giữa chừng nghĩa là xoá một nửa.
BANG_LICH_SU = (
    "ui_open_queue",
    "reconcile_finding",
    "alert",
    "event",
    "command",
    "pair",
    "pair_id_seq",
    "master_position",
    "symbol_spec",
)

#: Bảng cấu hình, cũng theo thứ tự xoá được. `agent` **không** có ở đây: giữ agent là giữ token,
#: và giữ token là không phải đụng vào giao diện MT5.
BANG_CAU_HINH = ("symbol_map", "client_account")


def _chan_dat_lai(db: Database) -> None:
    """Ba hàng rào chung của cả hai mức đặt lại."""
    che_do = (db.get_config("run_mode", "PAUSED") or "PAUSED").upper()
    if che_do != "PAUSED":
        raise LoiCauHinh("DAT_LAI_CAN_PAUSED", run_mode=che_do)

    dang_mo = db.query_one(
        "SELECT COUNT(*) n FROM pair WHERE status NOT IN ('CLOSED', 'OPEN_FAILED')")["n"]
    vi_the = db.query_one("SELECT COUNT(*) n FROM master_position WHERE status = 'OPEN'")["n"]
    if dang_mo or vi_the:
        raise LoiCauHinh("DAT_LAI_CON_DANG_MO", so_cap=int(dang_mo), so_vi_the=int(vi_the))

    dang_bay = db.query_one(
        "SELECT COUNT(*) n FROM command WHERE status IN ('PENDING', 'SENT')")["n"]
    if dang_bay:
        raise LoiCauHinh("DAT_LAI_CON_LENH_BAY", so_lenh=int(dang_bay))


def _xoa_bang(db: Database, bang: tuple[str, ...]) -> dict[str, int]:
    """Xoá sạch các bảng trong **một** giao dịch. Trả về số dòng đã xoá của từng bảng."""
    da_xoa: dict[str, int] = {}
    with db.transaction() as conn:
        for ten in bang:
            cur = conn.execute(f"DELETE FROM {ten}")  # noqa: S608 - tên bảng là hằng trong file này
            if cur.rowcount > 0:
                da_xoa[ten] = int(cur.rowcount)
    return da_xoa


def _gieo_lai_system_config(db: Database) -> None:
    """Đặt lại `system_config` về đúng mặc định khai trong `schema.sql` và các migration.

    Lấy thẳng các câu `INSERT OR IGNORE INTO system_config` trong file SQL thay vì chép danh sách
    khoá vào đây: chép là tạo bản sao thứ hai của sự thật, và bản sao đó sẽ lệch ở lần thêm khoá
    tiếp theo. `run_mode` vì vậy cũng về `PAUSED` — đúng D-15.
    """
    from bridge.db.migrations import SCHEMA_PATH, discover_migrations, split_statements

    def _bo_chu_thich(cau: str) -> str:
        """Bỏ các dòng chú thích ở đầu câu lệnh.

        `split_statements` giữ nguyên khối chú thích đứng trước mỗi câu, nên so khớp thẳng vào
        đầu chuỗi sẽ bỏ sót đúng những câu có chú thích — tức là gần hết.
        """
        dong = [d for d in cau.splitlines() if d.strip() and not d.strip().startswith("--")]
        return "\n".join(dong)

    cau_gieo: list[str] = []
    nguon = [SCHEMA_PATH.read_text(encoding="utf-8")]
    nguon += [m.read_sql() for m in discover_migrations()]
    for sql in nguon:
        for cau in split_statements(sql):
            than = _bo_chu_thich(cau)
            if than.upper().startswith("INSERT OR IGNORE INTO SYSTEM_CONFIG"):
                cau_gieo.append(than)
    if not cau_gieo:
        # Không tìm thấy câu gieo nào nghĩa là `schema.sql` đã đổi cách viết — dừng lại thay vì
        # để `system_config` trống, vì trống nghĩa là mọi giá trị rơi về mặc định trong code và
        # `run_mode` không còn dòng nào trong bảng.
        raise LoiCauHinh("KHONG_TIM_THAY_MAC_DINH")

    with db.transaction() as conn:
        conn.execute("DELETE FROM system_config")
        for cau in cau_gieo:
            conn.execute(cau)


def dat_lai_lich_su(db: Database, db_path: Path | None = None) -> dict[str, Any]:
    """Xoá lịch sử giao dịch, **giữ nguyên cấu hình**. Trả về số dòng đã xoá và bản sao lưu.

    Sau lệnh này hệ thống chạy tiếp được ngay: agent, client, ánh xạ symbol và mọi khoá hệ thống
    còn nguyên, chỉ là sổ sách trống.
    """
    _chan_dat_lai(db)
    # Mặc định sao lưu **đúng database đang mở**, không phải đường dẫn khai trong `config.toml`:
    # hai thứ đó lệch nhau là bản sao lưu nằm ở một thư mục khác với database vừa bị xoá.
    ban_sao = sao_luu(db, db_path or db.path)
    da_xoa = _xoa_bang(db, BANG_LICH_SU)
    log.warning("DAT LAI du lieu: %s (ban sao luu %s)", da_xoa, ban_sao.name)
    return {"da_xoa": da_xoa, "ban_sao": ban_sao.name}


def dat_lai_toan_bo(db: Database, db_path: Path | None = None) -> dict[str, Any]:
    """Xoá lịch sử **và** cấu hình nghiệp vụ, đưa khoá hệ thống về mặc định.

    **Agent và token được giữ lại.** Xoá chúng chỉ để dọn sổ sách là tự bắt mình mở giao diện MT5
    dán lại token cho cả hai EA — việc tay chân duy nhất trong cả quy trình cài đặt, và là chỗ dễ
    sai nhất. Muốn xoá cả agent thì `thu-hoi` rồi `them-agent` lại, có chủ đích từng cái một.
    """
    _chan_dat_lai(db)
    # Mặc định sao lưu **đúng database đang mở**, không phải đường dẫn khai trong `config.toml`:
    # hai thứ đó lệch nhau là bản sao lưu nằm ở một thư mục khác với database vừa bị xoá.
    ban_sao = sao_luu(db, db_path or db.path)
    da_xoa = _xoa_bang(db, BANG_LICH_SU + BANG_CAU_HINH)
    _gieo_lai_system_config(db)
    log.warning("DAT LAI toan bo: %s (ban sao luu %s)", da_xoa, ban_sao.name)
    return {"da_xoa": da_xoa, "ban_sao": ban_sao.name}


# =============================================================================================
# Trang Hướng dẫn: ô tự tích, và biên nhận của lần cập nhật
# =============================================================================================
#
# Vài bước trong hướng dẫn Bridge **không thể** tự kiểm — gắn EA lên chart, bấm `Ctrl+F5`, mở
# Toolbox ở tab Trade. Chúng cần một ô người dùng tự tích, và ô đó phải:
#
# * **sống sót khi đóng trình duyệt** → nằm trong `system_config`, không phải `localStorage`;
# * **bị xoá khi có lần cập nhật mới** → nếu không, ô tích của tháng trước làm danh sách trông như
#   đã xong, và một danh sách luôn xanh thì không ai đọc nữa.

#: Khoá `system_config` giữ danh sách mã bước đã tích, phân cách bằng dấu phẩy.
KHOA_TICH = "huong_dan_da_tich"
#: Biên nhận lần cập nhật gần nhất, do `cai-dat.ps1 -CapNhat` ghi.
KHOA_MOC_CAP_NHAT = "moc_cap_nhat"
KHOA_EA_DOI = "cap_nhat_ea_doi"
KHOA_TU_COMMIT = "cap_nhat_tu_commit"


def doc_tich_huong_dan(db: Database) -> set[str]:
    """Các mã bước đã được tích."""
    tho = db.get_config(KHOA_TICH, "") or ""
    return {m.strip() for m in tho.split(",") if m.strip()}


def dat_tich_huong_dan(db: Database, ma: str, tich: bool) -> set[str]:
    """Bật/tắt một ô tích. Trả về tập mã sau khi đổi.

    Từ chối mã lạ: một ô tích không ứng với bước nào là một dòng rác trong `system_config` mà không
    ai biết để dọn.
    """
    # Import tại chỗ: `views` đã import `ops`, nên import ngược ở đầu file là một vòng.
    from bridge.web.views import MA_BUOC

    if ma not in MA_BUOC:
        raise LoiCauHinh("MA_BUOC_LA", ma_buoc=ma)
    da = doc_tich_huong_dan(db)
    if tich:
        da.add(ma)
    else:
        da.discard(ma)
    db.set_config(KHOA_TICH, ",".join(sorted(da)))
    return da


def ghi_moc_cap_nhat(db: Database, ea_doi: bool, tu_commit: str = "") -> dict[str, Any]:
    """Ghi biên nhận của một lần cập nhật, và **xoá sạch** ô tích cũ.

    `cai-dat.ps1 -CapNhat` gọi hàm này qua `bridge.admin ghi-moc-cap-nhat`. Nó là thứ duy nhất cho
    dashboard biết "vừa có một lần cập nhật": Bridge không ghi lại phiên bản code nào, và
    `agent.last_seen_at` không phân biệt được "EA vừa gắn lại" với "EA nối lại vì dịch vụ khởi
    động" — mà mỗi lần `-CapNhat` đều khởi động lại dịch vụ.
    """
    moc = utc_now_iso()
    db.set_config(KHOA_MOC_CAP_NHAT, moc)
    db.set_config(KHOA_EA_DOI, "1" if ea_doi else "0")
    db.set_config(KHOA_TU_COMMIT, (tu_commit or "").strip()[:40])
    db.set_config(KHOA_TICH, "")
    log.warning("Ghi moc cap nhat %s (ea_doi=%s, tu %s), da xoa o tich cua huong dan",
                moc, ea_doi, tu_commit or "(khong ro)")
    return {"moc_cap_nhat": moc, "ea_doi": ea_doi}


# =============================================================================================
# Cấu hình của một clicker: suy từ chính EA đang chạy trên terminal đó
# =============================================================================================
#
# Clicker của `CL-01` lái **đúng cái terminal** mà EA của `CL-01` đang chạy — đó là topology duy
# nhất hệ thống này hỗ trợ (một terminal = một EA + một clicker). Mà EA thì tự khai số tài khoản ở
# **mỗi lần bắt tay**. Nên bắt người vận hành gõ lại con số ấy là hỏi một thứ hệ thống đã biết, và
# còn biết chính xác hơn: con số của EA đến từ terminal đang đăng nhập tài khoản đó, con số gõ tay
# đến từ trí nhớ.
#
# Ba điều cố ý:
#
# 1. **Tính lúc đọc, không ghi vào DB.** Ghi xuống thì một giá trị không ai gõ sẽ trông như đã gõ,
#    và lần sau terminal đăng nhập sang tài khoản khác thì DB nói sai mà không ai biết.
# 2. **Khai tay vẫn thắng.** Có người đã gõ thì dùng cái đã gõ (`nguon = "KHAI"`). Đè lên lựa chọn
#    của người vận hành là thứ không được phép làm im lặng.
# 3. **Lệch thì không tự chọn hộ.** `viec_can_lam` nêu cả hai con số và để người quyết — lệch nghĩa
#    là clicker đang lái nhầm terminal, hoặc terminal vừa đổi tài khoản. Cả hai đều đắt.
#
# Hàng rào cũ không đổi: clicker vẫn đối chiếu số Bridge giao với số đọc từ **cửa sổ thật** ở mỗi
# cú bấm (D-32). Suy từ EA chỉ làm nguồn của con số ấy đáng tin hơn.

#: Tiêu đề cửa sổ mặc định = chính số tài khoản.
#:
#: Không phải phỏng đoán: `clicker/ui/probe.py::account_login_from_title` đọc số tài khoản từ
#: **đầu** tiêu đề cửa sổ MT5, nên `str(login)` luôn là một mẩu khớp hợp lệ, và là mẩu hẹp nhất.
def _tieu_de_mac_dinh(login: int) -> str:
    return str(login) if login else ""


def agent_cung_terminal(db: Database, agent_id: str) -> str | None:
    """Agent EA chạy trên **cùng terminal** với clicker này, hoặc `None` nếu clicker chưa được gán.

    Hai đường gán, và chỉ hai: clicker của một Client (`client_account.clicker_agent_id`) và clicker
    lái terminal Master (`system_config.master_clicker_agent_id`).
    """
    dong = db.query_one(
        "SELECT agent_id FROM client_account WHERE clicker_agent_id = ? LIMIT 1", (agent_id,))
    if dong is not None:
        return str(dong["agent_id"])
    if (db.get_config("master_clicker_agent_id", "") or "").strip() == agent_id:
        master = db.query_one("SELECT agent_id FROM agent WHERE role = 'MASTER' LIMIT 1")
        if master is not None:
            return str(master["agent_id"])
    return None


def cau_hinh_clicker(db: Database, agent_id: str) -> dict[str, Any]:
    """Số tài khoản và tiêu đề cửa sổ mà clicker này phải dùng, kèm **nguồn** của chúng.

    Trả về `{login, tieu_de, nguon, tu_agent, login_suy}`:

    * `nguon = "KHAI"` — có người khai tay, dùng cái đó.
    * `nguon = "SUY"`  — suy từ EA cùng terminal.
    * `nguon = "CHUA_CO"` — chưa gán clicker cho ai, hoặc EA kia chưa bao giờ nối.

    `login_suy` luôn là con số suy được (0 nếu không suy được), để chỗ gọi so với `login` mà phát
    hiện lệch — hàm này **không** tự quyết khi lệch.
    """
    agent = db.get_agent(agent_id)
    if agent is None or agent["role"] != "CLICKER":
        raise LoiCauHinh("SAI_ROLE", agent_id=agent_id, can="CLICKER")

    tu_agent = agent_cung_terminal(db, agent_id)
    ea = db.get_agent(tu_agent) if tu_agent else None
    login_suy = int(ea["account_login"] or 0) if ea is not None else 0

    khai_login = int(agent["account_login"] or 0)
    khai_tieu_de = (agent["terminal_title"] or "").strip()
    if khai_login or khai_tieu_de:
        return {"login": khai_login or login_suy,
                "tieu_de": khai_tieu_de or _tieu_de_mac_dinh(khai_login or login_suy),
                "nguon": "KHAI", "tu_agent": tu_agent, "login_suy": login_suy}
    if login_suy:
        return {"login": login_suy, "tieu_de": _tieu_de_mac_dinh(login_suy),
                "nguon": "SUY", "tu_agent": tu_agent, "login_suy": login_suy}
    return {"login": 0, "tieu_de": "", "nguon": "CHUA_CO", "tu_agent": tu_agent, "login_suy": 0}


# =============================================================================================
# Đề xuất ánh xạ symbol
# =============================================================================================
#
# `symbol_spec` đã chứa **toàn bộ Market Watch** của cả Master lẫn từng Client, do EA đẩy lên sau
# mỗi lần bắt tay và mỗi 6 giờ. Nên hai ô gõ tay tên symbol là hỏi một thứ hệ thống đã biết — và
# gõ tay ở đây hỏng theo kiểu tệ nhất: sai một ký tự thì không có lỗi nào cả, chỉ là **mọi lệnh
# Master bị bỏ qua trong im lặng**.
#
# Đề xuất chứ **không tự tạo**: chọn sai symbol không báo lỗi, nó chỉ copy sang một thị trường
# khác. Việc đó phải có người bấm.

def symbol_cua_agent(db: Database, agent_id: str | None) -> list[dict[str, Any]]:
    """Danh sách symbol một agent đã đẩy lên, kèm thông số đủ để phân biệt bản micro."""
    if not agent_id:
        return []
    return [{"symbol": r["symbol"], "digits": r["digits"], "contract_size": r["contract_size"],
             "volume_min": r["volume_min"], "volume_step": r["volume_step"]}
            for r in db.query_all(
                "SELECT symbol, digits, contract_size, volume_min, volume_step "
                "FROM symbol_spec WHERE agent_id = ? ORDER BY symbol", (agent_id,))]


def _diem_ung_vien(master: dict[str, Any], client: dict[str, Any]) -> tuple[int, int]:
    """Điểm của một ứng viên: càng nhỏ càng khớp. `(hạng tên, phạt khác thông số)`.

    Hạng tên: 0 trùng hẳn, 1 tên Client nối thêm hậu tố (`XAUUSD` → `XAUUSDm`, `XAUUSD.s`),
    2 ngược lại, 3 không liên quan.
    """
    m, c = master["symbol"].upper(), client["symbol"].upper()
    if m == c:
        hang = 0
    elif c.startswith(m):
        hang = 1
    elif m.startswith(c):
        hang = 2
    else:
        hang = 3
    # `digits` và `contract_size` là thứ phân biệt XAUUSD với bản micro. Khác nhau không loại bỏ
    # ứng viên — nhiều sàn khai khác nhau hợp lệ — nhưng đẩy nó xuống sau.
    phat = int(master["digits"] != client["digits"]) + \
           int((master["contract_size"] or 0) != (client["contract_size"] or 0))
    return hang, phat


def de_xuat_anh_xa(db: Database, client_id: str) -> list[dict[str, Any]]:
    """Cặp symbol đề xuất cho một Client: mỗi symbol Master một ứng viên tốt nhất.

    Bỏ qua symbol đã có ánh xạ. Không có ứng viên nào đủ gần thì **không đề xuất** — một đề xuất
    sai còn tệ hơn không có, vì nó được bấm mà không ai đọc kỹ.
    """
    client = db.get_client_account(client_id)
    if client is None:
        return []
    master = db.query_one("SELECT agent_id FROM agent WHERE role = 'MASTER' LIMIT 1")
    ds_master = symbol_cua_agent(db, master["agent_id"] if master else None)
    ds_client = symbol_cua_agent(db, client["agent_id"])
    if not ds_master or not ds_client:
        return []

    da_co = {r["master_symbol"] for r in db.query_all(
        "SELECT master_symbol FROM symbol_map WHERE client_id = ?", (client_id,))}

    ket: list[dict[str, Any]] = []
    for m in ds_master:
        if m["symbol"] in da_co:
            continue
        ung_vien = [(( *_diem_ung_vien(m, c),), c) for c in ds_client]
        ung_vien = [(d, c) for d, c in ung_vien if d[0] < 3]
        if not ung_vien:
            continue
        ung_vien.sort(key=lambda x: (x[0], len(x[1]["symbol"])))
        (hang, phat), c = ung_vien[0]
        ket.append({"master_symbol": m["symbol"], "client_symbol": c["symbol"],
                    "chac_chan": hang == 0 and phat == 0})
    return ket


# =============================================================================================
# Thêm một Client: một lệnh, sinh đủ mọi thứ đi kèm
# =============================================================================================
#
# Thêm `CL-02` trước đây là **năm** việc rời nhau, làm đúng thứ tự mới chạy: tạo agent CLIENT, tạo
# agent CLICKER, khai token clicker vào `config.toml`, tạo dòng `client_account`, rồi đăng ký tác
# vụ trên VPS. Bốn việc đầu đều là suy ra được từ một con số — số thứ tự của Client — nên bắt gõ
# tên cho từng thứ chỉ tạo cơ hội đặt lệch nhau (`AG-CLIENT2` với mục `[clicker_cl_02]`).
#
# Việc thứ năm **không tự động hoá được từ trình duyệt**: đăng ký Scheduled Task cần quyền
# Administrator trên VPS. Nên hàm này trả về đúng câu lệnh đó để người dùng dán chạy.

#: Magic mặc định cho agent tạo từ dashboard.
#:
#: EA **ghi đè** giá trị này ở lần bắt tay đầu tiên (`server.py` lấy `hello.magic`), và không chỗ
#: nào trong Bridge so magic giữa các agent — nó chỉ được đóng dấu lên lệnh đi đường EA rồi chính
#: EA đó kiểm lại. Hỏi người dùng con số này không mua được gì.
MAGIC_MAC_DINH = 770001


def ma_client_ke_tiep(da_co: list[str]) -> str:
    """Mã client tiếp theo theo đúng dãy `CL-01`, `CL-02`, …

    Gợi ý chứ không ép: ô vẫn sửa được. Nhưng để trống rồi bắt người ta tự nghĩ ra mã là cách chắc
    chắn có ngày xuất hiện `CL2`, `cl-02` và `CL-2` trong cùng một bảng — mà mã này đi vào mọi lệnh
    `bridge.admin`, tên agent, tên mục clicker và tên Scheduled Task về sau.
    """
    so = {int(m.group(1)) for m in (re.fullmatch(r"CL-(\d+)", str(c)) for c in da_co) if m}
    return f"CL-{(max(so) + 1) if so else 1:02d}"


def ten_theo_client(client_id: str) -> dict[str, str]:
    """Mọi cái tên đi kèm một Client, sinh từ chính mã của nó.

    `CL-02` → agent `AG-CL02`, clicker `AG-CLICKER-CL02`, mục `[clicker_cl02]` trong `config.toml`,
    tác vụ `ClickerCl02`, log `clicker_cl02.log`. Một quy tắc, một chỗ — để cái tên trong database,
    trong `config.toml` và trong Task Scheduler không bao giờ lệch nhau.
    """
    gon = client_id.replace("-", "").upper()          # CL-02 -> CL02
    muc = f"clicker_{gon.lower()}"                    # clicker_cl02
    return {
        "agent": f"AG-{gon}",
        "clicker": f"AG-CLICKER-{gon}",
        "muc_clicker": muc,
        "tac_vu": "Clicker" + "".join(p.capitalize() for p in muc.split("_")[1:]),
        "log": f"{muc}.log",
    }


def tao_client_moi(db: Database) -> dict[str, Any]:
    """Tạo một Client mới cùng hai agent của nó. Trả về **cả hai token** (hiện đúng một lần).

    **Chỉ chạm database.** Việc ghi `config.toml` nằm ở chỗ gọi, vì hai lý do khác nhau và cả hai
    đều thật: `sua_config_toml` đọc/ghi file và gọi `icacls` nên phải chạy ở luồng khác để không
    giữ vòng sự kiện của Bridge; mà `sqlite3` thì **chỉ dùng được trong đúng luồng đã tạo kết nối**.
    Gộp hai thứ vào một hàm rồi bọc trong `asyncio.to_thread` là cách chắc chắn nhận
    `SQLite objects created in a thread can only be used in that same thread` — đã gặp thật.

    Chỗ gọi phải dọn bằng `huy_client_moi` nếu bước ghi file hỏng: một Client có agent mà không có
    token clicker trong `config.toml` là thứ chỉ lộ ra lúc clicker không khởi động được.
    """
    da_co = [str(r["client_id"]) for r in db.query_all("SELECT client_id FROM client_account")]
    client_id = ma_client_ke_tiep(da_co)
    ten = ten_theo_client(client_id)

    for ma in (ten["agent"], ten["clicker"]):
        if db.get_agent(ma) is not None:
            raise LoiCauHinh("AGENT_DA_TON_TAI", agent_id=ma)

    da_tao: list[str] = []
    try:
        token_ea = tao_agent(db, ten["agent"], "CLIENT", MAGIC_MAC_DINH, None)
        da_tao.append(ten["agent"])
        token_clicker = tao_agent(db, ten["clicker"], "CLICKER", MAGIC_MAC_DINH, None)
        da_tao.append(ten["clicker"])
        tao_client(db, client_id, ten["agent"], ten["clicker"], open_route="UI")
    except Exception:
        huy_client_moi(db, client_id, da_tao)
        raise

    log.warning("Da tao %s (%s, %s)", client_id, ten["agent"], ten["clicker"])
    # `token_clicker` đi thẳng vào `config.toml` ở chỗ gọi và **không bao giờ** ra tới trình duyệt:
    # clicker đọc nó từ file, còn một token đi qua JSON là một token nằm trong cache trình duyệt.
    return {"client_id": client_id, "token_ea": token_ea, "token_clicker": token_clicker, **ten}


def huy_client_moi(db: Database, client_id: str, agent_ids: list[str]) -> None:
    """Dọn một lần tạo Client hỏng giữa chừng.

    Nửa vời ở đây nghĩa là lần bấm sau đâm vào "agent đã tồn tại" mà không ai hiểu vì sao — và mã
    Client kế tiếp thì đã bị một dòng rác chiếm mất.
    """
    with contextlib.suppress(Exception), db.transaction() as conn:
        conn.execute("DELETE FROM client_account WHERE client_id = ?", (client_id,))
        for ma in agent_ids:
            conn.execute("DELETE FROM agent WHERE agent_id = ?", (ma,))
