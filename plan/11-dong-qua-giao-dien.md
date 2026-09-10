# Phase 11 — Đóng lệnh qua giao diện MT5

## Mục tiêu

Deal **đóng** phía Client mang `DEAL_REASON = CLIENT (0)` thay vì `EXPERT (3)`. Sau phase này,
mọi deal trên tài khoản Client — cả `entry = IN` lẫn `entry = OUT` — đều là `CLIENT`, và
`kiem-reason` **kiểm được** điều đó chứ không phải tin.

## Điều kiện đầu vào

Phase 6b xong và chạy ổn định. Ba tiến trình như cũ; không thêm tiến trình nào.

---

## 11.0 Vì sao phase này tồn tại

D-21 chốt đường **mở** đi qua giao diện và **cố ý** để đường đóng lại trên `OrderSend`, với lập
luận: bên kiểm tra chỉ nhìn vị thế / lệnh mở, mà `POSITION_REASON` lấy từ deal mở nên vẫn là
`CLIENT`. Hệ quả đã được ghi thẳng là rủi ro treo ở `PROGRESS.md`:

> Deal **đóng** vẫn mang `EXPERT`. Đã chấp nhận vì bên kiểm tra chỉ nhìn vị thế / lệnh mở. Nếu sau
> này phát hiện bên kiểm tra nhìn cả deal đóng thì phạm vi phải mở rộng đáng kể.

Đã xảy ra. Phase này là phần "mở rộng đáng kể" đó (D-21b).

---

## 11.1 Bốn phép đo trước khi thiết kế

Đúng cách phase 6b làm với E1/E2/E3. Đo ngày 2026-09-10, tài khoản Client 538217, MT5 build 5.00,
bằng `python -m clicker.ui.dump`.

| | Câu hỏi | Kết quả |
|---|---|---|
| **C1** | Tab Trade có control Win32 thật không? | **XANH.** `SysListView32` thật, ctrlID `10328` |
| **C2** | Đọc được dòng nào là vị thế nào không? | **Nửa.** Hình học và lựa chọn đọc được; `LVM_GETITEMTEXT` chép **0 ký tự** |
| **C3** | Hộp thoại đóng có hình dạng gì? | **XANH.** Chính là hộp thoại New Order, `#32770` |
| **C4** | Có ID lệnh menu để mở nó không? | **ĐỎ.** Cả cây menu không có mục "Close position" |

**C2 là cái quyết định, và nó đỏ ở đúng chỗ nguy hiểm:** nhắm một dòng thì tất định, nhưng biết
dòng đó là vị thế nào thì không. MT5 tự vẽ từng dòng và không giữ chuỗi trong control.

Kết luận âm này **đã được loại trừ khả năng là lỗi của bên đọc** trước khi ghi thành sự thật:
ghi dấu vân tay vào vùng đệm rồi đọc lại thấy nguyên vẹn, `sizeof(LVITEMW) = 88` chuẩn x64, và
Market Watch — nơi chắc chắn có chữ — cũng trả rỗng y hệt.

**Cái cứu cả hướng đi nằm ở C3:** hộp thoại đóng cho đọc ngược ticket từ **ba nguồn độc lập**.

---

## 11.2 Nhắm vị thế: phép tìm có kiểm chứng (D-30)

```
mở dòng N  →  đọc ngược ticket  →  sai thì ESC, thử dòng N+1
                               →  đúng thì điền volume, đọc lại, rồi mới bấm
```

- Toạ độ dòng lấy từ `LVM_GETITEMRECT`, **không bao giờ** tự tính bằng chiều cao nhân chỉ số —
  có cuộn dọc là sai ngay, mà sai ở đây nghĩa là mở nhầm vị thế.
- Chọn dòng bằng `LVM_SETITEMSTATE` (API của control, không qua chuột), rồi
  `WM_LBUTTONDOWN` + `WM_LBUTTONUP` + `WM_LBUTTONDBLCLK` bằng **`SendMessage`**.
- Quét hết mà không thấy → `already_closed`, **không phải lỗi** (FR-18).

**Điều làm phép tìm này an toàn: mở và huỷ hộp thoại không đặt lệnh nào.** Mọi bước dò nằm ở phía
an toàn của ranh giới D-24.

> Danh sách có cả **dòng tổng kết Balance**, và nó không mở hộp thoại nào. Nên số dòng ≠ số vị thế,
> và một dòng không mở được là chuyện bình thường chứ không phải lỗi.

---

## 11.3 Bộ tương quan đóng (D-27) — phần nguy hiểm nhất

Đường đóng qua EA có `RememberCause`. Đường đóng qua giao diện **không có gì tương đương**: EA
không gọi `OrderSend` nên không có gì để nhớ, và hộp thoại đóng **không có ô Comment** nên mẹo gắn
thẻ của D-07b/D-23 cũng không dùng được.

Để nguyên thì mọi event `position_closed` do bot phát ra về Bridge với `caused_by_command_id =
NULL` — **đúng dấu hiệu của lệnh người dùng đóng tay**. Với `can_close_master = 1`, mỗi lệnh đóng
của bot tự kích hoạt một cascade đóng vị thế Master.

Cách bịt: Bridge tự nhận cha bằng cửa sổ `ui_close_correlate_grace_ms` (mặc định 5000), rồi ghi
`caused_by_command_id` ngược vào event để nhật ký không nói dối.

**Mơ hồ thì nhận cha, không cascade** — ngược với D-23, vì hai hướng sai không cân nhau.

---

## 11.4 Định tuyến và cú rơi về EA (D-28)

`CloseFlow._gui_lenh_dong` là **điểm phễu duy nhất** của mọi lệnh đóng phía Client.

| Tình huống | Đi đâu | Ồn ào? |
|---|---|---|
| `close_route = 'EA'` | `CLOSE` / `CLOSE_PARTIAL` tới EA | Im lặng — cấu hình bình thường |
| `close_route = 'UI'`, clicker ONLINE | `CLOSE_UI` / `CLOSE_UI_PARTIAL` tới clicker | Im lặng |
| `close_route = 'UI'`, clicker hỏng, `close_degraded_fallback = EA` | Đường EA | **CRITICAL** `CLOSE_FELL_BACK_TO_EA` |
| `close_route = 'UI'`, clicker hỏng, `= SKIP` | Không gửi gì | **CRITICAL** `CLOSE_KHONG_GUI_DUOC` |

Payload đường giao diện **không mang `magic`**; clicker từ chối thẳng payload có nó.

---

## 11.5 Biến mục tiêu thành thứ đo được

- Cột `pair.client_close_reason`, song song `client_open_reason`.
- Khác `0` trên đường UI → CRITICAL `UI_CLOSE_REASON_MISMATCH`.
- `kiem-reason` soi **cả hai** cột. Chỉ soi cột mở sẽ cho một kết quả "ĐẠT" hoàn toàn thật mà vẫn
  bỏ sót đúng nửa số deal — nửa mà phase này nhắm tới.

---

## Kiểm tra lại phần cũ

- [x] Toàn bộ test cũ xanh, không sửa test nào để nó xanh.
- [x] 27 test của phase 7 giữ nguyên ngữ nghĩa: `close_route` mặc định `EA`, nên đường cũ không đổi.
- [ ] Mở tay 5 lệnh trên demo, xác nhận vẫn copy đúng.

## Kiểm tra phần mới

- [x] Master đóng → `CLOSE_UI` gửi tới `clicker_agent_id`, payload không có `magic`.
- [x] Đóng một phần → `CLOSE_UI_PARTIAL` mang đúng volume.
- [x] **Lệnh đóng của bot không kích hoạt cascade** dù `caused_by_command_id` từ EA là NULL.
- [x] Người dùng đóng tay **vẫn** cascade như cũ — bộ tương quan không nuốt nhầm.
- [x] Ngoài cửa sổ grace → coi là đóng tay.
- [x] Clicker chết → rơi về EA, vị thế vẫn đóng được, alert CRITICAL.
- [x] `close_degraded_fallback = SKIP` → không gửi gì, alert CRITICAL.
- [x] `client_close_reason = 3` trên đường UI → CRITICAL; sau khi rơi về EA thì **không** báo thêm.
- [x] Ack `CLOSE_UI` không rơi vào nhánh mặc định; `CLOSE_UI_PARTIAL` giữ đúng volume còn lại.
- [x] `already_closed` là kết quả bình thường, không làm cặp `ORPHANED`.
- [ ] **TEST-26/27/28 trên demo thật** — chưa chạy.

## Tiêu chí hoàn thành

`python -m bridge.admin kiem-reason` báo ĐẠT trên **cả hai** cột sau một phiên có đóng hẳn, đóng
một phần, đóng tay từ cả hai phía, và một lần clicker chết giữa chừng.

## Không làm ở phase này

Phía **Master** giữ `OrderSend` (D-29). Tính chất sống-qua-RDP của cú double-click **chưa được
chứng minh** — chỉ đo được trên VPS ở giai đoạn 2, và phải đo **trước** khi chạy tài khoản thật.
