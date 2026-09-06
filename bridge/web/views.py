"""Lắp dữ liệu cho dashboard: đọc DB, gắn nhãn tiếng Việt, sắp xếp, tính chỉ số.

Tách khỏi `app.py` để test được mà không cần dựng server HTTP. Cũng là ranh giới giữ cho tầng
web đúng vai: **chỉ hiển thị và gọi API của `bridge/engine/`**. Nếu ở đây xuất hiện một câu SQL
cập nhật `pair`, đó là dấu hiệu sai — quay lại dùng hàm ở tầng engine.

Mọi chuỗi tiếng Việt lấy từ `bridge/labels_vi.py` (D-16). JavaScript nhận chữ đã dịch sẵn và
không chứa nhãn nào, nên thêm một ngôn ngữ hay đổi cách gọi một khái niệm chỉ sửa một chỗ.
"""

from __future__ import annotations

import json
from typing import Any

from bridge.clock import parse_iso
from bridge.db.repo import Database
from bridge.labels_vi import (
    AGENT_STATUS,
    ALERT_LEVEL,
    PAIR_STATUS,
    RUN_MODE,
    UI,
    label,
)

#: Thứ tự nghiêm trọng của trạng thái cặp. Số nhỏ lên trước.
#:
#: **Sắp theo mức nghiêm trọng, không theo thời gian.** Khi có 40 cặp và 2 cặp mất hedge, sắp
#: theo thời gian sẽ chôn hai cặp cần cứu xuống giữa danh sách — đúng lúc cần thấy chúng nhất.
THU_TU_NGHIEM_TRONG = {
    "ORPHANED": 0,
    "OPEN_FAILED": 1,
    "CLOSING": 2,
    "PARTIALLY_CLOSED": 3,
    "PENDING_OPEN": 4,
    "OPEN": 5,
}

#: Trạng thái tính vào ô "cần can thiệp".
CAN_CAN_THIEP = frozenset({"ORPHANED", "OPEN_FAILED"})

#: `DEAL_REASON_CLIENT`. Cặp mở qua giao diện mà khác giá trị này là dấu hiệu phase 6b đã ngừng
#: hoạt động — không phải một sai lệch giao dịch thông thường.
REASON_CLIENT = 0


def trang_thai_chung(db: Database, server: Any = None) -> dict[str, Any]:
    """Thanh trạng thái: chế độ vận hành và tình hình từng agent."""
    mode = db.get_config("run_mode", "PAUSED") or "PAUSED"
    agents = []
    for row in db.query_all("SELECT * FROM agent WHERE enabled = 1 ORDER BY role, agent_id"):
        agents.append(_mo_ta_agent(row))
    return {
        "run_mode": mode,
        "run_mode_label": label(RUN_MODE, mode),
        "agents": agents,
    }


def _mo_ta_agent(row: Any) -> dict[str, Any]:
    """Một dòng agent trên thanh trạng thái.

    Với role `CLICKER`, `broker_connected = false` mang nghĩa khác hẳn: **không điều khiển được
    giao diện** (D-25). Kèm thời điểm canary chạy thành công gần nhất — một clicker `ONLINE`
    nhưng canary đã cũ vài phút là dấu hiệu sắp hỏng, và đó chính là loại trạng thái "trông vẫn
    khoẻ" mà `broker_connected` sinh ra để bắt.
    """
    trang_thai = row["status"]
    mo_ta = {
        "agent_id": row["agent_id"],
        "role": row["role"],
        "status": trang_thai,
        "status_label": label(AGENT_STATUS, trang_thai),
        "broker_connected": bool(row["broker_connected"]),
    }
    if row["role"] == "CLICKER":
        # Cùng một enum, nghĩa khác. Nhãn phải nói đúng thứ người vận hành cần hiểu.
        if trang_thai == "DEGRADED":
            mo_ta["status_label"] = "Không điều khiển được giao diện"
        mo_ta["canary_label"] = UI["canary_last_ok"]
        mo_ta["canary_at"] = row["last_seen_at"] if row["broker_connected"] else None
        mo_ta["canary_never"] = UI["canary_never"]
    return mo_ta


def chi_so(db: Database) -> dict[str, Any]:
    """Bốn ô chỉ số.

    Độ trễ copy là khoảng cách từ lúc Master khớp tới lúc Client khớp — không phải độ trễ mạng.
    Đó mới là con số quy ra tiền. Dùng **phân vị trong phiên** chứ không phải giá trị tức thời:
    một lần trễ 3 giây trong 200 lệnh là dấu hiệu cần điều tra, nhưng nhìn giá trị hiện tại thì
    nó đã trôi qua từ lâu.
    """
    do_tre = []
    for row in db.query_all(
        "SELECT open_time_master, open_time_client FROM pair "
        "WHERE open_time_master IS NOT NULL AND open_time_client IS NOT NULL "
        "ORDER BY pair_id DESC LIMIT 500"
    ):
        ms = _khoang_cach_ms(row["open_time_master"], row["open_time_client"])
        if ms is not None and ms >= 0:
            do_tre.append(ms)

    dang_hedge = db.query_one(
        "SELECT COUNT(*) n FROM pair WHERE status IN ('OPEN', 'PARTIALLY_CLOSED')")["n"]
    can_can_thiep = db.query_one(
        "SELECT COUNT(*) n FROM pair WHERE status IN ('ORPHANED', 'OPEN_FAILED')")["n"]

    return {
        "p50": _phan_vi(do_tre, 50),
        "p95": _phan_vi(do_tre, 95),
        "p50_label": UI["metric_p50"],
        "p95_label": UI["metric_p95"],
        "hedged": dang_hedge,
        "hedged_label": UI["metric_hedged"],
        "attention": can_can_thiep,
        "attention_label": UI["metric_attention"],
        # Chỉ tô đỏ khi khác 0. Nếu luôn đỏ, mắt sẽ quen và bỏ qua.
        "attention_alarm": can_can_thiep > 0,
        "mau": len(do_tre),
    }


def bang_cap_lenh(db: Database) -> list[dict[str, Any]]:
    """Bảng cặp lệnh, đã sắp theo mức nghiêm trọng.

    **Không có cột lãi lỗ.** Đây là công cụ đồng bộ hedge, không phải terminal giao dịch. Số P&L
    đã có sẵn trong MT5, và đưa lên đây chỉ mời gọi can thiệp tay vào những cặp đang chạy đúng.
    """
    rows = db.query_all(
        "SELECT * FROM pair WHERE status NOT IN ('CLOSED') ORDER BY pair_id DESC LIMIT 200")
    ket_qua = [_mo_ta_cap(db, r) for r in rows]
    ket_qua.sort(key=lambda c: (THU_TU_NGHIEM_TRONG.get(c["status"], 9), c["pair_id"]))
    return ket_qua


def _mo_ta_cap(db: Database, row: Any) -> dict[str, Any]:
    trang_thai = row["status"]
    nhan = label(PAIR_STATUS, trang_thai)
    if trang_thai == "ORPHANED":
        # Hành động xử lý hai trường hợp khác hẳn nhau, nên nhãn phải nói rõ bên nào còn vị thế.
        nhan = (UI["orphan_master_left"] if row["orphan_side"] == "MASTER"
                else UI["orphan_client_left"])

    client = db.get_client_account(row["client_id"])
    qua_giao_dien = client is not None and client["open_route"] == "UI"
    sai_kenh = (qua_giao_dien and row["client_open_reason"] is not None
                and int(row["client_open_reason"]) != REASON_CLIENT)

    return {
        "pair_id": row["pair_id"],
        "pair_short": row["pair_id"].rsplit("-", 1)[-1],
        "symbol": row["client_symbol"],
        "direction": f"{_chieu_master(row)}→{row['client_direction']}",
        "volume": f"{_so(row['master_current_volume'])} / {_so(row['client_current_volume'])}",
        "status": trang_thai,
        "status_label": nhan,
        "attention": trang_thai in CAN_CAN_THIEP,
        # Cặp mở qua giao diện mà `client_open_reason` khác CLIENT phải nổi bật: đó là dấu hiệu
        # cơ chế của phase 6b đã ngừng hoạt động.
        "reason_mismatch": sai_kenh,
        "reason_mismatch_label": UI["reason_mismatch"] if sai_kenh else None,
    }


def _chieu_master(row: Any) -> str:
    return "SELL" if row["client_direction"] == "BUY" and row["copy_mode"] == "OPPOSITE" else (
        "BUY" if row["copy_mode"] == "OPPOSITE" else row["client_direction"])


def danh_sach_sai_lech(db: Database) -> dict[str, Any]:
    """Màn hình xử lý sai lệch, tách theo **mức an toàn** chứ không theo loại lỗi.

    Lấy **mọi** finding đang `PENDING`, không phải finding của lần chạy gần nhất. Bộ đối chiếu
    có cổng lọc trùng, nên một sai lệch đã ghi ở vòng trước sẽ không xuất hiện lại trong `run_id`
    mới — lọc theo `run_id` sẽ giấu mất chính những dòng chưa ai xử lý.
    """
    safe, decision = [], []
    for row in db.list_findings(resolution="PENDING"):
        muc = _mo_ta_sai_lech(row)
        (safe if row["severity"] == "SAFE" else decision).append(muc)
    return {
        "safe": safe,
        "decision": decision,
        "safe_label": UI["findings_safe"],
        "decision_label": UI["findings_decision"],
        "tong": len(safe) + len(decision),
    }


def _mo_ta_sai_lech(row: Any) -> dict[str, Any]:
    """Một dòng sai lệch, kèm **cả ba nguồn** bằng chứng.

    Người vận hành đang quyết định chuyện tiền bạc. Đưa cho họ một dòng "Cặp 118 bất thường" là
    bắt họ tin bot một cách mù quáng.
    """
    bang_chung = {}
    try:
        bang_chung = json.loads(row["evidence_json"] or "{}")
    except json.JSONDecodeError:
        pass
    return {
        "id": row["id"],
        "kind": row["kind"],
        "severity": row["severity"],
        "pair_id": row["pair_id"],
        "suggested_action": row["suggested_action"],
        "evidence": {
            "db_label": UI["evidence_db"],
            "db": bang_chung.get("db"),
            "master_label": UI["evidence_master"],
            "master": bang_chung.get("master"),
            "client_label": UI["evidence_client"],
            "client": bang_chung.get("client"),
        },
    }


def nhat_ky(db: Database, level: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    sql = "SELECT * FROM alert WHERE acknowledged_at IS NULL"
    params: list[Any] = []
    if level:
        sql += " AND level = ?"
        params.append(level)
    rows = db.query_all(sql + " ORDER BY id DESC LIMIT ?", (*params, limit))
    return [{
        "id": r["id"],
        "level": r["level"],
        "level_label": label(ALERT_LEVEL, r["level"]),
        "code": r["code"],
        "message": r["message"],
        "pair_id": r["pair_id"],
        "created_at": r["created_at"],
    } for r in rows]


def xem_truoc_he_so(multiplier: float, volume_min: float = 0.01,
                    volume_step: float = 0.01) -> list[str]:
    """Dòng xem trước cho ô hệ số volume, **kèm cả trường hợp thất bại**.

    Nhìn trường hợp đẹp thì ai cũng thấy ổn; chỉ khi thấy dòng thứ hai người ta mới nhận ra hệ
    số 0.50 sẽ làm rơi mọi lệnh nhỏ.
    """
    from decimal import Decimal

    from bridge.engine.sizing import round_to_step

    dong = []
    # Dung thang `round_to_step` cua engine chu khong viet lai phep lam tron o day: mot ban xem
    # truoc lech voi thu engine that su lam con te hon la khong co xem truoc.
    for master in ("1.00", "0.01"):
        thô = Decimal(master) * Decimal(str(multiplier))
        lam_tron = round_to_step(thô, Decimal(str(volume_step)), "DOWN")
        if lam_tron < Decimal(str(volume_min)):
            dong.append(f"Master {master} → {thô.normalize()}, "
                        f"dưới mức tối thiểu {volume_min} → bỏ qua lệnh")
        else:
            dong.append(f"Master {master} → Client {lam_tron.normalize()}")
    return dong


# -- tiện ích ---------------------------------------------------------------------------------

def _phan_vi(mau: list[int], p: int) -> int | None:
    if not mau:
        return None
    sap = sorted(mau)
    vi_tri = max(0, min(len(sap) - 1, round((p / 100) * len(sap) + 0.5) - 1))
    return sap[vi_tri]


def _khoang_cach_ms(dau: str | None, cuoi: str | None) -> int | None:
    if not dau or not cuoi:
        return None
    try:
        return int((parse_iso(cuoi) - parse_iso(dau)).total_seconds() * 1000)
    except ValueError:
        return None


def _so(gia_tri: Any) -> str:
    if gia_tri is None:
        return "—"
    return f"{float(gia_tri):.2f}"
