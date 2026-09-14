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

## 6. Qua một đêm

Sáng hôm sau kiểm **cả ba** file log đều có bản đã xoay kèm ngày. Đây là bằng chứng duy nhất cho
việc mỗi tiến trình một file log là đủ (bài học 2026-09-11: `bridge.log` đứng im 63 giờ).

---

## Còn nợ dài hạn, chưa xếp lịch

- **B-08 — phiên RDP đã ngắt.** Chưa ai chứng minh hệ thống còn copy được sau khi đóng cửa sổ RDP.
  Đây là rủi ro **mất tiền**, nặng hơn mọi mục ở trên. Xem `docs/KE-HOACH-CHAY-THAT.md` mục 2.1.
- **TEST-19 — mất điện đột ngột** (B-02) và **B-03 — chạy 24 giờ liên tục**.
- Hiển thị `master_close_route` trên dashboard (không cần VPS, chưa làm).
