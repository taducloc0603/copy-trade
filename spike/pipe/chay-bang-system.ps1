<#
.SYNOPSIS
    Cau 3 cua Buoc 0: chay pipe_server.py bang LocalSystem -- dung tai khoan dich vu Bridge co the
    chay (scripts\tao-dich-vu.ps1) -- de xem EA trong MT5 (tai khoan thuong) co mo va GHI duoc pipe.

.DESCRIPTION
    Dang ky mot tac vu tam chay bang SYSTEM, khoi dong no, log ghi ra spike\pipe\system.log.
    Can PowerShell "Run as administrator".

    Hai lan thu:
      .\chay-bang-system.ps1                 # DACL cua ta -> EA phai DA NOI va co BAO CAO
      .\chay-bang-system.ps1 -DaclMacDinh    # DACL mac dinh -> du doan: EA KHONG mo duoc (err 5004)
      .\chay-bang-system.ps1 -Go             # dung va xoa tac vu tam

.EXAMPLE
    .\chay-bang-system.ps1
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [switch] $DaclMacDinh,
    [switch] $Go,
    [string] $Ten = "copybridge-spike"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$tacVu = "CopyBridgePipeSpike"

$laAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $laAdmin) {
    Write-Host "Can chay PowerShell bang 'Run as administrator'." -ForegroundColor Red
    exit 1
}

# Tac vu cu (neu co) phai dung truoc: hai server cung ten pipe thi EA noi vao ben nao cung duoc,
# va ket qua lan thu se khong noi len gi.
if (Get-ScheduledTask -TaskName $tacVu -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $tacVu -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $tacVu -Confirm:$false
    # Stop-ScheduledTask khong luon giet tien trinh con python.
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*pipe_server.py*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Write-Host "Da dung tac vu cu."
}
if ($Go) { exit 0 }

# SYSTEM khong co PATH cua nguoi dung: phai dua duong dan tuyet doi.
$py = (Get-Command python -ErrorAction Stop).Source
# Ban "python" trong WindowsApps la loi tat cua Store, gan voi ho so nguoi dung: SYSTEM khong chay duoc.
if ($py -like "*\WindowsApps\*") {
    Write-Host "python dang tro toi $py (loi tat Store) -- SYSTEM khong chay duoc no." -ForegroundColor Red
    Write-Host "Cai Python that (winget install Python.Python.3.12) roi chay lai." -ForegroundColor Red
    exit 1
}
$server = Join-Path $PSScriptRoot "pipe_server.py"
$log = Join-Path $PSScriptRoot "system.log"
$thamSo = "`"$server`" --ten $Ten --log `"$log`""
if ($DaclMacDinh) { $thamSo += " --dacl-mac-dinh" }

$action = New-ScheduledTaskAction -Execute $py -Argument $thamSo -WorkingDirectory $PSScriptRoot
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $tacVu -Action $action -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $tacVu
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Server dang chay bang SYSTEM ($(if ($DaclMacDinh) {'DACL MAC DINH'} else {'DACL cua ta'}))."
Write-Host "Log: $log"
Get-Content $log -Tail 3 -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Gan PipeSpike len chart roi xem: Get-Content `"$log`" -Wait -Tail 20"
Write-Host "Xong thi: .\chay-bang-system.ps1 -Go"
