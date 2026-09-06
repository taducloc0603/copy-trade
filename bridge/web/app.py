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

from bridge.db.repo import Database
from bridge.labels_vi import UI
from bridge.logging_setup import get_logger
from bridge.web import views

log = get_logger(__name__)

STATIC = Path(__file__).parent / "static"

#: Chuỗi phải gõ đúng để đóng khẩn cấp. **Cố ý không dấu**: bắt gõ tiếng Việt có dấu trong lúc
#: hoảng, với bộ gõ có thể đang ở chế độ khác, là tự tạo thêm rắc rối.
EMERGENCY_PHRASE = UI["emergency_phrase"]

WS_PUSH_SEC = 1.0


class Dashboard:
    """Gói trạng thái của dashboard. Tách khỏi module-level để test dựng được nhiều bản."""

    def __init__(self, db: Database, password: str | None = None,
                 processor: Any = None, server: Any = None) -> None:
        self.db = db
        self.password = password
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
    # Phục vụ CSS/JS từ đĩa. Không CDN: đúng lúc mất mạng là lúc cần nhìn thấy trạng thái nhất.
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def _chan(sid: str | None) -> JSONResponse | None:
        if dashboard.hop_le(sid):
            return None
        return JSONResponse({"error": "unauthorized"}, status_code=401)

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
        clients = [dict(r) for r in dashboard.db.query_all("SELECT * FROM client_account")]
        maps = [dict(r) for r in dashboard.db.query_all("SELECT * FROM symbol_map")]
        return {"ui": UI, "clients": clients, "symbol_maps": maps,
                "preview": views.xem_truoc_he_so(
                    clients[0]["volume_multiplier"] if clients else 1.0)}

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
