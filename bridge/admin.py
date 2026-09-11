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
from pathlib import Path

from bridge.clock import utc_now_iso
from bridge.config import load_config
from bridge.db.repo import Database
from bridge.ops import (
    bao_tri_hang_ngay,
    cap_token,
    kiem_chung_ban_sao_luu,
    kiem_reason_client,
    sao_luu,
    thu_hoi_token,
    thu_muc_sao_luu,
)
from bridge.protocol.auth import hash_token

VAI_TRO = ("MASTER", "CLIENT", "CLICKER")


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
    if db.get_agent(args.agent_id) is not None:
        print(f"Agent {args.agent_id} da ton tai. Dung `cap-token` neu chi muon doi token.",
              file=sys.stderr)
        return 1
    token = _sinh_va_luu(db, args.agent_id, args.role, args.magic, args.login)
    print(f"Da tao agent {args.agent_id} ({args.role}).")
    _in_token(args.agent_id, token)
    return 0


def _sinh_va_luu(db: Database, agent_id: str, role: str, magic: int, login: int | None) -> str:
    from bridge.protocol.auth import generate_token

    token = generate_token()
    db.upsert_agent(agent_id, role=role, token_hash=hash_token(token), magic_number=magic,
                    account_login=login)
    return token


def _in_token(agent_id: str, token: str) -> None:
    print()
    print(f"  TOKEN cua {agent_id} (chi hien MOT lan, khong ghi log, khong doc lai duoc):")
    print(f"  {token}")
    print()
    print("  Dat vao tham so EA (hoac muc clicker trong config.toml) ngay bay gio.")


def lenh_cap_token(db: Database, args: argparse.Namespace) -> int:
    try:
        token = cap_token(db, args.agent_id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Da cap token moi cho {args.agent_id}. Token cu het hieu luc ngay lap tuc.")
    _in_token(args.agent_id, token)
    return 0


def lenh_thu_hoi(db: Database, args: argparse.Namespace) -> int:
    if not thu_hoi_token(db, args.agent_id):
        print(f"Khong co agent {args.agent_id}", file=sys.stderr)
        return 1
    print(f"Da thu hoi token cua {args.agent_id}. Agent nay khong ket noi lai duoc nua.")
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

    return 1 if chua_ro else 0


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
    client = db.get_client_account(args.client_id)
    if client is None:
        print(f"Khong co client {args.client_id}", file=sys.stderr)
        return 1

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

    if args.tat:
        if db.query_one("SELECT 1 FROM symbol_map WHERE client_id = ? AND master_symbol = ?",
                        (args.client_id, args.master_symbol)) is None:
            print(f"Khong co anh xa cho {args.master_symbol}", file=sys.stderr)
            return 1
        db.upsert_symbol_map(args.client_id, args.master_symbol, args.client_symbol or "",
                             enabled=0)
        print(f"Da TAT anh xa {args.master_symbol}")
        return 0

    if not args.client_symbol:
        print("Thieu symbol phia Client. Vi du: --client-symbol XAUUSDm", file=sys.stderr)
        return 1

    # Kiem symbol co that tren san Client truoc khi luu. EA day `symbol_spec` len moi vai phut,
    # nen day la nguon su that chu khong phai phong doan — va sai ten symbol la loi khong hien ra
    # cho toi luc co lenh that di qua.
    spec = db.get_symbol_spec(client["agent_id"], args.client_symbol)
    if spec is None:
        print(f"San Client chua bao co symbol {args.client_symbol!r}.", file=sys.stderr)
        print("Kiem: EA Client dang chay chua, va symbol da duoc keo vao Market Watch chua.",
              file=sys.stderr)
        co = db.query_all("SELECT symbol FROM symbol_spec WHERE agent_id = ? ORDER BY symbol",
                          (client["agent_id"],))
        if co:
            print("San Client dang bao co: " + ", ".join(r["symbol"] for r in co), file=sys.stderr)
        return 1

    db.upsert_symbol_map(args.client_id, args.master_symbol, args.client_symbol,
                         enabled=1, verified_at=utc_now_iso())
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
    if db.query_one("SELECT 1 FROM client_account WHERE client_id = ?",
                    (args.client_id,)) is not None:
        print(f"Client {args.client_id} da ton tai. Dung `cau-hinh-client` de sua.",
              file=sys.stderr)
        return 1

    agent = db.get_agent(args.agent_id)
    if agent is None:
        print(f"Khong co agent {args.agent_id}. Tao bang `them-agent` truoc.", file=sys.stderr)
        return 1
    if agent["role"] != "CLIENT":
        print(f"Agent {args.agent_id} co role {agent['role']}, can CLIENT.", file=sys.stderr)
        return 1

    # Giu nguyen rang buoc cua `cau-hinh-client`: open_route = UI ma khong co clicker thi
    # duong mo lenh khong co ai bam, va no hong trong im lang chu khong bao gi.
    if args.open_route == "UI" and not args.clicker_agent:
        print("open_route = UI can --clicker-agent", file=sys.stderr)
        return 1
    # Mac dinh theo `--open-route`: mot Client dat duong giao dien de MO thi cung dat no de
    # DONG, con mot Client con o duong EA thi giu nguyen ca hai. Khong co cach ghep nao khac
    # vua hop ly vua khong bat nguoi ta phai go them mot co moi de giu nguyen hanh vi cu.
    close_route = args.close_route or args.open_route
    if close_route == "UI" and not args.clicker_agent:
        print("close_route = UI can --clicker-agent", file=sys.stderr)
        return 1
    if args.clicker_agent:
        clicker = db.get_agent(args.clicker_agent)
        if clicker is None:
            print(f"Khong co agent {args.clicker_agent}", file=sys.stderr)
            return 1
        if clicker["role"] != "CLICKER":
            print(f"Agent {args.clicker_agent} co role {clicker['role']}, can CLICKER.",
                  file=sys.stderr)
            return 1

    db.upsert_client_account(args.client_id, agent_id=args.agent_id,
                             display_name=args.ten or args.client_id,
                             open_route=args.open_route,
                             close_route=close_route,
                             clicker_agent_id=args.clicker_agent)
    print(f"Da tao client {args.client_id} -> agent {args.agent_id} "
          f"(open_route={args.open_route}, close_route={close_route}"
          f"{', clicker ' + args.clicker_agent if args.clicker_agent else ''})")
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
    client = db.query_one("SELECT * FROM client_account WHERE client_id = ?", (args.client_id,))
    if client is None:
        print(f"Khong co client {args.client_id}", file=sys.stderr)
        return 1

    doi = {}
    if args.copy_mode is not None:
        doi["copy_mode"] = args.copy_mode
    if args.multiplier is not None:
        if args.multiplier <= 0:
            print("volume_multiplier phai duong", file=sys.stderr)
            return 1
        doi["volume_multiplier"] = args.multiplier
    if args.open_route is not None:
        if args.open_route == "UI" and not client["clicker_agent_id"]:
            print("open_route = UI can clicker_agent_id, chua co", file=sys.stderr)
            return 1
        doi["open_route"] = args.open_route
    if args.close_route is not None:
        # Cung rang buoc voi `open_route`, va vi cung mot ly do: bat duong giao dien ma khong co
        # clicker la mot cau hinh vo nghia — lenh se khong bao gio gui duoc di dau.
        if args.close_route == "UI" and not client["clicker_agent_id"]:
            print("close_route = UI can clicker_agent_id, chua co", file=sys.stderr)
            return 1
        doi["close_route"] = args.close_route
    if args.can_close_master is not None:
        doi["can_close_master"] = 1 if args.can_close_master == "bat" else 0

    if not doi:
        print(f"{args.client_id}: copy_mode={client['copy_mode']} "
              f"volume_multiplier={client['volume_multiplier']} "
              f"open_route={client['open_route']} "
              f"close_route={client['close_route']} "
              f"can_close_master={client['can_close_master']}")
        return 0

    dang_mo = db.query_one(
        "SELECT COUNT(*) n FROM pair WHERE client_id = ? AND status NOT IN ('CLOSED','OPEN_FAILED')",
        (args.client_id,))["n"]
    db.upsert_client_account(args.client_id, agent_id=client["agent_id"], **doi)
    for khoa, gia_tri in doi.items():
        print(f"{args.client_id}.{khoa} = {gia_tri}")
    if dang_mo:
        print(f"Luu y: {dang_mo} cap dang chay giu nguyen ty le cu, chi lenh MOI dung gia tri nay.")
    return 0


def lenh_run_mode(db: Database, args: argparse.Namespace) -> int:
    if args.gia_tri is None:
        print(db.get_config("run_mode"))
        return 0
    # Khong co duong tu dong sang RUNNING (D-15) — nhung co duong **co chu dich**, va day la no.
    db.set_config("run_mode", args.gia_tri)
    print(f"run_mode = {args.gia_tri}")
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

    sub.add_parser("sao-luu", help="Sao luu DB ngay bay gio va kiem chung")
    sub.add_parser("bao-tri", help="Retention + sao luu + don ban cu")
    sub.add_parser("kiem-reason", help="TEST-23: moi vi the Client phai la DEAL_REASON_CLIENT")

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

    ax = sub.add_parser("anh-xa-symbol", help="Xem hoac khai bao anh xa symbol giua hai san")
    ax.add_argument("client_id")
    ax.add_argument("master_symbol", nargs="?")
    ax.add_argument("--client-symbol", dest="client_symbol")
    ax.add_argument("--tat", action="store_true", help="Tat anh xa nay")

    rm = sub.add_parser("run-mode", help="Xem hoac dat run_mode")
    rm.add_argument("gia_tri", nargs="?",
                    choices=("PAUSED", "RUNNING", "PAUSE_NEW_ENTRIES", "EMERGENCY"))
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
        if args.lenh == "sao-luu":
            return lenh_sao_luu(db, args, db_path)
        if args.lenh == "bao-tri":
            return lenh_bao_tri(db, args, db_path)
        if args.lenh == "kiem-reason":
            return lenh_kiem_reason(db, args)
        if args.lenh == "tinh-hinh":
            return lenh_tinh_hinh(db, args, db_path)
        if args.lenh == "anh-xa-symbol":
            return lenh_anh_xa_symbol(db, args)
        if args.lenh == "them-client":
            return lenh_them_client(db, args)
        if args.lenh == "cau-hinh-client":
            return lenh_cau_hinh_client(db, args)
        if args.lenh == "run-mode":
            return lenh_run_mode(db, args)
    finally:
        db.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
