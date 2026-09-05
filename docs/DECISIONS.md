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
| D-07 | *(bản 1, đã thay bằng D-07b)* Lệnh do bot mở phải mang magic number cố định. Không dựa vào trường comment. |
| D-07b | Trên **Master**, lệnh của bot mang magic cố định. Trên **Client**, lệnh MỞ đi qua giao diện nên `magic = 0` và không đặt được. Định danh "lệnh của bot" phía Client là **sự tồn tại của `(client_id, client_position_id)` trong bảng `pair`**. Comment chỉ là thẻ tương quan tạm thời, dùng một lần trong cửa sổ chờ khớp lệnh, không bao giờ là nguồn sự thật lâu dài. |
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
| D-21 | Lệnh **MỞ** phía Client đi qua giao diện MT5 để mang `DEAL_REASON_CLIENT`. Đường **ĐÓNG** vẫn dùng `OrderSend` của EA. |
| D-22 | Kênh mở lệnh là tiến trình riêng `clicker`, cùng giao thức NDJSON/TCP, role `CLICKER`, token riêng. Loại command riêng `OPEN_UI` để EA không thể lặng lẽ đặt lệnh `EXPERT` khi định tuyến sai. |
| D-23 | `position_id` của vị thế Client xác định bằng **tương quan tại Bridge** giữa `OPEN_UI` và event `position_opened` của EA. Event của EA là nguồn sự thật, ack của clicker là thông tin phụ. Nhiều ứng viên thì KHÔNG đoán. |
| D-24 | Trên đường giao diện, **chỉ `rejected`** (chứng minh được là chưa bấm nút gửi) mới được retry. `failed` và `unknown` không bao giờ retry tự động. |
| D-25 | Không gửi `OPEN_UI` cho clicker chưa chứng minh được nó điều khiển được giao diện. Clicker `DEGRADED` thì **không copy**, không tự rơi về đường EA. |
| D-26 | Mở lệnh qua **hộp thoại New Order**, không dùng One Click Trading. OCT không có ô Comment, mà thẻ trong comment là cơ chế tương quan duy nhất (D-07b, D-23). Ô volume phải ghi bằng `WM_CHAR`, không phải `WM_SETTEXT`. |

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

### D-07b — Sửa đổi phạm vi ở phase 6b

**Nội dung:** Trên **Master**, D-07 giữ nguyên. Trên **Client**, lệnh MỞ đi qua giao diện MT5
(D-21) nên `magic = 0` và không đặt được — hộp thoại New Order không có ô magic. Định danh
"lệnh của bot" phía Client chuyển thành **sự tồn tại của `(client_id, client_position_id)` trong
bảng `pair`**. Comment chỉ là **thẻ tương quan tạm thời**, tiêu thụ một lần trong cửa sổ chờ khớp
lệnh rồi vứt.

**Vì sao đây không phải là vi phạm bản 1.** Lệnh cấm ban đầu là *"đừng dựa vào comment"*, vì sàn
có thể cắt, sửa hoặc xoá nó. Bản 2 không dựa vào comment: comment được dùng một lần rồi thay
ngay bằng `position_id` bền vững (D-06). Nếu sàn phá comment thì tương quan thất bại **ồn ào**
(`unknown` + alert CRITICAL) chứ không âm thầm ghép sai. Đó là khác biệt giữa "dựa vào comment"
và "dùng comment như một gợi ý có kiểm chứng".

**Rủi ro đã biết, phải ghi ra chứ không để trong đầu ai đó.** Bỏ magic phía Client có nghĩa là
một vị thế của bot bị mất dấu hoàn toàn — sàn xoá comment **và** mất ack **và** mất event — sẽ bị
phân loại nhầm thành lệnh người dùng mở tay và không được đối chiếu. Đó là cái giá phải trả.

**Đã đo trên Connext-Demo (phase 6b):** comment gửi qua `OrderSend` sống sót nguyên vẹn trong
`DEAL_COMMENT`, không cắt, không bị chèn thêm chữ. Nên trên sàn này khớp theo thẻ là đường chính
và suy đoán chỉ là lưới an toàn. **Con số này phải đo lại nếu đổi sàn.**

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

### D-21 — Lệnh MỞ phía Client đi qua giao diện MT5

**Lý do:** `DEAL_REASON` do máy chủ broker gán theo *kênh* gửi lệnh. `MqlTradeRequest` không có
trường `reason` và MQL5 không có API nào đặt được nó, nên mọi lệnh do `OrderSend()` gửi đều là
`EXPERT`. Muốn ra `CLIENT` thì phải đổi kênh chứ không phải đổi tham số.

Đường ĐÓNG giữ nguyên `OrderSend` vì đóng phải nhắm đúng một `position_id` và phải đóng được một
phần theo volume chính xác (D-06, FR-11, FR-17) — những thứ giao diện làm rất tệ. Hệ quả đã chấp
nhận: deal đóng vẫn mang `EXPERT`, còn `POSITION_REASON` thì lấy từ deal mở nên vẫn là `CLIENT`.

### D-22 — Clicker là tiến trình riêng, và `OPEN_UI` là loại command riêng

**Lý do tách tiến trình:** MQL5 không tự động hoá được giao diện nếu không import DLL, mà điều đó
bị cấm ở mục 7 của `plan/00-README.md`. Bridge lại có thể nằm ở máy khác với terminal Client.

**Lý do tách loại command:** nếu định tuyến sai mà EA nhận `OPEN`, nó sẽ **lặng lẽ đặt lệnh
`EXPERT`** — đúng thứ D-21 tồn tại để làm cho bất khả thi. Với `OPEN_UI`, EA trả `rejected`.
Payload `OPEN_UI` cũng cố ý không có `magic` nên `Guard()` của EA chặn thêm một lớp độc lập.

### D-23 — `position_id` xác định bằng tương quan tại Bridge

**Lý do:** giao diện không trả về giá trị nào. Nhưng EA vẫn chạy trên terminal Client và
`OnTradeTransaction` báo mọi deal kèm `POSITION_IDENTIFIER` thật trong 11–21ms. Không cần giao
diện trả về gì — dùng chính event của EA làm đường về.

**Event của EA là nguồn sự thật; ack của clicker là thông tin phụ.** Ack `ok` chỉ nói "tôi đã
bấm", không nói "vị thế nào". Thiết kế không được phụ thuộc vào thứ tự đến của ack và event.

Nhiều ứng viên cùng khớp thì **không đoán**: alert CRITICAL và chờ người. Đoán sai ở đây nghĩa là
gắn vị thế của người dùng vào một cặp, rồi phase 7 sẽ đóng nó.

### D-24 — Trên đường giao diện, chỉ `rejected` mới được retry

**Lý do:** không có giá trị trả về nên "thất bại" và "không biết" rất khó phân biệt. Retry một
lệnh mà không chắc đã gửi hay chưa là mở lệnh thứ hai với xác suất khác không.

`rejected` có nghĩa hẹp và phải **chứng minh được**: clicker đọc ngược các trường từ hộp thoại
trước khi bấm, thấy lệch thì huỷ. Mọi trường hợp còn lại là `unknown`.

### D-25 — Không gửi lệnh cho clicker chưa chứng minh còn điều khiển được giao diện

**Lý do:** đây là bài học của mục 8.1 áp dụng lại. Thứ nguy hiểm nhất không phải thành phần đã
chết, mà là thành phần **trông vẫn khoẻ** trong khi đã mất khả năng làm việc. Clicker vẫn giữ
được kết nối TCP và vẫn gửi heartbeat đều trong khi cửa sổ MT5 đã đóng.

Clicker chạy canary định kỳ và báo kết quả qua `broker_connected`; hỏng thì `DEGRADED` và luồng
mở lệnh bỏ qua Client đó.

**Không tự rơi về đường EA khi clicker hỏng** — làm vậy là lặng lẽ vi phạm chính D-21. Thà không
copy: không copy thì thấy được và sửa được, copy sai kênh thì không ai biết cho tới khi quá muộn.


### D-26 — Hộp thoại New Order, không phải One Click Trading

**Lý do:** câu hỏi "sao không dùng OCT cho nhanh" là câu hỏi đúng, và OCT thật sự nhanh hơn —
nó là bảng nằm sẵn trên chart, không phải mở rồi đóng hộp thoại mỗi lệnh. Ghi lại ở đây vì câu
trả lời không hiển nhiên nếu chỉ nhìn code, và sẽ có người hỏi lại.

**Bảng OCT không có ô Comment.** Chỉ có volume, SELL, BUY. Một mình điều này đã đủ để loại:
thẻ trong comment là toàn bộ cơ chế tương quan của D-07b và D-23. Không có thẻ thì
`ui_fallback_match = STRICT` không bao giờ ghép được — mọi pair kẹt `PENDING_OPEN` — còn
`HEURISTIC` thì ghép bằng (symbol, chiều, volume), tức là **không phân biệt được lệnh của bot
với lệnh người dùng tự mở** cùng thông số trên cùng tài khoản. Ghép nhầm nghĩa là phase 7 sẽ
đóng vị thế của chính người dùng.

Hai lý do phụ, cùng chiều. Đo trên terminal thật: chart có một `Edit` ẩn 106×20 giống ô volume
của OCT, nhưng **không có `Button` nào thuộc chart** — nhiều khả năng BUY/SELL được vẽ trên
canvas, phải bấm theo toạ độ pixel, mong manh với DPI, theme và kích thước chart. Và OCT không
đọc lại được, trong khi bài học đắt nhất của phase này là *chữ hiển thị khác giá trị MT5 dùng*.

Đổi lại chỉ được tốc độ, mà tốc độ đang dư: đo được 511 ms cho một chu kỳ mở lệnh, tức khoảng
một lệnh mỗi giây cho mỗi Client — thừa cho mọi kịch bản copy trong phạm vi dự án.

**Phần thứ hai của quyết định này quan trọng ngang phần thứ nhất:** ô volume phải ghi bằng
`WM_CHAR` gõ từng ký tự. `WM_SETTEXT` đổi chữ hiển thị nhưng **không** cập nhật trạng thái nội
bộ của MT5, và lệnh gửi đi mang volume cũ. Tệ hơn nữa, MT5 giữ volume nội bộ qua các lần mở hộp
thoại, nên lỗi này gửi đi kích thước của **lệnh trước** chứ không phải một giá trị mặc định dễ
nhận ra. Đo ngày 2026-09-05: yêu cầu 0.02 nhưng gửi đi 0.01; yêu cầu 0.06 nhưng gửi đi 0.04 của
lệnh liền trước. Xem `clicker/ui/win32.py::type_text()`.
