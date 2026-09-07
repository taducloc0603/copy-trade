<#
.SYNOPSIS
    Dang ky Bridge lam Windows Service, va clicker + bao tri lam Scheduled Task.

.DESCRIPTION
    Bridge chay bang NSSM chu khong phai sc.exe hay Scheduled Task. Ly do ky thuat, khong phai
    so thich: tren Windows, `loop.add_signal_handler` luon nem NotImplementedError nen
    bridge/__main__.py KHONG dang ky duoc handler SIGTERM nao. Duong dung sach duy nhat con lai
    la mot su kien Ctrl+C tren console, nho do khoi `finally` moi chay (danh agent ve OFFLINE,
    checkpoint WAL, tat uvicorn). NSSM co AppStopMethodConsole -- no gui dung su kien do.
    TerminateProcess thang thi mat toan bo khoi `finally`.

    clicker thi nguoc lai: KHONG lam service duoc. Service nam o session 0 va khong thay cua so
    cua phien nguoi dung, ma toan bo duong mo lenh la PostMessage vao hop thoai New Order.

.EXAMPLE
    .\tao-dich-vu.ps1 -ThuMuc C:\CopyBridge -AccountLogin 538217 -TerminalTitle "538217"

.EXAMPLE
    .\tao-dich-vu.ps1 -GoBo
#>
[CmdletBinding()]
param(
    [string] $ThuMuc = "C:\CopyBridge",
    [string] $TenDichVu = "CopyBridge",
    [string] $NguoiDung = "$env:USERDOMAIN\$env:USERNAME",
    [int]    $AccountLogin = 0,
    [string] $TerminalTitle = "",
    [string] $GioBaoTri = "03:00",
    [switch] $BoQuaTacVu,
    [switch] $GoBo
)

Set-StrictMode -Version Latest
# PowerShell 5.1: voi 'Stop', MOT DONG stderr bat ky tu mot exe -- pip in "notice: A new release
# of pip", git in tien do fetch -- bi boc thanh NativeCommandError va nem ra NGAY, truoc khi
# script kip doc $LASTEXITCODE. Nghia la thong bao loi tu te ben duoi khong bao gio hien ra, con
# nguoi cai thi nhan mot traceback khong lien quan. Moi lenh native trong file nay deu duoc kiem
# bang $LASTEXITCODE tuong minh, con cmdlet nao that bai la hong that thi ghi -ErrorAction Stop
# tai cho.
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }

$DuongDanTacVu = "\CopyBridge\"

function ok([string] $tin)   { Write-Host "  OK: $tin" -ForegroundColor Green }
function canh([string] $tin) { Write-Host "  CANH BAO: $tin" -ForegroundColor Yellow }
function tieu_de([string] $t) {
    Write-Host ""
    Write-Host "== $t" -ForegroundColor Cyan
}

function la_admin() {
    $than = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($than)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ---------------------------------------------------------------------------------------------
# NSSM
# ---------------------------------------------------------------------------------------------
function tim_nssm() {
    $sanCo = Get-Command nssm -ErrorAction SilentlyContinue
    if ($sanCo) { return $sanCo.Source }

    $cucBo = Join-Path $ThuMuc "tools\nssm\nssm.exe"
    if (Test-Path $cucBo) { return $cucBo }

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "  Dang cai NSSM bang winget..." -ForegroundColor DarkGray
        winget install --id NSSM.NSSM -e --silent --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                    [Environment]::GetEnvironmentVariable('Path', 'User')
        $sanCo = Get-Command nssm -ErrorAction SilentlyContinue
        if ($sanCo) { return $sanCo.Source }
    }

    Write-Host "  Dang tai NSSM tu nssm.cc..." -ForegroundColor DarkGray
    $tam = Join-Path $env:TEMP "nssm-2.24.zip"
    $dich = Join-Path $ThuMuc "tools\nssm"
    New-Item -ItemType Directory -Force -Path $dich | Out-Null
    # TLS 1.2 phai bat tuong minh: PowerShell 5.1 mac dinh dung SSL3/TLS1 va nssm.cc tu choi.
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest "https://nssm.cc/release/nssm-2.24.zip" -OutFile $tam -UseBasicParsing
    $giaiNen = Join-Path $env:TEMP "nssm-giai-nen"
    if (Test-Path $giaiNen) { Remove-Item -Recurse -Force $giaiNen }
    Expand-Archive $tam -DestinationPath $giaiNen
    $exe = Get-ChildItem $giaiNen -Recurse -Filter nssm.exe |
           Where-Object { $_.FullName -like "*win64*" } | Select-Object -First 1
    if ($null -eq $exe) { throw "Khong tim thay nssm.exe trong ban tai ve." }
    Copy-Item $exe.FullName $dich -Force
    return (Join-Path $dich "nssm.exe")
}

function dang_ky_dich_vu([string] $nssm) {
    tieu_de "Dang ky Windows Service '$TenDichVu'"
    $py = Join-Path $ThuMuc ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { throw "Khong thay $py. Chay scripts\cai-dat.ps1 truoc." }

    $daCo = Get-Service $TenDichVu -ErrorAction SilentlyContinue
    if ($null -ne $daCo) {
        if ($daCo.Status -eq 'Running') { Stop-Service $TenDichVu }
        & $nssm remove $TenDichVu confirm | Out-Null
        canh "da go dich vu cu de dang ky lai"
        Start-Sleep -Seconds 2
    }

    & $nssm install $TenDichVu $py | Out-Null
    & $nssm set $TenDichVu AppParameters "-m bridge" | Out-Null
    # BAT BUOC. bridge/logging_setup.py dung duong dan tuong doi Path("logs"), nen chay sai thu
    # muc lam viec se ghi log ra C:\Windows\System32 trong khi database van dung cho -- mot he
    # thong "chay binh thuong" ma khong ai tim thay log.
    & $nssm set $TenDichVu AppDirectory $ThuMuc | Out-Null
    & $nssm set $TenDichVu DisplayName "MT5 Copy Bridge" | Out-Null
    & $nssm set $TenDichVu Description "Bridge dong bo lenh MT5 (TCP 8787 + dashboard 8080)" | Out-Null
    & $nssm set $TenDichVu Start SERVICE_AUTO_START | Out-Null

    & $nssm set $TenDichVu AppStdout (Join-Path $ThuMuc "logs\service-out.log") | Out-Null
    & $nssm set $TenDichVu AppStderr (Join-Path $ThuMuc "logs\service-err.log") | Out-Null
    & $nssm set $TenDichVu AppStdoutCreationDisposition 4 | Out-Null
    & $nssm set $TenDichVu AppStderrCreationDisposition 4 | Out-Null
    & $nssm set $TenDichVu AppRotateFiles 1 | Out-Null
    & $nssm set $TenDichVu AppRotateOnline 1 | Out-Null
    & $nssm set $TenDichVu AppRotateBytes 10485760 | Out-Null

    # Dich vu chay duoi code page he thong (cp1252/cp437). File log da la utf-8 nen khong sao,
    # nhung handler console cua setup_logging ghi ra stderr se nem UnicodeEncodeError o dong log
    # tieng Viet co dau dau tien -- khong giet tien trinh, nhung lam ban service-err.log va che
    # mat loi that.
    & $nssm set $TenDichVu AppEnvironmentExtra PYTHONUTF8=1 PYTHONIOENCODING=utf-8 | Out-Null

    & $nssm set $TenDichVu AppExit Default Restart | Out-Null
    & $nssm set $TenDichVu AppRestartDelay 5000 | Out-Null
    # Bridge chet ngay lap tuc (vi du config.toml sai) se bi NSSM dung vong lap restart thay vi
    # quay vo han.
    & $nssm set $TenDichVu AppThrottle 10000 | Out-Null

    # Ba dong nay la ly do chon NSSM: phai co console thi su kien Ctrl+C moi gui duoc, va chi
    # Ctrl+C moi lam khoi `finally` cua bridge/__main__.py chay.
    & $nssm set $TenDichVu AppNoConsole 0 | Out-Null
    & $nssm set $TenDichVu AppStopMethodSkip 0 | Out-Null
    & $nssm set $TenDichVu AppStopMethodConsole 15000 | Out-Null

    # Chay bang chinh tai khoan autologon. Tai khoan do du sao cung phai ton tai cho clicker, va
    # nhu vay dich vu, clicker, tac vu bao tri va lenh go tay deu cung mot danh tinh tren cung
    # mot file SQLite -- het chuyen ACL.
    Write-Host "  Nhap mat khau cua $NguoiDung (bo trong de dich vu chay bang LocalSystem):" -ForegroundColor Yellow
    $mk = Read-Host -AsSecureString
    $mkTho = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($mk))
    if ($mkTho) {
        & $nssm set $TenDichVu ObjectName $NguoiDung $mkTho | Out-Null
        ok "dich vu chay bang $NguoiDung"
    } else {
        icacls $ThuMuc /grant "$($env:USERNAME):(OI)(CI)M" /T /Q | Out-Null
        canh "dich vu chay bang LocalSystem; da cap quyen Modify cho $env:USERNAME tren $ThuMuc"
    }

    Start-Service $TenDichVu -ErrorAction Stop
    Start-Sleep -Seconds 3
    $dv = Get-Service $TenDichVu
    if ($dv.Status -ne 'Running') {
        throw "Dich vu khong len duoc. Xem logs\service-err.log."
    }
    ok "dich vu dang chay"
}

function kiem_tu_bat_lai([string] $nssm) {
    tieu_de "Kiem: giet tien trinh Bridge thi dich vu co tu bat lai khong"
    # Day la o checklist con bo trong o RUNBOOK muc 6. Kiem luon, ngay luc dang ky, chu khong
    # de lai thanh mot dong tai lieu chua ai chay.
    $tt = Get-CimInstance Win32_Service -Filter "Name='$TenDichVu'"
    if ($null -eq $tt -or -not $tt.ProcessId) { canh "khong lay duoc PID, bo qua bai kiem"; return }

    Stop-Process -Id $tt.ProcessId -Force
    Write-Host "  da giet PID $($tt.ProcessId), cho 20 giay..." -ForegroundColor DarkGray
    $den = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $den) {
        if ((Get-Service $TenDichVu).Status -eq 'Running') { break }
        Start-Sleep -Seconds 2
    }
    if ((Get-Service $TenDichVu).Status -eq 'Running') { ok "dich vu da tu bat lai" }
    else { canh "dich vu KHONG tu bat lai -- kiem lai AppExit/AppThrottle" }

    $py = Join-Path $ThuMuc ".venv\Scripts\python.exe"
    Push-Location $ThuMuc
    try {
        $che = (& $py -m bridge.admin run-mode) -join ' '
        if ($che -match 'PAUSED') { ok "khoi dong lai o PAUSED, dung D-15" }
        else { canh "run-mode sau khi bat lai: $che" }
    } finally { Pop-Location }
}

# ---------------------------------------------------------------------------------------------
# Scheduled Task
# ---------------------------------------------------------------------------------------------
function dang_ky_tac_vu_clicker() {
    tieu_de "Dang ky Scheduled Task '${DuongDanTacVu}Clicker'"
    $exe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
    $wrapper = Join-Path $ThuMuc "scripts\chay-clicker.ps1"
    if (-not (Test-Path $wrapper)) { throw "Khong thay $wrapper." }

    $doiSo = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$wrapper`" -ThuMuc `"$ThuMuc`""
    if ($AccountLogin -gt 0)  { $doiSo += " -AccountLogin $AccountLogin" }
    if ($TerminalTitle)       { $doiSo += " -TerminalTitle `"$TerminalTitle`"" }

    $hanhDong = New-ScheduledTaskAction -Execute $exe -Argument $doiSo -WorkingDirectory $ThuMuc
    $kichHoat = New-ScheduledTaskTrigger -AtLogOn -User $NguoiDung
    # Cho MT5 nap xong chart truoc khi clicker bat dau go cua so.
    $kichHoat.Delay = "PT90S"

    # Interactive, KHONG phai S4U hay Password: ca hai cai sau chay o phien khong tuong tac va
    # PostMessage se khong thay cua so MT5 nao. Day dung la cai bay khien clicker khong lam
    # service duoc, chi khac cai ten.
    $chuThe = New-ScheduledTaskPrincipal -UserId $NguoiDung -LogonType Interactive -RunLevel Limited

    $caiDat = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -StartWhenAvailable -MultipleInstances IgnoreNew
    # Mac dinh 3 ngay se giet clicker vao dung ngay thu ba.
    $caiDat.ExecutionTimeLimit = "PT0S"
    $caiDat.IdleSettings.StopOnIdleEnd = $false

    Register-ScheduledTask -TaskName "Clicker" -TaskPath $DuongDanTacVu -Action $hanhDong `
        -Trigger $kichHoat -Principal $chuThe -Settings $caiDat -Force | Out-Null
    ok "tac vu Clicker (chay khi dang nhap, tre 90 giay)"

    canh ("Muc toan ven cua clicker phai >= cua MT5. MT5 chay 'Run as administrator' ma clicker " +
          "chay thuong thi UIPI chan het window message: PostMessage tra ve thanh cong nhung " +
          "KHONG CO GI XAY RA.")
}

function dang_ky_tac_vu_bao_tri() {
    tieu_de "Dang ky Scheduled Task '${DuongDanTacVu}BaoTri' va 'TinhHinh'"
    $exe = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
    $wrapper = Join-Path $ThuMuc "scripts\chay-bao-tri.ps1"
    if (-not (Test-Path $wrapper)) { throw "Khong thay $wrapper." }

    $doiSo = "-NoProfile -ExecutionPolicy Bypass -File `"$wrapper`" -ThuMuc `"$ThuMuc`""
    $hanhDong = New-ScheduledTaskAction -Execute $exe -Argument $doiSo -WorkingDirectory $ThuMuc
    # S4U dung o day: bao tri khong dung toi cua so nao, va chay duoc ca khi chua dang nhap.
    $chuThe = New-ScheduledTaskPrincipal -UserId $NguoiDung -LogonType S4U -RunLevel Limited
    $caiDat = New-ScheduledTaskSettingsSet -StartWhenAvailable

    try {
        Register-ScheduledTask -TaskName "BaoTri" -TaskPath $DuongDanTacVu -Action $hanhDong `
            -Trigger (New-ScheduledTaskTrigger -Daily -At $GioBaoTri) `
            -Principal $chuThe -Settings $caiDat -Force | Out-Null
    } catch {
        canh "S4U that bai ($($_.Exception.Message)); lui ve Interactive"
        $chuThe = New-ScheduledTaskPrincipal -UserId $NguoiDung -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName "BaoTri" -TaskPath $DuongDanTacVu -Action $hanhDong `
            -Trigger (New-ScheduledTaskTrigger -Daily -At $GioBaoTri) `
            -Principal $chuThe -Settings $caiDat -Force | Out-Null
    }
    ok "tac vu BaoTri (hang ngay $GioBaoTri)"

    # `tinh-hinh` thoat khac 0 khi co muc can chu y, nen cot "Last Run Result" trong Task
    # Scheduler tro thanh mot den bao mien phi. Kenh canh bao ngoai dang tat co chu dich, nen
    # day la thu gan nhat voi mot he thong bao dong.
    $wrapperTh = Join-Path $ThuMuc "scripts\kiem-tra.ps1"
    $doiSoTh = "-NoProfile -ExecutionPolicy Bypass -File `"$wrapperTh`" -ThuMuc `"$ThuMuc`" -ChiTinhHinh"
    $hanhDongTh = New-ScheduledTaskAction -Execute $exe -Argument $doiSoTh -WorkingDirectory $ThuMuc
    $lapLai = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) `
                -RepetitionInterval (New-TimeSpan -Hours 1)
    Register-ScheduledTask -TaskName "TinhHinh" -TaskPath $DuongDanTacVu -Action $hanhDongTh `
        -Trigger $lapLai -Principal $chuThe -Settings $caiDat -Force | Out-Null
    ok "tac vu TinhHinh (moi gio; xem cot Last Run Result)"
}

function go_bo([string] $nssm) {
    tieu_de "Go bo"
    $dv = Get-Service $TenDichVu -ErrorAction SilentlyContinue
    if ($null -ne $dv) {
        if ($dv.Status -eq 'Running') { Stop-Service $TenDichVu }
        & $nssm remove $TenDichVu confirm | Out-Null
        ok "da go dich vu $TenDichVu"
    }
    foreach ($t in @("Clicker", "BaoTri", "TinhHinh")) {
        $tv = Get-ScheduledTask -TaskPath $DuongDanTacVu -TaskName $t -ErrorAction SilentlyContinue
        if ($null -ne $tv) {
            Unregister-ScheduledTask -TaskPath $DuongDanTacVu -TaskName $t -Confirm:$false
            ok "da go tac vu $t"
        }
    }
}

# ---------------------------------------------------------------------------------------------
try {
    if (-not (la_admin)) {
        throw "Can quyen Administrator. Mo lai PowerShell bang 'Run as administrator'."
    }
    $nssm = tim_nssm

    if ($GoBo) { go_bo $nssm; exit 0 }

    dang_ky_dich_vu $nssm
    kiem_tu_bat_lai $nssm
    if ($BoQuaTacVu) {
        canh "-BoQuaTacVu: khong dang ky Scheduled Task"
    } else {
        dang_ky_tac_vu_clicker
        dang_ky_tac_vu_bao_tri
    }

    Write-Host ""
    Write-Host " Lenh van hanh:" -ForegroundColor Cyan
    Write-Host "   Get-Service $TenDichVu | Format-List Name,Status,StartType"
    Write-Host "   Start-Service $TenDichVu   /   Stop-Service $TenDichVu"
    Write-Host "   Get-ScheduledTask -TaskPath '$DuongDanTacVu' | Get-ScheduledTaskInfo"
    Write-Host "   .\scripts\tao-dich-vu.ps1 -GoBo    # go het"
    Write-Host ""
    Get-Content (Join-Path $PSScriptRoot "canh-bao.txt") | ForEach-Object {
        Write-Host $_ -ForegroundColor Yellow
    }
    exit 0
} catch {
    Write-Host ""
    Write-Host " LOI: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
