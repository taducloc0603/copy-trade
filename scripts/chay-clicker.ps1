<#
.SYNOPSIS
    Chay clicker va giam sat no. Scheduled Task '\CopyBridge\Clicker' goi file nay.

.DESCRIPTION
    Vong lap giam sat o day la can thiet, khong phai thua: RestartCount cua Task Scheduler chi
    kich hoat khi TAC VU that bai, con clicker thoat 0 sau KeyboardInterrupt thi tac vu coi nhu
    xong binh thuong va khong bat lai. Ma clicker chet trong im lang nghia la Bridge co y KHONG
    copy lenh nao nua (D-25) -- dung thu khong duoc phep de tu chay im.

    Token KHONG di qua dong lenh: clicker doc no tu muc [clicker] trong config.toml. Dong lenh
    cua mot tien trinh la thu moi tai khoan tren cung may doc duoc bang Get-CimInstance
    Win32_Process, va clicker chay 24/7.
#>
[CmdletBinding()]
param(
    [string] $ThuMuc = "C:\CopyBridge",
    [int]    $AccountLogin = 0,
    [string] $TerminalTitle = "",
    [int]    $ChoGiuaHaiLan = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }
$env:PYTHONUTF8 = "1"

# BAT BUOC. Goi `clicker` khong nam trong packages cua pyproject.toml, no chay duoc nho sys.path[0]
# la thu muc lam viec; va DEFAULT_JOURNAL ("data/clicker_commands.ndjson") cung la duong dan
# tuong doi. Sai thu muc lam viec = khong import duoc, hoac nhat ky ghi ra C:\Windows\System32.
Set-Location $ThuMuc

$py = Join-Path $ThuMuc ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Khong thay $py. Chay scripts\cai-dat.ps1 truoc." }

$nhatKy = Join-Path $ThuMuc "logs\clicker-wrapper.log"

function ghi([string] $tin) {
    $dong = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $tin
    Write-Host $dong
    Add-Content -Path $nhatKy -Value $dong -Encoding utf8
}

$doiSo = @("-m", "clicker")
if ($AccountLogin -gt 0) { $doiSo += @("--account-login", "$AccountLogin") }
if ($TerminalTitle)      { $doiSo += @("--terminal-title", $TerminalTitle) }

ghi "wrapper khoi dong, thu muc $ThuMuc"

while ($true) {
    & $py @doiSo
    $ma = $LASTEXITCODE

    # 3 = SingleInstance: da co mot clicker khac dang lai terminal nay. Thu lai chi lam cai chet
    # cham hon chu khong an toan hon -- dung han, dung dung y clicker/__main__.py.
    if ($ma -eq 3) { ghi "thoat 3 (da co clicker khac lai terminal nay). Dung han."; break }

    # 2 = thieu tham so (token, so tai khoan, terminal-title). Chay lai cung the, chi rac log.
    if ($ma -eq 2) { ghi "thoat 2 (thieu tham so). Sua config.toml roi chay lai tac vu."; break }

    ghi "clicker thoat ma $ma, bat lai sau $ChoGiuaHaiLan giay"
    Start-Sleep -Seconds $ChoGiuaHaiLan
}

exit $LASTEXITCODE
