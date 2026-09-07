# Cài đặt lên VPS Windows

*Tài liệu này nói **gõ gì**, ngắn gọn. Bản chi tiết cho người vận hành — kèm cả quy trình
**cập nhật** khi có mã nguồn mới — là
[HUONG-DAN-CUNG-VPS-SCRIPT.html](HUONG-DAN-CUNG-VPS-SCRIPT.html). Muốn biết **vì sao** thì đọc
[RUNBOOK.md](RUNBOOK.md) mục 5b.*

Kiến trúc ở đây là **tất cả trên một VPS**: Bridge, clicker và cả hai terminal MT5 cùng một máy.
Agent nối tới Bridge qua `127.0.0.1`, nên không cần Tailscale, không cần luật firewall, không cần
máy thứ ba để kiểm.

---

## 0. Trước khi bắt đầu

**Cấu hình máy.** Đo thực tế lúc chạy không tải: mỗi terminal MT5 ~157 MB, Bridge ~49 MB,
clicker ~4 MB. Cộng Windows Server thì **4 GB RAM là mức nên có**, 2 GB sẽ chật. CPU 2 nhân là đủ
— đường mở lệnh bị chặn ở tốc độ giao diện MT5 (~600 ms/lệnh), không phải ở CPU. Windows Server
2019 hoặc 2022.

**Ba thứ bắt buộc phải bật trước, không phải tuỳ chọn** — clicker phải sống trong một phiên người
dùng đang tồn tại:

1. **Autologon** (`netplwiz`, bỏ tick "Users must enter a user name and password").
2. **Tắt sleep và hibernate**: `powercfg /change standby-timeout-ac 0` và `powercfg /hibernate off`.
3. **Tắt khoá màn hình tự động** (Screen saver → On resume, bỏ tick "display logon screen").

Bạn cũng cần quyền Administrator để cài Python và đăng ký dịch vụ.

---

## 1. Cài đặt một cú bấm

Mở PowerShell bằng **Run as administrator**:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
```

### Đường A — VPS trắng, chưa cài gì (khuyến nghị)

Kho là public nên tải thẳng được — không cần git, không cần token, không cần kéo file qua RDP.
Script tự cài Python, tự cài git, rồi tự clone vào `C:\CopyBridge`.

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest "https://raw.githubusercontent.com/taducloc0603/copy-trade/main/scripts/cai-dat.ps1" `
  -OutFile "$env:USERPROFILE\Desktop\cai-dat.ps1" -UseBasicParsing
& "$env:USERPROFILE\Desktop\cai-dat.ps1" -ThuMuc C:\CopyBridge
```

> **Đọc dòng banner đầu tiên.** Nó phải in `MT5 Copy Bridge -- cai dat (ban <ngày>)`. Không
> thấy `(ban ...)` nghĩa là bạn đang chạy một bản `cai-dat.ps1` cũ còn sót trên máy — chạy lại
> lệnh tải ở trên để đè nó. Bản cũ sẽ báo những lỗi đã được sửa từ lâu, chẳng hạn
> `khong co winget`.

### Đường B — máy đã có sẵn git

```powershell
git clone https://github.com/taducloc0603/copy-trade.git C:\CopyBridge
C:\CopyBridge\scripts\cai-dat.ps1 -ThuMuc C:\CopyBridge
```

### Đường C — chép thư mục qua RDP

Nén thư mục dự án ở máy của bạn (**không** kèm `.venv`, `data`, `logs`), kéo thả qua Remote
Desktop vào `C:\CopyBridge`, rồi:

```powershell
C:\CopyBridge\scripts\cai-dat.ps1 -ThuMuc C:\CopyBridge -BoQuaGit
```

Script tự làm 11 bước: cài Python 3.12 và git nếu thiếu (bằng winget, hoặc tải thẳng bộ cài từ
python.org và git-scm.com nếu máy không có winget — Windows Server thì gần như luôn không có),
lấy mã nguồn, tạo `.venv`, `pip install -e ".[dev]"`, tạo `data/` + `logs/`, tạo `config.toml`
với mật khẩu dashboard ngẫu nhiên, khởi tạo database, chạy bộ test. **Chạy lại bao nhiêu lần
cũng được** — mọi bước đã xong sẽ in `BO QUA`.

Mật khẩu dashboard được in ra một lần và nằm trong `C:\CopyBridge\config.toml` (đọc lại được — khác
với token của agent).

---

## 2. Tạo agent và cấp token

Database mới **luôn rỗng**: `data/` nằm trong `.gitignore`, nên bản clone trên VPS không mang theo
agent nào của máy cũ.

```powershell
cd C:\CopyBridge
$py = ".venv\Scripts\python.exe"
& $py -m bridge.admin them-agent AG-MASTER  --role MASTER  --magic 770001 --login <so-tk-master>
& $py -m bridge.admin them-agent AG-CLIENT  --role CLIENT  --magic 770001 --login <so-tk-client>
& $py -m bridge.admin them-agent AG-CLICKER --role CLICKER --magic 770001 --login <so-tk-client>

& $py -m bridge.admin cap-token AG-MASTER
& $py -m bridge.admin cap-token AG-CLIENT
& $py -m bridge.admin cap-token AG-CLICKER
```

**Token thô hiện đúng một lần** và không đi vào log. Mất thì cấp lại — không có đường đọc lại.

- Token của `AG-MASTER` và `AG-CLIENT` điền vào tham số `AgentToken` của EA tương ứng.
- Token của `AG-CLICKER` điền vào mục `[clicker]` trong `config.toml`:

```toml
[clicker]
token = "<token-vua-cap>"
account_login = 538217
terminal_title = "538217"
```

Đừng truyền token của clicker trên dòng lệnh. Dòng lệnh của một tiến trình là thứ **mọi tài khoản
trên cùng máy** đọc được bằng `Get-CimInstance Win32_Process`, và clicker chạy 24/7.

---

## 3. Khai báo ánh xạ symbol

**Đừng bỏ bước này.** Thiếu ánh xạ thì `find_symbol_map` trả `None` và **mọi lệnh Master bị bỏ qua
trong im lặng** — người cài lần đầu dựng xong toàn hệ thống rồi ngồi nhìn không có gì xảy ra.

```powershell
& $py -m bridge.admin anh-xa-symbol --help
```

Lệnh này cần **EA Client đang chạy** và symbol đã kéo vào Market Watch, vì nó kiểm `symbol_spec`
trước khi lưu. Nên làm sau bước 4.

---

## 4. MT5 và EA

Script không làm hộ phần này.

1. Cài hai terminal MT5 (một cho Master, một cho Client). Đăng nhập cả hai, tài khoản phải ở chế
   độ **Hedging**.
2. Biên dịch EA, không cần mở giao diện MetaEditor:
   ```powershell
   & "C:\Program Files\MetaTrader 5\MetaEditor64.exe" /compile:"C:\CopyBridge\ea\CopyBridgeMaster.mq5" /log:"C:\CopyBridge\logs\compile.log"
   & "C:\Program Files\MetaTrader 5\MetaEditor64.exe" /compile:"C:\CopyBridge\ea\CopyBridgeClient.mq5" /log:"C:\CopyBridge\logs\compile.log"
   ```
3. Chép `.ex5` vào `MQL5\Experts` của từng terminal, gắn EA lên chart, điền `AgentToken`
   (`BridgeHost` để `127.0.0.1`, `BridgePort` để `8787`).
4. **Bật nút Algo Trading trên cả hai terminal.**

> **Biên dịch lại thì phải GỠ EA khỏi chart rồi GẮN LẠI.** Đổi khung thời gian chỉ gọi lại
> `OnInit` trên bản đã nạp trong bộ nhớ — MT5 **không** đọc lại `.ex5` từ đĩa. Dấu hiệu nạp đúng
> bản mới: tab Experts hiện `CopyBridgeMaster khoi dong [co kha nang DONG lenh]`.

Client chỉ copy được **một symbol** cho mỗi terminal (B-01): hộp thoại New Order lấy symbol theo
chart đang mở. Mở đúng chart đó và giữ nguyên.

---

## 5. Đăng ký dịch vụ và tác vụ

```powershell
C:\CopyBridge\scripts\tao-dich-vu.ps1 -ThuMuc C:\CopyBridge -AccountLogin 538217 -TerminalTitle "538217"
```

Script sẽ hỏi mật khẩu của tài khoản autologon. Nhập vào thì dịch vụ chạy bằng chính tài khoản đó
— khuyến nghị, vì khi đó dịch vụ, clicker, tác vụ bảo trì và lệnh bạn gõ tay đều cùng một danh
tính trên cùng file SQLite. Bỏ trống thì dịch vụ chạy bằng LocalSystem và script tự cấp quyền
Modify cho bạn trên thư mục dự án.

Nó tạo bốn thứ:

| Tên | Loại | Việc |
|---|---|---|
| `CopyBridge` | Windows Service (NSSM) | Bridge + dashboard, tự bật khi máy khởi động |
| `\CopyBridge\Clicker` | Scheduled Task khi đăng nhập | clicker, trễ 90 giây cho MT5 nạp xong chart |
| `\CopyBridge\BaoTri` | Scheduled Task hằng ngày 03:00 | retention + sao lưu + kiểm chứng bản sao lưu |
| `\CopyBridge\TinhHinh` | Scheduled Task mỗi giờ | `tinh-hinh`; xem cột *Last Run Result* |

Sau khi đăng ký, script **tự chạy bài kiểm** mà RUNBOOK mục 6 để trống: giết tiến trình Bridge,
chờ, rồi xác nhận dịch vụ tự bật lại và `run_mode` trở về `PAUSED`.

Gỡ hết: `C:\CopyBridge\scripts\tao-dich-vu.ps1 -GoBo`

> **Mức toàn vẹn của clicker phải ≥ của MT5.** MT5 chạy "Run as administrator" mà clicker chạy
> thường thì UIPI chặn hết window message: `PostMessage` trả về thành công nhưng **không có gì xảy
> ra**. Hoặc cả hai đều thường, hoặc cả hai đều nâng quyền.

---

## 6. Việc mỗi lần đăng nhập vào VPS

```powershell
C:\CopyBridge\scripts\kiem-tra.ps1
```

Chín mục kiểm; mã thoát bằng số mục hỏng. Mục quan trọng nhất là mục cuối — `bridge.admin
tinh-hinh` — vì kênh cảnh báo ngoài đang **tắt có chủ đích** và đây là cách duy nhất bạn biết
chuyện đã xảy ra. (Kênh Telegram có sẵn nhưng để trống: điền `telegram_token` và
`telegram_chat_id` trong mục `[security]` của `config.toml` thì alert mức ERROR/CRITICAL sẽ được
gửi ra. Nó **chưa từng được kiểm chứng bằng tin thật** — xem RUNBOOK mục 6.)

Rồi bật copy theo **đúng thứ tự ba bước** (RUNBOOK mục 3):

1. Bridge đã chạy sẵn ở `PAUSED`. Backlog trong outbox của EA chảy vào và được ghi nhận `IGNORED`
   — đây là cách sạch nhất để dọn hàng đợi mà không sinh lệnh nào.
2. Kiểm **canary của clicker xanh** trên dashboard trước khi đi tiếp.
3. Chờ 0 event `PENDING`, rồi mới đặt `RUNNING`.

Dashboard: `http://127.0.0.1:8080` (chỉ mở được từ trong VPS — đó là chủ đích của
`host = "127.0.0.1"`). Ba thứ nhìn trước tiên: `run_mode`, canary của clicker, số finding đang chờ.

**Phải bấm `RUNNING` bằng tay sau mỗi lần khởi động lại.** Dịch vụ tự bật lại **không** có nghĩa
hệ thống đang copy lệnh.

---

## 7. Cập nhật

```powershell
C:\CopyBridge\scripts\cai-dat.ps1 -CapNhat
```

Nó sao lưu database trước (`VACUUM INTO`, an toàn với WAL), ghi lại commit hiện tại, dừng dịch vụ,
`git pull --ff-only`, cài lại gói, chạy bộ test, bật lại dịch vụ. Nếu `ea/` có thay đổi thì nó in
cảnh báo đỏ nhắc biên dịch lại và **gắn lại EA**.

Đường lùi được in ra cuối: `git -C C:\CopyBridge checkout <commit-cũ>` rồi chạy lại.

Script **không tự `stash`, không tự `reset --hard`**. `git pull` hỏng vì có sửa cục bộ thì nó dừng
và in `git status` cho bạn xử lý.

---

## 8. Những gì script KHÔNG làm được

Sáu việc dưới đây in ra ở cuối mỗi lần chạy `cai-dat.ps1` và `kiem-tra.ps1`. Không làm = mất tiền.

1. **Phiên RDP ngắt (B-08) — chưa ai chứng minh.** Toàn bộ đường mở lệnh dựa vào clicker điều
   khiển giao diện MT5 bằng `PostMessage`. Lập luận "chạy được khi phiên RDP đã ngắt" chưa bao giờ
   được đo trên VPS thật; `docs/BACKLOG.md` đánh dấu nó **chặn triển khai VPS**. Phải đo trước khi
   tin: ngắt phiên RDP (đóng cửa sổ, **không** Sign out), mở lệnh trên Master, rồi kiểm **qua
   database** xem cặp có được tạo không.
2. **Algo Trading (B-09).** Đường **mở** phía Client đi qua giao diện nên **không cần** Algo
   Trading; đường **đóng** đi qua EA nên **cần**. Terminal tắt Algo Trading vẫn mở lệnh bình
   thường rồi mới hỏng lúc đóng — hỏng muộn nhất có thể. Bridge hiện **không nhìn thấy** trạng
   thái này. Kiểm lại sau mỗi lần VPS khởi động lại hoặc MT5 tự cập nhật.
3. **Phải bấm `RUNNING` bằng tay sau mỗi lần khởi động lại (D-15).**
4. **Mỗi terminal Client chỉ copy được một symbol (B-01).**
5. **MT5 và EA phải làm tay** — và biên dịch lại thì phải gỡ EA khỏi chart rồi gắn lại.
6. **Mức toàn vẹn của clicker phải ≥ của MT5** (UIPI).

Thêm một rủi ro không phải kỹ thuật: hai tài khoản mở vị thế ngược chiều, cùng symbol, cách nhau
dưới một giây, **từ cùng một IP** là dấu vết rất dễ nhận. Nhiều broker cấm hoặc huỷ lợi nhuận từ
mô hình này. Đây là rủi ro **điều khoản**, và nó không hiện ra trong bất kỳ log nào cho tới lúc
tài khoản bị xử lý. Đọc điều khoản của cả hai broker.

---

## 9. Sự cố khi cài

| Hiện tượng | Nguyên nhân | Xử lý |
|---|---|---|
| `Tai bo cai Python that bai` | VPS chặn mạng ra ngoài, hoặc proxy nội bộ | Tải tay bộ cài rồi chạy lại, hoặc trỏ `-UrlPython <link-nội-bộ>` |
| `Bo cai Python ket thuc voi ma <n>` | Bộ cài silent bị chặn | Chạy tay file `.exe` trong `%TEMP%` để xem nó báo gì; nhớ tích **"Add python.exe to PATH"** |
| Cài Python xong vẫn báo không gọi được | PATH trong tiến trình PowerShell hiện tại đã cũ | Đóng PowerShell, mở lại, chạy lại script |
| `git clone that bai` | Repo private | `gh auth login` rồi `gh repo clone`, hoặc `-Repo "https://<PAT>@github.com/..."`, hoặc chép thư mục qua RDP rồi `-BoQuaGit` |
| `.venv san co khong dung duoc` | Chép cả `.venv` qua RDP; đường dẫn tuyệt đối bên trong vẫn trỏ về máy cũ | Chạy lại với `-LamMoiVenv` |
| `import bridge, clicker` thất bại | Gói cài không ở chế độ editable | `pyproject.toml` chỉ khai báo `packages = ["bridge"]`; phải `pip install -e .` |
| Bridge từ chối khởi động, lỗi parse TOML | `config.toml` có BOM | Ghi lại bằng UTF-8 **không BOM** |
| Dịch vụ không lên | Xem `logs\service-err.log` | Thường là `config.toml` sai |
| Dịch vụ không dừng sạch | `AppStopMethodConsole` bị đổi | Bridge chỉ dừng sạch qua sự kiện Ctrl+C; xem `tao-dich-vu.ps1` |
| Task Clicker chạy mà không bấm được gì | `LogonType` sai, hoặc UIPI | `LogonType` phải là `Interactive`, không phải `S4U`/`Password`; và mức toàn vẹn clicker phải ≥ MT5 |
| clicker thoát ngay, mã 2 | Thiếu token / số tài khoản | Điền mục `[clicker]` trong `config.toml` |
| clicker thoát mã 3 | Đã có một clicker khác lái terminal đó | Đúng thiết kế. Tìm và tắt tiến trình kia |

---

## 10. Trước khi chuyển sang tài khoản thật

Xem [RUNBOOK.md](RUNBOOK.md) mục 8 và [KE-HOACH-CHAY-THAT.md](KE-HOACH-CHAY-THAT.md). Tóm tắt:
chạy ổn định trên demo ít nhất một tuần, xong bài B-08 và B-09, đọc điều khoản của cả hai broker,
bắt đầu bằng volume nhỏ nhất và một symbol duy nhất, và **thử nút dừng khẩn cấp một lần trên demo
trước khi cần dùng tới nó**.
