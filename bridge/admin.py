"""Công cụ vận hành dòng lệnh: ``python -m bridge.admin <lệnh>``.

Tồn tại vì một lý do cụ thể. Từ phase 3 tới phase 9, mọi việc cấp agent và cấp token đều làm
bằng script tạm viết ra scratchpad rồi vứt đi. Món nợ đó đã **cắn thật**: token của clicker mất
theo scratchpad của một phiên trước và phải cấp lại. Việc vận hành thường xuyên phải là một
lệnh có tên, không phải một đoạn code viết lại mỗi lần.

Token thô chỉ in ra màn hình **đúng một lần** và không đi vào log — `bridge/logging_setup.py`
có bộ lọc che, nhưng cách chắc chắn nhất là không bao giờ ghi nó xuống.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from bridge.clock import to_iso
from bridge.config import load_config
from bridge.db.repo import Database
from bridge.ops import (
    VAI_TRO_AGENT,
    LoiCauHinh,
    bao_tri_hang_ngay,
    cap_token,
    dat_duong_dong_master,
    dat_lai_lich_su,
    dat_lai_toan_bo,
    dat_terminal_clicker,
    doi_login_agent,
    ghi_moc_cap_nhat,
    khai_anh_xa,
    kiem_chung_ban_sao_luu,
    kiem_reason_client,
    kiem_reason_master,
    sao_luu,
    sua_client,
    tao_agent,
    tao_client,
    tat_anh_xa,
    thu_hoi_token,
    thu_muc_sao_luu,
    xoa_anh_xa,
    xoa_client,
)

VAI_TRO = VAI_TRO_AGENT

#: Mã lỗi của `ops.LoiCauHinh` → câu in ra dòng lệnh. Chỗ duy nhất trong CLI dựng câu cho người
#: đọc; dashboard dịch **cùng những mã này** sang tiếng Việt có dấu qua `labels_vi.py` (D-16). Một
#: mã đi hai đường ra, nhưng chỉ có một chỗ kiểm — đó là mục đích của cả lần tách này.
CAU_LOI: dict[str, str] = {
    "AGENT_DA_TON_TAI": "Agent {agent_id} da ton tai. Dung `cap-token` neu chi muon doi token.",
    "KHONG_CO_AGENT": "Khong co agent {agent_id}",
    "SAI_ROLE": "Agent {agent_id} co role {role}, can {can}.",
    "ROLE_LA": "Role {role} khong hop le.",
    "LOGIN_KHONG_DUONG": "So tai khoan phai duong, nhan duoc {login}",
    "CLIENT_DA_TON_TAI": "Client {client_id} da ton tai. Dung `cau-hinh-client` de sua.",
    "KHONG_CO_CLIENT": "Khong co client {client_id}",
    "CLIENT_CON_LICH_SU": ("{client_id} da co {so_cap} cap lenh nen khong xoa duoc. "
                           "Dung: cau-hinh-client {client_id} --hoat-dong tat"),
    "CAN_CLICKER": "{truong} = UI can clicker_agent_id. Tao client kem --clicker-agent.",
    "CAN_CLICKER_MASTER": ("master_close_route = UI can master_clicker_agent_id, chua co. "
                           "Dat kem --clicker-agent."),
    "CLICKER_DA_DUNG": ("Agent {agent_id} dang la clicker cua Client {client_id}. "
                        "Moi terminal can mot clicker rieng."),
    "CLICKER_CUA_MASTER": ("Agent {agent_id} dang la clicker lai terminal Master. Dung chung la "
                           "lenh cua Client se duoc bam tren terminal Master."),
    "AGENT_DA_DUNG": ("Agent {agent_id} dang la agent cua Client {client_id}. Mot terminal MT5 "
                      "chi thuoc ve mot Client."),
    "THIEU_MA": "Thieu ma. Dien ma client hoac ten agent.",
    "DAT_LAI_CAN_PAUSED": "Dang o che do {run_mode}. Dat run-mode PAUSED truoc khi dat lai.",
    "DAT_LAI_CON_DANG_MO": ("Con {so_cap} cap va {so_vi_the} vi the Master dang mo. Dong het "
                            "roi hay dat lai."),
    "DAT_LAI_CON_LENH_BAY": "Con {so_lenh} lenh chua xong. Cho chung xong roi hay dat lai.",
    "CUM_TU_SAI": "Go chua dung cum xac nhan.",
    "KIEU_DAT_LAI_LA": "Kieu dat lai {kieu} khong hop le.",
    "MA_BUOC_LA": "Khong co buoc huong dan nao ma {ma_buoc}.",
    "HANH_DONG_CHAM_MT5": "{hanh_dong} la hanh dong gui lenh xuong MT5.",
    "KHONG_TIM_THAY_MAC_DINH": "Khong tim thay cau gieo mac dinh trong schema.sql.",
    "HE_SO_KHONG_DUONG": "volume_multiplier phai duong, nhan duoc {gia_tri}",
    "CHIEU_COPY_LA": "copy_mode {gia_tri} khong hop le (SAME hoac OPPOSITE).",
    "DUONG_LA": "{truong} = {gia_tri} khong hop le (EA hoac UI).",
    "THIEU_SYMBOL": "Thieu symbol phia Client. Vi du: --client-symbol XAUUSDm",
    "KHONG_CO_ANH_XA": "Khong co anh xa cho {master_symbol}",
    "SAN_KHONG_CO_SYMBOL": "San Client chua bao co symbol {client_symbol!r}.",
    "KHOA_NGOAI_DANH_SACH": "Khoa {khoa} khong sua duoc bang lenh nay.",
    "GIA_TRI_LA": "Gia tri {gia_tri!r} khong hop le cho {khoa}.",
    "NGOAI_MIEN": "{khoa} phai trong khoang {tu}..{den}, nhan duoc {gia_tri}",
}


def _in_loi(exc: LoiCauHinh) -> int:
    """In câu tương ứng mã lỗi rồi trả mã thoát 1."""
    mau = CAU_LOI.get(exc.ma, exc.ma)
    print(mau.format(**exc.ngu_canh), file=sys.stderr)
    if exc.ma == "SAN_KHONG_CO_SYMBOL":
        # Tên symbol sai là lỗi gõ nhầm chứ không phải lỗi hệ thống, nên câu báo phải nói luôn
        # cách tự kiểm và liệt kê những gì sàn đang báo có — thiếu hai dòng này thì người cài
        # ngồi đoán.
        print("Kiem: EA Client dang chay chua, va symbol da duoc keo vao Market Watch chua.",
              file=sys.stderr)
        if exc.ngu_canh.get("co"):
            print("San Client dang bao co: " + ", ".join(exc.ngu_canh["co"]), file=sys.stderr)
    return 1


def _mo_db() -> tuple[Database, Path]:
    config = load_config()
    return Database(config.db_path), config.db_path


def lenh_liet_ke(db: Database, _args: argparse.Namespace) -> int:
    rows = db.query_all("SELECT agent_id, role, status, account_login, enabled FROM agent "
                        "ORDER BY role, agent_id")
    if not rows:
        print("Chua co agent nao.")
        return 0
    print(f"{'agent_id':<20} {'role':<8} {'status':<10} {'login':>10}  bat")
    for r in rows:
        print(f"{r['agent_id']:<20} {r['role']:<8} {r['status']:<10} "
              f"{r['account_login'] or '':>10}  {'x' if r['enabled'] else '-'}")
    return 0


def lenh_them_agent(db: Database, args: argparse.Namespace) -> int:
    """Tạo agent mới và cấp token đầu tiên trong cùng một bước.

    Gộp hai việc lại là có chủ đích: một agent không token là một dòng vô dụng trong bảng, và
    tách hai bước ra chính là chỗ người ta quên bước thứ hai.
    """
    try:
        token = tao_agent(db, args.agent_id, args.role, args.magic, args.login)
    except LoiCauHinh as exc:
        return _in_loi(exc)
    print(f"Da tao agent {args.agent_id} ({args.role}).")
    _in_token(args.agent_id, token)
    return 0


def _in_token(agent_id: str, token: str) -> None:
    print()
    print(f"  TOKEN cua {agent_id} (chi hien MOT lan, khong ghi log, khong doc lai duoc):")
    print(f"  {token}")
    print()
    print("  Dat vao tham so EA (hoac muc clicker trong config.toml) ngay bay gio.")


def lenh_cap_token(db: Database, args: argparse.Namespace) -> int:
    try:
        token = cap_token(db, args.agent_id)
    except LoiCauHinh as exc:
        return _in_loi(exc)
    print(f"Da cap token moi cho {args.agent_id}. Token cu het hieu luc ngay lap tuc.")
    _in_token(args.agent_id, token)
    return 0


def lenh_thu_hoi(db: Database, args: argparse.Namespace) -> int:
    if not thu_hoi_token(db, args.agent_id):
        print(f"Khong co agent {args.agent_id}", file=sys.stderr)
        return 1
    print(f"Da thu hoi token cua {args.agent_id}. Agent nay khong ket noi lai duoc nua.")
    return 0


def lenh_sua_agent(db: Database, args: argparse.Namespace) -> int:
    """Sửa số tài khoản MT5 của một agent đã có — không đụng token.

    Sai số tài khoản thì Bridge từ chối bắt tay với `ACCOUNT_MISMATCH` mãi mãi, và trước lệnh này
    cách duy nhất để sửa là `UPDATE` tay vào database.
    """
    if args.login is None and args.terminal_title is None:
        print("Khong co gi de sua. Dat --login va/hoac --terminal-title.", file=sys.stderr)
        return 1
    try:
        if args.terminal_title is not None:
            dat_terminal_clicker(db, args.agent_id, args.login, args.terminal_title)
            print(f"Da dat terminal_title cua {args.agent_id} = {args.terminal_title!r}")
        if args.login is not None:
            if not doi_login_agent(db, args.agent_id, args.login):
                return _in_loi(LoiCauHinh("KHONG_CO_AGENT", agent_id=args.agent_id))
            print(f"Da dat account_login cua {args.agent_id} = {args.login}.")
    except LoiCauHinh as exc:
        return _in_loi(exc)
    print("Token giu nguyen; tien trinh dang bi tu choi se tu noi lai o lan thu ke tiep.")
    return 0


def lenh_sao_luu(db: Database, args: argparse.Namespace, db_path: Path) -> int:
    ban = sao_luu(db, db_path)
    dem = kiem_chung_ban_sao_luu(ban)
    print(f"Da sao luu: {ban}")
    print("  " + ", ".join(f"{k}={v}" for k, v in dem.items()))
    return 0


def lenh_bao_tri(db: Database, args: argparse.Namespace, db_path: Path) -> int:
    ket = bao_tri_hang_ngay(db, db_path)
    print(f"Ban sao luu: {ket.ban_sao_luu}")
    print(f"  event luu tru : {ket.event_luu_tru}")
    print(f"  command luu tru: {ket.command_luu_tru}")
    print(f"  ban cu da xoa : {len(ket.da_xoa)}")
    return 0


def lenh_kiem_reason(db: Database, _args: argparse.Namespace) -> int:
    """TEST-23 dưới dạng một lệnh chạy lại được, không phải một lần nhìn màn hình."""
    vi_pham = kiem_reason_client(db)
    tong = db.query_one(
        "SELECT COUNT(*) n FROM pair "
        "WHERE client_open_reason IS NOT NULL OR client_close_reason IS NOT NULL")["n"]
    mo = db.query_one(
        "SELECT COUNT(*) n FROM pair WHERE client_open_reason IS NOT NULL")["n"]
    dong = db.query_one(
        "SELECT COUNT(*) n FROM pair WHERE client_close_reason IS NOT NULL")["n"]
    def _in(r: dict, dich) -> None:
        print(f"  {r['pair_id']}  position={r['client_position_id']}  "
              f"mo={r['client_open_reason']} dong={r['client_close_reason']}  "
              f"-> sai o {r['cot']}", file=dich)

    da_ro = [r for r in vi_pham if r["da_giai_thich"]]
    chua_ro = [r for r in vi_pham if not r["da_giai_thich"]]

    if not chua_ro:
        print(f"TEST-23 DAT: {tong - len(da_ro)}/{tong} cap dung kenh "
              f"({mo} deal mo, {dong} deal dong).")
    else:
        print(f"TEST-23 KHONG DAT: {len(chua_ro)}/{tong} cap sai kenh khong giai thich duoc:",
              file=sys.stderr)
        for r in chua_ro:
            _in(r, sys.stderr)

    if da_ro:
        # In ra chu khong giau di: day van la deal that su da di sai kenh, va nguoi van hanh can
        # biet con bao nhieu. Chi khac o cho no KHONG tinh la that bai — xem `ops._da_giai_thich`.
        print(f"\n{len(da_ro)} cap sai kenh nhung DA CO GIAI THICH "
              f"(roi ve duong EA khi clicker hong, co alert CLOSE_FELL_BACK_TO_EA):")
        for r in da_ro:
            _in(r, sys.stdout)

    chua_ro_master = _in_phan_master(db)
    return 1 if (chua_ro or chua_ro_master) else 0


def _in_phan_master(db: Database) -> list[dict]:
    """Phần Master của `kiem-reason` (TEST-30). Im lặng khi `master_close_route = EA`."""
    vi_pham = kiem_reason_master(db)
    route = (db.get_config("master_close_route", "EA") or "EA").upper()
    if route != "UI":
        return []

    from bridge.ops import moc_bat_ui_master

    moc = moc_bat_ui_master(db)
    tong = db.query_one(
        "SELECT COUNT(*) n FROM master_position WHERE close_reason IS NOT NULL "
        "AND (close_time IS NULL OR ? IS NULL OR close_time >= ?)", (moc, moc))["n"]
    chua_ro = [r for r in vi_pham if not r["da_giai_thich"]]
    da_ro = [r for r in vi_pham if r["da_giai_thich"]]
    print(f"\n(TEST-30 chi tinh vi the Master dong sau khi bat master_close_route = UI luc {moc})")

    if not chua_ro:
        print(f"\nTEST-30 DAT: {tong - len(da_ro)}/{tong} vi the Master dong dung kenh.")
    else:
        print(f"\nTEST-30 KHONG DAT: {len(chua_ro)}/{tong} vi the Master dong sai kenh:",
              file=sys.stderr)
        for r in chua_ro:
            print(f"  master_position={r['master_position_id']} {r['symbol']} "
                  f"close_reason={r['close_reason']}", file=sys.stderr)
    if da_ro:
        print(f"{len(da_ro)} vi the Master sai kenh nhung DA CO GIAI THICH "
              "(alert CLOSE_MASTER_FELL_BACK_TO_EA):")
        for r in da_ro:
            print(f"  master_position={r['master_position_id']} {r['symbol']} "
                  f"close_reason={r['close_reason']}")
    return chua_ro


def lenh_kiem_dong_sai(db: Database, args: argparse.Namespace) -> int:
    """Chẩn đoán "bên kia chốt sai" — xem `ops.kiem_dong_sai`. Thoát 1 khi có dòng bị đánh dấu."""
    from bridge.ops import kiem_dong_sai

    kq = kiem_dong_sai(db, args.ngay)
    alert = ", ".join(f"{ma}={n}" for ma, n in sorted(kq["alert"].items())) or "0"
    print(f"ngay (UTC)        : {args.ngay or 'tat ca'}")
    print(f"ui_fallback_match : {kq['ui_fallback_match']}")
    print(f"alert lien quan   : {alert}")

    print(f"\n[C] cap ghep nham vi the luc mo : {len(kq['ghep_nham'])}")
    for r in kq["ghep_nham"]:
        print(f"    {r['pair_id']}  client_position={r['client_position_id']}  "
              f"the {r['open_tag']} KHONG co trong comment cua vi the")

    print(f"\n[A] deal dong mot vi the khong lenh nao nham toi : {len(kq['dong_nham'])}")
    for r in kq["dong_nham"]:
        lenh = "; ".join(f"{loai} nham {pid} ({cid})" for cid, loai, pid in r["lenh_gan"])
        print(f"    {r['received_at']}  {r['agent_id']}  dong {r['position_id']}  <- gan: {lenh}")

    print(f"\n[B] cap CLOSED ma vi the Client khong co deal dong : {len(kq['bao_dong_nham'])}")
    for r in kq["bao_dong_nham"]:
        print(f"    {r['pair_id']}  client_position={r['client_position_id']}  "
              f"cap nhat {r['updated_at']}")

    co = bool(kq["ghep_nham"] or kq["dong_nham"] or kq["bao_dong_nham"])
    if co:
        print("\nCo dong bi danh dau. Doc logs\\clicker.log quanh cac moc tren "
              "(Do dong, Tim vi the, Bam Close). [A] co the la nguoi dung dong tay dung luc do.")
    return 1 if co else 0


def lenh_cau_hinh_master(db: Database, args: argparse.Namespace) -> int:
    """Xem và sửa đường đóng phía Master (phase 12, D-21c).

    Master không có dòng `client_account` nào, nên hai giá trị này nằm ở `system_config`. Lệnh này
    tồn tại vì cùng lý do `cau-hinh-client` tồn tại: đổi chúng bằng `UPDATE` tay vào SQLite là chỗ
    dễ gõ nhầm nhất, mà gõ nhầm ở đây nghĩa là lệnh đóng Master đi sai kênh trong im lặng.
    """
    if args.close_route is None and args.clicker_agent is None:
        route = (db.get_config("master_close_route", "EA") or "EA").upper()
        clicker_id = (db.get_config("master_clicker_agent_id", "") or "").strip()
        print(f"master_close_route={route} master_clicker_agent_id={clicker_id or '(chua khai)'}")
        return 0

    try:
        doi = dat_duong_dong_master(db, args.clicker_agent, args.close_route)
    except LoiCauHinh as exc:
        return _in_loi(exc)
    for khoa, gia_tri in doi.items():
        print(f"{khoa} = {gia_tri}")
    if doi.get("master_close_route") == "UI":
        print("Luu y: terminal Master phai luon mo Toolbox o tab Trade, va clicker thu hai "
              "phai dang chay (python -m clicker --muc clicker_master).")
    return 0


def lenh_tinh_hinh(db: Database, _args: argparse.Namespace, db_path: Path) -> int:
    """Trả lời đúng một câu hỏi: **có gì cần làm không?**

    Hệ thống chạy trên VPS không có người trông và kênh cảnh báo ngoài đang tắt có chủ đích, nên
    mọi cảnh báo nằm im trong database cho tới khi có người nhìn. Lệnh này là cơ chế bù: nó gom
    những thứ mà mất chúng là mất tiền vào một màn hình đọc trong năm giây.

    **Mã thoát khác 0 khi có mục cần chú ý** — để cắm được vào Scheduled Task về sau.

    Dùng lại `bridge/web/views.py` thay vì viết truy vấn thứ hai: dashboard và lệnh này không bao
    giờ được nói khác nhau.
    """
    from bridge.clock import parse_iso, utc_now
    from bridge.web import views

    can_chu_y: list[str] = []
    chung = views.trang_thai_chung(db)
    so = views.chi_so(db)

    mode = chung["run_mode"]
    if mode == "RUNNING":
        print(f"run_mode : {mode}")
    else:
        print(f"run_mode : {mode}  <-- DANG KHONG COPY LENH MOI")
        can_chu_y.append(f"run_mode = {mode}")

    print()
    for a in chung["agents"]:
        cot = [f"  {a['agent_id']:<12} {a['role']:<8} {a['status']:<9}"]
        if not a["broker_connected"]:
            cot.append("broker: MAT KET NOI")
            can_chu_y.append(f"{a['agent_id']} mat ket noi broker")
        if a.get("trade_allowed") is False:
            cot.append("Algo Trading: TAT")
            can_chu_y.append(f"{a['agent_id']} tat Algo Trading")
        elif a.get("trade_allowed") is None and a["role"] != "CLICKER":
            cot.append("Algo Trading: khong ro")
        if a["status"] != "ONLINE":
            can_chu_y.append(f"{a['agent_id']} dang {a['status']}")
        print("  ".join(cot))

    print()
    print(f"cap dang hedge     : {so['hedged']}")
    if so["attention"]:
        print(f"cap can can thiep  : {so['attention']}")
        for cap in db.list_pairs_needing_attention():
            print(f"    {cap['pair_id']}  {cap['status']}"
                  f"{'  phia ' + cap['orphan_side'] if cap['orphan_side'] else ''}")
        can_chu_y.append(f"{so['attention']} cap can can thiep")
    else:
        print("cap can can thiep  : 0")

    cho = db.query_one("SELECT MIN(created_at) AS cu_nhat, COUNT(*) n FROM reconcile_finding "
                       "WHERE resolution = 'PENDING'")
    if cho and cho["n"]:
        tuoi = (utc_now() - parse_iso(cho["cu_nhat"])).total_seconds() / 3600.0
        print(f"sai lech dang cho  : {cho['n']}  (cu nhat {tuoi:.1f} gio)")
        can_chu_y.append(f"{cho['n']} sai lech dang cho xu ly")
    else:
        print("sai lech dang cho  : 0")

    # Hàng đợi mở qua giao diện (D-31). Bình thường nó rỗng vì mỗi lệnh chỉ chờ dưới một giây;
    # thấy nó có dòng nghĩa là Master đang vào lệnh nhanh hơn giao diện bấm được.
    hang_doi = db.query_one("SELECT COUNT(*) n, MIN(created_at) cu_nhat FROM ui_open_queue")
    if hang_doi and hang_doi["n"]:
        giay = (utc_now() - parse_iso(hang_doi["cu_nhat"])).total_seconds()
        print(f"hang doi mo (UI)   : {hang_doi['n']}  (cu nhat {giay:.1f} giay)")
        can_chu_y.append(f"{hang_doi['n']} lenh mo dang xep hang qua giao dien")
    else:
        print("hang doi mo (UI)   : 0")

    canh_bao = db.query_one(
        "SELECT COUNT(*) n FROM alert WHERE acknowledged_at IS NULL "
        "AND level IN ('ERROR', 'CRITICAL')")["n"]
    if canh_bao:
        print(f"canh bao chua xem  : {canh_bao} (ERROR/CRITICAL)")
        for r in db.query_all(
                "SELECT level, code, substr(message, 1, 70) m FROM alert "
                "WHERE acknowledged_at IS NULL AND level IN ('ERROR', 'CRITICAL') "
                "ORDER BY id DESC LIMIT 5"):
            print(f"    {r['level']:<8} {r['code']:<26} {r['m']}")
        can_chu_y.append(f"{canh_bao} canh bao ERROR/CRITICAL chua xem")
    else:
        print("canh bao chua xem  : 0")

    ban = sorted(thu_muc_sao_luu(db_path).glob("bridge-*.db"))
    if ban:
        gio = (utc_now().timestamp() - ban[-1].stat().st_mtime) / 3600.0
        print(f"sao luu gan nhat   : {ban[-1].name} ({gio:.1f} gio truoc)")
        if gio > 48:
            can_chu_y.append(f"sao luu gan nhat da {gio:.0f} gio truoc")
    else:
        print("sao luu gan nhat   : CHUA CO")
        can_chu_y.append("chua co ban sao luu nao")

    print()
    if not can_chu_y:
        print("=> Khong co gi can lam.")
        return 0
    print(f"=> {len(can_chu_y)} muc can chu y:")
    for muc in can_chu_y:
        print(f"   - {muc}")
    return 1


def lenh_anh_xa_symbol(db: Database, args: argparse.Namespace) -> int:
    """Xem và khai báo ánh xạ symbol giữa hai sàn.

    **Không có ánh xạ thì không copy được lệnh nào** — `find_symbol_map` trả `None` và mọi lệnh
    Master bị bỏ qua. Trước phase 11 chỉ tạo được dòng này bằng `INSERT` tay vào SQLite, nên một
    người cài đặt lần đầu sẽ dựng xong toàn bộ hệ thống rồi ngồi nhìn không có gì xảy ra.

    Hai sàn **không mặc định dùng cùng tên symbol** (`XAUUSD` với `XAUUSDm`), nên ánh xạ phải khai
    tường minh chứ không đoán.
    """
    if db.get_client_account(args.client_id) is None:
        return _in_loi(LoiCauHinh("KHONG_CO_CLIENT", client_id=args.client_id))

    if args.master_symbol is None:
        rows = db.query_all(
            "SELECT master_symbol, client_symbol, enabled, verified_at FROM symbol_map "
            "WHERE client_id = ? ORDER BY master_symbol", (args.client_id,))
        if not rows:
            print(f"{args.client_id}: CHUA CO anh xa nao. Se khong copy duoc lenh nao.")
            return 1
        print(f"{'symbol Master':<16} {'symbol Client':<16} bat  da kiem")
        for r in rows:
            print(f"  {r['master_symbol']:<14} {r['client_symbol']:<16} "
                  f"{'x' if r['enabled'] else '-':<4} {'x' if r['verified_at'] else '-'}")
        return 0

    if args.xoa:
        try:
            xoa_anh_xa(db, args.client_id, args.master_symbol)
        except LoiCauHinh as exc:
            return _in_loi(exc)
        print(f"Da XOA anh xa {args.master_symbol}")
        return 0

    if args.tat:
        try:
            tat_anh_xa(db, args.client_id, args.master_symbol)
        except LoiCauHinh as exc:
            return _in_loi(exc)
        print(f"Da TAT anh xa {args.master_symbol}")
        return 0

    if not args.client_symbol:
        return _in_loi(LoiCauHinh("THIEU_SYMBOL"))

    try:
        spec = khai_anh_xa(db, args.client_id, args.master_symbol, args.client_symbol)
    except LoiCauHinh as exc:
        return _in_loi(exc)
    print(f"{args.client_id}: {args.master_symbol} -> {args.client_symbol}  (da kiem tren san)")
    print(f"  volume toi thieu {spec['volume_min']}, buoc {spec['volume_step']}")
    return 0


def lenh_them_client(db: Database, args: argparse.Namespace) -> int:
    """Tạo dòng ``client_account`` cho một agent CLIENT.

    Đối xứng với `lenh_them_agent`, và tồn tại vì cùng một lý do. Trước lệnh này không có
    đường nào tạo được dòng `client_account`: `cau-hinh-client` từ chối khi dòng chưa tồn
    tại, còn Bridge không tự tạo lúc EA Client đăng ký. Nghĩa là một bản cài mới đi tới
    `anh-xa-symbol` là chết với "Khong co client", và cách duy nhất để qua được là `INSERT`
    tay vào SQLite — đúng thứ mà `cau-hinh-client` được viết ra để khỏi phải làm.

    `clicker_agent_id` cũng chỉ đặt được ở đây. `cau-hinh-client --open-route UI` đòi nó
    nhưng không có cờ nào để điền, nên trước đây bật `UI` bằng lệnh là chuyện bất khả.
    """
    try:
        da = tao_client(db, args.client_id, args.agent_id, args.clicker_agent,
                        args.open_route, args.close_route, args.ten)
    except LoiCauHinh as exc:
        return _in_loi(exc)
    clicker = da["clicker_agent_id"]
    print(f"Da tao client {args.client_id} -> agent {args.agent_id} "
          f"(open_route={da['open_route']}, close_route={da['close_route']}"
          f"{', clicker ' + clicker if clicker else ''})")
    print("Buoc tiep: `anh-xa-symbol` -- THIEU ANH XA LA MOI LENH MASTER BI BO QUA.")
    return 0


def lenh_cau_hinh_client(db: Database, args: argparse.Namespace) -> int:
    """Xem và sửa cấu hình một Client (B-11).

    Trước phase 11 chỉ sửa được bằng `UPDATE` tay vào SQLite — và để chạy đúng một mục nghiệm thu
    thì phải làm thế thật. Sửa cấu hình giao dịch bằng SQL tay là chỗ dễ gõ nhầm nhất trong cả hệ
    thống, nên nó xứng đáng có một lệnh với ràng buộc rõ ràng.

    **Chỉ đổi lệnh MỚI.** Cặp đang chạy giữ nguyên tỷ lệ của nó: đường đóng một phần lấy tỷ lệ
    trên volume còn lại của chính cặp đó và không hề đọc bảng này (D-19).
    """
    client = db.get_client_account(args.client_id)
    if client is None:
        return _in_loi(LoiCauHinh("KHONG_CO_CLIENT", client_id=args.client_id))

    co_gi_doi = any(x is not None for x in (args.copy_mode, args.multiplier, args.open_route,
                                           args.close_route, args.can_close_master,
                                           args.hoat_dong))
    if not co_gi_doi:
        print(f"{args.client_id}: copy_mode={client['copy_mode']} "
              f"volume_multiplier={client['volume_multiplier']} "
              f"open_route={client['open_route']} "
              f"close_route={client['close_route']} "
              f"can_close_master={client['can_close_master']} "
              f"enabled={client['enabled']}")
        return 0

    try:
        doi, dang_mo = sua_client(
            db, args.client_id, copy_mode=args.copy_mode, volume_multiplier=args.multiplier,
            open_route=args.open_route, close_route=args.close_route,
            can_close_master=(None if args.can_close_master is None
                              else args.can_close_master == "bat"),
            enabled=(None if args.hoat_dong is None else args.hoat_dong == "bat"))
    except LoiCauHinh as exc:
        return _in_loi(exc)
    for khoa, gia_tri in doi.items():
        print(f"{args.client_id}.{khoa} = {gia_tri}")
    if dang_mo:
        print(f"Luu y: {dang_mo} cap dang chay giu nguyen ty le cu, chi lenh MOI dung gia tri nay.")
    return 0


def lenh_xoa_client(db: Database, args: argparse.Namespace) -> int:
    """Xoá một `client_account`. Từ chối khi Client đã có cặp lệnh — dùng `--hoat-dong tat`."""
    try:
        xoa_client(db, args.client_id)
    except LoiCauHinh as exc:
        return _in_loi(exc)
    print(f"Da xoa client {args.client_id} (ke ca anh xa symbol cua no).")
    return 0


def lenh_ghi_moc_cap_nhat(db: Database, args: argparse.Namespace) -> int:
    """Ghi biên nhận của một lần cập nhật code, và xoá ô tự tích cũ của trang Hướng dẫn.

    `cai-dat.ps1 -CapNhat` gọi lệnh này ở cuối. Đây là thứ **duy nhất** cho dashboard biết vừa có
    một lần cập nhật: Bridge không lưu phiên bản code nào, và một agent nối lại thì trông giống
    nhau dù vì EA vừa gắn lại hay vì dịch vụ vừa khởi động.
    """
    kq = ghi_moc_cap_nhat(db, bool(args.ea_doi), args.tu_commit or "")
    print(f"Da ghi moc cap nhat {kq['moc_cap_nhat']} (ea_doi={int(kq['ea_doi'])}).")
    print("O tu tich cua trang Huong dan da duoc xoa -- danh sach sau update noi ve lan nay.")
    return 0


def lenh_dat_lai(db: Database, args: argparse.Namespace, db_path: Path) -> int:
    """Đặt lại hệ thống. Bắt gõ đúng cụm xác nhận, y như trên dashboard.

    Hai mức: `du-lieu` xoá lịch sử giao dịch và giữ cấu hình; `tat-ca` xoá thêm client, ánh xạ và
    đưa khoá hệ thống về mặc định — **agent và token vẫn giữ**.
    """
    cum = {"du-lieu": "DAT LAI DU LIEU", "tat-ca": "DAT LAI TAT CA"}[args.muc]
    if (args.xac_nhan or "").strip() != cum:
        print(f'Can go dung cum xac nhan: --xac-nhan "{cum}"', file=sys.stderr)
        return 1
    ham = dat_lai_lich_su if args.muc == "du-lieu" else dat_lai_toan_bo
    try:
        kq = ham(db, db_path)
    except LoiCauHinh as exc:
        return _in_loi(exc)
    for bang, so in kq["da_xoa"].items():
        print(f"  {bang:<20} xoa {so} dong")
    print(f"Da dat lai ({args.muc}). Ban sao luu truoc khi xoa: {kq['ban_sao']}")
    return 0


def lenh_run_mode(db: Database, args: argparse.Namespace) -> int:
    if args.gia_tri is None:
        print(db.get_config("run_mode"))
        return 0
    # Khong co duong tu dong sang RUNNING (D-15) — nhung co duong **co chu dich**, va day la no.
    db.set_config("run_mode", args.gia_tri)
    print(f"run_mode = {args.gia_tri}")
    return 0


def lenh_xac_nhan_alert(db: Database, args: argparse.Namespace) -> int:
    """Đánh dấu **đã xem** các alert cũ theo mã. Không đổi gì khác ngoài `acknowledged_at`.

    Dashboard chỉ xác nhận từng alert một. Sau đợt chạy thử, VPS ngày 2026-09-11 có 240 alert
    chưa xem, 207 trong số đó là hai mã lặp (`RECONCILE_NO_SNAPSHOT` mỗi phút, `FINDING_BO_QUEN`
    mỗi giờ). Bấm 240 lần thì không ai bấm, và ô "cảnh báo chưa xem" đỏ vĩnh viễn nghĩa là
    alert thật kế tiếp chìm luôn trong đó.

    Ba chốt, đều cố ý:

    * `--code` bắt buộc, không có "tất cả": phải nhìn thấy mã thì mới xác nhận được.
    * `--truoc` bắt buộc và phải có múi giờ: alert sinh ra **sau** lúc người vận hành đọc không
      bao giờ bị nuốt theo, và không phải đoán giờ địa phương hay UTC.
    * Mặc định chỉ đếm; phải có `--that` mới ghi.

    Không đụng `reconcile_finding`: xác nhận đã xem một lời nhắc không giải quyết sai lệch mà nó
    nhắc tới.
    """
    try:
        moc = datetime.fromisoformat(args.truoc)
    except ValueError:
        print(f"--truoc khong phai thoi diem ISO 8601: {args.truoc}", file=sys.stderr)
        return 1
    if moc.tzinfo is None:
        print("--truoc phai co mui gio, vi du 2026-09-11T16:30:00+07:00 hoac "
              "2026-09-11T09:30:00Z. Khong doan gio dia phuong hay UTC.", file=sys.stderr)
        return 1
    moc_iso = to_iso(moc)
    ma = sorted(set(args.code))
    dau_hoi = ", ".join("?" for _ in ma)
    rows = db.query_all(
        "SELECT level, code, COUNT(*) n, MIN(created_at) dau, MAX(created_at) cuoi FROM alert "
        f"WHERE acknowledged_at IS NULL AND created_at < ? AND code IN ({dau_hoi}) "
        "GROUP BY level, code ORDER BY n DESC", (moc_iso, *ma))
    tong = sum(int(r["n"]) for r in rows)

    print(f"Alert chua xem, sinh truoc {moc_iso}:")
    for r in rows:
        print(f"  {r['level']:<8} {r['code']:<28} {r['n']:>5}  ({r['dau']} -> {r['cuoi']})")
    if tong == 0:
        print("  (khong co)")
        return 0
    if not args.that:
        print(f"CHUA ghi gi. {tong} alert o tren se duoc xac nhan khi chay lai kem --that.")
        return 0
    so = db.acknowledge_alerts_by_code(ma, before=moc_iso)
    print(f"Da xac nhan {so} alert.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m bridge.admin",
                                description="Cong cu van hanh Bridge")
    sub = p.add_subparsers(dest="lenh", required=True)

    sub.add_parser("liet-ke", help="Liet ke agent")

    them = sub.add_parser("them-agent", help="Tao agent moi va cap token dau tien")
    them.add_argument("agent_id")
    them.add_argument("--role", required=True, choices=VAI_TRO)
    them.add_argument("--magic", type=int, required=True)
    them.add_argument("--login", type=int, default=None)

    cap = sub.add_parser("cap-token", help="Cap token moi (token cu het hieu luc)")
    cap.add_argument("agent_id")

    thu = sub.add_parser("thu-hoi", help="Thu hoi token, vo hieu hoa agent")
    thu.add_argument("agent_id")

    sa = sub.add_parser("sua-agent",
                        help="Sua so tai khoan MT5 / tieu de cua so cua agent (token giu nguyen)")
    sa.add_argument("agent_id")
    sa.add_argument("--login", type=int, default=None, help="So tai khoan MT5 dung")
    sa.add_argument("--terminal-title", dest="terminal_title",
                    help="Mau tieu de cua so terminal ma clicker phai lai (phai chua so tai khoan)")

    sub.add_parser("sao-luu", help="Sao luu DB ngay bay gio va kiem chung")
    sub.add_parser("bao-tri", help="Retention + sao luu + don ban cu")
    sub.add_parser("kiem-reason", help="TEST-23: moi vi the Client phai la DEAL_REASON_CLIENT")
    kd = sub.add_parser("kiem-dong-sai",
                        help="Chan doan 'ben kia chot sai': ghep nham, dong nham, bao dong nham")
    kd.add_argument("--ngay", help="Ngay UTC dang YYYY-MM-DD; bo trong la moi ngay")

    sub.add_parser("tinh-hinh", help="Co gi can lam khong (thoat khac 0 neu co)")

    tc = sub.add_parser("them-client", help="Tao client_account cho mot agent CLIENT")
    tc.add_argument("client_id")
    tc.add_argument("--agent", dest="agent_id", required=True, help="agent_id vai tro CLIENT")
    tc.add_argument("--clicker-agent", dest="clicker_agent",
                    help="agent_id vai tro CLICKER; bat buoc khi --open-route UI")
    tc.add_argument("--open-route", dest="open_route", default="UI", choices=("EA", "UI"))
    tc.add_argument("--close-route", dest="close_route", default=None, choices=("EA", "UI"),
                    help="Kenh gui lenh DONG. Mac dinh theo --open-route")
    tc.add_argument("--ten", help="Ten hien thi, mac dinh lay client_id")

    cf = sub.add_parser("cau-hinh-client", help="Xem hoac sua cau hinh mot Client")
    cf.add_argument("client_id")
    cf.add_argument("--copy-mode", dest="copy_mode", choices=("SAME", "OPPOSITE"))
    cf.add_argument("--multiplier", type=float)
    cf.add_argument("--open-route", dest="open_route", choices=("EA", "UI"))
    cf.add_argument("--close-route", dest="close_route", choices=("EA", "UI"),
                    help="Kenh gui lenh DONG. UI de deal dong mang DEAL_REASON_CLIENT")
    cf.add_argument("--can-close-master", dest="can_close_master", choices=("bat", "tat"))
    cf.add_argument("--hoat-dong", dest="hoat_dong", choices=("bat", "tat"),
                    help="Tat thi Client nay khong copy lenh moi nua (cap dang mo giu nguyen)")

    xc = sub.add_parser("xoa-client",
                        help="Xoa han mot client_account (chi khi chua co cap lenh nao)")
    xc.add_argument("client_id")

    cm = sub.add_parser("cau-hinh-master",
                        help="Xem hoac sua duong DONG phia Master (phase 12)")
    cm.add_argument("--close-route", dest="close_route", choices=("EA", "UI"),
                    help="UI de deal dong tren Master mang DEAL_REASON = CLIENT")
    cm.add_argument("--clicker-agent", dest="clicker_agent",
                    help="agent_id vai tro CLICKER lai terminal Master")

    ax = sub.add_parser("anh-xa-symbol", help="Xem hoac khai bao anh xa symbol giua hai san")
    ax.add_argument("client_id")
    ax.add_argument("master_symbol", nargs="?")
    ax.add_argument("--client-symbol", dest="client_symbol")
    ax.add_argument("--tat", action="store_true", help="Tat anh xa nay (dong van con trong bang)")
    ax.add_argument("--xoa", action="store_true", help="Xoa han anh xa nay khoi bang")

    dl = sub.add_parser("dat-lai", help="Xoa lich su (va cau hinh) -- bat go dung cum xac nhan")
    dl.add_argument("muc", choices=("du-lieu", "tat-ca"),
                    help="du-lieu: giu cau hinh. tat-ca: xoa ca client/anh xa/khoa he thong")
    dl.add_argument("--xac-nhan", dest="xac_nhan", required=True,
                    help='Cum xac nhan: "DAT LAI DU LIEU" hoac "DAT LAI TAT CA"')

    gm = sub.add_parser("ghi-moc-cap-nhat",
                        help="Ghi moc cap nhat cho trang Huong dan (cai-dat.ps1 -CapNhat goi)")
    gm.add_argument("--ea-doi", dest="ea_doi", type=int, choices=(0, 1), default=0,
                    help="1 khi thu muc ea/ doi o lan cap nhat nay (phai gan lai EA)")
    gm.add_argument("--tu-commit", dest="tu_commit", default="",
                    help="Commit truoc khi cap nhat, chi de hien ra cho de doi chieu")

    rm = sub.add_parser("run-mode", help="Xem hoac dat run_mode")
    rm.add_argument("gia_tri", nargs="?",
                    choices=("PAUSED", "RUNNING", "PAUSE_NEW_ENTRIES", "EMERGENCY"))

    xn = sub.add_parser("xac-nhan-alert",
                        help="Danh dau DA XEM cac alert cu theo ma (mac dinh chi dem)")
    xn.add_argument("--code", action="append", required=True,
                    help="Ma alert. Lap lai de chon nhieu ma. Khong co 'tat ca'")
    xn.add_argument("--truoc", required=True,
                    help="Chi alert sinh TRUOC moc nay, bat buoc co mui gio, "
                         "vi du 2026-09-11T16:30:00+07:00")
    xn.add_argument("--that", action="store_true", help="Ghi that. Thieu co nay thi chi dem")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db, db_path = _mo_db()
    try:
        if args.lenh == "liet-ke":
            return lenh_liet_ke(db, args)
        if args.lenh == "them-agent":
            return lenh_them_agent(db, args)
        if args.lenh == "cap-token":
            return lenh_cap_token(db, args)
        if args.lenh == "thu-hoi":
            return lenh_thu_hoi(db, args)
        if args.lenh == "sua-agent":
            return lenh_sua_agent(db, args)
        if args.lenh == "sao-luu":
            return lenh_sao_luu(db, args, db_path)
        if args.lenh == "bao-tri":
            return lenh_bao_tri(db, args, db_path)
        if args.lenh == "kiem-reason":
            return lenh_kiem_reason(db, args)
        if args.lenh == "kiem-dong-sai":
            return lenh_kiem_dong_sai(db, args)
        if args.lenh == "tinh-hinh":
            return lenh_tinh_hinh(db, args, db_path)
        if args.lenh == "anh-xa-symbol":
            return lenh_anh_xa_symbol(db, args)
        if args.lenh == "them-client":
            return lenh_them_client(db, args)
        if args.lenh == "cau-hinh-client":
            return lenh_cau_hinh_client(db, args)
        if args.lenh == "cau-hinh-master":
            return lenh_cau_hinh_master(db, args)
        if args.lenh == "xoa-client":
            return lenh_xoa_client(db, args)
        if args.lenh == "dat-lai":
            return lenh_dat_lai(db, args, db_path)
        if args.lenh == "ghi-moc-cap-nhat":
            return lenh_ghi_moc_cap_nhat(db, args)
        if args.lenh == "run-mode":
            return lenh_run_mode(db, args)
        if args.lenh == "xac-nhan-alert":
            return lenh_xac_nhan_alert(db, args)
    finally:
        db.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
