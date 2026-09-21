<#
.SYNOPSIS
    Dung xong he thong bang MOT lenh, roi mo dashboard de nguoi dung tu khai cau hinh.

.DESCRIPTION
    cai-dat.ps1 dung nguoi dung lai o mot khoi "BUOC TIEP THEO" gom nam viec, moi viec vai lenh
    phai go tay, co viec can token vua hien dung mot lan tren man hinh. Sai thu tu hoac bo sot
    mot buoc thi he thong dung xong van khong copy duoc lenh nao -- va hong trong im lang.
    Script nay la mot lenh duy nhat thay cho ca khoi do.

    No DIEU PHOI cac script va lenh da co (cai-dat.ps1, bridge.admin, tao-dich-vu.ps1,
    kiem-tra.ps1) chu khong chep lai viec cua chung. Moi buoc idempotent: chay lai bao nhieu lan
    cung duoc, buoc nao xong roi se in BO QUA.

    KHONG hoi mot cau nao ve NGHIEP VU. Anh xa symbol, chieu copy, he so, duong dong Master --
    tat ca khai tren dashboard (D-32), va khoi "Can lam" o dau tab Cau hinh liet ke chinh xac cai
    gi con thieu. Hoi tren console nhung thu do la bat nguoi ta tra loi mot lan, roi ve sau sua o
    mot cho khac -- hai giao dien cho cung mot viec.

    Cung KHONG in token cua EA ra man hinh. Lay chung tren dashboard: tab Cau hinh > Agent >
    Cap lai token, hien mot lan ngay tren trang. Mot token in ra console la mot token nam trong
    scrollback cua cua so RDP cho toi khi ai do dong no.

    Con dung mot viec phai lam bang tay va no nam trong giao dien MT5: gan EA len chart.

.EXAMPLE
    .\tro-ly.ps1
    Chay tu dau tren C:\CopyBridge.

.EXAMPLE
    .\tro-ly.ps1 -ThuMuc D:\CopyBridge -TuDongDongY
    Khong hoi mot cau nao. Chi dung o mot cho: mat khau tai khoan Windows cho dich vu.
    Day la duong ma cai-dat.ps1 goi.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string] $ThuMuc = "C:\CopyBridge",
    [string] $TenDichVu = "CopyBridge",
    [switch] $TuDongDongY,
    [switch] $BoQuaDichVu,
    # Mo dashboard trong trinh duyet o buoc cuoi. Mac dinh CO: cai xong la sang ngay cho lam viec
    # tiep theo, thay vi bat nguoi ta tu go dia chi va tu doan phai khai gi.
    [switch] $KhongMoDashboard,
    # CHI cho dashboard len roi mo trinh duyet, khong lam gi khac. `cai-dat.ps1 -CapNhat` goi duong
    # nay de dung lai phan cho-cong-web + mo-trinh-duyet, thay vi chep 15 dong sang file kia.
    [switch] $ChiMoDashboard
)

Set-StrictMode -Version Latest
# Cung ly do da giai thich dau cai-dat.ps1: voi 'Stop', MOT dong stderr bat ky tu mot exe bi boc
# thanh NativeCommandError va nem ra ngay, truoc khi script kip doc $LASTEXITCODE.
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }

$script:PhienBan = "2026-09-08"
$script:TongBuoc = 10
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

# Moi buoc va moi cau hoi deu phai tu noi no dung de lam gi. Nguoi van hanh khong doc ma nguon,
# nen mot cau hoi khong kem hau qua cua viec tra loi sai la mot cai bay.
function giai_thich([string[]] $dong) {
    foreach ($d in $dong) { Write-Host "        $d" -ForegroundColor DarkGray }
}

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
    # `$macDinh -or $true` luon la $true, nen -TuDongDongY tu tra loi CO cho ca nhung cau
    # hoi mac dinh KHONG -- ke ca "di tiep du Bridge chua chay?" va "cap lai token?".
    # Tu dong dong y nghia la lay dung mac dinh, khong phai lay dung CO.
    if ($TuDongDongY) { return $macDinh }
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

    # -TuDongDongY phai tra loi CA cau hoi gia tri, khong chi cau hoi co/khong. Truoc ban nay chi
    # `hoi_co_khong` doc cong tac do, nen mot lan chay "khong hoi gi" van dung lai o "Magic
    # number" va cho go tay -- tuc luong cai MOT LENH treo ngay o buoc hai, va treo trong im lang
    # vi con tro nam sau mot dong Write-Host khong xuong dong.
    if ($TuDongDongY) {
        if ($macDinh) {
            # IN ra gia tri da lay: mot lua chon im lang la mot lua chon khong ai kiem lai duoc.
            Write-Host ($nhan + $macDinh + "   (tu dong)") -ForegroundColor DarkGray
            return $macDinh
        }
        if ($choPhepRong) { return "" }
        throw "-TuDongDongY nhung cau hoi '$cauHoi' khong co gia tri mac dinh. Chay lai khong kem -TuDongDongY."
    }

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
function dat_khoa_clicker([hashtable] $khoa, [string] $Muc = "clicker") {
    $cfg = Join-Path $ThuMuc "config.toml"
    if (-not (Test-Path $cfg)) { throw "Khong thay $cfg." }
    $dong = [System.IO.File]::ReadAllLines($cfg)
    $trongMuc = $false
    $daDat = @{}

    for ($i = 0; $i -lt $dong.Count; $i++) {
        $d = $dong[$i].Trim()
        if ($d -match '^\[(.+)\]$') { $trongMuc = ($Matches[1] -eq $Muc); continue }
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
        $dong = @($dong) + @("", "[$Muc]") + @($thieu | ForEach-Object { "$_ = " + $khoa[$_] })
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
    giai_thich @(
        "Cai Python, tao .venv, cai goi, tao config.toml va khoi tao database.",
        "Uy quyen cho cai-dat.ps1. Da lam roi thi bo qua."
    )
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
    # -BoQuaTroLy la BAT BUOC o day, khong phai cho gon: cai-dat.ps1 tu chay tiep tro ly o cuoi
    # duong cai moi (D-36), nen thieu co nay thi hai script goi nhau khong ngung.
    & $caiDat -ThuMuc $ThuMuc -BoQuaTroLy
    if ($LASTEXITCODE -ne 0) { throw "cai-dat.ps1 that bai. Xem thong bao o tren." }
    if (-not (Test-Path $script:VenvPy)) { throw "cai-dat.ps1 chay xong nhung khong thay $script:VenvPy." }
    ok "nen da san sang"
}

# ---------------------------------------------------------------------------------------------
# B2. Thong so
# ---------------------------------------------------------------------------------------------
function buoc_thong_so() {
    buoc_moi "Thong so cua he thong"
    giai_thich @(
        "Hoi mot luot tat ca gia tri ma cac buoc sau can. Enter la lay mac dinh --",
        "gan nhu luon dung, tru khi ban chay hai he thong bot tren cung mot may.",
        "",
        "SO TAI KHOAN MT5 va TIEU DE CUA SO terminal KHONG hoi o day (D-32):",
        "  - EA tu bao so tai khoan cua no luc bat tay dau tien.",
        "  - Clicker nhan so tai khoan va tieu de tu Bridge, va ban khai chung tren",
        "    dashboard sau khi cai xong: http://127.0.0.1:8080 > tab Cau hinh > Agent.",
        "Doi terminal ve sau cung sua o do, khong phai sua config.toml roi dang ky lai tac vu."
    )

    Write-Host ""
    giai_thich @(
        "MAGIC NUMBER -- con so dinh danh he thong bot nay. Ba viec:",
        "  1. Bridge gan no vao moi lenh gui xuong EA; EA tu choi lenh khong khop magic.",
        "     Chay hai he thong bot tren cung mot may thi lenh khong the di nham sang nhau.",
        "  2. EA dong dau len lenh no tu mo. Broker khong sua duoc truong nay, khac voi comment.",
        "  3. Phan biet lenh bot voi lenh mo tay -- chi phia Master.",
        "KHONG loc lenh nao duoc copy: lenh ban mo TAY tren Master van duoc copy sang Client.",
        "",
        "Vi du   : 770001",
        "Cach lay: khong phai tra o dau -- ban tu chon. Cu Enter lay mac dinh.",
        "          Chay he thong bot thu hai tren cung may thi doi so khac, vi du 770002."
    )
    $script:Magic = hoi_so "Magic number" 770001

    # So tai khoan va tieu de cua so KHONG hoi o day nua: chung nam trong database va khai tren
    # dashboard (tab Cau hinh > Agent). EA tu bao so tai khoan cua no luc bat tay dau tien; clicker
    # nhan so tai khoan + tieu de tu Bridge moi lan bat tay. Doi terminal ve sau la sua tren
    # dashboard, khong phai RDP vao sua config.toml roi dang ky lai tac vu.
    $script:LoginMaster = 0
    $script:LoginClient = 0
    $script:TieuDe = ""
    $script:TieuDeMaster = ""

    Write-Host ""
    giai_thich @(
        "TEN AGENT -- nhan dinh danh cua ba tien trinh trong database va tren dashboard.",
        "Chi la ten goi, dat gi cung chay. Cu Enter ca ba.",
        "",
        "Vi du   : AG-MASTER / AG-CLIENT / AG-CLICKER",
        "Cach lay: khong phai tra o dau. Chi doi khi ban chay nhieu cap tren cung mot",
          "          Bridge, luc do dat AG-MASTER-2, AG-CLIENT-2..."
    )
    $script:IdMaster  = hoi_chuoi "Ten agent Master"  "AG-MASTER"
    $script:IdClient  = hoi_chuoi "Ten agent Client"  "AG-CLIENT"
    $script:IdClicker = hoi_chuoi "Ten agent Clicker" "AG-CLICKER"

    Write-Host ""
    giai_thich @(
        "DONG LENH PHIA MASTER QUA GIAO DIEN (D-21c) -- tuy chon, mac dinh KHONG.",
        "Bat khi ben kiem tra nhin CA tai khoan Master: deal DONG tren Master se mang",
        "DEAL_REASON = CLIENT thay vi EXPERT.",
        "Cai gia: them MOT tien trinh clicker nua lai terminal MASTER, va tu do terminal",
        "Master phai LUON mo Toolbox o tab Trade -- y het dieu kien ben Client.",
        "Khong bat thi lenh dong Master di OrderSend cua EA nhu cu.",
        "Token cua clicker nay cung duoc ghi THANG vao config.toml, khong hien ra man hinh.",
        "So tai khoan va tieu de cua so cua ca hai clicker khai tren dashboard sau khi cai xong."
    )
    # Mac dinh CO. Duong nay la ly do phase 12 ton tai: deal dong phia Master mang
    # "Placed by manual" thay vi dau vet cua EA. Tat no la mot lua chon, va lua chon do sua duoc
    # tren dashboard (khoi Duong dong phia Master) -- con BAT no ve sau thi phai dang ky them mot
    # Scheduled Task tren VPS, tuc dung cai ma sat luong cai mot lenh vua bo di.
    #
    # An toan khi chua khai xong: clicker Master chua san sang thi duong dong ROI VE EA kem alert
    # (D-28), khong phai khong dong duoc.
    $script:BatDongMaster = hoi_co_khong "Bat duong DONG phia Master qua giao dien?" $true
    if ($script:BatDongMaster) {
        $script:IdClickerMaster = hoi_chuoi "Ten agent Clicker Master" "AG-CLICKER-MASTER"
    }

    Write-Host ""
    giai_thich @(
        "MA CLIENT -- ma cua dong cau hinh NGHIEP VU phia Client: copy nguoc hay cung chieu, he",
        "so volume, duong mo lenh. Khac voi ten agent (la ket noi). Ban se go lai ma nay trong",
        "cac lenh anh-xa-symbol va cau-hinh-client. Cu Enter.",
        "",
        "Vi du   : CL-01",
        "Cach lay: khong phai tra o dau. Nhieu Client thi CL-02, CL-03..."
    )
    $script:IdClientAcc = hoi_chuoi "Ma client" "CL-01"
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

function cap_lai_token([string] $id) {
    $kq = admin @('cap-token', $id)
    if ($kq.ma -ne 0) {
        $kq.ra | ForEach-Object { Write-Host "        $_" -ForegroundColor Red }
        throw "cap-token $id that bai."
    }
    $token = tach_token $kq.ra
    if (-not $token) { throw "Cap lai token cho $id nhung khong doc duoc token tu output." }
    ok "da cap token MOI cho $id -- token cu vua het hieu luc"
    return $token
}

function tao_agent([string] $id, [string] $vaiTro, [int] $login) {
    if (co_agent $id) {
        bo_qua "$id da ton tai"
        # Token tho chi hien dung MOT lan luc tao. Ai chay lai tro ly vi da mat token thi
        # truoc day roi vao ngo cut: buoc nay im lang BO QUA, buoc Token in "khong co token
        # moi", va khong cho nao noi cho ho biet duong ra. Nay hoi thang.
        # Mac dinh KHONG, vi cap lai la giet token dang nam trong EA dang chay.
        if (hoi_co_khong "  $id da co roi. Cap LAI token? (chi khi ban da mat token cu; EA dang chay se rot cho toi khi go token moi)" $false) {
            return (cap_lai_token $id)
        }
        return $null
    }
    # KHONG truyen --login: de trong thi cot `account_login` la NULL, va Bridge gan no o lan bat
    # tay dau tien bang chinh so tai khoan EA bao len. Dien tay o day chi them mot cho go nham ma
    # trieu chung (EA khong bao gio len ONLINE) nhin y het sai token.
    $doiSo = @('them-agent', $id, '--role', $vaiTro, '--magic', "$($script:Magic)")
    if ($login -gt 0) { $doiSo += @('--login', "$login") }
    $kq = admin $doiSo
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
    giai_thich @(
        "Moi tien trinh noi vao Bridge can mot danh tinh rieng va mot token rieng:",
        "  MASTER  -- EA tren terminal Master, bao cao lenh ban mo",
        "  CLIENT  -- EA tren terminal Client, dong lenh va bao cao trang thai",
        "  CLICKER -- tien trinh bam giao dien MT5 de MO lenh phia Client",
        "Agent da ton tai thi BO QUA. Luc do no hoi ban co muon cap LAI token khong --",
        "mac dinh la KHONG, vi cap lai se giet token dang nam trong EA dang chay.",
        "Chi tra loi CO khi ban da mat token cu va phai go lai vao MT5."
    )
    if (-not (hoi_co_khong "Tao $($script:IdMaster), $($script:IdClient), $($script:IdClicker)?")) {
        bo_qua "nguoi dung tu choi"; return
    }
    $script:TokenMaster  = tao_agent $script:IdMaster  'MASTER'  $script:LoginMaster
    $script:TokenClient  = tao_agent $script:IdClient  'CLIENT'  $script:LoginClient
    $script:TokenClicker = tao_agent $script:IdClicker 'CLICKER' $script:LoginClient
    # Clicker thu hai lai terminal MASTER. Danh tinh rieng la bat buoc chu khong phai thu tuc:
    # Bridge tim agent BANG token, va `server.connections[agent_id]` chi giu mot ket noi -- dung
    # chung token thi clicker vao sau thay cho clicker vao truoc, va mot lenh dong danh cho Client
    # se duoc bam tren terminal Master.
    if ($script:BatDongMaster) {
        $script:TokenClickerMaster = tao_agent $script:IdClickerMaster 'CLICKER' `
                                               $script:LoginMaster
        canh ("Clicker Master chua lai duoc terminal nao cho toi khi ban khai so tai khoan va " +
              "tieu de cua so cho $($script:IdClickerMaster) tren dashboard.")
    }
}

function buoc_token() {
    buoc_moi "Token"
    giai_thich @(
        "Token cua CLICKER duoc ghi THANG vao config.toml, khong hien ra man hinh.",
        "Token cua EA thi LAY TREN DASHBOARD: tab Cau hinh > Agent > Cap lai token.",
        "Khong in ra day: mot token in ra console la mot token nam trong scrollback cua cua so",
        "RDP cho toi khi ai do dong no, va con nam trong lich su cuon cua Terminal."
    )

    # Token clicker di thang vao config.toml. Khong in ra man hinh, khong qua dong lenh: dong
    # lenh cua mot tien trinh la thu moi tai khoan tren cung may doc duoc bang
    # `Get-CimInstance Win32_Process`, va clicker chay 24/7.
    # CHI ghi token. So tai khoan va tieu de cua so nam trong database (khai tren dashboard) va
    # clicker nhan chung tu Bridge -- ghi chung o day nua la tao mot nguon su that thu hai, ma
    # `config.toml` lai la nguon THANG, nen sua tren dashboard se khong co tac dung.
    if ($script:TokenClicker) {
        dat_khoa_clicker @{
            token = (nhay $script:TokenClicker)
        }
        $script:TokenClicker = $null
        ok "token cua $($script:IdClicker) da ghi vao config.toml (khong hien ra man hinh)"
    } else {
        bo_qua "khong co token clicker moi"
    }

    if ($script:TokenClickerMaster) {
        dat_khoa_clicker @{
            token = (nhay $script:TokenClickerMaster)
        } "clicker_master"
        $script:TokenClickerMaster = $null
        ok "token cua $($script:IdClickerMaster) da ghi vao config.toml (khong hien ra man hinh)"
    }

    # Token cua EA KHONG in ra day. Token vua sinh luc tao agent bi bo di, va nguoi dung lay mot
    # token moi tren dashboard (Agent > Cap lai token) roi dan vao EA. Doi mot token la viec binh
    # thuong: EA dang chay se rot cho toi khi go token moi, ma o day chua co EA nao chay.
    if ($script:TokenMaster -or $script:TokenClient) {
        $script:TokenMaster = $null
        $script:TokenClient = $null
        ok "da tao agent cho EA -- lay token tren dashboard (tab Cau hinh > Agent > Cap lai token)"
    } else {
        bo_qua "khong co agent EA moi"
    }
}

# ---------------------------------------------------------------------------------------------
# B5. client_account
# ---------------------------------------------------------------------------------------------
function buoc_client() {
    buoc_moi "Cau hinh client"
    giai_thich @(
        "Tao dong cau hinh nghiep vu phia Client: copy nguoc hay cung chieu, he so volume,",
        "va duong mo lenh va dong lenh (UI = qua giao dien MT5, can clicker).",
        "Ca MO lan DONG deu di UI de deal phia Client mang DEAL_REASON = CLIENT (D-21, D-21b).",
        "THIEU DONG NAY thi buoc anh xa symbol se bao `"Khong co client`" va khong di tiep duoc."
    )
    $kq = admin @('cau-hinh-client', $script:IdClientAcc)
    if ($kq.ma -eq 0) {
        bo_qua "$($script:IdClientAcc) da ton tai"
        $kq.ra | ForEach-Object { Write-Host "        $_" -ForegroundColor DarkGray }
        # Ban cai cu nang cap qua migration 004 giu close_route = EA (nang cap khong tu doi hanh
        # vi). Buoc nay bo qua client da co, nen neu khong noi ra o day thi khong ai biet la duong
        # DONG van dang di qua EA.
        if (($kq.ra -join ' ') -match 'close_route=EA') {
            canh ("close_route = EA: lenh DONG phia Client van di qua OrderSend cua EA, deal dong " +
                  "se mang DEAL_REASON = EXPERT. Bat duong giao dien bang: " +
                  "bridge.admin cau-hinh-client $($script:IdClientAcc) --close-route UI")
        }
        return
    }
    if (-not (hoi_co_khong "Tao client $($script:IdClientAcc) (open_route = UI va close_route = UI, qua clicker)?")) {
        canh "bo qua -- THIEU DONG NAY LA anh-xa-symbol SE BAO 'Khong co client'"
        return
    }
    $ma = admin_in @('them-client', $script:IdClientAcc, '--agent', $script:IdClient,
                     '--clicker-agent', $script:IdClicker, '--open-route', 'UI',
                     '--close-route', 'UI')
    if ($ma -ne 0) { throw "them-client that bai." }
    ok "da tao $($script:IdClientAcc)"
}

# ---------------------------------------------------------------------------------------------
# B6. Duong DONG phia Master
# ---------------------------------------------------------------------------------------------
function buoc_dong_master() {
    buoc_moi "Duong DONG phia Master"
    if (-not $script:BatDongMaster) {
        bo_qua "khong bat -- lenh dong Master di OrderSend cua EA nhu cu"
        return
    }
    giai_thich @(
        "Bat `master_close_route = UI`: lenh dong vi the Master di qua giao dien, do clicker",
        "thu hai bam. Deal dong tren Master se mang DEAL_REASON = CLIENT.",
        "Clicker hong thi lenh VAN roi ve OrderSend cua EA kem alert CRITICAL -- khong dong",
        "duoc thi khong an toan, nen o day co duong lui (D-28)."
    )
    $ma = admin_in @('cau-hinh-master', '--clicker-agent', $script:IdClickerMaster,
                     '--close-route', 'UI')
    if ($ma -ne 0) { canh "cau-hinh-master tra ve $ma"; return }
    ok "master_close_route = UI, clicker $($script:IdClickerMaster)"
    canh "Terminal MASTER tu nay phai LUON mo Toolbox o tab Trade, y het terminal Client."
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
    giai_thich @(
        "Bien dich ea\*.mq5 thanh .ex5 bang MetaEditor, khong can mo giao dien.",
        "Chua cai MT5 thi bo qua buoc nay, cai xong chay lai script."
    )
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
# Hoi chinh Bridge xem no dang nghe cong nao, khong tu parse TOML trong PowerShell -- giong het
# cach `doc_cau_hinh` cua kiem-tra.ps1 lam.
function cong_theo_khoa([string] $khoa) {
    # Hoi chinh Bridge, khong tu parse TOML trong PowerShell.
    #
    # KHONG duoc nem: ham nay chi phuc vu buoc mo trinh duyet o cuoi, va mot lan cai dat da xong
    # khong duoc that bai vi khong doc noi mot so cong. Thieu .venv thi `&` nem
    # CommandNotFoundException -- mot loi TERMINATING ma $ErrorActionPreference khong chan.
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

function cong_bridge()  { return (cong_theo_khoa "port") }
function cong_web()     { return (cong_theo_khoa "web_port") }

function dang_nghe([int] $cong) {
    return $null -ne (Get-NetTCPConnection -State Listen -LocalPort $cong -ErrorAction SilentlyContinue)
}

# Cho dashboard len TRUOC khi mo trinh duyet. Mo som thi trinh duyet bao "khong ket noi duoc" va
# nguoi dung ket luan la ban cai hong, trong khi dich vu chi dang khoi dong.
function cho_dashboard([int] $cong, [int] $giay = 30) {
    $han = (Get-Date).AddSeconds($giay)
    while ((Get-Date) -lt $han) {
        if (dang_nghe $cong) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

# ---------------------------------------------------------------------------------------------
# B10 + B11. Dich vu va kiem tra
# ---------------------------------------------------------------------------------------------
function buoc_dich_vu() {
    buoc_moi "Dang ky dich vu va tac vu"
    giai_thich @(
        "Dang ky Windows Service cho Bridge va cac Scheduled Task (clicker, clicker Master",
        "neu bat duong dong Master, bao tri, tinh hinh).",
        "DAY LA THU KHOI DONG BRIDGE. Phai xong truoc khi gan EA, vi EA gan len chart khi chua",
        "ai nghe cong 8787 se khong bao gio len ONLINE.",
        "Se hoi mat khau tai khoan autologon. Bo trong thi dich vu chay bang LocalSystem."
    )
    if ($BoQuaDichVu) { bo_qua "-BoQuaDichVu"; return }
    if (Get-Service $TenDichVu -ErrorAction SilentlyContinue) {
        # Dich vu da co KHONG co nghia la moi tac vu da co. Ban cai dang chay ma bat duong dong Master
        # ve sau thi tac vu ClickerMaster chua bao gio duoc dang ky: truoc 2026-09-15 buoc nay return
        # ngay o day, route UI da bat ma khong co clicker nao, lenh dong Master roi ve EA.
        $coTacVu = Get-ScheduledTask -TaskPath '\CopyBridge\' -TaskName 'ClickerMaster' `
                                     -ErrorAction SilentlyContinue
        if ($script:BatDongMaster -and -not $coTacVu) {
            $tao = Join-Path $PSScriptRoot "tao-dich-vu.ps1"
            if (-not (Test-Path $tao)) { $tao = Join-Path $ThuMuc "scripts\tao-dich-vu.ps1" }
            if (-not (Test-Path $tao)) { canh "khong thay tao-dich-vu.ps1"; return }
            & $tao -ThuMuc $ThuMuc -TenDichVu $TenDichVu -ChiTacVuClicker
            if ($LASTEXITCODE -ne 0) { canh "dang ky tac vu ClickerMaster that bai ($LASTEXITCODE)"; return }
            Start-ScheduledTask -TaskPath '\CopyBridge\' -TaskName 'ClickerMaster'
            ok "da dang ky va bat tac vu ClickerMaster (dich vu $TenDichVu giu nguyen)"
            return
        }
        bo_qua "dich vu $TenDichVu da dang ky"; return
    }
    $tao = Join-Path $PSScriptRoot "tao-dich-vu.ps1"
    if (-not (Test-Path $tao)) { $tao = Join-Path $ThuMuc "scripts\tao-dich-vu.ps1" }
    if (-not (Test-Path $tao)) { canh "khong thay tao-dich-vu.ps1"; return }
    if (-not (hoi_co_khong "Dang ky dich vu Windows va cac Scheduled Task?")) {
        bo_qua "nguoi dung tu choi"; return
    }
    # Tac vu chi mang -Muc: so tai khoan va tieu de cua so nam trong DB. Doi terminal ve sau khong
    # phai dang ky lai tac vu. Nhung VIEC CO dang ky tac vu ClickerMaster hay khong thi van phai
    # noi ro o day, neu khong khong ai dang ky no ca.
    # PHAI la HASHTABLE. Splat mot MANG thi PowerShell truyen cac phan tu theo VI TRI, khong
    # phai theo ten: `@('-TacVuClicker', 'clicker_master')` lam "-TacVuClicker" roi vao $NguoiDung
    # va "clicker_master" roi vao $AccountLogin (kieu int) -- gay ca buoc dang ky dich vu.
    #
    # Ban truoc con te hon vi no IM LANG: `@('-TacVuClickerMaster')` chi co mot phan tu, no bind
    # gon vao $NguoiDung nhu mot chuoi binh thuong, va tac vu ClickerMaster khong bao gio duoc
    # dang ky -- khong mot dong loi nao. Do la ly do tao-dich-vu.ps1 nay dat PositionalBinding=$false.
    $doiSoMaster = @{}
    if ($script:BatDongMaster) { $doiSoMaster = @{ TacVuClicker = @('clicker_master') } }
    & $tao -ThuMuc $ThuMuc -TenDichVu $TenDichVu @doiSoMaster
    if ($LASTEXITCODE -ne 0) { canh "tao-dich-vu.ps1 tra ve $LASTEXITCODE" }
    else { ok "da dang ky" }
}

function buoc_kiem_tra() {
    buoc_moi "Kiem tra tong the"
    giai_thich @(
        "Chay kiem-tra.ps1: chin muc, ma thoat bang so muc hong.",
        "Day la lenh ban se chay moi lan dang nhap VPS ve sau."
    )
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
    buoc_moi "Xong -- con ba viec, lam het tren trinh duyet va trong MT5"

    $congWeb = cong_web
    if ($null -eq $congWeb) { $congWeb = 8080 }
    # Mo thang tab Huong dan, khong phai trang chu: danh sach viec tung buoc nam o do, va no tu
    # biet buoc nao da xong. Mo trang chu roi de nguoi dung tu tim ra tab la bo lai dung cai kho.
    $diaChi = "http://127.0.0.1:$congWeb/#huong-dan"

    Write-Host ""
    tach
    Write-Host " HE THONG DA DUNG XONG. CON BA VIEC, VA CHUNG NAM O HAI CHO:" -ForegroundColor Yellow
    tach
    Write-Host @"

  Tren dashboard ($diaChi -- tab Cau hinh):

    1. Khoi Agent > Cap lai token cho AG-MASTER va AG-CLIENT. Token hien MOT LAN
       ngay tren trang; dan vao tham so AgentToken cua EA tuong ung.
    2. Khoi Agent > khai SO TAI KHOAN va TIEU DE CUA SO cho tung clicker.
       Tieu de phai chua so tai khoan: do la thu clicker doi chieu truoc MOI cu bam.
    3. Khoi Anh xa symbol > khai symbol Master ung voi symbol nao ben Client.

  Trong MT5 (viec duy nhat khong tu dong hoa duoc):

    - Chep ea\*.ex5 vao MQL5\Experts cua tung terminal (File > Open Data Folder),
      keo EA len DUNG MOT chart, dien AgentToken vua lay, BridgeHost = 127.0.0.1,
      BridgePort = $(cong_bridge).
    - Bat nut Algo Trading, va mo Toolbox (Ctrl+T) o tab Trade.

  Trinh duyet vua mo tab HUONG DAN: ba viec tren nam trong danh sach "Cai dat lan
  dau", theo dung thu tu, va moi buoc tu biet da xong chua. Buoc nao dashboard khong
  thay duoc (gan EA len chart, mo Toolbox) thi co o de ban tu tich.
  Con buoc nao chua xong thi he thong KHONG copy duoc lenh nao.

  Moi lan dang nhap VPS:  $ThuMuc\scripts\kiem-tra.ps1

"@ -ForegroundColor Gray

    $canhBao = @(
        (Join-Path $PSScriptRoot "canh-bao.txt"),
        (Join-Path $ThuMuc "scripts\canh-bao.txt")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($canhBao) {
        Get-Content $canhBao | ForEach-Object { Write-Host $_ -ForegroundColor Yellow }
    } else {
        canh "Khong tim thay canh-bao.txt. Doc docs\CAI-DAT-VPS.md muc 'Nhung gi script KHONG lam duoc'."
    }

    if ($KhongMoDashboard) { bo_qua "-KhongMoDashboard: tu mo $diaChi"; return }
    Write-Host ""
    mo_dashboard
}

function mo_dashboard() {
    $congWeb = cong_web
    if ($null -eq $congWeb) { $congWeb = 8080 }
    $diaChi = "http://127.0.0.1:$congWeb/#huong-dan"

    if (-not (cho_dashboard $congWeb)) {
        canh "dashboard chua nghe cong $congWeb sau 30 giay. Xem logs\service-err.log, roi mo $diaChi bang tay."
        return
    }
    # Start-Process voi mot URL: Windows mo no bang trinh duyet mac dinh. Mot lan that bai (may
    # khong co trinh duyet mac dinh) khong duoc lam ca lan cai dat that bai theo.
    try {
        Start-Process $diaChi
        ok "da mo $diaChi trong trinh duyet"
    } catch {
        canh "khong mo duoc trinh duyet ($($_.Exception.Message)). Mo tay: $diaChi"
    }
}

# ---------------------------------------------------------------------------------------------
try {
    Write-Host ""
    Write-Host " MT5 Copy Bridge -- tro ly cai dat (ban $script:PhienBan)" -ForegroundColor Cyan
    Write-Host " Thu muc: $ThuMuc" -ForegroundColor DarkGray
    Write-Host " Khong hoi gi ve nghiep vu -- phan do khai tren dashboard. Chay lai duoc nhieu lan." -ForegroundColor DarkGray

    $script:VenvPy = Join-Path $ThuMuc ".venv\Scripts\python.exe"
    if ($ChiMoDashboard) {
        # Khong chay buoc nao ca: he thong da dung xong tu truoc, day chi la cu mo trinh duyet.
        mo_dashboard
        exit 0
    }

    $script:TokenMaster = $null
    $script:TokenClient = $null
    $script:TokenClicker = $null
    $script:TokenClickerMaster = $null
    $script:BatDongMaster = $false

    buoc_nen
    buoc_thong_so
    buoc_agent
    buoc_token
    buoc_client
    buoc_dong_master
    # Dang ky dich vu PHAI di truoc phan EA. `tao-dich-vu.ps1` la thu duy nhat khoi dong Bridge
    # (`cai-dat.ps1` chi Start-Service khi -CapNhat), nen neu de buoc nay xuong duoi thi EA gan
    # xong se goi vao mot cong khong ai nghe, buoc cho ONLINE luon het gio, va anh xa symbol luon
    # bi bo qua -- dung cai hố khien moi lenh Master bi bo qua trong im lang.
    buoc_dich_vu
    buoc_bien_dich
    # KHONG cho EA, KHONG hoi anh xa symbol. Ca hai deu can EA da gan xong -- viec phai lam trong
    # giao dien MT5 -- nen hoi o day la dung script lai hang phut de cho mot viec no khong lam
    # duoc. Anh xa symbol khai tren dashboard (D-32), va khoi "Can lam" o dau tab Cau hinh la thu
    # nhac rang no con thieu.
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
    $script:TokenClickerMaster = $null
}
