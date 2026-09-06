"""Test vận hành: sao lưu, token, dọn log, và kênh cảnh báo (plan mục 10.2–10.4).

Hai bất biến quan trọng nhất ở đây:

* **Một bản sao lưu chưa từng khôi phục thử thì không phải bản sao lưu** — nên hàm sao lưu tự
  kiểm chứng, và test kiểm luôn việc đó.
* **Kênh cảnh báo hỏng không được ảnh hưởng tới luồng giao dịch** — Telegram chết, mạng chết,
  token sai, hệ thống vẫn chạy y nguyên.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import pytest

from bridge.alerting import CUA_SO_GOP_SEC, AlertChannel, BoGop, TinNhan, tao_kenh
from bridge.db.repo import Database
from bridge.ops import (
    bao_tri_hang_ngay,
    cap_token,
    don_ban_cu,
    don_log_cu,
    khoi_phuc_thu,
    kiem_chung_ban_sao_luu,
    sao_luu,
    thu_hoi_token,
)
from bridge.protocol.auth import hash_token, verify_token
from tests.conftest import CLIENT_AGENT, CLIENT_ID, MASTER_AGENT, MASTER_POSITION_ID

# -- sao lưu ----------------------------------------------------------------------------------

def test_sao_luu_mo_lai_duoc_va_du_du_lieu(db: Database, db_path: Path,
                                           seeded: Database) -> None:
    ban = sao_luu(seeded, db_path)
    assert ban.exists()
    dem = kiem_chung_ban_sao_luu(ban)
    assert dem["agent"] >= 1, "Ban sao luu phai co du lieu that"


def test_sao_luu_chay_duoc_khi_dang_co_giao_dich_wal(seeded: Database,
                                                     db_path: Path) -> None:
    """`VACUUM INTO` an toàn với WAL — đó là lý do chọn nó thay vì copy file.

    Copy `bridge.db` khi WAL còn dữ liệu chưa checkpoint sẽ ra bản thiếu **đúng những giao dịch
    mới nhất**, tức những thứ quý nhất.
    """
    seeded.create_alert("INFO", "TRUOC_SAO_LUU", "ghi ngay truoc khi sao luu")
    ban = sao_luu(seeded, db_path)
    dem = kiem_chung_ban_sao_luu(ban)
    assert dem["agent"] >= 1
    # Doc thang tu ban sao luu de chac chan giao dich moi nhat co trong do.
    conn = sqlite3.connect(f"file:{ban}?mode=ro", uri=True)
    try:
        so = conn.execute(
            "SELECT COUNT(*) FROM alert WHERE code = 'TRUOC_SAO_LUU'").fetchone()[0]
    finally:
        conn.close()
    assert so == 1, "Giao dich ngay truoc khi sao luu bi mat"


def test_chi_giu_so_ban_sao_luu_da_dinh(seeded: Database, db_path: Path) -> None:
    for _ in range(5):
        sao_luu(seeded, db_path)
        time.sleep(1.05)      # ten file co do phan giai mot giay
    da_xoa = don_ban_cu(db_path, giu=2)
    con = sorted((db_path.parent / "backup").glob("bridge-*.db"))
    assert len(con) == 2
    assert len(da_xoa) == 3


def test_ban_sao_luu_hong_thi_bao_loi(seeded: Database, db_path: Path,
                                      tmp_path: Path) -> None:
    hong = tmp_path / "hong.db"
    hong.write_bytes(b"day khong phai file sqlite")
    with pytest.raises((sqlite3.DatabaseError, RuntimeError)):
        kiem_chung_ban_sao_luu(hong)


def test_khoi_phuc_thu_khong_dung_toi_ban_dang_chay(seeded: Database, db_path: Path,
                                                    tmp_path: Path) -> None:
    ban = sao_luu(seeded, db_path)
    dich = tmp_path / "khoi-phuc" / "bridge.db"
    khoi_phuc_thu(ban, dich)
    assert dich.exists()
    assert db_path.exists(), "Ban dang chay khong duoc dung toi"


def test_bao_tri_hang_ngay_chay_tron_ven(seeded: Database, db_path: Path) -> None:
    ket = bao_tri_hang_ngay(seeded, db_path)
    assert ket.ban_sao_luu is not None and ket.ban_sao_luu.exists()
    assert kiem_chung_ban_sao_luu(ket.ban_sao_luu)["agent"] >= 1


# -- token ------------------------------------------------------------------------------------

def test_cap_token_moi_thi_token_cu_het_hieu_luc(seeded: Database) -> None:
    cu = cap_token(seeded, MASTER_AGENT)
    moi = cap_token(seeded, MASTER_AGENT)
    assert cu != moi
    băm = seeded.get_agent(MASTER_AGENT)["token_hash"]
    assert verify_token(moi, băm)
    assert not verify_token(cu, băm), "Token cu phai het hieu luc"


def test_token_du_dai(seeded: Database) -> None:
    """Tối thiểu 32 byte (plan 10.2)."""
    token = cap_token(seeded, MASTER_AGENT)
    assert len(token) >= 32


def test_thu_hoi_token_thi_khong_con_token_nao_dung(seeded: Database) -> None:
    """Đặt hash thành giá trị không thể sinh ra từ bất kỳ token nào, thay vì xoá dòng agent."""
    token = cap_token(seeded, MASTER_AGENT)
    assert thu_hoi_token(seeded, MASTER_AGENT)

    agent = seeded.get_agent(MASTER_AGENT)
    assert agent is not None, "Khong duoc xoa dong agent — se mat lich su"
    assert not agent["enabled"]
    assert not verify_token(token, agent["token_hash"])
    assert agent["token_hash"] != hash_token(token)


def test_thu_hoi_agent_khong_ton_tai_thi_tra_false(seeded: Database) -> None:
    assert not thu_hoi_token(seeded, "AG-KHONG-CO")


# -- dọn log ----------------------------------------------------------------------------------

def test_don_log_cu_hon_30_ngay(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    cu = logs / "20250101.log"
    moi = logs / "20260906.log"
    cu.write_text("cu", encoding="utf-8")
    moi.write_text("moi", encoding="utf-8")
    qua_khu = time.time() - 60 * 24 * 3600
    os.utime(cu, (qua_khu, qua_khu))

    da_xoa = don_log_cu(logs, giu_ngay=30)
    assert cu not in list(logs.glob("*.log"))
    assert moi.exists()
    assert len(da_xoa) == 1


# -- kênh cảnh báo ------------------------------------------------------------------------------

class SenderGia:
    def __init__(self, hong: bool = False) -> None:
        self.da_gui: list[str] = []
        self.hong = hong

    def gui(self, text: str) -> bool:
        if self.hong:
            raise RuntimeError("mo phong mang chet")
        self.da_gui.append(text)
        return True


async def test_chi_gui_muc_error_va_critical(seeded: Database) -> None:
    kenh = AlertChannel(seeded, sender=SenderGia())
    seeded.create_alert("INFO", "MA_INFO", "khong gui")
    seeded.create_alert("WARNING", "MA_WARNING", "khong gui")
    seeded.create_alert("ERROR", "MA_ERROR", "co gui")
    seeded.create_alert("CRITICAL", "MA_CRITICAL", "co gui")

    assert await kenh.quet_mot_lan() == 2
    ten = " ".join(kenh.sender.da_gui)
    assert "MA_ERROR" in ten and "MA_CRITICAL" in ten
    assert "MA_INFO" not in ten and "MA_WARNING" not in ten


async def test_gop_cung_ma_loi_trong_cua_so(seeded: Database) -> None:
    """Một sự cố làm ngập điện thoại là cách nhanh nhất để người ta tắt thông báo."""
    kenh = AlertChannel(seeded, sender=SenderGia())
    for _ in range(5):
        seeded.create_alert("ERROR", "LAP_LAI", "cung mot su co")

    assert await kenh.quet_mot_lan() == 1
    assert kenh.da_nen == 4


async def test_critical_khong_bao_gio_bi_gop(seeded: Database) -> None:
    """Nếu phải chọn giữa làm phiền và bỏ sót, chọn làm phiền."""
    kenh = AlertChannel(seeded, sender=SenderGia())
    for _ in range(5):
        seeded.create_alert("CRITICAL", "RAT_NANG", "moi cai deu phai toi noi")

    assert await kenh.quet_mot_lan() == 5
    assert kenh.da_nen == 0


async def test_kenh_hong_khong_lam_sap_gi(seeded: Database) -> None:
    """Telegram chết, mạng chết — luồng copy vẫn chạy y nguyên."""
    kenh = AlertChannel(seeded, sender=SenderGia(hong=True))
    seeded.create_alert("CRITICAL", "MA_NANG", "thu gui")

    with pytest.raises(RuntimeError):
        # SenderGia nem thang; ban that (`TelegramSender`) nuot loi va tra False.
        await kenh.quet_mot_lan()

    # Quan trong hon: DB va luong nghiep vu khong he bi dung toi.
    assert seeded.query_one("SELECT COUNT(*) n FROM alert")["n"] >= 1


def test_telegram_sender_nuot_loi_mang_chu_khong_nem_len(monkeypatch: pytest.MonkeyPatch) -> None:
    from bridge.alerting import TelegramSender

    def no_mang(*a, **k):
        raise OSError("khong co mang")

    monkeypatch.setattr("urllib.request.urlopen", no_mang)
    assert TelegramSender("tok", "chat").gui("thu") is False


async def test_khoi_dong_lai_khong_doi_lai_lich_su_canh_bao(seeded: Database) -> None:
    """Khởi động lại không nên dội toàn bộ lịch sử cảnh báo vào điện thoại người vận hành."""
    for _ in range(3):
        seeded.create_alert("CRITICAL", "CU_ROI", "canh bao tu truoc")

    kenh = AlertChannel(seeded, sender=SenderGia())      # dung sau khi da co alert
    assert await kenh.quet_mot_lan() == 0

    seeded.create_alert("CRITICAL", "MOI", "canh bao moi")
    assert await kenh.quet_mot_lan() == 1


def test_thieu_cau_hinh_thi_kenh_im_lang_khong_loi(seeded: Database) -> None:
    kenh = tao_kenh(seeded, {})
    assert kenh.sender is None


def test_bo_gop_dung_cua_so_60_giay() -> None:
    gop = BoGop()
    assert gop.cua_so_sec == CUA_SO_GOP_SEC == 60
    assert gop.nen_gui("ERROR", "MA", 1000.0)
    assert not gop.nen_gui("ERROR", "MA", 1030.0)
    assert gop.nen_gui("ERROR", "MA", 1061.0)


def test_tin_nhan_co_muc_va_ma_loi() -> None:
    tin = TinNhan(level="CRITICAL", code="MAT_HEDGE", text="chi tiet").render()
    assert "CRITICAL" in tin and "MAT_HEDGE" in tin and "chi tiet" in tin


# -- khởi động (D-15) ---------------------------------------------------------------------------

def test_khoi_dong_ep_run_mode_ve_paused(seeded: Database) -> None:
    """D-15 không có ngoại lệ: mất điện lúc đang `RUNNING` thì bật lại vẫn phải `PAUSED`."""
    from bridge.__main__ import ep_ve_paused

    seeded.set_config("run_mode", "RUNNING")
    assert ep_ve_paused(seeded) == "RUNNING"
    assert seeded.get_config("run_mode") == "PAUSED"
    assert seeded.query_one(
        "SELECT COUNT(*) n FROM alert WHERE code = 'KHOI_DONG_EP_PAUSED'")["n"] == 1


def test_dang_paused_thi_khong_sinh_canh_bao(seeded: Database) -> None:
    from bridge.__main__ import ep_ve_paused

    seeded.set_config("run_mode", "PAUSED")
    assert ep_ve_paused(seeded) == "PAUSED"
    assert seeded.query_one(
        "SELECT COUNT(*) n FROM alert WHERE code = 'KHOI_DONG_EP_PAUSED'")["n"] == 0


# -- công cụ dòng lệnh --------------------------------------------------------------------------

def test_admin_them_agent_roi_cap_lai_token(db: Database, monkeypatch, capsys) -> None:
    """Cấp agent/token phải là một lệnh có tên, không phải script tạm viết lại mỗi lần."""
    from bridge import admin

    monkeypatch.setattr(admin, "_mo_db", lambda: (db, Path("bridge.db")))
    monkeypatch.setattr(db, "close", lambda: None)

    assert admin.main(["them-agent", "AG-THU", "--role", "CLICKER", "--magic", "1"]) == 0
    tok_dau = _doc_token(capsys)
    assert verify_token(tok_dau, db.get_agent("AG-THU")["token_hash"])

    # Tao trung thi tu choi chu khong lang le ghi de token dang chay.
    assert admin.main(["them-agent", "AG-THU", "--role", "CLICKER", "--magic", "1"]) == 1

    assert admin.main(["cap-token", "AG-THU"]) == 0
    tok_moi = _doc_token(capsys)
    assert tok_moi != tok_dau
    assert not verify_token(tok_dau, db.get_agent("AG-THU")["token_hash"])

    assert admin.main(["thu-hoi", "AG-THU"]) == 0
    assert not db.get_agent("AG-THU")["enabled"]


def _doc_token(capsys) -> str:
    dong = [d.strip() for d in capsys.readouterr().out.splitlines() if d.strip()]
    return dong[-2]


def test_admin_thu_hoi_agent_khong_co_thi_bao_loi(db: Database, monkeypatch) -> None:
    from bridge import admin

    monkeypatch.setattr(admin, "_mo_db", lambda: (db, Path("bridge.db")))
    monkeypatch.setattr(db, "close", lambda: None)
    assert admin.main(["thu-hoi", "AG-KHONG-CO"]) == 1


def test_admin_doc_va_dat_run_mode(db: Database, monkeypatch, capsys) -> None:
    from bridge import admin

    monkeypatch.setattr(admin, "_mo_db", lambda: (db, Path("bridge.db")))
    monkeypatch.setattr(db, "close", lambda: None)
    assert admin.main(["run-mode", "RUNNING"]) == 0
    assert db.get_config("run_mode") == "RUNNING"
    capsys.readouterr()
    assert admin.main(["run-mode"]) == 0
    assert capsys.readouterr().out.strip() == "RUNNING"


# -- TEST-23 ------------------------------------------------------------------------------------

def test_kiem_reason_client_bat_dung_cap_sai_kenh(seeded: Database) -> None:
    """Một cặp sai kênh giữa hai chục cặp đúng — đúng thứ nhìn bằng mắt sẽ bỏ sót."""
    from bridge.ops import kiem_reason_client

    pair_id = seeded.create_pending_pair(
        MASTER_POSITION_ID, client_id=CLIENT_ID, copy_mode="OPPOSITE",
        master_initial_volume=1.0, effective_multiplier=1.0)
    with seeded.transaction() as conn:
        conn.execute("UPDATE pair SET client_open_reason = 0")
    assert kiem_reason_client(seeded) == []

    with seeded.transaction() as conn:
        conn.execute("UPDATE pair SET client_open_reason = 3 WHERE pair_id = ?", (pair_id,))
    vi_pham = kiem_reason_client(seeded)
    assert len(vi_pham) == 1
    assert vi_pham[0]["client_open_reason"] == 3
    assert vi_pham[0]["pair_id"] == pair_id


def test_cap_chua_mo_duoc_khong_bi_tinh_la_vi_pham(seeded: Database) -> None:
    """`client_open_reason IS NULL` = chua co deal nao ben Client, khong phai sai kenh."""
    from bridge.ops import kiem_reason_client

    with seeded.transaction() as conn:
        conn.execute("UPDATE pair SET client_open_reason = NULL")
    assert kiem_reason_client(seeded) == []


def test_cap_token_bat_lai_agent_da_thu_hoi(seeded: Database) -> None:
    """B-10: cấp token cho agent đã thu hồi phải làm nó nối lại được, không im lặng thất bại.

    Bản đầu chỉ đổi hash, nên người vận hành nhận một token trông hợp lệ rồi agent vẫn bị từ chối
    bắt tay với `AGENT_DISABLED` — và không có gì chỉ ra vì sao.
    """
    assert thu_hoi_token(seeded, MASTER_AGENT)
    assert not seeded.get_agent(MASTER_AGENT)["enabled"]

    token = cap_token(seeded, MASTER_AGENT)
    agent = seeded.get_agent(MASTER_AGENT)
    assert agent["enabled"], "Cap token xong ma agent van bi vo hieu hoa"
    assert verify_token(token, agent["token_hash"])


# -- B-11: lenh admin doi cau hinh Client -------------------------------------------------------

def test_admin_doi_cau_hinh_client(seeded: Database, monkeypatch, capsys) -> None:
    """Sửa cấu hình giao dịch bằng SQL tay là chỗ dễ gõ nhầm nhất; nó xứng đáng có một lệnh."""
    from bridge import admin

    monkeypatch.setattr(admin, "_mo_db", lambda: (seeded, Path("bridge.db")))
    monkeypatch.setattr(seeded, "close", lambda: None)

    assert admin.main(["cau-hinh-client", CLIENT_ID]) == 0
    assert "copy_mode=OPPOSITE" in capsys.readouterr().out

    assert admin.main(["cau-hinh-client", CLIENT_ID,
                       "--copy-mode", "SAME", "--multiplier", "0.5"]) == 0
    row = seeded.get_client_account(CLIENT_ID)
    assert row["copy_mode"] == "SAME"
    assert row["volume_multiplier"] == 0.5


def test_admin_tu_choi_multiplier_khong_duong(seeded: Database, monkeypatch) -> None:
    from bridge import admin

    monkeypatch.setattr(admin, "_mo_db", lambda: (seeded, Path("bridge.db")))
    monkeypatch.setattr(seeded, "close", lambda: None)
    assert admin.main(["cau-hinh-client", CLIENT_ID, "--multiplier", "0"]) == 1
    assert seeded.get_client_account(CLIENT_ID)["volume_multiplier"] == 1.0


def test_admin_canh_bao_cap_dang_chay_giu_nguyen_ty_le(seeded: Database, monkeypatch,
                                                       capsys) -> None:
    """D-19: đổi hệ số giữa chừng không đụng cặp đang chạy — lệnh phải nói rõ điều đó."""
    from bridge import admin

    seeded.create_pending_pair(MASTER_POSITION_ID, client_id=CLIENT_ID, copy_mode="OPPOSITE",
                               master_initial_volume=1.0, effective_multiplier=1.0)
    monkeypatch.setattr(admin, "_mo_db", lambda: (seeded, Path("bridge.db")))
    monkeypatch.setattr(seeded, "close", lambda: None)

    assert admin.main(["cau-hinh-client", CLIENT_ID, "--multiplier", "5.0"]) == 0
    assert "giu nguyen ty le cu" in capsys.readouterr().out


def test_admin_tu_choi_open_route_UI_khi_chua_co_clicker(seeded: Database, monkeypatch) -> None:
    from bridge import admin

    monkeypatch.setattr(admin, "_mo_db", lambda: (seeded, Path("bridge.db")))
    monkeypatch.setattr(seeded, "close", lambda: None)
    assert admin.main(["cau-hinh-client", CLIENT_ID, "--open-route", "UI"]) == 1


# -- B-12: don so sach ---------------------------------------------------------------------------

def test_don_so_sach_dua_volume_master_ve_0(seeded: Database) -> None:
    """Cặp `CLOSED` mà vẫn còn volume Master là tàn dư của các bản sửa trước."""
    from bridge.ops import don_so_sach

    pair_id = seeded.create_pending_pair(
        MASTER_POSITION_ID, client_id=CLIENT_ID, copy_mode="OPPOSITE",
        master_initial_volume=1.0, effective_multiplier=1.0)
    seeded.set_master_position_status(MASTER_POSITION_ID, "CLOSED", current_volume=0.0)
    with seeded.transaction() as conn:
        conn.execute("UPDATE pair SET status = 'CLOSED', master_current_volume = 0.02 "
                     "WHERE pair_id = ?", (pair_id,))

    assert don_so_sach(seeded) == 1
    assert seeded.get_pair(pair_id)["master_current_volume"] == 0
    assert don_so_sach(seeded) == 0, "Chay lai khong duoc sua them gi"


def test_don_so_sach_khong_dung_toi_cap_ma_master_con_mo(seeded: Database) -> None:
    """Không suy diễn: vị thế Master còn `OPEN` thì con số kia là **thật**, không phải rác."""
    from bridge.ops import don_so_sach

    pair_id = seeded.create_pending_pair(
        MASTER_POSITION_ID, client_id=CLIENT_ID, copy_mode="OPPOSITE",
        master_initial_volume=1.0, effective_multiplier=1.0)
    with seeded.transaction() as conn:
        conn.execute("UPDATE pair SET status = 'CLOSED', master_current_volume = 0.02 "
                     "WHERE pair_id = ?", (pair_id,))

    assert don_so_sach(seeded) == 0
    assert seeded.get_pair(pair_id)["master_current_volume"] == 0.02


# -- tinh-hinh: co che bu khi khong co canh bao ra ngoai ----------------------------------------

def _tinh_hinh(db: Database, monkeypatch, tmp_path: Path):
    """Chạy lệnh với thư mục sao lưu thật, trả về (mã thoát, hàm đọc màn hình)."""
    from bridge import admin

    db_path = tmp_path / "bridge.db"
    (tmp_path / "backup").mkdir(exist_ok=True)
    (tmp_path / "backup" / "bridge-20260906-000000.db").write_bytes(b"x")
    monkeypatch.setattr(admin, "_mo_db", lambda: (db, db_path))
    monkeypatch.setattr(db, "close", lambda: None)
    return admin.main(["tinh-hinh"])


def test_tinh_hinh_moi_thu_khoe_thi_thoat_0(seeded: Database, monkeypatch, tmp_path,
                                            capsys) -> None:
    """Không được bịa ra cảnh báo giả: im lặng phải nghĩa là thật sự không có gì."""
    seeded.set_config("run_mode", "RUNNING")
    with seeded.transaction() as conn:
        conn.execute("UPDATE agent SET status = 'ONLINE', broker_connected = 1, "
                     "trade_allowed = 1")

    assert _tinh_hinh(seeded, monkeypatch, tmp_path) == 0
    ra = capsys.readouterr().out
    assert "Khong co gi can lam" in ra
    assert "can chu y" not in ra


def test_tinh_hinh_paused_thi_bao_dang_khong_copy(seeded: Database, monkeypatch, tmp_path,
                                                  capsys) -> None:
    """`PAUSED` là trạng thái sau mỗi lần khởi động lại (D-15) — và nó nghĩa là ngừng copy."""
    seeded.set_config("run_mode", "PAUSED")
    with seeded.transaction() as conn:
        conn.execute("UPDATE agent SET status = 'ONLINE', broker_connected = 1, "
                     "trade_allowed = 1")

    assert _tinh_hinh(seeded, monkeypatch, tmp_path) == 1
    ra = capsys.readouterr().out
    assert "DANG KHONG COPY" in ra
    assert "run_mode = PAUSED" in ra


def test_tinh_hinh_bat_algo_trading_tat(seeded: Database, monkeypatch, tmp_path,
                                        capsys) -> None:
    """B-09: terminal tắt Algo Trading vẫn mở được lệnh nhưng không đóng được."""
    seeded.set_config("run_mode", "RUNNING")
    with seeded.transaction() as conn:
        conn.execute("UPDATE agent SET status = 'ONLINE', broker_connected = 1, "
                     "trade_allowed = 1")
        conn.execute("UPDATE agent SET trade_allowed = 0 WHERE role = 'CLIENT'")

    assert _tinh_hinh(seeded, monkeypatch, tmp_path) == 1
    assert "Algo Trading: TAT" in capsys.readouterr().out


def test_tinh_hinh_dem_canh_bao_chua_xem(seeded: Database, monkeypatch, tmp_path,
                                         capsys) -> None:
    """Đã xác nhận rồi thì không đếm nữa — nếu không, con số chỉ tăng và mất ý nghĩa."""
    seeded.set_config("run_mode", "RUNNING")
    with seeded.transaction() as conn:
        conn.execute("UPDATE agent SET status = 'ONLINE', broker_connected = 1, "
                     "trade_allowed = 1")
    seeded.create_alert("ERROR", "THU_MOT", "chua xem")
    seeded.create_alert("CRITICAL", "THU_HAI", "chua xem")
    seeded.create_alert("WARNING", "THU_BA", "muc thap, khong tinh")

    assert _tinh_hinh(seeded, monkeypatch, tmp_path) == 1
    assert "canh bao chua xem  : 2" in capsys.readouterr().out

    with seeded.transaction() as conn:
        conn.execute("UPDATE alert SET acknowledged_at = '2026-09-06T00:00:00.000Z'")
    assert _tinh_hinh(seeded, monkeypatch, tmp_path) == 0
    assert "canh bao chua xem  : 0" in capsys.readouterr().out


def test_tinh_hinh_bao_sai_lech_dang_cho_kem_tuoi(seeded: Database, monkeypatch, tmp_path,
                                                  capsys) -> None:
    seeded.set_config("run_mode", "RUNNING")
    with seeded.transaction() as conn:
        conn.execute("UPDATE agent SET status = 'ONLINE', broker_connected = 1, "
                     "trade_allowed = 1")
    seeded.create_finding("REC-TEST", "SAFE", "THU_NGHIEM", suggested_action="NOTHING")

    assert _tinh_hinh(seeded, monkeypatch, tmp_path) == 1
    assert "sai lech dang cho  : 1" in capsys.readouterr().out


# -- anh xa symbol -------------------------------------------------------------------------------

def _admin(db: Database, monkeypatch, tmp_path: Path):
    from bridge import admin
    monkeypatch.setattr(admin, "_mo_db", lambda: (db, tmp_path / "bridge.db"))
    monkeypatch.setattr(db, "close", lambda: None)
    return admin


def test_chua_co_anh_xa_thi_bao_va_thoat_khac_0(seeded: Database, monkeypatch, tmp_path,
                                                capsys) -> None:
    """Không có ánh xạ nghĩa là **không copy được lệnh nào** — không được im lặng báo thành công."""
    admin = _admin(seeded, monkeypatch, tmp_path)
    assert admin.main(["anh-xa-symbol", CLIENT_ID]) == 1
    assert "CHUA CO anh xa" in capsys.readouterr().out


def test_khai_bao_anh_xa_kiem_symbol_co_that_tren_san(seeded: Database, monkeypatch, tmp_path,
                                                      capsys) -> None:
    """Sai tên symbol là lỗi không hiện ra cho tới lúc có lệnh thật đi qua — nên phải chặn tại đây."""
    admin = _admin(seeded, monkeypatch, tmp_path)
    seeded.replace_symbol_specs(CLIENT_AGENT, [{
        "symbol": "XAUUSDm", "digits": 2, "point": 0.01, "volume_min": 0.01,
        "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])

    # Symbol khong ton tai tren san Client -> tu choi, va goi y nhung symbol dang co.
    assert admin.main(["anh-xa-symbol", CLIENT_ID, "XAUUSD", "--client-symbol", "GO-KHONG-CO"]) == 1
    loi = capsys.readouterr().err
    assert "chua bao co symbol" in loi and "XAUUSDm" in loi

    assert admin.main(["anh-xa-symbol", CLIENT_ID, "XAUUSD", "--client-symbol", "XAUUSDm"]) == 0
    hang = seeded.find_symbol_map(CLIENT_ID, "XAUUSD")
    assert hang["client_symbol"] == "XAUUSDm"
    assert hang["enabled"] == 1
    assert hang["verified_at"] is not None, "Phai danh dau da kiem voi san"


def test_tat_anh_xa(seeded: Database, monkeypatch, tmp_path) -> None:
    admin = _admin(seeded, monkeypatch, tmp_path)
    seeded.replace_symbol_specs(CLIENT_AGENT, [{
        "symbol": "XAUUSDm", "digits": 2, "point": 0.01, "volume_min": 0.01,
        "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])
    admin.main(["anh-xa-symbol", CLIENT_ID, "XAUUSD", "--client-symbol", "XAUUSDm"])

    assert admin.main(["anh-xa-symbol", CLIENT_ID, "XAUUSD", "--tat"]) == 0
    assert seeded.find_symbol_map(CLIENT_ID, "XAUUSD")["enabled"] == 0
