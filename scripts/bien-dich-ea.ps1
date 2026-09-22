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

# `thu_muc_du_lieu_mt5` dung chung voi go-bo.ps1: mot ben CHEP .ex5 vao, mot ben XOA .ex5 ra.
. (Join-Path $PSScriptRoot "chung-mt5.ps1")

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

# Chep vao MT5 thay vi bao nguoi dung tu lam. Truoc day script chi IN ra "buoc tiep theo van phai
# lam tay: chep .ex5 vao MQL5\Experts cua TUNG terminal" -- ba viec con, va cai bay lon nhat la moi
# terminal co mot thu muc du lieu RIENG, nen chep vao mot cai roi tuong ca hai da co.
#
# Chep CA HAI file vao CA HAI terminal. Vo hai: EA chi chay khi duoc keo len chart, nen mot
# CopyBridgeClient.ex5 nam trong thu muc cua terminal Master khong lam gi ca. Doi lai, khong con
# phai biet file nao vao terminal nao.
Write-Host "Chep .ex5 vao MT5:"
$dich = @(thu_muc_du_lieu_mt5)
if ($dich.Count -eq 0) {
    # Noi thang la 0. Bao "xong" khi khong chep duoc gi la kieu im lang dang muon bo -- nguoi dung
    # se di gan EA va khong thay no trong Navigator.
    Write-Host "  KHONG THAY thu muc du lieu MT5 nao. Chua cai MT5, hoac cai o cho la."
    Write-Host "  Chep tay hai file trong $(Join-Path $ThuMuc 'ea') vao MQL5\Experts cua tung"
    Write-Host "  terminal (trong MT5: File > Open Data Folder)."
    exit 3
}

$soChep = 0
foreach ($t in $dich) {
    $experts = Join-Path $t "MQL5\Experts"
    if (-not (Test-Path $experts)) {
        New-Item -ItemType Directory -Force $experts | Out-Null
    }
    foreach ($ea in @("CopyBridgeMaster.ex5", "CopyBridgeClient.ex5")) {
        $nguon = Join-Path $ThuMuc "ea\$ea"
        if (-not (Test-Path $nguon)) { continue }
        try {
            Copy-Item $nguon $experts -Force -ErrorAction Stop
            $soChep++
        } catch {
            Write-Host "  HONG  $ea -> $experts : $($_.Exception.Message)"
            $hong++
        }
    }
    Write-Host "  OK    $experts"
}

Write-Host ""
if ($hong -gt 0) {
    Write-Host "Bien dich xong nhung chep khong tron ($hong loi). Doc cac dong HONG ben tren."
    exit 1
}
Write-Host "Xong: hai EA da bien dich va chep vao $($dich.Count) thu muc MT5 ($soChep file)."
Write-Host "Con dung MOT viec lam tay: trong tung MT5, Ctrl+N roi chuot phai Expert Advisors >"
Write-Host "Refresh de no doc lai danh sach."
exit 0
