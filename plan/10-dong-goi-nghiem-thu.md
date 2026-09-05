# Phase 10 — Đóng gói, vận hành và nghiệm thu

## Mục tiêu

Biến dự án thành thứ chạy được không cần người ngồi canh, và chứng minh nó đúng bằng
bộ nghiệm thu đầy đủ trên tài khoản demo.

## Điều kiện đầu vào

Phase 9 xong. Toàn bộ hệ thống chạy được đầu-cuối với giao diện.

---

## Việc cần làm

### 10.1 Chạy như dịch vụ Windows

- Đóng gói Bridge bằng PyInstaller, hoặc chạy trực tiếp bằng Python đã cài sẵn.
- **`clicker` đóng gói riêng và chạy như Scheduled Task theo phiên đăng nhập, KHÔNG phải
  Windows Service** — service chạy ở session 0 và không thấy cửa sổ của phiên người dùng.
  Cần bật autologon để phiên tồn tại sau khi máy khởi động lại, và tắt sleep/hibernate.
- Đăng ký dịch vụ bằng NSSM hoặc `pywin32`. Tự khởi động khi máy bật.
- Ghi log ra `logs/` với xoay vòng theo ngày, giữ 30 ngày.
- Dịch vụ khởi động ở `run_mode = PAUSED` (D-15). Không có ngoại lệ nào cho việc này,
  kể cả khi máy restart lúc 3 giờ sáng.
- Viết `docs/RUNBOOK.md`: cách cài, cách khởi động lại, cách xem log, xử lý các lỗi thường gặp.

### 10.2 Mạng và bảo mật

- Cài Tailscale trên máy Bridge và các VPS agent. Ghi lại địa chỉ `100.x.y.z` vào `RUNBOOK.md`.
- Tailscale ACL: chỉ node agent được chạm vào port 8787, chỉ máy quản trị được chạm 8080.
- Firewall Windows: chặn 8787 và 8080 trên mọi interface **trừ** interface Tailscale
  và loopback. Không bao giờ mở ra Internet công cộng.
- Token: sinh ngẫu nhiên tối thiểu 32 byte, lưu hash trong DB, giá trị thô chỉ đặt trong
  tham số EA và `config.toml`. Có hàm thu hồi và cấp lại.
- Kiểm tra toàn bộ log: không có dòng nào chứa token hoặc mật khẩu.

> Tailscale xác thực **máy**, không xác thực terminal nào hay tài khoản MT5 nào đang gửi lệnh.
> Token ở tầng ứng dụng vẫn bắt buộc (mục XX của đặc tả gốc).

### 10.3 Sao lưu và lưu trữ

- Công việc hàng ngày: chạy `retention.py`, xuất event/command quá 30 ngày sang
  `data/archive/YYYY-MM.db`, rồi xoá khỏi DB nóng (D-17).
- Sao lưu `bridge.db` hàng ngày bằng `VACUUM INTO` (an toàn với WAL, không cần dừng dịch vụ).
  Giữ 14 bản, copy sang ổ khác hoặc cloud storage.
- Kiểm chứng: khôi phục một bản sao lưu vào thư mục tạm và mở được, có đủ dữ liệu.

### 10.4 Kênh cảnh báo

- Telegram bot cho alert mức ERROR và CRITICAL. Cấu hình token và chat id trong `config.toml`.
- Gộp cảnh báo: cùng một mã lỗi lặp lại trong 60 giây chỉ gửi một tin kèm số lần.
  Không để một sự cố làm ngập điện thoại.
- Alert CRITICAL luôn gửi ngay, không gộp.
- Kênh cảnh báo hỏng **không được** ảnh hưởng tới luồng giao dịch. Chạy ở task riêng,
  lỗi chỉ ghi log.

### 10.5 Kiểm thử tải

- Bơm 10.000 event qua mock agent, đo thời gian xử lý và độ trễ p95.
- Chạy liên tục 24 giờ với mock agent sinh lệnh ngẫu nhiên: kiểm tra rò rỉ bộ nhớ,
  kích thước file WAL, tốc độ tăng của DB.
- Mô phỏng 5 Client cùng lúc trên mock agent. **Dù MVP chỉ dùng 1 Client**, mô hình dữ liệu
  đã viết cho N từ phase 2 — đây là lúc chứng minh nó thật sự hoạt động.

---

## Bộ nghiệm thu

Chạy toàn bộ trên **tài khoản demo**, ghi kết quả vào `docs/ACCEPTANCE.md` kèm ngày giờ.

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| TEST-01 | Copy cùng chiều: Master BUY XAUUSD 1.00, hệ số 0.50 | Client BUY symbol đã ánh xạ, 0.50 lot |
| TEST-02 | Copy khác chiều, cùng dữ liệu | Client SELL, 0.50 lot |
| TEST-03 | Master đóng một lệnh | Chỉ đóng đúng Client ticket cùng Pair ID |
| TEST-04 | Client đóng, công tắc TẮT | Master giữ nguyên, cảnh báo mất hedge |
| TEST-05 | Client đóng, công tắc BẬT | Master đóng đúng cặp, không vòng lặp |
| TEST-06 | Đóng một phần: Master 1.00 / Client 0.50, Master đóng 25% | Client đóng 25% volume của Client, chuẩn hoá theo step |
| TEST-07 | Ba lệnh cùng symbol trên Master | Ba Pair ID, đóng một lệnh chỉ tác động một cặp |
| TEST-08 | Nhiều symbol đồng thời | Đủ mapping, đúng chiều, đúng volume |
| TEST-09 | Khởi động lại EA và Bridge | Không copy trùng, khôi phục đúng các Pair ID đang mở |
| TEST-10 | Client thiếu margin | Retry hoặc đóng Master theo chính sách, ghi lỗi và cảnh báo |
| TEST-11 | Volume tính ra dưới mức tối thiểu của sàn | Bỏ qua lệnh, cảnh báo, không tự nâng volume |
| TEST-12 | Đổi hệ số volume khi có cặp đang chạy | Cặp cũ giữ nguyên tỷ lệ, chỉ lệnh mới dùng hệ số mới |
| TEST-13 | Master và Client cùng đóng trong 50ms | Xử lý một lần, kết thúc `CLOSED`, không báo lỗi giả |
| TEST-14 | Close-by trên Master để lại phần dư | Hai cặp đóng đúng, phần dư báo `UNPAIRED_MASTER`, không tự copy |
| TEST-15 | Cascade, Master không phản hồi trong 15 giây | Không cascade, toàn bộ chuyển `ORPHANED`, alert CRITICAL |
| TEST-16 | Client đóng một phần, công tắc BẬT | Không cascade, chỉ cảnh báo lệch tỷ lệ |
| TEST-17 | Client offline khi Master mở lệnh, sau đó nối lại | Theo `offline_reopen_policy`, mặc định không mở bù |
| TEST-18 | Terminal mất kết nối broker nhưng EA vẫn sống | Trạng thái `DEGRADED`, ngừng gửi command, alert ERROR |
| TEST-19 | Mất điện đột ngột máy Bridge | Sau khởi động lại: không mất event, đối chiếu bắt đúng sai lệch |
| TEST-20 | Symbol trong mapping không tồn tại trên sàn Client | Không lưu được cấu hình, không có lệnh nào bị gửi |
| TEST-21 | Nút đóng khẩn cấp | Đóng hết cặp đang quản lý, Client trước Master sau |
| TEST-22 | `PAUSE_NEW_ENTRIES` | Không copy lệnh mới, vẫn đồng bộ đóng cặp đang chạy |
| TEST-23 | **Mọi vị thế do bot mở trên Client** | `DEAL_REASON == CLIENT` cho **tất cả**, không trừ cái nào. Kiểm tra **tự động** bằng truy vấn lịch sử deal, không nhìn bằng mắt |
| TEST-24 | Clicker mất khả năng điều khiển giao diện | Bridge chuyển `DEGRADED`, ngừng gửi `OPEN_UI`, alert ERROR, **không** rơi về đường EA |
| TEST-25 | Giết clicker giữa lúc giữ chỗ và bấm, rồi gửi lại cùng `command_id` | Không có lệnh thứ hai, ack `unknown`, alert CRITICAL |

TEST-19 phải thực hiện bằng cách **rút điện thật hoặc tắt máy ảo đột ngột**, không phải
dừng dịch vụ êm. Đây là lý do `synchronous = FULL` tồn tại.

---

## Kiểm tra lại phần cũ

- [ ] **Chạy toàn bộ test tự động của mọi phase từ 1 đến 9.** Tất cả phải xanh.
- [ ] Chạy lại kịch bản hỗn loạn của phase 8 sau khi đã đóng gói thành dịch vụ.
- [ ] Đọc lại `docs/DECISIONS.md` và đối chiếu từng mục D-01…D-20 với code thực tế.
      Bất kỳ chỗ nào lệch: hoặc sửa code, hoặc ghi rõ vào `PROGRESS.md` lý do lệch và
      cập nhật quyết định. **Không để lệch âm thầm.**
- [ ] Kiểm tra `PROGRESS.md`: mọi mục "vấn đề còn treo" từ các phase trước đã được xử lý
      hoặc chuyển thành hạng mục v2 có ghi chép.

## Kiểm tra phần mới

- [ ] Dịch vụ tự khởi động sau khi restart Windows, và khởi động ở `PAUSED`.
- [ ] Giết tiến trình Bridge → dịch vụ tự bật lại, vẫn ở `PAUSED`.
- [ ] Port 8787 và 8080 không truy cập được từ ngoài Tailscale (kiểm tra bằng máy thứ ba).
- [ ] Thu hồi token của một agent → agent đó không kết nối được nữa.
- [ ] `grep -ri "token" logs/` không lộ giá trị thô.
- [ ] Sao lưu tự động chạy, và bản sao lưu khôi phục được, mở được, đủ dữ liệu.
- [ ] Retention chạy, event cũ vào archive, `pair` không bị xoá dòng nào.
- [ ] Telegram nhận được alert CRITICAL trong vòng vài giây.
- [ ] Chặn mạng tới Telegram → luồng giao dịch không bị chậm hay lỗi.
- [ ] 24 giờ liên tục: bộ nhớ không tăng đều, file WAL không phình vô hạn.
- [ ] 5 Client mô phỏng: mở một lệnh Master → 5 pair, đóng Master → cả 5 đóng.
- [ ] Toàn bộ 25 mục nghiệm thu ở trên đạt, có ghi chép trong `docs/ACCEPTANCE.md`.
- [ ] **Bộ migration đã được chạy thật ít nhất một lần trên database có dữ liệu.** Tới phase 6b
      nó vẫn chưa từng chạy quá version 1 — đây là rủi ro phải đóng trước khi dữ liệu trở nên quý.

---

## Trước khi chuyển sang tài khoản thật

Đây không phải checklist kỹ thuật mà là điều kiện vận hành. Ghi vào `RUNBOOK.md`:

- Phần mềm phải chạy ổn định trên demo ít nhất một tuần liên tục trước khi động vào tiền thật.
- Kiểm tra điều khoản của **cả hai broker** về hedging, bonus, giao dịch nhiều tài khoản
  và copy trading. Một số broker cấm hoặc huỷ lợi nhuận từ các mô hình này.
- Đối chiếu bằng tay các khác biệt giữa hai sàn: tên symbol, contract size, volume tối thiểu
  và bước volume, spread và giá báo, thời gian khớp lệnh, giờ giao dịch của từng symbol.
- Bắt đầu bằng volume nhỏ nhất có thể và một symbol duy nhất. Mở rộng dần sau khi quan sát
  ít nhất vài chục lệnh.
- Người vận hành phải biết cách bấm dừng khẩn cấp **trước khi** cần dùng tới nó.

## Các hạng mục để lại cho v2

Ghi vào `docs/BACKLOG.md`, không làm ở lần này:

- Nhiều Client thật trên giao diện: cấu hình riêng từng Client, so sánh chéo, chính sách theo nhóm.
- Copy Pending Order và đồng bộ sửa SL/TP.
- Hỗ trợ tài khoản Netting.
- Tự động copy phần dư sau close-by, sau khi đã có dữ liệu thực tế về hành vi của broker.
- Cascade cho đóng một phần từ phía Client.
- Quy đổi volume theo tick value thay vì contract size.
- Phân quyền nhiều người vận hành và nhật ký ai đổi gì lúc nào.
