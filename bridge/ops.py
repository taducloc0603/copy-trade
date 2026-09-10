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
        raise ValueError(f"Khong co agent {agent_id}")
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
        "SELECT pair_id, client_id, client_position_id, status, "
        "       client_open_reason, client_close_reason "
        "FROM pair WHERE (client_open_reason IS NOT NULL AND client_open_reason <> ?) "
        "           OR (client_close_reason IS NOT NULL AND client_close_reason <> ?) "
        "ORDER BY pair_id", (REASON_CLIENT, REASON_CLIENT))
    vi_pham = []
    for r in rows:
        cot = [ten for ten in ("client_open_reason", "client_close_reason")
               if r[ten] is not None and r[ten] != REASON_CLIENT]
        vi_pham.append({**dict(r), "cot": ", ".join(cot)})
    if vi_pham:
        log.error("TEST-23 KHONG DAT: %d cap co deal Client sai kenh", len(vi_pham))
    return vi_pham
