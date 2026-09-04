# Các quyết định đã chốt

File này là **hợp đồng**. Khi lập trình mà thấy mâu thuẫn với một quyết định ở đây, quay lại
đọc file này trước. Không tự ý đổi. Nếu phát hiện một quyết định không khả thi khi lập trình,
**dừng lại và báo cáo** thay vì tự chọn hướng khác.

Nếu code và file này lệch nhau, mặc định là **sửa code, không sửa tài liệu**. Chỉ sửa tài liệu
khi đã có quyết định tường minh của người chủ dự án, và khi đó phải ghi lý do vào `PROGRESS.md`.

---

## Bảng gốc (nguyên văn từ `plan/00-README.md` mục 4)

| # | Quyết định |
|---|---|
| D-01 | EA mỏng bằng MQL5 + Bridge bằng Python. Logic nằm hết ở Bridge. |
| D-02 | Truyền tin bằng NDJSON trên TCP. Mỗi message một dòng kết thúc bằng `\n`. |
| D-03 | Bridge là TCP server, EA là TCP client. MQL5 không listen được. |
| D-04 | Database là SQLite chạy cục bộ trên máy Bridge, bật WAL, `synchronous=FULL`. |
| D-05 | Không dùng cloud database. Xem từ xa bằng cách vào dashboard qua Tailscale. |
| D-06 | Khoá định danh vị thế là `POSITION_IDENTIFIER`, không phải ticket. |
| D-07 | Lệnh do bot mở phải mang magic number cố định. Không dựa vào trường comment. |
| D-08 | Chống vòng lặp đóng bằng `caused_by_command_id` trên sự kiện, không bằng cờ trạng thái. |
| D-09 | Client đóng hoàn toàn (cờ bật) → đóng Master → **chờ xác nhận** → mới cascade sang các Client khác. |
| D-10 | Timeout chờ Master xác nhận trước khi cascade: cấu hình được, mặc định 15000ms. Hết hạn thì KHÔNG cascade. |
| D-11 | Client đóng **một phần** thì KHÔNG cascade. Chỉ cascade khi đóng hoàn toàn. |
| D-12 | Close-by (`DEAL_ENTRY_OUT_BY`): đóng đúng 2 pair theo position_id, chạy đối chiếu ngay, phần dư thì cảnh báo và KHÔNG tự copy. |
| D-13 | Luật cứng: hệ thống được tự động **ĐÓNG**, không được tự động **MỞ**. Mở bù chỉ khi có người bấm. |
| D-14 | Sự kiện chỉ là tín hiệu kích hoạt. Trạng thái sau sự kiện (`volume_after`) do EA báo, Bridge không tự suy diễn bằng phép trừ. |
| D-15 | Bridge khởi động ở chế độ `PAUSED`. Không có đường tự động chuyển sang `RUNNING`. |
| D-16 | Enum trong DB, log và message dùng tiếng Anh không dấu. Tiếng Việt chỉ ở tầng hiển thị, qua một file nhãn duy nhất. |
| D-17 | Giữ 30 ngày dữ liệu event/command trong SQLite nóng, cũ hơn thì xuất sang file archive. Không bao giờ xoá `pair` và `master_position` theo thời gian. |
| D-18 | Làm tròn volume mặc định là làm tròn **xuống**. Nếu kết quả dưới mức tối thiểu của sàn thì **bỏ qua lệnh và cảnh báo**, không tự nâng volume. |
| D-19 | `effective_multiplier` (tỷ lệ thực tế sau làm tròn) được khoá tại thời điểm mở cặp và dùng cho mọi phép tính đóng một phần về sau. |
| D-20 | Cờ `can_close_master` đặt theo từng Client, mặc định TẮT. |

---

## Diễn giải từng quyết định

### D-01 — EA mỏng bằng MQL5 + Bridge bằng Python. Logic nằm hết ở Bridge.

**Lý do:** MQL5 khó test tự động, khó gỡ lỗi và phải biên dịch lại mỗi lần sửa. Gom logic về
Python cho phép viết test không cần MT5 và sửa quy tắc nghiệp vụ mà không đụng tới terminal.
Ngoại lệ duy nhất: EA tự chọn filling mode theo `SYMBOL_FILLING_MODE`, vì đó là chi tiết kỹ thuật
của broker chứ không phải quy tắc nghiệp vụ.

### D-02 — Truyền tin bằng NDJSON trên TCP. Mỗi message một dòng kết thúc bằng `\n`.

**Lý do:** JSON hợp lệ luôn escape newline thành hai ký tự `\` và `n`, nên byte `0x0A` thô không
bao giờ xuất hiện giữa một message. Khung dòng vì thế an toàn tuyệt đối mà không cần thêm header
độ dài, và đọc log bằng mắt được.

### D-03 — Bridge là TCP server, EA là TCP client.

**Lý do:** MQL5 không có API listen — chỉ `SocketConnect` ra ngoài. Chiều kết nối do ngôn ngữ
quyết định, không phải do lựa chọn thiết kế.

### D-04 — Database là SQLite cục bộ trên máy Bridge, bật WAL, `synchronous=FULL`.

**Lý do:** WAL cho phép đọc (dashboard) song song với ghi (engine). `synchronous = FULL` chậm hơn
`NORMAL` nhưng đảm bảo giao dịch đã commit sống sót qua mất điện đột ngột. Đây là tiền thật,
không đánh đổi độ bền lấy tốc độ.

### D-05 — Không dùng cloud database. Xem từ xa qua dashboard trên Tailscale.

**Lý do:** Đúng lúc mất mạng là lúc cần nhìn thấy trạng thái nhất. Dữ liệu nằm cùng máy với Bridge
thì dashboard vẫn hoạt động đầy đủ khi rớt Internet.

### D-06 — Khoá định danh vị thế là `POSITION_IDENTIFIER`, không phải ticket.

**Lý do:** Ticket của vị thế có thể đổi sau các thao tác của broker; `POSITION_IDENTIFIER` thì
bền suốt vòng đời vị thế. Dùng ticket làm khoá là cách mất dấu vị thế giữa chừng.

### D-07 — Lệnh do bot mở phải mang magic number cố định. Không dựa vào comment.

**Lý do:** Nhiều broker cắt, sửa hoặc xoá hẳn trường comment. Magic number thì không bị đụng tới
và là cách duy nhất tin được để phân biệt lệnh của bot với lệnh mở tay (FR-12).

### D-08 — Chống vòng lặp đóng bằng `caused_by_command_id` trên sự kiện, không bằng cờ trạng thái.

**Lý do:** Cờ trạng thái là dữ liệu toàn cục có vòng đời riêng — quên xoá, xoá sớm, hoặc mất khi
khởi động lại đều dẫn tới vòng lặp hoặc kẹt cứng. Gắn nguyên nhân vào chính sự kiện thì thông tin
đi kèm sự kiện, không phụ thuộc thứ tự và sống sót qua khởi động lại.

### D-09 — Client đóng hoàn toàn (cờ bật) → đóng Master → chờ xác nhận → mới cascade.

**Lý do:** Nếu Master từ chối lệnh đóng (requote liên tục, thị trường đóng cửa, mất kết nối) mà
ta đã đóng các Client còn lại rồi, thì cả nhóm mất hedge trong khi Master vẫn còn vị thế.
Đóng trước hỏi sau ở đây là sai.

### D-10 — Timeout chờ Master xác nhận: cấu hình được, mặc định 15000ms. Hết hạn thì KHÔNG cascade.

**Lý do:** Chờ vô hạn thì hệ thống treo im lặng; cascade khi hết hạn thì đúng vào tình huống
Master có vấn đề lại đi bỏ hedge. Hết hạn thì chuyển `ORPHANED` và gọi người — đây là quyết định
tiền bạc, không phải quyết định của máy.

### D-11 — Client đóng một phần thì KHÔNG cascade.

**Lý do:** Đóng một phần từ phía Client là thao tác chỉnh tỷ lệ, không phải tín hiệu thoát vị thế.
Suy diễn thành "đóng một phần Master" là tự ra một quyết định giao dịch thay người dùng.
Để lại cho v2 sau khi có dữ liệu thực tế.

### D-12 — Close-by: đóng đúng 2 pair theo position_id, đối chiếu ngay, phần dư chỉ cảnh báo.

**Lý do:** Hành vi của broker với phần dư không thống nhất giữa các build — có nơi tạo vị thế mới,
có nơi đóng một phần vị thế lớn. Tự copy phần dư dựa trên phỏng đoán là mở lệnh không ai yêu cầu,
vi phạm D-13.

### D-13 — Được tự động ĐÓNG, không được tự động MỞ.

**Lý do:** Đóng làm giảm phơi nhiễm, mở làm tăng. Khi không chắc chuyện gì đã xảy ra, hành động
an toàn luôn là đóng hoặc dừng lại chờ người. Đây là luật cứng xuyên suốt mọi phase; ngoại lệ
duy nhất là nút "Tạo cặp và copy" ở màn hình xử lý sai lệch, nơi có người nhìn bằng chứng và
bấm — tức là không tự động.

### D-14 — Sự kiện là tín hiệu kích hoạt. `volume_after` do EA báo, Bridge không suy diễn bằng phép trừ.

**Lý do:** Phép trừ chỉ đúng khi không có sự kiện nào bị mất, bị trùng hay tới sai thứ tự — tức là
đúng khi mọi thứ đã ổn, và sai đúng lúc cần nhất. EA đọc được trạng thái thật của vị thế, nên
để EA báo con số thật.

### D-15 — Bridge khởi động ở chế độ `PAUSED`. Không có đường tự động sang `RUNNING`.

**Lý do:** Sau một sự cố, thứ tệ nhất là hệ thống tự hồi sinh và bắt đầu vào lệnh trong khi chưa
ai kịp nhìn màn hình. Kể cả khi máy restart lúc 3 giờ sáng cũng không có ngoại lệ.

### D-16 — Enum trong DB, log và message dùng tiếng Anh không dấu. Tiếng Việt chỉ ở tầng hiển thị.

**Lý do:** Enum có dấu gây rắc rối với encoding, so sánh chuỗi, `grep` và SQL. Gom toàn bộ tiếng
Việt vào một file nhãn duy nhất (`bridge/labels_vi.py`) thì sửa cách gọi tên không phải đụng vào
logic, và thiếu một nhãn không làm sập dashboard.

### D-17 — Giữ 30 ngày event/command trong DB nóng. Không bao giờ xoá `pair` và `master_position` theo thời gian.

**Lý do:** `event` và `command` tăng nhanh và chỉ có giá trị điều tra ngắn hạn, nên xuất ra archive
được. `pair` và `master_position` là sổ sách của vị thế — xoá theo thời gian là mất khả năng đối
chiếu với một vị thế còn đang mở nhiều tháng.

### D-18 — Làm tròn volume mặc định là làm tròn **xuống**. Dưới mức tối thiểu thì bỏ qua lệnh và cảnh báo.

**Lý do:** Làm tròn lên hoặc tự nâng lên mức tối thiểu là tự tăng phơi nhiễu vượt ý muốn của người
dùng. Hedge thiếu một chút thì thấy được và sửa được; hedge thừa thì là một vị thế không ai yêu cầu.

### D-19 — `effective_multiplier` khoá tại thời điểm mở cặp, dùng cho mọi phép tính đóng một phần.

**Lý do:** Người vận hành đổi hệ số giữa chừng không được làm lệch các cặp đang chạy (FR-06).
Tỷ lệ thật sau làm tròn cũng khác hệ số cấu hình — ví dụ Master 0.07 với hệ số 0.33 cho Client 0.02,
tức tỷ lệ thật là 0.2857. Dùng 0.33 để tính đóng một phần sẽ sai dần theo từng lần đóng.

### D-20 — Cờ `can_close_master` đặt theo từng Client, mặc định TẮT.

**Lý do:** Chiều copy chính thức là Master → Client. Cho Client đóng ngược Master là mở đường
cascade tới mọi Client khác, nên phải là lựa chọn có ý thức của từng Client, không phải mặc định.
