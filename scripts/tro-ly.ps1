<#
.SYNOPSIS
    Dan qua toan bo viec cai dat MT5 Copy Bridge, hoi xac nhan truoc tung buoc.

.DESCRIPTION
    cai-dat.ps1 dung nguoi dung lai o mot khoi "BUOC TIEP THEO" gom nam viec, moi viec vai lenh
    phai go tay, co viec can token vua hien dung mot lan tren man hinh. Sai thu tu hoac bo sot
    mot buoc thi he thong dung xong van khong copy duoc lenh nao -- va hong trong im lang.
    Script nay la mot lenh duy nhat thay cho ca khoi do.

    No DIEU PHOI cac script va lenh da co (cai-dat.ps1, bridge.admin, tao-dich-vu.ps1,
    kiem-tra.ps1) chu khong chep lai viec cua chung. Moi buoc idempotent: chay lai bao nhieu lan
    cung duoc, buoc nao xong roi se in BO QUA.

    Co dung hai cho phai dung lai cho con nguoi, va ca hai deu khong tu dong hoa duoc:
    gan EA len chart trong giao dien MT5, va bam RUNNING.

.EXAMPLE
    .\tro-ly.ps1
    Chay tu dau tren C:\CopyBridge.

.EXAMPLE
    .\tro-ly.ps1 -ThuMuc D:\CopyBridge -TuDongDongY
    Khong hoi xac nhan tung buoc, chi hoi nhung gia tri bat buoc phai co.
#>
[CmdletBinding()]
param(
    [string] $ThuMuc = "C:\CopyBridge",
    [string] $TenDichVu = "CopyBridge",
    [int]    $GiayChoEA = 300,
    [switch] $TuDongDongY,
    [switch] $BoQuaDichVu
)

Set-StrictMode -Version Latest
# Cung ly do da giai thich dau cai-dat.ps1: voi 'Stop', MOT dong stderr bat ky tu mot exe bi boc
# thanh NativeCommandError va nem ra ngay, truoc khi script kip doc $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }

$script:PhienBan = "2026-09-07"
$script:TongBuoc = 12
$script:BuocHienTai = 0

function buoc_moi([string] $ten) {
    $script:BuocHienTai++
    Write-Host ""
    Write-Host ("[{0}/{1}] {2}" -f $script:BuocHienTai, $script:TongBuoc, $ten) -ForegroundColor Cyan
}
function ok([string] $tin)     { Write-Host "        OK: $tin" -ForegroundColor Green }
function bo_qua([string] $tin) { Write-Host "        BO QUA: $tin" -ForegroundColor DarkGray }
function canh([string] $tin)   { Write-Host "        CANH BAO: $tin" -ForegroundColor Yellow }
function tach()                { Write-Host ("-" * 69) -ForegroundColor DarkGray }

# ---------------------------------------------------------------------------------------------
# Hoi dap
# ---------------------------------------------------------------------------------------------
# Read-Host tra ve $null khi stdin dong (chay qua ong dan, hoac ai do Ctrl+Z). Goi .Trim() len
# do thi nem "You cannot call a method on a null-valued expression" -- mot thong bao khong noi
# len duoc dieu gi. Va mot vong `while ($true)` doc EOF thi quay mai mai. Chan ca hai o day.
function doc_dong() {
    $d = Read-Host
    if ($null -eq $d) { throw "Het dau vao (stdin da dong). Script nay phai chay tuong tac." }
    return $d
}

function hoi_co_khong([string] $cauHoi, [bool] $macDinh = $true) {
    if ($TuDongDongY) { return $macDinh -or $true }
    $goiY = if ($macDinh) { "[Y/n]" } else { "[y/N]" }
    while ($true) {
        Write-Host ""
        Write-Host "  $cauHoi $goiY " -ForegroundColor Yellow -NoNewline
        $tl = (doc_dong).Trim().ToLower()
        if (-not $tl)                   { return $macDinh }
        if ($tl -in @('y', 'yes', 'c')) { return $true }
        if ($tl -in @('n', 'no', 'k'))  { return $false }
    }
}

function hoi_chuoi([string] $cauHoi, [string] $macDinh = "", [bool] $choPhepRong = $false) {
    $nhan = if ($macDinh) { "  $cauHoi [$macDinh]: " } else { "  ${cauHoi}: " }
    while ($true) {
        Write-Host $nhan -ForegroundColor Yellow -NoNewline
        $tl = (doc_dong).Trim()
        if ($tl)          { return $tl }
        if ($macDinh)     { return $macDinh }
        if ($choPhepRong) { return "" }
    }
}

function hoi_so([string] $cauHoi, [int] $macDinh = 0) {
    while ($true) {
        $tl = hoi_chuoi $cauHoi ([string] $macDinh)
        $so = 0
        if ([int]::TryParse($tl, [ref] $so)) { return $so }
        canh "'$tl' khong phai mot so."
    }
}

function cho_den_khi([string] $moTa, [scriptblock] $kiemTra, [int] $giay) {
    # Vong cho co gio, khong treo vinh vien: buoc nay doi mot viec lam trong giao dien MT5, va
    # nguoi dung co the dang ket o do chu khong phai dang cho script.
    Write-Host "        Dang cho $moTa (toi da $giay giay, Ctrl+C de dung)..." -ForegroundColor DarkGray
    $het = (Get-Date).AddSeconds($giay)
    while ((Get-Date) -lt $het) {
        if (& $kiemTra) { return $true }
        Start-Sleep -Seconds 5
        Write-Host "." -ForegroundColor DarkGray -NoNewline
    }
    Write-Host ""
    return $false
}

# ---------------------------------------------------------------------------------------------
# Goi bridge.admin. Tra ve @{ ma = <exit code>; ra = <stdout+stderr, mang dong> }
# ---------------------------------------------------------------------------------------------
function admin([string[]] $doiSo) {
    Push-Location $ThuMuc
    try {
        $ra = & $script:VenvPy -m bridge.admin @doiSo 2>&1
        return @{ ma = $LASTEXITCODE; ra = @($ra | ForEach-Object { "$_" }) }
    } finally { Pop-Location }
}

function admin_in([string[]] $doiSo) {
    $kq = admin $doiSo
    $kq.ra | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
    return $kq.ma
}

# `_in_token` trong bridge/admin.py in token ra stdout theo khuon co dinh: mot dong nhan
# "TOKEN cua <id> (chi hien MOT lan...)" roi dong ngay sau la token tho. Bat o day de token cua
# clicker di thang vao config.toml, khong phai di qua mat va ban phim cua nguoi van hanh.
function tach_token([string[]] $dong) {
    for ($i = 0; $i -lt $dong.Count; $i++) {
        # Khong doi dau cach truoc "chi": dong that la "TOKEN cua AG-X (chi hien MOT lan, ...".
        if ($dong[$i] -match 'TOKEN cua .*chi hien MOT lan') {
            if ($i + 1 -lt $dong.Count) { return $dong[$i + 1].Trim() }
        }
    }
    return $null
}

# ---------------------------------------------------------------------------------------------
# Ghi khoa vao muc [clicker] cua config.toml, giu nguyen phan con lai
# ---------------------------------------------------------------------------------------------
function dat_khoa_clicker([hashtable] $khoa) {
    $cfg = Join-Path $ThuMuc "config.toml"
    if (-not (Test-Path $cfg)) { throw "Khong thay $cfg." }
    $dong = [System.IO.File]::ReadAllLines($cfg)
    $trongMuc = $false
    $daDat = @{}

    for ($i = 0; $i -lt $dong.Count; $i++) {
        $d = $dong[$i].Trim()
        if ($d -match '^\[(.+)\]$') { $trongMuc = ($Matches[1] -eq 'clicker'); continue }
        if (-not $trongMuc) { continue }
        foreach ($k in @($khoa.Keys)) {
            if ($d -match "^$k\s*=") {
                $dong[$i] = "$k = " + $khoa[$k]
                $daDat[$k] = $true
            }
        }
    }
    $thieu = @(@($khoa.Keys) | Where-Object { -not $daDat.ContainsKey($_) })
    if ($thieu.Count -gt 0) {
        $dong = @($dong) + @("", "[clicker]") + @($thieu | ForEach-Object { "$_ = " + $khoa[$_] })
    }

    # PHAI la UTF-8 KHONG BOM: bridge/config.py mo file o che do nhi phan roi dua cho tomllib, va
    # BOM lam tomllib nem loi parse voi mot thong bao khong he nhac toi BOM.
    [System.IO.File]::WriteAllLines($cfg, $dong, (New-Object System.Text.UTF8Encoding($false)))
    # KHONG dung toi icacls: cai-dat.ps1 da siet quyen tren file nay roi, ghi de la noi long.
}

function nhay([string] $s) {
    $q = [char] 34
    return "$q" + ($s -replace '\\', '\\' -replace "$q", "\$q") + "$q"
}

# ---------------------------------------------------------------------------------------------
# B1. Nen
# ---------------------------------------------------------------------------------------------
function buoc_nen() {
    buoc_moi "Nen: Python, venv, goi, database"
    $script:VenvPy = Join-Path $ThuMuc ".venv\Scripts\python.exe"
    $caiDat = Join-Path $PSScriptRoot "cai-dat.ps1"
    if (-not (Test-Path $caiDat)) { $caiDat = Join-Path $ThuMuc "scripts\cai-dat.ps1" }

    if ((Test-Path $script:VenvPy) -and (Test-Path (Join-Path $ThuMuc "config.toml"))) {
        bo_qua "da co .venv va config.toml"
        return
    }
    if (-not (Test-Path $caiDat)) { throw "Khong thay cai-dat.ps1 canh script nay hay trong $ThuMuc." }
    if (-not (hoi_co_khong "Chay cai-dat.ps1 de dung nen truoc?")) {
        throw "Khong co nen thi khong lam tiep duoc. Chay scripts\cai-dat.ps1 roi quay lai."
    }
    & $caiDat -ThuMuc $ThuMuc
    if ($LASTEXITCODE -ne 0) { throw "cai-dat.ps1 that bai. Xem thong bao o tren." }
    if (-not (Test-Path $script:VenvPy)) { throw "cai-dat.ps1 chay xong nhung khong thay $script:VenvPy." }
    ok "nen da san sang"
}

# ---------------------------------------------------------------------------------------------
# B2. Thong so
# ---------------------------------------------------------------------------------------------
function buoc_thong_so() {
    buoc_moi "Thong so cua he thong"
    Write-Host "        Magic number la con so EA dong dau len moi lenh no mo. Hai ben dung chung." -ForegroundColor DarkGray
    $script:Magic       = hoi_so    "Magic number" 770001
    $script:LoginMaster = hoi_so    "So tai khoan Master"
    $script:LoginClient = hoi_so    "So tai khoan Client"
    Write-Host "        Tieu de cua so terminal Client -- clicker tim cua so bang chuoi nay." -ForegroundColor DarkGray
    $script:TieuDe      = hoi_chuoi "Mau tieu de cua so terminal Client" ([string] $script:LoginClient)
    $script:IdMaster    = hoi_chuoi "Ten agent Master"  "AG-MASTER"
    $script:IdClient    = hoi_chuoi "Ten agent Client"  "AG-CLIENT"
    $script:IdClicker   = hoi_chuoi "Ten agent Clicker" "AG-CLICKER"
    $script:IdClientAcc = hoi_chuoi "Ma client"         "CL-01"
    ok "da ghi nhan"
}

# ---------------------------------------------------------------------------------------------
# B3 + B4. Agent va token
# ---------------------------------------------------------------------------------------------
function co_agent([string] $id) {
    $kq = admin @('liet-ke')
    foreach ($d in $kq.ra) {
        if ($d -match ("^" + [regex]::Escape($id) + "\s")) { return $true }
    }
    return $false
}

function tao_agent([string] $id, [string] $vaiTro, [int] $login) {
    if (co_agent $id) { bo_qua "$id da ton tai"; return $null }
    $kq = admin @('them-agent', $id, '--role', $vaiTro, '--magic', "$($script:Magic)",
                  '--login', "$login")
    if ($kq.ma -ne 0) {
        $kq.ra | ForEach-Object { Write-Host "        $_" -ForegroundColor Red }
        throw "them-agent $id that bai."
    }
    $token = tach_token $kq.ra
    if (-not $token) { throw "Tao duoc $id nhung khong doc duoc token tu output." }
    ok "da tao $id ($vaiTro)"
    return $token
}

function buoc_agent() {
    buoc_moi "Tao ba agent"
    if (-not (hoi_co_khong "Tao $($script:IdMaster), $($script:IdClient), $($script:IdClicker)?")) {
        bo_qua "nguoi dung tu choi"; return
    }
    $script:TokenMaster  = tao_agent $script:IdMaster  'MASTER'  $script:LoginMaster
    $script:TokenClient  = tao_agent $script:IdClient  'CLIENT'  $script:LoginClient
    $script:TokenClicker = tao_agent $script:IdClicker 'CLICKER' $script:LoginClient
}

function buoc_token() {
    buoc_moi "Token"

    # Token clicker di thang vao config.toml. Khong in ra man hinh, khong qua dong lenh: dong
    # lenh cua mot tien trinh la thu moi tai khoan tren cung may doc duoc bang
    # `Get-CimInstance Win32_Process`, va clicker chay 24/7.
    if ($script:TokenClicker) {
        dat_khoa_clicker @{
            token          = (nhay $script:TokenClicker)
            account_login  = "$($script:LoginClient)"
            terminal_title = (nhay $script:TieuDe)
        }
        $script:TokenClicker = $null
        ok "token cua $($script:IdClicker) da ghi vao config.toml (khong hien ra man hinh)"
    } else {
        bo_qua "khong co token clicker moi"
    }

    # Hai token con lai BUOC PHAI hien ra: chung duoc go vao tham so EA trong giao dien MT5,
    # khong co duong nao khac.
    if ($script:TokenMaster -or $script:TokenClient) {
        Write-Host ""
        tach
        Write-Host " TOKEN -- CHI HIEN MOT LAN, CHEP NGAY BAY GIO" -ForegroundColor Yellow
        tach
        if ($script:TokenMaster) {
            Write-Host " $($script:IdMaster) (tham so AgentToken cua EA Master):" -ForegroundColor Yellow
            Write-Host "   $($script:TokenMaster)" -ForegroundColor White
        }
        if ($script:TokenClient) {
            Write-Host " $($script:IdClient) (tham so AgentToken cua EA Client):" -ForegroundColor Yellow
            Write-Host "   $($script:TokenClient)" -ForegroundColor White
        }
        tach
        Write-Host ""
        Write-Host "  Da chep hai token vao cho an toan chua? Enter de di tiep " -ForegroundColor Yellow -NoNewline
        [void] (Read-Host)
    } else {
        bo_qua "khong co token moi"
    }
}

# ---------------------------------------------------------------------------------------------
# B5. client_account
# ---------------------------------------------------------------------------------------------
function buoc_client() {
    buoc_moi "Cau hinh client"
    $kq = admin @('cau-hinh-client', $script:IdClientAcc)
    if ($kq.ma -eq 0) {
        bo_qua "$($script:IdClientAcc) da ton tai"
        $kq.ra | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
        return
    }
    if (-not (hoi_co_khong "Tao client $($script:IdClientAcc) (open_route = UI, qua clicker)?")) {
        canh "bo qua -- THIEU DONG NAY LA anh-xa-symbol SE BAO 'Khong co client'"
        return
    }
    $ma = admin_in @('them-client', $script:IdClientAcc, '--agent', $script:IdClient,
                     '--clicker-agent', $script:IdClicker, '--open-route', 'UI')
    if ($ma -ne 0) { throw "them-client that bai." }
    ok "da tao $($script:IdClientAcc)"
}

# ---------------------------------------------------------------------------------------------
# B6. Bien dich EA
# ---------------------------------------------------------------------------------------------
function tim_metaeditor() {
    $ungVien = @(
        (Join-Path $env:ProgramFiles "MetaTrader 5\MetaEditor64.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "MetaTrader 5\MetaEditor64.exe")
    )
    foreach ($u in $ungVien) { if ($u -and (Test-Path $u)) { return $u } }
    $tim = Get-ChildItem $env:ProgramFiles -Filter MetaEditor64.exe -Recurse -ErrorAction SilentlyContinue |
           Select-Object -First 1
    if ($tim) { return $tim.FullName }
    return $null
}

function buoc_bien_dich() {
    buoc_moi "Bien dich EA"
    $me = tim_metaeditor
    if (-not $me) {
        canh "khong thay MetaEditor64.exe -- cai MT5 truoc, roi chay lai script nay."
        return
    }
    if (-not (hoi_co_khong "Bien dich hai EA bang $me ?")) { bo_qua "nguoi dung tu choi"; return }

    $log = Join-Path $ThuMuc "logs\compile.log"
    foreach ($ea in @("CopyBridgeMaster.mq5", "CopyBridgeClient.mq5")) {
        $nguon = Join-Path $ThuMuc "ea\$ea"
        if (-not (Test-Path $nguon)) { canh "khong thay $nguon"; continue }
        # MetaEditor thoat khac 0 khi chi co canh bao, nen su ton tai cua .ex5 moi la bang chung.
        & $me "/compile:$nguon" "/log:$log" | Out-Null
        $ex5 = [IO.Path]::ChangeExtension($nguon, ".ex5")
        if (Test-Path $ex5) { ok "$ea -> $(Split-Path -Leaf $ex5)" }
        else { canh "$ea bien dich khong ra .ex5 -- doc $log" }
    }
}

# ---------------------------------------------------------------------------------------------
# B7 + B8. Gan EA (tay) roi cho no len ONLINE
# ---------------------------------------------------------------------------------------------
function buoc_gan_ea() {
    buoc_moi "Gan EA len chart -- VIEC NAY PHAI LAM BANG TAY"
    Write-Host @"

        Script khong bam ho duoc phan nay. Trong tung terminal MT5:

          1. Chep ea\*.ex5 vao MQL5\Experts cua terminal do
             (File > Open Data Folder trong MT5).
          2. Keo EA len chart: Master len terminal Master, Client len terminal Client.
          3. Dien AgentToken bang token da hien o buoc 4.
             BridgeHost = 127.0.0.1, BridgePort = 8787.
          4. Bat nut Algo Trading tren CA HAI terminal.

        Bien dich lai roi thi PHAI GO EA KHOI CHART ROI GAN LAI. Doi khung thoi gian
        KHONG lam MT5 doc lai .ex5 tu dia.
"@ -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Gan xong ca hai EA chua? Enter de di tiep " -ForegroundColor Yellow -NoNewline
    [void] (Read-Host)
}

function agent_online([string] $id) {
    $kq = admin @('liet-ke')
    foreach ($d in $kq.ra) {
        if ($d -match ("^" + [regex]::Escape($id) + "\s+\S+\s+ONLINE")) { return $true }
    }
    return $false
}

function buoc_cho_ea() {
    buoc_moi "Cho EA ket noi"
    if ((agent_online $script:IdMaster) -and (agent_online $script:IdClient)) {
        bo_qua "ca hai EA da ONLINE"; return $true
    }
    $len = cho_den_khi "$($script:IdMaster) va $($script:IdClient) len ONLINE" {
        (agent_online $script:IdMaster) -and (agent_online $script:IdClient)
    } $GiayChoEA
    if ($len) { ok "ca hai EA da ONLINE"; return $true }

    canh "het gio ma chua thay ca hai EA. Thuong la: dich vu Bridge chua chay, sai token, hoac"
    canh "chua bat Algo Trading. Xem logs\bridge.log."
    [void] (admin_in @('liet-ke'))
    return (hoi_co_khong "Di tiep du chua thay EA? (anh xa symbol se that bai)" $false)
}

# ---------------------------------------------------------------------------------------------
# B9. Anh xa symbol
# ---------------------------------------------------------------------------------------------
function buoc_anh_xa() {
    buoc_moi "Anh xa symbol"
    Write-Host "        THIEU BUOC NAY LA MOI LENH MASTER BI BO QUA trong im lang." -ForegroundColor Yellow
    $kq = admin @('anh-xa-symbol', $script:IdClientAcc)
    if ($kq.ma -eq 0) {
        bo_qua "da co anh xa"
        $kq.ra | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
        if (-not (hoi_co_khong "Them mot anh xa nua?" $false)) { return }
    }

    while ($true) {
        $mS = hoi_chuoi "Symbol phia Master (Enter de dung)" "" $true
        if (-not $mS) { break }
        $cS = hoi_chuoi "Symbol tuong ung phia Client" $mS
        # Lenh nay kiem symbol co that tren san Client truoc khi luu, nen no vua la buoc khai bao
        # vua la buoc nghiem thu.
        $ma = admin_in @('anh-xa-symbol', $script:IdClientAcc, $mS, '--client-symbol', $cS)
        if ($ma -eq 0) { ok "$mS -> $cS" }
        else { canh "khong luu duoc. Kiem EA Client dang chay va symbol da vao Market Watch chua." }
        if (-not (hoi_co_khong "Them anh xa nua?" $false)) { break }
    }
}

# ---------------------------------------------------------------------------------------------
# B10 + B11. Dich vu va kiem tra
# ---------------------------------------------------------------------------------------------
function buoc_dich_vu() {
    buoc_moi "Dang ky dich vu va tac vu"
    if ($BoQuaDichVu) { bo_qua "-BoQuaDichVu"; return }
    if (Get-Service $TenDichVu -ErrorAction SilentlyContinue) {
        bo_qua "dich vu $TenDichVu da dang ky"; return
    }
    $tao = Join-Path $PSScriptRoot "tao-dich-vu.ps1"
    if (-not (Test-Path $tao)) { $tao = Join-Path $ThuMuc "scripts\tao-dich-vu.ps1" }
    if (-not (Test-Path $tao)) { canh "khong thay tao-dich-vu.ps1"; return }
    if (-not (hoi_co_khong "Dang ky dich vu Windows va ba Scheduled Task?")) {
        bo_qua "nguoi dung tu choi"; return
    }
    & $tao -ThuMuc $ThuMuc -TenDichVu $TenDichVu -AccountLogin $script:LoginClient `
           -TerminalTitle $script:TieuDe
    if ($LASTEXITCODE -ne 0) { canh "tao-dich-vu.ps1 tra ve $LASTEXITCODE" }
    else { ok "da dang ky" }
}

function buoc_kiem_tra() {
    buoc_moi "Kiem tra tong the"
    $kt = Join-Path $PSScriptRoot "kiem-tra.ps1"
    if (-not (Test-Path $kt)) { $kt = Join-Path $ThuMuc "scripts\kiem-tra.ps1" }
    if (-not (Test-Path $kt)) { canh "khong thay kiem-tra.ps1"; return }
    if (-not (hoi_co_khong "Chay kiem-tra.ps1?")) { bo_qua "nguoi dung tu choi"; return }
    # -KhongInCanhBao: buoc 12 in khoi canh bao roi, in hai lan thi nguoi ta thoi doc no.
    & $kt -ThuMuc $ThuMuc -TenDichVu $TenDichVu -KhongInCanhBao
    if ($LASTEXITCODE -eq 0) { ok "khong co muc nao hong" }
    else { canh "$LASTEXITCODE muc hong -- doc phan tren" }
}

# ---------------------------------------------------------------------------------------------
# B12. Ket
# ---------------------------------------------------------------------------------------------
function buoc_ket() {
    buoc_moi "Xong"
    Write-Host ""
    tach
    Write-Host " CON DUNG MOT VIEC, VA NO PHAI LAM BANG TAY" -ForegroundColor Yellow
    tach
    Write-Host @"
 Bridge LUON khoi dong o PAUSED, ke ca luc may tu bat lai 3 gio sang. Day la
 chu dich. Dich vu tu bat lai KHONG co nghia la he thong dang copy lenh.

 Bat theo DUNG THU TU BA BUOC:
   1. De backlog trong outbox cua EA chay het vao va duoc ghi nhan IGNORED.
   2. Kiem canary cua clicker XANH tren dashboard http://127.0.0.1:8080
   3. Cho 0 event PENDING, roi moi dat RUNNING:
        .venv\Scripts\python.exe -m bridge.admin run-mode RUNNING

 Moi lan dang nhap VPS:  .\scripts\kiem-tra.ps1
"@
    Write-Host ""
    $canhBao = @(
        (Join-Path $PSScriptRoot "canh-bao.txt"),
        (Join-Path $ThuMuc "scripts\canh-bao.txt")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($canhBao) {
        Get-Content $canhBao | ForEach-Object { Write-Host $_ -ForegroundColor Yellow }
    } else {
        canh "Khong tim thay canh-bao.txt. Doc docs\CAI-DAT-VPS.md muc 8."
    }
}

# ---------------------------------------------------------------------------------------------
try {
    Write-Host ""
    Write-Host " MT5 Copy Bridge -- tro ly cai dat (ban $script:PhienBan)" -ForegroundColor Cyan
    Write-Host " Thu muc: $ThuMuc" -ForegroundColor DarkGray
    Write-Host " Moi buoc deu hoi truoc khi lam. Chay lai bao nhieu lan cung duoc." -ForegroundColor DarkGray

    $script:TokenMaster = $null
    $script:TokenClient = $null
    $script:TokenClicker = $null

    buoc_nen
    buoc_thong_so
    buoc_agent
    buoc_token
    buoc_client
    buoc_bien_dich
    buoc_gan_ea
    # Chua co EA thi anh xa symbol chac chan that bai (`anh-xa-symbol` kiem `symbol_spec` truoc
    # khi luu, ma bang do chi co du lieu khi EA Client dang chay). Bo qua han thay vi bat nguoi
    # dung go symbol vao mot lenh se bao loi.
    if (buoc_cho_ea) {
        buoc_anh_xa
    } else {
        buoc_moi "Anh xa symbol"
        canh "bo qua vi chua co EA. CHAY LAI SCRIPT NAY sau khi gan EA xong --"
        canh "THIEU ANH XA LA MOI LENH MASTER BI BO QUA trong im lang."
    }
    buoc_dich_vu
    buoc_kiem_tra
    buoc_ket
    exit 0
} catch {
    Write-Host ""
    Write-Host " LOI: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    # Token khong nam lai trong bien cua phien PowerShell sau khi script ket thuc.
    $script:TokenMaster = $null
    $script:TokenClient = $null
    $script:TokenClicker = $null
}
