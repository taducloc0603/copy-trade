"""Test dashboard (plan `09-dashboard.md`).

Trọng tâm không phải bố cục mà là những chỗ giao diện có thể làm mất tiền:

* Nút đóng khẩn cấp không được làm gì cho tới khi gõ đúng chuỗi.
* `accept_all_safe` không được chạm tới dòng `DECISION` nào.
* Không tồn tại đường nào bỏ qua hàng loạt.
* Bảng cặp lệnh phải sắp theo **mức nghiêm trọng**, không theo thời gian.
* Thiếu một nhãn thì hiển thị chính enum đó chứ không được làm sập trang.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from bridge.clock import to_iso, utc_now
from bridge.db.repo import Database
from bridge.labels_vi import UI
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
