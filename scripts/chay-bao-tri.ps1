<#
.SYNOPSIS
    Chay `bridge.admin bao-tri` va giu lai output. Scheduled Task '\CopyBridge\BaoTri' goi file nay.

.DESCRIPTION
    Task Scheduler vut stdout di, nen wrapper nay ton tai chi de output con lai o dau do doc
    duoc. `bao-tri` chay retention, VACUUM INTO mot ban sao luu, giu 14 ban gan nhat, roi TU MO
    LAI ban vua tao de kiem chung -- mot ban sao luu chua tung khoi phuc thu thi khong phai ban
    sao luu, va cho de biet no hong la o day.
#>
[CmdletBinding()]
param([string] $ThuMuc = "C:\CopyBridge")

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }
$env:PYTHONUTF8 = "1"

# logs/ va data/ deu la duong dan tuong doi theo thu muc lam viec.
Set-Location $ThuMuc

$py = Join-Path $ThuMuc ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Khong thay $py. Chay scripts\cai-dat.ps1 truoc." }

$nhatKy = Join-Path $ThuMuc "logs\bao-tri.log"
Add-Content -Path $nhatKy -Value ("=" * 70) -Encoding utf8
Add-Content -Path $nhatKy -Value (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Encoding utf8

& $py -m bridge.admin bao-tri *>&1 | Tee-Object -FilePath $nhatKy -Append
exit $LASTEXITCODE
