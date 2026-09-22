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
| D-04 | Database là SQLite chạy cục bộ trên máy Bridge, bật WAL, `synchronous=FULL` *(2026-09-16: thử `NORMAL`, không nhanh hơn, đã trả lại `FULL` — xem diễn giải)*. |
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
| D-21c | Lệnh **ĐÓNG phía Master** cũng đi qua giao diện khi bật `master_close_route = UI`, bằng một clicker **thứ hai** lái terminal Master. Mặc định `EA` — bật là hành động có chủ đích. |
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

**2026-09-16 — đã thử `NORMAL` rồi TRẢ LẠI `FULL`, ghi lại để không ai đi vòng này lần nữa.** Vào lệnh
chậm (~3 giây/lệnh), ack của clicker và event EA bị Bridge đọc dồn trễ 1,3–1,8 giây. Đo commit trên đĩa
VPS: FULL trung vị 5,4 ms, NORMAL ~0 ms — và đã đổi sang NORMAL **trước khi có bằng chứng** về nguyên
nhân. Đổi xong **không cải thiện gì**. Bộ canh vòng sự kiện (`bridge/watchdog.py`) sau đó chỉ đúng thủ phạm:
`scan_deadlines` quét toàn bảng `command` mỗi giây (index một phần không dùng được), sửa bằng migration
`007`. Đo lại: ack trễ 11 ms, Master→Client 0,74 s. Fsync 5 ms không phải chỗ chậm, nên độ bền khi mất
điện được giữ nguyên. Bài học: đo xem vòng sự kiện bị chặn ở đâu trước, đánh đổi độ bền sau cùng.

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

### D-21c — Lệnh ĐÓNG phía **Master** cũng đi qua giao diện, khi bật `master_close_route = UI`

**Lý do:** D-21 chốt "Master giữ `OrderSend`" với cùng lập luận đã hỏng ở D-21b — bên kiểm tra chỉ
nhìn tài khoản Client. Khi phạm vi mở sang tài khoản Master thì phần ấy hết hiệu lực, và lần này
cái giá **không nằm ở code** mà ở vận hành: cần một clicker **thứ hai** lái terminal Master, token
riêng, tác vụ riêng, nhật ký riêng, và terminal Master phải luôn mở Toolbox ở tab Trade.

Vì cái giá đó có thật, mặc định là `EA`: nâng cấp không đổi hành vi của bản đang chạy. Bật là một
hành động có chủ đích, và `cau-hinh-master` từ chối bật khi chưa khai clicker.

Hai chỗ **bắt buộc** phải khác bản Client, và đều là chỗ sai thì hỏng âm thầm:

* **Nhận diện lệnh đóng chân Master theo agent nhận**, không theo loại lệnh. Cả hai đường đều gửi
  `CLOSE_UI` cho một agent role `CLICKER`; nhầm thì ghi sổ chân Client bằng kết quả của một lệnh
  đóng chân Master.
* **Nhận cha cho event đóng Master** (D-27 áp cho phía Master). EA Master không gọi `OrderSend` nên
  event về với `caused_by_command_id = NULL`, mang đúng dấu hiệu của một cú đóng tay — không nhận
  cha thì mỗi lần cascade tự kích hoạt thêm một lượt đồng bộ.

Rơi về `OrderSend` khi clicker Master hỏng: **được**, cùng lý do D-28. Các Client đã đóng rồi, nên
Master đứng lại một mình là phơi nhiễm một chiều. Deal lần ấy mang `EXPERT` và đi kèm alert CRITICAL
`CLOSE_MASTER_FELL_BACK_TO_EA`.

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

**Thứ tự dò (bổ sung 2026-09-15).** Bản đầu dò tuần tự từ dòng 0, nên đóng vị thế thứ 9 trong 10
phải mở rồi huỷ 8 hộp thoại trước (người dùng quan sát được). Nay `clicker/ui/timdong.py` chọn dòng:
trước hết theo **bản đồ `ticket → dòng`** mà chính các lần dò trước đã đọc được (dịch lên một sau mỗi
lần đóng hẳn), sau đó **tìm nhị phân theo ticket** — tab Trade mặc định sắp theo thời gian mở và
ticket tăng theo thời gian. Chiều sắp suy từ các ticket đã đọc; ticket mâu thuẫn với một thứ tự đơn
điệu thì quay về dò tuần tự.

Hai điều **không** đổi, và là lý do thay đổi này an toàn: mọi dòng vẫn bị đọc ngược ticket trước khi
bấm, và `already_closed` vẫn chỉ kết luận sau khi đã mở **mọi** dòng. Nhị phân cho biết đích *nên*
nằm đâu, không cho biết nó *không* nằm ở đâu — suy "đã đóng" từ đó là đặt cược sổ sách vào cách
người dùng sắp cột.

**Rà soát "chốt sai" (bổ sung 2026-09-15).** Người dùng nghi có lần bên kia chốt sai khi đang có ~10
vị thế. Rà cả hai nửa. Bridge **không** có đường gửi nhầm `position_id` (id luôn lấy từ dòng `pair`,
bộ tương quan đóng lọc theo cặp/vị thế). Ba lỗ hổng có thật đã bịt, xếp theo độ nghi:

1. **Khe hở giữa lúc kiểm và lúc MT5 xử lý cú bấm.** `BM_CLICK` là message post, chạy **sau** mọi
   message còn tồn — kể cả `SendMessageTimeout` đã hết hạn của lần dò trước, vốn vẫn được giao muộn.
   Nay `_commit_close` xả hàng đợi (`win32.cho_xu_ly_xong`, `WM_NULL` vào danh sách và hộp thoại),
   **rồi** mới đọc lại ticket; không xả được thì `rejected`. Kiểm thêm **con số trên nút Close** —
   đóng một phần phải bằng volume yêu cầu, đóng hẳn phải bằng volume vị thế ở tiêu đề. Giới hạn nói
   thẳng: `WM_NULL` không chứng minh được message **post** đã chạy hết; khe hở hẹp lại, không mất.
2. **`already_closed` chỉ từ một phép tìm sạch.** Một lần dò treo, một hộp thoại sót, hay một ticket
   hiện ở hai dòng (hộp thoại mở trễ) làm "quét hết không thấy" mất giá trị — trả `rejected` để Bridge
   rơi về EA, vốn đóng theo đúng ticket. Ticket ở hai dòng thì mở lại cả hai, không ghi bản đồ.
3. **Cửa sổ tương quan MỞ đo từ `received_at`** (bổ sung D-23), cùng lý do D-27 đã sửa cho đường
   đóng: vòng xử lý bận không được làm cặp đúng rớt khỏi cửa sổ. Ứng viên gộp theo cặp (lệnh thử lại
   cùng thẻ không tự gây `AMBIGUOUS`). Nhánh `HEURISTIC` từ chối vị thế mang thẻ của một cặp có thật và
   đếm cả cặp cùng thông số ngoài cửa sổ — hàng đợi D-31 làm nhiều cặp cùng thông số chờ ghép thành
   chuyện thường, và gắn nhầm ở đây nghĩa là mọi lần đóng về sau "đúng id" mà sai lệnh.

Không cơ chế nào ở trên đã được **quan sát** trên VPS; `bridge.admin kiem-dong-sai` là cách phân biệt.
**Không** từ chối hộp thoại có hwnd trùng lần trước: chưa đo MT5 có dùng lại hwnd hay không, và từ
chối sai sẽ tắt hẳn đường đóng qua giao diện — thay vào đó log hwnd mỗi lần dò để đo.

**Đo trên VPS 2026-09-15 (commit `0b2cec3`):** hai lần đóng liên tiếp cho hwnd `0xa20c4e` và
`0x19701a2` — MT5 **tạo cửa sổ mới** mỗi lần mở hộp thoại, không dùng lại. Quyết định không từ chối
hwnd trùng là đúng: nó không tắt gì, và nếu có ngày hwnd trùng xuất hiện thì đó là bất thường đáng
nhìn log, không phải hành vi thường. Xả hàng đợi đo được `0 ms` cả hai lần.

### D-31 — Clicker bận thì **xếp hàng**, không bỏ lệnh

**Bằng chứng:** 2026-09-14, vào 10 lệnh liên tiếp trên Master thì Client chỉ copy được vài lệnh.
Không phải lỗi ngẫu nhiên: cổng 2 của `_ui_route_blocked` cho **đúng một** `OPEN_UI` trên đường dây
mỗi Client, và bản trước **bỏ hẳn** lệnh thứ hai trở đi. Một vòng bấm giao diện mất ~0,8 giây, nên
thông lượng trần là ~1,2 lệnh/giây — dưới tốc độ một người nhấn tay.

**Cổng 2 được giữ nguyên.** Nó là thứ biến bài toán tương quan mờ (event Client không mang
`command_id`) thành hàng đợi một phần tử luôn phân giải được. Cái sai là *cách xử lý khi bận*: bỏ
một lệnh copy nghĩa là **mất hedge** — đúng thứ hệ thống này tồn tại để tránh.

Nên bận thì lệnh vào bảng `ui_open_queue`, và `_bom_hang_doi_ui()` đẩy lệnh kế tiếp ra khi đường
dây rảnh. Ba điều đi kèm, mỗi điều đều là một lựa chọn có thể sai theo hướng khác:

* **Trần tuổi 15 giây**, đo từ `ts_agent` chứ không từ lúc xếp hàng. Quá đó giá đã chạy đủ xa để
  mở thành mở sai giá, nên **huỷ** và kêu `UI_OPEN_QUEUE_EXPIRED` ở mức **ERROR** — mất hedge phải
  ra tới Telegram. Nới trần cho khỏi thấy dòng này là tự bịt mắt trước thông lượng thật.
* **FIFO tuyệt đối**: khi hàng đợi còn người đứng trước, lệnh mới cũng xếp cuối **dù đường dây đang
  rảnh**. Cho chen là tự chọn hy sinh lệnh cũ nhất — sai thứ tự để hy sinh.
* **Chỉ cổng 2 dẫn tới xếp hàng.** Clicker hỏng (cổng 1) và Algo Trading tắt là trạng thái
  **không tự hết**; xếp hàng ở đó chỉ tích lại một đống lệnh rồi hết hạn cả loạt.

*(Bổ sung 2026-09-21)* Phép kiểm Algo Trading — từng là "cổng 3" của đường giao diện — nay là
`_algo_trading_tat` và chạy cho **cả hai** đường mở. Nó nằm trong `_ui_route_blocked` nên Client đi
đường EA chưa từng được kiểm, trong khi ở đường EA thì Algo Trading tắt nghĩa là chính lệnh **mở**
thất bại: người vận hành nhận một `OPEN_FAILED` với retcode của terminal, và nếu Client đó đặt
`open_fail_policy = RETRY_CLOSE_MASTER` thì cú thất bại ấy còn kéo vị thế Master đóng theo. Đó là
đường mà một Client thứ hai hay dùng lúc đầu, nên chỗ này không phải trường hợp hiếm.

Hàng đợi nằm trong DB chứ không trong bộ nhớ, vì `tinh-hinh` phải thấy được nó, và một lần khởi
động lại giữa chừng thì lệnh đang chờ phải hết hạn **có tiếng** chứ không biến mất im lặng.

**Hệ quả:** giờ có thể có **nhiều** cặp `PENDING_OPEN` cùng lúc chờ tương quan. Điều này đã an toàn
sẵn — ghép bằng thẻ `open_tag` riêng từng lệnh, mất thẻ thì `STRICT` từ chối đoán và nhiều ứng viên
cùng khớp thì `UI_CORRELATE_AMBIGUOUS`. Hàng đợi làm **tăng tần suất** các nhánh đó, không tạo
nhánh mới.

### D-32 — Cấu hình nghiệp vụ nằm ở database và sửa trên dashboard; `config.toml` chỉ giữ thứ cần trước khi Bridge chạy

**Vấn đề:** mọi giá trị cấu hình phải nhập lúc cài (`scripts/tro-ly.ps1` hỏi 9 giá trị), rồi muốn
xem hay sửa lại phải RDP vào VPS gõ `bridge.admin`. Người vận hành không thấy được mình đang chạy
cấu hình gì — và đó là loại không-biết dẫn tới quyết định sai lúc có sự cố.

**Ranh giới đã chốt:**

* **Database** giữ cấu hình *nghiệp vụ*: agent (số tài khoản, magic, tiêu đề cửa sổ terminal của
  clicker), `client_account`, `symbol_map`, `system_config`. Sửa được trên dashboard, có hiệu lực
  ngay vì mọi khoá ở đây đều được đọc lại mỗi lần dùng.
* **`config.toml`** chỉ giữ thứ **phải có trước khi Bridge chạy**: cổng, đường dẫn DB, và token
  của clicker. Dashboard **sửa được** chúng, nhưng theo ba điều kiện — vì một
  `config.toml` hỏng là một Bridge không khởi động được, và lúc đó không còn dashboard nào để sửa
  lại: (1) nội dung mới chạy qua đúng `parse_config` của đường khởi động **trước khi** ghi, không
  qua được thì file cũ không bị đụng tới; (2) bản cũ được **sao lưu** kèm dấu thời gian; (3) sửa
  **tại chỗ từng dòng**, giữ nguyên chú thích — dựng lại file từ dict sẽ xoá sạch phần giải thích
  vì sao một giá trị được đặt như vậy. Giá trị bí mật **không bao giờ đi ra khỏi Bridge**: API chỉ
  báo "đã đặt" hay chưa, và ô để trống nghĩa là *giữ nguyên*. Tiến trình đang chạy **không nạp
  lại**: cấu hình khởi động nửa nạp nửa không là trạng thái không ai lường được, nên trang nói
  thẳng là phải khởi động lại dịch vụ.
* **Ràng buộc nằm ở `bridge/ops.py`, không ở tầng web và không ở CLI.** Hai đường vào cùng gọi một
  bộ hàm; lỗi là một **mã** ASCII, CLI dịch sang câu không dấu còn dashboard dịch qua
  `labels_vi.py` (D-16). Trước đó phép kiểm nằm lẫn với `print` trong `admin.py`, nên tầng web
  không gọi lại được — và hai đường vào kiểm khác nhau thì cái lỏng hơn mới là cái thật.

**Hệ quả cho clicker.** Số tài khoản và tiêu đề cửa sổ rời `config.toml` vào DB, nên clicker nhận
chúng trong `hello_ack` và đọc lại ở **mỗi lần bắt tay**; dashboard đổi giá trị thì Bridge cắt kết
nối và ba giây sau clicker lái đúng cửa sổ mới, không phải đăng ký lại Scheduled Task. Thứ tự ưu
tiên `--tham-so` > `config.toml` > Bridge giữ cho bản cài cũ chạy y như trước.

**Hai hàng rào phải đổi theo, và cả hai đổi theo hướng chặt hơn:**

1. `ACCOUNT_MISMATCH` ở Bridge so DB với con số agent gửi lên. Khi con số đến **từ** Bridge thì
   phép so đó tự khớp với chính nó, nên hàng rào chuyển sang clicker và đối chiếu với **cửa sổ
   thật**: số tài khoản đọc từ tiêu đề cửa sổ phải khớp số Bridge giao, kiểm mỗi nhịp heartbeat.
   Bản cũ đúng vĩnh viễn với một dòng cấu hình; bản mới bắt được cả terminal đăng nhập sang tài
   khoản khác giữa phiên.
2. Chưa khai tiêu đề thì clicker **thoát** (mã 4) chứ không chạy tiếp ở canary đỏ. Canary đỏ chỉ
   chặn đường MỞ; đường ĐÓNG rơi về `OrderSend` của EA theo `close_degraded_fallback = EA`, tức
   deal đóng mang `EXPERT` — đúng thứ đường đóng qua giao diện tồn tại để ngăn.

**~~Mọi endpoint SỬA cấu hình đều đòi dashboard có mật khẩu.~~** Đã bỏ — xem **D-39**. Đăng nhập
không còn tồn tại; đổi lại `bridge.host` bắt buộc là loopback.

**`bridge.db_path` KHÔNG sửa được trên dashboard.** Đổi nó rồi khởi động lại là Bridge mở một
database rỗng: toàn bộ agent, token, ánh xạ và cặp đang mở biến mất khỏi sổ trong khi vị thế thật
vẫn nằm trên sàn. Đó không phải một khoá cấu hình, đó là một nút xoá sổ sách.

**~~Cấp token trên dashboard bị chặn khi dashboard không có mật khẩu.~~** Đã bỏ — xem **D-39**.

### D-33 — Có nút đặt lại hai mức trên dashboard; gỡ nút đóng khẩn cấp

**Đặt lại.** Sau mỗi đợt thử, sổ sách đầy cặp lệnh và cảnh báo của những lần đã xong, và cách duy
nhất để dọn là `UPDATE`/`DELETE` tay vào SQLite — đúng thứ dự án cấm. Nên có hai nút, vì có hai
câu hỏi khác nhau:

* **Đặt lại dữ liệu** — "bắt đầu đếm lại". Xoá lịch sử giao dịch, giữ agent, client, ánh xạ symbol
  và khoá hệ thống; hệ thống chạy tiếp ngay sau đó.
* **Đặt lại toàn bộ** — "cấu hình lại từ đầu". Xoá thêm client và ánh xạ, đưa khoá hệ thống về
  mặc định khai trong `schema.sql`.

**Agent và token được giữ ở cả hai mức.** Xoá chúng chỉ để dọn sổ sách là tự bắt mình mở giao diện
MT5 dán lại token cho hai EA — việc tay chân duy nhất trong cả quy trình cài đặt, và là chỗ dễ sai
nhất. Muốn xoá một agent thì `thu-hoi` rồi `them-agent`, có chủ đích từng cái một.

Ba hàng rào, không mức nào bỏ được: **sao lưu trước khi xoá** (một lệnh xoá không có đường lùi thì
không phải lệnh vận hành); **không xoá khi còn cặp hay vị thế Master đang mở** — xoá sổ sách trong
lúc tiền còn nằm trên sàn là cách chắc chắn nhất để không ai biết còn gì đang mở; **không xoá khi
còn lệnh chưa xong và phải đang `PAUSED`**. Mỗi mức một **cụm xác nhận gõ tay riêng**, không dấu:
nhầm mức này sang mức kia là mất cấu hình mà không định mất.

Khoá hệ thống được gieo lại bằng chính các câu `INSERT OR IGNORE INTO system_config` đọc từ
`schema.sql` và các migration, chứ không chép danh sách khoá vào code: bản sao thứ hai của sự thật
sẽ lệch ở lần thêm khoá tiếp theo.

**Gỡ nút đóng khẩn cấp.** Nút này đóng sạch mọi vị thế đang quản lý bằng một cú bấm và một cụm gõ
tay. Nó nằm trên đúng trang mà người vận hành mở hằng ngày, và mọi thứ còn lại trên trang đó giờ
đều là việc thường ngày — càng quen tay càng gần tới lần bấm nhầm. Đổi lại, đóng khẩn cấp vẫn còn
nguyên dưới dạng `bridge.admin run-mode EMERGENCY`: cùng cơ chế, cùng thứ tự Client → Master, chỉ
khác là phải gõ ra một câu lệnh. Endpoint `/api/emergency` bị gỡ hẳn — để một đường HTTP đóng sạch
vị thế tồn tại mà không ai dùng thì nó chỉ còn là bề mặt tấn công.

### D-34 — Dashboard chỉ **xem và cấu hình**; mọi tác động lên vị thế làm trong MT5

Sau khi gỡ nút đóng khẩn cấp (D-33), trên dashboard vẫn còn một đường gửi lệnh thật xuống MT5, và
nó kín hơn hẳn: nút **Chấp nhận** ở tab Sai lệch. Sai lệch `MASTER_CLOSED_OFFLINE` mang hành động
`CLOSE_CLIENT` và được xếp mức **an toàn** — nên nút *"Chấp nhận tất cả mục an toàn"* đóng lệnh
**hàng loạt** bằng một cú bấm, trên một trang mà mọi thứ khác chỉ là xem.

Ranh giới từ nay:

* **Dashboard sửa sổ sách và cấu hình.** Chấp nhận một sai lệch vẫn làm được khi hành động của nó
  chỉ ghi vào database: `MARK_CLOSED`, `MARK_ORPHANED`, `REBIND_BY_TAG`, `ALERT_ONLY`.
* **Vị thế là việc của người dùng trên terminal MT5.** Sai lệch cần đóng (`CLOSE_CLIENT`) hoặc có
  thể mở (`APPLY_POLICY`) thì dashboard chỉ hiện bằng chứng và nói thẳng: đóng tay trong MT5, rồi
  quay lại bấm **Bỏ qua kèm ghi chú** — dòng ghi chú đó là thứ giải thích về sau.
* **Nút *Chấp nhận tất cả mục an toàn* bị gỡ hẳn**, cùng với endpoint của nó. Một nút hàng loạt
  trên một danh sách có lẫn hành động đóng lệnh là chỗ để mất tiền mà không ai kịp đọc gì.

Danh sách hành động chạm MT5 nằm ở `Reconciler.HANH_DONG_CHAM_MT5` và đi xuống giao diện dưới dạng
cờ `cham_mt5` trong mỗi dòng sai lệch: JavaScript không được tự suy ra hành động nào là nguy hiểm.

Ba nút đổi chế độ (`RUNNING` / `PAUSE_NEW_ENTRIES` / `PAUSED`) **ở lại** trên dashboard. Chúng
không gửi lệnh nào; chúng bật hoặc tắt việc copy, và đó là thứ người vận hành phải với tới được
nhanh. `EMERGENCY` thì vẫn chỉ đặt bằng dòng lệnh (D-33).

### D-35 — Mỗi Client một clicker riêng, số mục clicker không giới hạn

Trước 2026-09-21 chỉ đúng **hai** mục clicker được chấp nhận (`[clicker]` cho Client, `[clicker_master]`
cho Master). Hệ quả không nằm ở chỗ "chưa tiện": Client thứ hai **không có chỗ nào để khai token
clicker**, nên nó buộc phải đi đường EA — và deal của nó mang `DEAL_REASON = EXPERT` thay vì
`CLIENT`, tức là mất đúng thứ mà cả phase 6b và phase 11 tồn tại để đạt được (B-19).

Từ nay tên mục chỉ cần khớp `RE_MUC_CLICKER` = `^clicker(_[a-z0-9_]+)?$`:

* `Config.clickers` giữ **mọi** mục đọc được, `muc_clicker(ten)` tra theo tên, và khi gõ sai tên nó
  nói ra **những mục đang có** — gõ `clicker_cl2` thay vì `clicker_cl02` mà chỉ báo "thiếu token"
  thì người ta đi tìm token trong khi lỗi nằm ở cái tên.
* Token của mục mới khai được **ngay trên dashboard** (`kieu_khoa_file` cho mọi `clicker*.token`),
  đúng lý do của D-32: token không được đi qua dòng lệnh, và mở `config.toml` trên VPS chỉ để dán
  một dòng là việc không nên phải làm.
* `tao-dich-vu.ps1 -TacVuClicker clicker_master,clicker_cl02` đăng ký **một Scheduled Task cho mỗi
  mục**, tên tác vụ suy ra từ tên mục (`ClickerCl02`). `-GoBo` gỡ **mọi** tác vụ khớp `Clicker*`
  thay vì một danh sách cứng — danh sách cứng đã từng bỏ sót đúng `ClickerMaster`, và một tác vụ
  còn sót là một tiến trình vẫn bấm vào terminal cũ.

Ràng buộc **không** đổi: hai Client không dùng chung một clicker, và không Client nào dùng clicker
của Master (`_clicker_con_trong` trong `ops.py`). Một clicker lái hai terminal là hai hộp thoại
New Order cùng được điền — và cái hàng rào duy nhất chống lái nhầm terminal là số tài khoản phải
khớp tiêu đề cửa sổ, kiểm lại ở **mỗi** cú bấm.


### D-36 — Cài bằng một lệnh; mọi cấu hình nghiệp vụ khai trên dashboard

D-32 đưa cấu hình nghiệp vụ vào database và cho sửa trên dashboard, nhưng **đường cài đặt vẫn hỏi
chúng trên console**: trợ lý hỏi ánh xạ symbol, chờ EA lên `ONLINE` tới 5 phút, và in token thô ra
màn hình. Tức cùng một giá trị có **hai** chỗ khai, và chỗ khó dùng hơn lại là chỗ bắt buộc đi qua
trước.

Từ nay:

* **`cai-dat.ps1` tự chạy tiếp `tro-ly.ps1 -TuDongDongY`** trên đường cài mới. Năm việc trong khối
  "BUOC TIEP THEO" phải làm **đúng thứ tự**, một việc cần token vừa hiện một lần, và bỏ sót việc
  nào thì hệ thống dựng xong vẫn không copy được lệnh nào — hỏng trong im lặng. Một lệnh duy nhất
  là cách duy nhất không bao giờ sai thứ tự. `-BoQuaTroLy` để quay lại cách cũ.
* **Trợ lý không hỏi gì về nghiệp vụ nữa**, và bỏ hẳn hai bước chờ EA + hỏi ánh xạ symbol. Cả hai
  đều cần EA đã gắn xong — việc nằm trong giao diện MT5 — nên hỏi ở đó là dừng script lại hàng
  phút để chờ một việc nó không làm được.
* **Token của EA không in ra console.** Lấy trên dashboard: Agent → *Cấp lại token*, hiện một lần
  ngay trên trang. Một token in ra console là một token nằm trong scrollback của cửa sổ RDP cho
  tới khi ai đó đóng nó.
* **Trợ lý mở dashboard trong trình duyệt** ở bước cuối (`-KhongMoDashboard` để tắt), sau khi chờ
  cổng web thật sự lắng nghe — mở sớm thì trình duyệt báo "không kết nối được" và người dùng kết
  luận là bản cài hỏng.
* **`master_close_route = UI` thành mặc định BẬT.** Bật sau đòi đăng ký thêm một Scheduled Task
  trên VPS, tức đúng cái ma sát vừa bỏ đi; còn tắt nó thì sửa được ngay trên dashboard. An toàn
  khi chưa khai xong: clicker Master chưa sẵn sàng thì đường đóng **rơi về EA kèm alert** (D-28).

**Cái giá, và cách trả:** bỏ mọi câu hỏi nghĩa là không còn ai bắt người dùng khai ánh xạ symbol —
mà thiếu nó thì **mọi** lệnh Master bị bỏ qua trong im lặng. Nên cửa chặn chuyển vào dashboard:
khối **"Cần làm"** ở đầu tab Cấu hình (`views.viec_can_lam`) liệt kê chính xác cái gì còn thiếu,
mỗi mục nói **làm gì ở đâu**, và mục `CHẶN` nghĩa là hệ thống chưa copy được lệnh nào. Nó bắt: agent
chưa `ONLINE`, clicker chưa khai số tài khoản/tiêu đề, **tiêu đề không chứa số tài khoản**, Algo
Trading tắt, Client thiếu ánh xạ symbol, Client đi đường giao diện mà không có clicker, đường đóng
Master `UI` mà chưa khai clicker, và `run_mode` chưa `RUNNING`.

Khối đó **không biến mất khi rỗng** — "không còn việc nào" là thông tin người vận hành cần, và một
khối thỉnh thoảng mới xuất hiện thì không ai học được chỗ để tìm nó.


### D-37 — Hướng dẫn nằm **trong sản phẩm**, và tự biết bước nào đã xong

Cài đặt chỉ còn một lệnh (D-36) và trình duyệt tự mở, nhưng nó mở vào trang chủ: người dùng phải tự
tìm ra khối "Cần làm" nằm giữa tab Cấu hình. Khối đó nói *cái gì còn thiếu* — nó không nói **thứ tự
làm**, không chứa bước nào nằm ngoài tầm Bridge (gắn EA lên chart, bật Algo Trading, mở Toolbox), và
không phân biệt **cài lần đầu** với **sau khi cập nhật**, hai việc có danh sách khác hẳn nhau.

Nên có tab **Hướng dẫn** (`views.trang_huong_dan`), và script cài mở thẳng `/#huong-dan`. Bốn điều
đáng ghi lại:

* **Không có bộ luật thứ hai.** Mỗi bước tự kiểm được chỉ khai mã của `viec_can_lam`; trạng thái
  suy ra từ đó. Hai bộ luật cho cùng một câu hỏi thì sớm muộn lệch nhau, và lúc ấy không ai biết
  bên nào đúng.
* **Phép kiểm rỗng là cái bẫy.** Chưa có clicker nào thì "mọi clicker đã khai xong" là đúng về
  logic và sai về sự thật, nên các bước đó khai kèm `CHUA_CO_AGENT`. Một bước báo *Đã xong* khi
  chưa ai làm gì sẽ làm mất lòng tin vào cả danh sách.
* **Bước nào Bridge không thấy được thì nói thẳng là tự tích**, không giả vờ kiểm. Ví dụ đắt nhất:
  **"đã biên dịch lại và gắn lại EA"**. `hello` của EA **không mang phiên bản EA** — chỉ
  `terminal_build`, là của *terminal* — nên Bridge không phân biệt được một EA vừa gắn lại với một
  EA cũ vừa nối lại sau khi dịch vụ khởi động, mà mỗi lần `-CapNhat` đều khởi động lại dịch vụ.
  Xem B-20.
* **Ô tự tích nằm trong database và bị xoá theo mốc cập nhật.** Trong `localStorage` thì nó mất khi
  đổi trình duyệt; không xoá thì ô tích của lần cập nhật trước làm danh sách trông như đã xong — và
  một danh sách luôn xanh thì không ai đọc nữa. `cai-dat.ps1 -CapNhat` ghi biên nhận
  (`ghi-moc-cap-nhat`) gồm thời điểm, `ea/` có đổi không, và commit cũ; đó là **thứ duy nhất** cho
  dashboard biết vừa có một lần cập nhật, vì Bridge không lưu phiên bản code nào.

Hai bẫy giao diện, cả hai chỉ lộ ra khi chạy thật chứ không khi đọc code: đổi `#hash` trên một tab
**đang mở** thì trình duyệt **không** tải lại trang (nên phải nghe `hashchange`, nếu không thì mở
`/#huong-dan` lúc dashboard đã mở sẵn chẳng làm gì cả); và tab mới **phải** được thêm vào bảng nhãn
trong `veNutDieuKhien`, nếu không nó hiện chữ `undefined` và bị vẽ lại như vậy mỗi giây.


### D-38 — Trang Cấu hình chỉ hỏi những gì hệ thống không thể tự biết

Rà soát toàn bộ ô nhập cho một con số: để đi từ "cài xong" tới "copy được lệnh" với 1 Master +
1 Client, người dùng phải gõ **7 ô** — bốn ô cho hai clicker, ba ô cho ánh xạ symbol. Trong 15 ô của
cả trang, **11 ô suy được** từ dữ liệu Bridge đã có.

**Ba thứ nay tự suy, và vì sao suy được:**

* **Số tài khoản của clicker.** Clicker của `CL-01` lái đúng cái terminal mà EA của `CL-01` đang
  chạy — đó là topology duy nhất hệ thống hỗ trợ — và EA **tự khai** số tài khoản ở mỗi lần bắt
  tay. `ops.cau_hinh_clicker` đi theo liên kết `client_account.clicker_agent_id` (hoặc
  `master_clicker_agent_id`) để lấy con số ấy. Nó **tính lúc đọc, không ghi vào DB**: ghi xuống thì
  một giá trị không ai gõ sẽ trông như đã gõ, và lần sau terminal đăng nhập sang tài khoản khác thì
  DB nói sai mà không ai biết.
* **Tiêu đề cửa sổ** mặc định là chính số tài khoản. Không phải phỏng đoán:
  `clicker/ui/probe.py::account_login_from_title` đọc số từ **đầu** tiêu đề cửa sổ MT5, nên
  `str(login)` luôn là mẩu khớp hợp lệ và hẹp nhất.
* **Mọi cái tên đi kèm một Client** — `AG-CL02`, `AG-CLICKER-CL02`, `[clicker_cl02]`, `ClickerCl02`,
  `clicker_cl02.log` — sinh từ một quy tắc duy nhất (`ops.ten_theo_client`), nên tên trong database,
  trong `config.toml` và trong Task Scheduler không bao giờ lệch nhau.

**Khai tay vẫn thắng**, và **lệch thì không tự chọn hộ**: có người đã gõ thì dùng cái đã gõ; nếu con
số ấy khác con số EA báo thì `viec_can_lam` nêu **cả hai** ở mức CHẶN. Lệch nghĩa là clicker đang lái
nhầm terminal, hoặc terminal vừa đăng nhập sang tài khoản khác — cả hai đều đắt, và cả hai đều phải
do người quyết. Hàng rào cũ không đổi: clicker vẫn đối chiếu số Bridge giao với số đọc từ **cửa sổ
thật** ở mỗi cú bấm (D-32); suy từ EA chỉ làm nguồn của con số ấy đáng tin hơn.

**Ánh xạ symbol: đề xuất, không tự tạo.** `symbol_spec` đã chứa toàn bộ Market Watch của cả hai bên,
nên hai ô gõ tay thành hai danh sách thật kèm đề xuất (`XAUUSD → XAUUSDm`, xếp hạng theo tên rồi so
thêm `digits` và `contract_size` — thứ phân biệt bản micro). Nhưng **không tự tạo**: chọn sai symbol
không báo lỗi, nó chỉ lặng lẽ copy sang một thị trường khác. Việc đó phải có người bấm.

**Thêm Client là một nút.** Trước đây là năm việc rời nhau, làm đúng thứ tự mới chạy. Nay một lần
bấm tạo agent EA, agent clicker, dòng `client_account` route UI, và ghi token clicker thẳng vào
`config.toml`. Còn đúng hai việc phải làm tay, và cả hai **nằm ngoài trình duyệt**: dán token vào EA,
và đăng ký Scheduled Task (cần quyền Administrator trên VPS) — nên trang in sẵn token một lần và
đúng câu lệnh đó.

**Ba chỗ sai sửa kèm:**

1. ~~`CHUA_DAT_MAT_KHAU` từ mức Lưu ý lên **CHẶN**.~~ Mã này đã biến mất cùng với đăng nhập —
   xem **D-39**. Chính cái vòng khoá kín mô tả ở đây (không đặt nổi mật khẩu từ trang cần mật khẩu)
   là thứ làm lần cài thật tắc ở bước 1.
2. `magic` biến khỏi đường tạo agent: EA **ghi đè** nó ở lần bắt tay đầu, và không chỗ nào trong
   Bridge so magic giữa các agent. Hỏi con số này không mua được gì.
3. Khoá hệ thống, `config.toml` và Đặt lại gom vào mục **Nâng cao** đóng sẵn — một bản cài bình
   thường không bao giờ dùng tới chúng.

**Hai lỗi chỉ lộ ra khi bấm thật**, cả hai đều trong code viết cùng ngày: bọc hàm chạm database
trong `asyncio.to_thread` (sqlite3 chỉ dùng được trong đúng luồng đã tạo kết nối — nên phần DB chạy
trên vòng sự kiện, chỉ phần ghi file mới đẩy sang luồng khác); và vẽ khối token **trước** khi gọi
`taiCauHinh()`, mà hàm đó dựng lại cả tab — token hiện đúng một lần rồi bị chính mình xoá sau một
nhịp.

### D-39 — Dashboard không còn đăng nhập; đổi lại, nó chỉ được nghe loopback

Ngày 2026-09-22, chạy thử tài liệu trên VPS: **bước 1** của tab Hướng dẫn — cấp lại token cho EA —
không bấm được. Nút không hiện token nào. Nguyên nhân là một vòng khoá kín:

* `cai-dat.ps1` sinh một mật khẩu ngẫu nhiên lúc cài và in ra **đúng một lần**. Không chép lại ngay
  thì mất luôn đường vào.
* Không đăng nhập được thì **mọi** endpoint ghi trả 403 (D-32 mục `_chan_ghi`), kể cả
  `/api/file_config` — tức **không đặt nổi mật khẩu từ chính trang đó**.
* Bước "Đặt mật khẩu dashboard" lại nằm ở vị trí **7** trong danh sách chín việc, sau bước 1 vốn
  cần nó. Thứ tự ấy không bao giờ chạy được.

Ba lớp đều hợp lý một mình, và cộng lại thành một bản cài không làm gì được. Đó là dấu hiệu của một
cơ chế sai chỗ, không phải ba lỗi nhỏ.

**Quyết định: gỡ hẳn đăng nhập.** Không còn `/login`, không còn cookie phiên, không còn
`security.dashboard_password`, không còn `_chan` / `_chan_ghi` / `_chan_cap_token`. Ai mở được
`http://127.0.0.1:8080` là dùng được mọi thứ trên trang.

**Đổi lại — và đây là phần không được bỏ:** `bridge.host` giờ **bắt buộc** là loopback.
`parse_config` từ chối khởi động với bất kỳ địa chỉ nào khác. Trước đây phép kiểm này đòi mật khẩu
khi nghe ra ngoài; nay không còn mật khẩu nào để đòi, nên câu trả lời duy nhất còn lại là không mở
ra ngoài. Kiểm toán 2026-09-06 gọi thẳng `/api/emergency` không cookie và nó đóng 3 cặp (F-02) —
endpoint đó đã gỡ (D-33), nhưng bài học thì không: một bảng điều khiển không khoá trên một
interface công khai là một sự cố đang chờ xảy ra. Muốn xem từ máy khác thì Tailscale hoặc SSH
tunnel, không phải mở cổng.

**Cái giá, nói thẳng:** ai vào được VPS là đổi được chiều copy, hệ số volume, đường mở/đóng, và cấp
lại được token agent. Trên máy này ranh giới an toàn **là** ranh giới của phiên RDP, không hơn. Đó
là một đánh đổi có ý thức cho một VPS một người vận hành, không phải một mặc định để nhân bản.

**D-32 và D-38 bị sửa theo:** hai đoạn nói "mọi endpoint sửa cấu hình đều đòi dashboard có mật
khẩu" và "cấp token bị chặn khi không có mật khẩu" không còn đúng. Bước `LD_MAT_KHAU` biến khỏi
danh sách Cài đặt lần đầu — còn **tám** việc — và mã chặn `CHUA_DAT_MAT_KHAU` biến khỏi
`viec_can_lam`. Số ô phải điền tay trên trang Cấu hình xuống **0**.

### D-40 — Một bước hướng dẫn có bốn phần, không phải một câu

Lần chạy thử tài liệu trên VPS 2026-09-22 tắc ở bước 1 và không đi tiếp được. Gỡ xong cái tắc
(D-39) thì lộ ra vấn đề lớn hơn: **mô hình dữ liệu của một bước quá hẹp**. Một bước chỉ có một
chuỗi chữ, một câu lệnh, một trạng thái — nên mọi thứ phải nhồi vào câu chữ. Bước `LD_GAN_EA` gói
**sáu** hành động vào một đoạn: cấp token cho hai agent, kéo EA lên đúng một chart, dán token, đặt
host, đặt port, cảnh báo hai chart. Không thứ tự, không nói làm ở đâu, không cách tự kiểm.

**Một bước nay có bốn phần** (`views.Buoc`), và ba trong bốn là bắt buộc:

* `khoa` — một dòng để quét mắt. Test chặn nó dài quá 70 ký tự.
* `khoa_viec` — **tuple** các việc con, theo đúng thứ tự phải làm. Tuple chứ không phải một đoạn
  văn: một danh sách có thứ tự thì không thể viết lẫn lộn được.
* `khoa_kiem` — nhìn thấy gì thì coi là xong.
* `khoa_bay` — cái bẫy **đã** bắt được người thật. Không có thì để trống.

Cộng `noi` (dashboard / MT5 / PowerShell): ba nơi ấy đòi ba thứ khác nhau của người vận hành, nên
nói trước là tiết kiệm được một lần mò.

**Bước đỏ phải nói đỏ vì ĐỐI TƯỢNG nào.** `viec_can_lam` vốn đã sinh sẵn một dòng cho từng agent,
từng Client — và `_mot_buoc` nén hết xuống thành một boolean rồi bỏ đi. Nay nó đi thẳng lên trang,
nằm **ngoài** khối Chi tiết: một lý do phải bấm mới thấy thì không khác gì không có.

**Ba lỗ hổng nội dung sửa kèm:**

1. **Thêm bước biên dịch EA vào lần đầu.** Lệnh biên dịch trước đây chỉ nằm ở nhóm *sau khi cập
   nhật*, nên người cài lần đầu không hề được bảo phải tạo `.ex5`. Không có file đó thì bước gắn EA
   không làm được, mà triệu chứng lại là "EA không kéo được lên chart" — một câu không dẫn về đây.
2. **`AGENT_CHUA_ONLINE` tách theo role.** Agent EA và agent clicker hỏng vì hai lý do khác hẳn và
   sửa bằng hai việc khác hẳn. Một mã chung buộc câu chữ phải nước đôi ("gắn EA lên chart, **hoặc**
   kiểm clicker đang chạy"), và bước "Gắn EA" liệt kê cả clicker — bảo người dùng gắn EA cho một
   thứ không có EA. Nhìn thấy trên màn hình thật, không đọc ra từ code.
3. **Mọi bước làm trên dashboard đều in đường dòng lệnh tương đương.** Ngày 2026-09-22 đường
   dashboard tắc và trang không nhắc một câu nào về `bridge.admin`, dù CLI phủ hết cả chín bước.
   Một hướng dẫn chỉ có một đường là một hướng dẫn hỏng khi đường đó hỏng.

**`docs/CAI-DAT-VPS.md` A2/A3 co lại thành con trỏ.** Trước đây nó chép lại cùng nội dung "để đọc
trước khi bắt tay", và hai bản đã lệch thật: trang có bước biên dịch, doc thì không; doc nói "chín
bước" trong khi trang có tám. Nay doc chỉ giữ ba thứ tab Hướng dẫn không nói được, và bảng nghiệm
thu. Một tài liệu song song là một tài liệu sẽ sai.

**Câu mô tả nhóm thôi ghi cứng số việc.** Bản cũ ghi "Chín việc" khi danh sách có tám — số bước đã
đổi ba lần và không ai sửa câu đó. Giao diện tự đếm; có test chặn việc ghi lại bằng chữ.

### D-41 — Dashboard chạy hộ một **danh sách trắng cố định** các lệnh chẩn đoán

Tab Hướng dẫn in ra `.\scripts\kiem-tra.ps1` rồi bảo người dùng mở PowerShell chạy. Người vận hành
hệ thống này không phải dân kỹ thuật, và câu đó là **bốn** chỗ hỏng được: mở đúng PowerShell, đứng
đúng thư mục, dán đúng dòng, rồi tự đọc output. Cả bốn đều hỏng trong im lặng.

Nên có nút **Chạy** ngay trong bước, và kết quả hiện lên trang: một dòng kết luận tiếng Việt trước,
output thô để bên dưới cho ai cần.

**Phần nguy hiểm, và cách chặn.** Dashboard không còn xác thực (D-39), nên một endpoint chạy lệnh là
một đường thực thi mã cho bất kỳ ai chạm tới cổng 8080. Bốn ràng buộc, cả bốn có test khoá:

1. **Trình duyệt gửi MÃ, không gửi câu lệnh.** Không tham số, không đường dẫn, không tên file. Mã lạ
   thì từ chối — không đoán, không ghép chuỗi.
2. **`argv` dựng trong `bridge/web/lenh.py`**, chạy `create_subprocess_exec` chứ không phải `_shell`.
   Không có chỗ nào cho một chuỗi lạ chen vào. `chay()` chỉ nhận `(ma, goc)` — không có tham số nào
   để nhét một câu lệnh vào, kể cả khi endpoint sơ hở.
3. **Chỉ lệnh chỉ-đọc + biên dịch EA.** Không lệnh nào sửa cấu hình, chạm database hay đụng vị thế:
   những việc đó đã có nút riêng và đi qua đường riêng.
4. **Mọi lệnh có hạn giờ.** Một lệnh treo mà không có hạn giờ là một dashboard treo theo.

**Nút Chạy biên dịch CẢ HAI EA.** Câu lệnh in trên trang chỉ biên dịch Master rồi bảo "chạy lại, đổi
Master thành Client" — đúng loại việc người ta làm sót một nửa, và triệu chứng của nửa bị sót là
"EA Client không kéo được lên chart", một câu không dẫn về đây. `scripts/bien-dich-ea.ps1` tách ra
từ `tro-ly.ps1::buoc_bien_dich` vì bản trong trợ lý hỏi có/không trên stdin, mà một tiến trình con
của dịch vụ thì không trả lời được.

**Mọi nút bất đồng bộ đều khoá lại và nói "Đang chạy…".** Không có nó thì người dùng bấm một nút mất
vài giây, không thấy gì, rồi bấm lại — và với nút Cấp token, bấm lại là một hành động **thật**:
token vừa cấp chết ngay.

Bổ sung cho D-41 (2026-09-22) — **lệnh cần tham số đi qua endpoint, không qua danh sách trắng.**

Ba câu lệnh trên tab Hướng dẫn cần giá trị chỉ người vận hành biết: `sua-agent --login --terminal-title`,
`anh-xa-symbol`, `cau-hinh-client`. Trang trước đây chỉ nói "phải tự gõ" — đúng chỗ một người không
phải dân kỹ thuật dừng lại.

Cho chúng vào `LENH_CHAY_DUOC` là **phá chính bất biến của D-41**: một tiêu đề cửa sổ là chuỗi tự
do, cho nó đi vào `argv` trên một dashboard không có xác thực (D-39) là mở lại đúng cánh cửa vừa
đóng. Ba test đang khoá điều này, và phải nới chúng ra mới làm được — dấu hiệu rõ nhất rằng hướng đi
sai.

Thay vào đó: **form nhỏ ngay trong bước, POST vào endpoint đã có** (`/api/agent/{id}/terminal`,
`/api/symbol_map`). Cùng đường mà tab Cấu hình vẫn dùng, đã kiểm ràng buộc đầy đủ — tiêu đề không
chứa số tài khoản vẫn bị từ chối, bằng đúng câu tiếng Việt cũ. Không sinh tiến trình, không `argv`,
không bề mặt tấn công mới.

**Và mở terminal thật là việc không làm được, không phải việc khó.** Bridge chạy như một Windows
service qua NSSM, tức ở **session 0**; mọi tiến trình con nó sinh ra đều vô hình với người đang ngồi
trước máy. Chính `scripts/tao-dich-vu.ps1:13` đã ghi điều đó — đó là lý do clicker phải là Scheduled
Task chứ không phải service. Thêm `CREATE_NEW_CONSOLE` vào cũng không đổi được gì.

### D-42 — Bản giao cấu hình cho 1 Master + 1 Client; năng lực N Client giữ nguyên bên dưới

Bản gửi khách chỉ cho **1 Master + 1 Client**. Đây không phải cắt tính năng mà là **quay về đúng
phạm vi đã ghi từ đầu** — `docs/ARCHITECTURE.md`: *"1 Master, 1 Client. Nhưng toàn bộ mô hình dữ
liệu và routing phải viết cho N Client ngay từ đầu."* Năng lực N Client giữ lại để bán thêm về sau.

**Cổng chỉ nằm ở giao diện, và đó là một quyết định chứ không phải một sơ sót.** Kho mã này **công
khai** — `CAI-DAT.cmd` tải từ `raw.githubusercontent.com` không cần đăng nhập, và bản cài `git clone`
trọn nguồn về máy khách. Nên **mọi cổng đặt trong mã đều đọc được và gỡ được**, kể cả một giấy phép
ký số: khoá công khai để kiểm chữ ký cũng nằm trong chính mã ấy. Cái dựng ở đây là một **ranh giới
thương mại nhìn thấy được**, không phải một cái khoá, và nói thẳng ra thì tốt hơn là giả vờ ngược
lại.

Hệ quả: `ops.tao_client`, `ops.tao_client_moi`, `POST /api/client`, `POST /api/client_moi` và
`bridge.admin them-client` **không** kiểm giới hạn. Ai biết dòng lệnh vẫn tạo được Client thứ hai.
Chặn sâu hơn chỉ làm phiền chính người bán lúc hỗ trợ khách, mà không cưỡng chế được ai.

**Ba chi tiết đáng ghi:**

1. **Khoá giới hạn cố ý KHÔNG nằm trong `KHOA_SUA_DUOC`.** Danh sách đó là những khoá *khách được
   sửa từ dashboard*, và mọi khoá trong đó hiện thành một ô nhập ở mục Nâng cao — tức là tự mở cổng
   cho khách. Nó có hằng riêng: `ops.SO_CLIENT_MAC_DINH` + `ops.KHOA_GIOI_HAN_CLIENT`.
2. **Đếm Client đang BẬT, không đếm cả Client đã tắt.** Tắt một Client là cách người ta tạm ngừng
   nó, và một chỗ trống thật thì nên dùng lại được.
3. **Giấu thì giấu hẳn — không một chữ nào.** Bản đầu thay khối Thêm Client bằng câu *"liên hệ
   nhà cung cấp để mở thêm"*. Bỏ. Lý do đáng ghi vì nó ngược với D-38: **không ai đi tìm một nút họ
   chưa bao giờ biết là có**, nên câu ấy không gỡ một hoang mang nào — nó chỉ quảng cáo ra rằng có
   một bản đắt hơn, và biến một sản phẩm trọn vẹn thành một bản bị cắt. Ở D-38 có một thứ *biến mất
   khỏi chỗ nó vừa ở* nên im lặng là một câu hỏi; ở đây không có gì biến mất cả.

   Tương tự với tài liệu: phần thêm Client rời `docs/CAI-DAT-VPS.md` sang
   `docs/NOI-BO-nhieu-client.md`. Tài liệu cài đặt mà mô tả một thứ bản của khách không có thì hoặc
   làm họ đi tìm một nút không tồn tại, hoặc quảng cáo hộ.

   **Giới hạn của việc giấu, nói thẳng:** kho công khai và bản cài `git clone` trọn nguồn, nên một
   khách chịu đọc vẫn thấy `ops.SO_CLIENT_MAC_DINH`, thấy chính mục D-42 này, và thấy
   `docs/NOI-BO-nhieu-client.md`. Giấu ở đây chỉ có nghĩa là **không chủ động mời**, không phải là
   che được.

**Mở khoá:** `bridge.admin gioi-han-client <n>`. Không tham số thì in giá trị hiện tại.

**Thứ bảo vệ phần bán-thêm-sau khỏi mục đi:** một test chạy `tao_client_moi` **hai lần** ở đúng cảnh
bản giao (giới hạn 1, đã có `CL-01`) và đòi lần thứ hai ra `CL-02` đầy đủ. Một năng lực giữ lại mà
không ai chạy là một năng lực hỏng trong im lặng. Vì cùng lý do đó, `docs/ACCEPTANCE.md` (ca B-06,
hai Client) và bảng lệnh trong `docs/RUNBOOK.md` **giữ nguyên**.
