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
    # CHI de tuong thich ban cai cu. Truyen vao day la GHI DE gia tri khai tren dashboard, va
    # tu do sua tren dashboard se khong con tac dung (thu tu: dong lenh > config.toml > Bridge).
    [int]    $AccountLogin = 0,
    [string] $TerminalTitle = "",
    # Muc cau hinh trong config.toml, MOT muc cho moi clicker: `clicker` lai terminal Client
    # dau tien, `clicker_master` lai terminal Master, `clicker_cl02` lai terminal cua Client thu
    # hai. Moi muc mot token va mot nhat ky rieng; so tai khoan va tieu de cua so lay tu Bridge.
    #
    # Mau chu khong phai danh sach co san: so Client la thu doi theo cau hinh, nen mot danh sach
    # cung se lai chan Client thu ba y nhu truoc (B-19). Mau nay trung voi RE_MUC_CLICKER trong
    # bridge/config.py.
    [ValidatePattern('^clicker(_[a-z0-9_]+)?$')]
    [string] $Muc = "clicker",
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

$doiSo = @("-m", "clicker", "--muc", $Muc)
if ($AccountLogin -gt 0) { $doiSo += @("--account-login", "$AccountLogin") }
if ($TerminalTitle)      { $doiSo += @("--terminal-title", $TerminalTitle) }

ghi "wrapper khoi dong, thu muc $ThuMuc, muc $Muc"

while ($true) {
    & $py @doiSo
    $ma = $LASTEXITCODE

    # 3 = SingleInstance: da co mot clicker khac dang lai terminal nay. Thu lai chi lam cai chet
    # cham hon chu khong an toan hon -- dung han, dung dung y clicker/__main__.py.
    if ($ma -eq 3) { ghi "thoat 3 (da co clicker khac lai terminal nay). Dung han."; break }

    # 2 = thieu token. Chay lai cung the, chi rac log.
    if ($ma -eq 2) { ghi "thoat 2 (thieu token). Sua config.toml roi chay lai tac vu."; break }

    # 4 = chua ai khai tieu de cua so terminal cho agent nay. KHAC ma 2: viec nay sua tren
    # dashboard (tab Cau hinh > Agent) chu khong phai tren VPS, nen thu lai la dung -- khai xong
    # la lan bat ke tiep clicker len, khong phai dang nhap VPS chay lai tac vu. Cho lau hon de
    # khong rac log trong luc cho nguoi ta khai.
    if ($ma -eq 4) {
        ghi "thoat 4 (chua khai terminal tren dashboard). Thu lai sau 60 giay."
        Start-Sleep -Seconds 60
        continue
    }

    ghi "clicker thoat ma $ma, bat lai sau $ChoGiuaHaiLan giay"
    Start-Sleep -Seconds $ChoGiuaHaiLan
}

exit $LASTEXITCODE
