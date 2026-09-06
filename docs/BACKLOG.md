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

### B-05 — Trang cấu hình trên dashboard mới ở mức đọc

*(Thu hẹp ở phase 11: `copy_mode`, `volume_multiplier`, `open_route` và `can_close_master` nay
sửa được bằng `python -m bridge.admin cau-hinh-client`, không phải SQL tay nữa — B-11.)*

Còn lại: **dashboard** chưa có API ghi, và **ánh xạ symbol** vẫn phải sửa trong DB.

### B-06 — Cascade chưa chạy trên demo

*(Thu hẹp ở phase 11: **EMERGENCY đã nghiệm thu trên demo**, TEST-21 nay là DEMO.)*

Cascade (D-09, TEST-05, TEST-15) vẫn chỉ có test tự động — cần ≥2 Client thật để dựng tình huống
có ý nghĩa. Đường đóng vị thế Master mà cascade dựa vào thì **đã chạy thật** ở phase 11, nên rủi
ro còn lại nằm ở phần chờ-xác-nhận-rồi-mới-lan-truyền chứ không còn ở chính khả năng đóng.

### B-07 — Close By không có dữ liệu thực nghiệm

Broker Connext-Demo không hỗ trợ Close By, nên D-12 được cài mà chưa từng đối chiếu với hành vi
thật của sàn. Đổi broker thì đây là bài chạy lại đầu tiên.

### B-08 — Bài "phiên RDP đã ngắt" chưa từng chạy — **chặn triển khai VPS**

Toàn bộ đường mở lệnh dựa vào clicker điều khiển giao diện MT5 bằng `PostMessage`. Lập luận
"không cần desktop tương tác nên chạy được khi phiên RDP đã ngắt" có từ phase 6b mục E1 và **chưa
bao giờ được đo**: bản gần đúng duy nhất là 5/5 probe với cửa sổ **minimized** (phase 6b mục 4.6).
Mục này ghi là "chuyển sang phase 10 vì máy đo là laptop", rồi **rơi khỏi mọi danh sách theo dõi**
cho tới lượt rà soát 2026-09-06.

Trên laptop đây là mục nice-to-have. Trên VPS nó là **trạng thái vận hành bình thường**: người
vận hành RDP vào, làm việc, rồi ngắt kết nối — và từ giây đó trở đi mọi lệnh copy đều đi qua một
cơ chế chưa ai chứng minh là còn hoạt động.

**Cách trả:** trên chính VPS, RDP vào, chạy stack, đặt một lệnh, **ngắt phiên RDP** (đóng cửa sổ
RDP chứ không Sign out), rồi từ xa kiểm qua database xem lệnh tiếp theo có được copy không. Chế
độ hỏng cần phân biệt: canary đỏ (an toàn — Bridge ngừng gửi `OPEN_UI`) so với canary xanh mà cú
bấm không tới nơi (nguy hiểm).

### B-09 — Bridge không biết Algo Trading của terminal đang bật hay tắt

`MQL_TRADE_ALLOWED` chỉ được kiểm **bên trong EA**, lúc khởi động và lúc nhận command; nó không
bao giờ đi vào `hello` hay `heartbeat`, nên dashboard và bộ đối chiếu đều mù với nó.

Bất đối xứng nguy hiểm: đường **mở** phía Client đi qua giao diện nên **không cần** Algo Trading,
còn đường **đóng** đi qua EA nên **cần**. Một terminal có Algo Trading tắt sẽ vẫn mở lệnh bình
thường và chỉ hỏng khi đóng — tức là tích luỹ vị thế một chiều rồi mới báo `CLOSE_FAILED`.

Sau khi VPS khởi động lại hoặc MT5 tự cập nhật, Algo Trading tắt là trạng thái hoàn toàn có thật.

**Cách trả:** thêm `trade_allowed` vào heartbeat, hiện trên dashboard cạnh canary, và cho Bridge
từ chối gửi lệnh mở khi phía Client không đóng được. Chi phí: sửa EA (phải biên dịch và **gỡ ra
gắn lại**, xem RUNBOOK mục 2), sửa schema message, sửa dashboard.

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

**Phase 11 (lượt hai) — dọn nốt B-08…B-13:**

- ~~B-08: mức alert không nhất quán~~ → `VOLUME_BELOW_MIN`, `PARTIAL_CLOSE_ROUNDS_TO_ZERO` và
  `KHOI_DONG_EP_PAUSED` lên **ERROR** (đều là "đã mất hedge" hoặc "đã ngừng copy");
  `RECONCILE_FINDINGS` nay lấy mức theo **mức nghiêm trọng thật** của finding trong vòng đó —
  `DECISION` → ERROR, toàn `SAFE` → WARNING.
- ~~B-09: finding `PENDING` không có gì nhắc~~ → `FINDING_BO_QUEN` mức ERROR khi cái cũ nhất quá
  `finding_nhac_sau_phut` (mặc định 60). Mốc nhắc ghi vào `system_config` nên khởi động lại không
  thành cách vô tình để im lặng mãi; đặt 0 thì tắt.
- ~~B-10: `cap-token` không bật lại agent đã thu hồi~~ → cấp token nay bật lại `enabled`, kèm một
  dòng WARNING nói rõ.
- ~~B-11: không có lệnh admin đổi cấu hình Client~~ → `bridge.admin cau-hinh-client`, có ràng
  buộc (`multiplier > 0`, `open_route = UI` phải có clicker) và nói rõ cặp đang chạy giữ nguyên
  tỷ lệ cũ.
- ~~B-12: vài dòng `pair` còn số liệu sai~~ → `don_so_sach()`, chạy trong `bao_tri_hang_ngay`.
  Đã chạy thật trên `data/bridge.db`: sửa 2 dòng, còn 0.
- ~~B-13: guard D-16 chưa quét `clicker/`~~ → quét cả hai gói.
