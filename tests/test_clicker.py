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
from bridge.config import ConfigError
from bridge.db.repo import Database
from bridge.logging_setup import DEFAULT_LOG_FILENAME
from bridge.protocol.auth import hash_token
from bridge.protocol.dispatcher import CommandDispatcher
from bridge.protocol.server import BridgeServer, ServerConfig
from clicker.__main__ import (
    ENV_TOKEN,
    LOG_FILENAME,
    bo_sung_tham_so,
    build_parser,
    doc_muc_clicker,
    main,
    nhat_ky_theo_muc,
)
from clicker.journal import CommandJournal
from clicker.link import ClickerLink, LinkConfig, ThieuCauHinh
from clicker.ui import probe as ui_probe
from clicker.ui.driver import CloseRequest, DryRunDriver, OpenDriver, OpenOutcome, OpenRequest
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

async def test_che_do_that_ma_khong_ai_khai_tieu_de_thi_dung_han(tmp_path: Path) -> None:
    """Không ai khai tiêu đề cửa sổ — kể cả Bridge — thì clicker **thoát**, không chạy tiếp.

    Chạy tiếp ở trạng thái canary đỏ nghe có vẻ an toàn hơn, nhưng không: canary đỏ chỉ chặn
    đường MỞ, còn đường ĐÓNG rơi về `OrderSend` của EA theo `close_degraded_fallback = EA`, tức
    deal đóng mang `EXPERT` — đúng thứ đường đóng qua giao diện tồn tại để ngăn.
    """
    link = _link(tmp_path)
    link.dry_run = False
    link.config.terminal_title = ""

    async def _noi() -> None:
        return None

    async def _bat_tay() -> dict:
        return {"kind": "hello_ack", "agent_id": CLICKER_AGENT, "last_seq": 0, "config": {}}

    link.connect = _noi          # type: ignore[method-assign]
    link.handshake = _bat_tay    # type: ignore[method-assign]
    with pytest.raises(ThieuCauHinh):
        await link.run()


def test_tham_so_bat_buoc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Từ phase 11 argparse **không** còn là chỗ chặn: token có thể tới từ ba đường.

    Nhưng hợp đồng thì không đổi — thiếu token là dừng, không chạy tiếp và không rơi về
    `--dry-run`. Chỗ chặn chuyển vào `main()`, nên test đi theo.
    """
    parser = build_parser()
    parser.parse_args(["--dry-run"])          # khong con nem SystemExit

    monkeypatch.delenv(ENV_TOKEN, raising=False)
    monkeypatch.setattr("clicker.__main__.doc_muc_clicker", lambda *_a: {})
    assert main(["--dry-run"]) == 2


def test_clicker_khong_ghi_chung_file_log_voi_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Một file log, một tiến trình.

    Bridge và clicker cùng ghi `bridge.log` thì trên Windows lần xoay lúc nửa đêm hỏng và **cả
    hai ngừng ghi log vĩnh viễn** — đã xảy ra thật trên VPS, 63 giờ không một dòng log.
    """
    goi: list[dict[str, object]] = []
    monkeypatch.setattr("clicker.__main__.setup_logging", lambda **kw: goi.append(kw))
    monkeypatch.delenv(ENV_TOKEN, raising=False)
    monkeypatch.setattr("clicker.__main__.doc_muc_clicker", lambda *_a: {})

    assert main(["--dry-run"]) == 2
    assert len(goi) == 1
    assert goi[0].get("filename", DEFAULT_LOG_FILENAME) != DEFAULT_LOG_FILENAME


def test_hai_clicker_khong_ghi_chung_mot_file_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 12 co HAI clicker. Chung file log la lai dung cai bay da lam bridge.log im 63 gio."""
    goi: list[dict[str, object]] = []
    monkeypatch.setattr("clicker.__main__.setup_logging", lambda **kw: goi.append(kw))
    monkeypatch.delenv(ENV_TOKEN, raising=False)

    assert main(["--dry-run"]) == 2
    assert main(["--dry-run", "--muc", "clicker_master"]) == 2
    assert goi[0]["filename"] != goi[1]["filename"]
    assert goi[1]["filename"] == "clicker_master.log"


def test_clicker_thu_ba_co_log_va_nhat_ky_rieng(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mỗi Client đi đường giao diện có một clicker riêng, nên mục nào cũng phải chạy được.

    Dùng chung file log là bẫy đã làm `bridge.log` im 63 giờ; dùng chung nhật ký là **mất lệnh
    trong im lặng** — clicker này thấy `command_id` của clicker kia là "đã giữ chỗ nhưng chưa có
    ack".
    """
    goi: list[dict[str, object]] = []
    monkeypatch.setattr("clicker.__main__.setup_logging", lambda **kw: goi.append(kw))
    monkeypatch.delenv(ENV_TOKEN, raising=False)
    monkeypatch.setattr("clicker.__main__.doc_muc_clicker", lambda *_a: {})

    assert main(["--dry-run", "--muc", "clicker_cl02"]) == 2
    assert goi[0]["filename"] == "clicker_cl02.log"

    args = build_parser().parse_args(["--muc", "clicker_cl02"])
    assert nhat_ky_theo_muc(args) == "data/clicker_cl02_commands.ndjson"


def test_ten_muc_sai_thi_dung_ngay_va_khong_lay_no_lam_ten_file(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Tên mục sai thành tên file log và tên nhật ký, tức một nhật ký không ai đọc."""
    goi: list[dict[str, object]] = []
    monkeypatch.setattr("clicker.__main__.setup_logging", lambda **kw: goi.append(kw))

    assert main(["--dry-run", "--muc", "Clicker-Master"]) == 2
    # Vào log RIÊNG của clicker, không phải `bridge.log`: dừng vì tên sai không phải cái cớ để
    # ghi chung file log với Bridge.
    assert goi[0]["filename"] != DEFAULT_LOG_FILENAME
    assert goi[0]["filename"] == LOG_FILENAME


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


# --------------------------------------------------------------------------------------------
# Nguồn của token (phase 11): --token → biến môi trường → mục [clicker] trong config.toml.
#
# Lý do mục này tồn tại: dòng lệnh của một tiến trình là thứ mọi tài khoản trên cùng máy đọc
# được. Clicker chạy 24/7 dưới một Scheduled Task, nên `--token` ở đó là token phơi ra suốt ngày.
# --------------------------------------------------------------------------------------------

def _args(argv: list[str]) -> object:
    return build_parser().parse_args(argv)


def test_token_dong_lenh_thang_bien_moi_truong(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_TOKEN, "tu-moi-truong")
    monkeypatch.setattr("clicker.__main__.doc_muc_clicker", lambda *_a: {"token": "tu-config"})
    args = _args(["--token", "tu-dong-lenh", "--account-login", "1", "--terminal-title", "T"])
    bo_sung_tham_so(args)
    assert args.token == "tu-dong-lenh"


def test_token_lay_tu_bien_moi_truong_khi_thieu_dong_lenh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_TOKEN, "tu-moi-truong")
    monkeypatch.setattr("clicker.__main__.doc_muc_clicker", lambda *_a: {"token": "tu-config"})
    args = _args(["--account-login", "1", "--terminal-title", "T"])
    bo_sung_tham_so(args)
    assert args.token == "tu-moi-truong"


def test_lay_du_ba_gia_tri_tu_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_TOKEN, raising=False)
    monkeypatch.setattr("clicker.__main__.doc_muc_clicker",
                        lambda *_a: {"token": "tu-config", "account_login": 538217,
                                     "terminal_title": "MetaTrader 5 - 538217"})
    args = _args([])
    bo_sung_tham_so(args)
    assert (args.token, args.account_login, args.terminal_title) == (
        "tu-config", 538217, "MetaTrader 5 - 538217")


def test_thieu_token_o_ca_ba_duong_thi_thoat_khac_khong(monkeypatch: pytest.MonkeyPatch) -> None:
    """Không token thì **không** được chạy tiếp và cũng không được rơi về `--dry-run`."""
    monkeypatch.delenv(ENV_TOKEN, raising=False)
    monkeypatch.setattr("clicker.__main__.doc_muc_clicker", lambda *_a: {})
    assert main(["--account-login", "1", "--terminal-title", "T"]) == 2


def test_thieu_so_tai_khoan_thi_xin_tu_bridge_chu_khong_chan_khoi_dong(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Số tài khoản có thể khai trên dashboard, nên thiếu nó ở máy **không** còn là lỗi khởi động.

    Nó đi vào `hello` bằng 0, nghĩa là "chưa biết, xin Bridge giao".
    """
    monkeypatch.setattr("clicker.__main__.doc_muc_clicker", lambda *_a: {"token": "co-token"})
    args = build_parser().parse_args(["--terminal-title", "T"])
    bo_sung_tham_so(args)
    assert args.account_login == 0
    assert args.token == "co-token"


def test_config_thieu_thi_khong_nem(monkeypatch: pytest.MonkeyPatch) -> None:
    """`config.toml` vắng mặt là chuyện thường trên máy chỉ chạy clicker — không được ném."""
    def _nem(*_a: object, **_k: object) -> None:
        raise ConfigError("khong tim thay config.toml")

    monkeypatch.setattr("clicker.__main__.load_config", _nem)
    assert doc_muc_clicker() == {}


# -- lenh dong qua giao dien -------------------------------------------------------------------

CLOSE_PAYLOAD = {"position_id": 72205853}


async def test_nhan_close_ui_va_goi_dung_driver_close(tmp_path: Path) -> None:
    """Định tuyến trong `_execute`: `OPEN_UI` đi vào `open()`, lệnh đóng đi vào `close()`."""
    goi: list[str] = []

    class Ghi(DryRunDriver):
        def open(self, request):  # type: ignore[no-untyped-def]
            goi.append("open")
            return super().open(request)

        def close(self, request):  # type: ignore[no-untyped-def]
            goi.append("close")
            return super().close(request)

    link = _link(tmp_path, Ghi())
    await link.handle_command(_command("CMD-1", command_type="CLOSE_UI",
                                       payload=dict(CLOSE_PAYLOAD)))
    await link.handle_command(_command("CMD-2", command_type="CLOSE_UI_PARTIAL",
                                       payload={**CLOSE_PAYLOAD, "volume": 0.02}))
    await link.handle_command(_command("CMD-3"))

    assert goi == ["close", "close", "open"]


@pytest.mark.parametrize("loai", ["OPEN", "CLOSE", "CLOSE_PARTIAL", "REQUEST_SNAPSHOT"])
async def test_van_tu_choi_moi_loai_command_cua_duong_EA(tmp_path: Path, loai: str) -> None:
    """Hàng rào chống định tuyến sai: nhận nhầm `CLOSE` trần nghĩa là đóng bằng `OrderSend`."""
    link = _link(tmp_path)
    ack = await link.handle_command(_command("CMD-1", command_type=loai,
                                             payload=dict(CLOSE_PAYLOAD)))

    assert ack["status"] == "rejected"
    assert f"khong nhan command loai {loai}" in ack["retmsg"]
    assert "CMD-1" not in link.journal


async def test_close_ui_partial_thieu_volume_bi_tu_choi(tmp_path: Path) -> None:
    """Nếu lọt, nó thành **đóng hẳn** trong im lặng — đóng nhiều hơn phần đáng lẽ phải đóng."""
    link = _link(tmp_path)
    ack = await link.handle_command(_command("CMD-1", command_type="CLOSE_UI_PARTIAL",
                                             payload=dict(CLOSE_PAYLOAD)))

    assert ack["status"] == "rejected"
    assert "thieu volume" in ack["retmsg"]


async def test_payload_dong_mang_magic_bi_tu_choi(tmp_path: Path) -> None:
    """Có `magic` nghĩa là đang cầm payload của đường EA — định tuyến đã sai từ Bridge."""
    link = _link(tmp_path)
    ack = await link.handle_command(_command("CMD-1", command_type="CLOSE_UI",
                                             payload={**CLOSE_PAYLOAD, "magic": 770001}))

    assert ack["status"] == "rejected"
    assert "magic" in ack["retmsg"]


# -- cấu hình đến từ Bridge --------------------------------------------------------------------

def test_nhan_so_tai_khoan_va_tieu_de_tu_bridge_va_tro_lai_driver(tmp_path: Path) -> None:
    link = _link(tmp_path)
    link.config.account_login = 0
    link.config.terminal_title = ""
    link.ap_dung_cau_hinh({"account_login": 538217, "terminal_title": "538217 - Connext"})
    assert link.config.account_login == 538217
    assert link.config.terminal_title == "538217 - Connext"
    assert link.driver.terminal_title == "538217 - Connext"


def test_gia_tri_cuc_bo_thang_gia_tri_bridge_giao(tmp_path: Path) -> None:
    """Thứ tự ưu tiên: dòng lệnh > config.toml > Bridge.

    Nhờ vậy một bản cài cũ đang khai `[clicker]` trong `config.toml` nâng cấp lên không đổi hành
    vi — nó vẫn lái đúng cái terminal nó đang lái.
    """
    link = _link(tmp_path)
    link.config.cuc_bo = True          # đúng thứ `build_link` đặt khi máy có sẵn giá trị
    link.config.account_login = 111
    link.config.terminal_title = "cuc-bo"
    link.ap_dung_cau_hinh({"account_login": 222, "terminal_title": "tu-bridge"})
    assert (link.config.account_login, link.config.terminal_title) == (111, "cuc-bo")


def test_doi_terminal_tren_dashboard_thi_lan_bat_tay_sau_PHAI_de_gia_tri_cu(
        tmp_path: Path) -> None:
    """Bản đầu chỉ điền vào chỗ trống, nên sửa trên dashboard không bao giờ tới clicker đang chạy.

    Tệ hơn cả việc "không có tác dụng": clicker giữ cả số tài khoản CŨ lẫn tiêu đề CŨ, nên phép
    đối chiếu hai giá trị đó vẫn khớp và canary vẫn xanh — trong lúc Bridge đã định tuyến lệnh
    của nó sang một tài khoản khác.
    """
    link = _link(tmp_path)
    link.ap_dung_cau_hinh({"account_login": 111, "terminal_title": "111"})
    assert (link.config.account_login, link.config.terminal_title) == (111, "111")

    link.ap_dung_cau_hinh({"account_login": 222, "terminal_title": "222"})
    assert (link.config.account_login, link.config.terminal_title) == (222, "222")
    assert link.driver.terminal_title == "222"


def _gia_lap_cua_so(monkeypatch: pytest.MonkeyPatch, tieu_de: str) -> None:
    """Giả lập một cửa sổ terminal có tiêu đề cho trước, không cần Win32 thật."""
    monkeypatch.setattr(
        "clicker.ui.probe.find_terminal",
        lambda _t: ui_probe.ProbeResult(True, "thay", hwnd=1, title=tieu_de))
    monkeypatch.setattr("clicker.ui.win32.is_window", lambda _h: True)


def test_cua_so_cua_tai_khoan_khac_thi_canary_do(tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """Hàng rào thay cho `ACCOUNT_MISMATCH`: đối chiếu với **cửa sổ thật**, mỗi nhịp heartbeat."""
    link = _link(tmp_path)
    link.dry_run = False
    link.config.account_login = 538217
    link.config.terminal_title = "5382"
    _gia_lap_cua_so(monkeypatch, "538216 - Connext-Demo")
    kq = link.health()
    assert not kq.healthy
    assert "538216" in kq.detail


def test_cua_so_dung_tai_khoan_thi_canary_xanh(tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    link = _link(tmp_path)
    link.dry_run = False
    link.config.account_login = 538217
    link.config.terminal_title = "5382"
    _gia_lap_cua_so(monkeypatch, "538217 - Connext-Demo")
    assert link.health().healthy


def test_driver_cung_kiem_so_tai_khoan_chu_khong_chi_canary(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Canary chặn việc Bridge GỬI lệnh; phép kiểm trong driver chặn đúng cú BẤM.

    Cần cả hai: giữa hai nhịp heartbeat vẫn đủ chỗ cho một terminal đăng nhập sang tài khoản
    khác, và cú bấm thì không lấy lại được.
    """
    from clicker.ui.driver import Mt5UiDriver

    driver = Mt5UiDriver(terminal_title="5382", account_login=538217)
    _gia_lap_cua_so(monkeypatch, "538216 - Connext-Demo")
    kq = driver.close(CloseRequest(position_id=1))
    assert kq.status == "rejected"
    assert not kq.clicked
    assert "538216" in kq.reason


async def test_bat_tay_that_nhan_duoc_cau_hinh_tu_bridge(bridge, db: Database,
                                                         tmp_path: Path) -> None:
    """Đầu-cuối qua socket: khai trên DB (thứ dashboard ghi) → clicker nhận lúc bắt tay."""
    import asyncio

    server, _ = bridge
    db.upsert_agent(CLICKER_AGENT, role="CLICKER", token_hash=hash_token(CLICKER_TOKEN),
                    magic_number=770001, account_login=CLICKER_LOGIN,
                    terminal_title="538217 - Connext")
    link = _link(tmp_path)
    link.config.host, link.config.port = "127.0.0.1", server.port
    link.config.account_login = 0
    link.config.terminal_title = ""

    task = asyncio.create_task(link.run())
    try:
        await _wait_until(lambda: link.config.terminal_title == "538217 - Connext", timeout=3.0)
        assert link.config.account_login == CLICKER_LOGIN
        # Số 0 trong `hello` không được ghi đè số tài khoản đã khai trên dashboard.
        assert db.get_agent(CLICKER_AGENT)["account_login"] == CLICKER_LOGIN
    finally:
        link.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
