"""Test dashboard (plan `09-dashboard.md`).

Trọng tâm không phải bố cục mà là những chỗ giao diện có thể làm mất tiền:

* Nút đóng khẩn cấp không được làm gì cho tới khi gõ đúng chuỗi.
* `accept_all_safe` không được chạm tới dòng `DECISION` nào.
* Không tồn tại đường nào bỏ qua hàng loạt.
* Bảng cặp lệnh phải sắp theo **mức nghiêm trọng**, không theo thời gian.
* Thiếu một nhãn thì hiển thị chính enum đó chứ không được làm sập trang.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from bridge.clock import to_iso, utc_now
from bridge.config import parse_config
from bridge.db.repo import Database
from bridge.labels_vi import UI
from bridge.ops import (
    dat_terminal_clicker,
    dat_tich_huong_dan,
    doc_tich_huong_dan,
    ghi_moc_cap_nhat,
    ma_client_ke_tiep,
)
from bridge.protocol.auth import verify_token
from bridge.web import views
from bridge.web.app import CUM_DAT_LAI, Dashboard, tao_app
from tests.conftest import CLIENT_AGENT, CLIENT_ID, MASTER_AGENT


def _cap(db: Database, master_pos: int, status: str = "OPEN",
         orphan_side: str | None = None, reason: int | None = 0) -> str:
    db.upsert_master_position(master_pos, agent_id=MASTER_AGENT, symbol="XAUUSD",
                              direction="BUY", initial_volume=1.0, current_volume=1.0,
                              status="OPEN")
    pair_id = db.create_pending_pair(
        master_pos, CLIENT_ID, copy_mode="OPPOSITE", master_initial_volume=1.0,
        effective_multiplier=0.5, client_symbol="XAUUSDm", client_direction="SELL",
        open_time_master=to_iso(utc_now()))
    db.mark_pair_open(pair_id, client_position_id=master_pos + 500_000,
                      client_ticket=None, client_volume=0.5,
                      open_time_client=to_iso(utc_now()))
    fields: dict = {"client_open_reason": reason}
    if status != "OPEN":
        fields["status"] = status
    if orphan_side:
        fields["orphan_side"] = orphan_side
    db.update_pair(pair_id, **fields)
    return pair_id


@pytest.fixture
def seeded_web(db: Database) -> Database:
    db.upsert_agent(MASTER_AGENT, role="MASTER", token_hash="h", magic_number=770001,
                    account_login=1)
    db.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash="h", magic_number=770001,
                    account_login=2)
    db.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, copy_mode="OPPOSITE",
                             volume_multiplier=0.5)
    return db


def _http(app) -> httpx.AsyncClient:
    """Client chạy app **trong cùng luồng** với test.

    Không dùng `TestClient` của Starlette: nó chạy app ở một thread riêng, mà `Database` cố ý
    giữ đúng một kết nối SQLite đơn luồng (xem ghi chú đầu `protocol/server.py`). Đây là giới
    hạn của công cụ test, không phải của sản phẩm — trong thực tế dashboard chạy chung vòng lặp
    asyncio với Bridge.
    """
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                             base_url="http://test")


@pytest.fixture
async def client(seeded_web: Database) -> AsyncIterator[httpx.AsyncClient]:
    """Dashboard **có mật khẩu** và đã đăng nhập — đúng cấu hình thật trên VPS.

    Các endpoint ghi cấu hình đòi dashboard có mật khẩu (`_chan_ghi`): không mật khẩu thì
    `hop_le` cho qua mọi request, và khi đó một cổng 8080 chạm được là sửa được chiều copy, hệ
    số volume và cả `config.toml`.
    """
    async with _http(tao_app(Dashboard(seeded_web))) as c:
        yield c


# -- nút nguy hiểm ----------------------------------------------------------------------------

async def test_khong_con_duong_dong_khan_cap_nao_tren_dashboard(client: httpx.AsyncClient,
                                                                seeded_web: Database) -> None:
    """Đóng khẩn cấp đã rời khỏi dashboard hẳn — cả nút lẫn endpoint (D-33).

    Vẫn đóng tất cả được bằng `bridge.admin run-mode EMERGENCY`; cái bỏ đi là một nút đóng sạch
    vị thế nằm ngay trên trang.
    """
    _cap(seeded_web, 900001)
    r = await client.post("/api/emergency", json={"phrase": "DONG TAT CA"})
    assert r.status_code == 404
    assert not seeded_web.query_all("SELECT 1 FROM command"), "Khong duoc sinh command nao"


async def test_cum_xac_nhan_dat_lai_khong_dau_va_khac_nhau(client: httpx.AsyncClient) -> None:
    """Cụm có dấu thì phụ thuộc bộ gõ; hai cụm giống nhau thì nhầm mức này sang mức kia."""
    assert all(cum.isascii() for cum in CUM_DAT_LAI.values())
    assert CUM_DAT_LAI["lich_su"] != CUM_DAT_LAI["toan_bo"]


async def test_doi_run_mode_sang_gia_tri_la_bi_tu_choi(client: httpx.AsyncClient,
                                                 seeded_web: Database) -> None:
    r = await client.post("/api/run_mode", json={"mode": "TU_CHAY"})
    assert r.status_code == 400
    assert seeded_web.get_config("run_mode") == "PAUSED"


def test_khong_co_duong_nao_bo_qua_hang_loat(seeded_web: Database) -> None:
    """Nút bỏ qua hàng loạt là cách mất tiền âm thầm nhất — nó không được tồn tại."""
    app = tao_app(Dashboard(seeded_web))
    duong = {getattr(r, "path", "") for r in app.routes}
    assert not [d for d in duong if "skip" in d and "{finding_id}" not in d]


# -- bảng cặp lệnh ----------------------------------------------------------------------------

def test_bang_cap_sap_theo_muc_nghiem_trong_khong_theo_thoi_gian(seeded_web: Database) -> None:
    """20 cặp OPEN và 1 cặp ORPHANED → cặp ORPHANED phải ở dòng đầu.

    Sắp theo thời gian sẽ chôn cặp cần cứu xuống giữa danh sách, đúng lúc cần thấy nó nhất.
    """
    for i in range(20):
        _cap(seeded_web, 900001 + i)
    mo_coi = _cap(seeded_web, 900999, status="ORPHANED", orphan_side="MASTER")

    bang = views.bang_cap_lenh(seeded_web)
    assert bang[0]["pair_id"] == mo_coi
    assert bang[0]["attention"] is True


def test_orphaned_noi_ro_ben_nao_con_vi_the(seeded_web: Database) -> None:
    """Hành động xử lý hai trường hợp khác hẳn nhau, nên nhãn phải nói rõ."""
    _cap(seeded_web, 900001, status="ORPHANED", orphan_side="MASTER")
    _cap(seeded_web, 900002, status="ORPHANED", orphan_side="CLIENT")

    nhan = {c["pair_id"]: c["status_label"] for c in views.bang_cap_lenh(seeded_web)}
    assert UI["orphan_master_left"] in nhan.values()
    assert UI["orphan_client_left"] in nhan.values()


def test_cap_mo_qua_giao_dien_sai_reason_thi_noi_bat(seeded_web: Database) -> None:
    """Đó là dấu hiệu phase 6b đã ngừng hoạt động, không phải sai lệch giao dịch thông thường."""
    seeded_web.upsert_agent("AG-CLICKER", role="CLICKER", token_hash="h", magic_number=0)
    seeded_web.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT, open_route="UI",
                                     clicker_agent_id="AG-CLICKER")
    _cap(seeded_web, 900001, reason=3)          # 3 = EXPERT
    _cap(seeded_web, 900002, reason=0)          # 0 = CLIENT, dung

    bang = {c["pair_id"].rsplit("-", 1)[-1]: c for c in views.bang_cap_lenh(seeded_web)}
    sai = [c for c in bang.values() if c["reason_mismatch"]]
    assert len(sai) == 1
    assert sai[0]["reason_mismatch_label"] == UI["reason_mismatch"]


def test_khong_hien_thi_lai_lo(seeded_web: Database) -> None:
    """Đây là công cụ đồng bộ hedge, không phải terminal giao dịch."""
    _cap(seeded_web, 900001)
    khoa = set(views.bang_cap_lenh(seeded_web)[0])
    assert not [k for k in khoa if "profit" in k or "pnl" in k or "lai" in k]


# -- ô chỉ số ---------------------------------------------------------------------------------

def test_o_can_can_thiep_bang_0_thi_khong_to_do(seeded_web: Database) -> None:
    """Nếu luôn đỏ, mắt sẽ quen và bỏ qua."""
    _cap(seeded_web, 900001)
    assert views.chi_so(seeded_web)["attention_alarm"] is False

    _cap(seeded_web, 900002, status="ORPHANED", orphan_side="MASTER")
    assert views.chi_so(seeded_web)["attention_alarm"] is True


def test_do_tre_copy_la_phan_vi_khong_phai_gia_tri_tuc_thoi(seeded_web: Database) -> None:
    _cap(seeded_web, 900001)
    m = views.chi_so(seeded_web)
    assert "p50" in m and "p95" in m
    assert m["mau"] >= 1


# -- màn hình sai lệch -------------------------------------------------------------------------

async def test_moi_dong_sai_lech_hien_du_ba_nguon(client: httpx.AsyncClient, seeded_web: Database) -> None:
    """Đưa cho người vận hành một dòng "cặp 118 bất thường" là bắt họ tin bot mù quáng."""
    pair_id = _cap(seeded_web, 900001)
    seeded_web.create_finding(
        "REC-1", "SAFE", "MASTER_CLOSED_OFFLINE", suggested_action="CLOSE_CLIENT",
        pair_id=pair_id,
        evidence_json='{"db": {"status": "OPEN"}, "master": null, '
                      '"client": {"position_id": 1}}')

    data = (await client.get("/api/findings")).json()
    dong = data["safe"][0]
    assert dong["evidence"]["db_label"] == UI["evidence_db"]
    assert dong["evidence"]["master_label"] == UI["evidence_master"]
    assert dong["evidence"]["client_label"] == UI["evidence_client"]
    assert dong["evidence"]["db"] == {"status": "OPEN"}
    assert dong["evidence"]["master"] is None
    assert dong["evidence"]["client"] == {"position_id": 1}


async def test_sai_lech_tach_theo_muc_an_toan(client: httpx.AsyncClient, seeded_web: Database) -> None:
    p1 = _cap(seeded_web, 900001)
    p2 = _cap(seeded_web, 900002)
    seeded_web.create_finding("REC-1", "SAFE", "BOTH_CLOSED", pair_id=p1)
    seeded_web.create_finding("REC-1", "DECISION", "CLIENT_CLOSED_OFFLINE", pair_id=p2)

    data = (await client.get("/api/findings")).json()
    assert len(data["safe"]) == 1 and len(data["decision"]) == 1
    assert data["tong"] == 2


def test_danh_sach_lay_moi_finding_dang_cho_khong_theo_run_id(seeded_web: Database) -> None:
    """Bộ đối chiếu có cổng lọc trùng: sai lệch cũ không xuất hiện lại trong `run_id` mới.

    Lọc theo `run_id` sẽ giấu mất chính những dòng chưa ai xử lý — tôi đã tự vấp đúng chỗ này
    khi viết kịch bản nghiệm thu phase 8.
    """
    p1 = _cap(seeded_web, 900001)
    p2 = _cap(seeded_web, 900002)
    seeded_web.create_finding("REC-CU", "SAFE", "BOTH_CLOSED", pair_id=p1)
    seeded_web.create_finding("REC-MOI", "SAFE", "BOTH_CLOSED", pair_id=p2)

    assert views.danh_sach_sai_lech(seeded_web)["tong"] == 2


# -- nhãn -------------------------------------------------------------------------------------

def test_thieu_nhan_thi_hien_chinh_enum_khong_sap_trang(seeded_web: Database,
                                                        caplog: pytest.LogCaptureFixture) -> None:
    """Thêm một enum mới vào DB mà quên nhãn → hiển thị chính enum đó, ghi WARNING."""
    pair_id = _cap(seeded_web, 900001)
    with seeded_web.transaction() as conn:
        conn.execute("PRAGMA writable_schema = ON")
    seeded_web.update_pair(pair_id, status="CLOSING")
    # `CLOSING` co nhan; gio thu mot gia tri KHONG co nhan bang cach goi thang label().
    from bridge.labels_vi import PAIR_STATUS, label
    assert label(PAIR_STATUS, "TRANG_THAI_MOI_TINH") == "TRANG_THAI_MOI_TINH"
    assert views.bang_cap_lenh(seeded_web), "Trang van phai ve duoc"


def test_khong_co_chuoi_tieng_viet_nao_trong_html_va_js(project_root) -> None:
    """D-16: template và JavaScript không được chứa nhãn tiếng Việt.

    Chữ đi từ `bridge/labels_vi.py` xuống qua JSON. Đây chính là phép kiểm mà quy tắc đó tồn
    tại để cho phép.
    """
    # Kiem bang cach dao nguoc: file phai la ASCII, tru mot danh sach ky tu **kieu chu** duoc
    # phep. Liet ke dau tieng Viet thi de sot (bang chu co hon 130 ky tu co dau); liet ke thu
    # duoc phep thi khong sot duoc.
    ky_tu_duoc_phep = set("·→—✕✓")
    for ten in ("index.html", "app.js"):
        noi_dung = (project_root / "bridge" / "web" / "static" / ten).read_text(
            encoding="utf-8")
        lot = {c for c in noi_dung if not c.isascii()} - ky_tu_duoc_phep
        assert not lot, f"{ten} chua ky tu ngoai ASCII: {sorted(lot)}"


# -- ánh xạ symbol ----------------------------------------------------------------------------

async def test_kiem_tra_symbol_khong_ton_tai_tren_san_thi_bao_loi(client: httpx.AsyncClient,
                                                            seeded_web: Database) -> None:
    r = await client.post("/api/symbol_map/verify",
                    json={"client_id": CLIENT_ID, "client_symbol": "XAUUSDn"})
    assert r.status_code == 400
    assert r.json()["message"] == UI["map_verify_failed"]


async def test_kiem_tra_symbol_co_ky_tu_cyrillic_bi_bat(client: httpx.AsyncClient,
                                                  seeded_web: Database) -> None:
    """Tên copy từ website broker có thể chứa ký tự Cyrillic nhìn giống hệt chữ Latin.

    Chỉ có đối chiếu với spec sàn đẩy lên mới bắt được — mắt thường thì không.
    """
    seeded_web.replace_symbol_specs(CLIENT_AGENT, [{
        "symbol": "XAUUSDm", "digits": 2, "point": 0.01, "volume_min": 0.01,
        "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])
    r_ok = await client.post("/api/symbol_map/verify",
                             json={"client_id": CLIENT_ID, "client_symbol": "XAUUSDm"})
    assert r_ok.status_code == 200

    gia_mao = "XAUUSD" + "а"      # U+0430 CYRILLIC SMALL LETTER A, nhin giong 'a'
    r = await client.post("/api/symbol_map/verify",
                    json={"client_id": CLIENT_ID, "client_symbol": gia_mao})
    assert r.status_code == 400


# -- xem trước hệ số --------------------------------------------------------------------------

def test_xem_truoc_he_so_hien_ca_truong_hop_that_bai() -> None:
    """Nhìn trường hợp đẹp thì ai cũng thấy ổn; chỉ dòng thứ hai mới lộ ra hệ số làm rơi lệnh nhỏ."""
    dong = views.xem_truoc_he_so(0.5)
    assert len(dong) == 2
    assert "1.00" in dong[0]
    assert "bỏ qua lệnh" in dong[1], dong[1]
    assert "0.01" in dong[1]


def test_xem_truoc_he_so_1_thi_khong_rot_lenh_nao() -> None:
    dong = views.xem_truoc_he_so(1.0)
    assert not [d for d in dong if "bỏ qua" in d]


def test_khong_phu_thuoc_gi_ngoai_may(project_root) -> None:
    """Đúng lúc mất mạng là lúc cần nhìn thấy trạng thái nhất.

    Không CDN, không font tải về, không API ngoài. Toàn bộ dữ liệu đọc thẳng từ SQLite cục bộ.
    """
    import re
    for ten in ("index.html", "app.js", "app.css"):
        noi_dung = (project_root / "bridge" / "web" / "static" / ten).read_text(
            encoding="utf-8")
        ngoai = re.findall(r"https?://[^\s\"')]+", noi_dung)
        assert not ngoai, f"{ten} tham chieu ra ngoai may: {ngoai}"


async def test_dashboard_hien_trang_thai_algo_trading(seeded: Database) -> None:
    """B-09: người vận hành phải NHÌN THẤY được, không phải đợi lệnh đóng thất bại mới biết."""
    with seeded.transaction() as conn:
        conn.execute("UPDATE agent SET trade_allowed = 0 WHERE role = 'CLIENT'")
        conn.execute("UPDATE agent SET trade_allowed = 1 WHERE role = 'MASTER'")

    agents = views.trang_thai_chung(seeded)["agents"]
    client = next(a for a in agents if a["role"] == "CLIENT")
    master = next(a for a in agents if a["role"] == "MASTER")

    assert client["trade_allowed"] is False
    assert "TẮT" in client["canh_bao"]
    assert master["trade_allowed"] is True
    assert "canh_bao" not in master


async def test_khong_bao_biet_thi_hien_khong_biet(seeded: Database) -> None:
    """`NULL` phải hiện là "không biết", không được hiển thị thành "ổn"."""
    with seeded.transaction() as conn:
        conn.execute("UPDATE agent SET trade_allowed = NULL")

    for a in views.trang_thai_chung(seeded)["agents"]:
        if a["role"] != "CLICKER":
            assert a["trade_allowed"] is None
            assert "canh_bao" not in a


# -- API ghi cấu hình -------------------------------------------------------------------------
#
# Ràng buộc nằm ở `bridge/ops.py` và đã có test riêng ở `tests/test_ops.py`. Ở đây chỉ kiểm phần
# việc của tầng web: gọi đúng hàm, trả đúng mã lỗi kèm câu tiếng Việt, và **không** cho ai chưa
# đăng nhập đi qua.


@pytest.fixture
def clicker_web(seeded_web: Database) -> Database:
    seeded_web.upsert_agent("AG-CLICKER", role="CLICKER", token_hash="h", magic_number=770001,
                            account_login=2)
    seeded_web.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT,
                                     clicker_agent_id="AG-CLICKER")
    return seeded_web


async def test_sua_client_tren_dashboard_ghi_vao_db(client: httpx.AsyncClient,
                                                    seeded_web: Database) -> None:
    r = await client.post(f"/api/client/{CLIENT_ID}",
                          json={"copy_mode": "SAME", "volume_multiplier": 0.25})
    assert r.status_code == 200
    assert r.json()["doi"] == {"copy_mode": "SAME", "volume_multiplier": 0.25}
    dong = seeded_web.get_client_account(CLIENT_ID)
    assert dong["copy_mode"] == "SAME"
    assert dong["volume_multiplier"] == 0.25


async def test_sua_client_sai_rang_buoc_thi_tra_ma_loi_va_cau_tieng_viet(
        client: httpx.AsyncClient, seeded_web: Database) -> None:
    r = await client.post(f"/api/client/{CLIENT_ID}", json={"close_route": "UI"})
    assert r.status_code == 400
    assert r.json()["error"] == "CAN_CLICKER"
    assert r.json()["message"].strip()
    assert seeded_web.get_client_account(CLIENT_ID)["close_route"] == "EA"


async def test_bat_duong_dong_master_qua_dashboard(clicker_web: Database) -> None:
    """Clicker của Client không dùng lại được cho Master — hai terminal khác nhau."""
    async with _http(tao_app(Dashboard(clicker_web))) as c:
        r = await c.post("/api/master_close_route",
                         json={"clicker_agent": "AG-CLICKER", "close_route": "UI"})
        assert r.status_code == 400
        assert r.json()["error"] == "CLICKER_DA_DUNG"

        clicker_web.upsert_agent("AG-CLICKER-MASTER", role="CLICKER", token_hash="h",
                                 magic_number=770001, account_login=1)
        r = await c.post("/api/master_close_route",
                         json={"clicker_agent": "AG-CLICKER-MASTER", "close_route": "UI"})
        assert r.status_code == 200
    assert clicker_web.get_config("master_close_route") == "UI"


async def test_luu_anh_xa_symbol_kiem_voi_san_truoc_khi_ghi(client: httpx.AsyncClient,
                                                            seeded_web: Database) -> None:
    seeded_web.replace_symbol_specs(CLIENT_AGENT, [
        {"symbol": "XAUUSDm", "volume_min": 0.01, "volume_step": 0.01, "volume_max": 50.0,
         "digits": 2, "contract_size": 100.0},
    ])
    r = await client.post("/api/symbol_map", json={"client_id": CLIENT_ID,
                                                   "master_symbol": "XAUUSD",
                                                   "client_symbol": "XAUUSDn"})
    assert r.status_code == 400
    assert r.json()["error"] == "SAN_KHONG_CO_SYMBOL"
    assert seeded_web.find_symbol_map(CLIENT_ID, "XAUUSD") is None

    r = await client.post("/api/symbol_map", json={"client_id": CLIENT_ID,
                                                   "master_symbol": "XAUUSD",
                                                   "client_symbol": "XAUUSDm"})
    assert r.status_code == 200
    assert seeded_web.find_symbol_map(CLIENT_ID, "XAUUSD")["verified_at"]


async def test_tat_anh_xa_giu_nguyen_ten_symbol_phia_client(client: httpx.AsyncClient,
                                                             seeded_web: Database) -> None:
    seeded_web.upsert_symbol_map(CLIENT_ID, "XAUUSD", "XAUUSDm", enabled=1)
    r = await client.post("/api/symbol_map/disable",
                          json={"client_id": CLIENT_ID, "master_symbol": "XAUUSD"})
    assert r.status_code == 200
    dong = seeded_web.find_symbol_map(CLIENT_ID, "XAUUSD")
    assert dong["enabled"] == 0
    assert dong["client_symbol"] == "XAUUSDm"


async def test_khoa_he_thong_ngoai_danh_sach_trang_bi_tu_choi(client: httpx.AsyncClient,
                                                              seeded_web: Database) -> None:
    r = await client.post("/api/system_config",
                          json={"khoa": "event_retention_days", "gia_tri": 1})
    assert r.status_code == 400
    assert r.json()["error"] == "KHOA_NGOAI_DANH_SACH"
    assert seeded_web.get_config_int("event_retention_days", 30) == 30

    r = await client.post("/api/system_config",
                          json={"khoa": "ui_open_queue_max_age_ms", "gia_tri": 20000})
    assert r.status_code == 200
    assert seeded_web.get_config_int("ui_open_queue_max_age_ms", 0) == 20000


async def test_cap_token_tra_token_mot_lan(seeded_web: Database) -> None:
    async with _http(tao_app(Dashboard(seeded_web))) as c:
        r = await c.post("/api/agent", json={"agent_id": "AG-X", "role": "CLIENT",
                                             "magic": 770001, "login": 9})
        assert r.status_code == 200
        token = r.json()["token"]
        assert len(token) > 20
        agent = seeded_web.get_agent("AG-X")
        assert verify_token(token, agent["token_hash"])

        r = await c.post(f"/api/agent/{MASTER_AGENT}/token")
        assert r.status_code == 200
        assert verify_token(r.json()["token"], seeded_web.get_agent(MASTER_AGENT)["token_hash"])


async def test_trang_cau_hinh_hien_config_toml_nhung_che_bi_mat(seeded_web: Database) -> None:
    """Biết `telegram_token` đang trống là thông tin vận hành; biết nó là gì thì không."""
    config = parse_config({
        "bridge": {"host": "127.0.0.1", "port": 8787, "web_port": 8080},
        "security": {"telegram_token": "sieu-bi-mat"},
        "clicker": {"token": "tok", "account_login": 538217, "terminal_title": "538217"},
    }, source_path=Path("config.toml"), project_root=Path("."))
    async with _http(tao_app(Dashboard(seeded_web, config=config))) as c:
        r = await c.get("/api/config")
    khoa = {d["khoa"]: d["gia_tri"] for d in r.json()["file_config"]}
    assert khoa["security.telegram_token"] == UI["cfg_file_masked"]
    assert khoa["clicker.token"] == UI["cfg_file_masked"]
    assert "sieu-bi-mat" not in r.text
    assert "tok" not in [d["gia_tri"] for d in r.json()["file_config"]]
    assert khoa["clicker.account_login"] == "538217"


async def test_trang_cau_hinh_hien_du_bon_khoi(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/config")
    data = r.json()
    assert [a["agent_id"] for a in data["agents"]] == [CLIENT_AGENT, MASTER_AGENT]
    assert data["clients"][0]["client_id"] == CLIENT_ID
    assert data["master"]["master_close_route"] == "EA"
    assert {k["khoa"] for k in data["he_thong"]} >= {"ui_open_queue_max_len",
                                                     "close_degraded_fallback"}
    assert data["file_config"] == []


def test_moi_nhan_app_js_dung_deu_co_trong_labels(project_root) -> None:
    """`UI.abc` gõ sai trong JS không làm sập trang — nó hiện ô trống, im lặng.

    Trang Cấu hình có mấy chục nhãn, nên "im lặng" ở đây nghĩa là một nút không có chữ mà không
    ai biết. Phép kiểm này rẻ và bắt đúng loại lỗi đó.
    """
    js = (project_root / "bridge" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    dung = set(re.findall(r"UI\.([a-z0-9_]+)", js))
    thieu = sorted(dung - set(UI))
    assert not thieu, f"app.js dùng nhãn không có trong labels_vi.UI: {thieu}"


def test_moi_duong_api_app_js_goi_deu_co_route_that(project_root, seeded_web: Database) -> None:
    """Gõ sai đường trong `goi(\"/api/...\")` chỉ lộ ra khi người vận hành bấm nút."""
    js = (project_root / "bridge" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    duong_js = {d for d in re.findall(r'"(/api/[a-z_/]*)', js)}
    mau = set()
    for route in tao_app(Dashboard(seeded_web)).routes:
        duong = getattr(route, "path", "")
        if duong.startswith("/api/"):
            # Bỏ phần tham số: JS ghép id vào bằng chuỗi nên chỉ so được phần tĩnh đầu.
            mau.add(duong.split("{")[0])
    for d in sorted(duong_js):
        # So khớp một chiều: đường JS phải **bắt đầu bằng** một route có thật. So hai chiều thì
        # `/api/sym` (gõ thiếu) vẫn lọt vì nó là tiền tố của `/api/symbol_map`.
        assert any(d.startswith(m) for m in mau), f"app.js goi {d} khong co route"


async def test_khai_terminal_cho_clicker_va_cat_ket_noi_de_nap_lai(seeded_web) -> None:
    """Khai trên dashboard rồi clicker nhận ở lần bắt tay kế tiếp — không phải chạy lại tác vụ."""
    seeded_web.upsert_agent("AG-CLICKER", role="CLICKER", token_hash="h", magic_number=770001,
                            account_login=538217)
    da_dong: list[tuple[str, str]] = []

    class ServerGia:
        def dong_ket_noi(self, agent_id: str, ly_do: str) -> bool:
            da_dong.append((agent_id, ly_do))
            return True

    async with _http(tao_app(Dashboard(seeded_web,
                                       server=ServerGia()))) as c:
        r = await c.post("/api/agent/AG-CLICKER/terminal",
                         json={"login": 538217, "terminal_title": "538217 - Connext"})
        assert r.status_code == 200
        assert r.json()["nap_lai"] is True
    assert seeded_web.get_agent("AG-CLICKER")["terminal_title"] == "538217 - Connext"
    assert da_dong and da_dong[0][0] == "AG-CLICKER"


async def test_tieu_de_khong_chua_so_tai_khoan_bi_tu_choi(client: httpx.AsyncClient,
                                                          seeded_web: Database) -> None:
    """Mẩu tiêu đề không chứa số tài khoản khớp cả hai terminal — đó là cách lái nhầm cửa sổ."""
    seeded_web.upsert_agent("AG-CLICKER", role="CLICKER", token_hash="h", magic_number=770001,
                            account_login=538217)
    r = await client.post("/api/agent/AG-CLICKER/terminal",
                          json={"terminal_title": "MetaTrader 5"})
    assert r.status_code == 400
    assert r.json()["error"] == "TIEU_DE_KHONG_CO_SO_TK"
    assert seeded_web.get_agent("AG-CLICKER")["terminal_title"] is None


async def test_khai_terminal_cho_agent_khong_phai_clicker_bi_tu_choi(
        client: httpx.AsyncClient) -> None:
    r = await client.post(f"/api/agent/{MASTER_AGENT}/terminal",
                          json={"terminal_title": "1"})
    assert r.status_code == 400
    assert r.json()["error"] == "SAI_ROLE"


# -- sửa config.toml từ dashboard ---------------------------------------------------------------

MAU_FILE_CONFIG = """# Chu thich PHAI con nguyen.
[bridge]
host = "127.0.0.1"
port = 8787
web_port = 8080
db_path = "data/bridge.db"

[security]
telegram_token = "TELEGRAM-BI-MAT"

[clicker]
token = "TOKEN-CLICKER-BI-MAT"
"""


def _dashboard_co_file(db: Database, tmp_path: Path) -> tuple[Dashboard, Path]:
    duong_dan = tmp_path / "config.toml"
    duong_dan.write_text(MAU_FILE_CONFIG, encoding="utf-8")
    config = parse_config(tomllib.loads(MAU_FILE_CONFIG), source_path=duong_dan,
                          project_root=tmp_path)
    return Dashboard(db, config=config), duong_dan


async def test_sua_config_toml_tu_dashboard_va_giu_chu_thich(seeded_web: Database,
                                                             tmp_path: Path) -> None:
    dashboard, duong_dan = _dashboard_co_file(seeded_web, tmp_path)
    async with _http(tao_app(dashboard)) as c:
        r = await c.post("/api/file_config", json={"doi": {"bridge.web_port": 8090}})
    assert r.status_code == 200
    assert r.json()["can_khoi_dong_lai"] is True
    moi = duong_dan.read_text(encoding="utf-8")
    assert "web_port = 8090" in moi
    assert "# Chu thich PHAI con nguyen." in moi
    # Ban cu duoc sao luu canh file.
    assert list(tmp_path.glob("config.toml.bak-*"))


async def test_config_toml_sai_thi_tu_choi_va_khong_cham_vao_file(seeded_web: Database,
                                                                  tmp_path: Path) -> None:
    """Kiểm bằng đúng `parse_config` của đường khởi động, không phải một bản rút gọn."""
    dashboard, duong_dan = _dashboard_co_file(seeded_web, tmp_path)
    async with _http(tao_app(dashboard)) as c:
        r = await c.post("/api/file_config", json={"doi": {"bridge.web_port": 8787}})
    assert r.status_code == 400
    assert r.json()["error"] == "CONFIG_KHONG_HOP_LE"
    assert duong_dan.read_text(encoding="utf-8") == MAU_FILE_CONFIG


async def test_khoa_ngoai_danh_sach_khong_ghi_vao_config_toml(seeded_web: Database,
                                                              tmp_path: Path) -> None:
    dashboard, duong_dan = _dashboard_co_file(seeded_web, tmp_path)
    async with _http(tao_app(dashboard)) as c:
        r = await c.post("/api/file_config", json={"doi": {"bridge.khoa_la": "x"}})
    assert r.status_code == 400
    assert duong_dan.read_text(encoding="utf-8") == MAU_FILE_CONFIG


async def test_bi_mat_khong_bao_gio_di_ra_khoi_bridge(seeded_web: Database,
                                                      tmp_path: Path) -> None:
    dashboard, _ = _dashboard_co_file(seeded_web, tmp_path)
    async with _http(tao_app(dashboard)) as c:
        r = await c.get("/api/config")
    assert "TELEGRAM-BI-MAT" not in r.text
    # `in` trên danh sách chỉ bắt trùng khớp hẳn, nên nó bỏ sót một token dài hơn chuỗi tìm.
    assert not any("TOKEN-CLICKER" in d["gia_tri"] for d in r.json()["file_config"])
    assert "TOKEN-CLICKER-BI-MAT" not in r.text
    khoa = {d["khoa"]: d for d in r.json()["file_config"]}
    assert khoa["security.telegram_token"]["bi_mat"] is True
    assert khoa["security.telegram_token"]["gia_tri"] == UI["cfg_file_masked"]
    assert khoa["bridge.port"]["gia_tri"] == "8787"


async def test_css_va_js_khong_duoc_trinh_duyet_giu_cache(client: httpx.AsyncClient) -> None:
    """Sau khi cập nhật, tab đang mở phải nhận được CSS/JS mới.

    Triệu chứng của việc thiếu dòng này: "sửa xong mà dashboard không đổi gì" — và người ta sẽ đi
    tìm nguyên nhân ở mọi chỗ trừ cache trình duyệt. Gặp thật khi làm trang Cấu hình.
    """
    for duong in ("/static/app.css", "/static/app.js"):
        r = await client.get(duong)
        assert r.status_code == 200, duong
        assert "no-cache" in r.headers.get("cache-control", ""), duong


async def test_xoa_anh_xa_tren_dashboard(client: httpx.AsyncClient, seeded_web: Database) -> None:
    seeded_web.upsert_symbol_map(CLIENT_ID, "XAUUSD", "XAUUSDm", enabled=0)
    r = await client.post("/api/symbol_map/delete",
                          json={"client_id": CLIENT_ID, "master_symbol": "XAUUSD"})
    assert r.status_code == 200
    assert seeded_web.find_symbol_map(CLIENT_ID, "XAUUSD") is None


async def test_xoa_anh_xa_khong_co_thi_tra_ma_loi(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/symbol_map/delete",
                          json={"client_id": CLIENT_ID, "master_symbol": "KHONG-CO"})
    assert r.status_code == 400
    assert r.json()["error"] == "KHONG_CO_ANH_XA"


async def test_them_client_moi_tren_dashboard(client: httpx.AsyncClient,
                                              seeded_web: Database) -> None:
    seeded_web.upsert_agent("AG-CLIENT-2", role="CLIENT", token_hash="h", magic_number=770001,
                            account_login=3)
    r = await client.post("/api/client", json={"client_id": "CL-02", "agent_id": "AG-CLIENT-2",
                                               "open_route": "EA", "close_route": "EA"})
    assert r.status_code == 200
    assert seeded_web.get_client_account("CL-02")["open_route"] == "EA"


async def test_tat_client_tren_dashboard(client: httpx.AsyncClient,
                                         seeded_web: Database) -> None:
    r = await client.post(f"/api/client/{CLIENT_ID}", json={"enabled": False})
    assert r.status_code == 200
    assert seeded_web.get_client_account(CLIENT_ID)["enabled"] == 0
    assert seeded_web.list_enabled_clients() == []


async def test_xoa_client_da_co_cap_bi_tu_choi_va_bao_nen_tat(client: httpx.AsyncClient,
                                                              seeded_web: Database) -> None:
    seeded_web.upsert_master_position(9501, agent_id=MASTER_AGENT, symbol="XAUUSD",
                                      direction="BUY", initial_volume=1.0, current_volume=1.0,
                                      status="OPEN")
    seeded_web.create_pending_pair(9501, CLIENT_ID, copy_mode="OPPOSITE",
                                   master_initial_volume=1.0, effective_multiplier=1.0)
    r = await client.post(f"/api/client/{CLIENT_ID}/delete")
    assert r.status_code == 400
    assert r.json()["error"] == "CLIENT_CON_LICH_SU"
    assert seeded_web.get_client_account(CLIENT_ID) is not None


async def test_xoa_client_chua_co_cap_thi_duoc(client: httpx.AsyncClient,
                                               seeded_web: Database) -> None:
    seeded_web.upsert_agent("AG-CLIENT-2", role="CLIENT", token_hash="h", magic_number=770001,
                            account_login=3)
    seeded_web.upsert_client_account("CL-02", agent_id="AG-CLIENT-2")
    r = await client.post("/api/client/CL-02/delete")
    assert r.status_code == 200
    assert seeded_web.get_client_account("CL-02") is None


def test_ma_client_ke_tiep_theo_dung_day_CL(db: Database) -> None:
    """Để trống rồi bắt người ta tự nghĩ mã là cách chắc chắn có ngày thấy `CL2` và `cl-02`."""
    assert ma_client_ke_tiep([]) == "CL-01"
    assert ma_client_ke_tiep(["CL-01"]) == "CL-02"
    assert ma_client_ke_tiep(["CL-01", "CL-09"]) == "CL-10"
    # Mã không theo dãy thì bỏ qua khi đếm, chứ không làm hỏng gợi ý.
    assert ma_client_ke_tiep(["CL-01", "KHACH-VIP"]) == "CL-02"


async def test_trang_cau_hinh_goi_y_ma_client_ke_tiep(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/config")
    assert r.json()["ma_client_goi_y"] == "CL-02"


def test_nut_doi_che_do_nam_tren_thanh_tren_cung(project_root) -> None:
    """Ba nút đổi chế độ phải ở chỗ luôn nhìn thấy, không tụt xuống dưới bảng cặp lệnh.

    Nút đóng khẩn cấp thì **không** được lên đó: bấm nhầm nó là đóng hết vị thế.
    """
    html = (project_root / "bridge" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    dau = html.index("<header")
    cuoi = html.index("</header>")
    thanh = html[dau:cuoi]
    for nut in ("nut-pause-new", "nut-stop-sync", "nut-resume"):
        assert nut in thanh, nut
    assert "nut-emergency" not in thanh
    assert "nut-emergency" not in html, "Nut dong khan cap da duoc go khoi dashboard (D-33)"


async def test_dat_lai_tu_dashboard_can_dung_cum_xac_nhan(client: httpx.AsyncClient,
                                                          seeded_web: Database,
                                                          tmp_path: Path) -> None:
    """Gõ sai cụm thì không xoá gì — ma sát đặt đúng chỗ hành động không lùi được."""
    dashboard, _ = _dashboard_co_file(seeded_web, tmp_path)
    _cap(seeded_web, 900002, status="CLOSED")
    # Đặt lại chỉ chạy khi không còn gì đang mở — kể cả vị thế Master mà `_cap` tạo ra.
    seeded_web.upsert_master_position(900002, agent_id=MASTER_AGENT, symbol="XAUUSD",
                                      direction="BUY", initial_volume=1.0, current_volume=0.0,
                                      status="CLOSED")
    async with _http(tao_app(dashboard)) as c:
        r = await c.post("/api/dat_lai", json={"kieu": "lich_su", "phrase": "dat lai du lieu"})
        assert r.status_code == 400
        assert r.json()["error"] == "CUM_TU_SAI"
        assert seeded_web.query_all("SELECT 1 FROM pair")

        r = await c.post("/api/dat_lai",
                         json={"kieu": "lich_su", "phrase": CUM_DAT_LAI["lich_su"]})
        assert r.status_code == 200, r.text
    assert seeded_web.query_all("SELECT 1 FROM pair") == []
    assert seeded_web.get_client_account(CLIENT_ID) is not None


async def test_dat_lai_toan_bo_tu_dashboard_giu_agent(client: httpx.AsyncClient,
                                                      seeded_web: Database,
                                                      tmp_path: Path) -> None:
    dashboard, _ = _dashboard_co_file(seeded_web, tmp_path)
    async with _http(tao_app(dashboard)) as c:
        r = await c.post("/api/dat_lai",
                         json={"kieu": "toan_bo", "phrase": CUM_DAT_LAI["toan_bo"]})
        assert r.status_code == 200, r.text
    assert seeded_web.get_client_account(CLIENT_ID) is None
    assert seeded_web.get_agent(MASTER_AGENT) is not None


async def test_can_lam_di_theo_api_config_va_muc_CHAN_len_truoc(client: httpx.AsyncClient,
                                                                seeded_web: Database) -> None:
    """Thứ tự là thứ tự phải sửa: mục chặn việc copy lên trước, bật copy xuống cuối."""
    r = await client.get("/api/config")
    can_lam = r.json()["can_lam"]

    assert can_lam, "Mot ban cai chua khai gi phai co viec can lam"
    muc = [v["muc"] for v in can_lam]
    assert muc == sorted(muc, key=lambda m: 0 if m == "CHAN" else 1)
    assert can_lam[-1]["ma"] == "CHUA_BAT_COPY"
    # Cau chu phai noi LAM GI O DAU, khong chi noi cai gi sai.
    assert all(v["chu"].strip() for v in can_lam)


# -- trang Huong dan ----------------------------------------------------------------------------
#
# Trang nay la thu nguoi dung nhin thay dau tien sau khi cai (script mo san /#huong-dan), nen mot
# buoc bao sai o day dat hon mot dong tai lieu sai.

def _buoc(db: Database, config: Any = None) -> dict[str, dict[str, Any]]:
    hd = views.trang_huong_dan(db, config)
    return {b["ma"]: b for n in hd["nhom"] for b in n["buoc"]}


def test_huong_dan_buoc_tu_kiem_doi_trang_thai_khi_sua_dung_nguyen_nhan(
        seeded_web: Database) -> None:
    """Bước tự kiểm phải đi theo **sự thật trong database**, không theo một ô tích."""
    seeded_web.upsert_agent("AG-CLICKER-X", role="CLICKER", token_hash="h", magic_number=770001)
    assert _buoc(seeded_web)["LD_KHAI_CLICKER"]["trang_thai"] == "CON_THIEU"

    # Khai xong mà clicker vẫn chưa nối thì bước CHƯA xong: khai tiêu đề không làm clicker chạy,
    # nó chỉ gỡ lý do khiến clicker thoát mã 4. Bước này chỉ xanh khi clicker THẬT SỰ lên.
    dat_terminal_clicker(seeded_web, "AG-CLICKER-X", 538217, "538217 - Demo")
    assert _buoc(seeded_web)["LD_KHAI_CLICKER"]["trang_thai"] == "CON_THIEU"

    for a in seeded_web.query_all("SELECT agent_id FROM agent WHERE role = 'CLICKER'"):
        seeded_web.upsert_agent(a["agent_id"], role="CLICKER", token_hash="h", magic_number=0,
                                status="ONLINE")
    assert _buoc(seeded_web)["LD_KHAI_CLICKER"]["trang_thai"] == "XONG"


def test_huong_dan_khong_bao_XONG_khi_chua_co_agent_nao(db: Database) -> None:
    """Phép kiểm rỗng là cái bẫy: chưa có clicker nào thì "mọi clicker đã khai" là đúng về logic
    và sai về sự thật — và một bước báo Đã xong khi chưa ai làm gì thì cả danh sách mất giá trị."""
    buoc = _buoc(db)
    assert buoc["LD_GAN_EA"]["trang_thai"] == "CON_THIEU"
    assert buoc["LD_KHAI_CLICKER"]["trang_thai"] == "CON_THIEU"
    assert buoc["LD_ALGO"]["trang_thai"] == "CON_THIEU"


def test_huong_dan_buoc_thu_cong_co_o_tich_va_buoc_tu_kiem_thi_khong(seeded_web: Database) -> None:
    """Tích tay một bước Bridge kiểm được là tự bịt mắt mình, nên bước đó không có ô tích."""
    buoc = _buoc(seeded_web)
    assert buoc["UP_CTRL_F5"]["tu_kiem"] is False      # bam Ctrl+F5: server khong thay duoc
    assert buoc["LD_BAT_COPY"]["tu_kiem"] is True      # run_mode thi thay duoc


def test_huong_dan_o_tich_song_qua_moi_lan_doc_va_bi_xoa_khi_co_moc_moi(
        seeded_web: Database) -> None:
    """Ô tích nằm trong database, và **phải** bị xoá ở lần cập nhật sau.

    Không xoá thì ô tích của lần cập nhật trước làm danh sách trông như đã xong, và một danh sách
    luôn xanh thì không ai đọc nữa.
    """
    dat_tich_huong_dan(seeded_web, "UP_CTRL_F5", True)
    assert _buoc(seeded_web)["UP_CTRL_F5"]["da_tich"] is True

    ghi_moc_cap_nhat(seeded_web, ea_doi=False, tu_commit="a" * 40)
    assert _buoc(seeded_web)["UP_CTRL_F5"]["da_tich"] is False
    assert doc_tich_huong_dan(seeded_web) == set()


def test_huong_dan_buoc_gan_lai_EA_chi_hien_khi_ea_doi(seeded_web: Database) -> None:
    """In "biên dịch lại EA" ở **mọi** lần cập nhật là cách chắc chắn để nó bị bỏ qua đúng lần
    nó có thật."""
    ghi_moc_cap_nhat(seeded_web, ea_doi=False)
    assert "UP_GAN_LAI_EA" not in _buoc(seeded_web)

    ghi_moc_cap_nhat(seeded_web, ea_doi=True)
    assert _buoc(seeded_web)["UP_GAN_LAI_EA"]["tu_kiem"] is False


def test_huong_dan_mo_muc_lan_dau_khi_may_con_trang(db: Database) -> None:
    assert views.trang_huong_dan(db)["che_do"] == "LAN_DAU"


def test_huong_dan_mo_muc_sau_update_khi_vua_cap_nhat(seeded_web: Database) -> None:
    ghi_moc_cap_nhat(seeded_web, ea_doi=False)
    hd = views.trang_huong_dan(seeded_web)
    assert hd["che_do"] == "SAU_UPDATE"
    assert hd["moc_cap_nhat"]


def test_huong_dan_bat_khoa_clicker_con_sot_trong_config_toml(seeded_web: Database,
                                                              tmp_path: Path) -> None:
    """`config.toml` còn khai `account_login` thì **file thắng database** — khai trên dashboard
    không có tác dụng, và không script nào kiểm hộ."""
    dashboard, _ = _dashboard_co_file(seeded_web, tmp_path)
    assert _buoc(seeded_web, dashboard.config)["UP_CONFIG_SOT"]["trang_thai"] == "XONG"

    con_sot = MAU_FILE_CONFIG.replace('[clicker]\ntoken = "TOKEN-CLICKER-BI-MAT"',
                                      '[clicker]\ntoken = "x"\naccount_login = 538217')
    cfg = parse_config(tomllib.loads(con_sot), source_path=tmp_path / "config.toml",
                       project_root=tmp_path)
    assert _buoc(seeded_web, cfg)["UP_CONFIG_SOT"]["trang_thai"] == "CON_THIEU"


async def test_api_tich_ghi_duoc_va_tu_choi_ma_la(client: httpx.AsyncClient,
                                                  seeded_web: Database) -> None:
    r = await client.post("/api/huong_dan/tich", json={"ma": "LD_TOOLBOX", "tich": True})
    assert r.status_code == 200, r.text
    assert "LD_TOOLBOX" in r.json()["da_tich"]

    r = await client.get("/api/huong_dan")
    buoc = {b["ma"]: b for n in r.json()["nhom"] for b in n["buoc"]}
    assert buoc["LD_TOOLBOX"]["da_tich"] is True

    r = await client.post("/api/huong_dan/tich", json={"ma": "KHONG-CO-BUOC-NAY", "tich": True})
    assert r.status_code == 400
    assert r.json()["error"] == "MA_BUOC_LA"


async def test_api_huong_dan_moi_buoc_co_cau_chu(client: httpx.AsyncClient) -> None:
    """Một bước không có câu chữ là một dòng trống trên trang — và D-16 nói mọi câu chữ phải
    đi qua `labels_vi`, nên thiếu nhãn là thiếu ở đó."""
    r = await client.get("/api/huong_dan")
    for n in r.json()["nhom"]:
        assert n["ten"].strip() and n["chu"].strip()
        for b in n["buoc"]:
            assert b["chu"].strip(), b["ma"]


# -- suy cau hinh clicker, nhin tu dashboard ----------------------------------------------------

def test_can_lam_bao_lech_khi_khai_tay_khac_so_EA_bao(seeded_web: Database) -> None:
    """Lệch nghĩa là clicker đang lái nhầm terminal, hoặc terminal vừa đăng nhập sang tài khoản
    khác. Cả hai đều phải do người quyết — code không tự chọn hộ."""
    seeded_web.upsert_agent("AG-CLICKER-X", role="CLICKER", token_hash="h", magic_number=0)
    seeded_web.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT,
                                     clicker_agent_id="AG-CLICKER-X")
    dat_terminal_clicker(seeded_web, "AG-CLICKER-X", 999111, "999111 - San khac")

    viec = [v for v in views.viec_can_lam(seeded_web) if v["ma"] == "CLICKER_LECH_SO_TK"]
    assert len(viec) == 1
    assert viec[0]["muc"] == "CHAN"
    assert "999111" in viec[0]["chu"]


def test_can_lam_khong_bao_chua_khai_khi_suy_duoc(seeded_web: Database) -> None:
    """Bắt "chưa khai" trong khi clicker vẫn chạy được là báo một việc không có thật."""
    seeded_web.upsert_agent("AG-CLICKER-X", role="CLICKER", token_hash="h", magic_number=0)
    seeded_web.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT,
                                     clicker_agent_id="AG-CLICKER-X")
    ma = {v["ma"] for v in views.viec_can_lam(seeded_web)}
    assert "CLICKER_CHUA_KHAI" not in ma


async def test_trang_cau_hinh_gui_danh_sach_symbol_va_de_xuat(client: httpx.AsyncClient,
                                                              seeded_web: Database) -> None:
    def spec(s, digits=2, contract=100.0):
        return {"symbol": s, "digits": digits, "point": 0.01, "volume_min": 0.01,
                "volume_max": 50.0, "volume_step": 0.01, "contract_size": contract}

    seeded_web.replace_symbol_specs(MASTER_AGENT, [spec("XAUUSD")])
    seeded_web.replace_symbol_specs(CLIENT_AGENT, [spec("XAUUSDm")])

    d = (await client.get("/api/config")).json()
    assert [x["symbol"] for x in d["symbol_master"]] == ["XAUUSD"]
    assert [x["symbol"] for x in d["symbol_client"][CLIENT_ID]] == ["XAUUSDm"]
    assert d["de_xuat_anh_xa"][CLIENT_ID][0]["client_symbol"] == "XAUUSDm"


# -- them Client bang mot nut -------------------------------------------------------------------

async def test_api_client_moi_tao_du_va_ghi_token_vao_config(seeded_web: Database,
                                                             tmp_path: Path) -> None:
    dashboard, duong_dan = _dashboard_co_file(seeded_web, tmp_path)
    async with _http(tao_app(dashboard)) as c:
        r = await c.post("/api/client_moi")
    assert r.status_code == 200, r.text
    d = r.json()

    assert seeded_web.get_client_account(d["client_id"]) is not None
    assert seeded_web.get_agent(d["agent"])["role"] == "CLIENT"
    assert seeded_web.get_agent(d["clicker"])["role"] == "CLICKER"
    # Token clicker đi thẳng vào config.toml và KHÔNG bao giờ ra tới trình duyệt: một token đi qua
    # JSON là một token nằm trong cache trình duyệt.
    assert "token_clicker" not in d
    doc = tomllib.loads(duong_dan.read_text(encoding="utf-8"))
    assert len(doc[d["muc_clicker"]]["token"]) >= 32
    # Câu lệnh đăng ký tác vụ phải dán chạy được, không bắt người dùng tự ghép.
    assert d["muc_clicker"] in d["lenh_tac_vu"]


def test_huong_dan_mo_muc_lan_dau_ngay_sau_khi_tro_ly_cai_xong(db: Database) -> None:
    """Lỗi bắt được ở lần cài thật thứ hai (2026-09-22): trang mở mục "Sau khi cập nhật" cho một
    máy vừa cài lần đầu.

    Bản đầu hỏi "chưa có agent hoặc chưa có Client?" để nhận ra lần cài đầu — câu hỏi ấy **không
    bao giờ đúng**, vì `tro-ly.ps1` tạo sẵn bốn agent và `CL-01` ngay trong lần cài. Câu hỏi đúng
    là "việc của lần cài đầu đã xong chưa".
    """
    for a, r in [("AG-MASTER", "MASTER"), ("AG-CLIENT", "CLIENT"), ("AG-CLICKER", "CLICKER"),
                 ("AG-CLICKER-MASTER", "CLICKER")]:
        db.upsert_agent(a, role=r, token_hash="h", magic_number=770001)
    db.upsert_client_account("CL-01", agent_id="AG-CLIENT", clicker_agent_id="AG-CLICKER",
                             open_route="UI", close_route="UI")

    assert views.trang_huong_dan(db)["che_do"] == "LAN_DAU"


def test_huong_dan_may_dang_chay_vua_khoi_dong_lai_khong_bi_coi_la_moi_cai(db: Database) -> None:
    """`run_mode` về `PAUSED` sau **mỗi** lần khởi động lại (D-15), nên nếu tính bước "bấm Bắt đầu
    copy" vào phép quyết định thì mọi máy vừa restart đều bị coi là mới cài."""
    db.upsert_agent("AG-MASTER", role="MASTER", token_hash="h", magic_number=770001,
                    account_login=538216, status="ONLINE", trade_allowed=1)
    db.upsert_agent("AG-CLIENT", role="CLIENT", token_hash="h", magic_number=770001,
                    account_login=538217, status="ONLINE", trade_allowed=1)
    db.upsert_agent("AG-CLICKER", role="CLICKER", token_hash="h", magic_number=0,
                    status="ONLINE")
    db.upsert_client_account("CL-01", agent_id="AG-CLIENT", clicker_agent_id="AG-CLICKER",
                             open_route="UI", close_route="UI")
    db.upsert_symbol_map("CL-01", "XAUUSD", "XAUUSDm", enabled=1)
    db.set_config("run_mode", "PAUSED")

    assert views.trang_huong_dan(db)["che_do"] == "SAU_UPDATE"


def test_huong_dan_o_tu_tich_chua_bam_khong_lam_ket_o_muc_lan_dau(db: Database) -> None:
    """Ô tự tích không ai bấm thì chưa xong vĩnh viễn — tính nó vào là trang kẹt ở Lần đầu mãi."""
    db.upsert_agent("AG-MASTER", role="MASTER", token_hash="h", magic_number=770001,
                    account_login=538216, status="ONLINE", trade_allowed=1)
    db.upsert_agent("AG-CLIENT", role="CLIENT", token_hash="h", magic_number=770001,
                    account_login=538217, status="ONLINE", trade_allowed=1)
    db.upsert_agent("AG-CLICKER", role="CLICKER", token_hash="h", magic_number=0, status="ONLINE")
    db.upsert_client_account("CL-01", agent_id="AG-CLIENT", clicker_agent_id="AG-CLICKER",
                             open_route="UI", close_route="UI")
    db.upsert_symbol_map("CL-01", "XAUUSD", "XAUUSDm", enabled=1)
    db.set_config("run_mode", "RUNNING")

    hd = views.trang_huong_dan(db)
    lan_dau = next(n for n in hd["nhom"] if n["ma"] == "LAN_DAU")
    assert any(b["trang_thai"] == "TU_TICH" and not b["da_tich"] for b in lan_dau["buoc"])
    assert hd["che_do"] == "SAU_UPDATE"


# -- huong dan chi tiet (ban 2026-09-22) -------------------------------------------------------
#
# Lan chay thu tai lieu tren VPS tac ngay o buoc 1: mot buoc = mot dong chu, gom sau hanh dong,
# khong thu tu, khong noi lam o dau, khong cach tu kiem. Bon test duoi day khoa lai dung bon thieu
# sot do, de mot ban sau khong am tham quay ve bang mot dong.

def test_moi_buoc_co_du_bon_phan(seeded_web: Database) -> None:
    """Mỗi bước phải có: nơi làm, các việc con, cách tự kiểm. `bay` thì tuỳ bước.

    Thiếu một trong ba là quay về đúng bản đã tắc: người đọc biết phải làm *gì* nhưng không biết
    làm *ở đâu*, theo thứ tự nào, và nhìn thấy gì thì coi là xong.
    """
    for ma, b in _buoc(seeded_web).items():
        assert b["noi"] in ("DASHBOARD", "MT5", "POWERSHELL"), f"{ma}: noi = {b['noi']!r}"
        assert len(b["viec"]) >= 2, f"{ma}: chi co {len(b['viec'])} viec con"
        assert b["kiem"].strip(), f"{ma}: khong noi cach tu kiem"
        # Mot dong chu de quet mat, khong phai mot doan van: doan van la dung thu vua bo.
        assert len(b["chu"]) <= 70, f"{ma}: dong mot dai {len(b['chu'])} ky tu"


def test_buoc_do_noi_ro_do_vi_DOI_TUONG_nao(seeded_web: Database) -> None:
    """Bước đỏ phải nói rõ **đối tượng nào** đang thiếu, không chỉ một dấu ✗.

    `viec_can_lam` đã sinh sẵn một dòng cho từng agent / từng Client. Bản đầu nén hết xuống thành
    một boolean rồi bỏ đi, nên một bước đỏ bắt người dùng đi dò lại bằng tay đúng thứ Bridge vừa
    biết.
    """
    b = _buoc(seeded_web)["LD_GAN_EA"]
    assert b["trang_thai"] == "CON_THIEU"
    assert b["thieu"], "buoc do ma khong noi thieu gi"
    # Ten agent phai co mat trong loi giai thich.
    assert any(MASTER_AGENT in t or CLIENT_AGENT in t for t in b["thieu"]), b["thieu"]

    # Buoc xanh thi khong co gi de ke.
    seeded_web.set_config("run_mode", "RUNNING")
    assert _buoc(seeded_web)["LD_BAT_COPY"]["thieu"] == []


def test_lan_dau_co_buoc_bien_dich_ea(seeded_web: Database) -> None:
    """Lần đầu **phải** có bước biên dịch EA, và nó phải đứng trước bước gắn EA.

    Bản đầu không có bước này: lệnh biên dịch chỉ nằm ở nhóm "sau khi cập nhật", nên người cài lần
    đầu không hề được bảo phải tạo `.ex5`. Không có file đó thì bước gắn EA không làm được, mà
    triệu chứng lại là "EA không kéo được lên chart" — một câu không dẫn về đây.
    """
    hd = views.trang_huong_dan(seeded_web)
    lan_dau = next(n for n in hd["nhom"] if n["ma"] == views.NHOM_LAN_DAU)
    ma = [b["ma"] for b in lan_dau["buoc"]]
    assert "LD_BIEN_DICH" in ma
    assert ma.index("LD_BIEN_DICH") < ma.index("LD_GAN_EA")
    lenh = _buoc(seeded_web)["LD_BIEN_DICH"]["lenh"]
    assert any("MetaEditor64.exe" in x["chu"] for x in lenh), lenh
    # Va no phai CHAY DUOC tu trang: buoc dau tien ma bat nguoi dung mo PowerShell la cho
    # de bo cuoc nhat.
    assert any(x["ma_chay"] for x in lenh), lenh


def test_moi_buoc_lam_tren_dashboard_deu_co_duong_dong_lenh(seeded_web: Database) -> None:
    """Bước làm trên dashboard phải kèm đường dòng lệnh tương đương.

    Ngày 2026-09-22 đường dashboard tắc (nút Cấp lại token trả 403 vì chưa đặt mật khẩu) và trang
    không nhắc một câu nào về `bridge.admin` — nên không còn đường nào để đi tiếp, dù CLI phủ hết
    cả chín bước. Một hướng dẫn chỉ có một đường là một hướng dẫn hỏng khi đường đó hỏng.
    """
    # `LD_CAU_HINH_COPY` va `UP_CTRL_F5` la ngoai le co y: mot cai la "xem lai roi tu tich" (lenh
    # `cau-hinh-client` chi xem, van dua vao), con Ctrl+F5 thi khong co dong lenh nao tuong duong.
    khong_can = {"UP_CTRL_F5", "UP_CONFIG_SOT"}
    for ma, b in _buoc(seeded_web).items():
        if b["noi"] != "DASHBOARD" or ma in khong_can:
            continue
        assert b["lenh"], f"{ma}: lam tren dashboard ma khong co duong dong lenh"
        assert any("bridge.admin" in x["chu"] for x in b["lenh"]), f"{ma}: khong co bridge.admin"


def test_chu_nhom_lan_dau_khong_ghi_cung_so_viec(seeded_web: Database) -> None:
    """Câu mô tả nhóm không được ghi số việc bằng chữ.

    Bản cũ ghi "Chín việc" trong khi danh sách có tám, và không ai sửa — số bước đã đổi ba lần.
    Giao diện tự đếm, nên câu chữ đừng nói lại.
    """
    from bridge.labels_vi import UI
    chu = UI["hd_nhom_lan_dau_chu"].lower()
    for so in ("bảy việc", "tám việc", "chín việc", "mười việc"):
        assert so not in chu, f"cau mo ta con ghi cung so viec: {so!r}"


def test_ghi_cau_hinh_ve_lai_tab_TRUOC_khi_goi_sauKhiXong(project_root) -> None:
    """`ghiCauHinh` phải gọi `taiCauHinh()` **trước** `sauKhiXong`, không phải sau.

    `taiCauHinh()` dựng lại cả tab (`el.innerHTML = ""`), nên bất cứ thứ gì `sauKhiXong` vẽ ra
    trước đó đều bị xoá sau một nhịp: hiện đúng một khoảnh khắc rồi biến mất.

    Cùng một lỗi đã xảy ra **hai lần** với cùng một triệu chứng "không thấy token đâu cả": lần đầu
    ở nút Thêm Client (sửa riêng tại chỗ gọi), lần hai ở nút Cấp lại token — bắt được khi chạy thử
    tài liệu trên VPS 2026-09-22, và nó chặn đúng bước 2 của danh sách Cài đặt lần đầu.

    Test đọc thứ tự trong mã nguồn vì đây là thứ không có phép kiểm nào khác: hàm chạy xong thì
    DOM đã đúng, chỉ có điều nó đúng trong một khoảnh khắc không ai nhìn thấy.
    """
    js = (project_root / "bridge" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    dau = js.index("async function ghiCauHinh(")
    than = js[dau:js.index("\n}", dau)]
    assert "taiCauHinh()" in than and "sauKhiXong(" in than
    assert than.index("taiCauHinh()") < than.index("sauKhiXong(r.data)"), (
        "ghiCauHinh goi sauKhiXong TRUOC taiCauHinh(): moi thu no ve ra se bi xoa ngay sau do"
    )


def test_moi_hanh_dong_cua_buoc_deu_duoc_JS_xu_ly(project_root, seeded_web: Database) -> None:
    """Mã hành động khai trong `views.Buoc` phải có nhánh xử lý trong `app.js`.

    Hai bên nối nhau bằng một chuỗi, không bằng kiểu — nên gõ sai hay đổi tên một bên là nút hiện
    ra mà bấm không làm gì, **im lặng**. Đúng loại hỏng đắt nhất: người dùng bấm, không thấy gì,
    rồi bấm lại.
    """
    js = (project_root / "bridge" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    ma = {h for b in views.BUOC_LAN_DAU + views.BUOC_SAU_UPDATE for h in b.hanh_dong}
    assert ma, "khong buoc nao co hanh dong -- bang khai bao co dung khong?"
    for h in sorted(ma):
        assert f'"{h}"' in js, f"app.js khong xu ly hanh dong {h}"


def test_doi_che_do_tu_ve_lai_chu_khong_cho_websocket(project_root) -> None:
    """`doiCheDo` phải kiểm kết quả POST **và** tự vẽ lại, không chờ WebSocket.

    Bản cũ bắn POST rồi quên luôn: nhãn trạng thái chỉ đổi khi WebSocket đẩy bản chụp kế tiếp. Nên
    WebSocket chết là bấm nút không thấy gì xảy ra — mà một POST thất bại **cũng** không thấy gì
    xảy ra. Hai chuyện khác hẳn nhau trong cùng một vẻ im lặng, và người dùng báo đúng triệu chứng
    đó ngày 2026-09-22.
    """
    js = (project_root / "bridge" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    dau = js.index("async function doiCheDo(")
    than = js[dau:js.index("\n}\n", dau)]
    assert "if (!r.ok)" in than, "doiCheDo khong kiem ket qua POST"
    assert "alert(" in than, "doiCheDo that bai trong im lang"
    assert "/api/snapshot" in than, "doiCheDo khong tu ve lai, van cho WebSocket"


def test_moi_form_cua_buoc_deu_duoc_JS_xu_ly(project_root, seeded_web: Database) -> None:
    """Mã form khai trong `views.Buoc.form` phải có nhánh vẽ trong `app.js`.

    Cùng một kiểu nối như `hanh_dong`: hai bên nối nhau bằng một **chuỗi**, nên gõ sai hay đổi tên
    một bên là form không hiện ra — và không có lỗi nào báo, chỉ là một bước trông như chưa làm gì.
    """
    js = (project_root / "bridge" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    ma = {f for b in views.BUOC_LAN_DAU + views.BUOC_SAU_UPDATE for f in b.form}
    assert ma, "khong buoc nao co form"
    for f in sorted(ma):
        assert f'"{f}"' in js, f"app.js khong ve form {f}"


def test_form_trong_buoc_khong_di_qua_api_chay(project_root) -> None:
    """Form POST vào endpoint đã có, **không** qua `/api/chay`.

    Đây là ranh giới của D-41 và nó phải nhìn thấy được trong mã: `/api/chay` chỉ nhận một MÃ, còn
    form thì gửi giá trị người dùng gõ. Cho giá trị ấy đi vào đường chạy lệnh là mở một lối để một
    chuỗi tự do đi tới `argv`, trên một dashboard không có xác thực (D-39).
    """
    js = (project_root / "bridge" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    for ten, duong in (("formClicker", "/terminal"), ("formAnhXa", "/api/symbol_map")):
        dau = js.index(f"function {ten}(")
        than = js[dau:js.index("\n}\n", dau)]
        assert duong in than, f"{ten} khong goi {duong}"
        assert "/api/chay" not in than, f"{ten} di qua /api/chay -- xem D-41"


def test_trang_huong_dan_va_trang_cau_hinh_dung_CHUNG_nguon_symbol(seeded_web: Database) -> None:
    """Hai trang phải lấy danh sách symbol từ cùng một nguồn, không tính lại theo cách khác.

    Lỗi bắt được khi bấm thật: `symbol_cua_agent` trả về list **dict** (`{symbol, digits, ...}`),
    khối Ánh xạ của tab Cấu hình đã `.map(x => x.symbol)` nhưng form mới thì quên — mọi option
    thành `[object Object]` và giá trị gửi lên rỗng. Test này chốt cái hình dạng đó lại.
    """
    seeded_web.replace_symbol_specs(MASTER_AGENT, [
        {"symbol": "XAUUSD", "digits": 2, "point": 0.01, "volume_min": 0.01,
         "volume_max": 50.0, "volume_step": 0.01, "contract_size": 100.0}])
    hd = views.trang_huong_dan(seeded_web)
    ch = views.trang_cau_hinh(seeded_web)
    assert hd["symbol_master"] == ch["symbol_master"]
    assert hd["symbol_client"] == ch["symbol_client"]
    assert hd["de_xuat_anh_xa"] == ch["de_xuat_anh_xa"]
    # Va hinh dang la list dict co khoa `symbol` -- JS PHAI map, khong dung thang.
    assert hd["symbol_master"] and isinstance(hd["symbol_master"][0], dict)
    assert "symbol" in hd["symbol_master"][0]


def test_js_luon_map_symbol_ra_ten_truoc_khi_dung(project_root) -> None:
    """Mọi chỗ JS đọc `symbol_master` / `symbol_client` đều phải `.map(x => x.symbol)`.

    Chốt riêng ở đây vì test hình dạng phía Python **không** bắt được lỗi này: payload vẫn đúng,
    chỉ có JS dùng sai. Triệu chứng là mọi lựa chọn thành `[object Object]` và giá trị gửi lên
    rỗng — rồi máy chủ trả "Thiếu tên symbol", một câu không dẫn về đây chút nào.
    """
    js = (project_root / "bridge" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    for dong in js.splitlines():
        cau = dong.strip()
        if cau.startswith("//") or ("symbol_master" not in cau and "symbol_client" not in cau):
            continue
        # Gán cả dict `symbol_client` rồi map ở nơi tra cứu thì hợp lệ: chỉ chỗ biến nó thành một
        # DANH SÁCH TÊN mới bắt buộc map. Nhận ra bằng `[...]` ở cuối — một list symbol.
        if "symbol_client ||" in cau and "{}" in cau:
            continue
        assert "x.symbol" in cau, f"doc symbol ma khong map ra ten: {cau[:80]}"

    # Va moi cho tra cuu ra mot danh sach roi dung lam lua chon cung phai map.
    for ten in ("khoiAnhXa", "formAnhXa"):
        dau = js.index(f"function {ten}(")
        than = js[dau:js.index("\n}\n", dau)]
        assert than.count("x.symbol") >= 2, f"{ten}: thieu mot lan map symbol ra ten"


def test_cac_buoc_gom_theo_NOI_LAM_khong_bat_nhay_qua_lai(seeded_web: Database) -> None:
    """Số lần đổi `noi` giữa hai bước liên tiếp phải ≤ 3.

    Mỗi lần đổi là một lần người vận hành phải rời cửa sổ đang làm: đóng dashboard mở MT5, rồi
    ngược lại. Bản đầu đổi **5 lần** vì bước khai clicker (dashboard) nằm giữa khối MT5 — và không
    ai đếm được điều đó khi đọc một danh sách chín dòng.

    Khoá **tính chất**, không khoá một thứ tự cụ thể: xếp lại thoải mái, miễn đừng làm nát nhóm.
    """
    noi = [b.noi for b in views.BUOC_LAN_DAU]
    doi = sum(1 for a, b in zip(noi, noi[1:], strict=False) if a != b)
    assert doi <= 3, f"cac buoc bat nhay cho {doi} lan: {noi}"


def test_viec_con_khong_noi_sai_NOI_LAM(seeded_web: Database) -> None:
    """Việc con của một bước `noi = DASHBOARD` không được mở đầu bằng "Trong MT5".

    Đây là cách `LD_ANH_XA` khai sai mà không ai thấy: nó khai `noi = DASHBOARD` nhưng việc con
    đầu tiên là "Trong MT5 của Client: mở Market Watch". Một bước nói làm ở một nơi rồi bắt sang
    nơi khác chính là thứ làm số lần nhảy chỗ đếm ra sai.
    """
    from bridge.labels_vi import UI
    cam = {"DASHBOARD": ("trong mt5", "trong mỗi terminal", "trong terminal"),
           "MT5": ("sang tab cấu hình", "tab cấu hình >")}
    for b in views.BUOC_LAN_DAU + views.BUOC_SAU_UPDATE:
        for viec in UI[b.khoa_viec]:
            dau = viec.lower()[:30]
            for mau in cam.get(b.noi, ()):
                assert mau not in dau, f"{b.ma} (noi={b.noi}) co viec con bat sang cho khac: {viec[:60]}"


def test_khoi_agent_nhan_duoc_gia_tri_CO_HIEU_LUC_cua_clicker(seeded_web: Database) -> None:
    """Payload phải nói giá trị của clicker đến TỪ ĐÂU, không chỉ nói cột DB là gì.

    Giá trị của clicker được suy lúc đọc và **cố ý không ghi xuống** (D-38). Bản đầu gửi đúng cột
    thô, nên một clicker đã chạy ngon vẫn hiện hai ô **rỗng** trên trang Cấu hình — và ô rỗng đọc
    ra là "còn thiếu". Người dùng báo lại đúng triệu chứng đó.
    """
    seeded_web.upsert_agent(CLIENT_AGENT, role="CLIENT", token_hash="h", magic_number=770001,
                            account_login=538217)
    # Clicker gan cho CL-01: do la lien ket `cau_hinh_clicker` di theo de suy ra so tai khoan.
    seeded_web.upsert_agent("AG-CLICKER-X", role="CLICKER", token_hash="h", magic_number=0)
    seeded_web.upsert_client_account(CLIENT_ID, agent_id=CLIENT_AGENT,
                                     clicker_agent_id="AG-CLICKER-X")
    ag = {a["agent_id"]: a for a in views.trang_cau_hinh(seeded_web)["agents"]}
    clicker = [a for a in ag.values() if a["role"] == "CLICKER"]
    assert clicker, "chua tao duoc clicker nao"
    assert ag["AG-CLICKER-X"]["nguon"] == "SUY", ag["AG-CLICKER-X"]
    for a in clicker:
        assert "nguon" in a, f"{a['agent_id']}: payload khong noi gia tri den tu dau"
        assert a["nguon"] in ("KHAI", "SUY", "CHUA_CO")
        if a["nguon"] == "SUY":
            assert a["login_hieu_luc"], a
            assert a["tieu_de_hieu_luc"], a
    # Agent EA khong co cac khoa nay -- chung chi co nghia voi clicker.
    assert "nguon" not in ag[MASTER_AGENT]


def test_khoa_he_thong_hien_gia_tri_DANG_CHAY_chu_khong_phai_o_rong(db: Database) -> None:
    """Khoá chưa ai đổi phải hiện **mặc định của engine**, kèm cờ `mac_dinh`.

    `schema.sql` chỉ gieo hai trong bảy khoá, nên năm khoá còn lại đọc ra chuỗi rỗng và trang vẽ ô
    trống — trong khi engine vẫn chạy bằng mặc định cứng của chính nó. Một ô trống đọc ra là "chưa
    đặt", và người vận hành không có cách nào biết hệ thống đang dùng số mấy.
    """
    from bridge.ops import KHOA_SUA_DUOC
    he_thong = {k["khoa"]: k for k in views.trang_cau_hinh(db)["he_thong"]}
    assert set(he_thong) == set(KHOA_SUA_DUOC)
    for khoa, k in he_thong.items():
        assert str(k["gia_tri"]).strip(), f"{khoa}: van hien o rong"

    # Đổi một khoá: nó thôi là mặc định, các khoá khác không đổi theo.
    db.set_config("ui_open_queue_max_len", "33")
    he_thong = {k["khoa"]: k for k in views.trang_cau_hinh(db)["he_thong"]}
    assert he_thong["ui_open_queue_max_len"]["mac_dinh"] is False
    assert str(he_thong["ui_open_queue_max_len"]["gia_tri"]) == "33"
    assert he_thong["finding_nhac_sau_phut"]["mac_dinh"] is True


def test_mac_dinh_trang_bao_DUNG_BANG_mac_dinh_engine_that_su_dung(db: Database) -> None:
    """Con số trang hiện phải **là** con số engine dùng, không phải một bản chép tay.

    Trước đây mặc định nằm rải bốn chỗ: hai hằng có tên trong `closing.py`, ba số trần trong
    `processor.py`, một trong `reconcile.py`. Chép chúng sang `views` là tạo ra hai nguồn sự thật,
    và lệch kiểu đó thì **im lặng**: trang nói 15 giây, engine chờ 20, không ai sai rõ ràng.
    """
    from bridge.engine.closing import DEFAULT_CASCADE_WAIT_MS, DEFAULT_UI_CLOSE_GRACE_MS
    from bridge.ops import MAC_DINH_KHOA, gia_tri_khoa

    assert DEFAULT_CASCADE_WAIT_MS == MAC_DINH_KHOA["cascade_wait_master_ms"]
    assert DEFAULT_UI_CLOSE_GRACE_MS == MAC_DINH_KHOA["ui_close_correlate_grace_ms"]
    # Và `gia_tri_khoa` trên một DB trống phải trả về đúng bảng mặc định đó.
    for khoa, mac_dinh in MAC_DINH_KHOA.items():
        if not db.get_config(khoa, ""):
            assert gia_tri_khoa(db, khoa) == mac_dinh, khoa


def test_khoi_master_khong_moi_chon_clicker_da_bi_chiem(project_root) -> None:
    """Danh sách clicker của Master phải lọc bỏ clicker đã gán cho một Client.

    `ops._clicker_con_trong` từ chối chúng với `CLICKER_DA_DUNG`. Mời người dùng chọn một thứ chắc
    chắn bị từ chối là một cái bẫy, không phải một lựa chọn.
    """
    js = (project_root / "bridge" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    dau = js.index("function khoiMaster(")
    than = js[dau:js.index("\n}\n", dau)]
    assert "clicker_agent_id" in than, "khoiMaster khong he nhin toi clicker cua cac Client"
    assert "dangDung" in than or "filter" in than, "khoiMaster khong loc danh sach"


def test_khoi_master_khong_xoa_clicker_khi_no_hien_dang_chu(project_root) -> None:
    """Nút Lưu của khối Master không được gửi `null` khi ô clicker là chữ, không phải `<select>`.

    Khi chỉ còn một lựa chọn hợp lệ, ô chọn được thay bằng một `<div>` — và `div.value` là
    `undefined`, nên `|| null` biến nó thành "xoá clicker của Master". Người dùng chỉ định đổi
    đường đóng lại mất luôn clicker, im lặng.
    """
    js = (project_root / "bridge" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    dau = js.index("function khoiMaster(")
    than = js[dau:js.index("\n}\n", dau)]
    assert "chonClicker.value || null" not in than, (
        "doc thang .value tren mot phan tu co the la <div> -- xem chu thich trong ham"
    )
    assert "motLuaChon ? hienTai" in than
