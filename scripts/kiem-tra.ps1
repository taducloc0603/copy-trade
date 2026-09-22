<#
.SYNOPSIS
    Kiem tra suc khoe he thong. Chay lenh nay MOI LAN dang nhap vao may.

.DESCRIPTION
    Kenh canh bao ngoai dang tat co chu dich, nen khong co gi tu bao cho ban biet chuyen da xay
    ra. Day la thay the: mot lenh, muoi muc kiem, ma thoat bang so muc hong.

    Muc quan trong nhat la muc cuoi -- `bridge.admin tinh-hinh`. Tam muc trong deu xanh ma he
    thong van ngung copy la chuyen binh thuong: xem lai khoi canh bao in ra o cuoi.

.EXAMPLE
    .\kiem-tra.ps1

.EXAMPLE
    .\kiem-tra.ps1 -ChiTinhHinh
    Chi chay `tinh-hinh`. Dung cho Scheduled Task '\CopyBridge\TinhHinh'.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string] $ThuMuc = "C:\CopyBridge",
    [string] $TenDichVu = "CopyBridge",
    [switch] $ChiTinhHinh,
    [switch] $KhongInCanhBao
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }
$env:PYTHONUTF8 = "1"

$script:SoHong = 0
$script:MaTinhHinh = 0

function xanh([string] $tin)  { Write-Host "[  OK  ] $tin" -ForegroundColor Green }
function vang([string] $tin)  { Write-Host "[CANHBAO] $tin" -ForegroundColor Yellow }
function do_([string] $tin)   { $script:SoHong++; Write-Host "[ LOI  ] $tin" -ForegroundColor Red }

$py = Join-Path $ThuMuc ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "[ LOI  ] Khong thay $py. Chay scripts\cai-dat.ps1 truoc." -ForegroundColor Red
    exit 1
}
Set-Location $ThuMuc

# ---------------------------------------------------------------------------------------------
# Khong tu parse TOML trong PowerShell -- hoi chinh Bridge, no la nguon su that duy nhat.
# ---------------------------------------------------------------------------------------------
function doc_cau_hinh() {
    $ra = & $py -c "from bridge.config import load_config; c=load_config(); print(c.bridge.host, c.bridge.port, c.bridge.web_port)" 2>&1
    if ($LASTEXITCODE -ne 0) { return $null }
    $phan = ("$ra".Trim() -split '\s+')
    if ($phan.Count -lt 3) { return $null }
    return @{ host = $phan[0]; port = [int] $phan[1]; web_port = [int] $phan[2] }
}

function muc_tinh_hinh() {
    Write-Host ""
    Write-Host "--- bridge.admin tinh-hinh ---" -ForegroundColor Cyan
    # `| Out-Host` la bat buoc, khong phai trang tri: trong mot ham PowerShell, stdout cua lenh
    # native roi vao luong tra ve cua ham chu khong ra man hinh. Thieu no thi muc kiem quan
    # trong nhat cua ca script in ra rong.
    & $py -m bridge.admin tinh-hinh | Out-Host
    $script:MaTinhHinh = $LASTEXITCODE
    Write-Host "------------------------------" -ForegroundColor Cyan
    if ($script:MaTinhHinh -eq 0) { xanh "tinh-hinh: khong co gi can lam" }
    else { do_ "tinh-hinh: CO MUC CAN XU LY (ma thoat $script:MaTinhHinh). Doc phan tren." }
}

if ($ChiTinhHinh) {
    muc_tinh_hinh
    exit $script:MaTinhHinh
}

Write-Host ""
Write-Host " Kiem tra MT5 Copy Bridge -- $ThuMuc" -ForegroundColor Cyan
Write-Host ""

# Doc cong TRUOC muc 1: muc 1 can biet cong de phat hien trang thai "dich vu da dung ma
# cong van bi giu" -- thu lam Start-Service that bai ma Windows khong noi mot chu nao.
$cfg = doc_cau_hinh

# 1. Dich vu
$dv = Get-Service $TenDichVu -ErrorAction SilentlyContinue
if ($null -eq $dv) {
    do_ "chua dang ky dich vu $TenDichVu (chay scripts\tao-dich-vu.ps1)"
} elseif ($dv.Status -ne 'Running') {
    do_ "dich vu $TenDichVu dang o trang thai $($dv.Status)"
    # Dich vu da dung MA CONG VAN BI GIU la trang thai lam `Start-Service` that bai, va thong bao
    # cua Windows khong he nhac toi cong -- no chi noi "Failed to start service". Da mat muoi phut
    # vi dung cai nay tren VPS 2026-09-22, sau dung mot lenh Restart-Service.
    $dsCong = if ($null -eq $cfg) { @(8787, 8080) } else { @($cfg.port, $cfg.web_port) }
    $giuCong = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
                 Where-Object { $_.LocalPort -in $dsCong } |
                 ForEach-Object { [int] $_.OwningProcess } | Sort-Object -Unique)
    if ($giuCong.Count -gt 0) {
        do_ ("dich vu da dung nhung cong " + ($dsCong -join '/') + " VAN bi giu boi PID " +
             ($giuCong -join ', ') + " -- day la mot tien trinh mo coi, va no lam dich vu khong " +
             "bat len duoc. Chay: scripts\khoi-dong-lai.ps1")
    }
} elseif ($dv.StartType -ne 'Automatic') {
    vang "dich vu dang chay nhung StartType = $($dv.StartType), se khong tu bat sau reboot"
} else {
    xanh "dich vu ${TenDichVu}: Running / Automatic"
}

# 2 + 3. Cong nghe va dashboard
if ($null -eq $cfg) {
    do_ "khong doc duoc config.toml"
} else {
    foreach ($c in @($cfg.port, $cfg.web_port)) {
        $nghe = Get-NetTCPConnection -State Listen -LocalPort $c -ErrorAction SilentlyContinue
        if ($nghe) { xanh "cong $c dang nghe" } else { do_ "cong $c KHONG nghe" }
    }
    try {
        $tl = Invoke-WebRequest "http://127.0.0.1:$($cfg.web_port)/" -UseBasicParsing -TimeoutSec 5
        xanh "dashboard tra loi $($tl.StatusCode)"
    } catch {
        $ma = $null
        if ($_.Exception.Response) { $ma = [int] $_.Exception.Response.StatusCode }
        # 302 (chuyen toi /login) va 401 deu la dashboard con song, chi la chua dang nhap.
        if ($ma -eq 302 -or $ma -eq 401) { xanh "dashboard tra loi $ma (chua dang nhap)" }
        else { do_ "dashboard khong tra loi: $($_.Exception.Message)" }
    }
}

# 4. clicker
# CHI IN PID. Tuyet doi khong in CommandLine: neu ai do van chay clicker kieu cu thi token dang
# nam trong do, va muc dich cua ca bo script nay la token khong bao gio ra man hinh.
$tienTrinh = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
               Where-Object { $_.CommandLine -like '*-m clicker*' })
if ($tienTrinh.Count -eq 0) {
    do_ "clicker KHONG chay (Bridge se co y khong copy lenh nao -- D-25)"
    # Noi VI SAO, khong chi noi la khong chay. Hai nguyen nhan, va chung can hai cach xu ly khac
    # han nhau -- nen phai phan biet duoc ngay o day thay vi de nguoi dung doan.
    $tvClicker = @(Get-ScheduledTask -TaskPath '\CopyBridge\' -ErrorAction SilentlyContinue |
                   Where-Object { $_.TaskName -like 'Clicker*' })
    $chuaChay = @($tvClicker | Where-Object { $_.State -ne 'Running' })
    if ($tvClicker.Count -eq 0) {
        vang "chua dang ky tac vu clicker nao. Chay: scripts\tao-dich-vu.ps1"
    } elseif ($chuaChay.Count -gt 0) {
        # Trigger la "khi dang nhap", ma viec cai dat luon dien ra trong mot phien da dang nhap tu
        # truoc -- nen tac vu vua dang ky se nam im o trang thai Ready cho toi lan dang nhap ke
        # tiep. Dung loi da gap o lan cai that thu hai (2026-09-22).
        vang ("tac vu " + (($chuaChay | ForEach-Object { $_.TaskName }) -join ', ') +
              " da dang ky nhung KHONG chay (trigger 'khi dang nhap' da troi qua). Bat ngay: " +
              "Get-ScheduledTask -TaskPath '\CopyBridge\' | Where-Object TaskName -like " +
              "'Clicker*' | Start-ScheduledTask")
    } else {
        vang ("Nguyen nhan hay gap nhat: chua khai so tai khoan + tieu de cua so cho clicker tren " +
              "dashboard (tab Cau hinh > Agent). Doc logs\clicker-wrapper.log: 'thoat 4' la dau hieu.")
    }
} else {
    xanh ("clicker dang chay, PID " + (($tienTrinh | ForEach-Object { $_.ProcessId }) -join ', '))
}

# 4b. Code dang chay co cu hon code tren dia khong
# Dang "trong van khoe" nguy hiem nhat: dich vu Running, clicker song, moi muc tren deu xanh, nhung
# ca hai van la code TRUOC lan git pull gan nhat. Da xay ra that tren VPS 2026-09-11 sau mot lan
# chay cai-dat.ps1 thieu -CapNhat. Moc so sanh la lan HEAD doi gan nhat (reflog), khong phai ngay
# commit: commit cu co the duoc pull ve rat lau sau khi tien trinh da chay.
$reflog = Join-Path $ThuMuc ".git\logs\HEAD"
if (Test-Path $reflog) {
    $doiCode = (Get-Item $reflog).LastWriteTime
    $cu = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match '-m (bridge|clicker)(\s|$)' -and
                           $_.CreationDate -lt $doiCode })
    if ($cu.Count -gt 0) {
        vang ("co $($cu.Count) tien trinh Bridge/clicker chay tu truoc lan cap nhat code luc " +
              "$doiCode -- dang chay CODE CU. Chay scripts\cai-dat.ps1 -CapNhat")
    } else {
        xanh "Bridge va clicker deu chay code hien tai tren dia"
    }
}

# 4c. git co goi duoc khong
# Moi lan cap nhat deu bat dau bang `git pull`, va tai lieu bao go dung cau do. Nhung winget cai
# git xong chi cap nhat PATH trong registry: mot cua so PowerShell mo tu TRUOC luc cai van mang
# PATH cu va bao "git: The term 'git' is not recognized" -- mot thong bao khong he nhac toi PATH,
# nen khong ai noi duoc no ve nguyen nhan. Da chan that mot lan cap nhat 2026-09-22.
if (Get-Command git -ErrorAction SilentlyContinue) {
    xanh ("git goi duoc: " + ((git --version) -join ''))
} else {
    do_ ("khong goi duoc git trong cua so nay, nen `git pull` se bao 'not recognized'. PATH cua " +
         "cua so nay cu hon lan cai git. Mo cua so PowerShell MOI, hoac nap lai PATH: " +
         "`$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + " +
         "[Environment]::GetEnvironmentVariable('Path','User')")
}

# 5. Hai terminal MT5
$term = @(Get-Process terminal64 -ErrorAction SilentlyContinue)
if ($term.Count -eq 2) { xanh "co 2 terminal MT5" }
elseif ($term.Count -eq 0) { do_ "khong co terminal MT5 nao dang chay" }
else { vang "co $($term.Count) terminal MT5, mong doi 2" }

# 6. Scheduled Task
$tacVu = @(Get-ScheduledTask -TaskPath "\CopyBridge\" -ErrorAction SilentlyContinue)
if ($tacVu.Count -eq 0) {
    vang "chua dang ky Scheduled Task nao trong \CopyBridge\"
} else {
    foreach ($t in $tacVu) {
        $tt = $t | Get-ScheduledTaskInfo
        # 267009 = tac vu dang chay, khong phai loi.
        if ($tt.LastTaskResult -eq 0 -or $tt.LastTaskResult -eq 267009) {
            xanh "tac vu $($t.TaskName): ket qua $($tt.LastTaskResult), chay luc $($tt.LastRunTime)"
        } else {
            vang "tac vu $($t.TaskName): ket qua $($tt.LastTaskResult), chay luc $($tt.LastRunTime)"
        }
    }
}

# 7. Log con tuoi
$log = Join-Path $ThuMuc "logs\bridge.log"
if (-not (Test-Path $log)) {
    do_ "khong thay logs\bridge.log"
} else {
    $tuoi = (Get-Date) - (Get-Item $log).LastWriteTime
    if ($tuoi.TotalMinutes -gt 15) {
        vang ("logs\bridge.log khong doi trong {0:N0} phut" -f $tuoi.TotalMinutes)
    } else {
        xanh "logs\bridge.log con tuoi"
    }
}

# 8. Dia trong
$o = (Get-Item $ThuMuc).PSDrive
if ($null -ne $o -and $null -ne $o.Free) {
    $gb = [math]::Round($o.Free / 1GB, 1)
    if ($gb -lt 2) { vang "o $($o.Name): con $gb GB (14 ban sao luu + log 30 ngay can cho)" }
    else { xanh "o $($o.Name): con $gb GB" }
}

# 9. tinh-hinh
muc_tinh_hinh

Write-Host ""
if ($script:SoHong -eq 0) { Write-Host " Khong co muc nao hong." -ForegroundColor Green }
else { Write-Host " CO $($script:SoHong) MUC HONG." -ForegroundColor Red }

if (-not $KhongInCanhBao) {
    Write-Host ""
    Get-Content (Join-Path $PSScriptRoot "canh-bao.txt") | ForEach-Object {
        Write-Host $_ -ForegroundColor Yellow
    }
}

exit $script:SoHong
