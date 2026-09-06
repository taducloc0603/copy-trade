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

import uvicorn

from bridge.config import ConfigError, load_config
from bridge.db.repo import Database
from bridge.engine.processor import EventProcessor
from bridge.logging_setup import get_logger, setup_logging
from bridge.protocol.dispatcher import CommandDispatcher
from bridge.protocol.server import BridgeServer, ServerConfig
from bridge.web.app import Dashboard, tao_app

log = get_logger(__name__)


async def run() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        log.critical("Khong doc duoc cau hinh: %s", exc)
        return 2

    db = Database(config.db_path)
    run_mode = db.get_config("run_mode")
    log.info("Bridge khoi dong, database %s, run_mode = %s", config.db_path, run_mode)
    if run_mode != "PAUSED":
        # Khong tu sua ve PAUSED: gia tri nay do nguoi van hanh dat, va tu doi
        # trang thai van hanh sau lung ho la viec khong duoc phep.
        log.warning("run_mode dang la %s chu khong phai PAUSED", run_mode)

    server = BridgeServer(db, ServerConfig(host=config.bridge.host, port=config.bridge.port))
    dispatcher = CommandDispatcher(db, server)
    processor = EventProcessor(db, server, dispatcher)
    await server.start()
    await processor.start()

    # Dashboard chạy trong cùng tiến trình: nó đọc thẳng SQLite cục bộ và gọi API của tầng
    # engine, nên không cần tiến trình riêng và không có đường nào để hai bên lệch trạng thái.
    dashboard = Dashboard(db, password=config.security.get("dashboard_password"),
                          processor=processor, server=server)
    web = uvicorn.Server(uvicorn.Config(
        tao_app(dashboard), host=config.bridge.host, port=config.bridge.web_port,
        log_level="warning", access_log=False))
    web_task = asyncio.create_task(web.serve())
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
