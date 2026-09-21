# Cài đặt và cập nhật trên VPS Windows

Tài liệu cài đặt **duy nhất** của dự án. Chọn phần theo tình trạng máy:

| Tình trạng VPS | Đọc |
|---|---|
| **Chưa có hệ thống** — VPS trắng, hoặc mới chỉ có MT5 | [Phần A — Cài mới](#phần-a--cài-mới-trên-vps-chưa-có-hệ-thống) |
| **Đã có hệ thống** `C:\CopyBridge` đang chạy | [Phần B — VPS đã có hệ thống](#phần-b--vps-đã-có-hệ-thống): B1 cập nhật · B2 lùi bản · B3 bật thêm tính năng · B4 đổi tài khoản MT5 · B5 chuyển VPS · B6 thêm/tắt/xoá Client · B7 cài lại sạch |
| Hằng ngày, sau mỗi lần khởi động lại | [Phần C — Vận hành](#phần-c--vận-hành-hằng-ngày) |

Muốn biết **vì sao** một bước như vậy: [RUNBOOK.md](RUNBOOK.md). Gặp sự cố khi đang chạy: RUNBOOK mục 7.

**Kiến trúc:** tất cả trên **một** VPS — Bridge, hai terminal MT5 (Master, Client) và các clicker.
Agent nối tới Bridge qua `127.0.0.1`, không cần Tailscale hay luật firewall. Kiến trúc nhiều máy
**chưa được hỗ trợ**.

```
Terminal Master + EA ─┐                          ┌─ Clicker Client  (mở + đóng lệnh Client qua giao diện)
                      ├─ TCP 127.0.0.1:8787 ─ Bridge ─┤
Terminal Client + EA ─┘   (dịch vụ Windows)       └─ Clicker Master  (đóng lệnh Master qua giao diện, tuỳ chọn)
                                   └─ Dashboard http://127.0.0.1:8080
```

| Thành phần | Chạy dưới dạng | Tên |
|---|---|---|
| Bridge + dashboard | Windows Service (NSSM) | `CopyBridge` |
| Clicker Client | Scheduled Task khi đăng nhập | `\CopyBridge\Clicker` |
| Clicker Master (tuỳ chọn) | Scheduled Task khi đăng nhập | `\CopyBridge\ClickerMaster` |
| Bảo trì + sao lưu | Scheduled Task 03:00 hằng ngày | `\CopyBridge\BaoTri` |
| Kiểm tình hình | Scheduled Task mỗi giờ | `\CopyBridge\TinhHinh` |

> Mọi lệnh bên dưới chạy trong **PowerShell mở bằng Run as administrator**, trong thư mục
> `C:\CopyBridge` (trừ khi ghi khác). Nếu PowerShell chặn script:
> `Set-ExecutionPolicy -Scope Process Bypass -Force`.

---

# Phần A — Cài mới trên VPS chưa có hệ thống

## A0. Chuẩn bị máy

**Cấu hình:** Windows Server 2019/2022, **4 GB RAM** (mỗi MT5 ~160 MB, Bridge ~50 MB), 2 CPU.

**Ba việc bắt buộc** — clicker phải sống trong một phiên người dùng đang đăng nhập:

1. **Autologon:** chạy `netplwiz`, bỏ tick *Users must enter a user name and password*.
2. **Tắt sleep/hibernate:**
   ```powershell
   powercfg /change standby-timeout-ac 0
   powercfg /hibernate off
   ```
3. **Tắt khoá màn hình:** Screen saver → bỏ tick *On resume, display logon screen*.

**Hai terminal MT5** (một Master, một Client), đăng nhập sẵn, tài khoản chế độ **Hedging**.
Cài MT5 thứ hai vào thư mục khác (ví dụ `C:\Program Files\MetaTrader 5 1`).

Trên **mỗi** terminal:
- Tools → Options → Expert Advisors: tick **Allow WebRequest for listed URL**, thêm `127.0.0.1`.
  Thiếu dòng này EA không bao giờ lên `ONLINE` (triệu chứng giống sai token).
- Bật nút **Algo Trading**.
- Mở **Toolbox** (`Ctrl+T`) và để ở tab **Trade**. Clicker đọc danh sách vị thế ở đây.
- Terminal **Client**: mở sẵn chart của **symbol sẽ copy** (hộp thoại New Order lấy symbol theo
  chart; mỗi terminal Client chỉ copy một symbol — B-01).

> **MT5 và clicker phải cùng mức quyền.** Cả hai chạy thường, hoặc cả hai "Run as administrator".
> Lệch nhau thì Windows chặn mọi thao tác của clicker mà không báo lỗi.

Ghi lại **số tài khoản** Master và Client. Xem nhanh bằng:

```powershell
Get-Process terminal64 | Select-Object Id, MainWindowTitle
```

Tiêu đề có dạng `538217 - Connext-Demo: Demo Account - Hedge - [XAUUSD,M1]` — số đầu là số tài khoản.

## A1. Tải mã nguồn và dựng nền

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest "https://raw.githubusercontent.com/taducloc0603/copy-trade/main/scripts/cai-dat.ps1" `
  -OutFile "$env:USERPROFILE\Desktop\cai-dat.ps1" -UseBasicParsing
& "$env:USERPROFILE\Desktop\cai-dat.ps1" -ThuMuc C:\CopyBridge
```

Script tự cài Python 3.12 và git nếu thiếu, clone vào `C:\CopyBridge`, tạo `.venv`, cài gói, tạo
`data\`, `logs\`, tạo `config.toml` (mật khẩu dashboard ngẫu nhiên, in ra một lần), khởi tạo database
và chạy bộ test (vài phút). Chạy lại bao nhiêu lần cũng được — bước đã xong in `BO QUA`.

Dòng đầu phải in `MT5 Copy Bridge -- cai dat (ban <ngày>)`. Không có `(ban ...)` là bạn đang chạy
một bản script cũ — tải lại.

Tuỳ chọn hay dùng: `-BoQuaTest` (bỏ bộ test), `-BoQuaGit` (thư mục đã chép sẵn qua RDP, không
clone), `-LamMoiVenv` (tạo lại `.venv`).

## A2. Chạy trợ lý cài đặt

```powershell
C:\CopyBridge\scripts\tro-ly.ps1 -ThuMuc C:\CopyBridge
```

Trợ lý hỏi xác nhận từng bước, bước đã xong thì bỏ qua. Nó sẽ hỏi:

| Câu hỏi | Trả lời |
|---|---|
| Magic number | Enter (`770001`) |
| Tên agent Master / Client / Clicker | Enter (`AG-MASTER`, `AG-CLIENT`, `AG-CLICKER`) |
| **Bật đường ĐÓNG phía Master qua giao diện?** | **Có** nếu muốn lệnh đóng trên Master hiện *Placed by manual* (cần clicker thứ hai, terminal Master cũng phải để tab Trade) |
| Mã client | Enter (`CL-01`) |

Trợ lý **không hỏi số tài khoản MT5 hay tiêu đề cửa sổ** nữa: EA tự báo số tài khoản của nó lúc kết
nối, còn của clicker thì khai trên dashboard ở bước A4. Thêm `-TuDongDongY` thì trợ lý lấy hết giá
trị mặc định và chỉ dừng ở hai chỗ phải làm tay: chép token vào EA, và mật khẩu tài khoản Windows.

Rồi nó tự làm theo thứ tự:

1. Tạo agent và **ghi token clicker thẳng vào `config.toml`** (mục `[clicker]`, `[clicker_master]`).
2. **In token của `AG-MASTER` và `AG-CLIENT` một lần** — chép lại ngay, dùng ở bước gắn EA.
3. Tạo client `CL-01` với đường mở và đóng qua giao diện.
4. Đăng ký dịch vụ `CopyBridge` và các Scheduled Task (hỏi mật khẩu tài khoản autologon — nên nhập).
   Bridge bắt đầu chạy từ đây, ở `PAUSED`.
5. Biên dịch hai EA.
6. **Dừng chờ bạn gắn EA** (A3).
7. Chờ EA lên `ONLINE`, rồi hỏi **ánh xạ symbol** (Master `XAUUSD` → Client `XAUUSDm`...).
   Thiếu ánh xạ thì **mọi lệnh Master bị bỏ qua im lặng**.
8. Chạy `kiem-tra.ps1`.

> **Token hiện đúng một lần**, không vào log. Mất thì cấp lại:
> `.\.venv\Scripts\python.exe -m bridge.admin cap-token AG-MASTER` rồi dán vào EA.
> Không bao giờ đưa token clicker lên dòng lệnh.

## A3. Gắn EA (làm tay, trong lúc trợ lý chờ)

1. Chép `ea\CopyBridgeMaster.ex5` vào `MQL5\Experts` của terminal **Master**,
   `ea\CopyBridgeClient.ex5` vào terminal **Client** (File → Open Data Folder).
2. Kéo EA lên **đúng MỘT chart** mỗi terminal. Client: chart của symbol đang copy.
3. Tham số: `AgentToken` = token vừa in; `BridgeHost` = `127.0.0.1`; `BridgePort` = `8787`.
   Tab Common: tick **Allow Algo Trading**.
4. Tab **Experts** phải hiện `CopyBridgeMaster khoi dong ...` / `CopyBridgeClient khoi dong ...`.

> **Hai chart cùng gắn EA = hai kết nối cùng token đá nhau liên tục** (đã gây 388 nghìn alert
> 12→15/09). Kiểm menu **Window** và tab Experts: tên chart trong ngoặc chỉ được có **một**.

Quay lại cửa sổ trợ lý, bấm Enter để đi tiếp.

## A4. Cấu hình trên dashboard

Mở `http://127.0.0.1:8080` (mật khẩu in ra ở bước A1, và nằm trong `config.toml`) → tab **Cấu hình**.

**Bắt buộc — khối Agent:** khai **số tài khoản** và **tiêu đề cửa sổ terminal** cho từng clicker.

| Clicker | Số tài khoản | Tiêu đề cửa sổ |
|---|---|---|
| `AG-CLICKER` | tài khoản **Client** | thường chính là số tài khoản Client |
| `AG-CLICKER-MASTER` (nếu bật) | tài khoản **Master** | thường chính là số tài khoản Master |

Tiêu đề **phải chứa số tài khoản** — cửa sổ MT5 mở đầu tiêu đề bằng số tài khoản, và đó là thứ
clicker đối chiếu trước khi bấm. Đừng dùng chuỗi chung như `MetaTrader 5`: nó khớp cả hai terminal.
Bấm Lưu xong, clicker tự nối lại trong vài giây; chưa khai thì clicker **không chạy** (thoát mã 4 và
thử lại mỗi 60 giây).

**Bắt buộc — khối Ánh xạ symbol:** khai symbol Master ứng với symbol nào phía Client
(`XAUUSD` → `XAUUSDm`). Dashboard kiểm với sàn trước khi lưu. **Thiếu ánh xạ là mọi lệnh Master bị
bỏ qua trong im lặng.**

**Khối Client — tuỳ chọn:** chiều copy (`OPPOSITE` = Master BUY thì Client SELL), hệ số volume,
đường mở/đóng lệnh, và *Cho phép Client đóng ngược Master*.

- **Mở lệnh chỉ đi một chiều Master → Client.** Mở tay ở Client không làm Master vào lệnh.
- **Đóng:** Master đóng thì Client luôn đóng theo. Client đóng thì Master chỉ đóng theo khi
  *Cho phép Client đóng ngược Master* được bật (mặc định **tắt**).
- Đổi cấu hình chỉ áp cho **lệnh mới**; cặp đang mở giữ tỷ lệ cũ.

Làm bằng dòng lệnh cũng được, cùng một bộ ràng buộc:

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py -m bridge.admin cau-hinh-client CL-01                              # xem cấu hình hiện tại
& $py -m bridge.admin cau-hinh-client CL-01 --copy-mode OPPOSITE --multiplier 1.0
& $py -m bridge.admin cau-hinh-client CL-01 --can-close-master bat
& $py -m bridge.admin sua-agent AG-CLICKER --login <so-tk-Client> --terminal-title "<so-tk-Client>"
& $py -m bridge.admin anh-xa-symbol CL-01 XAUUSD --client-symbol XAUUSDm
```

## A5. Kiểm tra và bật copy

```powershell
.\scripts\kiem-tra.ps1
& $py -m bridge.admin liet-ke        # 4 (hoặc 3) agent ONLINE
& $py -m bridge.admin run-mode RUNNING
```

Thử trên **demo**, volume nhỏ nhất:

| Thử | Đạt khi |
|---|---|
| Mở 1 lệnh ở **Master** | Client có lệnh tương ứng trong ~1 giây, đúng chiều theo `copy_mode` |
| Đóng lệnh đó ở **Master** | Client đóng theo |
| Mở lại, đóng ở **Client** (khi `can-close-master bat`) | Master đóng theo; bật đường đóng Master UI thì deal hiện *Placed by manual* |
| `& $py -m bridge.admin kiem-reason` | `DAT` |
| `& $py -m bridge.admin kiem-dong-sai` | `[A] [B] [C]` đều 0 |

Xong phần A. Từ giờ theo **Phần C** mỗi lần đăng nhập.

---

# Phần B — VPS đã có hệ thống

## B1. Cập nhật lên code mới (việc thường gặp nhất)

```powershell
cd C:\CopyBridge
.\.venv\Scripts\python.exe -m bridge.admin tinh-hinh     # nên 0 cặp đang hedge
.\scripts\cai-dat.ps1 -CapNhat
```

`-CapNhat` làm theo thứ tự: sao lưu database → ghi commit cũ → dừng dịch vụ → `git pull` → cài lại
gói → chạy migration và bộ test → **nạp lại cả hai clicker** → bật lại dịch vụ. Cuối cùng in lệnh lùi
bản.

> **Luôn có `-CapNhat` trên máy đã cài.** Thiếu nó, script từ chối chạy khi dịch vụ đang Running
> — nếu không, code mới nằm trên đĩa nhưng Bridge và clicker vẫn chạy code cũ.

Sau khi cập nhật:

```powershell
.\scripts\kiem-tra.ps1                                     # mục 4b phải xanh (không còn tiến trình chạy code cũ)
.\.venv\Scripts\python.exe -m bridge.admin liet-ke         # agent ONLINE lại (clicker cần ~10-45 giây)
.\.venv\Scripts\python.exe -m bridge.admin run-mode RUNNING # Bridge khởi động lại luôn về PAUSED
```

Mở dashboard rồi **bấm `Ctrl+F5` một lần**: tab mở từ trước lần cập nhật vẫn chạy CSS/JS cũ, và
triệu chứng là "cập nhật xong mà dashboard y như cũ". Chỉ cần làm một lần cho mỗi tab đang mở.

### B1b. Riêng bản 2026-09-21 — cấu hình chuyển vào database (D-32)

Bản này có **migration 008** và đổi chỗ hai giá trị của clicker. Làm đúng bốn việc sau, một lần:

1. **Xoá `account_login` và `terminal_title`** khỏi mục `[clicker]` và `[clicker_master]` trong
   `config.toml` (Notepad, lưu **UTF-8 không BOM**). Còn chúng trong file thì **file thắng
   database**: khai trên dashboard sẽ không có tác dụng, và không script nào báo cho bạn biết —
   dấu hiệu duy nhất là hai dòng đỏ trong khối `config.toml` ở tab Cấu hình.
2. Khởi động lại dịch vụ để Bridge đọc lại file: `Restart-Service CopyBridge`.
3. Trên dashboard → tab **Cấu hình** → khối **Agent**: khai **số tài khoản** và **tiêu đề cửa sổ**
   cho từng clicker (xem A4). Chưa khai thì clicker thoát mã 4 và thử lại mỗi 60 giây; kiểm bằng
   `Get-Content logs\clicker-wrapper.log -Tail 20`.
4. Nếu bạn đang dùng đường đóng Master qua giao diện, kiểm tác vụ còn không:
   ```powershell
   Get-ScheduledTask -TaskPath '\CopyBridge\' | Select-Object TaskName, State
   ```
   Thiếu `ClickerMaster` thì `.\scripts\tao-dich-vu.ps1 -ChiTacVuClicker` (máy đang chạy — không
   đụng tới dịch vụ).

Xong bốn việc: `liet-ke` phải cho cả hai clicker **ONLINE**, và canary của chúng xanh trên dashboard.

**Nếu script in cảnh báo đỏ `ea/ thay doi`:** biên dịch lại EA, chép `.ex5` mới vào
`MQL5\Experts` của từng terminal (như A3), rồi **gỡ EA khỏi chart và gắn lại** với token cũ (đổi
khung thời gian không nạp lại `.ex5`). Biên dịch không cần mở MetaEditor:

```powershell
& "C:\Program Files\MetaTrader 5\MetaEditor64.exe" /compile:"C:\CopyBridge\ea\CopyBridgeMaster.mq5" /log:"C:\CopyBridge\logs\compile.log"
& "C:\Program Files\MetaTrader 5\MetaEditor64.exe" /compile:"C:\CopyBridge\ea\CopyBridgeClient.mq5" /log:"C:\CopyBridge\logs\compile.log"
```

**Dashboard trông như bản cũ sau khi cập nhật:** tải lại trang một lần bằng `Ctrl+F5`. Từ bản
2026-09-21 Bridge bảo trình duyệt hỏi lại mỗi lần nên chuyện này chỉ xảy ra đúng một lần, cho tab
đã mở từ **trước** lần cập nhật đó.

**Chạy lại clicker bằng tay** (khi nghi clicker chưa nạp code mới):

```powershell
Get-ScheduledTask -TaskPath '\CopyBridge\' | Where-Object TaskName -like 'Clicker*' | Stop-ScheduledTask
Get-ScheduledTask -TaskPath '\CopyBridge\' | Where-Object TaskName -like 'Clicker*' | Start-ScheduledTask
```

**`git pull` hỏng vì có sửa cục bộ:** script dừng và in `git status`. Script không tự `stash` hay
`reset`. `config.toml`, `data\`, `logs\` nằm ngoài git nên không bao giờ gây xung đột.

## B2. Lùi về bản cũ

Script in sẵn commit cũ ở cuối lần cập nhật.

**Bản mới không có migration** (không đổi database) — chỉ cần:

```powershell
git -C C:\CopyBridge checkout <commit-cu>
.\scripts\cai-dat.ps1 -CapNhat -BoQuaGit
```

`-BoQuaGit` là bắt buộc ở đây: sau `checkout` một commit, `git pull` không chạy được. Khi muốn quay
lại bản mới nhất: `git -C C:\CopyBridge checkout main` rồi `.\scripts\cai-dat.ps1 -CapNhat`.

**Bản 2026-09-21 CÓ migration (008).** Lùi khỏi nó thì không đủ `git checkout` — phải phục hồi
database từ bản sao lưu, theo đúng các bước dưới đây.

**Bản mới đã chạy migration** — phải phục hồi database từ bản sao lưu tạo **trước** lần cập nhật
(`data\backup\bridge-<ngày-giờ>.db`):

```powershell
Stop-Service CopyBridge
Get-ScheduledTask -TaskPath '\CopyBridge\' | Where-Object TaskName -like 'Clicker*' | Stop-ScheduledTask
Copy-Item data\bridge.db data\bridge-hong.db
Copy-Item data\backup\bridge-<ngay-gio>.db data\bridge.db -Force
Remove-Item data\bridge.db-wal, data\bridge.db-shm -ErrorAction SilentlyContinue   # BẮT BUỘC
git checkout <commit-cu>
.\scripts\cai-dat.ps1 -CapNhat -BoQuaGit
```

Không xoá `-wal`/`-shm` là trộn database của hai thời điểm. Mọi thứ xảy ra sau bản sao lưu (cặp mới,
lệnh mới) không còn trong sổ — đối chiếu tay với terminal.

## B3. Bật thêm tính năng trên hệ thống đang chạy

**Đóng phía Master qua giao diện** (deal đóng Master hiện *Placed by manual*) — cách dễ nhất là chạy
lại trợ lý và trả lời **có** ở câu *Bat duong DONG phia Master qua giao dien?*; các bước đã xong sẽ
tự bỏ qua:

```powershell
.\scripts\tro-ly.ps1 -ThuMuc C:\CopyBridge
```

Kiểm sau đó:

```powershell
Get-ScheduledTask -TaskPath '\CopyBridge\' | Select-Object TaskName, State   # có ClickerMaster
.\.venv\Scripts\python.exe -m bridge.admin liet-ke                           # AG-CLICKER-MASTER ONLINE
.\.venv\Scripts\python.exe -m bridge.admin cau-hinh-master                   # close_route UI
```

- Thiếu tác vụ `ClickerMaster`: `.\scripts\tao-dich-vu.ps1 -ChiTacVuClicker`
- Clicker Master chưa lái terminal nào: khai số tài khoản + tiêu đề cửa sổ cho `AG-CLICKER-MASTER`
  trên dashboard (tab Cấu hình → Agent), hoặc
  `.\.venv\Scripts\python.exe -m bridge.admin sua-agent AG-CLICKER-MASTER --login <so-tk-Master> --terminal-title "<so-tk-Master>"`

**Đổi chiều copy, hệ số, đóng hai chiều:** trên dashboard, tab Cấu hình → khối Client (xem [A4](#a4-cấu-hình-trên-dashboard)).

**Thêm symbol:** trên dashboard (tab Cấu hình → Ánh xạ symbol), hoặc
`.\.venv\Scripts\python.exe -m bridge.admin anh-xa-symbol CL-01 <symbol-Master> --client-symbol <symbol-Client>`.
Thôi copy một symbol: **Tắt** giữ lại dòng để bật sau, **Xoá** bỏ hẳn khỏi danh sách
(`--tat` / `--xoa` nếu dùng dòng lệnh). Cặp đang mở không bị ảnh hưởng — đường đóng nhắm
theo `position_id` chứ không tra bảng ánh xạ.
(EA Client phải đang chạy, symbol có trong Market Watch). Nhớ: terminal Client chỉ copy symbol của
chart đang gắn EA.

## B4. Đổi tài khoản MT5

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py -m bridge.admin run-mode PAUSED
& $py -m bridge.admin tinh-hinh                          # phải 0 cặp đang hedge
```

Rồi trên dashboard, tab **Cấu hình** → khối **Agent**: sửa số tài khoản của `AG-CLIENT` và sửa
**cả số tài khoản lẫn tiêu đề cửa sổ** của `AG-CLICKER`. Clicker tự nối lại và lái cửa sổ mới trong
vài giây — **không** phải sửa `config.toml`, không phải đăng ký lại tác vụ. Đổi tài khoản Master thì
làm tương tự với `AG-MASTER` và `AG-CLICKER-MASTER`. Token giữ nguyên; EA giữ nguyên token cũ.

## B5. Chuyển sang VPS mới, giữ nguyên dữ liệu

1. Máy cũ: `run-mode PAUSED`, chờ 0 cặp đang hedge, rồi
   `.\.venv\Scripts\python.exe -m bridge.admin sao-luu` và dừng hết:
   ```powershell
   .\scripts\tao-dich-vu.ps1 -GoBo
   ```
2. Chép sang máy mới: bản sao lưu vừa tạo trong `data\backup\` và `config.toml`.
3. Máy mới: làm **A0** và **A1**, rồi thay database và cấu hình:
   ```powershell
   Copy-Item <ban-sao-luu>.db C:\CopyBridge\data\bridge.db -Force
   Remove-Item C:\CopyBridge\data\bridge.db-wal, C:\CopyBridge\data\bridge.db-shm -ErrorAction SilentlyContinue
   Copy-Item <config.toml-cu> C:\CopyBridge\config.toml -Force
   ```
4. Chạy **A2** (trợ lý thấy agent và client đã có, bỏ qua các bước đó — **đừng cấp lại token**),
   gắn EA với **token cũ** (A3), rồi A5.

Token nằm trong database (dạng hash) và `config.toml`, nên chép đủ hai thứ này thì EA và clicker
dùng lại được token cũ. Mất token EA thì cấp lại trên dashboard (tab Cấu hình → Agent → *Cấp lại
token*, chỉ dùng được khi dashboard có mật khẩu) hoặc bằng `bridge.admin cap-token`, rồi dán lại
vào EA. Cấu hình nghiệp vụ nằm trong database nên đi theo bản sao lưu — không phải khai lại.

## B6. Thêm Client thứ hai, tắt hoặc xoá Client đang có

**Một Client = một terminal MT5 riêng.** Thêm `CL-02` không chỉ là thêm một dòng cấu hình; nó cần:

| Cần gì | Làm ở đâu |
|---|---|
| Terminal MT5 thứ ba, đăng nhập tài khoản Client thứ hai | Trên VPS, như A0 |
| Một agent `CLIENT` riêng + token riêng, EA gắn lên đúng terminal đó | Dashboard → Cấu hình → Agent → *Thêm agent* (**chỉ dùng được khi dashboard có mật khẩu**); token hiện một lần, dán vào EA |
| Dòng cấu hình `CL-02` | Dashboard → Cấu hình → khối **Thêm Client** |
| Ánh xạ symbol cho `CL-02` | Dashboard → Cấu hình → Ánh xạ symbol |
| **Một clicker riêng**, nếu muốn `CL-02` mở/đóng qua giao diện | **Chưa hỗ trợ** — xem dưới |

> **Giới hạn hiện tại: hệ thống chạy được đúng hai clicker** (`clicker` cho Client, `clicker_master`
> cho Master). Nên `CL-02` hôm nay phải đi **đường EA** cho cả mở lẫn đóng: nó hoạt động bình
> thường, chỉ khác là deal mang `DEAL_REASON = EXPERT` chứ không phải `CLIENT`. Muốn `CL-02` cũng
> đi qua giao diện thì cần mở rộng phần cấu hình clicker — chưa làm (B-19).

**Tắt một Client** (khối *Cấu hình copy* → *Trạng thái Client* → `ĐÃ TẮT` → Lưu): ngừng copy lệnh
**mới** cho Client đó. Cặp đang mở **giữ nguyên và vẫn đóng theo Master**. Đây là cách dừng một
Client mà không mất gì.

**Xoá một Client** (nút *Xoá* cạnh nút *Lưu*): chỉ làm được khi Client **chưa có cặp lệnh nào**.
Có rồi thì dashboard từ chối và bảo bạn tắt — vì `pair` trỏ vào dòng này, xoá đi là mất luôn đường
đọc lại lịch sử của những cặp đó. Xoá kéo theo ánh xạ symbol của chính Client đó.

Bằng dòng lệnh, cùng một bộ ràng buộc:

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py -m bridge.admin them-client CL-02 --agent AG-CLIENT-2 --open-route EA --close-route EA
& $py -m bridge.admin cau-hinh-client CL-01 --hoat-dong tat    # tat, giu lich su
& $py -m bridge.admin xoa-client CL-02                          # chi khi chua co cap nao
```

## B7. Cài lại sạch từ đầu

Chỉ khi muốn **xoá hết lịch sử** (cặp, lệnh, alert):

```powershell
.\scripts\tao-dich-vu.ps1 -GoBo
Rename-Item C:\CopyBridge C:\CopyBridge-cu-$(Get-Date -Format yyyyMMdd)
```

Rồi làm lại **Phần A** từ A1. Token cũ mất hiệu lực — gắn lại EA với token mới.

---

# Phần C — Vận hành hằng ngày

**Mỗi lần đăng nhập VPS:**

```powershell
cd C:\CopyBridge
.\scripts\kiem-tra.ps1
```

Mục cuối là `tinh-hinh` — cách duy nhất biết chuyện đã xảy ra (không có kênh cảnh báo ngoài).
Dashboard: `http://127.0.0.1:8080` (chỉ mở được trong VPS; mật khẩu trong `config.toml`).

**Sau mỗi lần VPS hoặc Bridge khởi động lại** — Bridge luôn về `PAUSED` (D-15), có chủ đích:

1. Kiểm nút **Algo Trading** xanh và Toolbox ở tab **Trade** trên **cả hai** terminal.
2. `.\.venv\Scripts\python.exe -m bridge.admin liet-ke` — agent `ONLINE`.
3. Bấm **Bắt đầu copy** ở đầu trang dashboard, hoặc
   `.\.venv\Scripts\python.exe -m bridge.admin run-mode RUNNING`

| `run_mode` | Mở lệnh mới | Đồng bộ đóng |
|---|---|---|
| `RUNNING` (nút **Bắt đầu copy**) | có | có |
| `PAUSE_NEW_ENTRIES` (nút **Tạm dừng lệnh mới**) | không | có |
| `PAUSED` (nút **Dừng toàn bộ đồng bộ**) | không | **không** — đóng một bên thì bên kia vẫn mở |
| `EMERGENCY` (**chỉ đặt bằng dòng lệnh**) | không | đóng tất cả |

Dừng khẩn cấp **không còn nút trên dashboard** (D-33):
`.\.venv\Scripts\python.exe -m bridge.admin run-mode EMERGENCY`. Thử một lần trên demo trước khi
cần tới nó.

**Đặt lại hệ thống** nằm ở cuối tab Cấu hình, hai mức, mỗi mức một cụm xác nhận phải gõ tay:

| Nút | Xoá | Giữ |
|---|---|---|
| **Đặt lại dữ liệu** (`DAT LAI DU LIEU`) | cặp lệnh, vị thế Master, event, lệnh đã gửi, cảnh báo, sai lệch | agent, token, client, ánh xạ symbol, khoá hệ thống |
| **Đặt lại toàn bộ** (`DAT LAI TAT CA`) | như trên, **cộng** client và ánh xạ symbol; khoá hệ thống về mặc định | agent và token — nên **không** phải dán lại token vào EA |

Cả hai chỉ chạy khi `run_mode = PAUSED`, không còn cặp hay vị thế Master nào mở, và không còn lệnh
nào chưa xong. Database được **sao lưu trước khi xoá** (`data\backup\bridge-<ngày-giờ>.db`) — đó là
đường lùi duy nhất. Dòng lệnh tương đương:
`bridge.admin dat-lai du-lieu --xac-nhan "DAT LAI DU LIEU"`.

**Lệnh hay dùng** (`.\.venv\Scripts\python.exe -m bridge.admin ...`):

| Lệnh | Việc |
|---|---|
| `tinh-hinh` | Có gì cần làm không |
| `liet-ke` | Trạng thái agent |
| `run-mode [RUNNING\|PAUSE_NEW_ENTRIES\|PAUSED]` | Xem / đặt chế độ |
| `cau-hinh-client CL-01 [...]` | Xem / sửa cấu hình copy |
| `cau-hinh-client CL-01 --hoat-dong tat` | Ngừng copy lệnh mới cho Client đó (cặp đang mở vẫn đóng theo Master) |
| `xoa-client CL-02` | Xoá hẳn một Client — chỉ khi nó chưa có cặp lệnh nào |
| `dat-lai du-lieu\|tat-ca --xac-nhan "<cụm>"` | Đặt lại hệ thống (sao lưu trước khi xoá) |
| `run-mode EMERGENCY` | Đóng tất cả — đường duy nhất sau khi gỡ nút khỏi dashboard |
| `cau-hinh-master [...]` | Xem / sửa đường đóng phía Master |
| `anh-xa-symbol CL-01 [...]` | Xem / khai ánh xạ symbol |
| `kiem-reason` | Mọi deal của bot mang `DEAL_REASON_CLIENT` |
| `kiem-dong-sai [--ngay YYYY-MM-DD]` | Có lệnh nào bị đóng nhầm không |
| `xac-nhan-alert --code <MA> --truoc <moc> [--that]` | Đánh dấu đã xem alert cũ |
| `sao-luu` | Sao lưu ngay |
| `cap-token <agent>` | Cấp lại token (token cũ hết hiệu lực ngay) |
| `sua-agent <agent> [--login N] [--terminal-title "N"]` | Sửa số tài khoản / tiêu đề cửa sổ của clicker. Hai cờ đều tuỳ chọn, phải có ít nhất một |

**Log:** `logs\bridge.log`, `logs\clicker.log`, `logs\clicker_master.log`, `logs\service-err.log`.

**Cấu hình nằm ở đâu:** cấu hình *nghiệp vụ* (agent, client, ánh xạ symbol, khoá hệ thống) nằm
trong database — sửa trên dashboard là có hiệu lực ngay. `config.toml` giữ thứ cần **trước khi**
Bridge chạy: cổng, đường dẫn DB, mật khẩu dashboard, token clicker. Dashboard cũng sửa được các
khoá này, nhưng giá trị mới chỉ có hiệu lực **sau khi khởi động lại dịch vụ**:
`Restart-Service CopyBridge`. Giá trị bí mật không bao giờ hiện lại trên màn hình — ô để trống
nghĩa là giữ nguyên (D-32).

Nội dung mới được kiểm bằng đúng phép kiểm của lần khởi động **trước khi** ghi, nên một giá trị
sai bị từ chối và file cũ không hề bị đụng tới — không cần sửa tay sau một lần bị từ chối. Mỗi lần
lưu để lại `config.toml.bak-<ngày-giờ>` cạnh file gốc và chỉ giữ **5 bản gần nhất**; đó là bản rõ
của mật khẩu và token nên đừng chép chúng đi đâu.

**Một khoá còn sót trong `config.toml` sẽ đè giá trị khai trên dashboard** (thứ tự: dòng lệnh >
`config.toml` > Bridge). Bản cài cũ thường còn `account_login` và `terminal_title` trong mục
`[clicker]`: trang Cấu hình hiện chúng kèm cảnh báo, xoá khỏi file thì dashboard mới có tác dụng.

**Không bao giờ** sửa database bằng tay, và không đưa token lên dòng lệnh hay ảnh chụp màn hình.

---

## Những gì script KHÔNG làm được

Các script in danh sách này ở cuối mỗi lần chạy (`scripts\canh-bao.txt`). Không làm = có thể mất tiền.

1. **Phiên RDP ngắt (B-08) chưa được đo chính thức.** Ngắt RDP bằng cách **đóng cửa sổ**, không
   bao giờ *Sign out* (Sign out giết cả MT5 lẫn clicker).
2. **Algo Trading** phải bật trên cả hai terminal — là lưới cuối khi clicker hỏng.
3. **Bấm `RUNNING` bằng tay** sau mỗi lần khởi động lại.
4. **Mỗi terminal Client chỉ copy một symbol** (B-01).
5. **Cài MT5 và gắn EA phải làm tay**; biên dịch lại EA thì gỡ ra gắn lại.
6. **Clicker và MT5 cùng mức quyền.**
7. **Khai số tài khoản + tiêu đề cửa sổ cho từng clicker trên dashboard** (A4). Trợ lý không hỏi
   hai giá trị này nữa; chưa khai thì clicker thoát mã 4 và thử lại mỗi 60 giây — hệ thống dựng
   xong vẫn không bấm được lệnh nào. Cùng trang đó khai **ánh xạ symbol**.
   **Bản cài cũ:** xoá `account_login`/`terminal_title` khỏi `config.toml` trước, vì file thắng
   database và không script nào kiểm hộ (B1b).

Rủi ro không phải kỹ thuật: hai tài khoản vào lệnh ngược chiều, cùng symbol, cách nhau dưới một giây,
**cùng IP** — nhiều broker cấm. Đọc điều khoản của cả hai broker.

## Sự cố khi cài

| Hiện tượng | Xử lý |
|---|---|
| `Tai bo cai Python that bai` | VPS chặn mạng ra ngoài. Tải tay bộ cài hoặc `-UrlPython <link>` |
| Cài Python xong vẫn báo không gọi được | Đóng PowerShell, mở lại, chạy lại script |
| `Dich vu CopyBridge dang chay ... -CapNhat` | Máy đã có hệ thống: dùng `cai-dat.ps1 -CapNhat` (B1) |
| `.venv san co khong dung duoc` | Chạy lại với `-LamMoiVenv` |
| Bridge không khởi động, lỗi TOML | `config.toml` bị lưu có BOM — lưu lại UTF-8 không BOM. Xem `logs\service-err.log` |
| EA không lên `ONLINE` | Thiếu `127.0.0.1` trong *Allow WebRequest*, sai token, hoặc Bridge chưa chạy |
| Log EA `REPLACED`, alert `AGENT_DUPLICATE_CONNECTION` | EA gắn trên hai chart — gỡ bớt (A3) |
| `Khong co client CL-01` | Chưa tạo client — chạy lại trợ lý |
| Lệnh Master không copy | `run_mode` chưa `RUNNING`, thiếu ánh xạ symbol, hoặc clicker chưa `ONLINE` |
| Clicker thoát mã 2 | Thiếu `token` trong `[clicker]` của `config.toml` |
| Clicker thoát mã 4, log `chua khai terminal` | Chưa khai số tài khoản + tiêu đề cửa sổ cho clicker đó trên dashboard (A4). Khác mã 2 và 3: mã 4 **tự thử lại mỗi 60 giây**, khai xong là clicker tự lên, không phải chạy lại tác vụ |
| Canary clicker đỏ, log `Tieu de cua so la tai khoan ...` | Tiêu đề đang trỏ vào terminal của tài khoản khác — sửa trên dashboard |
| Clicker thoát mã 3 / `Da co mot clicker khac` | Đã có clicker khác lái terminal đó — đúng thiết kế |
| Log **EA** báo `ACCOUNT_MISMATCH` | Token đang gắn với tài khoản MT5 khác. `sua-agent <agent> --login <so-dung>`, hoặc gắn lại đúng token vào đúng terminal |
| Log **clicker** báo `ACCOUNT_MISMATCH` | Chỉ xảy ra khi `config.toml` còn khai `account_login` lệch với DB — **file thắng database**. Xoá khoá đó khỏi file rồi khai trên dashboard |
| Clicker chạy mà không bấm được gì | Lệch mức quyền với MT5, hoặc tác vụ không chạy kiểu *Interactive* |
| Đóng lệnh báo `Tab Trade ... khong mo` | Chuyển Toolbox về tab Trade |
| Clicker báo `Hop thoai khong dung hinh dang` | MT5 khác build — đo lại theo RUNBOOK mục 5a |

## Trước khi chuyển sang tài khoản thật

RUNBOOK mục 8. Tóm tắt: chạy ổn định trên demo ít nhất một tuần; đo B-08 (RDP ngắt) và TEST-19 (mất
điện đột ngột); đọc điều khoản cả hai broker; bắt đầu bằng **một symbol** và volume nhỏ nhất.
