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

import httpx
import pytest

from bridge.clock import to_iso, utc_now
from bridge.config import parse_config
from bridge.db.repo import Database
from bridge.labels_vi import UI
from bridge.protocol.auth import verify_token
from bridge.web import views
from bridge.web.app import EMERGENCY_PHRASE, Dashboard, tao_app
from tests.conftest import CLIENT_AGENT, CLIENT_ID, MASTER_AGENT

MAT_KHAU = "mat-khau-thu-nghiem"


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
    async with _http(tao_app(Dashboard(seeded_web))) as c:
        yield c


# -- nút nguy hiểm ----------------------------------------------------------------------------

async def test_dong_khan_cap_khong_lam_gi_khi_go_sai_chuoi(client: httpx.AsyncClient,
                                                     seeded_web: Database) -> None:
    """Ma sát cao nhất dành cho hành động nguy hiểm nhất."""
    _cap(seeded_web, 900001)
    truoc = seeded_web.get_config("run_mode")

    r = await client.post("/api/emergency", json={"phrase": "dong tat ca"})   # sai hoa/thuong

    assert r.status_code == 400
    assert r.json()["error"] == "wrong_phrase"
    assert seeded_web.get_config("run_mode") == truoc
    assert not seeded_web.query_all("SELECT 1 FROM command"), "Khong duoc sinh command nao"


async def test_dong_khan_cap_chuoi_xac_nhan_khong_dau(client: httpx.AsyncClient) -> None:
    """Bắt gõ tiếng Việt có dấu trong lúc hoảng, với bộ gõ đang ở chế độ khác, là tự tạo rắc rối."""
    assert EMERGENCY_PHRASE.isascii()
    assert EMERGENCY_PHRASE == "DONG TAT CA"


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


# -- xác thực ---------------------------------------------------------------------------------

async def test_khong_dang_nhap_thi_api_tra_401(seeded_web: Database) -> None:
    async with _http(tao_app(Dashboard(seeded_web, password=MAT_KHAU))) as c:
        assert (await c.get("/api/snapshot")).status_code == 401
        assert (await c.get("/")).status_code == 303


async def test_dang_nhap_dung_mat_khau_thi_vao_duoc(seeded_web: Database) -> None:
    async with _http(tao_app(Dashboard(seeded_web, password=MAT_KHAU))) as c:
        r = await c.post("/login", data={"password": MAT_KHAU})
        assert r.status_code == 303
        c.cookies.update(r.cookies)
        assert (await c.get("/api/snapshot")).status_code == 200


async def test_dang_nhap_sai_mat_khau_thi_khong_vao_duoc(seeded_web: Database) -> None:
    async with _http(tao_app(Dashboard(seeded_web, password=MAT_KHAU))) as c:
        await c.post("/login", data={"password": "sai"})
        assert (await c.get("/api/snapshot")).status_code == 401


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


async def test_khong_cap_token_khi_dashboard_chua_dat_mat_khau(
        client: httpx.AsyncClient, seeded_web: Database) -> None:
    """Không mật khẩu thì `hop_le` cho qua mọi request — cấp token khi đó là phát hành danh tính
    cho bất kỳ ai chạm được cổng 8080."""
    r = await client.post("/api/agent", json={"agent_id": "AG-X", "role": "CLIENT",
                                              "magic": 770001, "login": 9})
    assert r.status_code == 403
    assert r.json()["error"] == "CHUA_DAT_MAT_KHAU"
    assert seeded_web.get_agent("AG-X") is None

    r = await client.post(f"/api/agent/{MASTER_AGENT}/token")
    assert r.status_code == 403


async def test_cap_token_khi_da_dat_mat_khau_thi_tra_token_mot_lan(seeded_web: Database) -> None:
    async with _http(tao_app(Dashboard(seeded_web, password=MAT_KHAU))) as c:
        await c.post("/login", data={"password": MAT_KHAU})
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


@pytest.mark.parametrize("duong, than", [
    ("/api/client/CL-01", {"copy_mode": "SAME"}),
    ("/api/client", {"client_id": "CL-9", "agent_id": "AG-CLIENT"}),
    ("/api/master_close_route", {"close_route": "EA"}),
    ("/api/symbol_map", {"client_id": "CL-01", "master_symbol": "X", "client_symbol": "Y"}),
    ("/api/symbol_map/disable", {"client_id": "CL-01", "master_symbol": "X"}),
    ("/api/system_config", {"khoa": "ui_open_queue_max_len", "gia_tri": 5}),
    ("/api/agent", {"agent_id": "AG-X", "role": "CLIENT", "magic": 1}),
    ("/api/agent/AG-MASTER/token", {}),
])
async def test_moi_endpoint_ghi_deu_doi_dang_nhap(seeded_web: Database, duong: str,
                                                  than: dict) -> None:
    async with _http(tao_app(Dashboard(seeded_web, password=MAT_KHAU))) as c:
        r = await c.post(duong, json=than)
        assert r.status_code == 401, duong


async def test_trang_cau_hinh_hien_config_toml_nhung_che_bi_mat(seeded_web: Database) -> None:
    """Biết `dashboard_password` đang trống là thông tin vận hành; biết nó là gì thì không."""
    config = parse_config({
        "bridge": {"host": "127.0.0.1", "port": 8787, "web_port": 8080},
        "security": {"dashboard_password": "sieu-bi-mat"},
        "clicker": {"token": "tok", "account_login": 538217, "terminal_title": "538217"},
    }, source_path=Path("config.toml"), project_root=Path("."))
    async with _http(tao_app(Dashboard(seeded_web, config=config))) as c:
        r = await c.get("/api/config")
    khoa = {d["khoa"]: d["gia_tri"] for d in r.json()["file_config"]}
    assert khoa["security.dashboard_password"] == UI["cfg_file_masked"]
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
        assert any(m.startswith(d) or d.startswith(m) for m in mau), f"app.js goi {d} khong co route"


async def test_khai_terminal_cho_clicker_va_cat_ket_noi_de_nap_lai(seeded_web) -> None:
    """Khai trên dashboard rồi clicker nhận ở lần bắt tay kế tiếp — không phải chạy lại tác vụ."""
    seeded_web.upsert_agent("AG-CLICKER", role="CLICKER", token_hash="h", magic_number=770001,
                            account_login=538217)
    da_dong: list[tuple[str, str]] = []

    class ServerGia:
        def dong_ket_noi(self, agent_id: str, ly_do: str) -> bool:
            da_dong.append((agent_id, ly_do))
            return True

    async with _http(tao_app(Dashboard(seeded_web, server=ServerGia()))) as c:
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
dashboard_password = "mat-khau-thu-nghiem"

[clicker]
token = "tok"
"""


def _dashboard_co_file(db: Database, tmp_path: Path) -> tuple[Dashboard, Path]:
    duong_dan = tmp_path / "config.toml"
    duong_dan.write_text(MAU_FILE_CONFIG, encoding="utf-8")
    config = parse_config(tomllib.loads(MAU_FILE_CONFIG), source_path=duong_dan,
                          project_root=tmp_path)
    return Dashboard(db, password=MAT_KHAU, config=config), duong_dan


async def test_sua_config_toml_tu_dashboard_va_giu_chu_thich(seeded_web: Database,
                                                             tmp_path: Path) -> None:
    dashboard, duong_dan = _dashboard_co_file(seeded_web, tmp_path)
    async with _http(tao_app(dashboard)) as c:
        await c.post("/login", data={"password": MAT_KHAU})
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
        await c.post("/login", data={"password": MAT_KHAU})
        r = await c.post("/api/file_config", json={"doi": {"bridge.web_port": 8787}})
    assert r.status_code == 400
    assert r.json()["error"] == "CONFIG_KHONG_HOP_LE"
    assert duong_dan.read_text(encoding="utf-8") == MAU_FILE_CONFIG


async def test_khoa_ngoai_danh_sach_khong_ghi_vao_config_toml(seeded_web: Database,
                                                              tmp_path: Path) -> None:
    dashboard, duong_dan = _dashboard_co_file(seeded_web, tmp_path)
    async with _http(tao_app(dashboard)) as c:
        await c.post("/login", data={"password": MAT_KHAU})
        r = await c.post("/api/file_config", json={"doi": {"bridge.khoa_la": "x"}})
    assert r.status_code == 400
    assert duong_dan.read_text(encoding="utf-8") == MAU_FILE_CONFIG


async def test_bi_mat_khong_bao_gio_di_ra_khoi_bridge(seeded_web: Database,
                                                      tmp_path: Path) -> None:
    dashboard, _ = _dashboard_co_file(seeded_web, tmp_path)
    async with _http(tao_app(dashboard)) as c:
        await c.post("/login", data={"password": MAT_KHAU})
        r = await c.get("/api/config")
    assert "mat-khau-thu-nghiem" not in r.text
    assert "tok" not in [d["gia_tri"] for d in r.json()["file_config"]]
    khoa = {d["khoa"]: d for d in r.json()["file_config"]}
    assert khoa["security.dashboard_password"]["bi_mat"] is True
    assert khoa["security.dashboard_password"]["gia_tri"] == UI["cfg_file_masked"]
    assert khoa["bridge.port"]["gia_tri"] == "8787"


async def test_doi_mat_khau_dashboard_tren_ui_thi_ghi_vao_file(seeded_web: Database,
                                                               tmp_path: Path) -> None:
    dashboard, duong_dan = _dashboard_co_file(seeded_web, tmp_path)
    async with _http(tao_app(dashboard)) as c:
        await c.post("/login", data={"password": MAT_KHAU})
        r = await c.post("/api/file_config",
                         json={"doi": {"security.dashboard_password": "mat-khau-moi"}})
    assert r.status_code == 200
    doc = tomllib.loads(duong_dan.read_text(encoding="utf-8"))
    assert doc["security"]["dashboard_password"] == "mat-khau-moi"
    # Tien trinh dang chay KHONG nap lai: cau hinh khoi dong nua nap nua khong la trang thai
    # khong ai luong duoc. Mat khau cu van dung cho toi khi khoi dong lai dich vu.
    assert dashboard.password == MAT_KHAU


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
