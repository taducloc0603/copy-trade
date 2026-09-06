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
        if args.lenh == "run-mode":
            return lenh_run_mode(db, args)
    finally:
        db.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
