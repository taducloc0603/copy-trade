# Phase 9 — Dashboard và cấu hình

## Mục tiêu

Giao diện web phục vụ bởi chính Bridge, dùng được cả khi mất Internet, truy cập từ xa qua Tailscale.

## Điều kiện đầu vào

Phase 8 xong. Toàn bộ logic nghiệp vụ hoạt động, chỉ thiếu mặt người.

---

## Việc cần làm

### 9.1 Nền tảng

FastAPI + WebSocket, phục vụ ở `web_port` (mặc định 8080), bind `0.0.0.0` để truy cập được
qua địa chỉ Tailscale.

- HTML/CSS/JS thuần, không framework nặng. Giao diện này phải mở được nhanh trên điện thoại.
- WebSocket đẩy cập nhật thời gian thực. HTTP chỉ dùng cho tải trang đầu và các thao tác ghi.
- **Toàn bộ dữ liệu đọc thẳng từ SQLite cục bộ.** Không phụ thuộc Internet — đúng lúc mất mạng
  là lúc cần nhìn thấy trạng thái nhất.
- Mọi nhãn hiển thị lấy từ `bridge/labels_vi.py` (D-16). Không viết chuỗi tiếng Việt
  trực tiếp trong template.

Xác thực: mật khẩu đơn giản đặt trong `config.toml`, session cookie. Tailscale đã lo phần mạng,
nhưng vẫn cần một lớp để tránh người khác trong mạng nội bộ mở được.

### 9.2 Màn hình chính

Từ trên xuống:

**Thanh trạng thái.** Chế độ vận hành hiển thị nổi bật bằng nhãn tiếng Việt.
Trạng thái từng agent: kết nối / mất kết nối / mất kết nối sàn. Đồng hồ.

Với agent role `CLICKER`, nhãn "mất kết nối sàn" mang nghĩa khác: **không điều khiển được
giao diện** (D-25). Hiển thị thêm thời điểm canary chạy thành công gần nhất — một clicker
ONLINE nhưng canary đã cũ vài phút là dấu hiệu sắp hỏng, và đó chính là loại trạng thái
"trông vẫn khoẻ" mà `broker_connected` sinh ra để bắt.

**Bốn ô chỉ số.** Độ trễ copy p50, độ trễ copy p95, số cặp đang hedge, số cặp cần can thiệp.

> Độ trễ copy là khoảng cách từ lúc Master khớp tới lúc Client khớp — không phải độ trễ mạng.
> Đó mới là con số quy ra tiền. Hiển thị dạng phân vị trong phiên, không phải giá trị tức thời:
> một lần trễ 3 giây trong 200 lệnh là dấu hiệu cần điều tra, nhưng nhìn giá trị hiện tại
> thì nó đã trôi qua từ lâu.

> Ô "cần can thiệp" chỉ tô đỏ khi khác 0. Nếu luôn đỏ, mắt sẽ quen và bỏ qua.

**Bảng cặp lệnh.** Cột: Cặp, Symbol, Chiều (`BUY→SELL`), Vol M/C (`1.00 / 0.50`), Trạng thái.

- Cặp mở qua giao diện mà `client_open_reason` khác `CLIENT` phải nổi bật — đó là dấu hiệu
  phase 6b đã ngừng hoạt động, không phải một sai lệch giao dịch thông thường.

- **Sắp theo mức nghiêm trọng, không theo thời gian.** `ORPHANED` và `OPEN_FAILED` lên đầu,
  rồi `PARTIALLY_CLOSED`, rồi `OPEN`. Khi có 40 cặp và 2 cặp mất hedge, sắp theo thời gian
  sẽ chôn hai cặp cần cứu xuống giữa danh sách.
- Pair ID rút gọn còn hậu tố, bấm vào mở chi tiết kèm toàn bộ lịch sử event của cặp đó.
- `ORPHANED` hiển thị kèm bên nào còn vị thế: "Mất hedge — còn Master" và "Mất hedge — còn Client".
  Hành động xử lý hai trường hợp khác hẳn nhau.
- **Không hiển thị lãi lỗ.** Đây là công cụ đồng bộ hedge, không phải terminal giao dịch.
  Số P&L đã có sẵn trong MT5, và đưa lên đây chỉ mời gọi can thiệp tay vào những cặp đang chạy đúng.

**Cụm nút điều khiển.** Ma sát tăng dần theo mức nguy hiểm:

| Nút | Ma sát |
|---|---|
| Tạm dừng lệnh mới | Bấm thẳng, vô hại, hoàn tác được |
| Dừng toàn bộ đồng bộ | Hộp xác nhận, vì nó bỏ rơi các cặp đang chạy |
| Đóng khẩn cấp tất cả | Bắt gõ tay chuỗi `DONG TAT CA` |

Nút khẩn cấp đặt **tách khỏi** cụm nút thường ngày, căn về phía đối diện, viền đỏ.
Đặt cạnh nhau là sớm muộn cũng có ngày bấm nhầm.

> Chuỗi xác nhận cố ý **không dấu**. Bắt gõ tiếng Việt có dấu trong lúc hoảng,
> với bộ gõ có thể đang ở chế độ khác, là tự tạo thêm rắc rối.

### 9.3 Màn hình xử lý sai lệch

Đây là màn hình quan trọng nhất mà hầu hết công cụ loại này bỏ qua.

Ba nguyên tắc:

**Hiển thị bằng chứng, không chỉ kết luận.** Mỗi dòng phải cho thấy cả ba nguồn: DB nói gì,
Master thực tế có gì, Client thực tế có gì. Người vận hành đang quyết định chuyện tiền bạc —
đưa cho họ một dòng "Cặp 118 bất thường" là bắt họ tin bot một cách mù quáng.

**Tách theo mức an toàn, không theo loại lỗi.** Nhóm SAFE là những sai lệch mà hành động
khắc phục chỉ có đóng lệnh hoặc sửa sổ sách — chấp nhận hàng loạt được bằng một nút.
Nhóm DECISION dính tới mở lệnh hoặc đóng Master, xử lý từng dòng.

**Không có nút "bỏ qua tất cả".** Bỏ qua là hành động cho từng dòng, và mỗi dòng bị bỏ qua
để lại một alert tồn tại. Nút bỏ qua hàng loạt là cách mất tiền âm thầm nhất.

Nút "Bắt đầu copy" ở cuối vẫn bấm được kể cả khi còn finding chưa xử lý — nhưng mở hộp xác nhận
liệt kê chính xác những mục đang bỏ lại. Khoá nút thì người ta sẽ đi tìm cách lách; cho bấm
nhưng bắt nhìn thẳng vào cái mình đang bỏ qua thì hiệu quả hơn.

Với finding `UNPAIRED_MASTER`, một trong các lựa chọn là "Tạo cặp và copy sang Client".
Đây là **ngoại lệ duy nhất** với luật "không tự động mở" (D-13) — nó không phải tự động,
có người nhìn bằng chứng và quyết định. Vì vậy hành động này chỉ tồn tại ở màn hình này,
không bao giờ nằm trong luồng xử lý tự động.

### 9.4 Trang cấu hình

Vấn đề lớn nhất không phải bố cục mà là **thời điểm có hiệu lực**.

- Mỗi trường đổi được phải mang nhãn hiệu lực ngay bên cạnh. Hệ số volume ghi rõ:
  "Chỉ áp dụng cho lệnh mở sau khi lưu. Các cặp đang chạy giữ nguyên tỷ lệ." (FR-06)
- Ô hệ số volume có dòng xem trước tính ngay tại chỗ, **hiển thị cả trường hợp thất bại**:
  "Master 1.00 → Client 0.50 · Master 0.03 → 0.015, dưới mức tối thiểu 0.01 → bỏ qua lệnh".
  Nhìn trường hợp đẹp thì ai cũng thấy ổn; chỉ khi thấy dòng thứ hai người ta mới nhận ra
  hệ số 0.50 sẽ làm rơi mọi lệnh nhỏ.
- Công tắc "Master đóng thì Client đóng" hiển thị **dạng chữ, không phải nút gạt**.
  FR-13 nói đây là chức năng bắt buộc; đưa nó thành nút bấm được là mời gọi tắt nhầm.
  Thứ không được phép tắt thì không nên trông giống thứ tắt được.
- Công tắc `can_close_master` cần hộp xác nhận nêu rõ hậu quả cascade, và cảnh báo đậm hơn
  khi nhóm có nhiều hơn một Client.

Trang cấu hình Client cần thêm ô **`open_route`** (`EA` / `UI`). Đổi sang `UI` bắt buộc phải
chỉ đích danh một clicker đang ONLINE, và phải có hộp xác nhận nêu rõ: thông lượng giảm còn
khoảng một lệnh mỗi 2–4 giây, và độ trễ copy tăng từ vài trăm mili giây lên vài giây.

> **Thêm sau phase 11:** cần cả ô **`close_route`** bên cạnh, vì nó chính là thứ quyết định deal
> đóng mang `CLIENT` hay `EXPERT`. Hiện `close_route` **đã hiện** trên trang cấu hình nhưng vẫn ở
> mức đọc (B-05), giống `open_route`. Hộp xác nhận khi bật `UI` phải nói thêm: đóng lệnh chậm hơn
> đường EA khoảng 16 lần (đo được 5,1–5,9 giây), và clicker trở thành điểm nghẽn của **cả hai**
> đường vì nó xử lý một lệnh tại một thời điểm.

**Bảng ánh xạ symbol** phải có nút kiểm tra thực sự gọi xuống agent để xác nhận symbol tồn tại
trên sàn Client và lấy về spec. **Không cho lưu mapping chưa kiểm tra** (`verified_at` NULL).

> Gõ nhầm `XAUUSDm` thành `XAUUSDn` xảy ra thường xuyên, và hậu quả là phát hiện ra vào đúng lúc
> Master vừa vào lệnh. Nguy hiểm hơn: tên copy từ website broker có thể chứa ký tự Cyrillic
> nhìn giống hệt chữ Latin. Chỉ có kiểm tra với sàn mới bắt được.

### 9.5 Trang nhật ký

Danh sách alert lọc theo mức và theo khoảng thời gian, có nút xác nhận đã xử lý.
Trang tra cứu lịch sử event theo `pair_id` hoặc `position_id`.

---

## Kiểm tra lại phần cũ

- [ ] Toàn bộ test phase 1–3, 6, 7, 8 xanh. Dashboard không được làm đổi hành vi nghiệp vụ nào.
- [ ] Đặc biệt: các thao tác từ giao diện phải gọi đúng API của phase 8,
      không viết lại logic. Nếu thấy mình đang viết SQL cập nhật `pair` trong tầng web,
      đó là dấu hiệu sai — quay lại dùng hàm ở `bridge/engine/`.
- [ ] Chạy lại kịch bản hỗn loạn của phase 8, lần này quan sát qua dashboard.

## Kiểm tra phần mới

- [ ] Mở dashboard từ máy khác qua địa chỉ Tailscale.
- [ ] Ngắt Internet của máy Bridge (giữ mạng LAN) → dashboard vẫn hoạt động đầy đủ.
- [ ] Mọi trạng thái hiển thị bằng tiếng Việt. `grep -rn` trong template không tìm thấy
      chuỗi enum tiếng Anh nào bị lọt ra giao diện.
- [ ] Thêm một enum mới vào DB mà quên nhãn → hiển thị chính enum đó, ghi WARNING, **không sập trang**.
- [ ] Bảng cặp lệnh sắp đúng: tạo 20 cặp `OPEN` và 1 cặp `ORPHANED` → cặp `ORPHANED` ở dòng đầu.
- [ ] Ô "cần can thiệp" bằng 0 → không tô đỏ.
- [ ] Nút "Đóng khẩn cấp tất cả" không thực hiện gì cho tới khi gõ đúng `DONG TAT CA`.
- [ ] Gõ sai chuỗi xác nhận → không thực hiện, không có command nào sinh ra.
- [ ] Màn hình sai lệch hiển thị đủ ba nguồn dữ liệu cho mỗi dòng.
- [ ] `accept_all_safe` từ giao diện không động tới dòng `DECISION` nào.
- [ ] Không tìm thấy nút nào bỏ qua hàng loạt.
- [ ] Bấm "Bắt đầu copy" khi còn finding → hộp xác nhận liệt kê đúng số mục còn lại.
- [ ] Lưu mapping symbol chưa kiểm tra → bị từ chối.
- [ ] Kiểm tra một symbol không tồn tại trên sàn Client → báo lỗi rõ ràng, không lưu.
- [ ] Kiểm tra một symbol có ký tự Cyrillic trà trộn → bị bắt.
- [ ] Đổi `volume_multiplier` khi đang có cặp chạy → cặp cũ giữ nguyên `effective_multiplier`.
      Kiểm tra trong DB, không chỉ trên màn hình.
- [ ] Bật `can_close_master` → có hộp xác nhận nêu hậu quả.
- [ ] WebSocket: mở lệnh trên demo, dashboard cập nhật trong dưới 1 giây mà không cần tải lại trang.
- [ ] Mở dashboard trên điện thoại, bảng cặp lệnh vẫn đọc được.

## Tiêu chí hoàn thành

Một người chưa từng đọc code có thể ngồi trước dashboard, hiểu hệ thống đang ở trạng thái nào,
phát hiện được cặp nào có vấn đề, và xử lý được một danh sách sai lệch sau khởi động lại —
mà không cần mở terminal hay đọc log.

## Không làm ở phase này

Không sửa logic nghiệp vụ. Nếu phát hiện thiếu sót ở tầng engine, ghi vào `PROGRESS.md`
và sửa ở đó chứ không vá tạm trong tầng web.
