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
from bridge.config import KHOA_FILE_SUA_DUOC
from bridge.db.repo import Database
from bridge.engine.reconcile import Reconciler
from bridge.labels_vi import (
    AGENT_ROLE,
    AGENT_STATUS,
    ALERT_LEVEL,
    PAIR_STATUS,
    RUN_MODE,
    UI,
    label,
)
from bridge.ops import (
    KHOA_SUA_DUOC,
    cau_hinh_clicker,
    de_xuat_anh_xa,
    doc_tich_huong_dan,
    ma_client_ke_tiep,
    symbol_cua_agent,
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
    # `None` = agent khong bao (clicker, hoac EA ban cu). Hien "khong biet" chu khong hien
    # thanh "on" — day dung la loai trang thai ma dashboard khong duoc phep doan (B-09).
    if row["role"] != "CLICKER":
        mo_ta["trade_allowed"] = (None if row["trade_allowed"] is None
                                  else bool(row["trade_allowed"]))
        mo_ta["trade_allowed_label"] = UI["trade_allowed"]
        if row["trade_allowed"] == 0:
            mo_ta["canh_bao"] = UI["trade_not_allowed"]

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

    def _sai(tuyen: str, cot: str) -> bool:
        """Chỉ soi vế nào **thực sự** đi qua giao diện.

        Client bật đường mở nhưng chưa bật đường đóng thì deal đóng mang `EXPERT` là **đúng**
        cấu hình, không phải sự cố — gộp hai vế lại sẽ biến một cấu hình bình thường thành một
        ô đỏ trên dashboard, và ô đỏ báo oan thì lần sau không ai nhìn nữa.
        """
        return (client is not None and client[tuyen] == "UI" and row[cot] is not None
                and int(row[cot]) != REASON_CLIENT)

    sai_mo = _sai("open_route", "client_open_reason")
    sai_dong = _sai("close_route", "client_close_reason")
    sai_kenh = sai_mo or sai_dong
    nhan_sai = (UI["reason_mismatch"] if sai_mo and not sai_dong else
                UI["close_reason_mismatch"] if sai_dong and not sai_mo else
                UI["reason_mismatch_ca_hai"] if sai_kenh else None)

    return {
        "pair_id": row["pair_id"],
        "pair_short": row["pair_id"].rsplit("-", 1)[-1],
        "symbol": row["client_symbol"],
        "direction": f"{_chieu_master(row)}→{row['client_direction']}",
        "volume": f"{_so(row['master_current_volume'])} / {_so(row['client_current_volume'])}",
        "status": trang_thai,
        "status_label": nhan,
        "attention": trang_thai in CAN_CAN_THIEP,
        # Cặp đi qua giao diện mà `DEAL_REASON` khác CLIENT phải nổi bật: đó là dấu hiệu cơ
        # chế đổi kênh đã ngừng hoạt động, và nó im lặng nếu không có ô này.
        "reason_mismatch": sai_kenh,
        "reason_mismatch_label": nhan_sai,
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
        # JS không được tự suy ra hành động nào chạm MT5: danh sách đó thuộc về engine.
        "cham_mt5": Reconciler.cham_mt5(row["suggested_action"]),
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


# =============================================================================================
# "Cần làm" — cái gì còn thiếu để hệ thống copy được lệnh
# =============================================================================================
#
# Cài đặt nay chỉ còn một lệnh, và mọi cấu hình nghiệp vụ khai trên trang này (D-32). Nghĩa là
# **một bản cài xong vẫn có thể không copy được lệnh nào** — và trước khối này, cách duy nhất để
# biết là chạy `kiem-tra.ps1` trên VPS rồi tự đối chiếu chín mục với trí nhớ.
#
# Mỗi mục dưới đây là một cách hệ thống hỏng **trong im lặng** đã gặp thật:
#
# * Clicker chưa khai số tài khoản hay tiêu đề cửa sổ → clicker thoát mã 4 mỗi 60 giây, dashboard
#   trông bình thường, không lệnh nào được bấm.
# * Tiêu đề không chứa số tài khoản → hàng rào chống lái nhầm terminal thành vô hiệu.
# * Client không có ánh xạ symbol → **mọi** lệnh Master bị bỏ qua, chỉ còn một alert trong danh
#   sách dài.
# * Algo Trading tắt phía Client → lệnh đóng dự phòng (D-28) không chạy được.
#
# Thứ tự trong danh sách là thứ tự phải sửa: mục chặn nhiều nhất lên trước, `run_mode` xuống cuối
# vì nó là việc làm **sau khi** mọi thứ khác xanh.

#: Mức của một việc cần làm. `CHAN` = chắc chắn không copy được lệnh; `LUU_Y` = nên sửa.
MUC_CHAN = "CHAN"
MUC_LUU_Y = "LUU_Y"


def viec_can_lam(db: Database, config: Any = None) -> list[dict[str, Any]]:
    """Danh sách việc còn thiếu, đã sắp theo thứ tự nên sửa."""
    viec: list[dict[str, Any]] = []

    def them(muc: str, ma: str, chu: str) -> None:
        viec.append({"muc": muc, "ma": ma, "chu": chu})

    agents = [dict(r) for r in db.query_all("SELECT * FROM agent ORDER BY role, agent_id")]
    clients = [dict(r) for r in db.query_all(
        "SELECT * FROM client_account ORDER BY client_id")]

    if not agents:
        them(MUC_CHAN, "CHUA_CO_AGENT", UI["can_lam_chua_co_agent"])
    if not clients:
        them(MUC_CHAN, "CHUA_CO_CLIENT", UI["can_lam_chua_co_client"])

    # -- clicker: hai ô phải có, và tiêu đề phải chứa số tài khoản ------------------------------
    for a in agents:
        if a["role"] != "CLICKER" or not a["enabled"]:
            continue
        # Xét giá trị **có hiệu lực**, không phải cột trong DB: chưa ai khai thì Bridge suy từ EA
        # chạy trên chính terminal đó và gửi giá trị suy được xuống clicker. Bắt "chưa khai" ở đây
        # trong khi clicker vẫn chạy được là báo một việc không có thật.
        hieu_luc = cau_hinh_clicker(db, a["agent_id"])
        login = hieu_luc["login"]
        tieu_de = hieu_luc["tieu_de"]
        # Khai tay một đằng, EA báo một nẻo: clicker đang lái nhầm terminal, hoặc terminal vừa
        # đăng nhập sang tài khoản khác. Không tự chọn hộ — nêu cả hai con số.
        if (hieu_luc["nguon"] == "KHAI" and hieu_luc["login_suy"]
                and hieu_luc["login_suy"] != login):
            them(MUC_CHAN, "CLICKER_LECH_SO_TK",
                 UI["can_lam_clicker_lech"].format(
                     agent_id=a["agent_id"], khai=login, suy=hieu_luc["login_suy"],
                     tu_agent=hieu_luc["tu_agent"] or "?"))
        if not login or not tieu_de:
            them(MUC_CHAN, "CLICKER_CHUA_KHAI",
                 UI["can_lam_clicker_chua_khai"].format(agent_id=a["agent_id"]))
        elif str(login) not in tieu_de:
            # Số tài khoản phải nằm trong tiêu đề: đó là thứ clicker đối chiếu với cửa sổ thật ở
            # MỖI cú bấm. Lệch nhau thì clicker không bấm được gì — hoặc, nếu tiêu đề chung như
            # "MetaTrader 5", nó khớp cả terminal khác.
            them(MUC_CHAN, "TIEU_DE_KHONG_CHUA_SO_TK",
                 UI["can_lam_tieu_de_lech"].format(agent_id=a["agent_id"], login=login,
                                                   tieu_de=tieu_de))

    # -- agent chưa nối, hoặc terminal mất kết nối sàn -------------------------------------------
    for a in agents:
        if not a["enabled"]:
            continue
        if a["status"] == "ONLINE":
            continue
        them(MUC_CHAN, "AGENT_CHUA_ONLINE",
             UI["can_lam_agent_chua_online"].format(
                 agent_id=a["agent_id"], role=label(AGENT_ROLE, a["role"]),
                 status=label(AGENT_STATUS, a["status"])))

    # -- Algo Trading: lưới cuối của đường đóng (B-09) ------------------------------------------
    for a in agents:
        if a["role"] == "CLICKER" or not a["enabled"]:
            continue
        # `None` nghĩa là agent chưa báo (EA bản cũ), KHÁC hẳn "biết là tắt". Chỉ nói khi biết.
        if a["trade_allowed"] == 0:
            them(MUC_CHAN, "ALGO_TRADING_TAT",
                 UI["can_lam_algo_tat"].format(agent_id=a["agent_id"]))

    # -- từng Client: ánh xạ symbol và clicker --------------------------------------------------
    for c in clients:
        if not c["enabled"]:
            continue
        co_anh_xa = db.query_one(
            "SELECT 1 FROM symbol_map WHERE client_id = ? AND enabled = 1 LIMIT 1",
            (c["client_id"],))
        if co_anh_xa is None:
            them(MUC_CHAN, "THIEU_ANH_XA",
                 UI["can_lam_thieu_anh_xa"].format(client_id=c["client_id"]))
        if (c["open_route"] == "UI" or c["close_route"] == "UI") and not c["clicker_agent_id"]:
            them(MUC_CHAN, "CLIENT_THIEU_CLICKER",
                 UI["can_lam_client_thieu_clicker"].format(client_id=c["client_id"]))

    # -- đường đóng Master qua giao diện --------------------------------------------------------
    if (db.get_config("master_close_route", "EA") or "EA").upper() == "UI":
        clicker_master = (db.get_config("master_clicker_agent_id", "") or "").strip()
        if not clicker_master or db.get_agent(clicker_master) is None:
            them(MUC_CHAN, "MASTER_THIEU_CLICKER", UI["can_lam_master_thieu_clicker"])

    # -- cuối cùng: bật copy -------------------------------------------------------------------
    run_mode = db.get_config("run_mode", "PAUSED") or "PAUSED"
    if run_mode != "RUNNING":
        them(MUC_LUU_Y, "CHUA_BAT_COPY",
             UI["can_lam_chua_bat_copy"].format(run_mode=label(RUN_MODE, run_mode)))
    return viec


# =============================================================================================
# Trang "Hướng dẫn" — hai danh sách việc, từng bước, tự biết bước nào đã xong
# =============================================================================================
#
# Khối "Cần làm" nói **cái gì còn thiếu**. Nó không nói **thứ tự làm**, không chứa bước nào nằm
# ngoài tầm Bridge (gắn EA, bật Algo Trading, mở Toolbox), và không phân biệt **cài lần đầu** với
# **sau khi cập nhật** — hai việc có danh sách khác nhau hẳn. Trang này là chỗ cho cả ba điều đó.
#
# Ba quyết định đáng ghi lại:
#
# 1. **Không viết bộ luật thứ hai.** Mỗi bước tự kiểm được chỉ khai `ma_kiem` — mã của
#    `viec_can_lam` — và trạng thái suy ra từ đó. Hai bộ luật cho cùng một câu hỏi thì sớm muộn
#    lệch nhau, và lúc đó không ai biết bên nào đúng.
# 2. **Bước nào Bridge KHÔNG thấy được thì nói thẳng là tự tích**, không giả vờ kiểm. Ví dụ đắt
#    nhất: "đã biên dịch lại và gắn lại EA" — `hello` của EA **không mang phiên bản EA** (chỉ có
#    `terminal_build`, là của terminal), nên Bridge không thể phân biệt một EA vừa gắn lại với một
#    EA cũ vừa nối lại sau khi dịch vụ khởi động. Xem B-20.
# 3. **Ô tự tích nằm trong database**, không phải `localStorage`: nó phải sống sót khi đóng trình
#    duyệt, và phải **bị xoá** khi có lần cập nhật mới — một danh sách luôn xanh thì không ai đọc.

#: Trạng thái một bước.
BUOC_XONG = "XONG"
BUOC_CON_THIEU = "CON_THIEU"
BUOC_TU_TICH = "TU_TICH"

#: Hai nhóm việc.
NHOM_LAN_DAU = "LAN_DAU"
NHOM_SAU_UPDATE = "SAU_UPDATE"

#: Một bước: `(mã, khoá nhãn, mã kiểm của viec_can_lam, khoá câu lệnh)`.
#:
#: `ma_kiem` rỗng nghĩa là **tự tích**. `khoa_lenh` rỗng nghĩa là bước không có câu lệnh nào để
#: copy — phần lớn việc làm trên chính trang này hoặc trong MT5.
BUOC_LAN_DAU: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("LD_GAN_EA", "hd_ld_gan_ea", ("AGENT_CHUA_ONLINE", "CHUA_CO_AGENT"), ""),
    # `CHUA_CO_AGENT` đi kèm hai bước dưới đây vì thiếu nó thì phép kiểm thành **rỗng**: chưa có
    # clicker nào thì "mọi clicker đã khai xong" là đúng về logic và sai về sự thật — và một bước
    # báo Đã xong khi chưa ai làm gì là cách nhanh nhất để mất lòng tin vào cả danh sách.
    ("LD_KHAI_CLICKER", "hd_ld_khai_clicker",
     ("CHUA_CO_AGENT", "CLICKER_CHUA_KHAI", "TIEU_DE_KHONG_CHUA_SO_TK"), ""),
    ("LD_ALGO", "hd_ld_algo", ("CHUA_CO_AGENT", "ALGO_TRADING_TAT"), ""),
    ("LD_TOOLBOX", "hd_ld_toolbox", (), ""),
    ("LD_ANH_XA", "hd_ld_anh_xa", ("THIEU_ANH_XA", "CHUA_CO_CLIENT"), ""),
    ("LD_CAU_HINH_COPY", "hd_ld_cau_hinh_copy", (), ""),
    ("LD_BAT_COPY", "hd_ld_bat_copy", ("CHUA_BAT_COPY",), ""),
    ("LD_THU_DEMO", "hd_ld_thu_demo", (), "hd_lenh_kiem_demo"),
)

BUOC_SAU_UPDATE: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("UP_CTRL_F5", "hd_up_ctrl_f5", (), ""),
    ("UP_GAN_LAI_EA", "hd_up_gan_lai_ea", (), "hd_lenh_bien_dich"),
    ("UP_AGENT_ONLINE", "hd_up_agent_online", ("AGENT_CHUA_ONLINE",), "hd_lenh_liet_ke"),
    ("UP_CODE_CU", "hd_up_code_cu", (), "hd_lenh_kiem_tra"),
    ("UP_CONFIG_SOT", "hd_up_config_sot", ("CONFIG_CON_KHOA_CLICKER",), ""),
    ("UP_BAT_COPY", "hd_up_bat_copy", ("CHUA_BAT_COPY",), ""),
    ("UP_TINH_HINH", "hd_up_tinh_hinh", (), "hd_lenh_tinh_hinh"),
)

#: Mọi mã bước, để `ops.dat_tich_huong_dan` từ chối mã lạ.
MA_BUOC = tuple(b[0] for b in BUOC_LAN_DAU + BUOC_SAU_UPDATE)


def _buoc_ea_doi_moi_hien(ma: str, ea_doi: bool) -> bool:
    """`ea/` không đổi thì bước gắn lại EA **không** hiện ra.

    In một bước "biên dịch lại EA" ở mọi lần cập nhật là cách chắc chắn nhất để người ta bỏ qua nó
    đúng vào lần nó có thật.
    """
    return ma != "UP_GAN_LAI_EA" or ea_doi


def _mot_buoc(bo: tuple[str, str, tuple[str, ...], str], ma_thieu: set[str],
              da_tich: set[str]) -> dict[str, Any]:
    ma, khoa, ma_kiem, khoa_lenh = bo
    if ma_kiem:
        trang_thai = BUOC_CON_THIEU if (set(ma_kiem) & ma_thieu) else BUOC_XONG
    else:
        trang_thai = BUOC_TU_TICH
    return {
        "ma": ma,
        "chu": UI[khoa],
        "lenh": UI[khoa_lenh] if khoa_lenh else "",
        "trang_thai": trang_thai,
        "da_tich": ma in da_tich,
        # `tu_kiem` = Bridge tự biết bước này xong chưa. Giao diện dùng nó để quyết định hiện dấu
        # tích hay hiện ô cho người dùng tự tích — JS không được tự suy ra điều đó.
        "tu_kiem": bool(ma_kiem),
    }


def trang_huong_dan(db: Database, config: Any = None) -> dict[str, Any]:
    """Hai nhóm việc kèm trạng thái từng bước, và nhóm nào nên mở sẵn."""
    thieu = viec_can_lam(db, config)
    ma_thieu = {v["ma"] for v in thieu}
    # Khoá clicker còn sót trong `config.toml` **thắng** database (D-32), nên nó là một việc thật
    # sự còn thiếu — nhưng nó không nằm trong `viec_can_lam` vì chỉ trang Cấu hình đọc file. Lấy
    # từ cùng một nguồn mà khối config.toml dùng, để hai chỗ không bao giờ nói khác nhau.
    if any(d.get("chi_doc") for d in _mo_ta_file_config(config)):
        ma_thieu.add("CONFIG_CON_KHOA_CLICKER")

    da_tich = doc_tich_huong_dan(db)
    ea_doi = (db.get_config("cap_nhat_ea_doi", "0") or "0") == "1"
    moc = (db.get_config("moc_cap_nhat", "") or "").strip() or None

    lan_dau = [_mot_buoc(b, ma_thieu, da_tich) for b in BUOC_LAN_DAU]
    sau_update = [_mot_buoc(b, ma_thieu, da_tich) for b in BUOC_SAU_UPDATE
                  if _buoc_ea_doi_moi_hien(b[0], ea_doi)]

    def con_viec(buoc: list[dict[str, Any]]) -> bool:
        return any(b["trang_thai"] == BUOC_CON_THIEU
                   or (b["trang_thai"] == BUOC_TU_TICH and not b["da_tich"]) for b in buoc)

    def con_chan(buoc: list[dict[str, Any]]) -> bool:
        """Còn bước nào **Bridge tự kiểm được** mà chưa xong không.

        Khác `con_viec` ở hai chỗ, và cả hai đều cần thiết để chọn đúng nhóm:

        * **Không tính ô tự tích.** Ô không ai bấm thì chưa xong vĩnh viễn, và trang sẽ kẹt ở mục
          Lần đầu mãi mãi.
        * **Không tính `LD_BAT_COPY`.** `run_mode` về `PAUSED` sau **mỗi** lần khởi động lại
          (D-15), nên tính nó thì một máy đang chạy tốt vừa restart cũng bị coi là mới cài.
        """
        return any(b["trang_thai"] == BUOC_CON_THIEU and b["ma"] != "LD_BAT_COPY" for b in buoc)

    # Mở sẵn nhóm nào.
    #
    # Bản đầu hỏi "chưa có agent hoặc chưa có Client?" để nhận ra lần cài đầu — và nó **không bao
    # giờ đúng**: `tro-ly.ps1` tạo sẵn bốn agent và `CL-01` ngay trong lần cài, nên ngay khi cài
    # xong cả hai mã ấy đều vắng mặt và trang mở mục "Sau khi cập nhật" cho một máy vừa cài lần
    # đầu. Lỗi lộ ra ở đúng lần chạy thật đầu tiên.
    #
    # Câu hỏi đúng không phải "đã có agent chưa" mà là **"việc của lần cài đầu đã xong chưa"**:
    # chưa gắn EA, chưa khai clicker, chưa có ánh xạ symbol thì dù agent có tồn tại, đây vẫn là một
    # bản cài chưa dựng xong.
    if moc and con_viec(sau_update):
        che_do = NHOM_SAU_UPDATE
    elif con_chan(lan_dau):
        che_do = NHOM_LAN_DAU
    else:
        che_do = NHOM_SAU_UPDATE

    return {
        "che_do": che_do,
        "moc_cap_nhat": moc,
        "ea_doi": ea_doi,
        "nhom": [
            {"ma": NHOM_LAN_DAU, "ten": UI["hd_nhom_lan_dau"],
             "chu": UI["hd_nhom_lan_dau_chu"], "buoc": lan_dau},
            {"ma": NHOM_SAU_UPDATE, "ten": UI["hd_nhom_sau_update"],
             "chu": UI["hd_nhom_sau_update_chu"], "buoc": sau_update},
        ],
    }


def _agent_master(db: Database) -> str | None:
    dong = db.query_one("SELECT agent_id FROM agent WHERE role = 'MASTER' LIMIT 1")
    return str(dong["agent_id"]) if dong is not None else None


def trang_cau_hinh(db: Database, config: Any = None) -> dict[str, Any]:
    """Mọi thứ trang Cấu hình cần, trong một lượt đọc.

    Gộp bốn nhóm vào một endpoint chứ không tách bốn: trang này mở ra là để **so** chúng với nhau
    — một Client đặt `close_route = UI` mà clicker của nó chưa khai số tài khoản là một cấu hình
    hỏng, và chỉ nhìn thấy khi hai khối nằm cạnh nhau.
    """
    clients = [dict(r) for r in db.query_all("SELECT * FROM client_account ORDER BY client_id")]
    return {
        "agents": [_mo_ta_agent_cau_hinh(r) for r in db.query_all(
            "SELECT * FROM agent ORDER BY role, agent_id")],
        "clients": clients,
        "symbol_maps": [dict(r) for r in db.query_all(
            "SELECT * FROM symbol_map ORDER BY client_id, master_symbol")],
        "master": {
            "master_close_route": (db.get_config("master_close_route", "EA") or "EA").upper(),
            "master_clicker_agent_id": (db.get_config("master_clicker_agent_id", "") or "").strip(),
        },
        "he_thong": [
            {"khoa": khoa, "kieu": kieu, "tu": a, "den": b,
             "gia_tri": db.get_config(khoa, ""),
             "chon": list(a) if kieu == "enum" else None}
            for khoa, (kieu, a, b) in KHOA_SUA_DUOC.items()
        ],
        "ma_client_goi_y": ma_client_ke_tiep([c["client_id"] for c in clients]),
        # Danh sách symbol thật của hai bên, để hai ô gõ tay thành hai danh sách chọn. Gõ tay ở đây
        # hỏng theo kiểu tệ nhất: sai một ký tự thì không có lỗi nào, chỉ là mọi lệnh Master bị bỏ
        # qua trong im lặng.
        "symbol_master": symbol_cua_agent(db, _agent_master(db)),
        "symbol_client": {c["client_id"]: symbol_cua_agent(db, c["agent_id"]) for c in clients},
        "de_xuat_anh_xa": {c["client_id"]: de_xuat_anh_xa(db, c["client_id"]) for c in clients},
        "file_config": _mo_ta_file_config(config),
        # Theo TỪNG Client, không phải một bảng dùng chung. Bản cũ lấy `clients[0]`, nên với
        # hai Client khác hệ số thì khối CL-02 hiển thị con số của CL-01 — một bảng xem trước
        # nói sai chính là thứ tệ hơn không có bảng nào.
        "preview": {c["client_id"]: xem_truoc_he_so(c["volume_multiplier"]) for c in clients},
        # Đặt ngay trong endpoint này chứ không tách riêng: người mở trang Cấu hình cần thấy
        # "còn thiếu gì" **trước** khi cuộn qua tám khối cấu hình.
        "can_lam": viec_can_lam(db, config),
    }


def _mo_ta_agent_cau_hinh(row: Any) -> dict[str, Any]:
    return {
        "agent_id": row["agent_id"],
        "role": row["role"],
        "role_label": label(AGENT_ROLE, row["role"]),
        "status": row["status"],
        "status_label": label(AGENT_STATUS, row["status"]),
        "account_login": row["account_login"],
        "terminal_title": row["terminal_title"],
        "magic_number": row["magic_number"],
        "enabled": row["enabled"],
    }


def _mo_ta_file_config(config: Any) -> list[dict[str, Any]]:
    """Các khoá `config.toml` đang có hiệu lực. Sửa được, nhưng **chỉ có hiệu lực sau khi khởi
    động lại dịch vụ** — nhãn `cfg_file_restart` nói đúng điều đó trên trang.

    Giá trị bí mật **không bao giờ** đi qua JSON: chỉ báo có hay không. Biết `dashboard_password`
    đang trống là thông tin vận hành cần thiết, còn biết nó là gì thì không — và một mật khẩu đã
    đi ra khỏi tiến trình là một mật khẩu nằm trong cache trình duyệt.
    """
    if config is None:
        return []

    def _gia_tri(khoa: str) -> Any:
        muc, _, ten = khoa.rpartition(".")
        if muc == "bridge":
            return getattr(config.bridge, ten)
        return (getattr(config, muc, None) or {}).get(ten, "")

    dong = []
    for khoa, (kieu, bi_mat) in KHOA_FILE_SUA_DUOC.items():
        gia_tri = _gia_tri(khoa)
        dong.append({
            "khoa": khoa,
            "kieu": kieu,
            "bi_mat": bi_mat,
            # Bí mật: chỉ nói CÓ hay KHÔNG, không bao giờ nói là gì.
            "gia_tri": (UI["cfg_file_masked"] if gia_tri else "") if bi_mat else str(gia_tri or ""),
        })
    # Token của các mục clicker **ngoài hai mục có tên cố định** (`clicker_cl02`, …). Chúng
    # không nằm trong `KHOA_FILE_SUA_DUOC` vì tên do người vận hành đặt, nên phải lấy từ chính
    # file đang dùng — mỗi Client đi đường giao diện có một mục như vậy.
    cac_muc = dict(getattr(config, "clickers", None) or {})
    for muc in sorted(cac_muc):
        if f"{muc}.token" in KHOA_FILE_SUA_DUOC:
            continue
        dong.append({
            "khoa": f"{muc}.token", "kieu": "str", "bi_mat": True,
            "gia_tri": UI["cfg_file_masked"] if cac_muc[muc].get("token") else "",
        })
    # Hai khoá dưới đây không sửa ở đây: chúng đã chuyển vào database (D-32) và chỉ còn hiện ra
    # để người vận hành thấy bản cài cũ còn sót giá trị trong file — mà file thì THẮNG database.
    for muc in ("clicker", "clicker_master", *sorted(cac_muc)):
        for ten in ("account_login", "terminal_title"):
            gia_tri = (cac_muc.get(muc) or {}).get(ten, "")
            if gia_tri and not any(d["khoa"] == f"{muc}.{ten}" for d in dong):
                dong.append({"khoa": f"{muc}.{ten}", "kieu": "str", "bi_mat": False,
                             "chi_doc": True, "gia_tri": str(gia_tri)})
    return dong
