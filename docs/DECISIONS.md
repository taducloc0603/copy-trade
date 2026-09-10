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
| D-19 | *(sửa ở phase 11)* Đóng một phần lấy **tỷ lệ trên volume còn lại của hai bên tại thời điểm đóng**, không nhân lại từ hệ số cấu hình. `effective_multiplier` vẫn khoá lúc mở cặp nhưng dùng cho **đối chiếu**, không dùng cho phép tính đóng. |
| D-20 | Cờ `can_close_master` đặt theo từng Client, mặc định TẮT. |
| D-21 | Lệnh **MỞ** phía Client đi qua giao diện MT5 để mang `DEAL_REASON_CLIENT`. Đường **ĐÓNG** vẫn dùng `OrderSend` của EA. |
| D-22 | Kênh mở lệnh là tiến trình riêng `clicker`, cùng giao thức NDJSON/TCP, role `CLICKER`, token riêng. Loại command riêng `OPEN_UI` để EA không thể lặng lẽ đặt lệnh `EXPERT` khi định tuyến sai. |
| D-23 | `position_id` của vị thế Client xác định bằng **tương quan tại Bridge** giữa `OPEN_UI` và event `position_opened` của EA. Event của EA là nguồn sự thật, ack của clicker là thông tin phụ. Nhiều ứng viên thì KHÔNG đoán. |
| D-24 | Trên đường giao diện, **chỉ `rejected`** (chứng minh được là chưa bấm nút gửi) mới được retry. `failed` và `unknown` không bao giờ retry tự động. |
| D-25 | Không gửi `OPEN_UI` cho clicker chưa chứng minh được nó điều khiển được giao diện. Clicker `DEGRADED` thì **không copy**, không tự rơi về đường EA. |
| D-26 | Mở lệnh qua **hộp thoại New Order**, không dùng One Click Trading. OCT không có ô Comment, mà thẻ trong comment là cơ chế tương quan duy nhất (D-07b, D-23). Ô volume phải ghi bằng `WM_CHAR`, không phải `WM_SETTEXT`. |
| D-21b | Lệnh **ĐÓNG** phía Client cũng đi qua giao diện (`close_route = 'UI'`). D-21 giữ nguyên tinh thần — đổi kênh chứ không đổi tham số — nhưng phạm vi mở rộng sang deal đóng, vì bên kiểm tra nhìn cả `entry = OUT`. |
| D-27 | Tương quan đóng làm tại Bridge bằng **cửa sổ command đang bay**, không bằng thẻ trong comment: hộp thoại đóng không có ô Comment. Thiếu nó thì mọi lệnh đóng của bot tự kích hoạt cascade. |
| D-28 | Clicker hỏng thì đường đóng **được** rơi về `OrderSend` của EA (`close_degraded_fallback = EA`), ngược với D-25, kèm alert CRITICAL. Không mở được thì an toàn; không đóng được thì không. |
| D-29 | Phía **Master** giữ nguyên `OrderSend`. Chỉ tài khoản Client bị soi `DEAL_REASON`. |
| D-30 | Danh sách vị thế **không đọc được nội dung**. Nhắm một vị thế là **phép tìm có kiểm chứng**: mở hộp thoại theo dòng, đọc ngược ticket, sai thì huỷ rồi thử dòng khác. Mở và huỷ không đặt lệnh nào. |

---

## Diễn giải từng quyết định

### D-01 — EA mỏng bằng MQL5 + Bridge bằng Python. Logic nằm hết ở Bridge.

**Lý do:** MQL5 khó test tự động, khó gỡ lỗi và phải biên dịch lại mỗi lần sửa. Gom logic về
Python cho phép viết test không cần MT5 và sửa quy tắc nghiệp vụ mà không đụng tới terminal.
Ngoại lệ duy nhất: EA tự chọn filling mode theo `SYMBOL_FILLING_MODE`, vì đó là chi tiết kỹ thuật
của broker chứ không phải quy tắc nghiệp vụ.

**Ranh giới quyền giao dịch, làm rõ ở phase 11.** Từ phase 5 tới phase 10, ranh giới là *"chỉ EA
Client được đặt lệnh"*, khoá bằng một test cấm `OrderSend` trong file Master và file dùng chung.
Ranh giới đó **mâu thuẫn với D-09 và TEST-21**, vốn đều đòi hỏi đóng được vị thế Master — và mâu
thuẫn này tồn tại suốt vì đường đóng Master chưa từng chạy đầu-cuối: kiểm toán 2026-09-06 đếm được
**0 lệnh đóng nào từng gửi cho Master** trong toàn bộ lịch sử database. Bấm nút dừng khẩn cấp trên
demo thì EA Master trả về `Command type not supported by this agent role`.

Ranh giới mới, tinh hơn: **EA Master được ĐÓNG, không bao giờ được MỞ.** Cụ thể là mọi `OrderSend`
trong code dùng chung đều phải đặt `request.position`, tức chỉ có thể đóng một vị thế đã tồn tại;
đường mở chỉ nằm trong `CopyBridgeClient.mq5`; và `CMasterAgent::OnCommand` cố ý không nhận loại
`OPEN`. Cả ba điều được khoá bằng `test_chi_ea_client_duoc_MO_lenh`.

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

> **Bản 1, đã bị D-07b thu hẹp phạm vi ở phase 6b. Đọc cả hai mục.** Phần dưới đây chỉ còn đúng
> với **Master**. Với **Client**, câu "magic là cách duy nhất tin được" đã sai kể từ khi lệnh MỞ
> đi qua giao diện: vị thế mang `magic = 0`, và việc nhận dạng chuyển sang **sự tồn tại của
> `(client_id, client_position_id)` trong bảng `pair`**.

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

### D-19 — Đóng một phần lấy tỷ lệ trên volume **còn lại**; `effective_multiplier` dùng để đối chiếu.

**Bản 1 (phase 6 → 10):** *"`effective_multiplier` khoá tại thời điểm mở cặp và dùng cho **mọi**
phép tính đóng một phần."* Yêu cầu gốc vẫn đúng và không đổi: người vận hành đổi hệ số giữa chừng
không được làm lệch cặp đang chạy (FR-06), và hệ số cấu hình khác tỷ lệ thật sau làm tròn — Master
0.07 với hệ số 0.33 cho Client 0.02, tức tỷ lệ thật 0.2857.

**Sửa ở phase 11.** Kiểm toán 2026-09-06 phát hiện code **chưa bao giờ** làm theo chữ của bản 1:
`effective_multiplier` chỉ được *ghi* lúc mở cặp và được *đọc* đúng một chỗ là bộ đối chiếu, còn
`CloseFlow._close_pair_partially` tính bằng

```
ty_le   = master_delta / master_con_lai
can_dong = lam_tron_xuong(client_con_lai * ty_le)
```

Hai công thức trùng nhau khi không có làm tròn, nhưng khác nhau khi có. Bản đang chạy **đúng
hơn**: nó lấy tỷ lệ trên `client_current_volume` *thật*, nên phần dư do làm tròn xuống được thu
lại ở các lần đóng sau thay vì tồn tại vĩnh viễn. Mô phỏng Master 1.00 hệ số 0.5 step 0.01, đóng
0.25 ba lần: bản đang chạy để Client còn **0.130**, công thức theo chữ bản 1 để lại **0.140**,
lý tưởng là 0.125.

Vì bản 1 mô tả một cơ chế kém hơn cơ chế đang chạy, **quyết định được sửa theo code**, không phải
ngược lại. FR-06 vẫn được bảo đảm — mạnh hơn là khác: đường đóng không hề đọc `client_account`
nên hệ số cấu hình đổi giữa chừng **không có đường nào** chạm tới cặp đang chạy.

`effective_multiplier` giữ nguyên vai trò khoá-lúc-mở, dùng làm **kỳ vọng khi đối chiếu**
(`Reconciler._soi_lech_volume`). Vì làm tròn xuống luôn tạo lệch hợp lệ, dung sai ở đó phải tính
theo `volume_step` chứ không phải một epsilon.

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

### D-21b — Lệnh ĐÓNG phía Client cũng đi qua giao diện

**Lý do:** D-21 chốt đường mở đi qua giao diện và **cố ý** để đường đóng lại trên `OrderSend`, với
một lập luận cụ thể: bên kiểm tra chỉ nhìn vị thế / lệnh mở, mà `POSITION_REASON` lấy từ deal mở
nên vẫn là `CLIENT`. Lập luận ấy đúng với thứ biết được lúc đó, và hệ quả của nó đã được ghi thẳng
là một rủi ro treo: *"nếu sau này phát hiện bên kiểm tra nhìn cả deal đóng thì phạm vi phải mở
rộng đáng kể."*

Đã xảy ra. Nên D-21 **không bị xoá** — tinh thần của nó (`DEAL_REASON` đổi bằng đổi kênh, không
bằng đổi tham số) vẫn nguyên vẹn và nay áp cho cả hai đường. Cái đổi là **phạm vi**, đúng cách
D-07b đã thu hẹp D-07 chứ không lật nó.

Cái giá đã được trả đúng như dự đoán trong chính D-21: đóng phải nhắm đúng một `position_id` và
đóng được một phần theo volume chính xác — hai thứ giao diện làm rất tệ. Cách trả nằm ở D-30.

Bật theo từng Client bằng `close_route`, mặc định `EA`, vì nâng cấp không được tự đổi hành vi của
một Client đang chạy.

### D-27 — Tương quan đóng bằng cửa sổ command, không bằng thẻ comment

**Lý do:** đây là chỗ dễ mất tiền nhất của cả thay đổi, và nó không hiển nhiên.

Đường đóng qua EA có `RememberCause`: EA gọi `OrderSend` nên biết deal nào là con của command nào
và gắn `caused_by_command_id` (D-08). Đường đóng qua giao diện **không có gì tương đương** — EA
không gọi `OrderSend` nên không có gì để nhớ. Mẹo gắn thẻ của D-07b/D-23 cũng không dùng được:
**hộp thoại đóng không có ô Comment**.

Hệ quả nếu để nguyên: mọi event `position_closed` do chính bot phát ra về Bridge với
`caused_by_command_id = NULL`, tức mang **đúng dấu hiệu của một lệnh người dùng đóng tay**. Với
`can_close_master = 1`, mỗi lệnh đóng của bot sẽ tự kích hoạt một cascade đóng vị thế Master.

Cách bịt: Bridge tự nhận cha. Nó vừa gửi lệnh đóng cho đúng cặp ấy cách đây vài trăm mili giây,
nên event vừa về là con của lệnh đó. Cửa sổ `ui_close_correlate_grace_ms` mặc định 5000 — đủ rộng
cho một chu kỳ đóng đo được 0,3–3 giây, đủ hẹp để không nuốt nhầm một cú đóng tay ngay sau đó.

**Mơ hồ thì nhận cha, không cascade.** Ngược với D-23, nơi mơ hồ thì dừng lại chờ người. Lý do là
hai hướng sai không cân nhau: không cascade thì cùng lắm để lại một cặp `ORPHANED`, sửa được;
cascade nhầm thì đóng vị thế Master và không lấy lại được.

### D-28 — Clicker hỏng thì đường ĐÓNG được rơi về EA, ngược với D-25

**Lý do:** không phải nới lỏng D-25, mà là **hai tình huống khác nhau về hậu quả**.

* Không **mở** được thì an toàn. Bỏ một lệnh copy là mất một cơ hội — thấy được, sửa được.
* Không **đóng** được thì không an toàn. Master đã đóng mà Client còn đứng vị thế trần là phơi
  nhiễm tiền thật, và nó không tự hết.

Sự khác biệt ấy được diễn đạt bằng **cấu hình chứ không bằng lời bình luận**: hai khoá cạnh nhau
với hai mặc định ngược nhau, `ui_degraded_fallback = SKIP` và `close_degraded_fallback = EA`.

Cái giá **được ghi nhận chứ không được nuốt**: deal đóng lần ấy mang `EXPERT`, và nó đi kèm alert
CRITICAL `CLOSE_FELL_BACK_TO_EA` nói thẳng điều đó, cộng `pair.error_message` để dashboard thấy.

Đặt `SKIP` là chấp nhận giữ vị thế trần khi clicker hỏng. Đó phải là lựa chọn có ý thức.

### D-29 — Phía Master giữ `OrderSend`

**Lý do:** chỉ tài khoản **Client** bị soi `DEAL_REASON` — đó là tài khoản được copy tới. Master là
tài khoản của chính người chủ dự án. Đưa Master sang giao diện đồng nghĩa với dựng thêm một clicker
nữa cho terminal Master, tức tăng phạm vi và chi phí vận hành mà không đổi lấy điều gì.

Hệ quả cần nhớ khi đọc code: `_gui_lenh_dong_master()` và `_dang_dong_master()` **cố ý** không đi
qua nhánh định tuyến mới, và SQL của cái sau vẫn lọc `type = 'CLOSE'`.

### D-30 — Nhắm vị thế bằng phép tìm có kiểm chứng, không bằng phép đoán

**Lý do:** đo ngày 2026-09-10 trên tab Trade của MT5 build 5.00 — danh sách vị thế là
`SysListView32` **thật**, nhưng `LVM_GETITEMTEXT` chép về **0 ký tự**: MT5 tự vẽ từng dòng và không
giữ chuỗi trong control. Nên hình học đọc được (số dòng, hình chữ nhật từng dòng, chọn dòng theo
chỉ số) mà **nội dung thì không**. Nhắm một dòng là tất định; biết dòng đó là vị thế nào thì không.

Cái bù lại nằm ở hộp thoại: mở ra rồi thì ticket đọc được từ **ba nguồn độc lập** — tiêu đề cửa sổ,
chữ trên nút `Close #…`, và `WM_GETTEXT` của combo chọn vị thế. Nên trình tự là: mở dòng N, đọc
ngược ticket, sai thì ESC rồi thử dòng khác, đúng mới điền volume và bấm.

**Điều làm phép tìm này an toàn: mở và huỷ hộp thoại không đặt lệnh nào.** Mọi bước dò đều nằm ở
phía an toàn của ranh giới D-24, nên một lần dò trượt vẫn là `rejected` đúng nghĩa. Đây không phải
đoán rồi sửa sau — không có "sau".

Quét hết danh sách mà không thấy vị thế là `already_closed`, **không phải lỗi**: `LVM_GETITEMCOUNT`
đếm mọi dòng bất kể cuộn tới đâu, nên đó là bằng chứng vị thế không còn mở (FR-18).

Hai chi tiết đã trả giá để biết, ghi lại để không ai phải trả lần nữa:

* `WM_LBUTTONDBLCLK` phải gửi bằng **`SendMessage`**, và phải có `WM_LBUTTONDOWN` + `WM_LBUTTONUP`
  đi trước. Bản thiếu vẫn mở được **dòng đầu tiên** — đúng trường hợp người ta thử tay.
* Hộp thoại đóng mang **đủ cả bốn** control trong `SIGNATURE` của hộp thoại New Order, nên chữ ký
  một mình nó không phân biệt được hai chế độ. Thứ phân biệt được là control `10410` đang hiện với
  chữ bắt đầu bằng `"Close #"`, hoặc tiêu đề bắt đầu bằng `"Position: #"`.
