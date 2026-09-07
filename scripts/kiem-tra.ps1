<#
.SYNOPSIS
    Kiem tra suc khoe he thong. Chay lenh nay MOI LAN dang nhap vao may.

.DESCRIPTION
    Kenh canh bao ngoai dang tat co chu dich, nen khong co gi tu bao cho ban biet chuyen da xay
    ra. Day la thay the: mot lenh, chin muc kiem, ma thoat bang so muc hong.

    Muc quan trong nhat la muc cuoi -- `bridge.admin tinh-hinh`. Tam muc trong deu xanh ma he
    thong van ngung copy la chuyen binh thuong: xem lai khoi canh bao in ra o cuoi.

.EXAMPLE
    .\kiem-tra.ps1

.EXAMPLE
    .\kiem-tra.ps1 -ChiTinhHinh
    Chi chay `tinh-hinh`. Dung cho Scheduled Task '\CopyBridge\TinhHinh'.
#>
[CmdletBinding()]
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

# 1. Dich vu
$dv = Get-Service $TenDichVu -ErrorAction SilentlyContinue
if ($null -eq $dv) {
    do_ "chua dang ky dich vu $TenDichVu (chay scripts\tao-dich-vu.ps1)"
} elseif ($dv.Status -ne 'Running') {
    do_ "dich vu $TenDichVu dang o trang thai $($dv.Status)"
} elseif ($dv.StartType -ne 'Automatic') {
    vang "dich vu dang chay nhung StartType = $($dv.StartType), se khong tu bat sau reboot"
} else {
    xanh "dich vu ${TenDichVu}: Running / Automatic"
}

# 2 + 3. Cong nghe va dashboard
$cfg = doc_cau_hinh
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
} else {
    xanh ("clicker dang chay, PID " + (($tienTrinh | ForEach-Object { $_.ProcessId }) -join ', '))
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
