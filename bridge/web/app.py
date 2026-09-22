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
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from bridge.config import ConfigError, sua_config_toml
from bridge.db.repo import Database
from bridge.engine.reconcile import Reconciler
from bridge.labels_vi import LOI_CAU_HINH, UI
from bridge.logging_setup import get_logger
from bridge.ops import (
    LoiCauHinh,
    cap_token,
    dat_duong_dong_master,
    dat_lai_lich_su,
    dat_lai_toan_bo,
    dat_terminal_clicker,
    dat_tich_huong_dan,
    huy_client_moi,
    khai_anh_xa,
    sua_client,
    sua_khoa_he_thong,
    tao_agent,
    tao_client,
    tao_client_moi,
    tat_anh_xa,
    xoa_anh_xa,
    xoa_client,
)
from bridge.web import views
from bridge.web.lenh import LENH_CHAY_DUOC, chay

log = get_logger(__name__)

STATIC = Path(__file__).parent / "static"

#: Chuỗi phải gõ đúng để đặt lại. **Cố ý không dấu**: một cụm có dấu sẽ phụ thuộc vào bộ gõ đang
#: ở chế độ nào, và hai cụm **khác nhau** để không ai vừa định xoá dữ liệu lại xoá luôn cấu hình.
CUM_DAT_LAI = {"lich_su": UI["reset_phrase_data"], "toan_bo": UI["reset_phrase_all"]}

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

    def __init__(self, db: Database, processor: Any = None, server: Any = None,
                 config: Any = None) -> None:
        self.db = db
        #: `Config` đã nạp lúc Bridge khởi động. Trang Cấu hình hiện các khoá của `config.toml`
        #: và sửa được chúng (`/api/file_config`), nhưng **tiến trình đang chạy không nạp lại**:
        #: cấu hình khởi động nửa nạp nửa không là trạng thái không ai lường được. Giá trị mới có
        #: hiệu lực khi khởi động lại dịch vụ, và trang nói đúng điều đó.
        self.config = config
        #: `EventProcessor` — để gọi `reconciler` và `closing`. Có thể None khi chỉ xem.
        self.processor = processor
        self.server = server

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

    # -- trang ---------------------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def trang_chinh() -> Any:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    # -- API đọc -------------------------------------------------------------------------------

    @app.get("/api/snapshot")
    async def api_snapshot() -> Any:
        return dashboard.anh_chup()

    @app.get("/api/findings")
    async def api_findings() -> Any:
        return {"ui": UI, **views.danh_sach_sai_lech(dashboard.db)}

    @app.get("/api/alerts")
    async def api_alerts(level: str | None = None) -> Any:
        return {"ui": UI, "alerts": views.nhat_ky(dashboard.db, level)}

    @app.get("/api/config")
    async def api_config() -> Any:
        return {"ui": UI, **views.trang_cau_hinh(dashboard.db, dashboard.config)}

    @app.get("/api/huong_dan")
    async def api_huong_dan() -> Any:
        """Hai danh sách việc từng bước, kèm trạng thái đã kiểm được của từng bước."""
        return {"ui": UI, **views.trang_huong_dan(dashboard.db, dashboard.config)}

    @app.get("/api/preview")
    async def api_preview(multiplier: float) -> Any:
        return {"lines": views.xem_truoc_he_so(multiplier)}

    # -- API ghi -------------------------------------------------------------------------------

    @app.post("/api/run_mode")
    async def api_run_mode(request: Request) -> Any:
        body = await request.json()
        mode = body.get("mode")
        if mode not in ("RUNNING", "PAUSE_NEW_ENTRIES", "PAUSED"):
            return JSONResponse({"error": "bad_mode"}, status_code=400)
        dashboard.db.set_config("run_mode", mode)
        log.info("Dashboard doi run_mode sang %s", mode)
        return {"ok": True, "mode": mode}

    @app.post("/api/huong_dan/tich")
    async def api_tich_huong_dan(request: Request) -> Any:
        """Bật/tắt một ô tự tích của trang Hướng dẫn.

        Đi qua `_chan_ghi` như mọi nút Lưu: ô tích là một lần **ghi vào database**, và một dashboard
        không mật khẩu thì cho qua mọi request — không có lý do gì để ô này là ngoại lệ.
        """
        body = await request.json()
        try:
            da = dat_tich_huong_dan(dashboard.db, str(body.get("ma") or ""),
                                    bool(body.get("tich")))
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        return {"ok": True, "da_tich": sorted(da)}

    @app.post("/api/dat_lai")
    async def api_dat_lai(request: Request) -> Any:
        """Đặt lại hệ thống. Hai mức, và cả hai đều bắt gõ đúng một cụm xác nhận riêng.

        Ràng buộc nằm ở `ops`: phải đang `PAUSED`, không còn cặp hay vị thế Master đang mở, không
        còn lệnh nào chưa xong — và sao lưu trước khi xoá.
        """
        body = await request.json()
        kieu = body.get("kieu")
        if kieu not in CUM_DAT_LAI:
            return _tra_loi(LoiCauHinh("KIEU_DAT_LAI_LA", kieu=kieu))
        if (body.get("phrase") or "").strip() != CUM_DAT_LAI[kieu]:
            log.warning("Bam dat lai (%s) nhung cum xac nhan sai, khong lam gi", kieu)
            return _tra_loi(LoiCauHinh("CUM_TU_SAI"))
        ham = dat_lai_lich_su if kieu == "lich_su" else dat_lai_toan_bo
        try:
            kq = ham(dashboard.db)
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        log.warning("Dashboard dat lai (%s): %s", kieu, kq["da_xoa"])
        return {"ok": True, "kieu": kieu, **kq}

    @app.post("/api/findings/{finding_id}/accept")
    async def api_accept(finding_id: int) -> Any:
        # Kiểm TRƯỚC khi đụng tới engine: câu trả lời cho một hành động chạm MT5 là "không", và
        # nó không phụ thuộc việc engine có đang chạy hay không. Dashboard chỉ sửa **sổ sách**;
        # đóng (hoặc mở) một vị thế thật là việc làm trong MT5, rồi quay lại bấm Bỏ qua kèm ghi
        # chú (D-34).
        f = dashboard.db.get_finding(finding_id)
        if f is not None and Reconciler.cham_mt5(f["suggested_action"]):
            return _tra_loi(LoiCauHinh("HANH_DONG_CHAM_MT5",
                                       hanh_dong=f["suggested_action"]))
        if dashboard.processor is None:
            return JSONResponse({"error": "no_engine"}, status_code=503)
        ok = await dashboard.processor.reconciler.accept_finding(finding_id)
        return {"ok": ok}

    @app.post("/api/findings/{finding_id}/skip")
    async def api_skip(finding_id: int, request: Request) -> Any:
        body = await request.json()
        note = (body.get("note") or "").strip()
        if not note:
            return JSONResponse({"error": "note_required"}, status_code=400)
        if dashboard.processor is None:
            return JSONResponse({"error": "no_engine"}, status_code=503)
        return {"ok": dashboard.processor.reconciler.skip_finding(finding_id, note)}

    @app.post("/api/alerts/{alert_id}/ack")
    async def api_ack(alert_id: int) -> Any:
        dashboard.db.acknowledge_alert(alert_id)
        return {"ok": True}

    @app.post("/api/symbol_map/verify")
    async def api_verify_map(request: Request) -> Any:
        """Kiểm tra symbol **với sàn**, không chỉ kiểm chính tả.

        Gõ nhầm `XAUUSDm` thành `XAUUSDn` xảy ra thường xuyên, và hậu quả lộ ra đúng lúc Master
        vừa vào lệnh. Nguy hiểm hơn: tên copy từ website broker có thể chứa ký tự Cyrillic nhìn
        giống hệt chữ Latin. Chỉ có đối chiếu với spec sàn đẩy lên mới bắt được.
        """
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
    async def api_sua_client(client_id: str, request: Request) -> Any:
        body = await request.json()
        try:
            doi, dang_mo = sua_client(
                dashboard.db, client_id,
                copy_mode=body.get("copy_mode"),
                volume_multiplier=body.get("volume_multiplier"),
                open_route=body.get("open_route"),
                close_route=body.get("close_route"),
                can_close_master=body.get("can_close_master"),
                enabled=body.get("enabled"),
            )
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        log.info("Dashboard sua client %s: %s", client_id, doi)
        return {"ok": True, "doi": doi, "dang_mo": dang_mo}

    @app.post("/api/client")
    async def api_tao_client(request: Request) -> Any:
        body = await request.json()
        try:
            da = tao_client(dashboard.db, body.get("client_id") or "", body.get("agent_id") or "",
                            body.get("clicker_agent"), body.get("open_route") or "UI",
                            body.get("close_route"), body.get("ten"))
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        log.info("Dashboard tao client %s", da["client_id"])
        return {"ok": True, "client": da}

    @app.post("/api/client_moi")
    async def api_client_moi() -> Any:
        """Tạo một Client mới cùng **tất cả** thứ đi kèm, không hỏi gì.

        Mã Client, tên hai agent, tên mục clicker, tên Scheduled Task — tất cả suy từ một con số
        (số thứ tự của Client), nên hỏi từng cái chỉ tạo cơ hội đặt lệch nhau. Việc duy nhất còn
        lại cho người dùng là dán token vào EA và chạy một câu lệnh trên VPS: đăng ký Scheduled
        Task cần quyền Administrator, trình duyệt không với tới.
        """
        try:
            kq = tao_client_moi(dashboard.db)
        except LoiCauHinh as exc:
            return _tra_loi(exc)

        # Phần DB chạy ngay trên vòng sự kiện (sqlite cục bộ, vài mili giây). Phần ghi file thì
        # KHÔNG: `sua_config_toml` gọi `icacls`, và một lần treo vài giây ở đây là heartbeat của
        # agent trễ theo, agent rơi OFFLINE, D-25 ngừng copy lệnh.
        #
        # Và **không** gộp hai thứ vào một lần `to_thread`: `sqlite3` chỉ dùng được trong đúng
        # luồng đã tạo kết nối, nên gộp là nhận `SQLite objects created in a thread...` — đã gặp
        # thật ở lần bấm nút đầu tiên.
        cfg = dashboard.config
        token_clicker = kq.pop("token_clicker")
        if cfg is not None:
            try:
                await asyncio.to_thread(
                    sua_config_toml, Path(cfg.source_path),
                    {f"{kq['muc_clicker']}.token": token_clicker}, Path(cfg.project_root))
            except (ConfigError, OSError) as exc:
                huy_client_moi(dashboard.db, kq["client_id"], [kq["agent"], kq["clicker"]])
                return JSONResponse({"error": "KHONG_GHI_DUOC_FILE", "message": str(exc)},
                                    status_code=500)
        # Câu lệnh đăng ký tác vụ: in ra đúng dạng dán chạy được, không bắt người dùng tự ghép.
        kq["lenh_tac_vu"] = (f".\\scripts\\tao-dich-vu.ps1 -ChiTacVuClicker "
                             f"-TacVuClicker {kq['muc_clicker']}")
        return {"ok": True, **kq}

    @app.post("/api/client/{client_id}/delete")
    async def api_xoa_client(client_id: str) -> Any:
        """Xoá hẳn một Client. Từ chối khi nó đã có cặp lệnh — khi đó hãy **tắt**."""
        try:
            xoa_client(dashboard.db, client_id)
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        log.warning("Dashboard xoa client %s", client_id)
        return {"ok": True}

    @app.post("/api/master_close_route")
    async def api_duong_dong_master(request: Request) -> Any:
        body = await request.json()
        try:
            doi = dat_duong_dong_master(dashboard.db, body.get("clicker_agent"),
                                        body.get("close_route"))
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        log.info("Dashboard doi duong dong Master: %s", doi)
        return {"ok": True, "doi": doi}

    @app.post("/api/symbol_map")
    async def api_luu_anh_xa(request: Request) -> Any:
        """Kiểm với sàn **rồi mới** lưu — cùng phép kiểm của `/api/symbol_map/verify`."""
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
    async def api_tat_anh_xa(request: Request) -> Any:
        body = await request.json()
        try:
            tat_anh_xa(dashboard.db, body.get("client_id") or "",
                       (body.get("master_symbol") or "").strip())
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        return {"ok": True}

    @app.post("/api/symbol_map/delete")
    async def api_xoa_anh_xa(request: Request) -> Any:
        """Xoá hẳn một ánh xạ. Tắt thì dòng còn đó; xoá thì không còn dấu vết."""
        body = await request.json()
        try:
            xoa_anh_xa(dashboard.db, body.get("client_id") or "",
                       (body.get("master_symbol") or "").strip())
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        return {"ok": True}

    @app.post("/api/system_config")
    async def api_khoa_he_thong(request: Request) -> Any:
        body = await request.json()
        try:
            gia_tri = sua_khoa_he_thong(dashboard.db, body.get("khoa") or "", body.get("gia_tri"))
        except LoiCauHinh as exc:
            return _tra_loi(exc)
        return {"ok": True, "khoa": body.get("khoa"), "gia_tri": gia_tri}

    @app.post("/api/file_config")
    async def api_sua_file_config(request: Request) -> Any:
        """Sửa `config.toml`. Kiểm nội dung mới **trước khi** ghi, và sao lưu bản cũ.

        Một `config.toml` hỏng là một Bridge không khởi động được — và lúc đó không còn dashboard
        nào để sửa lại. Nên phép kiểm ở đây chạy đúng `parse_config` của đường khởi động, chứ
        không phải một bản kiểm rút gọn viết riêng cho tầng web.
        """
        if dashboard.config is None:
            return _tra_loi(LoiCauHinh("KHONG_CO_FILE_CONFIG"), status=409)
        body = await request.json()
        doi = body.get("doi") or {}
        if not isinstance(doi, dict) or not doi:
            return _tra_loi(LoiCauHinh("KHONG_CO_GI_DOI"))
        try:
            # Chạy ở luồng khác: `sua_config_toml` đọc/ghi file và gọi `icacls`, mà dashboard
            # dùng **chung vòng sự kiện** với Bridge. Một lần `icacls` treo vài giây là heartbeat
            # của agent trễ theo, agent rơi OFFLINE, và D-25 ngừng copy lệnh.
            ban_sao = await asyncio.to_thread(
                sua_config_toml, Path(dashboard.config.source_path), doi,
                Path(dashboard.config.project_root))
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
    async def api_tao_agent(request: Request) -> Any:
        """Tạo agent và trả token thô **đúng một lần**. Không ghi log, không lưu lại."""
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
    async def api_terminal_clicker(agent_id: str, request: Request) -> Any:
        """Khai terminal của một clicker. Clicker đang chạy nhận giá trị mới trong vài giây."""
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
        # Cắt kết nối để clicker nối lại và đọc cấu hình mới — nhưng **không** cắt khi nó đang
        # giữ một lệnh chưa xong: command đã gửi mà chưa ack sẽ mất theo kết nối, và lệnh đó có
        # thể là một lệnh đóng. Còn lệnh đang bay thì để clicker nhận giá trị mới ở lần nối lại
        # kế tiếp; trang nói rõ điều đó qua `nap_lai`.
        nap_lai = False
        if doi and dashboard.server is not None:
            dang_bay = [c for c in dashboard.db.list_inflight_commands()
                        if c["target_agent_id"] == agent_id]
            if not dang_bay:
                nap_lai = dashboard.server.dong_ket_noi(agent_id, "doi terminal tu dashboard")
            else:
                log.warning("Khong cat ket noi %s de nap lai: dang co %d lenh chua xong",
                            agent_id, len(dang_bay))
        return {"ok": True, "doi": doi, "nap_lai": nap_lai}

    @app.post("/api/chay/{ma}")
    async def api_chay(ma: str) -> Any:
        """Chạy một lệnh trong **danh sách trắng cố định**. Xem `bridge/web/lenh.py`.

        Trình duyệt gửi MÃ, không gửi câu lệnh. Mã lạ thì từ chối — không đoán, không ghép chuỗi.
        """
        if ma not in LENH_CHAY_DUOC:
            log.warning("Dashboard xin chay ma la: %r", ma)
            return _tra_loi(LoiCauHinh("LENH_KHONG_CHAY_DUOC", lenh=ma))
        goc = getattr(dashboard.config, "project_root", None) or Path.cwd()
        return {"ok": True, **await chay(ma, Path(goc))}

    @app.post("/api/agent/{agent_id}/token")
    async def api_cap_token(agent_id: str) -> Any:
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
