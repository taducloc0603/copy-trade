<#
.SYNOPSIS
    Khoi dong lai Bridge cho DEN NOI: dung, cho cong duoc nha, giet tien trinh mo coi, bat lai.

.DESCRIPTION
    `Restart-Service CopyBridge` khong du, va cai thieu cua no im lang:

      SCM bao dich vu da dung TRUOC KHI tien trinh python con thoat han. Ban moi khoi dong len
      thay cong 8787 con bi giu va CO Y khong chay (Bridge kiem cong truoc de bao loi tu te thay
      vi chay nua voi). Windows chi noi "Failed to start service" -- khong mot chu nao ve cong.
      Dau vet duy nhat nam trong logs\service-err.log, file khong ai mo cho toi khi co su co.

    Da xay ra that tren VPS 2026-09-22, sau dung mot lenh `git pull` + `Restart-Service` -- tuc
    dung thu tai lieu dang bao nguoi dung lam sau moi lan cap nhat.

    Script nay lam dung thu tu do: dung -> cho cong duoc nha -> giet tien trinh mo coi neu con
    giu -> bat lai -> cho toi khi cong THAT SU co nguoi nghe roi moi bao xong.

.EXAMPLE
    .\khoi-dong-lai.ps1

.EXAMPLE
    .\khoi-dong-lai.ps1 -ThuMuc D:\CopyBridge -GiayChoNha 30
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string] $ThuMuc = "C:\CopyBridge",
    [string] $TenDichVu = "CopyBridge",
    # Cho cong duoc nha bao lau truoc khi ket luan la co tien trinh mo coi.
    [int]    $GiayChoNha = 20,
    # Cho dich vu len va cong co nguoi nghe bao lau.
    [int]    $GiayChoLen = 45,
    # Khong giet gi ca: chi bao ai dang giu cong roi thoat. Dung khi nghi co tien trinh la.
    [switch] $KhongGiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }

function ok([string] $tin)   { Write-Host "  OK: $tin" -ForegroundColor Green }
function canh([string] $tin) { Write-Host "  CANH BAO: $tin" -ForegroundColor Yellow }
function tieu_de([string] $t) {
    Write-Host ""
    Write-Host "== $t" -ForegroundColor Cyan
}

$script:VenvPy = Join-Path $ThuMuc ".venv\Scripts\python.exe"

function cong_theo_khoa([string] $khoa) {
    # Hoi chinh Bridge, khong tu parse TOML trong PowerShell. KHONG duoc nem: thieu .venv thi `&`
    # nem CommandNotFoundException -- mot loi TERMINATING ma $ErrorActionPreference khong chan.
    if (-not (Test-Path $script:VenvPy)) { return $null }
    Push-Location $ThuMuc
    try {
        $ra = & $script:VenvPy -c "from bridge.config import load_config; print(load_config().bridge.$khoa)" 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $p = 0
        if ([int]::TryParse("$ra".Trim(), [ref] $p)) { return $p }
        return $null
    } catch {
        return $null
    } finally { Pop-Location }
}

# Ba ham duoi tra ve MANG, va moi cho GAN phai boc lai bang @(). PowerShell trai phang gia tri
# tra ve cua ham: mot mang rong thanh $null, mot phan tu thanh scalar. Voi Set-StrictMode thi
# $null.Count nem "The property 'Count' cannot be found on this object" -- va do la cach script nay
# chet ngay lan chay dau tien tren VPS (2026-09-22), dung o nhanh MUNG nhat: cong da duoc nha.
function ai_dang_giu([int] $cong) {
    return @(Get-NetTCPConnection -State Listen -LocalPort $cong -ErrorAction SilentlyContinue |
             ForEach-Object { [int] $_.OwningProcess } | Sort-Object -Unique)
}

function cho_nha([int[]] $cong, [int] $giay) {
    $han = (Get-Date).AddSeconds($giay)
    while ((Get-Date) -lt $han) {
        $giu = @($cong | ForEach-Object { ai_dang_giu $_ } | Sort-Object -Unique)
        if ($giu.Count -eq 0) { return @() }
        Start-Sleep -Seconds 2
    }
    return @($cong | ForEach-Object { ai_dang_giu $_ } | Sort-Object -Unique)
}

function cho_nghe([int[]] $cong, [int] $giay) {
    $han = (Get-Date).AddSeconds($giay)
    while ((Get-Date) -lt $han) {
        $thieu = @($cong | Where-Object { @(ai_dang_giu $_).Count -eq 0 })
        if ($thieu.Count -eq 0) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

# ---------------------------------------------------------------------------------------------
try {
    Write-Host ""
    Write-Host " MT5 Copy Bridge -- khoi dong lai (ban 2026-09-22)" -ForegroundColor Cyan
    Write-Host " Thu muc: $ThuMuc"

    $congAgent = cong_theo_khoa "port"
    $congWeb = cong_theo_khoa "web_port"
    if ($null -eq $congAgent) { $congAgent = 8787 }
    if ($null -eq $congWeb)   { $congWeb = 8080 }
    $cong = @($congAgent, $congWeb)
    Write-Host " Cong: agent $congAgent, dashboard $congWeb" -ForegroundColor DarkGray

    tieu_de "Dung dich vu"
    $dv = Get-Service $TenDichVu -ErrorAction SilentlyContinue
    if ($null -eq $dv) {
        canh "chua dang ky dich vu $TenDichVu. Chay scripts\tao-dich-vu.ps1 truoc."
        exit 1
    }
    if ($dv.Status -ne 'Stopped') {
        Stop-Service $TenDichVu -ErrorAction SilentlyContinue
        ok "da yeu cau dung"
    } else {
        ok "dich vu dang dung san"
    }

    tieu_de "Cho cong duoc nha"
    $giu = @(cho_nha $cong $GiayChoNha)
    if ($giu.Count -eq 0) {
        ok "khong con ai giu cong $congAgent / $congWeb"
    } else {
        # Day chinh la trang thai lam `Restart-Service` that bai trong im lang. CHI in PID: dong
        # lenh cua clicker ban cu co token trong do.
        canh ("cong van bi giu sau $GiayChoNha giay boi PID " + ($giu -join ', ') +
              " -- SCM bao da dung nhung tien trinh con chua thoat.")
        if ($KhongGiet) {
            canh "-KhongGiet: dung tay bang Stop-Process -Id <PID> -Force roi chay lai."
            exit 2
        }
        foreach ($p in $giu) {
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
            ok "da giet PID $p"
        }
        $conGiu = @(cho_nha $cong 10)
        if ($conGiu.Count -gt 0) {
            canh ("VAN con PID " + ($conGiu -join ', ') + " giu cong. Dung tay roi chay lai.")
            exit 2
        }
        ok "cong da duoc nha"
    }

    tieu_de "Bat lai"
    Start-Service $TenDichVu -ErrorAction SilentlyContinue
    if (cho_nghe $cong $GiayChoLen) {
        ok "dich vu dang chay va cong $congAgent / $congWeb da co nguoi nghe"
        Write-Host ""
        Write-Host " Dashboard: http://127.0.0.1:$congWeb/#huong-dan" -ForegroundColor Cyan
        Write-Host " Bridge luon khoi dong o PAUSED (D-15) -- phai bam 'Bat dau copy' bang tay." -ForegroundColor Yellow
        exit 0
    }

    # Len khong duoc thi noi DUNG BA CHO can xem, thay vi de nguoi dung tu do.
    canh "dich vu khong len sau $GiayChoLen giay. Ba cho can xem, theo thu tu:"
    Write-Host "    Get-Content $ThuMuc\logs\service-err.log -Tail 25" -ForegroundColor Yellow
    Write-Host "    Get-Content $ThuMuc\logs\bridge.log -Tail 25" -ForegroundColor Yellow
    Write-Host "    Get-NetTCPConnection -State Listen -LocalPort $congAgent | Select-Object OwningProcess" -ForegroundColor Yellow
    exit 3
} catch {
    Write-Host ""
    Write-Host " LOI: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
