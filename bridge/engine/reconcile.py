"""Đối chiếu ba nguồn và ghi sai lệch (plan mục 8.4–8.7).

So **ba nguồn**, không phải hai: bảng `pair` trong DB, vị thế thật trên Master, vị thế thật trên
Client. Hai nguồn chỉ cho biết "có lệch", ba nguồn mới cho biết **lệch ở đâu**.

Ba luật chi phối toàn bộ file:

* **Được tự động ĐÓNG, không được tự động MỞ** (D-13). Đóng làm giảm phơi nhiễm, mở làm tăng.
  Khi không chắc chuyện gì đã xảy ra, hành động an toàn luôn là đóng hoặc dừng lại chờ người.
* **Đối chiếu chỉ ghi nhận, không tự hành động.** Nó sinh `reconcile_finding`; việc áp dụng nằm
  ở `accept_finding()` và người vận hành bấm nút. Một vòng quét định kỳ mà tự đóng lệnh là thứ
  không ai dám bật.
* **Nhận dạng phía Client không dùng magic** (D-07b). Vị thế mở qua giao diện có `magic = 0`,
  giống hệt lệnh người dùng mở tay. Thứ tự: (1) có mặt trong `pair`; (2) thẻ tương quan trong
  comment, dùng một lần; (3) suy đoán — chỉ khi có **đúng một** ứng viên.

`evidence_json` của mỗi finding chứa cả ba nguồn chứ không chỉ kết luận. Người vận hành phải
thấy được bằng chứng để tự phán đoán.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from decimal import Decimal
from typing import Any

from bridge.clock import parse_iso, utc_now, utc_now_iso
from bridge.db.repo import Database
from bridge.engine.sizing import to_decimal
from bridge.logging_setup import get_logger
from bridge.protocol.dispatcher import CommandDispatcher

log = get_logger(__name__)

#: Trạng thái pair đã kết thúc — không tham gia đối chiếu.
DONE_STATUSES = frozenset({"CLOSED", "OPEN_FAILED"})

#: Trạng thái coi là "sổ sách nói đang mở".
#:
#: `ORPHANED` **cố ý không có ở đây**: nó nghĩa là sai lệch đã được phát hiện, đã có alert, và
#: đang chờ người xử lý. Đưa nó vào đây thì mỗi vòng đối chiếu lại đẻ thêm một finding cho cùng
#: một chuyện người ta đã biết — đúng loại rác làm người vận hành ngừng đọc danh sách.
LIVE_STATUSES = frozenset({"OPEN", "PARTIALLY_CLOSED", "CLOSING"})

SNAPSHOT_TIMEOUT_SEC = 6.0

#: Dung sai khi so volume hai bên. Nhỏ hơn một phần trăm của bước volume nhỏ nhất.
VOLUME_EPS = 1e-6


def new_run_id() -> str:
    return "REC-" + utc_now().strftime("%Y%m%d-%H%M%S-%f")[:-3]


class Reconciler:
    """Đối chiếu sổ sách với thực tế trên hai terminal."""

    def __init__(self, db: Database, server: Any, dispatcher: CommandDispatcher,
                 closing: Any, alert: Any) -> None:
        self.db = db
        self.server = server
        self.dispatcher = dispatcher
        #: `CloseFlow` — dùng lại đường đóng thay vì tự tạo command, để mọi cổng an toàn của
        #: phase 7 (một lệnh mỗi cặp, cảnh báo cặp ghép suy đoán) vẫn có hiệu lực.
        self.closing = closing
        self._alert = alert

    # -- chạy một vòng đối chiếu ---------------------------------------------------------------

    async def run(self, trigger: str = "MANUAL") -> str:
        """Chạy một vòng đối chiếu. Trả về `run_id`.

        Chỉ **ghi nhận**. Không đóng lệnh, không mở lệnh, không sửa `pair` — trừ những sai lệch
        thuần sổ sách mà bằng chứng là tuyệt đối (cả hai bên đều đã đóng thật).
        """
        run_id = new_run_id()
        master_agent = self._master_agent()
        if master_agent is None:
            log.warning("Doi chieu %s: khong co agent MASTER, bo qua", run_id)
            return run_id

        vi_the_master = await self._snapshot(master_agent["agent_id"])
        if vi_the_master is None:
            self._alert("WARNING", "RECONCILE_NO_SNAPSHOT",
                        f"Doi chieu {run_id}: khong lay duoc snapshot cua Master "
                        f"{master_agent['agent_id']}, bo qua vong nay.",
                        agent_id=master_agent["agent_id"])
            return run_id

        clients = self.db.query_all("SELECT * FROM client_account WHERE enabled = 1")
        vi_the_client: dict[str, dict[int, Any]] = {}
        for client in clients:
            snap = await self._snapshot(client["agent_id"])
            if snap is None:
                self._alert("WARNING", "RECONCILE_NO_SNAPSHOT",
                            f"Doi chieu {run_id}: khong lay duoc snapshot cua Client "
                            f"{client['client_id']}, bo qua Client nay.",
                            agent_id=client["agent_id"])
                continue
            vi_the_client[client["client_id"]] = snap

        self._soi_tung_cap(run_id, vi_the_master, vi_the_client)
        self._soi_vi_the_master_thua(run_id, vi_the_master, master_agent)
        self._soi_vi_the_client_thua(run_id, vi_the_client)
        # Đếm từ DB chứ không cộng tay: cổng lọc trùng ở `_create_finding` có thể đã bỏ bớt,
        # và con số báo ra phải là số dòng THẬT sự được ghi trong vòng này.
        so = self.db.query_one(
            "SELECT COUNT(*) n FROM reconcile_finding WHERE run_id = ?", (run_id,))["n"]
        # `so` la so dong GHI DUOC trong vong nay — cong loc trung o `_create_finding` da bo bot.
        # Bao mot minh con so do ra ngoai la noi doi: hom kiem toan 2026-09-06 log ghi "0 sai
        # lech" trong khi 2/2 cap deu sai va mot finding dang nam cho (F-06). Nen luon kem ca
        # TONG SO DANG CHO XU LY.
        dang_cho = self.db.query_one(
            "SELECT COUNT(*) n FROM reconcile_finding WHERE resolution = 'PENDING'")["n"]

        log.info("Doi chieu %s (%s): %d sai lech moi, %d dang cho xu ly",
                 run_id, trigger, so, dang_cho)
        if so:
            # Muc canh bao theo muc NGHIEM TRONG that cua finding, khong phai mot muc co dinh
            # (B-08). `DECISION` nghia la co thu can nguoi quyet dinh — thu do phai ra duoc kenh
            # ngoai; toan `SAFE` thi de trong dashboard la du.
            co_quyet_dinh = self.db.query_one(
                "SELECT 1 FROM reconcile_finding WHERE run_id = ? AND severity = 'DECISION' "
                "LIMIT 1", (run_id,)) is not None
            self._alert("ERROR" if co_quyet_dinh else "WARNING", "RECONCILE_FINDINGS",
                        f"Doi chieu {run_id} ({trigger}) phat hien {so} sai lech moi giua so "
                        f"sach va thuc te; tong cong {dang_cho} dang cho xu ly. Can nguoi xem "
                        "tung dong.")
        self._nhac_finding_bo_quen()
        return run_id

    def _nhac_finding_bo_quen(self) -> None:
        """Nhắc lại khi có sai lệch nằm chờ quá lâu (B-09).

        Cổng chống trùng ở `_create_finding` khiến một sai lệch chỉ được báo **một lần**, và cổng
        đó đúng — nhưng hệ quả là sau tin báo đầu tiên thì không còn gì nhắc nữa. Kiểm toán
        2026-09-06 tìm thấy một finding nằm `PENDING` suốt cả ngày, đi qua trọn một phiên làm
        việc mà không ai để ý.

        Mốc nhắc lần cuối ghi vào `system_config` chứ không giữ trong bộ nhớ: khởi động lại
        không được biến thành một cách vô tình để im lặng mãi.
        """
        han_phut = self.db.get_config_int("finding_nhac_sau_phut", 60)
        if han_phut <= 0:
            return
        bay_gio = utc_now()
        # MIN() chu khong phai mot cot tran canh COUNT(*): khong co MIN thi SQLite tra ve
        # created_at cua mot dong bat ky, va "cai cu nhat" se sai.
        cu_nhat = self.db.query_one(
            "SELECT MIN(created_at) AS created_at, COUNT(*) n FROM reconcile_finding "
            "WHERE resolution = 'PENDING'")
        if cu_nhat is None or not cu_nhat["n"] or cu_nhat["created_at"] is None:
            return
        tuoi_phut = (bay_gio - parse_iso(cu_nhat["created_at"])).total_seconds() / 60.0
        if tuoi_phut < han_phut:
            return

        lan_cuoi = self.db.get_config("finding_nhac_lan_cuoi")
        if lan_cuoi is not None:
            if (bay_gio - parse_iso(lan_cuoi)).total_seconds() / 60.0 < han_phut:
                return
        self.db.set_config("finding_nhac_lan_cuoi", utc_now_iso())
        self._alert("ERROR", "FINDING_BO_QUEN",
                    f"Co {cu_nhat['n']} sai lech dang cho xu ly, cai cu nhat da {tuoi_phut:.0f} "
                    f"phut. So sach va thuc te dang lech ma chua ai xu ly.")

    async def _snapshot(self, agent_id: str) -> dict[int, Any] | None:
        """Hỏi agent hiện đang có những vị thế nào. Trả về `{position_id: vị thế}`."""
        truoc = self.server.latest_snapshots.get(agent_id)
        het = asyncio.get_running_loop().time() + SNAPSHOT_TIMEOUT_SEC
        da_hoi = False
        while asyncio.get_running_loop().time() < het:
            agent = self.db.get_agent(agent_id)
            # Agent chưa ONLINE thì **chờ trong hạn** chứ không bỏ cuộc ngay: lúc khởi động,
            # agent có thể đang bắt tay dở. Bỏ cuộc ngay sẽ đẻ ra một alert báo giả, và alert
            # báo giả làm người vận hành quen với việc bỏ qua alert.
            if agent is not None and agent["status"] == "ONLINE":
                if not da_hoi:
                    await self.dispatcher.request_snapshot(agent_id)
                    da_hoi = True
                snap = self.server.latest_snapshots.get(agent_id)
                if snap is not None and snap is not truoc:
                    return {p.position_id: p for p in snap.positions}
            await asyncio.sleep(0.1)
        return None

    def _master_agent(self) -> sqlite3.Row | None:
        return self.db.query_one("SELECT * FROM agent WHERE role = 'MASTER' LIMIT 1")

    def _create_finding(self, run_id: str, severity: str, kind: str,
                        suggested_action: str | None = None, **fields: Any) -> int:
        """Ghi một finding, **trừ khi** đã có một cái y hệt đang chờ xử lý.

        Đối chiếu chạy mỗi `reconcile_interval_sec`. Không có cổng này thì một sai lệch người ta
        chưa kịp xử lý sẽ sinh thêm một dòng mỗi phút, và danh sách finding trở thành thứ không
        ai đọc nữa — mất luôn tác dụng của chính nó.
        """
        dieu_kien = ["kind = ?", "resolution = 'PENDING'"]
        tham_so: list[Any] = [kind]
        for cot in ("pair_id", "master_position_id", "client_id"):
            gia_tri = fields.get(cot)
            if gia_tri is None:
                dieu_kien.append(f"{cot} IS NULL")
            else:
                dieu_kien.append(f"{cot} = ?")
                tham_so.append(gia_tri)
        da_co = self.db.query_one(
            "SELECT id FROM reconcile_finding WHERE " + " AND ".join(dieu_kien) + " LIMIT 1",
            tuple(tham_so))
        if da_co is not None:
            log.debug("Bo qua finding %s trung voi #%s dang cho xu ly", kind, da_co["id"])
            return 0
        return self.db.create_finding(run_id, severity, kind,
                                      suggested_action=suggested_action, **fields)

    # -- ma trận sai lệch ----------------------------------------------------------------------

    def _soi_tung_cap(self, run_id: str, master: dict[int, Any],
                      clients: dict[str, dict[int, Any]]) -> int:
        so = 0
        pairs = self.db.query_all(
            "SELECT * FROM pair WHERE status NOT IN ('CLOSED','OPEN_FAILED') ORDER BY pair_id")
        for pair in pairs:
            if pair["client_id"] not in clients:
                continue  # Client không lấy được snapshot; đã cảnh báo ở trên.
            snap_client = clients[pair["client_id"]]
            co_master = pair["master_position_id"] in master
            vi_the_client = (snap_client.get(pair["client_position_id"])
                             if pair["client_position_id"] else None)
            co_client = vi_the_client is not None
            bang_chung = self._bang_chung(pair, master.get(pair["master_position_id"]),
                                          vi_the_client)

            if pair["status"] in LIVE_STATUSES:
                so += self._soi_cap_dang_mo(run_id, pair, co_master, co_client, bang_chung)
            elif pair["status"] == "PENDING_OPEN":
                so += self._soi_cap_dang_cho(run_id, pair, co_master, snap_client, bang_chung)
            elif pair["status"] == "ORPHANED":
                so += self._soi_cap_mo_coi(run_id, pair, co_master, co_client, bang_chung)

            if co_client and vi_the_client is not None:
                so += self._soi_lech_volume(run_id, pair, vi_the_client, bang_chung)
                so += self._soi_reason(run_id, pair, bang_chung)
        return so

    def _soi_cap_mo_coi(self, run_id: str, pair: sqlite3.Row, co_master: bool,
                        co_client: bool, bang_chung: dict) -> int:
        """Cặp `ORPHANED` mà **cả hai chân đều đã biến mất** thì người ta đã xử lý xong ngoài đời.

        `ORPHANED` cố ý nằm ngoài `LIVE_STATUSES` để không đẻ finding trùng cho việc đã biết. Hệ
        quả không lường: cặp đó **không bao giờ được xem lại nữa**, nên khi người vận hành đóng
        nốt chân còn lại trên terminal thì sổ sách nằm nguyên như cũ mãi mãi. Kiểm toán
        2026-09-06 tìm thấy `PAIR-20260905-000025` ở đúng tình trạng đó (F-05), trong khi một
        cặp khác **cùng hoàn cảnh ngoài đời** nhưng ở trạng thái `PARTIALLY_CLOSED` thì được phát
        hiện ngay.

        Chỉ soi đúng trường hợp này — hai chân đều sạch — nên không quay lại kiểu rác cũ; cổng
        chống trùng ở `_create_finding` lo phần lặp.
        """
        if co_master or co_client:
            return 0
        self._create_finding(
            run_id, "SAFE", "ORPHAN_RESOLVED", suggested_action="MARK_CLOSED",
            pair_id=pair["pair_id"], master_position_id=pair["master_position_id"],
            client_id=pair["client_id"],
            evidence_json=json.dumps(bang_chung, ensure_ascii=False))
        return 1

    def _soi_cap_dang_mo(self, run_id: str, pair: sqlite3.Row, co_master: bool,
                         co_client: bool, bang_chung: dict) -> int:
        pair_id = pair["pair_id"]
        if co_master and co_client:
            return 0  # Khớp.

        if not co_master and co_client:
            self._create_finding(
                run_id, "SAFE", "MASTER_CLOSED_OFFLINE",
                suggested_action="CLOSE_CLIENT", pair_id=pair_id,
                master_position_id=pair["master_position_id"], client_id=pair["client_id"],
                evidence_json=json.dumps(bang_chung, ensure_ascii=False))
            return 1

        if co_master and not co_client:
            # DECISION chứ không SAFE: đóng Master lúc này là một **quyết định giao dịch mới**,
            # không phải đồng bộ. Sau vài phút offline giá đã trôi và bối cảnh đã khác.
            self._create_finding(
                run_id, "DECISION", "CLIENT_CLOSED_OFFLINE",
                suggested_action="MARK_ORPHANED", pair_id=pair_id,
                master_position_id=pair["master_position_id"], client_id=pair["client_id"],
                evidence_json=json.dumps(bang_chung, ensure_ascii=False))
            return 1

        self._create_finding(
            run_id, "SAFE", "BOTH_CLOSED", suggested_action="MARK_CLOSED", pair_id=pair_id,
            master_position_id=pair["master_position_id"], client_id=pair["client_id"],
            evidence_json=json.dumps(bang_chung, ensure_ascii=False))
        return 1

    def _soi_cap_dang_cho(self, run_id: str, pair: sqlite3.Row, co_master: bool,
                          snap_client: dict[int, Any], bang_chung: dict) -> int:
        """Cặp `PENDING_OPEN`: ack có thể đã mất giữa đường."""
        pair_id = pair["pair_id"]
        if not co_master:
            self._create_finding(
                run_id, "SAFE", "BOTH_CLOSED", suggested_action="MARK_CLOSED", pair_id=pair_id,
                master_position_id=pair["master_position_id"], client_id=pair["client_id"],
                evidence_json=json.dumps(bang_chung, ensure_ascii=False))
            return 1

        ung_vien = self._ung_vien_khong_chu(snap_client, pair['client_id'])
        the = pair["open_tag"]
        khop_the = [v for v in ung_vien if the and the in (v.comment or "")]

        if len(khop_the) == 1:
            bang_chung["client_ung_vien"] = _mo_ta(khop_the[0])
            self._create_finding(
                run_id, "SAFE", "ACK_LOST", suggested_action="REBIND_BY_TAG", pair_id=pair_id,
                master_position_id=pair["master_position_id"], client_id=pair["client_id"],
                evidence_json=json.dumps(bang_chung, ensure_ascii=False))
            return 1

        # Không có thẻ: chỉ ghép được bằng suy đoán. **DECISION, không phải SAFE** — ghép sai ở
        # đây nghĩa là gắn vị thế của người dùng vào một cặp, rồi phase 7 sẽ đóng nó.
        doan = [v for v in ung_vien
                if v.symbol == pair["client_symbol"]
                and v.direction == pair["client_direction"]]
        if doan:
            bang_chung["client_ung_vien"] = [_mo_ta(v) for v in doan]
            self._create_finding(
                run_id, "DECISION", "ACK_LOST", suggested_action="REBIND_BY_GUESS",
                pair_id=pair_id, master_position_id=pair["master_position_id"],
                client_id=pair["client_id"],
                evidence_json=json.dumps(bang_chung, ensure_ascii=False))
            return 1

        self._create_finding(
            run_id, "DECISION", "CLIENT_NOT_OPENED",
            suggested_action=f"APPLY_POLICY:{self.db.get_config('offline_reopen_policy', 'NONE')}",
            pair_id=pair_id, master_position_id=pair["master_position_id"],
            client_id=pair["client_id"],
            evidence_json=json.dumps(bang_chung, ensure_ascii=False))
        return 1

    def _ung_vien_khong_chu(self, snap: dict[int, Any], client_id: str) -> list[Any]:
        """Vị thế Client chưa thuộc cặp nào — tập ứng viên hợp lệ để ghép lại."""
        return [v for pid, v in snap.items()
                if self.db.find_pair_by_client_position(client_id, pid) is None]

    def _ghep_lai(self, f: sqlite3.Row, pair: sqlite3.Row) -> None:
        """Ghép lại cặp `PENDING_OPEN` với vị thế Client đã tìm ra bằng thẻ.

        Chỉ chạy cho `REBIND_BY_TAG`. Bản suy đoán (`REBIND_BY_GUESS`) cố ý **không** tự động
        được: nó là `DECISION`, và người vận hành phải gọi `manual_action()` sau khi tự nhìn.
        """
        bang_chung = json.loads(f["evidence_json"] or "{}")
        ung_vien = bang_chung.get("client_ung_vien")
        if not isinstance(ung_vien, dict):
            log.warning("Finding %s khong co ung vien don nhat de ghep lai", f["id"])
            return
        self.db.mark_pair_open(
            pair["pair_id"], client_position_id=ung_vien["position_id"],
            client_ticket=ung_vien["position_id"], client_volume=ung_vien["volume"],
            open_time_client=utc_now_iso())
        log.info("Ghep lai cap %s voi vi the %s theo the tuong quan",
                 pair["pair_id"], ung_vien["position_id"], extra={"pair_id": pair["pair_id"]})

    def _soi_vi_the_master_thua(self, run_id: str, master: dict[int, Any],
                                master_agent: sqlite3.Row) -> int:
        """Vị thế Master không thuộc cặp nào. **Không copy** — có thể là lệnh người dùng."""
        so = 0
        for position_id, vi_the in master.items():
            co = self.db.query_one(
                "SELECT 1 FROM pair WHERE master_position_id = ? "
                "AND status NOT IN ('CLOSED','OPEN_FAILED') LIMIT 1", (position_id,))
            if co is not None:
                continue
            self._create_finding(
                run_id, "DECISION", "UNPAIRED_MASTER", suggested_action="ALERT_ONLY",
                master_position_id=position_id,
                evidence_json=json.dumps(
                    {"db": None, "master": _mo_ta(vi_the), "client": None},
                    ensure_ascii=False))
            so += 1
        del master_agent
        return so

    def _soi_vi_the_client_thua(self, run_id: str,
                                clients: dict[str, dict[int, Any]]) -> int:
        """Vị thế Client không thuộc cặp nào.

        **Còn thẻ** của một `OPEN_UI` đã biết → `UNPAIRED_CLIENT`, cần người xem.
        **Không thẻ** → lệnh người dùng mở tay, bỏ qua hoàn toàn (FR-12). Đây là chỗ dễ sai
        nhất: nhận dạng bằng magic sẽ coi mọi vị thế là của bot, vì lệnh mở qua giao diện cũng
        có `magic = 0` (D-07b).
        """
        so = 0
        for client_id, snap in clients.items():
            for position_id, vi_the in snap.items():
                if self.db.find_pair_by_client_position(client_id, position_id) is not None:
                    continue
                the = self._the_da_biet(vi_the.comment or "")
                if the is None:
                    continue  # Lệnh mở tay. Không phải việc của bot.
                self._create_finding(
                    run_id, "DECISION", "UNPAIRED_CLIENT", suggested_action="ALERT_ONLY",
                    client_id=client_id,
                    evidence_json=json.dumps(
                        {"db": None, "master": None, "client": _mo_ta(vi_the),
                         "the_khop_command": the}, ensure_ascii=False))
                so += 1
        return so

    def _the_da_biet(self, comment: str) -> str | None:
        """Comment có mang thẻ của một `OPEN_UI` mà Bridge từng phát ra không."""
        if not comment:
            return None
        row = self.db.query_one(
            "SELECT open_tag FROM pair WHERE open_tag IS NOT NULL "
            "AND instr(?, open_tag) > 0 LIMIT 1", (comment,))
        return row["open_tag"] if row is not None else None

    def _soi_lech_volume(self, run_id: str, pair: sqlite3.Row, vi_the: Any,
                         bang_chung: dict) -> int:
        mong_doi = to_decimal(pair["master_current_volume"] or 0) * to_decimal(
            pair["effective_multiplier"] or 1)
        that = to_decimal(vi_the.volume)
        # Dung sai theo `volume_step`, khong phai epsilon (D-19 ban phase 11): dong mot phan
        # **luon** lam tron xuong, nen mot cap khoe manh van lech tren duoi mot buoc volume.
        # Truoc phase 11 cho nay dung EPS = 1e-6 roi bu lai bang cach TAT han voi moi cap khong
        # phai OPEN — tuc bo do lech bi tat dung tren nhom cap duy nhat co the lech (F-04/F-05).
        buoc = self._buoc_volume(pair)
        if abs(float(that - mong_doi)) <= float(buoc) + VOLUME_EPS:
            return 0
        if pair["status"] not in LIVE_STATUSES:
            return 0
        chi_tiet = dict(bang_chung)
        chi_tiet["volume_mong_doi"] = float(mong_doi)
        chi_tiet["volume_thuc_te"] = float(that)
        self._create_finding(
            run_id, "DECISION", "VOLUME_MISMATCH", suggested_action="ALERT_ONLY",
            pair_id=pair["pair_id"], master_position_id=pair["master_position_id"],
            client_id=pair["client_id"],
            evidence_json=json.dumps(chi_tiet, ensure_ascii=False))
        return 1

    def _buoc_volume(self, pair: sqlite3.Row) -> Decimal:
        """`volume_step` của symbol Client, hoặc 0 nếu chưa có spec (khi đó siết về đúng epsilon)."""
        client = self.db.get_client_account(pair["client_id"])
        if client is None:
            return Decimal(0)
        spec = self.db.get_symbol_spec(client["agent_id"], pair["client_symbol"])
        return to_decimal(spec["volume_step"]) if spec is not None else Decimal(0)

    def _soi_reason(self, run_id: str, pair: sqlite3.Row, bang_chung: dict) -> int:
        """Mục tiêu của cả phase 6b, kiểm lại ở đây thay vì tin."""
        client = self.db.get_client_account(pair["client_id"])
        if client is None or client["open_route"] != "UI":
            return 0
        reason = pair["client_open_reason"]
        if reason is None or int(reason) == 0:
            return 0
        self._create_finding(
            run_id, "DECISION", "UI_REASON_MISMATCH", suggested_action="ALERT_ONLY",
            pair_id=pair["pair_id"], master_position_id=pair["master_position_id"],
            client_id=pair["client_id"],
            evidence_json=json.dumps({**bang_chung, "client_open_reason": reason},
                                     ensure_ascii=False))
        return 1

    @staticmethod
    def _bang_chung(pair: sqlite3.Row, vt_master: Any, vt_client: Any) -> dict[str, Any]:
        return {
            "db": {"pair_id": pair["pair_id"], "status": pair["status"],
                   "master_position_id": pair["master_position_id"],
                   "client_position_id": pair["client_position_id"],
                   "master_current_volume": pair["master_current_volume"],
                   "client_current_volume": pair["client_current_volume"],
                   "open_tag": pair["open_tag"]},
            "master": _mo_ta(vt_master),
            "client": _mo_ta(vt_client),
        }

    # -- API xử lý finding (plan 8.7) ----------------------------------------------------------

    async def accept_finding(self, finding_id: int) -> bool:
        """Thực hiện hành động đề xuất của một finding."""
        f = self.db.get_finding(finding_id)
        if f is None or f["resolution"] != "PENDING":
            return False
        hanh_dong = (f["suggested_action"] or "").split(":")[0]
        pair = self.db.get_pair(f["pair_id"]) if f["pair_id"] else None

        if hanh_dong == "CLOSE_CLIENT" and pair is not None:
            await self.closing.close_pair_now(pair, "BOT")
        elif hanh_dong == "MARK_CLOSED" and pair is not None:
            # `master_da_dong=True`: finding nay chi sinh ra khi snapshot cho thay vi the
            # Master da bien mat khoi terminal — tuc co bang chung, khong phai suy dien.
            self.db.mark_pair_closed(pair["pair_id"], close_source="BROKER",
                                     close_time_client=utc_now_iso(), master_da_dong=True)
        elif hanh_dong == "MARK_ORPHANED" and pair is not None:
            self.db.update_pair(pair["pair_id"], status="ORPHANED", orphan_side="MASTER",
                                close_source="CLIENT")
        elif hanh_dong == "REBIND_BY_TAG" and pair is not None:
            self._ghep_lai(f, pair)
        elif hanh_dong == "APPLY_POLICY":
            await self._ap_chinh_sach_mo_bu(f, pair)
        elif hanh_dong == "ALERT_ONLY":
            pass
        else:
            log.warning("Finding %s co hanh dong %r khong ap dung tu dong duoc",
                        finding_id, f["suggested_action"])
            return False

        self.db.resolve_finding(finding_id, "ACCEPTED")
        log.info("Finding %s da ap dung: %s", finding_id, f["suggested_action"])
        return True

    def skip_finding(self, finding_id: int, note: str) -> bool:
        """Bỏ qua một finding — và **tạo một alert tồn tại**. Bỏ qua không có nghĩa là quên."""
        f = self.db.get_finding(finding_id)
        if f is None or f["resolution"] != "PENDING":
            return False
        self.db.resolve_finding(finding_id, "SKIPPED", note=note)
        self._alert("WARNING", "FINDING_SKIPPED",
                    f"Sai lech {f['kind']} (finding {finding_id}) bi bo qua co y: {note}. "
                    "Sai lech nay VAN CON; alert nay o lai de khong ai quen.",
                    pair_id=f["pair_id"])
        return True

    async def accept_all_safe(self, run_id: str) -> int:
        """Chấp nhận hàng loạt — **chỉ** `severity = SAFE`.

        Cố ý không có hàm nào chấp nhận hàng loạt các finding `DECISION`. Chúng dính tới mở lệnh
        hoặc đóng Master, và phải có người nhìn từng dòng.
        """
        so = 0
        for f in self.db.list_findings(run_id=run_id, resolution="PENDING", severity="SAFE"):
            if await self.accept_finding(f["id"]):
                so += 1
        return so

    async def manual_action(self, finding_id: int, action: str,
                            note: str | None = None) -> bool:
        """Người vận hành chọn một hành động khác với đề xuất."""
        f = self.db.get_finding(finding_id)
        if f is None or f["resolution"] != "PENDING":
            return False
        pair = self.db.get_pair(f["pair_id"]) if f["pair_id"] else None
        if action == "CLOSE_CLIENT" and pair is not None:
            await self.closing.close_pair_now(pair, "BOT")
        elif action == "MARK_CLOSED" and pair is not None:
            self.db.mark_pair_closed(pair["pair_id"], close_source="MANUAL",
                                     close_time_client=utc_now_iso(), master_da_dong=True)
        elif action == "MARK_ORPHANED" and pair is not None:
            self.db.update_pair(pair["pair_id"], status="ORPHANED", orphan_side="MASTER")
        elif action != "NOTHING":
            return False
        self.db.resolve_finding(finding_id, "MANUAL", note=note or action)
        return True

    # -- mở bù (plan 8.5) ----------------------------------------------------------------------

    async def _ap_chinh_sach_mo_bu(self, f: sqlite3.Row, pair: sqlite3.Row | None) -> None:
        """`offline_reopen_policy`. Mặc định `NONE` — ghi finding rồi chờ người.

        Với `IF_STILL_OPEN` bắt buộc **hai** điều kiện đồng thời: tuổi sự kiện và độ lệch giá.
        Chỉ dùng điều kiện thời gian là không đủ — vàng có thể nhảy 200 điểm trong 10 giây khi
        ra tin, và một sự kiện "mới 8 giây" vẫn khiến ta hedge ở mức giá vô nghĩa.
        """
        policy = self.db.get_config("offline_reopen_policy", "NONE")
        if policy != "IF_STILL_OPEN" or pair is None:
            log.info("Finding %s: offline_reopen_policy = %s nen khong mo bu", f["id"], policy)
            return

        ly_do = self._khong_du_dieu_kien_mo_bu(pair)
        if ly_do:
            self._alert("WARNING", "REOPEN_SKIPPED",
                        f"Cap {pair['pair_id']}: khong mo bu vi {ly_do}.",
                        pair_id=pair["pair_id"])
            return

        self._alert("WARNING", "REOPEN_REQUESTED",
                    f"Cap {pair['pair_id']}: du dieu kien mo bu theo IF_STILL_OPEN.",
                    pair_id=pair["pair_id"])

    def _khong_du_dieu_kien_mo_bu(self, pair: sqlite3.Row) -> str | None:
        """Trả về lý do KHÔNG đủ điều kiện, hoặc `None` nếu đủ cả hai."""
        client = self.db.get_client_account(pair["client_id"])
        tuoi = _tuoi_ms(pair["open_time_master"])
        gioi_han = int(client["max_event_age_ms"]) if client else 5000
        if tuoi is None or tuoi > gioi_han:
            return f"su kien da {tuoi}ms tuoi, vuot {gioi_han}ms"

        toi_da = self.db.get_config_int("max_reopen_slippage_points", 0)
        if toi_da <= 0:
            return "max_reopen_slippage_points chua duoc cau hinh (dang la 0)"
        return None


def _mo_ta(vi_the: Any) -> dict[str, Any] | None:
    if vi_the is None:
        return None
    return {"position_id": vi_the.position_id, "symbol": vi_the.symbol,
            "direction": vi_the.direction, "volume": vi_the.volume,
            "magic": vi_the.magic, "comment": vi_the.comment}


def _tuoi_ms(moc_iso: str | None) -> int | None:
    if not moc_iso:
        return None
    try:
        return int((parse_iso(utc_now_iso()) - parse_iso(moc_iso)).total_seconds() * 1000)
    except (ValueError, TypeError):
        return None
