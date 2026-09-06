# RUNBOOK — vận hành MT5 Copy Bridge

*Chốt ngày 2026-09-06 (Phase 10), cập nhật sau Phase 11. Đọc `docs/DECISIONS.md` trước nếu bạn định sửa hành vi;
tài liệu này chỉ nói cách **chạy**.*

---

## 0. Điều quan trọng nhất, đọc trước tiên

**Hệ thống luôn khởi động ở `run_mode = PAUSED`, không có ngoại lệ** (D-15). Kể cả khi máy tự
bật lại lúc 3 giờ sáng sau khi mất điện. Nếu DB đang ghi `RUNNING`, Bridge sẽ **đặt lại về
`PAUSED`** và sinh alert `KHOI_DONG_EP_PAUSED`.

Nghĩa là: **sau mỗi lần khởi động lại, phải có người bấm `RUNNING` bằng tay.** Đó là chủ đích,
không phải thiếu sót. Thứ tệ nhất sau một sự cố là hệ thống tự hồi sinh và bắt đầu vào lệnh khi
chưa ai kịp nhìn màn hình.

**Nút dừng khẩn cấp** nằm ở dashboard, phải gõ đúng cụm `DONG TAT CA` để xác nhận. Người vận
hành phải biết cách bấm nó **trước khi** cần dùng tới.

---

## 1. Kiến trúc chạy — ba tiến trình

| Tiến trình | Chạy ở đâu | Vai trò |
|---|---|---|
| **Bridge** (`python -m bridge`) | Máy Bridge | TCP server 8787, dashboard 8080, toàn bộ logic. |
| **EA** (`CopyBridgeClient.mq5`, `CopyBridgeMaster.mq5`) | Trong mỗi terminal MT5 | Gửi event, thực thi lệnh **ĐÓNG**. Client mở được lệnh, **Master thì không** — xem D-01. |
| **clicker** (`python -m clicker`) | Cùng phiên đăng nhập Windows với terminal Client | Mở lệnh qua hộp thoại New Order (D-21, D-22, D-26). |

Bridge là server, hai cái kia là client. MQL5 không listen được (D-03).

> **clicker KHÔNG chạy được như Windows Service.** Service nằm ở session 0 và không thấy cửa sổ
> của phiên người dùng. Nó phải là **Scheduled Task theo phiên đăng nhập**, kèm autologon và tắt
> sleep/hibernate. Bridge thì chạy service bình thường.

---

## 2. Cài đặt

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item config.example.toml config.toml     # roi dien gia tri that
```

`config.toml` nằm trong `.gitignore`. Các khoá:

```toml
[bridge]
host = "127.0.0.1"      # MAC DINH: chi may nay cham duoc
port = 8787             # agent
web_port = 8080         # dashboard
db_path = "data/bridge.db"

[security]
dashboard_password = "..."
telegram_token   = ""    # de trong thi kenh canh bao im lang, khong loi
telegram_chat_id = ""
```

> **Bridge sẽ TỪ CHỐI khởi động** nếu `host` không phải loopback mà `dashboard_password` để
> trống. Không có mật khẩu thì dashboard không bắt đăng nhập, và khi đó bất kỳ ai chạm được tới
> cổng 8080 đều bấm được nút đóng khẩn cấp — kiểm toán 2026-09-06 đã gọi `/api/emergency` không
> kèm cookie và nó đóng sạch 3 cặp. Muốn agent từ máy khác nối vào thì đặt `host = "0.0.0.0"`
> **và** đặt mật khẩu.

Gắn EA lên chart của **cả hai** terminal, điền token vào tham số EA (mục 4).

> **Sau khi biên dịch lại EA, phải GỠ EA khỏi chart rồi GẮN LẠI.** Đổi khung thời gian chỉ gọi
> lại `OnInit` trên bản đã nạp trong bộ nhớ — MT5 **không** đọc lại `.ex5` từ đĩa. Dấu hiệu nạp
> đúng bản mới: tab Experts hiện `CopyBridgeMaster khoi dong [co kha nang DONG lenh]`.
>
> Biên dịch không cần mở giao diện MetaEditor:
> `& "C:\Program Files\MetaTrader 5 1\MetaEditor64.exe" /compile:"<duong-dan>.mq5" /log:"<log>"`

---

## 3. Khởi động và dừng

```powershell
.\.venv\Scripts\python.exe -m bridge                      # Bridge + dashboard
.\.venv\Scripts\python.exe -m clicker --token <TOKEN> --account-login 538217
```

Thứ tự **quan trọng** khi hàng đợi của EA đang có event cũ:

1. Bật Bridge **khi `run_mode` vẫn là `PAUSED`**. Backlog trong outbox của EA chảy vào và được
   ghi nhận `IGNORED`. Đây là cách sạch nhất để dọn hàng đợi mà không sinh lệnh nào.
2. Bật clicker, **kiểm canary xanh** trên dashboard trước khi đi tiếp.
3. Chờ 0 event `PENDING`, rồi mới đặt `RUNNING`.

Bật `RUNNING` trước bước 3 thì event cũ bị từ chối bằng `EVENT_TOO_OLD` thay vì `IGNORED` —
không sai, nhưng sinh alert nhiễu.

Dừng: `Ctrl+C` (bắt `SIGINT`/`SIGTERM`, đóng sạch và đánh mọi agent về `OFFLINE`).

---

## 4. Lệnh vận hành

Toàn bộ qua `python -m bridge.admin`. **Không sửa DB bằng tay**, và không viết script tạm nữa —
món nợ đó đã một lần làm mất token của clicker.

```powershell
.\.venv\Scripts\python.exe -m bridge.admin liet-ke
.\.venv\Scripts\python.exe -m bridge.admin them-agent AG-CLICKER --role CLICKER --magic 770001 --login 538217
.\.venv\Scripts\python.exe -m bridge.admin cap-token AG-CLIENT
.\.venv\Scripts\python.exe -m bridge.admin thu-hoi AG-CLICKER
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01                  # xem
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01 --multiplier 0.5
.\.venv\Scripts\python.exe -m bridge.admin run-mode              # xem
.\.venv\Scripts\python.exe -m bridge.admin run-mode RUNNING      # dat
.\.venv\Scripts\python.exe -m bridge.admin sao-luu
.\.venv\Scripts\python.exe -m bridge.admin bao-tri               # retention + sao luu + don ban cu
.\.venv\Scripts\python.exe -m bridge.admin kiem-reason           # TEST-23
```

**Token thô chỉ hiện đúng một lần** và không đi vào log. Mất thì cấp lại — không có đường đọc
lại. `thu-hoi` không xoá dòng agent (sẽ mất lịch sử); nó đặt hash thành giá trị không token nào
sinh ra được và tắt `enabled`. `cap-token` **bật lại** agent đã thu hồi — cấp token là hành động
có chủ đích để nó nối lại được.

Đổi cấu hình giao dịch bằng `cau-hinh-client`, đừng `UPDATE` tay. Cặp **đang chạy** giữ nguyên tỷ
lệ cũ; giá trị mới chỉ áp cho lệnh mới (D-19).

Đặt `bao-tri` chạy hằng ngày bằng Scheduled Task. Nó chạy retention (D-17), `VACUUM INTO` một
bản sao lưu, giữ 14 bản gần nhất, rồi **tự mở lại bản vừa tạo để kiểm chứng** — vì một bản sao
lưu chưa từng khôi phục thử thì không phải bản sao lưu.

---

## 5. Xem log và trạng thái

Log: `logs/bridge.log`, xoay vòng theo ngày, giữ 30 ngày, UTF-8. Có bộ lọc che token —
`grep -ri "token" logs/` phải ra rỗng (kiểm ngày 2026-09-06: 0 dòng trên ~15.000 dòng log).

Dashboard `http://<dia-chi-tailscale>:8080` là nơi nhìn trạng thái. Ba thứ nhìn trước tiên:
`run_mode`, canary của clicker, và số finding đối chiếu đang chờ.

---

## 5b. Triển khai tất cả trên MỘT VPS

Đây là kiến trúc đơn giản nhất và cũng là kiến trúc **khác** với mục 6 bên dưới: Bridge, cả hai
terminal MT5 và clicker cùng nằm trên một máy. Mục 6 viết cho kiến trúc nhiều máy — khi chạy
một-VPS thì phần lớn nó **không áp dụng**, nhưng đổi lại có ba rủi ro mới.

### Cái gì biến mất

Agent nối tới Bridge qua `127.0.0.1`, nên đặt `host = "127.0.0.1"` là **đóng hẳn** cả 8787 lẫn
8080 với thế giới bên ngoài — không cần Tailscale ACL, không cần luật firewall, không cần máy thứ
ba để kiểm. Đo trên máy phát triển: `host = "0.0.0.0"` cho `netstat` ra
`0.0.0.0:8787 LISTENING`, tức mở ra toàn mạng; `127.0.0.1` thì không.

Cái giá: dashboard chỉ mở được **từ trong VPS**. Muốn xem từ máy khác thì hoặc RDP vào rồi mở
trình duyệt trên đó, hoặc cài Tailscale và đặt `host = "0.0.0.0"` **kèm mật khẩu mạnh** (Bridge
sẽ từ chối khởi động nếu thiếu — xem mục 2).

### Ba rủi ro mới

1. **Phiên RDP ngắt (B-08) — nghiêm trọng nhất.** Cách vận hành VPS bình thường là RDP vào rồi
   ngắt ra, và từ giây đó mọi lệnh mở đều đi qua một cơ chế **chưa ai chứng minh là còn chạy**.
   Phải đo trước khi tin: ngắt phiên RDP (đóng cửa sổ, **không** Sign out), rồi kiểm qua database
   xem lệnh tiếp theo có được copy không.
2. **Algo Trading tắt (B-09).** Đường mở phía Client đi qua giao diện nên **không cần** Algo
   Trading; đường đóng đi qua EA nên **cần**. Terminal có Algo Trading tắt vẫn mở lệnh bình
   thường rồi mới hỏng lúc đóng. Bridge hiện **không nhìn thấy** trạng thái này. Sau mỗi lần VPS
   khởi động lại hoặc MT5 tự cập nhật: kiểm nút **Algo Trading** sáng xanh trên **cả hai**
   terminal.
3. **Hai tài khoản, một địa chỉ IP.** Hai tài khoản mở vị thế ngược chiều, cùng symbol, cách nhau
   dưới một giây, từ cùng một IP là một dấu vết rất dễ nhận. Nhiều broker cấm hoặc huỷ lợi nhuận
   từ mô hình này. Đây là rủi ro **điều khoản**, không phải rủi ro kỹ thuật, và nó không hiện ra
   trong bất kỳ log nào cho tới lúc tài khoản bị xử lý.

### Cấu hình máy

Đo thực tế lúc chạy không tải: mỗi terminal MT5 ~157 MB, Bridge ~49 MB, clicker ~4 MB. Cộng
Windows Server thì **4 GB RAM là mức nên có**, 2 GB sẽ chật. CPU 2 nhân là đủ — đường mở bị chặn
ở tốc độ giao diện MT5 (~600 ms/lệnh), không phải ở CPU.

Bắt buộc: **autologon**, **tắt sleep/hibernate**, và **tắt khoá màn hình tự động** — clicker phải
sống trong một phiên người dùng đang tồn tại.

### Khác biệt so với mục 6

| Mục 6 nói | Khi chạy một-VPS |
|---|---|
| Tailscale ACL cho 8787 | Không cần — agent đi loopback |
| Firewall chặn 8787/8080 | Thay bằng `host = "127.0.0.1"` |
| Kiểm bằng máy thứ ba | Không cần, nếu đã bind loopback |
| Bridge chạy Windows Service | Vẫn nên, để tự bật sau reboot |
| clicker chạy Scheduled Task theo phiên | **Bắt buộc**, kèm autologon |

---

## 6. Mạng và bảo mật cho kiến trúc NHIỀU MÁY — **CHƯA LÀM**

> Chạy tất cả trên một VPS thì đọc **mục 5b** thay cho mục này; phần lớn mục 6 không áp
> dụng, và mục 5b nói rõ chỗ nào thay bằng gì.

Những mục dưới đây **chưa được thực hiện hay kiểm chứng** ở lượt này vì cần môi trường thật
(máy thứ ba, VPS, quyền quản trị mạng):

- [ ] Cài Tailscale trên máy Bridge và các node agent; ghi địa chỉ `100.x.y.z` vào đây.
- [ ] Tailscale ACL: chỉ node agent chạm được 8787, chỉ máy quản trị chạm được 8080.
- [ ] Firewall Windows: chặn 8787 và 8080 trên **mọi** interface trừ interface Tailscale và
      loopback. Không bao giờ mở ra Internet công cộng.
- [ ] Kiểm bằng **máy thứ ba**: cả hai port không truy cập được từ ngoài Tailscale.
- [ ] Đăng ký Bridge làm Windows Service (NSSM hoặc `pywin32`), tự khởi động khi máy bật.
- [ ] Đăng ký clicker làm **Scheduled Task theo phiên đăng nhập** + autologon + tắt sleep.
- [ ] Kiểm: giết tiến trình Bridge → dịch vụ tự bật lại, và bật lại ở `PAUSED`.
- [ ] Kiểm: Telegram nhận alert CRITICAL trong vài giây; chặn mạng tới Telegram → luồng giao
      dịch không chậm hay lỗi (đã có test tự động cho vế sau, chưa gửi tin thật lần nào).

> Tailscale xác thực **máy**, không xác thực terminal hay tài khoản MT5 nào đang gửi lệnh. Token
> ở tầng ứng dụng vẫn bắt buộc, không bỏ được.

---

## 7. Sự cố thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| Master vào lệnh mà Client không copy | `run_mode = PAUSED`, hoặc clicker chưa chạy / canary đỏ | Xem dashboard. Clicker `DEGRADED` thì **cố ý không copy** và không rơi về đường EA (D-25). |
| Alert `UI_OPEN_BUSY` | Hai lệnh Master trong ~600 ms; mỗi Client chỉ cho **một** `OPEN_UI` đang bay | Lệnh sau **bị bỏ** — đây là mất hedge thật, nên nó ở mức ERROR và đi ra Telegram. Kiểm và mở bù bằng tay. |
| Alert `ORPHANED_MASTER` | Client đóng khi `can_close_master = 0` (D-20) | Đúng thiết kế. Quyết định bằng tay: đóng Master hay mở lại Client. |
| Agent `DEGRADED` | Terminal mất kết nối broker nhưng EA còn sống | Bridge **ngừng gửi command** cho agent đó. Chờ terminal nối lại. |
| Alert `TRADE_NOT_ALLOWED` | Algo Trading TẮT trên terminal của agent đó | Bật nút **Algo Trading**. Đường MỞ qua giao diện vẫn chạy nhưng đường ĐÓNG sẽ hỏng — đừng bỏ qua. |
| Alert `CLIENT_TRADE_NOT_ALLOWED` | Bridge **từ chối mở lệnh mới** vì Client không đóng được | Đúng thiết kế: đừng mở cái không đóng được. Bật Algo Trading rồi copy chạy lại. |
| Alert `FINDING_BO_QUEN` | Có sai lệch nằm chờ quá `finding_nhac_sau_phut` (mặc định 60) | Mở dashboard, xử lý từng finding. Đặt khoá này về 0 để tắt nhắc. |
| Finding đối chiếu đang chờ | Sổ sách lệch với thực tế trên terminal | Mở finding trên dashboard, đọc `evidence_json` (có đủ ba nguồn) rồi mới `accept`. Không accept khi chưa đọc bằng chứng. |
| EA gửi bù lặp không dứt | Đã sửa ở Phase 10: trần 3 lần cho mỗi mốc `from_seq` | Nếu tái diễn, xem `bridge/protocol/server.py`. |
| Lệnh mở bị từ chối vì symbol lệch | Hộp thoại New Order lấy symbol theo chart đang mở | **Giới hạn đã biết** (`BACKLOG.md` B-01): mỗi terminal Client copy được một symbol. Mở đúng chart đó. |

---

## 8. Trước khi chuyển sang tài khoản thật

> Kế hoạch chi tiết theo thứ tự nên làm nằm ở **`docs/KE-HOACH-CHAY-THAT.md`**. Mục này là bản
> rút gọn của các điều kiện.


Đây là điều kiện vận hành, không phải checklist kỹ thuật. Không mục nào được bỏ.

1. **Chạy ổn định trên demo ít nhất một tuần liên tục** trước khi động vào tiền thật.
2. **Hoàn thành toàn bộ mục 6** ở trên. Hiện chưa mục nào được kiểm chứng.
3. **Chạy TEST-19 thật** — rút điện hoặc tắt máy ảo đột ngột, rồi kiểm không mất event và bộ đối
   chiếu bắt đúng sai lệch. Đây là lý do `synchronous = FULL` tồn tại, và hiện nó **chưa từng
   được chứng minh bằng quan sát** (`BACKLOG.md` B-02).
4. **Đọc điều khoản của cả hai broker** về hedging, bonus, giao dịch nhiều tài khoản và copy
   trading. Một số broker cấm hoặc huỷ lợi nhuận từ các mô hình này.
5. **Đối chiếu tay khác biệt giữa hai sàn:** tên symbol, contract size, volume tối thiểu và bước
   volume, spread và giá báo, thời gian khớp lệnh, giờ giao dịch từng symbol.
6. **Bắt đầu bằng volume nhỏ nhất có thể và một symbol duy nhất.** Mở rộng dần sau khi quan sát
   ít nhất vài chục lệnh.
7. **Người vận hành phải biết cách bấm dừng khẩn cấp trước khi cần dùng tới nó.** Thử một lần
   trên demo.
8. Biết rõ những gì **chưa từng chạy trên sàn thật** — `docs/ACCEPTANCE.md` cột "Nguồn", mọi
   dòng ghi TEST hoặc KHÔNG.
9. **Nếu chạy một VPS:** xong bài "phiên RDP đã ngắt" (B-08) và kiểm Algo Trading bật ở cả hai
   terminal (B-09). Mục 5b nói cách làm.
