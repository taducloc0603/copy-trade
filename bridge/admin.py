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
        "SELECT COUNT(*) n FROM pair WHERE client_open_reason IS NOT NULL")["n"]
    if not vi_pham:
        print(f"TEST-23 DAT: {tong}/{tong} vi the Client mang DEAL_REASON_CLIENT (0).")
        return 0
    print(f"TEST-23 KHONG DAT: {len(vi_pham)}/{tong} cap sai kenh mo:", file=sys.stderr)
    for r in vi_pham:
        print(f"  {r['pair_id']}  position={r['client_position_id']}  "
              f"reason={r['client_open_reason']}", file=sys.stderr)
    return 1


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
    if args.can_close_master is not None:
        doi["can_close_master"] = 1 if args.can_close_master == "bat" else 0

    if not doi:
        print(f"{args.client_id}: copy_mode={client['copy_mode']} "
              f"volume_multiplier={client['volume_multiplier']} "
              f"open_route={client['open_route']} "
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

    cf = sub.add_parser("cau-hinh-client", help="Xem hoac sua cau hinh mot Client")
    cf.add_argument("client_id")
    cf.add_argument("--copy-mode", dest="copy_mode", choices=("SAME", "OPPOSITE"))
    cf.add_argument("--multiplier", type=float)
    cf.add_argument("--open-route", dest="open_route", choices=("EA", "UI"))
    cf.add_argument("--can-close-master", dest="can_close_master", choices=("bat", "tat"))

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
        if args.lenh == "cau-hinh-client":
            return lenh_cau_hinh_client(db, args)
        if args.lenh == "run-mode":
            return lenh_run_mode(db, args)
    finally:
        db.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
