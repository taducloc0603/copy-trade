"""Chạy Bridge như một tiến trình: ``python -m bridge``.

Ở phase 4 đây mới chỉ là **đường ống**: nhận kết nối agent, ghi event vào DB, gửi command.
Chưa có vòng xử lý nghiệp vụ (`bridge/engine/`, phase 6) và chưa có dashboard (phase 9).

Bridge luôn khởi động ở `run_mode = PAUSED` (D-15). Không có đường tự động chuyển sang
`RUNNING` — kể cả ở đây.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import socket

import uvicorn

from bridge.alerting import tao_kenh
from bridge.config import ConfigError, load_config
from bridge.db.repo import Database
from bridge.engine.processor import EventProcessor
from bridge.logging_setup import get_logger, setup_logging
from bridge.protocol.dispatcher import CommandDispatcher
from bridge.protocol.server import BridgeServer, ServerConfig
from bridge.web.app import Dashboard, tao_app

log = get_logger(__name__)


def ep_ve_paused(db: Database) -> str | None:
    """Ép `run_mode` về `PAUSED` mỗi lần khởi động (D-15). Trả về giá trị trước đó.

    Không phải chỉ cảnh báo. `run_mode` nằm trong DB nên nó **sống sót qua mất điện**: máy tự bật
    lại lúc 3 giờ sáng với `RUNNING` còn nguyên trong bảng `config` là hệ thống tự hồi sinh và vào
    lệnh khi chưa ai kịp nhìn màn hình — đúng thứ D-15 tồn tại để chặn. Cái giá là mỗi lần khởi
    động lại đều phải bấm `RUNNING` bằng tay, và đó là chủ đích.
    """
    truoc = db.get_config("run_mode")
    if truoc != "PAUSED":
        db.set_config("run_mode", "PAUSED")
        # ERROR (B-08): D-15 sinh ra cho tinh huong may tu bat lai luc khong ai nhin man
        # hinh — dung tinh huong do ma de o WARNING thi canh bao khong di den dau ca, trong
        # khi thuc te la HE THONG DA NGUNG COPY.
        db.create_alert("ERROR", "KHOI_DONG_EP_PAUSED",
                        f"Bridge khoi dong lai: dat run_mode tu {truoc} ve PAUSED theo D-15")
        log.warning("run_mode dang la %s, da dat ve PAUSED (D-15)", truoc)
    return truoc


def cong_dang_ban(host: str, port: int) -> OSError | None:
    """Thử chiếm cổng trước để báo lỗi tử tế thay vì để traceback nổi lên.

    Không đặt ``SO_REUSEADDR``: trên Windows cờ đó cho phép chiếm chồng lên cổng người khác
    đang giữ, nên bật nó vào đây là biến phép thử này thành luôn luôn "rảnh".
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as thu:
        try:
            thu.bind((host, port))
        except OSError as exc:
            return exc
    return None


def bao_cong_ban(host: str, port: int, ten: str, exc: OSError) -> None:
    """Một dòng nói đúng việc cần làm. Traceback 20 dòng ở đây không thêm thông tin gì."""
    log.critical(
        "Cong %s %s:%d dang bi tien trinh khac giu, Bridge khong khoi dong duoc (%s). "
        "Neu dich vu CopyBridge dang chay thi dung no truoc: Stop-Service CopyBridge. "
        "Hoac tim tien trinh dang giu cong: Get-NetTCPConnection -LocalPort %d | Select-Object OwningProcess",
        ten, host, port, exc, port)


async def run() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        log.critical("Khong doc duoc cau hinh: %s", exc)
        return 2

    db = Database(config.db_path)
    truoc = ep_ve_paused(db)
    log.info("Bridge khoi dong, database %s, run_mode truoc do = %s", config.db_path, truoc)

    # Kiểm cả hai cổng trước khi dựng bất cứ thứ gì: hỏng ở đây thì chưa có gì phải dọn.
    for cong, ten in ((config.bridge.port, "agent"), (config.bridge.web_port, "dashboard")):
        ban = cong_dang_ban(config.bridge.host, cong)
        if ban is not None:
            bao_cong_ban(config.bridge.host, cong, ten, ban)
            db.close()
            return 2

    server = BridgeServer(db, ServerConfig(host=config.bridge.host, port=config.bridge.port))
    dispatcher = CommandDispatcher(db, server)
    processor = EventProcessor(db, server, dispatcher)
    try:
        await server.start()
    except OSError as exc:
        # Có khe hở giữa lúc kiểm và lúc chiếm thật, nên vẫn phải bắt ở đây.
        bao_cong_ban(config.bridge.host, config.bridge.port, "agent", exc)
        db.close()
        return 2
    await processor.start()

    # Dashboard chạy trong cùng tiến trình: nó đọc thẳng SQLite cục bộ và gọi API của tầng
    # engine, nên không cần tiến trình riêng và không có đường nào để hai bên lệch trạng thái.
    dashboard = Dashboard(db, password=config.security.get("dashboard_password"),
                          processor=processor, server=server)
    web = uvicorn.Server(uvicorn.Config(
        tao_app(dashboard), host=config.bridge.host, port=config.bridge.web_port,
        log_level="warning", access_log=False))
    web_task = asyncio.create_task(web.serve())

    # Kênh cảnh báo ra ngoài chạy ở task riêng. Nó hỏng thì chỉ mất thông báo, luồng giao dịch
    # không hề biết (plan 10.4).
    kenh = tao_kenh(db, config.security)
    await kenh.start()
    log.info("Dashboard tai http://%s:%d", config.bridge.host, config.bridge.web_port)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    with contextlib.suppress(NotImplementedError):
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

    try:
        await stop.wait()
    except asyncio.CancelledError:
        pass
    finally:
        log.info("Bridge dung lai")
        await kenh.stop()
        web.should_exit = True
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(web_task, timeout=5)
        await processor.stop()
        await server.stop()
        db.close()
    return 0


def main() -> int:
    setup_logging(level=logging.INFO)
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
