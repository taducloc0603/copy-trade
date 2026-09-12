# Backlog — để lại cho v2

*Chốt ngày 2026-09-06 (Phase 10), cập nhật sau Phase 11.*

Danh sách này gồm hai loại và chúng khác nhau hoàn toàn: **món nợ** (đã biết là thiếu, có ảnh
hưởng tới cách dùng hôm nay) và **mở rộng** (chưa cần cho MVP). Món nợ đứng trước.

---

## Quyết định có chủ đích, KHÔNG phải thiếu sót

**Kênh cảnh báo Telegram bị tắt.** Người dùng chốt ngày 2026-09-06. `bridge/alerting.py` vẫn còn
nguyên và hoạt động; cấu hình trống thì kênh im lặng chứ không lỗi, nên bật lại chỉ là điền
`telegram_token` + `telegram_chat_id` vào `config.toml`.

Hệ quả đã được chấp nhận: **không có gì chủ động báo khi hệ thống gặp sự cố.** Cơ chế bù là
`python -m bridge.admin tinh-hinh` kèm lịch kiểm tay — xem `docs/KE-HOACH-CHAY-THAT.md` mục 1.2.

Đừng ghi việc này thành một món nợ ở lượt rà soát sau.

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

---

### B-14 — Tab Trade của Toolbox phải là tab đang mở

**Trạng thái:** giới hạn vận hành của đường đóng qua giao diện, cùng loại với B-01.

Clicker nhận ra danh sách vị thế bằng `ctrlID 10328`, và tab không mở thì control đó không
`visible`. Chế độ hỏng là **an toàn**: `tradetab.tim_danh_sach()` từ chối ồn ào chứ không đoán, nên
không có nguy cơ đóng nhầm vị thế. Nhưng lệnh đóng sẽ rơi về EA và deal đó mang `EXPERT`.

**Cách trả:** đo xem có chuyển tab được bằng `TCM_SETCURSEL` hay bằng `ToolbarWindow32` của Toolbox
mà MT5 thật sự đổi nội dung hay không — cùng kiểu nghi ngờ đã dùng cho `WM_SETTEXT`. Trước khi đo
được thì đây là một dòng trong `RUNBOOK.md` mục 5c, không phải một tính năng.

### B-15 — Đóng lệnh qua giao diện chậm hơn đường EA khoảng 16 lần

Đo 2026-09-10 trên demo: `CLOSE_UI` **5,1–5,5 giây**, `CLOSE_UI_PARTIAL` **5,8–5,9 giây**, so với
**342 ms** của đường EA. Clicker xử lý **một lệnh tại một thời điểm** (`link._gate`), nên nó là
điểm nghẽn của **cả hai** đường — mở và đóng giành nhau cùng một cổng.

Hệ quả đã xử lý: hạn chờ của đóng khẩn cấp co giãn theo số lệnh (`10 + 8n`, trần 120 giây) thay vì
10 giây cố định.

Hệ quả **chưa** xử lý: một cặp đang chờ đóng sẽ làm chậm lệnh mở của cặp khác. Chưa quan sát thấy
gây hại, nhưng chưa đo với nhiều cặp cùng lúc.

**Cách trả:** phần lớn thời gian có vẻ nằm ở việc `_map_controls` đọc `WM_GETTEXT` của ~50 control
mỗi lần quét hộp thoại, và `cho_mo` quét lại mỗi 50 ms. Đo trước khi tối ưu — đừng đoán.

**Đo trên VPS 2026-09-11 — con số "5 giây" không phải chi phí của đường giao diện.** Tách từng chặng
của một lần đóng thật: Master báo → Bridge gửi `CLOSE_UI` **95 ms**; clicker **6,1 s** rồi `rejected`;
rơi về EA **26 ms**; EA đóng **264 ms**. 6,1 giây đó là **một cú double-click bị treo** (chặn đúng
hết hạn 2 giây, không mở hộp thoại) cộng 2 giây chờ, rồi 2 giây chờ vô ích ở dòng Balance. Chạy chẩn
đoán tay trên cùng terminal: **13/15** lần nhấp mở hộp thoại trong **0,27–0,75 s**; 2 lần còn lại đúng
kiểu treo đó (cộng lần đóng thật là 3), và lần nhấp lại ngay sau một lần treo thì mở. Đã loại trừ: terminal không ở phía trước, MT5 nghỉ
45 giây, bước chọn dòng. Chưa tìm ra cơ chế. Bản sửa: `_mo_dong` nhấp lại **một lần** khi message
treo (không nhấp lại khi dòng trả lời ngay mà không mở gì), và ghi log thời gian từng lần nhấp vào
`logs/clicker.log` — lần sau đo từ log chứ không phải chạy script tay.

**Tối ưu 2026-09-12 — bỏ phần đắt nhất của phép dò.** `_map_controls` đọc `WM_GETTEXT` của ~55
control, mỗi lời gọi là một `SendMessage` **liên tiến trình** vào đúng luồng giao diện MT5 đang bận,
và phép tìm trả cái giá đó cho **mọi** dòng nó mở ra chỉ để loại. Nhưng loại một dòng chỉ cần ticket,
mà ticket nằm trong tiêu đề `Position: #<ticket>` — `GetWindowTextW` đọc từ cache của hệ điều hành,
không chặn. Nay vòng dò dùng `dialog.HopThoaiDongSoBo` (chỉ tiêu đề); chỉ dòng **đã khớp ticket** mới
`ClosePositionDialog.tu_hwnd()` đọc đủ control, và `_commit_close` vẫn kiểm ticket từ cả ba nguồn
trước khi bấm (D-30 không đổi). Thêm `_thu_tu_dong`: dòng đóng trúng lần trước được dò trước — chỉ là
thứ tự, đoán sai vẫn đọc ngược kiểm chứng. Giữ đường dự phòng quét đầy đủ cho bản MT5 đặt tiêu đề
khác.

**Đo lại trên VPS sau tối ưu đó: `CLOSE_UI` còn 3,2–4,5 giây, và 6/6 lần đóng đều mất 2,5 giây ở
cùng một chỗ.** Log `Do dong` cho thấy cú nhấp **đầu tiên của mỗi lần đóng** treo tới đúng hết hạn
`SEND_TIMEOUT_MS` = 2 giây rồi **không** mở hộp thoại; cú nhấp lại mở trong 0,28–1,17 giây. Tức là
hiện tượng "thỉnh thoảng treo" hôm 09-11 thật ra là **luôn treo** trong ngữ cảnh clicker thật, chỉ
chạy tay mới thấy thưa. Chưa biết cơ chế; nghi MT5 vào một vòng lặp bắt kéo-thả chờ chuột thật.

Hạ giá phải trả mà không cần biết cơ chế: thêm `win32.CLICK_TIMEOUT_MS = 600` cho **riêng** ba
message chuột (hạn chờ 2 giây vẫn giữ cho các message đọc), và `CHO_SAU_KHI_TREO_SEC` 0,5 → 0,15 vì
cú nhấp treo không bao giờ mở hộp thoại. Hạ được vì giá trị trả về của ba message ấy **không phải
bằng chứng**. Dự kiến còn ~1,5 giây; **chưa đo**.

### B-16 — `dry_probe()` chưa được nối vào canary

**Đây là quyết định có chủ đích, ghi lại để không ai tưởng là quên.** Canary chạy mỗi giây, mà
`dry_probe` mở rồi đóng một hộp thoại **thật** trên terminal đang giao dịch. Nối thẳng vào nhịp
heartbeat là sai.

Canary hiện chỉ kiểm cửa sổ terminal còn sống (`probe.probe()`), không kiểm được "hộp thoại còn
điền được". Khoảng trống đó có thật.

**Cách trả:** chạy `dry_probe` theo chu kỳ riêng, thưa hơn hẳn (vài phút), và **chỉ khi không có
lệnh nào đang bay**. Cũng không đưa "tab Trade có đang mở" vào canary chung: tab Trade đóng **không**
ảnh hưởng đường mở, nên để nó làm canary đỏ sẽ dừng copy vì một lý do không liên quan.

### B-17 — `already_closed` cho lệnh đóng **một phần** để lại volume cũ

Nếu một `CLOSE_UI_PARTIAL` (hoặc `CLOSE_PARTIAL`) trả `already_closed` — vị thế đã biến mất trước
khi lệnh tới — thì `_sau_dong_bot` trừ `0` và cặp nằm lại `PARTIALLY_CLOSED` với volume cũ, cho tới
khi vòng đối chiếu bắt được.

**Có sẵn ở cả đường EA**, không phải lỗi mới. Không sửa ngay vì đối chiếu đúng là cơ chế tồn tại
cho loại lệch này, và vì đường đi này chưa quan sát thấy lần nào trên demo.

### B-18 — Ô "cần can thiệp" đỏ vĩnh viễn vì hai cặp diễn tập cũ

`views.py` đếm mọi pair ở `ORPHANED` hoặc `OPEN_FAILED`. Hai cặp `PAIR-20260905-000006` và
`000007` là dấu vết của một buổi diễn tập bị abort ở phase 6b — đã ghi rõ lý do trong
`error_message`, đã hết từ lâu ngoài đời, và **không còn gì để can thiệp**.

Nhưng `OPEN_FAILED` nằm trong `TERMINAL_STATUSES` nên vòng đối chiếu không bao giờ nhìn lại chúng,
và không có khái niệm "đã xem" cho pair như `alert.acknowledged_at`. Nên ô ấy đỏ **vĩnh viễn**.

Chính bình luận trong `views.py` nói vì sao điều đó tệ: *"Chỉ tô đỏ khi khác 0. Nếu luôn đỏ, mắt sẽ
quen và bỏ qua."*

**Cố ý chưa sửa.** Ba hướng đều có nhược điểm và không hướng nào nên chọn vội ngay trước khi lên
VPS: lọc theo `error_message IS NOT NULL` sẽ **giấu luôn** các lỗi thật (`CLOSE_TIMEOUT`,
`CLOSE_FELL_BACK_TO_EA` cũng ghi cột đó); lọc theo thời gian là một ngưỡng tuỳ tiện khác; thêm cột
"đã xem" cho pair là đúng nhất nhưng cần migration và một lệnh admin.

Đổi ngữ nghĩa của một tín hiệu được thiết kế để tin, dưới sức ép thời gian, là đúng loại thay đổi
không nên làm.

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
- ~~B-09: Bridge không biết Algo Trading của terminal~~ → EA gửi `trade_allowed` trong heartbeat,
  Bridge lưu (migration `003`), báo `TRADE_NOT_ALLOWED` mức ERROR **khi cờ đổi**, hiện trên
  dashboard, và thêm **cổng thứ ba** ở đường mở: Client không đóng được thì **không mở lệnh mới**.
  `NULL` (EA bản cũ) không chặn — "không biết" khác "biết là tắt".
