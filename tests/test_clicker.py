"""Test gói `clicker/` ở chế độ `--dry-run` (phase 6b bước 3).

Chưa có driver giao diện, nên thứ được kiểm ở đây là phần **không** phụ thuộc MT5 và cũng là
phần dễ làm hỏng nhất: giao thức, và tính bất biến khi không có giá trị trả về.

Câu hỏi trung tâm của cả file: *sau khi tiến trình chết bất cứ lúc nào, khởi động lại có bao giờ
bấm lần hai không?* Câu trả lời phải là không, trong mọi trường hợp.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from bridge.clock import to_iso, utc_now
from bridge.db.repo import Database
from bridge.protocol.auth import hash_token
from bridge.protocol.dispatcher import CommandDispatcher
from bridge.protocol.server import BridgeServer, ServerConfig
from clicker.__main__ import build_parser, main
from clicker.journal import CommandJournal
from clicker.link import ClickerLink, LinkConfig
from clicker.ui.driver import DryRunDriver, OpenDriver, OpenOutcome, OpenRequest
from tests.test_server import _wait_until

CLICKER_AGENT = "AG-CLICKER"
CLICKER_TOKEN = "token-clicker-6b"
CLICKER_LOGIN = 333333

PAYLOAD = {"symbol": "XAUUSDm", "direction": "SELL", "volume": 0.5, "deviation": 20,
           "comment": "CBabc1234567"}


def _command(command_id: str, *, payload: dict | None = None, command_type: str = "OPEN_UI",
             deadline: str | None = None) -> dict:
    return {"v": 1, "kind": "command", "ts": to_iso(utc_now()), "command_id": command_id,
            "type": command_type, "payload": PAYLOAD if payload is None else payload,
            "deadline_ts": deadline or to_iso(utc_now().replace(year=utc_now().year + 1))}


def _link(tmp_path: Path, driver: OpenDriver | None = None) -> ClickerLink:
    return ClickerLink(
        config=LinkConfig(host="127.0.0.1", port=0, token=CLICKER_TOKEN,
                          account_login=CLICKER_LOGIN),
        journal=CommandJournal(tmp_path / "clicker_commands.ndjson"),
        driver=driver or DryRunDriver(),
    )


# -- nhật ký --------------------------------------------------------------------------------

def test_giu_cho_ghi_xuong_dia_ngay(tmp_path: Path) -> None:
    """Dòng giữ chỗ phải nằm trên đĩa trước khi trả về, không phải trong bộ đệm."""
    path = tmp_path / "j.ndjson"
    journal = CommandJournal(path)
    journal.reserve("CMD-1")

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["command_id"] for r in rows] == ["CMD-1"]
    assert rows[0]["ack"] is None


def test_nhat_ky_doc_lai_duoc_sau_khi_khoi_dong_lai(tmp_path: Path) -> None:
    path = tmp_path / "j.ndjson"
    first = CommandJournal(path)
    first.reserve("CMD-1")
    first.complete("CMD-1", {"status": "ok", "retmsg": "xong"})
    first.reserve("CMD-2")

    again = CommandJournal(path)
    assert len(again) == 2
    assert again.get("CMD-1").ack["status"] == "ok"
    assert again.get("CMD-2").ack is None, "Giu cho ma chua co ket qua thi phai van la None"


def test_dong_cuoi_bi_cat_khong_lam_hong_ca_nhat_ky(tmp_path: Path) -> None:
    """Mất điện giữa lúc ghi: bỏ dòng hỏng, giữ mọi bằng chứng đã ghi trước đó."""
    path = tmp_path / "j.ndjson"
    journal = CommandJournal(path)
    journal.reserve("CMD-1")
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"command_id": "CMD-2", "reserv')

    again = CommandJournal(path)
    assert "CMD-1" in again
    assert "CMD-2" not in again


def test_giu_cho_hai_lan_cung_command_id_la_loi(tmp_path: Path) -> None:
    journal = CommandJournal(tmp_path / "j.ndjson")
    journal.reserve("CMD-1")
    with pytest.raises(ValueError):
        journal.reserve("CMD-1")


# -- hợp đồng payload -------------------------------------------------------------------------

def test_payload_co_magic_bi_tu_choi() -> None:
    """Nhận được `magic` nghĩa là đang cầm payload của đường EA — định tuyến đã sai."""
    with pytest.raises(ValueError, match="magic"):
        OpenRequest.from_payload({**PAYLOAD, "magic": 770001})


@pytest.mark.parametrize("thieu", ["symbol", "direction", "volume"])
def test_payload_thieu_truong_bat_buoc_bi_tu_choi(thieu: str) -> None:
    payload = {k: v for k, v in PAYLOAD.items() if k != thieu}
    with pytest.raises(ValueError, match=thieu):
        OpenRequest.from_payload(payload)


def test_payload_volume_am_bi_tu_choi() -> None:
    with pytest.raises(ValueError, match="duong"):
        OpenRequest.from_payload({**PAYLOAD, "volume": -0.1})


def test_trang_thai_ack_ngoai_hop_dong_bi_chan() -> None:
    with pytest.raises(ValueError):
        OpenOutcome("da_xong", "khong phai mot trong bon trang thai")


# -- xử lý command ---------------------------------------------------------------------------

async def test_dry_run_luon_tra_rejected(tmp_path: Path) -> None:
    """`rejected` chứ không phải `unknown`: ở chế độ chạy thử thì đúng là chưa bấm gì cả."""
    link = _link(tmp_path)
    ack = await link.handle_command(_command("CMD-1"))

    assert ack["status"] == "rejected"
    assert "DRY_RUN" in ack["retmsg"]
    assert link.journal.get("CMD-1").clicked is False


async def test_command_khong_phai_open_ui_bi_tu_choi_va_khong_vao_nhat_ky(
        tmp_path: Path) -> None:
    """Từ chối `OPEN` là lớp bảo vệ cuối chống việc lỡ đặt một lệnh `EXPERT`."""
    link = _link(tmp_path)
    ack = await link.handle_command(_command("CMD-1", command_type="OPEN"))

    assert ack["status"] == "rejected"
    assert "khong nhan command loai OPEN" in ack["retmsg"]
    assert "CMD-1" not in link.journal


async def test_command_qua_han_bi_tu_choi(tmp_path: Path) -> None:
    link = _link(tmp_path)
    ack = await link.handle_command(_command("CMD-1", deadline="2000-01-01T00:00:00.000Z"))

    assert ack["status"] == "rejected"
    assert "qua han" in ack["retmsg"]


async def test_nhan_lai_command_da_xong_thi_gui_lai_ack_cu(tmp_path: Path) -> None:
    driver = DryRunDriver()
    link = _link(tmp_path, driver)
    first = await link.handle_command(_command("CMD-1"))
    second = await link.handle_command(_command("CMD-1"))

    assert second["status"] == first["status"]
    assert second["retmsg"] == first["retmsg"]
    assert len(driver.seen) == 1, "Khong duoc goi driver lan hai"


async def test_khoi_dong_lai_sau_khi_giu_cho_thi_tra_unknown(tmp_path: Path) -> None:
    """Ca quan trọng nhất của cả file: chết giữa chừng, không ai được bấm lần hai."""
    path = tmp_path / "clicker_commands.ndjson"
    CommandJournal(path).reserve("CMD-1")     # tiến trình cũ chết ngay sau khi giữ chỗ

    driver = DryRunDriver()
    link = ClickerLink(
        config=LinkConfig(host="127.0.0.1", port=0, token=CLICKER_TOKEN,
                          account_login=CLICKER_LOGIN),
        journal=CommandJournal(path), driver=driver,
    )
    ack = await link.handle_command(_command("CMD-1"))

    assert ack["status"] == "unknown"
    assert driver.seen == [], "TUYET DOI khong duoc cham vao giao dien lan hai"


async def test_driver_nem_ngoai_le_thi_tra_unknown_khong_phai_rejected(
        tmp_path: Path) -> None:
    """Driver hỏng giữa chừng thì KHÔNG được kết luận là chưa bấm."""

    class DriverHong:
        def open(self, request: OpenRequest) -> OpenOutcome:
            raise RuntimeError("mat cua so giua chung")

        def dry_probe(self) -> OpenOutcome:  # pragma: no cover - khong dung o day
            raise NotImplementedError

    link = _link(tmp_path, DriverHong())
    ack = await link.handle_command(_command("CMD-1"))

    assert ack["status"] == "unknown"
    assert link.journal.get("CMD-1").ack["status"] == "unknown"


async def test_canary_bao_do_khi_chay_thu(tmp_path: Path) -> None:
    """Clicker không chạm vào giao diện thì không điều khiển được giao diện. Nói thật điều đó."""
    link = _link(tmp_path)
    assert not link.health()
    assert "DRY_RUN" in link.health().detail


# -- đầu-cuối với Bridge thật -----------------------------------------------------------------

@pytest.fixture
async def bridge(db: Database) -> AsyncIterator[tuple[BridgeServer, CommandDispatcher]]:
    db.upsert_agent(CLICKER_AGENT, role="CLICKER", token_hash=hash_token(CLICKER_TOKEN),
                    magic_number=0, account_login=CLICKER_LOGIN)
    server = BridgeServer(db, ServerConfig(host="127.0.0.1", port=0, hello_timeout_sec=1.0,
                                           monitor_interval_sec=0.05,
                                           heartbeat_timeout_ms=5000))
    dispatcher = CommandDispatcher(db, server)
    await server.start()
    try:
        yield server, dispatcher
    finally:
        await server.stop()


async def test_clicker_that_bat_tay_va_tra_ack_qua_socket(
        bridge, db: Database, tmp_path: Path) -> None:
    import asyncio

    server, dispatcher = bridge
    link = _link(tmp_path)
    link.config.host, link.config.port = "127.0.0.1", server.port
    # Nhịp đầu tiên gửi ngay khi nối, nên không cần chu kỳ ngắn để thấy canary đỏ.
    link.config.heartbeat_sec = 1.0

    task = asyncio.create_task(link.run())
    try:
        await _wait_until(lambda: db.get_agent(CLICKER_AGENT)["status"] == "ONLINE", timeout=3.0)

        command_id = await dispatcher.dispatch(
            CLICKER_AGENT, "OPEN_UI", payload=dict(PAYLOAD), deadline_ms=30000)
        await _wait_until(
            lambda: db.get_command(command_id)["status"] == "ACK_FAILED", timeout=3.0)

        command = db.get_command(command_id)
        assert "DRY_RUN" in command["retmsg"]

        # Canary đỏ phải kéo agent xuống DEGRADED, đúng cơ chế sẵn có của phase 3.
        await _wait_until(lambda: db.get_agent(CLICKER_AGENT)["status"] == "DEGRADED",
                          timeout=3.0)
    finally:
        link.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


# -- điểm khởi động ---------------------------------------------------------------------------

def test_khong_co_dry_run_thi_tu_choi_khoi_dong() -> None:
    """Driver chưa được đo thì không được phép chạy trên tài khoản thật."""
    code = main(["--token", CLICKER_TOKEN, "--account-login", str(CLICKER_LOGIN)])
    assert code == 2


def test_tham_so_bat_buoc() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--dry-run"])


def test_nhip_heartbeat_phai_nho_hon_han_cua_bridge() -> None:
    """F-03: gửi mỗi 5 giây với hạn 5 giây là biên bằng 0, và clicker OFFLINE = ngừng copy (D-25).

    EA gửi mỗi 1000 ms với cùng hạn 5000 ms — biên gấp 5. Clicker phải cùng mức, không được là
    ngoại lệ, vì nó là agent duy nhất mà trạng thái ONLINE quyết định có copy hay không.
    """
    # Doc thang tu schema chu khong chep tay: han doi thi test nay phai doi theo.
    import re

    from clicker.link import DEFAULT_HEARTBEAT_SEC

    schema = (Path(__file__).resolve().parents[1]
              / "bridge" / "db" / "schema.sql").read_text(encoding="utf-8")
    han_bridge_sec = int(
        re.search(r"'heartbeat_timeout_ms',\s*'(\d+)'", schema).group(1)) / 1000.0
    assert DEFAULT_HEARTBEAT_SEC * 3 <= han_bridge_sec, (
        f"Nhip {DEFAULT_HEARTBEAT_SEC}s so voi han {han_bridge_sec}s khong du bien"
    )
