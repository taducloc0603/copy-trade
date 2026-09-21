"""Dashboard: FastAPI + WebSocket, phục vụ bởi chính Bridge (plan mục 9.1).

Hai ranh giới không được vượt:

* **Tầng web chỉ hiển thị và gọi API của `bridge/engine/`.** Không có câu SQL nào ở đây cập nhật
  `pair`. Thấy mình đang viết một câu như vậy nghĩa là đang viết lại logic đã có.
* **Không chuỗi tiếng Việt nào trong template hay JavaScript** (D-16). Chữ đi từ
  `bridge/labels_vi.py` xuống qua JSON; JS chỉ hiển thị thứ nó nhận được.

Toàn bộ dữ liệu đọc thẳng từ SQLite cục bộ — đúng lúc mất mạng là lúc cần nhìn thấy trạng thái
nhất, nên trang này không được phụ thuộc bất cứ thứ gì ngoài máy.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import secrets
from pathlib import Path
from typing import Any

from fastapi import Cookie, FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from bridge.config import ConfigError, sua_config_toml
from bridge.db.repo import Database
from bridge.labels_vi import LOI_CAU_HINH, UI
from bridge.logging_setup import get_logger
from bridge.ops import (
    LoiCauHinh,
    cap_token,
    dat_duong_dong_master,
    dat_terminal_clicker,
    khai_anh_xa,
    sua_client,
    sua_khoa_he_thong,
    tao_agent,
    tao_client,
    tat_anh_xa,
)
from bridge.web import views

log = get_logger(__name__)

STATIC = Path(__file__).parent / "static"

#: Chuỗi phải gõ đúng để đóng khẩn cấp. **Cố ý không dấu**: bắt gõ tiếng Việt có dấu trong lúc
#: hoảng, với bộ gõ có thể đang ở chế độ khác, là tự tạo thêm rắc rối.
EMERGENCY_PHRASE = UI["emergency_phrase"]

WS_PUSH_SEC = 1.0


def _tra_loi(exc: LoiCauHinh, status: int = 400) -> JSONResponse:
    """Mã lỗi của `ops` → JSON kèm câu tiếng Việt đã dựng sẵn.

    JavaScript chỉ hiển thị `message`; nó không bao giờ dựng câu, không bao giờ chứa chữ (D-16).
    """
    mau = LOI_CAU_HINH.get(exc.ma, exc.ma)
    try:
        cau = mau.format(**exc.ngu_canh)
    except (KeyError, IndexError):
        cau = mau
    return JSONResponse({"error": exc.ma, "message": cau}, status_code=status)


class Dashboard:
    """Gói trạng thái của dashboard. Tách khỏi module-level để test dựng được nhiều bản."""

    def __init__(self, db: Database, password: str | None = None,
                 processor: Any = None, server: Any = None, config: Any = None) -> None:
        self.db = db
        self.password = password
        #: `Config` đã nạp lúc Bridge khởi động. Trang Cấu hình hiện các khoá của `config.toml`
        #: và sửa được chúng (`/api/file_config`), nhưng **tiến trình đang chạy không nạp lại**:
        #: cấu hình khởi động nửa nạp nửa không là trạng thái không ai lường được. Giá trị mới có
        #: hiệu lực khi khởi động lại dịch vụ, và trang nói đúng điều đó.
        self.config = config
        #: `EventProcessor` — để gọi `reconciler` và `closing`. Có thể None khi chỉ xem.
        self.processor = processor
        self.server = server
        self.sessions: set[str] = set()

    # -- xác thực ------------------------------------------------------------------------------

    def can_dang_nhap(self) -> bool:
        """Không đặt mật khẩu thì không bắt đăng nhập.

        Tailscale đã lo phần mạng, nhưng vẫn nên có một lớp để người khác trong mạng nội bộ
        không mở được. Bỏ trống là lựa chọn có ý thức của người vận hành, không phải mặc định
        âm thầm.
        """
        return bool(self.password)

    def kiem_tra(self, mat_khau: str) -> str | None:
        if not self.can_dang_nhap():
            return None
        if not hmac.compare_digest(mat_khau, self.password or ""):
            return None
        token = secrets.token_urlsafe(24)
        self.sessions.add(token)
        return token

    def hop_le(self, token: str | None) -> bool:
        if not self.can_dang_nhap():
            return True
        return bool(token) and token in self.sessions

    # -- dữ liệu đẩy xuống ---------------------------------------------------------------------

    def anh_chup(self) -> dict[str, Any]:
        """Toàn bộ dữ liệu một lần cho trang chính."""
        return {
            "ui": UI,
            "status": views.trang_thai_chung(self.db, self.server),
            "metrics": views.chi_so(self.db),
            "pairs": views.bang_cap_lenh(self.db),
            "findings_count": views.danh_sach_sai_lech(self.db)["tong"],
        }


def tao_app(dashboard: Dashboard) -> FastAPI:
    app = FastAPI(title=UI["app_title"], docs_url=None, redoc_url=None)

    class TinhKhongGiuCache(StaticFiles):
        """Trình duyệt phải **hỏi lại** mỗi lần, thay vì tự giữ bản cũ.

        Sau một lần `cai-dat.ps1 -CapNhat`, CSS/JS trên đĩa đã mới còn tab đang mở vẫn chạy bản
        cũ — và triệu chứng là "sửa xong mà dashboard không đổi gì", thứ người ta sẽ đi tìm
        nguyên nhân ở mọi chỗ trừ cache. `no-cache` không có nghĩa là tải lại toàn bộ: ETag vẫn
        cho câu trả lời 304 rẻ tiền, chỉ là trình duyệt không được tự quyết bỏ qua lần hỏi.
        """

        def is_not_modified(self, response_headers: Any, request_headers: Any) -> bool:
            return super().is_not_modified(response_headers, request_headers)

        def file_response(self, *args: Any, **kwargs: Any) -> Any:
            res = super().file_response(*args, **kwargs)
            res.headers["cache-control"] = "no-cache"
            return res

    # Phục vụ CSS/JS từ đĩa. Không CDN: đúng lúc mất mạng là lúc cần nhìn thấy trạng thái nhất.
    app.mount("/static", TinhKhongGiuCache(directory=STATIC), name="static")

    def _chan(sid: str | None) -> JSONResponse | None:
        if dashboard.hop_le(sid):
            return None
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    def _chan_cap_token() -> JSONResponse | None:
        """Không có mật khẩu dashboard thì **không** cấp token ở đây.

        `hop_le` cho qua mọi request khi `password` rỗng, và `config.py` chỉ bắt buộc mật khẩu khi
        `host` không phải loopback — nên trên đúng cấu hình đang dùng, một nút cấp token sẽ là
        đường phát hành danh tính **không cần xác thực**. Sửa cấu hình thì vẫn cho (hỏng thì sửa
        lại được), nhưng token là danh tính: mất nó là mất quyền điều khiển tài khoản MT5.
        """
        if dashboard.can_dang_nhap():
            return None
        return _tra_loi(LoiCauHinh("CHUA_DAT_MAT_KHAU"), status=403)

    # -- trang ---------------------------------------------------------------------------------

    @app.get("/login", response_class=HTMLResponse)
    async def trang_dang_nhap(loi: int = 0) -> str:
        return _trang_dang_nhap(bool(loi))

    @app.post("/login")
    async def dang_nhap(password: str = Form("")) -> RedirectResponse:
        token = dashboard.kiem_tra(password)
        if token is None:
            return RedirectResponse("/login?loi=1", status_code=303)
        res = RedirectResponse("/", status_code=303)
        res.set_cookie("sid", token, httponly=True, samesite="lax")
        return res

    @app.get("/", response_class=HTMLResponse)
    async def trang_chinh(sid: str | None = Cookie(None)) -> Any:
        if not dashboard.hop_le(sid):
            return RedirectResponse("/login", status_code=303)
        return (STATIC / "index.html").read_text(encoding="utf-8")

    # -- API đọc -------------------------------------------------------------------------------

    @app.get("/api/snapshot")
    async def api_snapshot(sid: str | None = Cookie(None)) -> Any:
        return _chan(sid) or dashboard.anh_chup()

    @app.get("/api/findings")
    async def api_findings(sid: str | None = Cookie(None)) -> Any:
        return _chan(sid) or {"ui": UI, **views.danh_sach_sai_lech(dashboard.db)}

    @app.get("/api/alerts")
    async def api_alerts(level: str | None = None, sid: str | None = Cookie(None)) -> Any:
        return _chan(sid) or {"ui": UI, "alerts": views.nhat_ky(dashboard.db, level)}

    @app.get("/api/config")
    async def api_config(sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        return {"ui": UI, "co_mat_khau": dashboard.can_dang_nhap(),
                **views.trang_cau_hinh(dashboard.db, dashboard.config)}

    @app.get("/api/preview")
    async def api_preview(multiplier: float, sid: str | None = Cookie(None)) -> Any:
        return _chan(sid) or {"lines": views.xem_truoc_he_so(multiplier)}

    # -- API ghi -------------------------------------------------------------------------------

    @app.post("/api/run_mode")
    async def api_run_mode(request: Request, sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        mode = body.get("mode")
        if mode not in ("RUNNING", "PAUSE_NEW_ENTRIES", "PAUSED"):
            return JSONResponse({"error": "bad_mode"}, status_code=400)
        dashboard.db.set_config("run_mode", mode)
        log.info("Dashboard doi run_mode sang %s", mode)
        return {"ok": True, "mode": mode}

    @app.post("/api/emergency")
    async def api_emergency(request: Request, sid: str | None = Cookie(None)) -> Any:
        """Đóng khẩn cấp — chỉ chạy khi gõ đúng chuỗi xác nhận."""
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        if (body.get("phrase") or "").strip() != EMERGENCY_PHRASE:
            log.warning("Bam dong khan cap nhung chuoi xac nhan sai, khong lam gi")
            return JSONResponse({"error": "wrong_phrase", "message": UI["emergency_wrong"]},
                                status_code=400)
        dashboard.db.set_config("run_mode", "EMERGENCY")
        # Bao ra so lenh da gui cho TUNG VE. Ban cu tra `len(pairs)` — so cap duoc xet — nen no
        # bao "closed: 3" ke ca khi khong dong duoc gi, va che mat viec phia Master bi bo qua.
        so = {"client": 0, "master": 0}
        if dashboard.processor is not None:
            so = await dashboard.processor.closing.emergency_close_all()
        return {"ok": True, "closed": so["client"] + so["master"], **so}

    @app.post("/api/findings/{finding_id}/accept")
    async def api_accept(finding_id: int, sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        if dashboard.processor is None:
            return JSONResponse({"error": "no_engine"}, status_code=503)
        ok = await dashboard.processor.reconciler.accept_finding(finding_id)
        return {"ok": ok}

    @app.post("/api/findings/{finding_id}/skip")
    async def api_skip(finding_id: int, request: Request,
                       sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        note = (body.get("note") or "").strip()
        if not note:
            return JSONResponse({"error": "note_required"}, status_code=400)
        if dashboard.processor is None:
            return JSONResponse({"error": "no_engine"}, status_code=503)
        return {"ok": dashboard.processor.reconciler.skip_finding(finding_id, note)}

    @app.post("/api/findings/accept_all_safe")
    async def api_accept_all_safe(sid: str | None = Cookie(None)) -> Any:
        """Chỉ áp dụng cho `severity = SAFE`.

        Cố ý **không có** đường nào bỏ qua hàng loạt: bỏ qua là hành động cho từng dòng, và mỗi
        dòng bị bỏ qua để lại một alert tồn tại. Nút bỏ qua hàng loạt là cách mất tiền âm thầm
        nhất.
        """
        if (loi := _chan(sid)) is not None:
            return loi
        if dashboard.processor is None:
            return JSONResponse({"error": "no_engine"}, status_code=503)
        so = 0
        for f in dashboard.db.list_findings(resolution="PENDING", severity="SAFE"):
            if await dashboard.processor.reconciler.accept_finding(f["id"]):
                so += 1
        return {"ok": True, "accepted": so}

    @app.post("/api/alerts/{alert_id}/ack")
    async def api_ack(alert_id: int, sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        dashboard.db.acknowledge_alert(alert_id)
        return {"ok": True}

    @app.post("/api/symbol_map/verify")
    async def api_verify_map(request: Request, sid: str | None = Cookie(None)) -> Any:
        """Kiểm tra symbol **với sàn**, không chỉ kiểm chính tả.

        Gõ nhầm `XAUUSDm` thành `XAUUSDn` xảy ra thường xuyên, và hậu quả lộ ra đúng lúc Master
        vừa vào lệnh. Nguy hiểm hơn: tên copy từ website broker có thể chứa ký tự Cyrillic nhìn
        giống hệt chữ Latin. Chỉ có đối chiếu với spec sàn đẩy lên mới bắt được.
        """
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        client_id, client_symbol = body.get("client_id"), body.get("client_symbol")
        client = dashboard.db.get_client_account(client_id)
        if client is None:
            return JSONResponse({"error": "unknown_client"}, status_code=400)
        spec = dashboard.db.get_symbol_spec(client["agent_id"], client_symbol)
        if spec is None:
            return JSONResponse(
                {"ok": False, "message": UI["map_verify_failed"], "symbol": client_symbol},
                status_code=400)
        return {"ok": True, "spec": {k: spec[k] for k in
                                     ("symbol", "volume_min", "volume_step", "volume_max")}}

    # -- API ghi cấu hình ----------------------------------------------------------------------
    #
    # Mọi endpoint dưới đây chỉ làm ba việc: chặn phiên, đọc JSON, gọi `bridge/ops.py`. Không phép
    # kiểm nào ở đây — `ops` là chỗ duy nhất giữ ràng buộc, nên `bridge.admin` và dashboard không
    # thể nới lỏng khác nhau.

    @app.post("/api/client/{client_id}")
    async def api_sua_client(client_id: str, request: Request,
                             sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        try:
            doi, dang_mo = sua_client(
                dashboard.db, client_id,
                copy_mode=body.get("copy_mode"),
                volume_multiplier=body.get("volume_multiplier"),
                open_route=body.get("open_route"),
                close_route=body.get("close_route"),
                can_close_master=body.get("can_close_master"),
            )
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        log.info("Dashboard sua client %s: %s", client_id, doi)
        return {"ok": True, "doi": doi, "dang_mo": dang_mo}

    @app.post("/api/client")
    async def api_tao_client(request: Request, sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        try:
            da = tao_client(dashboard.db, body.get("client_id") or "", body.get("agent_id") or "",
                            body.get("clicker_agent"), body.get("open_route") or "UI",
                            body.get("close_route"), body.get("ten"))
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        log.info("Dashboard tao client %s", da["client_id"])
        return {"ok": True, "client": da}

    @app.post("/api/master_close_route")
    async def api_duong_dong_master(request: Request, sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        try:
            doi = dat_duong_dong_master(dashboard.db, body.get("clicker_agent"),
                                        body.get("close_route"))
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        log.info("Dashboard doi duong dong Master: %s", doi)
        return {"ok": True, "doi": doi}

    @app.post("/api/symbol_map")
    async def api_luu_anh_xa(request: Request, sid: str | None = Cookie(None)) -> Any:
        """Kiểm với sàn **rồi mới** lưu — cùng phép kiểm của `/api/symbol_map/verify`."""
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        try:
            spec = khai_anh_xa(dashboard.db, body.get("client_id") or "",
                               (body.get("master_symbol") or "").strip(),
                               (body.get("client_symbol") or "").strip())
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        return {"ok": True, "spec": {k: spec[k] for k in
                                     ("symbol", "volume_min", "volume_step", "volume_max")}}

    @app.post("/api/symbol_map/disable")
    async def api_tat_anh_xa(request: Request, sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        try:
            tat_anh_xa(dashboard.db, body.get("client_id") or "",
                       (body.get("master_symbol") or "").strip())
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        return {"ok": True}

    @app.post("/api/system_config")
    async def api_khoa_he_thong(request: Request, sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        try:
            gia_tri = sua_khoa_he_thong(dashboard.db, body.get("khoa") or "", body.get("gia_tri"))
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        return {"ok": True, "khoa": body.get("khoa"), "gia_tri": gia_tri}

    @app.post("/api/file_config")
    async def api_sua_file_config(request: Request, sid: str | None = Cookie(None)) -> Any:
        """Sửa `config.toml`. Kiểm nội dung mới **trước khi** ghi, và sao lưu bản cũ.

        Một `config.toml` hỏng là một Bridge không khởi động được — và lúc đó không còn dashboard
        nào để sửa lại. Nên phép kiểm ở đây chạy đúng `parse_config` của đường khởi động, chứ
        không phải một bản kiểm rút gọn viết riêng cho tầng web.
        """
        if (loi := _chan(sid)) is not None:
            return loi
        if dashboard.config is None:
            return _tra_loi(LoiCauHinh("KHONG_CO_FILE_CONFIG"), status=409)
        body = await request.json()
        doi = body.get("doi") or {}
        if not isinstance(doi, dict) or not doi:
            return _tra_loi(LoiCauHinh("KHONG_CO_GI_DOI"))
        try:
            ban_sao = sua_config_toml(Path(dashboard.config.source_path), doi,
                                      project_root=Path(dashboard.config.project_root))
        except ConfigError as exc:
            # Câu của `ConfigError` đã là tiếng Việt và nói rõ khoá nào sai, nên đưa thẳng ra.
            return JSONResponse({"error": "CONFIG_KHONG_HOP_LE", "message": str(exc)},
                                status_code=400)
        except OSError as exc:
            return JSONResponse({"error": "KHONG_GHI_DUOC_FILE", "message": str(exc)},
                                status_code=500)
        # KHÔNG nạp lại vào tiến trình đang chạy: `config.toml` là cấu hình khởi động, nửa nạp
        # nửa không là trạng thái không ai lường được. Trang báo rõ phải khởi động lại dịch vụ.
        log.warning("Dashboard sua config.toml: %s", sorted(doi))
        return {"ok": True, "ban_sao": ban_sao.name, "can_khoi_dong_lai": True}

    @app.post("/api/agent")
    async def api_tao_agent(request: Request, sid: str | None = Cookie(None)) -> Any:
        """Tạo agent và trả token thô **đúng một lần**. Không ghi log, không lưu lại."""
        if (loi := _chan(sid)) is not None:
            return loi
        if (loi := _chan_cap_token()) is not None:
            return loi
        body = await request.json()
        try:
            token = tao_agent(dashboard.db, body.get("agent_id") or "", body.get("role") or "",
                              int(body.get("magic") or 0),
                              int(body["login"]) if body.get("login") else None)
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        log.info("Dashboard tao agent %s", body.get("agent_id"))
        return {"ok": True, "token": token}

    @app.post("/api/agent/{agent_id}/terminal")
    async def api_terminal_clicker(agent_id: str, request: Request,
                                   sid: str | None = Cookie(None)) -> Any:
        """Khai terminal của một clicker. Clicker đang chạy nhận giá trị mới trong vài giây."""
        if (loi := _chan(sid)) is not None:
            return loi
        body = await request.json()
        try:
            doi = dat_terminal_clicker(
                dashboard.db, agent_id,
                int(body["login"]) if body.get("login") else None,
                body.get("terminal_title"))
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        # Clicker đọc cấu hình ở **mỗi lần bắt tay**, nên cắt kết nối là cách rẻ nhất để giá trị
        # mới có hiệu lực. Không cần thêm loại message, và vẫn đúng khi clicker đang offline.
        nap_lai = False
        if doi and dashboard.server is not None:
            nap_lai = dashboard.server.dong_ket_noi(agent_id, "doi terminal tu dashboard")
        return {"ok": True, "doi": doi, "nap_lai": nap_lai}

    @app.post("/api/agent/{agent_id}/token")
    async def api_cap_token(agent_id: str, sid: str | None = Cookie(None)) -> Any:
        if (loi := _chan(sid)) is not None:
            return loi
        if (loi := _chan_cap_token()) is not None:
            return loi
        try:
            token = cap_token(dashboard.db, agent_id)
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        log.info("Dashboard cap lai token cho %s", agent_id)
        return {"ok": True, "token": token}

    # -- WebSocket -----------------------------------------------------------------------------

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        if not dashboard.hop_le(socket.cookies.get("sid")):
            await socket.close(code=4401)
            return
        try:
            while True:
                await socket.send_text(json.dumps(dashboard.anh_chup(), ensure_ascii=False,
                                                  default=str))
                await asyncio.sleep(WS_PUSH_SEC)
        except (WebSocketDisconnect, ConnectionError):
            return
        except Exception:
            log.exception("Loi trong vong day WebSocket")

    return app


def _trang_dang_nhap(loi: bool) -> str:
    thong_bao = f'<p class="loi">{UI["login_wrong"]}</p>' if loi else ""
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{UI["login_title"]}</title><link rel="stylesheet" href="/static/app.css"></head>
<body class="dangnhap"><form method="post" action="/login">
<h1>{UI["app_title"]}</h1>{thong_bao}
<label>{UI["login_password"]}<input type="password" name="password" autofocus></label>
<button type="submit">{UI["login_submit"]}</button></form></body></html>"""
