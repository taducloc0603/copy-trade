# RUNBOOK — vận hành MT5 Copy Bridge

*Cập nhật 2026-09-17 (sau phase 12). Cài đặt và cập nhật: [CAI-DAT-VPS.md](CAI-DAT-VPS.md). Đọc
[DECISIONS.md](DECISIONS.md) trước nếu định sửa hành vi; tài liệu này nói cách **chạy** và **xử lý sự cố**.*

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

## 1. Kiến trúc chạy — ba tiến trình, hoặc **bốn** khi bật đường đóng Master qua giao diện

| Tiến trình | Chạy ở đâu | Vai trò |
|---|---|---|
| **Bridge** (`python -m bridge`) | Máy Bridge | TCP server 8787, dashboard 8080, toàn bộ logic. |
| **EA** (`CopyBridgeClient.mq5`, `CopyBridgeMaster.mq5`) | Trong mỗi terminal MT5 | Gửi event; thực thi lệnh **ĐÓNG phía Master**, và phía Client khi `close_route = 'EA'` hoặc khi clicker hỏng (D-28). |
| **clicker** (`python -m clicker`) | Cùng phiên đăng nhập Windows với terminal Client | Mở lệnh qua hộp thoại New Order (D-21, D-22, D-26) và **đóng lệnh** khi `close_route = 'UI'` (D-21b, D-30). |

Bridge là server, hai cái kia là client. MQL5 không listen được (D-03).

> **clicker KHÔNG chạy được như Windows Service.** Service nằm ở session 0 và không thấy cửa sổ
> của phiên người dùng. Nó phải là **Scheduled Task theo phiên đăng nhập**, kèm autologon và tắt
> sleep/hibernate. Bridge thì chạy service bình thường.

---

## 2. Cấu hình

> Các bước **cài đặt** không nằm ở đây — xem [CAI-DAT-VPS.md](CAI-DAT-VPS.md). Mục này chỉ giải thích các khoá cấu hình và **vì sao**
> chúng như vậy — thứ bạn cần khi đang vận hành, không phải khi đang cài.

**Cấu hình nằm hai chỗ, và ranh giới là "có cần trước khi Bridge chạy không" (D-32):**

| Nằm ở | Gồm những gì | Sửa bằng |
|---|---|---|
| **Database** | agent (số tài khoản, magic, tiêu đề cửa sổ terminal của clicker), `client_account` (chiều copy, hệ số, đường mở/đóng, đóng ngược Master), `symbol_map`, `system_config` | Dashboard tab **Cấu hình**, hoặc `bridge.admin`. Có hiệu lực ngay |
| **`config.toml`** | `host`, `port`, `web_port`, `db_path`, `dashboard_password`, Telegram, **token** của hai clicker | Dashboard tab **Cấu hình** (kiểm lại rồi mới ghi, sao lưu bản cũ) hoặc mở file. Có hiệu lực **sau khi khởi động lại dịch vụ** |

**Thứ tự ưu tiên của clicker: tham số dòng lệnh > `config.toml` > giá trị Bridge giao.** Nghĩa
là một `account_login` hay `terminal_title` còn sót trong `config.toml` sẽ **âm thầm đè** giá trị
khai trên dashboard — sửa trên trang mà không thấy gì đổi thì kiểm chỗ này trước. Trang Cấu hình
hiện hai khoá đó kèm cảnh báo khi file còn khai chúng.

Mỗi lần lưu từ dashboard để lại một bản `config.toml.bak-<ngày-giờ>` cạnh file gốc, **giữ 5 bản
gần nhất**. Chúng là bản rõ của mật khẩu và token, nên đừng chép chúng đi đâu.

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

[clicker]                # CHI token. So tai khoan va tieu de cua so nam trong DB (D-32).
token = "..."
account_login = <so-tai-khoan-Client>   # so tai khoan Client
terminal_title = "<so-tai-khoan-Client>"  # mau tieu de cua so terminal Client
```

> **Đừng truyền token clicker bằng `--token`.** Dòng lệnh của một tiến trình là thứ mọi tài
> khoản trên cùng máy đọc được bằng `Get-CimInstance Win32_Process`, mà clicker chạy 24/7.
> Thứ tự ưu tiên: `--token` > biến môi trường `COPYBRIDGE_CLICKER_TOKEN` > mục này.

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

Trên VPS mọi thứ chạy nền (bảng thành phần ở đầu [CAI-DAT-VPS.md](CAI-DAT-VPS.md)):

```powershell
Restart-Service CopyBridge                                          # Bridge + dashboard
Get-ScheduledTask -TaskPath '\CopyBridge\' | Where-Object TaskName -like 'Clicker*' | Stop-ScheduledTask
Get-ScheduledTask -TaskPath '\CopyBridge\' | Where-Object TaskName -like 'Clicker*' | Start-ScheduledTask
```

Chạy tay để gỡ lỗi (dừng dịch vụ/tác vụ tương ứng trước): `.\.venv\Scripts\python.exe -m bridge`,
`.\.venv\Scripts\python.exe -m clicker` (đọc mục `[clicker]`), `... -m clicker --muc clicker_master`.

Thứ tự **quan trọng** khi hàng đợi của EA đang có event cũ:

1. Bật Bridge **khi `run_mode` vẫn là `PAUSED`**. Backlog trong outbox của EA chảy vào và được
   ghi nhận `IGNORED`. Đây là cách sạch nhất để dọn hàng đợi mà không sinh lệnh nào.
2. Bật clicker, **kiểm canary xanh** trên dashboard trước khi đi tiếp.
3. Chờ 0 event `PENDING`, rồi mới đặt `RUNNING`.

Bật `RUNNING` trước bước 3 thì event cũ bị từ chối bằng `EVENT_TOO_OLD` thay vì `IGNORED` —
không sai, nhưng sinh alert nhiễu.

Dịch vụ dừng sạch qua Ctrl+C (NSSM gửi sự kiện console), đánh mọi agent về `OFFLINE`.

---

## 4. Lệnh vận hành

Toàn bộ qua `python -m bridge.admin`. **Không sửa DB bằng tay**, và không viết script tạm nữa —
món nợ đó đã một lần làm mất token của clicker.

```powershell
.\.venv\Scripts\python.exe -m bridge.admin tinh-hinh                            # co gi can lam khong
.\.venv\Scripts\python.exe -m bridge.admin liet-ke
.\.venv\Scripts\python.exe -m bridge.admin them-agent AG-CLICKER --role CLICKER --magic 770001
# KHONG can --login: EA tu bao so tai khoan luc bat tay dau tien, con clicker thi nhan tu Bridge.
.\.venv\Scripts\python.exe -m bridge.admin cap-token AG-CLIENT
.\.venv\Scripts\python.exe -m bridge.admin thu-hoi AG-CLICKER
.\.venv\Scripts\python.exe -m bridge.admin them-client CL-01 --agent AG-CLIENT --clicker-agent AG-CLICKER
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01                  # xem
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01 --multiplier 0.5
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01 --close-route UI  # dong qua giao dien
# Terminal ma mot clicker phai lai. Khai tren dashboard cung duoc, va la duong chinh (D-32).
.\.venv\Scripts\python.exe -m bridge.admin sua-agent AG-CLICKER --login 538217 --terminal-title "538217"
# Hai co deu tuy chon, nhung phai co it nhat mot.
.\.venv\Scripts\python.exe -m bridge.admin run-mode              # xem
.\.venv\Scripts\python.exe -m bridge.admin run-mode RUNNING      # dat
.\.venv\Scripts\python.exe -m bridge.admin sao-luu
.\.venv\Scripts\python.exe -m bridge.admin bao-tri               # retention + sao luu + don ban cu
.\.venv\Scripts\python.exe -m bridge.admin kiem-reason           # TEST-23
# Danh dau DA XEM alert cu theo ma. Mac dinh chi dem; them --that de ghi. Khong dung finding.
.\.venv\Scripts\python.exe -m bridge.admin xac-nhan-alert --code FINDING_BO_QUEN --truoc 2026-09-11T16:30:00+07:00
# Duong DONG phia Master (phase 12). Mac dinh EA; bat UI can clicker thu hai lai terminal Master.
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-master                                    # xem
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-master --clicker-agent AG-CLICKER-MASTER --close-route UI
```

> **Bật `master_close_route = UI` là thêm một tiến trình và một điều kiện vận hành.** Clicker thứ
> hai chạy bằng `python -m clicker --muc clicker_master`, đọc **token riêng** ở mục
> `[clicker_master]` của `config.toml` và ghi nhật ký riêng `data/clicker_master_commands.ndjson`
> — dùng chung nhật ký là mất lệnh trong im lặng. Số tài khoản và tiêu đề cửa sổ của nó khai trên
> dashboard như mọi clicker khác. Terminal **Master** từ đó phải luôn mở Toolbox ở tab **Trade**,
> y như Client. Đăng ký tác vụ: `scripts\tao-dich-vu.ps1 -TacVuClickerMaster`.
>
> **Không phải chạm vào token.** `scripts\tro-ly.ps1` hỏi một câu ở bước thông số, rồi tự tạo agent,
> **ghi token thẳng vào `[clicker_master]`** và đăng ký tác vụ — token của cả hai clicker không bao
> giờ hiện ra màn hình, không bao giờ đi qua dòng lệnh. Token vẫn cần vì Bridge **tìm agent bằng
> token**: nó là danh tính, không phải thủ tục. Dùng chung một token cho hai clicker thì
> `server.connections[agent_id]` chỉ giữ một kết nối, và lệnh đóng dành cho Client sẽ được bấm trên
> terminal Master.

**Token thô chỉ hiện đúng một lần** và không đi vào log. Mất thì cấp lại — không có đường đọc
lại. `thu-hoi` không xoá dòng agent (sẽ mất lịch sử); nó đặt hash thành giá trị không token nào
sinh ra được và tắt `enabled`. `cap-token` **bật lại** agent đã thu hồi — cấp token là hành động
có chủ đích để nó nối lại được.

`CL-01` không tự sinh ra: `them-client` tạo nó, `cau-hinh-client` chỉ **sửa** một dòng đã có.

Đổi cấu hình giao dịch bằng `cau-hinh-client`, đừng `UPDATE` tay. Cặp **đang chạy** giữ nguyên tỷ
lệ cũ; giá trị mới chỉ áp cho lệnh mới (D-19).

Đặt `bao-tri` chạy hằng ngày bằng Scheduled Task — `scripts/tao-dich-vu.ps1` đăng ký sẵn. Nó chạy retention (D-17), `VACUUM INTO` một
bản sao lưu, giữ 14 bản gần nhất, rồi **tự mở lại bản vừa tạo để kiểm chứng** — vì một bản sao
lưu chưa từng khôi phục thử thì không phải bản sao lưu.

---

## 5. Xem log và trạng thái

**Việc đầu tiên mỗi lần đăng nhập vào máy:**

```powershell
.\.venv\Scripts\python.exe -m bridge.admin tinh-hinh
```

Nó trả lời đúng một câu hỏi — *có gì cần làm không?* — và thoát khác 0 khi có. Kênh cảnh báo
ngoài đang **tắt có chủ đích**, nên đây là cách duy nhất bạn biết chuyện đã xảy ra. Lịch kiểm:
mỗi lần đăng nhập chạy `scripts\kiem-tra.ps1`; tác vụ `\CopyBridge\TinhHinh` chạy mỗi giờ (cột
*Last Run Result* khác 0 là có việc).

Log: `logs/bridge.log` (Bridge), `logs/clicker.log` và `logs/clicker_master.log` (hai clicker), xoay vòng theo ngày, giữ 30
ngày, UTF-8. Có bộ lọc che token — `grep -ri "token" logs/` phải ra rỗng (kiểm ngày 2026-09-06:
0 dòng trên ~15.000 dòng log). `logs/service-err.log` do NSSM ghi là **toàn bộ output console** của Bridge
— trùng nội dung với `bridge.log`, không phải chỉ lỗi — cộng thêm những thứ `bridge.log` không
bắt được: Python không khởi động được, traceback của chính bộ ghi log (ví dụ lần xoay hỏng). NSSM
tự xoay nó ở 10 MB. Tìm lỗi trong đó bằng `Select-String`, đừng đọc cả file.

**Mỗi tiến trình một file log, không bao giờ dùng chung.** Trước 2026-09-11 clicker ghi vào
chính `bridge.log`. Trên Windows, hai tiến trình chạy lâu cùng giữ một file mở thì lần xoay lúc
nửa đêm không đổi tên được file (`WinError 32`), và vì lần xoay hỏng không dời mốc xoay kế tiếp nên
mọi lần ghi sau đều thử lại và hỏng lại: **cả hai ngừng ghi log vĩnh viễn** trong khi vẫn chạy
bình thường. Trên VPS nó làm `bridge.log` đứng im 63 giờ. `kiem-tra.ps1` mục 7 bắt được triệu
chứng này ("log không đổi trong N phút").

Dashboard `http://127.0.0.1:8080` (mở trong VPS) là nơi nhìn trạng thái. Ba thứ nhìn trước tiên:
`run_mode`, canary của clicker, và số finding đối chiếu đang chờ.

---

## 5a. Đo lại cấu trúc giao diện MT5 — khi đổi sàn hoặc khi clicker hành xử lạ

Clicker nhắm các ô trong hộp thoại New Order bằng **`ctrlID` chôn cứng**, đo trên *Connext-Demo
build 5.00* (`clicker/ui/dialog.py`). Mỗi sàn phát hành một bản MT5 riêng, nên các hằng số đó
**không có gì bảo đảm** đúng trên terminal khác. Triệu chứng khi chúng sai: clicker báo `rejected`
với "Hop thoai khong dung hinh dang", hoặc tệ hơn là không tìm thấy hộp thoại dù nó đang mở.

Công cụ để trả lời, **chỉ đọc, không bấm gì** — chạy được cả khi đang có lệnh thật đang mở:

```powershell
.\.venv\Scripts\python.exe -m clicker.ui.dump                        # mọi hộp thoại đang mở
.\.venv\Scripts\python.exe -m clicker.ui.dump --title 538287         # kèm cây control của terminal
.\.venv\Scripts\python.exe -m clicker.ui.dump --title 538287 --menu  # cây menu và ID lệnh
.\.venv\Scripts\python.exe -m clicker.ui.dump --all-controls         # kể cả control ẩn
.\.venv\Scripts\python.exe -m clicker.ui.dump --listview 0x1A2B3C    # thử đọc một control danh sách
```

Cách dùng: mở hộp thoại cần đo **bằng tay** trên terminal, rồi chạy lệnh trên ở cửa sổ khác. Bản in
cho `ctrlID`, class, kích thước và chữ của từng control — đúng bộ số cần để sửa hằng số trong
`dialog.py`. `--menu` cho ID lệnh, tức nguồn của hằng số như `MENU_NEW_ORDER = 32848`.

> **Đọc `--listview` cho đúng.** Một control **không phải** ListView vẫn trả `0` chứ không báo lỗi.
> Nên `0` một mình nó không có nghĩa là "danh sách rỗng" — công cụ in kèm cảnh báo class và trả mã
> thoát khác 0 trong trường hợp đó. Chi tiết ở `clicker/ui/win32.py::listview_item_count`.

## 5b. Triển khai tất cả trên MỘT VPS

> Các bước cài: [CAI-DAT-VPS.md](CAI-DAT-VPS.md). Mục này giải thích **vì sao**.

Đây là kiến trúc **duy nhất được hỗ trợ**: Bridge, cả hai terminal MT5 và các clicker cùng nằm trên
một máy. Đổi lại sự đơn giản là ba rủi ro riêng.

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
   ngắt ra, và từ giây đó **mọi lệnh mở lẫn lệnh đóng** đều đi qua một cơ chế **chưa ai chứng minh
   là còn chạy**. Chiều đóng nguy hiểm hơn: không mở được thì mất một cơ hội, còn tưởng đã đóng mà
   chưa đóng là phơi nhiễm mà không ai biết.
   Phải đo trước khi tin: ngắt phiên RDP (đóng cửa sổ, **không** Sign out), rồi kiểm qua database
   xem lệnh tiếp theo có được copy không.
2. **Algo Trading tắt (B-09).** Cả đường mở lẫn đường đóng phía Client đều đi qua giao diện nên
   **không cần** Algo Trading để chạy bình thường — nhưng nó vẫn **cần**, vì đó là **lưới cuối**:
   clicker hỏng thì lệnh đóng rơi về `OrderSend` của EA (D-28), và lúc ấy Algo Trading là thứ duy
   nhất còn giữ cho vị thế đóng được. Bridge **nhìn thấy** trạng thái này từ migration `003` (EA
   gửi `trade_allowed` trong heartbeat) và có cổng thứ ba ở đường mở: Client không đóng được thì
   không mở lệnh mới. Vẫn kiểm bằng mắt sau mỗi lần VPS khởi động lại hoặc MT5 tự cập nhật: nút
   **Algo Trading** sáng xanh trên **cả hai** terminal.
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

---

## 5c. Đường ĐÓNG qua giao diện — điều kiện và khoá cấu hình

Bật cho Client: `bridge.admin cau-hinh-client CL-01 --close-route UI` (trợ lý cài đặt bật sẵn).
Bật cho Master: `bridge.admin cau-hinh-master --clicker-agent AG-CLICKER-MASTER --close-route UI`
(cần clicker thứ hai — [CAI-DAT-VPS.md](CAI-DAT-VPS.md) mục B3). Sau phiên đầu có đóng lệnh, chạy
`bridge.admin kiem-reason`: nó soi cả deal mở lẫn deal đóng.

### Quay lại nếu cần

```powershell
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01 --close-route EA
```

Chỉ vậy. **Không cần hạ migration** — schema mới tương thích ngược, và `close_route = 'EA'` đi
đúng đường cũ, im lặng, không alert. Đó là lý do cờ này tồn tại thay vì suy ra từ việc có clicker
hay không.

### Hai điều kiện vận hành

1. **Tab Trade của Toolbox phải là tab đang mở** trên terminal Client (và Master nếu bật đường đóng Master). Clicker nhận ra danh sách
   vị thế bằng ctrlID `10328`, và tab không mở thì control đó không `visible`. Bridge **từ chối ồn
   ào** chứ không đoán, nên không có nguy cơ đóng nhầm — nhưng lệnh đóng sẽ rơi về EA và deal đóng
   mang `EXPERT`. Cùng loại giới hạn với B-01 (một symbol mỗi terminal).
2. **Toolbox không được tắt** (`Ctrl+T` bật lại).

### Hai khoá cấu hình

| Khoá | Mặc định | Nghĩa |
|---|---|---|
| `close_degraded_fallback` | `EA` | Clicker hỏng thì vẫn đóng bằng `OrderSend`, kèm CRITICAL. Đặt `SKIP` là **chấp nhận giữ vị thế trần** thay vì để một deal mang `EXPERT`. |
| `ui_close_correlate_grace_ms` | `5000` | Cửa sổ Bridge nhận cha cho event đóng do chính nó gây ra. Đặt quá ngắn → bot tự cascade đóng Master. Đặt quá dài → nuốt mất lệnh đóng tay của người dùng. |

## 6. Kiến trúc nhiều máy — chưa hỗ trợ

Master, Client và Bridge trên các máy khác nhau **chưa từng chạy thử** và script không hỗ trợ. Nếu
cần về sau, tối thiểu phải: đặt `host = "0.0.0.0"` **kèm** `dashboard_password` (Bridge từ chối khởi
động nếu thiếu), chỉ mở 8787/8080 qua mạng riêng (Tailscale ACL + firewall Windows chặn mọi interface
khác), kiểm từ một máy thứ ba rằng hai cổng không lộ ra Internet, và khai địa chỉ Bridge trong
*Allow WebRequest* của từng terminal. Tailscale xác thực **máy**, không thay được token của agent.

---

## 7. Sự cố thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| Master vào lệnh mà Client không copy | `run_mode = PAUSED`, hoặc clicker chưa chạy / canary đỏ | Xem dashboard. Clicker `DEGRADED` thì **cố ý không copy** và không rơi về đường EA (D-25). |
| Alert `UI_OPEN_QUEUE_EXPIRED` | Lệnh xếp hàng chờ clicker quá **15 giây** (`ui_open_queue_max_age_ms`) | Lệnh đó **bị huỷ có chủ đích** — mở sau 15 giây là mở sai giá (D-31). Mất hedge thật: kiểm và quyết định bằng tay có mở bù không. Thấy dòng này lặp lại nghĩa là Master vào lệnh nhanh hơn giao diện bấm được; **đừng nới trần**, hãy ghi số vào B-15. |
| Alert `UI_OPEN_QUEUE_FULL` | Hàng đợi chạm `ui_open_queue_max_len` (mặc định 20) | Chặn cuối. Lệnh **mất thật**. Cùng cách xử lý như trên, nhưng mức độ nặng hơn: hàng đợi đã dài 20 lệnh nghĩa là clicker đang tắc hẳn — kiểm tab Trade của terminal Client xem có hộp thoại nào đang kẹt không. |
| Alert ERROR `AGENT_DUPLICATE_CONNECTION`; log EA `Bridge tu choi: REPLACED - …`; (bản trước 2026-09-15: hàng trăm nghìn `COMMAND_TIMEOUT … REQUEST_SNAPSHOT`, log EA lặp `Gui khong tron goi (-1/…)`); `bridge.log` lặp `mo ket noi moi … dong ket noi cu` mỗi ~1 giây | **EA gắn trên HAI chart** của cùng một terminal (hoặc hai terminal cùng token). Bridge giữ một kết nối mỗi agent, nên hai bản đá nhau ra liên tục. Đã xảy ra thật 2026-09-12→15: 388 nghìn alert | Log EA (tab Experts) sẽ hiện **hai tên chart khác nhau** trong ngoặc, ví dụ `CopyBridgeMaster (ETHUSD.s,H1)` và `(BTCUSD.s,H1)`. Menu **Window** để thấy mọi chart; giữ EA trên **đúng một** chart. Phía Client giữ chart của symbol đang copy (B-01). Hết lũ rồi mới `xac-nhan-alert --code COMMAND_TIMEOUT`. |
| Log **EA** lặp `Bridge tu choi bat tay … ACCOUNT_MISMATCH` | Token đang gắn với một tài khoản MT5 khác. Bridge gắn agent với số tài khoản ở **lần bắt tay đầu tiên** rồi giữ nguyên | `bridge.admin sua-agent <agent> --login <so-dung>`, hoặc gắn đúng token vào đúng terminal. Dòng log `Agent X gan voi tai khoan MT5 Y (lan dau)` cho biết nó đã gắn với số nào. |
| Log **clicker** lặp `ACCOUNT_MISMATCH` | Chỉ xảy ra khi `config.toml` còn khai `account_login` khác số trong DB — **file thắng database** (D-32) | Xoá `account_login` khỏi mục `[clicker]`/`[clicker_master]` của `config.toml` rồi khai trên dashboard. Clicker tự nối lại sau ~3 giây. |
| Clicker thoát **mã 4**, `logs\clicker-wrapper.log` ghi `chua khai terminal` | Chưa ai khai tiêu đề cửa sổ cho clicker đó — ở đâu cũng không có | Dashboard tab **Cấu hình** → Agent: điền số tài khoản và tiêu đề cửa sổ. Clicker thử lại mỗi 60 giây nên khai xong là nó tự lên. Cố ý **không** chạy tiếp ở canary đỏ: canary đỏ chỉ chặn đường MỞ, còn đường ĐÓNG sẽ rơi về EA và deal đóng mang `EXPERT`. |
| Canary clicker đỏ, log `Tieu de cua so la tai khoan X, khac Y` | Tiêu đề đang trỏ vào terminal của **tài khoản khác** | Sửa tiêu đề trên dashboard. Đây là hàng rào thay cho `ACCOUNT_MISMATCH` (D-32): đối chiếu với cửa sổ thật, mỗi nhịp heartbeat. |
| Đã bật `master_close_route = UI` mà lệnh đóng Master vẫn **Placed by expert** | Clicker Master không sẵn sàng lúc đóng, lệnh rơi về EA theo D-28 | `bridge.admin liet-ke`: `AG-CLICKER-MASTER` phải **ONLINE**. Đọc alert `CLOSE_MASTER_FELL_BACK_TO_EA` — lý do nằm ngay trong nội dung (`dang OFFLINE`, `chua khai …`). OFFLINE thì xem tác vụ `\CopyBridge\ClickerMaster` có chạy không và `logs\clicker_master.log`. |
| Đóng ở Client mà Master **không** đóng theo | Một trong các cửa chặn của `closing.on_client_close`: `run_mode = PAUSED` (Bridge cố ý không đồng bộ đóng — chỉ `RUNNING` / `PAUSE_NEW_ENTRIES` / `EMERGENCY` mới đồng bộ); `can_close_master = 0` (alert `ORPHANED_MASTER`); vị thế không thuộc cặp nào; Bridge coi là bot đóng; đóng một phần (`CLIENT_PARTIAL_CLOSE`, không cascade theo D-11); hoặc cascade chạy mà Master không xác nhận trong 15 s (`CASCADE_MASTER_TIMEOUT`) | Đọc `event.process_status` / `process_error` của event đóng phía Client — nó ghi **đúng** nhánh đã đi. Truy vấn sẵn: plan chẩn đoán 2026-09-15 (in cấu hình, 5 event đóng gần nhất, lệnh và alert của cặp). `PAUSED` thì dùng `run-mode PAUSE_NEW_ENTRIES` nếu muốn vẫn đồng bộ đóng mà không mở lệnh mới. Cặp đã lỡ **không** tự sửa khi đổi chế độ: đóng Master bằng tay hoặc xử lý finding trên dashboard, không `UPDATE` DB. |
| Nghi "bên kia chốt sai lệnh" | Ba cơ chế đã rà (D-30, bổ sung 2026-09-15): cặp ghép nhầm lúc mở, deal đóng một vị thế khác lệnh nhắm tới, hoặc clicker báo nhầm đã đóng | Chạy `python -m bridge.admin kiem-dong-sai --ngay YYYY-MM-DD` (ngày **UTC**) cho đúng ngày xảy ra. `[C]` = cặp gắn nhầm vị thế; `[A]` = deal đóng X trong lúc lệnh nhắm Y (có thể là người dùng đóng tay đúng lúc đó — đọc log); `[B]` = cặp `CLOSED` mà vị thế không có deal đóng — **kiểm terminal**, vị thế có thể vẫn đang mở. Rồi đọc `logs\clicker.log` quanh mốc đó: `Do dong`, `Dong N mo hop thoai`, `Bam Close ticket`. Gửi cả hai phần khi báo lỗi. |
| Clicker trả `rejected` kèm "phep tim khong sach" hoặc "khong xu ly xong hang doi" | Lần tìm có dò treo / hộp thoại sót / ticket ở hai dòng, hoặc MT5 đang bận ngay trước cú bấm | Đúng thiết kế: clicker từ chối kết luận thay vì đoán. Bridge rơi về EA (alert `CLOSE_FELL_BACK_TO_EA`), deal đóng mang `EXPERT`. Lặp lại nhiều thì terminal đang quá tải — kiểm CPU và số chart mở. |
| `tinh-hinh` in `hang doi mo (UI)` khác 0 | Đang có lệnh xếp hàng chờ bấm | Bình thường nếu chỉ thoáng qua (mỗi lệnh chờ dưới một giây). Đứng yên nhiều giây là clicker tắc. |
| Alert `ORPHANED_MASTER` | Client đóng khi `can_close_master = 0` (D-20) | Đúng thiết kế. Quyết định bằng tay: đóng Master hay mở lại Client. |
| Agent `DEGRADED` | Terminal mất kết nối broker nhưng EA còn sống | Bridge **ngừng gửi command** cho agent đó. Chờ terminal nối lại. |
| Alert `TRADE_NOT_ALLOWED` | Terminal của agent đó không đặt được lệnh | **Đọc tab Experts để biết chỗ nào đang chặn** — EA ghi rõ. Có **bốn** chỗ, và bật nút trên thanh công cụ chỉ sửa được một: (1) nút **Algo Trading** trên thanh công cụ, (2) ô **"Allow Algo Trading"** trong thuộc tính EA — bị bỏ tick khi gắn EA lúc nút toàn cục đang tắt, và **bật lại nút KHÔNG tick lại ô này**, (3) tài khoản không được phép giao dịch, (4) tài khoản không cho EA giao dịch. Hai cái cuối ở phía broker. |
| Alert `CLIENT_TRADE_NOT_ALLOWED` | Bridge **từ chối mở lệnh mới** vì Client không đóng được | Đúng thiết kế: đừng mở cái không đóng được. Bật Algo Trading rồi copy chạy lại. |
| Alert `FINDING_BO_QUEN` | Có sai lệch nằm chờ quá `finding_nhac_sau_phut` (mặc định 60) | Mở dashboard, xử lý từng finding. Đặt khoá này về 0 để tắt nhắc. |
| Finding đối chiếu đang chờ | Sổ sách lệch với thực tế trên terminal | Mở finding trên dashboard, đọc `evidence_json` (có đủ ba nguồn) rồi mới `accept`. Không accept khi chưa đọc bằng chứng. Nếu trạng thái cặp đã đổi kể từ lúc phát hiện, Bridge **từ chối** accept (finding cũ, dashboard báo) — xử lý bằng **Bỏ qua** kèm ghi chú. |
| EA gửi bù lặp không dứt | Đã sửa ở Phase 10: trần 3 lần cho mỗi mốc `from_seq` | Nếu tái diễn, xem `bridge/protocol/server.py`. |
| Lệnh mở bị từ chối vì symbol lệch | Hộp thoại New Order lấy symbol theo chart đang mở | **Giới hạn đã biết** (`BACKLOG.md` B-01): mỗi terminal Client copy được một symbol. Mở đúng chart đó. |
| Clicker báo "Hop thoai khong dung hinh dang" | `ctrlID` chôn cứng không khớp bản MT5 của sàn này | Đo lại bằng `python -m clicker.ui.dump` — xem **mục 5a**. Đừng đoán hằng số. |
| Alert `CLOSE_FELL_BACK_TO_EA` | Clicker hỏng nên lệnh đóng đi qua `OrderSend` của EA | **Vị thế đã đóng được** — đây không phải mất tiền, mà là một deal đóng mang `EXPERT` thay vì `CLIENT`. Sửa clicker rồi chạy `kiem-reason` để biết còn bao nhiêu deal sai kênh. Đây là ngoại lệ có ý thức với D-25 (xem D-28). |
| Alert `CLOSE_KHONG_GUI_DUOC` | Clicker hỏng **và** `close_degraded_fallback = SKIP` | **Vị thế Client vẫn đang mở và không còn đối ứng.** Cần người xử lý ngay: sửa clicker, hoặc đóng tay, hoặc đổi khoá về `EA`. |
| Alert `UI_CLOSE_REASON_MISMATCH` | Deal đóng mang `EXPERT` trong khi `close_route = 'UI'` | Cơ chế đổi kênh đã ngừng hoạt động. Đây đúng là điều cả đường đóng qua giao diện tồn tại để ngăn — dừng lại và tìm hiểu trước khi copy tiếp. |
| Alert `UI_CLOSE_CORRELATE_MO_HO` | Một cặp có hơn một lệnh đóng qua giao diện trong cùng cửa sổ | Không nên xảy ra (mục 7.6 chặn hai lệnh đóng cùng chạy trên một cặp). Bridge nhận cha theo lệnh mới nhất và **không** cascade — hướng an toàn — nhưng cần xem lại vì sao có hai lệnh. |
| Lệnh đóng `rejected` với "Tab Trade cua Toolbox dang khong mo" | Người vận hành chuyển Toolbox sang tab khác | **Giới hạn đã biết:** clicker chỉ nhìn thấy danh sách vị thế khi tab Trade đang mở. Chuyển về tab Trade. Bridge từ chối chứ không đoán, nên không có nguy cơ đóng nhầm. |

---

## 8. Trước khi chuyển sang tài khoản thật

**Kết luận hiện tại: chưa GO.** Ba phép đo chỉ VPS làm được vẫn còn nợ:

**B-08 — phiên RDP đã ngắt (chặn).** Mở một cặp, **ngắt RDP bằng cách đóng cửa sổ** (không Sign out),
đợi vài phút, mở rồi đóng lệnh ở Master từ nơi khác (ví dụ app MT5 trên điện thoại), rồi nối lại và
đọc database.

| Quan sát | Nghĩa |
|---|---|
| Canary đỏ, không có `OPEN_UI` | **An toàn** — Bridge tự dừng copy (D-25) |
| Canary xanh nhưng không có vị thế Client | **Nguy hiểm** — hệ thống tưởng đang copy mà không |
| Lệnh đóng rơi về `CLOSE` của EA, có `CLOSE_FELL_BACK_TO_EA` | **An toàn** — vị thế vẫn đóng, chỉ mất `DEAL_REASON_CLIENT` (D-28) |
| Có `CLOSE_UI` nhưng vị thế Client **không đóng** | **Nguy hiểm nhất** — sổ tưởng đã đóng mà tiền chưa |

Rơi vào ô nguy hiểm thì dừng kế hoạch chạy thật cho tới khi giải xong.

**TEST-19 / B-02 — mất điện đột ngột.** Dùng *force stop* / *hard reset* của nhà cung cấp VPS đúng
lúc có lệnh đang bay. Bật lại: không mất event, bộ đối chiếu bắt đúng sai lệch.

**B-03 — chạy 24 giờ liên tục.** Ghi RAM các tiến trình và kích thước `bridge.db` + WAL lúc đầu và
lúc cuối; sáng hôm sau kiểm mỗi file log đều có bản đã xoay theo ngày.

**Bắt đầu bằng cấu hình nhỏ nhất:** một symbol (giới hạn kỹ thuật B-01), volume nhỏ nhất sàn cho
phép, kiểm `tinh-hinh` mỗi lần đăng nhập và `kiem-reason` + `kiem-dong-sai` mỗi ngày trong tuần đầu.

Đây là điều kiện vận hành, không phải checklist kỹ thuật. Không mục nào được bỏ.

1. **Chạy ổn định trên demo ít nhất một tuần liên tục** trước khi động vào tiền thật.
2. **Chạy TEST-19 thật** — rút điện hoặc tắt máy ảo đột ngột, rồi kiểm không mất event và bộ đối
   chiếu bắt đúng sai lệch. Đây là lý do `synchronous = FULL` tồn tại, và hiện nó **chưa từng
   được chứng minh bằng quan sát** (`BACKLOG.md` B-02).
3. **Đọc điều khoản của cả hai broker** về hedging, bonus, giao dịch nhiều tài khoản và copy
   trading. Một số broker cấm hoặc huỷ lợi nhuận từ các mô hình này.
4. **Đối chiếu tay khác biệt giữa hai sàn:** tên symbol, contract size, volume tối thiểu và bước
   volume, spread và giá báo, thời gian khớp lệnh, giờ giao dịch từng symbol.
5. **Bắt đầu bằng volume nhỏ nhất có thể và một symbol duy nhất.** Mở rộng dần sau khi quan sát
   ít nhất vài chục lệnh.
6. **Người vận hành phải biết cách bấm dừng khẩn cấp trước khi cần dùng tới nó.** Thử một lần
   trên demo.
7. Biết rõ những gì **chưa từng chạy trên sàn thật** — `docs/ACCEPTANCE.md` cột "Nguồn", mọi
   dòng ghi TEST hoặc KHÔNG.
8. **Trên VPS:** xong bài "phiên RDP đã ngắt" (B-08) và kiểm Algo Trading bật ở cả hai
   terminal (B-09). Mục 5b nói cách làm.
