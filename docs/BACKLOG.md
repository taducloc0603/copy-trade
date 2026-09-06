# Backlog — để lại cho v2

*Chốt ngày 2026-09-06 (Phase 10).*

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

### B-06 — Cascade và EMERGENCY chưa chạy trên demo

Cả hai chỉ có test tự động (TEST-05, TEST-15, TEST-21). Cần ≥2 Client thật để dựng tình huống có
ý nghĩa.

### B-07 — Close By không có dữ liệu thực nghiệm

Broker Connext-Demo không hỗ trợ Close By, nên D-12 được cài mà chưa từng đối chiếu với hành vi
thật của sàn. Đổi broker thì đây là bài chạy lại đầu tiên.

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
