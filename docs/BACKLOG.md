# Backlog — để lại cho v2

*Chốt ngày 2026-09-06 (Phase 10), cập nhật sau Phase 11.*

Danh sách này gồm hai loại và chúng khác nhau hoàn toàn: **món nợ** (đã biết là thiếu, có ảnh
hưởng tới cách dùng hôm nay) và **mở rộng** (chưa cần cho MVP). Món nợ đứng trước.

---

## Món nợ — ảnh hưởng tới cách dùng hôm nay

### B-01 — Mỗi terminal Client chỉ copy được một symbol

**Trạng thái:** chặn TEST-08. `plan/00` mục 2 nói MVP hỗ trợ "nhiều symbol đồng thời", nên hệ
thống hiện **hẹp hơn phạm vi đã tuyên bố**.

Hộp thoại New Order lấy symbol theo chart đang mở. Driver *kiểm tra* symbol và từ chối nếu lệch
chứ không đổi — đổi symbol qua ComboBox `10331`/`10325` **chưa được đo lần nào**.

Chế độ hỏng hiện tại là an toàn ("không copy, có cảnh báo"), không phải "copy sai symbol". Đó là
lý do món nợ này chấp nhận được để lại, chứ không phải lý do nó biến mất.

**Cách trả:** đo hai ComboBox trên terminal thật đúng cách đã đo `WM_CHAR` ở phase 6b — thử từng
đường, xem MT5 có thật sự đổi trạng thái nội bộ không, chứ không tin vào việc ô hiển thị đúng
chữ. Bài học `WM_SETTEXT` là chính xác về chuyện này: ô hiện đúng nhưng lệnh gửi đi mang giá trị
của lần trước.

### B-02 — TEST-19: chưa từng rút điện thật

Toàn bộ lập luận "không mất event khi mất điện" hiện dựa vào `synchronous = FULL` + WAL, tức là
*cấu hình đúng*, không phải *quan sát*. Phải chạy trước khi động vào tiền thật —
xem `RUNBOOK.md`.

### B-03 — Chạy 24 giờ liên tục

`pytest -m cham` đã kiểm được WAL **có** được checkpoint (4,1 MB → 0) và thông lượng ~900
event/s, nhưng rò rỉ bộ nhớ và tốc độ tăng của DB chỉ lộ ra sau nhiều giờ.

### B-04 — `offline_reopen_policy = CLOSE_MASTER` chưa cài

Mới có `NONE` (mặc định) và `IF_STILL_OPEN`. Bản `IF_STILL_OPEN` hiện dừng ở mức kiểm hai điều
kiện rồi cảnh báo, **chưa thực sự mở bù** — cố ý: "được tự động ĐÓNG, không được tự động MỞ"
(D-13) nên việc mở bù cần người bấm.

### B-05 — Trang cấu hình mới ở mức đọc

Sửa hệ số, đổi `open_route`, lưu ánh xạ symbol chưa có API ghi. Hiện phải sửa thẳng trong DB
hoặc bằng `python -m bridge.admin`.

### B-06 — Cascade chưa chạy trên demo

*(Thu hẹp ở phase 11: **EMERGENCY đã nghiệm thu trên demo**, TEST-21 nay là DEMO.)*

Cascade (D-09, TEST-05, TEST-15) vẫn chỉ có test tự động — cần ≥2 Client thật để dựng tình huống
có ý nghĩa. Đường đóng vị thế Master mà cascade dựa vào thì **đã chạy thật** ở phase 11, nên rủi
ro còn lại nằm ở phần chờ-xác-nhận-rồi-mới-lan-truyền chứ không còn ở chính khả năng đóng.

### B-07 — Close By không có dữ liệu thực nghiệm

Broker Connext-Demo không hỗ trợ Close By, nên D-12 được cài mà chưa từng đối chiếu với hành vi
thật của sàn. Đổi broker thì đây là bài chạy lại đầu tiên.

### B-08 — Mức alert không nhất quán cho cùng một hậu quả (F-07)

Phase 10 nâng `UI_OPEN_BUSY` lên ERROR vì bỏ một lệnh copy là mất hedge, mà chỉ ERROR trở lên mới
ra được Telegram. Lập luận đó chưa áp cho các mã cùng hậu quả: `VOLUME_BELOW_MIN` (bỏ một lệnh
copy), `PARTIAL_CLOSE_ROUNDS_TO_ZERO` (phần đóng bị bỏ), `RECONCILE_FINDINGS` (sổ sách lệch thực
tế), và `KHOI_DONG_EP_PAUSED` — mã cuối nghịch lý nhất, vì D-15 sinh ra cho tình huống *không ai
nhìn màn hình* mà alert lại ở mức không gửi đi đâu.

### B-09 — Finding `PENDING` không có gì nhắc lại (F-08)

Hiện có 4 finding `PENDING`, cái cũ nhất từ 03:57 ngày 06-09. Không có cơ chế nhắc, và alert duy
nhất báo về chúng ở mức WARNING (B-08).

### B-10 — `cap-token` không bật lại agent đã thu hồi

`thu-hoi` đặt `enabled = 0`; `cap-token` sau đó cấp token mới nhưng **không** bật lại, nên agent
vẫn bị từ chối bắt tay với `AGENT_DISABLED` và người vận hành không có manh mối nào. Gặp thật khi
dựng lại clicker trong phase 11, phải `UPDATE` thẳng DB.

### B-11 — Không có lệnh admin đổi cấu hình Client (F-12)

`copy_mode`, `volume_multiplier`, `open_route` chỉ sửa được bằng SQL tay. Để chạy TEST-01 trong
phase 11 phải `UPDATE` thẳng vào `client_account`. Đây là cái giá thật của B-05.

### B-12 — Vài dòng `pair` cũ còn số liệu sai

`PAIR-20260906-000007` và `000008` là `CLOSED` nhưng còn `master_current_volume` khác 0 — dữ liệu
sinh ra giữa lúc phase 11 đang sửa. Cùng loại với `PAIR-000027` mang `0.030000000000000002`. Vô
hại về nghiệp vụ (cặp đã đóng) nhưng làm bẩn báo cáo.

### B-13 — Test canh gác D-16 chưa quét `clicker/` (F-11)

Hiện `clicker/` không có vi phạm nào, nên đây thuần là rủi ro hồi quy.

---

## Mở rộng — không thuộc MVP

- Nhiều Client **thật** trên giao diện: cấu hình riêng từng Client, so sánh chéo, chính sách
  theo nhóm.
- Copy Pending Order và đồng bộ sửa SL/TP.
- Hỗ trợ tài khoản Netting (hiện chỉ Hedging).
- Tự động copy phần dư sau close-by — chỉ làm sau khi đã có dữ liệu thật cho B-07.
- Cascade cho đóng một phần từ phía Client (hiện D-11 nói KHÔNG cascade).
- Quy đổi volume theo tick value thay vì contract size.
- Phân quyền nhiều người vận hành và nhật ký ai đổi gì lúc nào.

---

## Đã đóng ở Phase 10

Ghi lại để lần sau không phải đi tìm:

- ~~Gửi bù khuếch đại vô hạn~~ → `MAX_RESEND_ATTEMPTS = 3` cho mỗi mốc `from_seq`
  (`bridge/protocol/server.py`).
- ~~Log `chuyển OFFLINE` lặp mỗi 0,5 giây~~ → chỉ in khi **chuyển** trạng thái.
- ~~Trạng thái `ONLINE` cũ không bao giờ được dọn~~ → `BridgeServer.start()`/`stop()` đánh mọi
  agent về `OFFLINE`.
- ~~Cấp agent/token bằng script tạm trong scratchpad~~ → `python -m bridge.admin`.
- ~~`UI_OPEN_BUSY` ở mức WARNING~~ → nâng lên **ERROR**: bỏ một lệnh copy là mất hedge, và từ
  Phase 10 chỉ ERROR trở lên mới ra được Telegram.
- ~~Bộ migration chưa từng chạy quá version 1~~ → migration `002` đã chạy thật trên
  `data/bridge.db`, version 1 → 2, dữ liệu nguyên vẹn.
- ~~`run_mode` không bị ép về `PAUSED` khi khởi động~~ → nay ép thật, kèm alert (D-15).
- ~~41 chuỗi log còn dấu tiếng Việt~~ → bỏ dấu, và khoá bằng test (D-16).

**Phase 11 (2026-09-06), sau kiểm toán độc lập:**

- ~~F-01: nút đóng khẩn cấp không đóng phía Master~~ → `emergency_close_all` nay đóng cả hai vế,
  và **EA Master được cấp khả năng đóng lệnh** (vẫn cấm mở). Nghiệm thu trên demo: `master_position`
  còn OPEN = 0.
- ~~F-02: dashboard không xác thực với cấu hình mặc định~~ → `parse_config` từ chối khởi động khi
  nghe ngoài loopback mà không có mật khẩu; mặc định `host` đổi thành `127.0.0.1`.
- ~~F-03: clicker rơi OFFLINE vì biên heartbeat bằng 0~~ → nhịp 5s → **1s**, khớp EA. Đo 36 phút
  liên tục: 0 lần OFFLINE.
- ~~F-04: D-19 lệch giữa quyết định và code~~ → sửa **quyết định** cho khớp code, và cho bộ đối
  chiếu dùng cùng công thức.
- ~~F-05: cặp `ORPHANED` không bao giờ được đối chiếu lại~~ → thêm `ORPHAN_RESOLVED`. Chạy thật:
  hai cặp mồ côi được phát hiện và đóng sổ.
- ~~F-06: "0 sai lệch" nghĩa là "0 finding mới"~~ → báo cả số mới lẫn tổng đang chờ.
- ~~F-09: `ACCEPTANCE.md` tự khai sai số~~ → đếm lại từ bảng.
