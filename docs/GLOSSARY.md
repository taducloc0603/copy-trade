# Thuật ngữ

Chép từ mục 5 của `plan/00-README.md`, bổ sung dần khi gặp thuật ngữ mới.

## Thuật ngữ gốc

- **Master** — tài khoản phát sinh lệnh gốc.
- **Client** — tài khoản nhận lệnh copy.
- **Agent** — tiến trình EA gắn vào một terminal MT5.
- **Bridge** — tiến trình Python trung tâm.
- **Pair** — liên kết giữa một vị thế Master và một vị thế Client.
  Một vị thế Master sinh ra N pair (N = số Client).
- **Event** — sự kiện giao dịch do agent báo lên.
- **Command** — yêu cầu Bridge gửi xuống agent để thực thi.
- **Cascade** — chuỗi đóng lan truyền: Client A đóng → Master đóng → các Client khác đóng.
- **Reconciliation** — đối chiếu giữa DB, vị thế thực trên Master và vị thế thực trên Client.
- **Orphaned** — cặp lệnh mà một bên còn vị thế nhưng bên kia không còn.

## Bổ sung

*(Thêm mục mới ở đây khi gặp thuật ngữ chưa có. Giữ thứ tự bảng chữ cái.)*

- **Pair ID** — mã cặp lệnh dạng `PAIR-YYYYMMDD-NNNNNN`, bộ đếm reset theo ngày.
  Cố ý không dùng UUID để đọc được bằng mắt trên dashboard và trong log.
- **`effective_multiplier`** — tỷ lệ volume **thực tế sau làm tròn** giữa Client và Master,
  khoá tại thời điểm mở cặp (D-19). Khác với `volume_multiplier` là hệ số cấu hình.
- **`caused_by_command_id`** — trường trên event, cho biết sự kiện này do chính bot gây ra
  (khác NULL) hay do người/broker gây ra (NULL). Là toàn bộ cơ chế chống vòng lặp (D-08).
- **DEGRADED** — agent còn sống và gửi heartbeat đều, nhưng terminal mất kết nối với broker
  (`broker_connected = false`). Nguy hiểm nhất vì nhìn từ ngoài hệ thống có vẻ vẫn khoẻ.
- **Finding** — một dòng sai lệch do đối chiếu phát hiện, lưu ở bảng `reconcile_finding`.
  Chia hai mức: `SAFE` (khắc phục chỉ gồm đóng lệnh hoặc sửa sổ sách) và `DECISION`
  (dính tới mở lệnh hoặc đóng Master, phải có người quyết định).
- **`POSITION_IDENTIFIER`** — định danh vị thế bền suốt vòng đời trong MT5. Đây là khoá dùng
  trong toàn hệ thống, **không phải** ticket (D-06).
- **`run_mode`** — chế độ vận hành của Bridge: `RUNNING`, `PAUSE_NEW_ENTRIES`, `PAUSED`,
  `EMERGENCY`. Khởi động luôn ở `PAUSED` (D-15).
- **Clicker** — tiến trình Python chạy cạnh terminal Client, **mở và đóng** lệnh bằng cách điều
  khiển giao diện MT5 để deal mang `DEAL_REASON_CLIENT` thay vì `DEAL_REASON_EXPERT` (D-21,
  D-21b).
- **`DEAL_REASON`** — trường do **máy chủ broker** gán cho mỗi deal, cho biết lệnh đi vào
  bằng kênh nào: `CLIENT` (terminal desktop), `EXPERT` (chương trình MQL5), `SL`, `TP`, `SO`…
  Không đặt được từ MQL5.
- **Thẻ tương quan** — chuỗi ngắn dạng `CB<hậu tố command_id>` mà Bridge sinh cho mỗi lệnh mở
  qua giao diện. Clicker gõ vào ô Comment, EA đọc lại và báo lên, Bridge dùng để ghép vị thế
  với cặp lệnh. Dùng **một lần** rồi vứt — không phải nguồn sự thật lâu dài (D-07b).
- **Unpaired** — vị thế tồn tại thật trên terminal nhưng không thuộc pair nào trong sổ sách.
- **Probe khô** — mở hộp thoại New Order, đọc lại các ô, bấm ESC. Chứng minh toàn tuyến điều
  khiển giao diện còn sống mà **không đặt lệnh nào**. Hiện **chưa được nối vào canary**: canary
  chạy mỗi giây, mà probe khô mở rồi đóng một hộp thoại thật (xem `BACKLOG.md`).
- **`commit()`** — hàm duy nhất dẫn tới nút gửi lệnh của clicker. Điền → đọc lại → so → lệch thì
  huỷ. Nó là **ranh giới giữa `rejected` và `unknown`**: trước nó, "chưa bấm" là sự thật chứng
  minh được nên được retry; sau nó thì không còn gì chứng minh được nữa (D-24).
- **`open_route`** — cột trên `client_account`: `EA` thì lệnh mở đi bằng `OrderSend`, `UI` thì đi
  qua giao diện MT5 (D-21). Clicker hỏng **không** làm nó tự rơi về `EA` (D-25).
- **`close_route`** — cột song song, cho lệnh **đóng** (D-21b). Mặc định `EA`; bật `UI` thì lệnh
  đóng đi qua giao diện. Khác `open_route` ở một điểm quan trọng: clicker hỏng thì nó **được** rơi
  về `EA` kèm alert CRITICAL (D-28) — không mở được thì an toàn, không đóng được thì không.
- **`CLOSE_UI` / `CLOSE_UI_PARTIAL`** — hai loại command đóng qua giao diện. Tách đôi chứ không
  dùng một loại với `volume` tuỳ chọn: một lệnh đóng một phần rơi mất `volume` mà vẫn chạy sẽ
  thành **đóng hẳn** trong im lặng.
- **Phép tìm có kiểm chứng** — cách nhắm một vị thế khi danh sách vị thế không đọc được nội dung:
  mở hộp thoại đóng theo từng dòng, đọc ngược ticket, sai thì huỷ rồi thử dòng khác (D-30). An
  toàn vì mở và huỷ hộp thoại **không đặt lệnh nào**.
