<#
.SYNOPSIS
    Bien dich CA HAI EA thanh .ex5 bang MetaEditor. Khong tuong tac, khong mo giao dien.

.DESCRIPTION
    Tach ra khoi `tro-ly.ps1::buoc_bien_dich` de nut "Chay" tren dashboard goi duoc: tro ly hoi
    "co/khong" truoc khi lam, va mot cau hoi tren stdin thi mot tien trinh con cua dich vu khong
    tra loi duoc.

    Bien dich CA HAI trong mot lan chay. Cau lenh in tren tab Huong dan chi bien dich Master roi
    bao nguoi dung "chay lai, doi Master thanh Client" -- dung loai viec nguoi ta lam sot mot nua,
    va trieu chung cua nua bi sot la "EA Client khong keo duoc len chart".

.EXAMPLE
    .\bien-dich-ea.ps1
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string] $ThuMuc = "C:\CopyBridge"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }

function tim_metaeditor() {
    $ungVien = @(
        (Join-Path $env:ProgramFiles "MetaTrader 5\MetaEditor64.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "MetaTrader 5\MetaEditor64.exe")
    )
    foreach ($u in $ungVien) { if ($u -and (Test-Path $u)) { return $u } }
    $tim = @(Get-ChildItem $env:ProgramFiles -Filter MetaEditor64.exe -Recurse `
                -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($tim.Count -gt 0) { return $tim[0].FullName }
    return $null
}

$me = tim_metaeditor
if ($null -eq $me) {
    Write-Host "KHONG THAY MetaEditor64.exe. Cai MT5 truoc roi bam lai nut nay."
    exit 2
}
Write-Host "MetaEditor: $me"

$log = Join-Path $ThuMuc "logs\compile.log"
$hong = 0
foreach ($ea in @("CopyBridgeMaster.mq5", "CopyBridgeClient.mq5")) {
    $nguon = Join-Path $ThuMuc "ea\$ea"
    if (-not (Test-Path $nguon)) {
        Write-Host "KHONG THAY $nguon"
        $hong++
        continue
    }
    $ex5 = [IO.Path]::ChangeExtension($nguon, ".ex5")
    $truoc = if (Test-Path $ex5) { (Get-Item $ex5).LastWriteTimeUtc } else { [datetime]::MinValue }

    # MetaEditor thoat KHAC 0 khi chi co canh bao, nen ma thoat cua no khong dung de ket luan.
    # Bang chung la .ex5 co ton tai va co MOI hon luc bat dau hay khong.
    & $me "/compile:$nguon" "/log:$log" | Out-Null

    if (-not (Test-Path $ex5)) {
        Write-Host "HONG  $ea -> khong ra .ex5. Doc logs\compile.log"
        $hong++
    } elseif ((Get-Item $ex5).LastWriteTimeUtc -le $truoc) {
        Write-Host "HONG  $ea -> .ex5 cu khong doi. Doc logs\compile.log"
        $hong++
    } else {
        Write-Host "OK    $ea -> $(Split-Path -Leaf $ex5)"
    }
}

Write-Host ""
if ($hong -gt 0) {
    Write-Host "$hong EA khong bien dich duoc. Chi tiet trong logs\compile.log"
    exit 1
}
Write-Host "Hai EA da bien dich xong. Buoc tiep theo van phai lam tay: chep .ex5 vao"
Write-Host "MQL5\Experts cua TUNG terminal (File > Open Data Folder), roi Refresh trong Navigator."
exit 0
