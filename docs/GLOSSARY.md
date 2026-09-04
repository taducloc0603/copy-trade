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
- **Unpaired** — vị thế tồn tại thật trên terminal nhưng không thuộc pair nào trong sổ sách.
