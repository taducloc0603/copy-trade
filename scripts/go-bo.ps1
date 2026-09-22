<#
.SYNOPSIS
    Go sach toan bo ban cai tren may nay: dich vu, tac vu, tien trinh, EA, bi mat, thu muc.

.DESCRIPTION
    Viec go co THU TU BAT BUOC, va sai thu tu thi im lang khong bao:

      dung cai dang chay  ->  xoa file  ->  xoa thu muc

    Vi du ve cai gia cua sai thu tu: xoa thu muc truoc khi giet clicker thi clicker van song,
    van bam vao cua so MT5, va van giu mutex Global\CopyBridgeClicker-<muc> -- ban cai moi se
    thoat ma 3 ("da co clicker khac dang chay") ma khong ai hieu vi sao.

    Truoc ban nay cach go duy nhat la muc B7 cua docs\CAI-DAT-VPS.md: `-GoBo` roi `Rename-Item`.
    No de lai bon thu: tien trinh clicker dang chay, EA con gan tren chart cung .ex5 va
    MQL5\Files\copybridge cua tung terminal, BAN RO cua mat khau dashboard + token clicker trong
    thu muc vua doi ten, va thu muc tac vu \CopyBridge\ + tools\nssm + bo cai trong %TEMP%.

    Script KHONG go: Python, git, NSSM (winget, may khac con dung); autologon + tat sleep + tat
    khoa man hinh (muc A0 -- ban cai moi VAN CAN); MT5 va cac tai khoan; va EA dang gan tren chart
    -- thu duy nhat phai lam tay, vi chart nam trong profile cua MT5.

.EXAMPLE
    # Xem truoc: in ra se xoa nhung gi roi thoat, KHONG cham gi.
    .\go-bo.ps1 -ThuMuc C:\CopyBridge -ChayThu

.EXAMPLE
    .\go-bo.ps1 -ThuMuc C:\CopyBridge
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string] $ThuMuc = "C:\CopyBridge",
    [string] $TenDichVu = "CopyBridge",
    # In ra se lam gi roi thoat. Chay duoc o bat ky may nao, ke ca may dev.
    [switch] $ChayThu,
    # Bo qua cau hoi thu hai khi con cap dang mo. CHI dung khi ban da tu dong tay trong MT5.
    [switch] $BoQuaKiemCap
)

Set-StrictMode -Version Latest
# PowerShell 5.1: voi 'Stop', MOT DONG stderr bat ky tu mot exe bi boc thanh NativeCommandError va
# nem ra NGAY. Moi lenh native o day duoc kiem tuong minh.
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }

$DuongDanTacVu = "\CopyBridge\"
#: Cum phai go dung de go sach. CO Y KHONG DAU: mot cum co dau phu thuoc bo go dang o che do nao.
$CumXacNhan = "GO BO TAT CA"

function ok([string] $tin)   { Write-Host "  OK: $tin" -ForegroundColor Green }
function canh([string] $tin) { Write-Host "  CANH BAO: $tin" -ForegroundColor Yellow }
function se([string] $tin)   { Write-Host "  SE XOA: $tin" -ForegroundColor Cyan }
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
# Tim kiem: dung chung giua -ChayThu va lan chay that, de hai duong khong bao gio lech nhau
# ---------------------------------------------------------------------------------------------
function tien_trinh_cua_tool() {
    # CHI tra ve doi tuong de lay ProcessId. TUYET DOI khong in CommandLine: clicker kieu cu co
    # token trong do, va mot dong log co token la mot token bi ro ri vinh vien.
    return @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -match '-m (bridge|clicker)(\s|$)' })
}

function tien_trinh_wrapper() {
    # WRAPPER: powershell.exe chay chay-clicker.ps1 / chay-bao-tri.ps1 / kiem-tra.ps1 trong $ThuMuc.
    #
    # Bo sot chung la sai o hai muc, va da xay ra that tren VPS 2026-09-21:
    #
    #   1. chay-clicker.ps1 co VONG TU BAT LAI. Giet python.exe ma bo wrapper thi wrapper bat len
    #      mot clicker moi -- dung cai no ton tai de lam.
    #   2. Wrapper la thu GIU logs\clicker-wrapper.log (no Add-Content vao do moi vong) va giu ca
    #      $ThuMuc lam thu muc lam viec (`Set-Location $ThuMuc` o dau file). Do la ly do xoa thu
    #      muc that bai voi "being used by another process".
    #
    # Nen wrapper phai bi giet TRUOC python.exe, khong phai sau.
    #
    # Loc theo $ThuMuc de khong dung toi wrapper cua mot ban cai khac tren cung may. Tru $PID va
    # tru chinh go-bo.ps1: dong lenh cua chinh script nay cung chua duong dan $ThuMuc.
    return @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like "*$ThuMuc*" -and
                            $_.CommandLine -notlike "*go-bo*" })
}

function tac_vu_cua_tool() {
    return @(Get-ScheduledTask -TaskPath $DuongDanTacVu -ErrorAction SilentlyContinue)
}

function thu_muc_du_lieu_mt5() {
    # Moi terminal MT5 mot thu muc du lieu rieng duoi %APPDATA%\MetaQuotes\Terminal\<hash>. Ban
    # portable thi du lieu nam ngay trong thu muc cai, nen quet ca hai cho.
    $goc = @(Join-Path $env:APPDATA "MetaQuotes\Terminal")
    $goc += @("C:\Program Files", "C:\Program Files (x86)")
    $ket = @()
    foreach ($g in $goc) {
        if (-not (Test-Path $g)) { continue }
        $ket += @(Get-ChildItem $g -Directory -ErrorAction SilentlyContinue |
                  Where-Object { Test-Path (Join-Path $_.FullName "MQL5") } |
                  ForEach-Object { $_.FullName })
    }
    return $ket
}

function file_ea_cua_tool() {
    # .ex5 trong MQL5\Experts, VA thu muc MQL5\Files\copybridge -- cho EA giu state.json,
    # outbox.ndjson, commands.ndjson cua tung tai khoan. Bo sot thu muc nay thi ban cai moi doc
    # lai mot outbox cua he thong cu.
    $ket = @()
    foreach ($t in @(thu_muc_du_lieu_mt5)) {
        $ket += @(Get-ChildItem (Join-Path $t "MQL5\Experts") -Filter "CopyBridge*" -File `
                    -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
        $hop = Join-Path $t "MQL5\Files\copybridge"
        if (Test-Path $hop) { $ket += $hop }
    }
    return $ket
}

function file_bi_mat() {
    # config.toml va MOI ban sao cua no: mot ban sao la mot ban RO cua mat khau dashboard va token
    # clicker. `.tam` la file trung gian cua duong sua tu dashboard, co the sot lai sau mot cu chet.
    if (-not (Test-Path $ThuMuc)) { return @() }
    return @(Get-ChildItem $ThuMuc -Filter "config.toml*" -File -ErrorAction SilentlyContinue |
             ForEach-Object { $_.FullName })
}

function rac_tam() {
    $ket = @()
    $desktop = Join-Path $env:USERPROFILE "Desktop\cai-dat.ps1"
    # Ban cai-dat.ps1 cu tren Desktop la dung cai bay muc A1 phai canh bao: chay lai ban cu thi
    # khong co dong "(ban <ngay>)" va khong ai doc ra vi sao buoc cai loi.
    if (Test-Path $desktop) { $ket += $desktop }
    foreach ($mau in @("python-*-amd64.exe", "Git-*-64-bit.exe", "nssm-*.zip")) {
        $ket += @(Get-ChildItem $env:TEMP -Filter $mau -File -ErrorAction SilentlyContinue |
                  ForEach-Object { $_.FullName })
    }
    $giaiNen = Join-Path $env:TEMP "nssm-giai-nen"
    if (Test-Path $giaiNen) { $ket += $giaiNen }
    return $ket
}

# ---------------------------------------------------------------------------------------------
function in_xem_truoc() {
    tieu_de "Se go nhung thu sau"

    $dv = Get-Service $TenDichVu -ErrorAction SilentlyContinue
    if ($null -ne $dv) { se "dich vu $TenDichVu (dang $($dv.Status))" }
    else { Write-Host "  (khong co dich vu $TenDichVu)" -ForegroundColor DarkGray }

    $tv = @(tac_vu_cua_tool)
    if ($tv.Count -gt 0) { foreach ($t in $tv) { se "tac vu ${DuongDanTacVu}$($t.TaskName)" } }
    else { Write-Host "  (khong co tac vu nao trong $DuongDanTacVu)" -ForegroundColor DarkGray }

    $wr = @(tien_trinh_wrapper)
    if ($wr.Count -gt 0) { se ("wrapper PowerShell PID " + (($wr | ForEach-Object { $_.ProcessId }) -join ', ')) }
    else { Write-Host "  (khong co wrapper PowerShell nao cua $ThuMuc)" -ForegroundColor DarkGray }

    $tt = @(tien_trinh_cua_tool)
    if ($tt.Count -gt 0) { se ("tien trinh PID " + (($tt | ForEach-Object { $_.ProcessId }) -join ', ')) }
    else { Write-Host "  (khong co tien trinh Bridge/clicker nao)" -ForegroundColor DarkGray }

    $ea = @(file_ea_cua_tool)
    if ($ea.Count -gt 0) { foreach ($f in $ea) { se $f } }
    else { Write-Host "  (khong thay EA hay du lieu EA trong terminal nao)" -ForegroundColor DarkGray }

    foreach ($f in @(file_bi_mat)) { se "$f  <-- ban ro mat khau/token" }
    foreach ($f in @(rac_tam))     { se $f }

    if (Test-Path $ThuMuc) { se "ca thu muc $ThuMuc (database, log, .venv, tools\nssm)" }
    else { Write-Host "  (khong co thu muc $ThuMuc)" -ForegroundColor DarkGray }

    tieu_de "CO Y KHONG go"
    Write-Host "  - Python 3.12, git, NSSM: ban cai moi can dung chung. Muon go:" -ForegroundColor DarkGray
    Write-Host "      winget uninstall Python.Python.3.12 Git.Git NSSM.NSSM" -ForegroundColor DarkGray
    Write-Host "  - Autologon, tat sleep/hibernate, tat khoa man hinh (muc A0): ban cai moi VAN CAN." -ForegroundColor DarkGray
    Write-Host "  - MT5, cac tai khoan, Allow WebRequest 127.0.0.1, Algo Trading, Toolbox tab Trade." -ForegroundColor DarkGray
    Write-Host "  - EA dang gan tren chart: PHAI go tay tren tung terminal (chuot phai chart ->" -ForegroundColor DarkGray
    Write-Host "    Expert Advisors -> Remove). Chart nam trong profile cua MT5, script khong voi toi." -ForegroundColor DarkGray
}

function kiem_cap_dang_mo() {
    # Xoa so sach trong luc tien con tren san la cach chac chan nhat de khong ai biet con gi mo.
    $py = Join-Path $ThuMuc ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { return }
    Push-Location $ThuMuc
    try {
        $ra = (& $py -m bridge.admin tinh-hinh) 2>&1
        $ma = $LASTEXITCODE
    } finally { Pop-Location }
    if ($ma -eq 0) { ok "tinh-hinh: khong co muc nao can chu y"; return }

    canh "tinh-hinh thoat ma $ma -- co muc can chu y. Doc ky truoc khi xoa:"
    $ra | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    if ($BoQuaKiemCap) { canh "-BoQuaKiemCap: di tiep"; return }
    Write-Host ""
    Write-Host "  Con cap dang mo thi vi the THAT tren san khong bien mat khi xoa database." -ForegroundColor Yellow
    Write-Host "  Dong tay trong MT5 truoc, hoac go 'DONG Y' de di tiep:" -ForegroundColor Yellow
    if ((Read-Host "  ") -ne "DONG Y") { throw "Dung lai theo yeu cau." }
}

function go_dich_vu_va_tac_vu() {
    tieu_de "Dich vu va tac vu"
    $tao = Join-Path $ThuMuc "scripts\tao-dich-vu.ps1"
    if (Test-Path $tao) {
        # Dung lai -GoBo thay vi viet lai: no da go dich vu NSSM (keo theo ca mat khau tai khoan
        # dich vu do SCM giu) va MOI tac vu Clicker* + BaoTri + TinhHinh.
        & $tao -ThuMuc $ThuMuc -TenDichVu $TenDichVu -GoBo
        if ($LASTEXITCODE -ne 0) { canh "tao-dich-vu.ps1 -GoBo thoat ma $LASTEXITCODE" }
    } else {
        canh "khong thay $tao, go bang tay"
        $dv = Get-Service $TenDichVu -ErrorAction SilentlyContinue
        if ($null -ne $dv) {
            if ($dv.Status -eq 'Running') { Stop-Service $TenDichVu -Force }
            $nssm = (Get-Command nssm -ErrorAction SilentlyContinue)
            if ($null -ne $nssm) { & $nssm.Source remove $TenDichVu confirm | Out-Null; ok "da go dich vu" }
            else { canh "khong thay nssm.exe -- go dich vu $TenDichVu bang tay" }
        }
        foreach ($t in @(tac_vu_cua_tool)) {
            Unregister-ScheduledTask -TaskPath $DuongDanTacVu -TaskName $t.TaskName -Confirm:$false
            ok "da go tac vu $($t.TaskName)"
        }
    }

    # Xoa THU MUC tac vu: Unregister-ScheduledTask khong xoa no, va mot thu muc \CopyBridge\ con
    # lai se lam nguoi kiem tuong he thong chua duoc go.
    $conLai = @(tac_vu_cua_tool)
    if ($conLai.Count -gt 0) {
        canh ("con " + $conLai.Count + " tac vu trong ${DuongDanTacVu} : " +
              (($conLai | ForEach-Object { $_.TaskName }) -join ', '))
        return
    }
    try {
        $folder = New-Object -ComObject "Schedule.Service"
        $folder.Connect()
        $folder.GetFolder("\").DeleteFolder($DuongDanTacVu.Trim('\'), 0)
        ok "da xoa thu muc tac vu $DuongDanTacVu"
    } catch {
        canh "khong xoa duoc thu muc tac vu $DuongDanTacVu ($($_.Exception.Message)) -- vo hai"
    }
}

function giet_tien_trinh_con_sot() {
    tieu_de "Tien trinh con sot"

    # THU TU: wrapper TRUOC, python SAU. Nguoc lai thi vong tu bat lai cua chay-clicker.ps1 se bat
    # len mot clicker moi ngay sau khi ta giet cai cu.
    $wr = @(tien_trinh_wrapper)
    foreach ($p in $wr) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        ok "da giet wrapper PID $($p.ProcessId)"
    }
    if ($wr.Count -eq 0) { ok "khong co wrapper PowerShell nao cua $ThuMuc" }
    else { Start-Sleep -Seconds 1 }

    $tt = @(tien_trinh_cua_tool)
    foreach ($p in $tt) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        ok "da giet PID $($p.ProcessId)"
    }
    if ($tt.Count -eq 0) { ok "khong con tien trinh Bridge/clicker nao" }

    if ($wr.Count -eq 0 -and $tt.Count -eq 0) { return }
    Start-Sleep -Seconds 2
    $con = @(tien_trinh_wrapper) + @(tien_trinh_cua_tool)
    if ($con.Count -gt 0) {
        canh ("KHONG giet duoc PID " + (($con | ForEach-Object { $_.ProcessId }) -join ', ') +
              " -- chung con giu mutex Global\CopyBridgeClicker-*, con giu logs\ va con giu ca " +
              "thu muc cai, nen buoc xoa thu muc se that bai")
    } else {
        ok "mutex Global\CopyBridgeClicker-* da duoc tha"
    }
}

function go_ea_tren_cac_terminal() {
    tieu_de "EA va du lieu EA tren cac terminal MT5"
    $ea = @(file_ea_cua_tool)
    if ($ea.Count -eq 0) { ok "khong thay gi de xoa"; return }
    foreach ($f in $ea) {
        try {
            Remove-Item $f -Recurse -Force -ErrorAction Stop
            ok "da xoa $f"
        } catch {
            # File .ex5 dang duoc MT5 nap thi bi giu. Do la dau hieu EA CHUA duoc go khoi chart.
            canh "khong xoa duoc $f ($($_.Exception.Message)). Go EA khoi chart roi chay lai."
        }
    }
}

function xoa_bi_mat() {
    tieu_de "Bi mat"
    $f = @(file_bi_mat)
    if ($f.Count -eq 0) { ok "khong con config.toml hay ban sao nao"; return }
    # Xoa TRUOC khi xoa thu muc: neu buoc xoa thu muc that bai vi mot file bi giu, bi mat van da
    # di roi. Day la thu tu co chu dich, khong phai tinh co.
    foreach ($x in $f) {
        Remove-Item $x -Force -ErrorAction SilentlyContinue
        if (Test-Path $x) { canh "khong xoa duoc $x" } else { ok "da xoa $x" }
    }
}

function xoa_rac_tam() {
    tieu_de "Bo cai tam va script tren Desktop"
    $r = @(rac_tam)
    if ($r.Count -eq 0) { ok "khong co gi"; return }
    foreach ($x in $r) {
        Remove-Item $x -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $x) { canh "khong xoa duoc $x" } else { ok "da xoa $x" }
    }
}

function xoa_thu_muc_cai() {
    tieu_de "Thu muc cai"
    if (-not (Test-Path $ThuMuc)) { ok "$ThuMuc khong ton tai"; return $true }

    # PHAI doi CA HAI thu, khong phai mot:
    #
    #   Set-Location             -> vi tri cua PROVIDER PowerShell
    #   [Environment]::CurrentDirectory -> thu muc lam viec that cua TIEN TRINH
    #
    # Set-Location KHONG cap nhat cai thu hai. Va cai thu hai moi la cai Windows dung de tu choi
    # xoa: neu thu muc lam viec cua tien trinh nam trong $ThuMuc thi `Remove-Item -Recurse` xoa
    # het NOI DUNG roi that bai o dung THU MUC GOC. Da gap that tren VPS 2026-09-21 -- tai lieu
    # day `cd C:\CopyBridge` roi moi chay script, nen cai bay nay la duong chay binh thuong.
    Set-Location "C:\"
    [Environment]::CurrentDirectory = "C:\"

    Remove-Item $ThuMuc -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $ThuMuc) {
        # Windows co the con dang tha handle cua cac file vua bi xoa. Thu lai MOT lan truoc khi
        # ket luan, chu khong bao that bai ngay.
        Start-Sleep -Seconds 1
        Remove-Item $ThuMuc -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path $ThuMuc)) { ok "da xoa $ThuMuc"; return $true }

    # Con lai gi? Khac biet giua "chi con cai vo" va "database + config.toml chua xoa" la khac
    # biet giua may da sach va ban ro mat khau con nam tren dia. Noi thang ra, dung de nguoi doc
    # tu doan.
    $conLai = @(Get-ChildItem $ThuMuc -Force -Recurse -ErrorAction SilentlyContinue)
    if ($conLai.Count -eq 0) {
        canh "KHONG xoa duoc $ThuMuc, nhung no RONG: khong con database, log hay bi mat nao."
        Write-Host "    Chi con cai vo thu muc. Xoa no tu MOT CUA SO PowerShell KHAC:" -ForegroundColor Yellow
    } else {
        canh "KHONG xoa duoc $ThuMuc, va con $($conLai.Count) muc ben trong:"
        $conLai | Select-Object -First 5 | ForEach-Object {
            Write-Host "      $($_.FullName)" -ForegroundColor Yellow
        }
        $biMat = @($conLai | Where-Object { $_.Name -like "config.toml*" })
        if ($biMat.Count -gt 0) {
            canh ("VAN CON BI MAT tren dia: " + (($biMat | ForEach-Object { $_.Name }) -join ', ') +
                  " -- do la ban ro cua mat khau dashboard va token clicker. Xoa chung truoc.")
        }
        # Dung dong lenh, KHONG dung duong dan file thuc thi: ke giu file hay gap nhat la
        # chay-clicker.ps1, ma no chay bang powershell.exe nam trong System32 -- loc theo
        # `$_.Path -like "$ThuMuc\*"` se khong bao gio thay no. Van chi in TEN va PID.
        $giu = @(tien_trinh_wrapper) + @(tien_trinh_cua_tool)
        if ($giu.Count -gt 0) {
            canh ("Tien trinh dang giu file: " +
                  (($giu | ForEach-Object { "$($_.Name) (PID $($_.ProcessId))" }) -join ', ') +
                  ". Giet chung roi xoa lai.")
        } else {
            Write-Host "    Khong thay tien trinh nao chay tu thu muc do. Thu dong MT5 va" -ForegroundColor Yellow
            Write-Host "    moi cua so dang mo file trong do, roi chay:" -ForegroundColor Yellow
        }
    }
    Write-Host "    Remove-Item -Recurse -Force '$ThuMuc'" -ForegroundColor Yellow
    return $false
}

function in_bang_kiem() {
    tieu_de "Kiem may da sach (moi dong phai ra ket qua nhu ghi chu)"
    # Bo loc phai HEP bang dung bo loc `tien_trinh_cua_tool` / `tien_trinh_wrapper` da dung de giet
    # -- neu khong thi bang kiem va script noi hai chuyen khac nhau. Ban cu loc
    # `CommandLine` khop ten thu muc cai la khop ca notepad.exe dang mo mot file trong do, va
    # da bao nham tren VPS 2026-09-22. Mot bang kiem keu oan la bang kiem nguoi ta thoi doc.
    @(
        'Get-Service CopyBridge -ErrorAction SilentlyContinue                       # khong ra gi',
        "Get-ScheduledTask -TaskPath '$DuongDanTacVu' -ErrorAction SilentlyContinue # khong ra gi",
        'Get-CimInstance Win32_Process -Filter "Name=''python.exe''" | Where-Object {',
        '  $_.CommandLine -match ''-m (bridge|clicker)(\s|$)'' }                    # khong ra gi',
        'Get-CimInstance Win32_Process -Filter "Name=''powershell.exe''" | Where-Object {',
        "  `$_.ProcessId -ne `$PID -and `$_.CommandLine -like '*$ThuMuc*' }          # khong ra gi",
        "Test-Path '$ThuMuc'                                                        # False",
        'Get-ChildItem "$env:APPDATA\MetaQuotes\Terminal\*\MQL5\Experts\CopyBridge*"    # khong ra gi',
        'Get-ChildItem "$env:APPDATA\MetaQuotes\Terminal\*\MQL5\Files\copybridge" -EA 0 # khong ra gi'
    ) | ForEach-Object { Write-Host "  $_" }

    Write-Host ""
    Write-Host " Token cu tu mat hieu luc: Bridge chi giu HASH cua token trong agent.token_hash," -ForegroundColor Green
    Write-Host " nen xoa database la xoa het -- khong phai di thu hoi o dau." -ForegroundColor Green
    Write-Host ""
    Write-Host " Cai lai: lam theo Phan A cua docs\CAI-DAT-VPS.md tu A1. Neu A1 in 'BO QUA' o buoc" -ForegroundColor Cyan
    Write-Host " nao thi may CHUA sach -- do la phep thu tot nhat." -ForegroundColor Cyan
}

# ---------------------------------------------------------------------------------------------
try {
    Write-Host ""
    Write-Host " MT5 Copy Bridge -- go sach (ban 2026-09-21)" -ForegroundColor Cyan
    Write-Host " Thu muc: $ThuMuc"

    in_xem_truoc

    if ($ChayThu) {
        Write-Host ""
        Write-Host " -ChayThu: khong cham gi ca. Bo -ChayThu de go that." -ForegroundColor Cyan
        exit 0
    }

    if (-not (la_admin)) {
        throw "Can quyen Administrator. Mo lai PowerShell bang 'Run as administrator'."
    }

    Write-Host ""
    Write-Host " Go bo KHONG LUI DUOC: database, log va config.toml bi xoa han." -ForegroundColor Yellow
    Write-Host " Go dung cum sau de di tiep, hoac Enter de thoi:" -ForegroundColor Yellow
    Write-Host "   $CumXacNhan" -ForegroundColor Yellow
    if ((Read-Host "  ") -ne $CumXacNhan) {
        Write-Host " Cum xac nhan khong dung. Khong xoa gi." -ForegroundColor Green
        exit 1
    }

    kiem_cap_dang_mo
    go_dich_vu_va_tac_vu
    giet_tien_trinh_con_sot
    go_ea_tren_cac_terminal
    xoa_bi_mat
    xoa_rac_tam
    $sach = xoa_thu_muc_cai
    in_bang_kiem

    if (-not $sach) { exit 2 }
    exit 0
} catch {
    Write-Host ""
    Write-Host " LOI: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
