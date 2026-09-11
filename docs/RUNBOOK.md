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
| **EA** (`CopyBridgeClient.mq5`, `CopyBridgeMaster.mq5`) | Trong mỗi terminal MT5 | Gửi event; thực thi lệnh **ĐÓNG phía Master**, và phía Client khi `close_route = 'EA'` hoặc khi clicker hỏng (D-28). |
| **clicker** (`python -m clicker`) | Cùng phiên đăng nhập Windows với terminal Client | Mở lệnh qua hộp thoại New Order (D-21, D-22, D-26) và **đóng lệnh** khi `close_route = 'UI'` (D-21b, D-30). |

Bridge là server, hai cái kia là client. MQL5 không listen được (D-03).

> **clicker KHÔNG chạy được như Windows Service.** Service nằm ở session 0 và không thấy cửa sổ
> của phiên người dùng. Nó phải là **Scheduled Task theo phiên đăng nhập**, kèm autologon và tắt
> sleep/hibernate. Bridge thì chạy service bình thường.

---

## 2. Cấu hình

> Các bước **cài đặt** không nằm ở đây. Chọn tài liệu trong bảng ở đầu
> [CAI-DAT-VPS.md](CAI-DAT-VPS.md). Mục này chỉ giải thích các khoá cấu hình và **vì sao**
> chúng như vậy — thứ bạn cần khi đang vận hành, không phải khi đang cài.

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

[clicker]                # token clicker dat o DAY, khong phai tren dong lenh
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

```powershell
.\.venv\Scripts\python.exe -m bridge                      # Bridge + dashboard
.\.venv\Scripts\python.exe -m clicker --token <TOKEN> --account-login <so-tai-khoan-Client>
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
.\.venv\Scripts\python.exe -m bridge.admin tinh-hinh                            # co gi can lam khong
.\.venv\Scripts\python.exe -m bridge.admin liet-ke
.\.venv\Scripts\python.exe -m bridge.admin them-agent AG-CLICKER --role CLICKER --magic 770001 --login <so-tai-khoan-Client>
.\.venv\Scripts\python.exe -m bridge.admin cap-token AG-CLIENT
.\.venv\Scripts\python.exe -m bridge.admin thu-hoi AG-CLICKER
.\.venv\Scripts\python.exe -m bridge.admin them-client CL-01 --agent AG-CLIENT --clicker-agent AG-CLICKER
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01                  # xem
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01 --multiplier 0.5
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01 --close-route UI  # dong qua giao dien
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
ngoài đang **tắt có chủ đích**, nên đây là cách duy nhất bạn biết chuyện đã xảy ra; xem
`docs/KE-HOACH-CHAY-THAT.md` mục 1.2 để biết lịch kiểm.

Log: `logs/bridge.log` (Bridge) và `logs/clicker.log` (clicker), xoay vòng theo ngày, giữ 30
ngày, UTF-8. Có bộ lọc che token — `grep -ri "token" logs/` phải ra rỗng (kiểm ngày 2026-09-06:
0 dòng trên ~15.000 dòng log). Lỗi của chính dịch vụ (Python không khởi động được, traceback lúc
xoay log) nằm ở `logs/service-err.log` do NSSM ghi.

**Mỗi tiến trình một file log, không bao giờ dùng chung.** Trước 2026-09-11 clicker ghi vào
chính `bridge.log`. Trên Windows, hai tiến trình chạy lâu cùng giữ một file mở thì lần xoay lúc
nửa đêm không đổi tên được file (`WinError 32`), và vì lần xoay hỏng không dời mốc xoay kế tiếp nên
mọi lần ghi sau đều thử lại và hỏng lại: **cả hai ngừng ghi log vĩnh viễn** trong khi vẫn chạy
bình thường. Trên VPS nó làm `bridge.log` đứng im 63 giờ. `kiem-tra.ps1` mục 7 bắt được triệu
chứng này ("log không đổi trong N phút").

Dashboard `http://<dia-chi-tailscale>:8080` là nơi nhìn trạng thái. Ba thứ nhìn trước tiên:
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

> **Cài đặt bằng script:** [HUONG-DAN-CUNG-VPS-SCRIPT.html](HUONG-DAN-CUNG-VPS-SCRIPT.html) —
> đầy đủ, kèm quy trình **cập nhật** khi có mã nguồn mới. Bản rút gọn:
> [CAI-DAT-VPS.md](CAI-DAT-VPS.md). Mục này giải thích **vì sao**, hai tài liệu kia nói **gõ gì**.

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

### Khác biệt so với mục 6

| Mục 6 nói | Khi chạy một-VPS |
|---|---|
| Tailscale ACL cho 8787 | Không cần — agent đi loopback |
| Firewall chặn 8787/8080 | Thay bằng `host = "127.0.0.1"` |
| Kiểm bằng máy thứ ba | Không cần, nếu đã bind loopback |
| Bridge chạy Windows Service | Vẫn nên, để tự bật sau reboot |
| clicker chạy Scheduled Task theo phiên | **Bắt buộc**, kèm autologon |

---

## 5c. Cập nhật lên đường ĐÓNG qua giao diện

> **Migration `004` dựng lại bảng `command`.** SQLite không sửa được ràng buộc `CHECK`, nên cách
> duy nhất để nhận thêm hai loại lệnh mới là tạo bảng mới, chép dữ liệu, xoá bảng cũ, đổi tên.
> Sao lưu trước là **bắt buộc**, không phải khuyến nghị. Việc chép dữ liệu có test riêng
> (`test_migration_004_giu_nguyen_du_lieu_command_cu`) chạy trên DB **đã có dữ liệu**, nhưng một
> test không thay được một bản sao lưu.

Migration chạy **tự động** khi Bridge mở database. Không có lệnh chạy tay, và không cần có.

### Thứ tự

```powershell
# 1. Dung an toan. Cho toi khi khong con gi dang bay.
.\.venv\Scripts\python.exe -m bridge.admin run-mode PAUSED
.\.venv\Scripts\python.exe -m bridge.admin tinh-hinh      # phai sach: 0 cap chua dong
# 2. Tat clicker truoc, roi Bridge (Ctrl+C ca hai).
# 3. Sao luu TRUOC MIGRATION -- xem canh bao ngay duoi.
.\.venv\Scripts\python.exe -c "import sqlite3,pathlib,datetime; t=datetime.datetime.now().strftime('%Y%m%d-%H%M%S'); d=pathlib.Path('data/backup'); d.mkdir(parents=True,exist_ok=True); c=sqlite3.connect('data/bridge.db'); c.execute('VACUUM INTO ?', (str(d/f'truoc-004-{t}.db'),)); print('Da sao luu:', d/f'truoc-004-{t}.db')"
# 4. Lay code moi.
git pull
# 5. Bat Bridge mot lan -> migration 004 chay. Kiem version.
.\.venv\Scripts\python.exe -m bridge
```

> **Đừng dùng `bridge.admin sao-luu` cho bản sao lưu TRƯỚC migration.** Mọi lệnh `bridge.admin`
> đều mở database qua `Database(...)`, mà hàm đó mặc định `migrate=True` — nên nó sẽ **chạy
> migration trước, rồi mới sao lưu bản đã migrate**. Bản sao lưu đó không quay lại được.
>
> Lệnh ở bước 3 dùng `sqlite3` trần với `VACUUM INTO`: không đi qua `Database`, không chạm
> migration, và cho ra một file duy nhất đã gộp WAL nên chép đi đâu cũng mở được.
>
> `bridge.admin sao-luu` vẫn đúng cho mọi việc sao lưu **thường ngày** — chỉ riêng thời điểm này,
> khi cái cần giữ là trạng thái *trước* khi schema đổi, thì nó không dùng được.

Kiểm migration đã chạy (Bridge vẫn đang bật, mở PowerShell khác):

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('data/bridge.db'); print(c.execute('SELECT MAX(version) FROM schema_version').fetchone()[0])"
```

Phải in ra `4`. Nếu không, **dừng lại** — đừng bật `RUNNING` trên một schema nửa vời.

```powershell
# 6. Bat duong dong qua giao dien cho tung Client. Mac dinh la EA, tuc khong doi gi.
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01 --close-route UI
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01          # xem lai
# 7. Bat clicker, cho canary xanh tren dashboard.
# 8. Roi moi chay.
.\.venv\Scripts\python.exe -m bridge.admin run-mode RUNNING
```

Sau phiên đầu tiên có đóng lệnh:

```powershell
.\.venv\Scripts\python.exe -m bridge.admin kiem-reason
```

Nay nó soi **cả hai** cột. `TEST-23 DAT: n/n` kèm số deal mở và số deal đóng mới là đạt.

### Quay lại nếu cần

```powershell
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-client CL-01 --close-route EA
```

Chỉ vậy. **Không cần hạ migration** — schema mới tương thích ngược, và `close_route = 'EA'` đi
đúng đường cũ, im lặng, không alert. Đó là lý do cờ này tồn tại thay vì suy ra từ việc có clicker
hay không.

### Hai điều kiện vận hành MỚI

1. **Tab Trade của Toolbox phải là tab đang mở** trên terminal Client. Clicker nhận ra danh sách
   vị thế bằng ctrlID `10328`, và tab không mở thì control đó không `visible`. Bridge **từ chối ồn
   ào** chứ không đoán, nên không có nguy cơ đóng nhầm — nhưng lệnh đóng sẽ rơi về EA và deal đóng
   mang `EXPERT`. Cùng loại giới hạn với B-01 (một symbol mỗi terminal).
2. **Toolbox không được tắt** (`Ctrl+T` bật lại).

### Hai khoá cấu hình mới

| Khoá | Mặc định | Nghĩa |
|---|---|---|
| `close_degraded_fallback` | `EA` | Clicker hỏng thì vẫn đóng bằng `OrderSend`, kèm CRITICAL. Đặt `SKIP` là **chấp nhận giữ vị thế trần** thay vì để một deal mang `EXPERT`. |
| `ui_close_correlate_grace_ms` | `5000` | Cửa sổ Bridge nhận cha cho event đóng do chính nó gây ra. Đặt quá ngắn → bot tự cascade đóng Master. Đặt quá dài → nuốt mất lệnh đóng tay của người dùng. |

## 6. Mạng và bảo mật cho kiến trúc NHIỀU MÁY — **CHƯA LÀM**

> Chạy tất cả trên một VPS thì đọc **mục 5b** thay cho mục này; phần lớn mục 6 không áp
> dụng, và mục 5b nói rõ chỗ nào thay bằng gì.

> **Hướng dẫn từng bước cho kiến trúc hai máy:**
> [HUONG-DAN-KHAC-VPS.html](HUONG-DAN-KHAC-VPS.html) — bố trí máy A/máy B, Tailscale, luật
> firewall, `host = "0.0.0.0"` kèm mật khẩu bắt buộc. Đó là nơi duy nhất mô tả cách bố trí
> này. Danh sách dưới đây là **những gì chưa ai kiểm chứng**, và tài liệu kia cũng viết theo
> thiết kế chứ không theo kinh nghiệm chạy thật.

Những mục dưới đây **chưa được thực hiện hay kiểm chứng** ở lượt này vì cần môi trường thật
(máy thứ ba, VPS, quyền quản trị mạng):

- [ ] Cài Tailscale trên máy Bridge và các node agent; ghi địa chỉ `100.x.y.z` vào đây.
- [ ] Tailscale ACL: chỉ node agent chạm được 8787, chỉ máy quản trị chạm được 8080.
- [ ] Firewall Windows: chặn 8787 và 8080 trên **mọi** interface trừ interface Tailscale và
      loopback. Không bao giờ mở ra Internet công cộng.
- [ ] Kiểm bằng **máy thứ ba**: cả hai port không truy cập được từ ngoài Tailscale.
- [x] Đăng ký Bridge làm Windows Service (NSSM hoặc `pywin32`), tự khởi động khi máy bật.
      — **đã có script** (`scripts/tao-dich-vu.ps1`, dùng NSSM), **chưa kiểm chứng trên VPS thật**.
- [x] Đăng ký clicker làm **Scheduled Task theo phiên đăng nhập** + autologon + tắt sleep.
      — **đã có script**, **chưa kiểm chứng trên VPS thật**. Có script không đồng nghĩa đã kiểm
      chứng, và mục này là danh sách kiểm chứng.
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
| Alert `TRADE_NOT_ALLOWED` | Terminal của agent đó không đặt được lệnh | **Đọc tab Experts để biết chỗ nào đang chặn** — EA ghi rõ. Có **bốn** chỗ, và bật nút trên thanh công cụ chỉ sửa được một: (1) nút **Algo Trading** trên thanh công cụ, (2) ô **"Allow Algo Trading"** trong thuộc tính EA — bị bỏ tick khi gắn EA lúc nút toàn cục đang tắt, và **bật lại nút KHÔNG tick lại ô này**, (3) tài khoản không được phép giao dịch, (4) tài khoản không cho EA giao dịch. Hai cái cuối ở phía broker. |
| Alert `CLIENT_TRADE_NOT_ALLOWED` | Bridge **từ chối mở lệnh mới** vì Client không đóng được | Đúng thiết kế: đừng mở cái không đóng được. Bật Algo Trading rồi copy chạy lại. |
| Alert `FINDING_BO_QUEN` | Có sai lệch nằm chờ quá `finding_nhac_sau_phut` (mặc định 60) | Mở dashboard, xử lý từng finding. Đặt khoá này về 0 để tắt nhắc. |
| Finding đối chiếu đang chờ | Sổ sách lệch với thực tế trên terminal | Mở finding trên dashboard, đọc `evidence_json` (có đủ ba nguồn) rồi mới `accept`. Không accept khi chưa đọc bằng chứng. |
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


> **Thêm sau khi đường ĐÓNG chuyển sang giao diện — điều kiện này CHƯA đạt.**
>
> Cú double-click mở hộp thoại đóng đi bằng `SendMessage` tới window proc, **không** phải
> `SendInput` bơm vào hàng đợi bàn phím của phiên tương tác. Nên về nguyên lý nó sống qua phiên
> RDP đã ngắt, giống hệt đường mở. Nhưng **đó là suy luận, chưa phải phép đo** — và bài học của
> chính dự án này là suy luận về giao diện MT5 sai nhiều hơn đúng.
>
> Phép đo bắt buộc, chỉ VPS mới làm được (B-08, TEST-19):
>
> 1. Mở một cặp trên demo qua VPS.
> 2. **Ngắt phiên RDP** bằng cách đóng cửa sổ Remote Desktop — *không* bấm Sign out, vì Sign out
>    kết thúc phiên và cả clicker lẫn terminal đều chết theo.
> 3. Đóng lệnh phía Master từ máy khác.
> 4. Nối lại RDP, kiểm: vị thế Client **đã đóng**, và `kiem-reason` báo `reason = 0` cho deal đóng.
>
> Đo ra kết quả âm thì đặt `close_route = EA` cho tới khi có hướng khác. Đừng chạy tiền thật với
> một đường đóng chưa biết có sống qua RDP ngắt hay không.
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
