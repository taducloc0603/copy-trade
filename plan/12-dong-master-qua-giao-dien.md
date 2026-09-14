# Phase 12 — Đóng lệnh phía Master qua giao diện MT5

## Mục tiêu

Khi Client đóng và `can_close_master = 1`, lệnh đóng vị thế **Master** cũng phải mang
`DEAL_REASON = CLIENT (0)` thay vì `EXPERT (3)` — tức "Placed by manual" trên tài khoản Master.

## Điều kiện đầu vào

Phase 11 xong và chạy ổn định trên VPS (`CLOSE_UI` 0,77 giây, không rơi về EA). Cascade
`can_close_master = 1` đã bật và đã đo (TEST-29).

---

## 12.0 Vì sao phase này tồn tại

D-21 chốt từ đầu: **Master giữ `OrderSend`**. Lập luận lúc đó là bên kiểm tra chỉ soi tài khoản
Client. Nay yêu cầu mở rộng sang tài khoản Master, nên phần "Master giữ OrderSend" hết hiệu lực —
giống hệt cách D-21b đã mở rộng D-21 sang deal đóng của Client.

Hệ quả **không nhỏ**: đây là lần đầu hệ thống điều khiển giao diện của terminal **Master**. Trước
phase này, Master chỉ gửi sự kiện và nhận lệnh `CLOSE` qua EA; không có gì chạm vào cửa sổ của nó.

---

## 12.1 Cái phải thêm: một clicker thứ hai

Clicker là **một tiến trình lái một terminal**, khoá bằng mutex theo số tài khoản
(`SingleInstance`, `clicker/__main__.py:35`). Nên terminal Master cần **tiến trình riêng, agent
riêng, token riêng**.

| Thành phần | Hôm nay | Sau phase 12 |
|---|---|---|
| Tiến trình clicker | 1 (terminal Client) | 2 (thêm terminal Master) |
| Agent role `CLICKER` | `AG-CLICKER` | thêm `AG-CLICKER-MASTER` |
| Mục cấu hình | `[clicker]` | thêm `[clicker_master]` |
| Scheduled Task | `\CopyBridge\Clicker` | thêm `\CopyBridge\ClickerMaster` |

**Token không đi qua dòng lệnh** (quy tắc đã có): `clicker/__main__.py` thêm `--muc` (mặc định
`clicker`) để chọn mục cấu hình; `bridge/config.py` đọc thêm `[clicker_master]` thành một
`SecretSection` nữa. `chay-clicker.ps1` nhận `-Muc` và truyền xuống; `tao-dich-vu.ps1` đăng ký tác
vụ thứ hai.

Driver **không phải sửa gì**: `Mt5UiDriver.close()` lái theo `terminal_title` được truyền vào, và
phép tìm có kiểm chứng (D-30) không giả định terminal đó là Client.

---

## 12.2 Định tuyến lệnh đóng Master

Hôm nay `_gui_lenh_dong_master` (`bridge/engine/closing.py:563`) luôn gửi `CLOSE` cho EA Master, và
**hai** đường gọi nó: cascade (D-09) và đóng khẩn cấp.

Master **không có** dòng `client_account` để mang cột `close_route`. Dùng `system_config` — nó là
key/value nên không phải đổi schema:

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `master_close_route` | `EA` | `UI` thì đóng Master qua giao diện |
| `master_clicker_agent_id` | rỗng | agent `CLICKER` lái terminal Master |

`_gui_lenh_dong_master` thành điểm phễu duy nhất, đúng hình dạng `_gui_lenh_dong` của Client
(`:889`): `EA` → im lặng đi đường cũ; `UI` + clicker `ONLINE` → `CLOSE_UI` **không mang `magic`**;
clicker hỏng → rơi về EA kèm alert CRITICAL `CLOSE_MASTER_FELL_BACK_TO_EA`.

Rơi về được ở đây vì cùng lý do D-28: **không đóng được thì không an toàn**. Master còn vị thế
trong khi các Client đã đóng là phơi nhiễm một chiều.

---

## 12.3 Tương quan: đừng để chính mình kích hoạt mình

`on_master_close` (`:136`) phân biệt "bot đóng" với "người đóng" bằng `caused_by_command_id`, mà
EA Master **chỉ gán được khi chính nó thực thi lệnh**. Đóng qua giao diện thì clicker bấm, EA chỉ
thấy một deal không rõ nguồn → `caused_by_command_id = NULL` → Bridge tưởng **người dùng** vừa đóng
Master.

Đây là lỗ hổng đã gặp và đã giải ở phía Client (D-27): gán nguyên nhân tại Bridge bằng **cửa sổ
lệnh đang bay**, đo từ `event.received_at` chứ không phải "bây giờ". Phase này dùng lại đúng cơ
chế đó cho Master: `_ai_gay_ra` được mở rộng để soi cả `CLOSE_UI` gửi tới clicker của Master.

Thiếu bước này, một lần cascade sẽ tự kích hoạt lại chính nó và sinh ra alert cùng finding rác.

---

## 12.4 Đo được, không phải tin

Hôm nay `pair.client_close_reason` giữ `DEAL_REASON` của deal đóng phía Client (`:503`), và
`kiem-reason` soi hai cột đó (`bridge/ops.py:204`). Phía Master **không lưu gì**.

- Migration `005`: thêm `master_position.close_reason`.
- `on_master_close` ghi `data["reason"]` vào cột đó — EA đã gửi sẵn (`CopyBridgeCommon.mqh:1897`).
- `kiem-reason` thêm một mục: khi `master_close_route = UI`, mọi `master_position.close_reason`
  khác `0` là vi phạm, cùng cách "đã có giải thích" nếu có alert rơi về EA.
- Bộ đối chiếu `_soi_reason` thêm cặp `master_close_route` / `close_reason`.

---

## 12.5 Rủi ro mới, và cái không đổi

**Mới:**

- Terminal Master phải **luôn mở Toolbox ở tab Trade**, y như Client (B-14 mở rộng).
- Mức toàn vẹn của clicker Master phải ≥ MT5 Master, nếu không `PostMessage` trả về thành công mà
  không có gì xảy ra (bẫy UIPI đã biết).
- Thêm một tiến trình (~4 MB) và một token phải quản lý.
- Đóng Master chậm hơn: `OrderSend` ~0,3 giây so với ~0,8 giây qua giao diện. Hạn chờ cascade
  (`cascade_wait_master_ms`) phải xét lại, cùng cách hạn chờ đóng khẩn cấp đã co giãn.

**Không đổi:** đường **mở** của Master. Bot không bao giờ mở lệnh trên Master — người dùng tự mở.

---

## 12.6 Thứ tự làm

1. **Đo trước** trên terminal Master của VPS: `python -m clicker.ui.dump --title <so-tk-master>
   --all-controls` với hộp thoại đóng đang mở. Khác ctrlID thì dừng, không sửa code.
2. Cấu hình clicker thứ hai: `config.py` + `clicker/__main__.py --muc` + `chay-clicker.ps1 -Muc` +
   `tao-dich-vu.ps1`.
3. Định tuyến: `system_config` hai khoá + `_gui_lenh_dong_master` + rơi về EA có alert.
4. Tương quan `_ai_gay_ra` cho Master.
5. Migration `005` + ghi `close_reason` + `kiem-reason` + đối chiếu.
6. Lệnh `bridge.admin cau-hinh-master --close-route UI --clicker-agent AG-CLICKER-MASTER`, và hiển
   thị trên dashboard.
7. Tài liệu: DECISIONS (D-21c), RUNBOOK, CAI-DAT-VPS, ACCEPTANCE (TEST-30).

---

## 12.7 Nghiệm thu

| | Phép thử | Đạt khi |
|---|---|---|
| TEST-30a | Đóng ở Client, `can_close_master = 1` | Master đóng theo, `master_position.close_reason = 0` |
| TEST-30b | Tắt clicker Master rồi đóng ở Client | Master vẫn đóng qua EA, có alert CRITICAL, `kiem-reason` xếp vào "đã có giải thích" |
| TEST-30c | Cascade với hai Client | Không sinh vòng lặp tự kích hoạt; đúng một lệnh đóng Master |
| TEST-30d | Đóng khẩn cấp | Thứ tự Client → Master giữ nguyên, Master mang `CLIENT` |
| TEST-30e | `kiem-reason` sau cả bốn bài | ĐẠT, và **đỏ** nếu cố tình đặt `master_close_route = UI` mà đóng Master bằng EA |

Ước lượng: phần code khoảng như phase 11 nhưng hẹp hơn — không có phép tìm mới, chỉ là định tuyến,
tương quan, cấu hình và đo lường. Phần **vận hành** mới là chỗ tốn: thêm token, thêm tác vụ, thêm
một terminal phải giữ đúng tư thế.
