# Việc còn nợ trên VPS — gom lại chạy một lượt

*Cập nhật 2026-09-14. Đây là **danh sách đang mở**: mỗi lần làm xong một mục thì xoá mục đó đi và
ghi kết quả vào `PROGRESS.md`. Việc nào cần chạy trên VPS mà chưa chạy thì phải nằm ở đây, không
nằm trong trí nhớ ai cả.*

Trạng thái VPS lần cuối (2026-09-13): commit `de38de7`, `CLOSE_UI` 0,77 giây, `kiem-reason` ĐẠT,
sổ sạch. Mọi thứ bên dưới là **của các bản sau đó** và **chưa bản nào chạy trên VPS**.

---

## 1. Cập nhật và kiểm nền

```powershell
cd C:\CopyBridge
.\.venv\Scripts\python.exe -m bridge.admin run-mode PAUSED
.\.venv\Scripts\python.exe -m bridge.admin tinh-hinh     # 0 cap dang hedge moi cap nhat
.\scripts\cai-dat.ps1 -CapNhat
.\scripts\kiem-tra.ps1
```

**Đạt khi:** `git log -1` ra commit mới nhất; mục 4b của `kiem-tra.ps1` xanh; clicker có PID mới.

## 2. Đo ctrlID trên terminal **Master** — cổng chặn của phase 12

Chưa đo thì **không được bật** `master_close_route = UI`. Mở tay một lệnh `0.01` trên Master, nhấp
đúp vào dòng đó trong tab Trade, **không bấm Close**, rồi:

```powershell
$env:PYTHONPATH = "C:\CopyBridge"
.\.venv\Scripts\python.exe -m clicker.ui.dump --title <so-tai-khoan-Master> --all-controls
Remove-Item Env:PYTHONPATH
```

**Đạt khi:** tab Trade `10328`, nút Close `10410` (bản đang hiện, chữ bắt đầu `Close #`), ô volume
`10333`, tiêu đề bắt đầu `Position: #`. Lệch bất kỳ số nào → dừng, giữ đường EA cho Master.

## 3. Bật đường đóng Master qua giao diện (phase 12)

```powershell
.\scripts\tro-ly.ps1
```

Trả lời **có** ở câu *"Bat duong DONG phia Master qua giao dien?"*, điền tiêu đề cửa sổ terminal
Master. Trợ lý tự tạo agent, ghi token vào `[clicker_master]`, đăng ký tác vụ `ClickerMaster`, bật
`cau-hinh-master`. **Không phải chạm vào token.**

**Đạt khi:**

- `bridge.admin cau-hinh-master` in `master_close_route=UI`;
- có **hai** tiến trình clicker (`kiem-tra.ps1` mục 4);
- `logs\` có **ba** file đang được ghi: `bridge.log`, `clicker.log`, `clicker_master.log`;
- terminal Master mở Toolbox ở tab **Trade** và giữ nguyên.

## 4. TEST-30 — nghiệm thu đường đóng Master (`docs/ACCEPTANCE.md`)

Làm trên demo, `can_close_master = 1`:

| | Làm gì | Đạt khi |
|---|---|---|
| a | Mở ở Master, chờ Client copy, rồi **đóng ở Client** | Master đóng theo; `master_position.close_reason = 0`; lệnh `CLOSE_UI` tới clicker của Master |
| b | Tắt tác vụ `ClickerMaster`, rồi đóng ở Client | Master **vẫn đóng** qua EA; alert CRITICAL `CLOSE_MASTER_FELL_BACK_TO_EA` |
| c | Đóng khẩn cấp từ dashboard | Thứ tự Client → Master giữ nguyên; deal đóng Master mang `CLIENT` |
| d | `bridge.admin kiem-reason` | Có phần **TEST-30 DAT**; mục (b) xếp vào "đã có giải thích" |

```powershell
@'
import sqlite3
c = sqlite3.connect("file:data/bridge.db?mode=ro", uri=True)
for r in c.execute("SELECT master_position_id, symbol, status, close_reason, close_time "
                   "FROM master_position WHERE close_time >= date('now') ORDER BY master_position_id"):
    print(r)
for r in c.execute("SELECT type, target_agent_id, status, "
                   "ROUND((julianday(acked_at) - julianday(sent_at)) * 86400, 2) giay "
                   "FROM command WHERE created_at >= date('now') AND type LIKE 'CLOSE%' ORDER BY created_at"):
    print(r)
'@ | .\.venv\Scripts\python.exe -
```

## 5. Đo lại tốc độ sau khi có clicker thứ hai

`CLOSE_UI` phía Client phải vẫn quanh **0,8 giây**. Hai clicker chạy song song, mỗi cái một khoá và
một terminal, nên về lý thuyết không giành nhau — nhưng đó là lý thuyết, chưa đo.

Lần này log có thêm hai dòng để biết cắt được bao nhiêu từ bản bỏ đọc chữ thừa (2026-09-14):

```powershell
Select-String -Path logs\clicker.log -Pattern 'Tim danh sach Trade|Doc control hop thoai|Do dong' |
  Select-Object -Last 15 | Out-Host
```

Ghi số **thật** vào `docs/BACKLOG.md` B-15. Nếu hai dòng đó chỉ vài chục mili giây thì nói thẳng là
mức cắt không đáng kể: phần còn lại của 0,77 giây là MT5 dựng hộp thoại (~0,3 giây), và chỗ đó chỉ
cắt được bằng cách không mở hộp thoại nào — đường menu chuột phải, **chưa ai đo**.

## 6. TEST-31 — hàng đợi mở qua giao diện (D-31)

Chính sự cố đã báo: nhấn **10** lệnh `0.01` liên tiếp trên Master, nhanh hết mức tay làm được.

```powershell
@'
import sqlite3
c = sqlite3.connect("file:data/bridge.db?mode=ro", uri=True)
print("cap:", [r[0] for r in c.execute(
    "SELECT master_position_id FROM pair WHERE created_at >= date('now') ORDER BY pair_id")])
print("con cho:", c.execute("SELECT COUNT(*) FROM ui_open_queue").fetchone()[0])
for r in c.execute("SELECT level, code, COUNT(*) FROM alert WHERE created_at >= date('now') "
                   "AND code LIKE 'UI_OPEN_QUEUE%' GROUP BY 1, 2"):
    print(r)
'@ | .\.venv\Scripts\python.exe -
```

**Đạt khi:** đủ **10** cặp, đúng thứ tự Master vào lệnh, `ui_open_queue` rỗng, không có
`UI_OPEN_QUEUE_EXPIRED`.

Rồi đo thông lượng thật — đây mới là số quyết định trần 15 giây có đủ không:

```powershell
Select-String -Path logs\clicker.log -Pattern 'Do dong|OPEN_UI' | Select-Object -Last 20 | Out-Host
```

Nếu có dòng `UI_OPEN_QUEUE_EXPIRED`, đó là **số đo thật**, không phải lỗi phần mềm — ghi vào
`docs/BACKLOG.md` B-15 và bàn tiếp. **Đừng nới 15 giây cho khỏi thấy.**

## 7. Lũ alert `COMMAND_TIMEOUT` của `REQUEST_SNAPSHOT` — LÀM TRƯỚC mọi test khác

*(Mục "tìm vị thế không dò từ dòng 0" đã ĐẠT 2026-09-15: `2 lan mo / 11 dong`, `1 lan mo / 10 dong`
— xem B-15.)*

`tinh-hinh` 2026-09-15 báo **388.059** ERROR/CRITICAL chưa xem, toàn `COMMAND_TIMEOUT … REQUEST_SNAPSHOT`
(~1,2 alert/giây). Code không có đường nào sinh ngần ấy khi kết nối ổn định; nghi hai EA dùng chung một
token (EA gắn trên hai chart, hoặc terminal thừa) đá nhau ra liên tục. Thu bằng chứng, **chỉ đọc**:

```powershell
cd C:\CopyBridge
@'
import sqlite3
c = sqlite3.connect("file:data/bridge.db?mode=ro", uri=True)
print("== COMMAND_TIMEOUT theo gio (6 gio gan nhat) ==")
for r in c.execute("SELECT substr(created_at,1,13) h, COUNT(*) FROM alert WHERE code='COMMAND_TIMEOUT' "
                   "GROUP BY h ORDER BY h DESC LIMIT 6"): print(r)
print("== REQUEST_SNAPSHOT 10 phut gan nhat, theo agent va trang thai ==")
for r in c.execute("SELECT target_agent_id, status, COUNT(*) FROM command WHERE type='REQUEST_SNAPSHOT' "
                   "AND created_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now','-10 minutes') "
                   "GROUP BY 1,2 ORDER BY 1,2"): print(r)
print("== alert khac COMMAND_TIMEOUT dang mo ==")
for r in c.execute("SELECT code, COUNT(*) FROM alert WHERE acknowledged_at IS NULL "
                   "AND code <> 'COMMAND_TIMEOUT' GROUP BY code ORDER BY 2 DESC"): print(r)
print("== sai lech dang cho theo loai ==")
for r in c.execute("SELECT kind, severity, COUNT(*) FROM reconcile_finding WHERE resolution='PENDING' "
                   "GROUP BY 1,2 ORDER BY 3 DESC"): print(r)
'@ | .\.venv\Scripts\python.exe - | Tee-Object logs\lu-alert.txt

Select-String -Path logs\bridge.log -Pattern 'da ket noi|dong ket noi|thay the|qua dai' |
  Select-Object -Last 40 | Out-File logs\ket-noi.txt
Get-NetTCPConnection -LocalPort 8787 -State Established |
  Select-Object RemoteAddress, RemotePort, OwningProcess | Out-File logs\tcp-8787.txt
```

Nhìn tay trên **từng** terminal: EA `CopyBridge` gắn trên **mấy chart**? Có terminal MT5 nào khác chạy?

**Kết quả thu 2026-09-15 ~14:10 (giờ VN):** mỗi terminal **1** EA, không terminal thừa ⇒ giả thuyết "hai
EA cùng token" **bị bác**. Nhưng lũ đang chạy: 10 phút gần nhất 430 `TIMEOUT` + 605 `ACK_OK`; **cả
AG-CLIENT lẫn AG-MASTER nối lại mỗi 1,2–1,4 giây** (`mo ket noi moi … dong ket noi cu`); cổng 8787 có 6
kết nối. Đã có từ 02:00 UTC — trước bản `0b2cec3`.

Code loại trừ: bắt tay không chậm (SHA-256), Bridge không tự đá (chỉ đóng kết nối cũ khi có hello mới),
payload heartbeat/snapshot của EA khớp schema. EA chỉ tự ngắt ở **bốn** chỗ và **chỗ nào cũng ghi log EA**:
`Gui khong tron goi`, `Bridge gui dong qua dai`, `Bridge tu choi: <code> - <message>`, `Bat tay khong
xong`. Backoff 1 giây + `hello_ack` đặt lại backoff ⇒ đúng nhịp 1,3 giây. Bước tiếp — lấy lý do:

```powershell
Get-Content logs\bridge.log -Tail 400 | Out-File logs\bridge-tail.txt -Encoding utf8
Select-String -Path logs\bridge.log -Pattern 'sai schema|giai ma|qua dai|Tu choi|WARNING|ERROR' |
  Select-Object -Last 40 | Out-File logs\bridge-loi.txt -Encoding utf8
```

Và log EA hôm nay của **cả hai** terminal (Toolbox → Experts → chuột phải → Open): ~30 dòng gần nhất có
`Bridge tu choi`, `Gui khong tron goi`, `qua dai`, `Bat tay`, `Da ket noi toi Bridge`.

**Kết quả `bridge.log` 2026-09-15 ~14:21:** **không** có dòng `sai schema` / `giai ma` / `qua dai` /
`Tu choi` / WARNING nào ⇒ Bridge **không** gửi lỗi, nhánh `error` bị loại. `dong ket noi` là EOF từ phía
EA ⇒ **EA tự đóng socket** ~1,2 giây sau mỗi lần nối, có lúc chưa trả lời snapshot. Mỗi lần nối Bridge
gửi **hai** `REQUEST_SNAPSHOT` (`on_agent_online` + đối chiếu `AGENT_ONLINE`). Còn ba đường: `Gui khong tron
goi`, `Bridge gui dong qua dai`, hoặc EA bị gỡ/khởi động lại (`… dung, ly do N`). Bước tiếp — **log EA
không lọc**, ~60 dòng cuối file `MQL5\Logs\YYYYMMDD.log` hôm nay của **cả hai** terminal, kèm cỡ file:

```powershell
Get-ChildItem -Path "$env:APPDATA\MetaQuotes\Terminal" -Recurse -Filter commands.ndjson -ErrorAction SilentlyContinue |
  Select-Object FullName, Length, LastWriteTime | Format-List | Out-File C:\CopyBridge\logs\ea-commands.txt -Encoding utf8
```

**Không** gỡ EA ra gắn lại trước khi có log — làm vậy có thể dừng lũ tạm thời và xoá dấu vết.

**Đạt khi** (sau khi đã gỡ nguyên nhân): 10 phút gần nhất `REQUEST_SNAPSHOT` chỉ vài dòng và `ACK_OK`;
`tcp-8787.txt` đúng 3 kết nối (EA Master, EA Client, clicker). **Chỉ khi đó** mới dọn:
`bridge.admin xac-nhan-alert --code COMMAND_TIMEOUT --truoc <moc-lu-da-dung> [--that]`. 125 sai lệch
đang chờ **không** dọn hàng loạt — có thể là hệ quả của đối chiếu không lấy được snapshot.

## 8. Chẩn đoán "chốt sai" — chạy TRƯỚC khi cập nhật (D-30, bổ sung 2026-09-15)

Người dùng nghi có lần bên kia chốt sai khi đang có ~10 vị thế. Code đã được rà, nhưng **chưa có
bằng chứng từ VPS** cơ chế nào đã xảy ra. Lệnh `kiem-dong-sai` có trong bản mới, nên thứ tự là:
cập nhật code (mục 1) **nhưng chưa làm gì khác**, rồi chạy cho **ngày xảy ra sự cố** (ngày UTC):

```powershell
.\.venv\Scripts\python.exe -m bridge.admin kiem-dong-sai --ngay 2026-09-15
Select-String -Path logs\clicker.log -Pattern 'Do dong|Tim vi the|gui=False|lan 2' |
  Select-Object -Last 60 | Out-Host
```

Gửi nguyên văn cả hai phần. `[C]` khác 0 là cặp gắn nhầm lúc mở; `[A]` khác 0 thì đọc log quanh mốc
đó; `[B]` khác 0 thì **mở terminal kiểm vị thế đó còn không** — sổ nói đã đóng.

Sau đó tái hiện: mở 10 lệnh `0.01`, đóng nhanh liên tiếp 5 lệnh ở Master rồi 5 lệnh ở Client.

**Đạt khi:** `kiem-dong-sai` cho ngày hôm đó không đánh dấu dòng nào; `kiem-reason` ĐẠT; mỗi dòng
`Bam Close ticket T` trong log khớp đúng ticket của deal đóng. Có dòng `rejected … khong sach` thì ghi
số lần vào B-15 — đó là số đo thật của việc MT5 treo khi dò.

## 9. Qua một đêm

Sáng hôm sau kiểm **cả ba** file log đều có bản đã xoay kèm ngày. Đây là bằng chứng duy nhất cho
việc mỗi tiến trình một file log là đủ (bài học 2026-09-11: `bridge.log` đứng im 63 giờ).

---

## Còn nợ dài hạn, chưa xếp lịch

- **B-08 — phiên RDP đã ngắt.** Chưa ai chứng minh hệ thống còn copy được sau khi đóng cửa sổ RDP.
  Đây là rủi ro **mất tiền**, nặng hơn mọi mục ở trên. Xem `docs/KE-HOACH-CHAY-THAT.md` mục 2.1.
- **TEST-19 — mất điện đột ngột** (B-02) và **B-03 — chạy 24 giờ liên tục**.
- Hiển thị `master_close_route` trên dashboard (không cần VPS, chưa làm).
