<#
.SYNOPSIS
    Cai dat MT5 Copy Bridge len mot may Windows. Chay lai duoc bao nhieu lan cung duoc.

.DESCRIPTION
    Moi buoc deu idempotent, nen chinh script nay cung la bo cap nhat: them -CapNhat thi no
    sao luu database, dung dich vu, git pull, cai lai goi, roi bat dich vu len.

    Script KHONG cai MetaTrader 5, KHONG bien dich EA, KHONG bam RUNNING ho ban. Ly do nam o
    khoi canh bao in ra cuoi cung.

.EXAMPLE
    .\cai-dat.ps1
    Cai lan dau vao C:\CopyBridge, clone tu GitHub.

.EXAMPLE
    .\cai-dat.ps1 -ThuMuc D:\CopyBridge -BoQuaGit
    Dung thu muc da co san (duong keo folder qua RDP), khong dung toi git.

.EXAMPLE
    .\cai-dat.ps1 -CapNhat
    Sao luu, dung dich vu, keo ban moi, cai lai, bat dich vu.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string] $ThuMuc = "C:\CopyBridge",
    [string] $Repo   = "https://github.com/taducloc0603/copy-trade.git",
    [string] $Nhanh  = "main",
    [string] $TenDichVu = "CopyBridge",
    # Ghim phien ban cu the, giong cach tao-dich-vu.ps1 ghim nssm-2.24.zip. Ghi de duoc khi VPS
    # di qua proxy noi bo hoac ban muon ban khac.
    [string] $UrlPython = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe",
    [string] $UrlGit    = "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe",
    [switch] $CapNhat,
    [switch] $BoQuaGit,
    [switch] $LamMoiVenv,
    [switch] $BoQuaTest,
    # Bo test khong duoc phep chay vo han: mot test TREO thi lan cai ket cung, khong bao
    # gio tu thoat, va nguoi cai khong phan biet duoc "dang chay" voi "da treo".
    [int] $GiayChoTest = 900,
    [switch] $KhongCaiPython,
    # Dung lai sau khi dung nen, in khoi "BUOC TIEP THEO" nhu truoc thay vi tu chay tro ly.
    # Dung khi ban muon lam tung buoc bang tay, hoac khi may nay chi dung de dung ma nguon.
    [switch] $BoQuaTroLy
)

Set-StrictMode -Version Latest
# PowerShell 5.1: voi 'Stop', MOT DONG stderr bat ky tu mot exe -- pip in "notice: A new release
# of pip", git in tien do fetch -- bi boc thanh NativeCommandError va nem ra NGAY, truoc khi
# script kip doc $LASTEXITCODE. Nghia la thong bao loi tu te ben duoi khong bao gio hien ra, con
# nguoi cai thi nhan mot traceback khong lien quan. Moi lenh native trong file nay deu duoc kiem
# bang $LASTEXITCODE tuong minh, con cmdlet nao that bai la hong that thi ghi -ErrorAction Stop
# tai cho.
$ErrorActionPreference = 'Continue'
# Output cua `python -m bridge.admin` co tieng Viet co dau o phan nhan giao dien. Khong dat
# dong nay thi no ra ky tu rac trong console dung code page he thong.
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }

$script:TongBuoc = 13
# Ghi cung trong file chu khong hoi git: tinh huong hong that la mot ban cai-dat.ps1 chep ra
# Desktop cua VPS, nam ngoai moi kho git, bao mot loi da duoc sua tu lau. In so nay ra banner de
# nguoi van hanh doc mot dong la biet minh dang chay ban nao. DOI SO NAY MOI LAN SUA SCRIPT.
$script:PhienBan = "2026-09-22"

# So sanh khoa giua config.toml va config.example.toml. Viet bang Python chu khong phai
# PowerShell vi PS 5.1 khong co bo doc TOML nao, va tomllib thi da nam san trong venv.
$script:MaSoSanhKhoa = @'
import tomllib
def khoa(p):
    with open(p, 'rb') as fh:
        d = tomllib.load(fh)
    return {muc + '.' + k for muc, gt in d.items() if isinstance(gt, dict) for k in gt}
thieu = sorted(khoa('config.example.toml') - khoa('config.toml'))
print(', '.join(thieu))
'@
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

function la_admin() {
    $than = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($than)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function nap_lai_path() {
    # winget cap nhat PATH trong registry chu khong trong tien trinh dang chay. Khong nap lai
    # thi ngay sau khi cai xong Python van "khong tim thay python".
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
}

function tai_va_cai([string] $ten, [string] $url, [string[]] $thamSo) {
    # Windows Server khong co winget, va cai winget len Server lai phai tai tay chinh App
    # Installer cong may goi VCLibs phu thuoc -- phien hon la tai thang bo cai ngay o day.
    $tam = Join-Path $env:TEMP ([IO.Path]::GetFileName(([Uri] $url).AbsolutePath))
    canh "Dang tai $ten tu $url"
    try {
        # TLS 1.2 phai bat tuong minh: PowerShell 5.1 mac dinh dung SSL3/TLS1, bi tu choi.
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        # -UseBasicParsing la bat buoc: Server Core va IE Enhanced Security khong co engine IE.
        Invoke-WebRequest $url -OutFile $tam -UseBasicParsing -ErrorAction Stop
    } catch {
        throw ("Tai bo cai $ten that bai ($($_.Exception.Message)). VPS co the dang chan mang ra " +
               "ngoai. Tai tay tai $url , chay no, roi chay lai script.")
    }
    canh "Dang cai $ten (vai phut, khong co cua so nao hien ra)"
    $tt = Start-Process $tam -Wait -PassThru -ArgumentList $thamSo
    if ($tt.ExitCode -ne 0) {
        throw "Bo cai $ten ket thuc voi ma $($tt.ExitCode). Chay tay $tam de xem no bao gi."
    }
    nap_lai_path
}

function phien_ban_python([string] $exe, [string[]] $tienTo) {
    try {
        $ra = & $exe @tienTo -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return [version] ("$ra".Trim())
    } catch { return $null }
}

function tim_python() {
    # Thu tu co chu dich: `py -3.12` truoc `python` vi tren Windows `python` thuong la cai stub
    # cua Microsoft Store, chay ra mot cua so Store thay vi mot trinh thong dich.
    $ungVien = @(
        @{ exe = 'py';     args = @('-3.12') },
        @{ exe = 'py';     args = @('-3.11') },
        @{ exe = 'py';     args = @('-3')    },
        @{ exe = 'python'; args = @()        }
    )
    foreach ($uv in $ungVien) {
        if (-not (Get-Command $uv.exe -ErrorAction SilentlyContinue)) { continue }
        $pb = phien_ban_python $uv.exe $uv.args
        if ($null -ne $pb -and $pb -ge [version]'3.11') {
            return @{ exe = $uv.exe; args = $uv.args; pb = $pb }
        }
    }
    return $null
}

# ---------------------------------------------------------------------------------------------
# B1. Python >= 3.11
# ---------------------------------------------------------------------------------------------
function bao_dam_python() {
    buoc_moi "Kiem tra Python 3.11 tro len"
    $py = tim_python
    if ($null -ne $py) { ok ("Python " + $py.pb); return $py }

    if ($KhongCaiPython) { throw "Khong tim thay Python >= 3.11 va da chi dinh -KhongCaiPython." }
    # Kiem quyen truoc CA HAI duong cai, khong rieng winget: bo cai tu python.org voi
    # InstallAllUsers=1 cung ghi vao C:\Program Files.
    if (-not (la_admin)) {
        throw "Cai Python can quyen Administrator. Mo lai PowerShell bang 'Run as administrator'."
    }
    if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        throw ("May nay la ARM64 nhung -UrlPython mac dinh tro toi ban amd64. Lay link ban ARM64 " +
               "o https://www.python.org/downloads/windows/ roi chay lai voi -UrlPython <link>.")
    }

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        canh "Chua co Python, dang cai bang winget (vai phut)"
        # Out-Host chu khong de tran: ham nay TRA VE $py, ma trong PowerShell gia tri tra
        # ve la MOI thu ghi ra output stream -- ke ca stdout cua winget. De tran thi $py
        # thanh mang va `$py.exe` o bao_dam_venv im lang thanh rong.
        winget install --id Python.Python.3.12 --exact --scope machine --silent `
            --accept-package-agreements --accept-source-agreements | Out-Host
        nap_lai_path
        $py = tim_python
    }
    if ($null -eq $py) {
        # Khong co winget (Windows Server hau nhu luon vay), hoac co ma cai khong xong.
        tai_va_cai "Python 3.12" $UrlPython @('/quiet', 'InstallAllUsers=1', 'PrependPath=1', 'Include_test=0')
        $py = tim_python
    }
    if ($null -eq $py) {
        throw "Cai Python xong nhung van khong goi duoc. Dong PowerShell, mo lai, roi chay lai script."
    }
    ok ("da cai Python " + $py.pb)
    return $py
}

# ---------------------------------------------------------------------------------------------
# B2. git
# ---------------------------------------------------------------------------------------------
function bao_dam_git() {
    buoc_moi "Kiem tra git"
    if ($BoQuaGit) { bo_qua "-BoQuaGit"; return $false }
    if (Get-Command git -ErrorAction SilentlyContinue) { ok ((git --version) -join ''); return $true }
    # Tu day tro xuong la PHAI CAI. Danh dau lai: chi khi vua cai thi cac cua so PowerShell mo tu
    # TRUOC do moi khong thay git, va chi khi do moi can canh bao o cuoi.
    $script:VuaCaiGit = $true

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        canh "Chua co git, dang cai bang winget"
        winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements | Out-Host
        nap_lai_path
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        # Thieu git KHONG chi mang -- van con duong '-BoQuaGit / dung thu muc san co'. Nen nuot
        # loi cua tai_va_cai o day thay vi de no bay len khoi catch cuoi file va giet ca ban cai.
        try {
            tai_va_cai "Git for Windows" $UrlGit @('/VERYSILENT', '/NORESTART', '/NOCANCEL', '/SP-')
        } catch {
            canh $_.Exception.Message
        }
    }
    if (Get-Command git -ErrorAction SilentlyContinue) { ok ((git --version) -join ''); return $true }
    canh "Khong cai duoc git. Chuyen sang dung thu muc san co."
    return $false
}

# ---------------------------------------------------------------------------------------------
# Chot chan: khong cai de len mot ban dang chay
# ---------------------------------------------------------------------------------------------
function chan_cai_de_len_ban_dang_chay() {
    # Chay thuong (khong -CapNhat) tren ban cai DANG CHAY van git pull va van chay migration (qua
    # `bridge.admin liet-ke`), nhung bo qua sao luu, khong dung dich vu va khong nap lai gi: code
    # moi tren dia, code cu trong bo nho, migration chay ngay duoi mot Bridge dang RUNNING, khong
    # co ban sao luu ngay truoc do. Da xay ra that tren VPS 2026-09-11, va kiem-tra.ps1 van xanh
    # gan het. tro-ly.ps1 chi goi script nay khi chua co .venv + config.toml nen khong vuong chot.
    if ($CapNhat) { return }
    $dv = Get-Service $TenDichVu -ErrorAction SilentlyContinue
    if ($null -ne $dv -and $dv.Status -eq 'Running') {
        throw ("Dich vu $TenDichVu dang chay -- day la ban cai dang hoat dong. Chay lai voi -CapNhat " +
               "(sao luu, dung dich vu, cap nhat, nap lai clicker, bat lai dich vu).")
    }
}

# ---------------------------------------------------------------------------------------------
# B3. Sao luu + dung dich vu (chi khi -CapNhat)
# ---------------------------------------------------------------------------------------------
function truoc_khi_cap_nhat([string] $venvPy) {
    buoc_moi "Sao luu database va dung dich vu"
    if (-not $CapNhat) { bo_qua "khong phai -CapNhat"; return $null }

    if (Test-Path $venvPy) {
        # `sao-luu` dung VACUUM INTO nen an toan voi WAL va chay duoc ca khi dich vu dang chay.
        # Sao luu TRUOC khi dung dich vu: neu buoc dung hong thi van con mot ban sao.
        Push-Location $ThuMuc
        try {
            & $venvPy -m bridge.admin sao-luu | Out-Host
            if ($LASTEXITCODE -ne 0) { throw "sao-luu that bai, DUNG cap nhat." }
        } finally { Pop-Location }
        ok "da sao luu"
    } else {
        canh "chua co venv, bo qua sao luu"
    }

    $commitCu = ""
    if (Test-Path (Join-Path $ThuMuc ".git")) {
        $commitCu = (git -C $ThuMuc rev-parse HEAD).Trim()
        ok "commit hien tai $commitCu"
    }

    $dv = Get-Service $TenDichVu -ErrorAction SilentlyContinue
    if ($null -ne $dv -and $dv.Status -eq 'Running') {
        Stop-Service $TenDichVu
        ok "da dung dich vu $TenDichVu"
    } else {
        bo_qua "dich vu chua chay"
    }
    return $commitCu
}

# ---------------------------------------------------------------------------------------------
# B4. Ma nguon
# ---------------------------------------------------------------------------------------------
# Tai lieu NOI BO -- khong de nam san trong thu muc cai cua khach.
#
# Day la mot RANH GIOI THUONG MAI, KHONG PHAI MOT CAI KHOA: kho nay CONG KHAI, nen ai mo GitHub
# van doc duoc het. Muc dich hep va that: khong dat 9.389 dong tai lieu noi bo -- ke ca
# NOI-BO-nhieu-client.md, tuc chinh cach mo khoa phan nhieu Client (D-42) -- ngay trong thu muc
# khach mo hang ngay.
#
# Duong dan khai TUONG MINH tung cai. Mot mau chung kieu `docs\*` se xoa ca CAI-DAT-VPS.md va
# RUNBOOK.md, tuc hai tai lieu duy nhat khach thuc su can.
$script:DuongNoiBo = @(
    "PROGRESS.md",
    "plan",
    # Ban thu ky thuat, vd. named pipe o huong A: cong cu cua nguoi phat trien, khong phai cua khach.
    "spike",
    "docs\NOI-BO-nhieu-client.md",
    "docs\BACKLOG.md",
    "docs\DECISIONS.md",
    "docs\ACCEPTANCE.md",
    "docs\ARCHITECTURE.md",
    "docs\CONVENTIONS.md"
)

# Dua trang thai ve SACH truoc khi pull.
#
# DA DO (2026-09-22, hai kho git thu tren cung may): `git pull --ff-only` KHONG tu choi khi file
# chi bi xoa khoi thu muc lam viec -- no chay binh thuong, va tu tao lai nhung file ma ban moi co
# cham vao. Nen ham nay KHONG phai de cuu lan pull; dung tin no la vay.
#
# Ly do that, va nho hon: sau lan don dau tien, `git status` bao cac duong nay la " D". Chot thu
# hai cua `don_ban_khach` -- "dang co thay doi chua commit thi de nguyen" -- doc chinh
# `git status`, nen khong lam sach truoc thi cai chot ay khong con phan biet duoc "da xoa tu lan
# truoc" voi "nguoi phat trien dang sua do". Mot trang thai xac dinh dang gia hon mot trang thai
# tinh co dung.
#
# Khong dung `git checkout -- .`: qua rong, no cuon ca sua tay that cua nguoi van hanh.
function phuc_hoi_tai_lieu_noi_bo() {
    if (-not (Test-Path (Join-Path $ThuMuc ".git"))) { return }
    # TUNG DUONG MOT, khong dua ca danh sach vao mot lenh: `git checkout --` gap MOT pathspec
    # khong khop la bao loi va KHONG phuc hoi cai nao ca. Mot file bi doi ten tren nhanh moi se
    # keo theo ca bay cai con lai khong duoc phuc hoi, roi `pull` tu choi -- va thong bao luc do
    # khong he nhac toi ham nay.
    foreach ($d in $script:DuongNoiBo) {
        git -C $ThuMuc checkout -- $d 2>&1 | Out-Null
    }
}

# Chay SAU buoc test: bo test co doc PROGRESS.md va docs\NOI-BO-nhieu-client.md, va
# `cai-dat.ps1` HUY CA LAN CAI khi test do -- xoa truoc la tu lam khach khong cai duoc.
function don_ban_khach() {
    buoc_moi "Don tai lieu noi bo khoi ban cai"

    # CHOT 1: chi xoa khi co .git. Khong co git thi khong co duong phuc hoi, va truong hop do la
    # "thu muc du an chep qua RDP" -- xoa o day la xoa mot chieu. Thua mot ban ro tai lieu con hon
    # xoa mat ban duy nhat cua ai do.
    if (-not (Test-Path (Join-Path $ThuMuc ".git"))) {
        bo_qua "khong phai kho git -- khong co duong phuc hoi, khong xoa"
        return
    }

    $soXoa = 0
    foreach ($d in $script:DuongNoiBo) {
        $duong = Join-Path $ThuMuc $d
        if (-not (Test-Path $duong)) { continue }

        # CHOT 2: dang sua do thi de nguyen. Tinh huong that: mot nguoi phat trien chay chinh
        # script nay trong ban lam viec cua ho. Xoa PROGRESS.md dang co sua tay chua commit la mat
        # han -- `git checkout` khong lay lai duoc thu chua bao gio duoc ghi vao git.
        $dangSua = @(git -C $ThuMuc status --porcelain -- $d 2>$null)
        if ($dangSua.Count -gt 0) {
            bo_qua "$d dang co thay doi chua commit -- khong xoa"
            continue
        }

        try {
            Remove-Item -Recurse -Force $duong -ErrorAction Stop
            $soXoa++
        } catch {
            # Khong nem: mot tai lieu con sot lai khong lam he thong sai mot ly nao.
            canh "khong xoa duoc $d ($($_.Exception.Message))"
        }
    }
    if ($soXoa -gt 0) { ok "da xoa $soXoa duong tai lieu noi bo" }
    else { bo_qua "khong con tai lieu noi bo nao" }
}

function lay_ma_nguon([bool] $coGit) {
    buoc_moi "Lay ma nguon"
    $coPyproject = Test-Path (Join-Path $ThuMuc "pyproject.toml")
    $coDotGit    = Test-Path (Join-Path $ThuMuc ".git")

    if (-not $coGit -or ($coPyproject -and -not $coDotGit)) {
        if (-not $coPyproject) {
            throw "Khong dung duoc git va $ThuMuc cung khong chua pyproject.toml. Chep thu muc du an vao do roi chay lai."
        }
        bo_qua "dung thu muc san co, khong dung git"
        return
    }

    if ($coDotGit) {
        # Phuc hoi tai lieu noi bo da xoa o lan truoc, de trang thai git sach khi vao pull.
        # `don_ban_khach` o cuoi lan chay nay xoa lai.
        phuc_hoi_tai_lieu_noi_bo
        git -C $ThuMuc fetch --prune
        # Khong tu `stash`, khong tu `reset --hard`. Doan y nguoi van hanh o day la cach lam mat
        # mot ban va sua tay luc 2 gio sang.
        git -C $ThuMuc pull --ff-only
        if ($LASTEXITCODE -ne 0) {
            git -C $ThuMuc status
            throw "git pull that bai. Xem trang thai o tren, xu ly bang tay roi chay lai."
        }
        ok "da cap nhat tu $Nhanh"
        return
    }

    if (Test-Path $ThuMuc) {
        $conLai = @(Get-ChildItem -Force $ThuMuc)
        if ($conLai.Count -gt 0) {
            throw "$ThuMuc da ton tai va khong rong nhung khong phai kho git. Xoa hoac doi -ThuMuc."
        }
    }
    git clone --branch $Nhanh -- $Repo $ThuMuc
    if ($LASTEXITCODE -ne 0) {
        throw ("git clone that bai. Neu kho la private thi chon mot trong ba duong: " +
               "(1) gh auth login roi gh repo clone taducloc0603/copy-trade; " +
               "(2) chay lai voi -Repo https://<TOKEN>@github.com/taducloc0603/copy-trade.git; " +
               "(3) chep thu muc qua RDP roi chay lai voi -BoQuaGit")
    }
    ok "da clone vao $ThuMuc"
}

# ---------------------------------------------------------------------------------------------
# B5. venv
# ---------------------------------------------------------------------------------------------
function bao_dam_venv($py) {
    buoc_moi "Tao moi truong ao .venv"
    $venvPy = Join-Path $ThuMuc ".venv\Scripts\python.exe"

    if ($LamMoiVenv -and (Test-Path (Join-Path $ThuMuc ".venv"))) {
        Remove-Item -Recurse -Force (Join-Path $ThuMuc ".venv") -ErrorAction Stop
        canh "da xoa .venv cu"
    }

    if (Test-Path $venvPy) {
        $pb = phien_ban_python $venvPy @()
        if ($null -eq $pb -or $pb -lt [version]'3.11') {
            # Thuong gap khi ai do chep ca thu muc du an (ke ca .venv) qua RDP: duong dan tuyet
            # doi ben trong .venv van tro ve may cu nen no khong chay duoc o day.
            throw ".venv san co khong dung duoc (phien ban $pb). Chay lai voi -LamMoiVenv."
        }
        bo_qua "da co .venv (Python $pb)"
        return $venvPy
    }

    & $py.exe @($py.args) -m venv (Join-Path $ThuMuc ".venv") | Out-Host
    if (-not (Test-Path $venvPy)) { throw "Tao .venv that bai." }
    ok "da tao .venv"
    return $venvPy
}

# ---------------------------------------------------------------------------------------------
# B6. Goi phu thuoc
# ---------------------------------------------------------------------------------------------
function cai_goi([string] $venvPy) {
    buoc_moi "Cai goi phu thuoc"
    Push-Location $ThuMuc
    try {
        & $venvPy -m pip install --upgrade pip --quiet
        # PHAI la editable. pyproject.toml chi khai bao packages = ["bridge"], nen mot ban cai
        # thuong se KHONG co goi `clicker`: he thong chay duoc Bridge nhung khong mo duoc lenh
        # nao, va loi lo ra o cho kho doan nhat. Buoc kiem khoi ben duoi bat dung cai nay.
        & $venvPy -m pip install -e ".[dev]"
        if ($LASTEXITCODE -ne 0) { throw "pip install that bai." }
    } finally { Pop-Location }
    ok "da cai (editable)"
}

# ---------------------------------------------------------------------------------------------
# B7. Thu muc runtime
# ---------------------------------------------------------------------------------------------
function bao_dam_thu_muc() {
    buoc_moi "Tao thu muc data/ va logs/"
    foreach ($t in @("data", "logs", "data\backup")) {
        $d = Join-Path $ThuMuc $t
        if (Test-Path $d) {
            bo_qua $t
        } else {
            New-Item -ItemType Directory -Force -Path $d -ErrorAction Stop | Out-Null
            ok $t
        }
    }
}

# ---------------------------------------------------------------------------------------------
# B8. config.toml
# ---------------------------------------------------------------------------------------------
function bao_dam_config([string] $venvPy) {
    buoc_moi "Cau hinh config.toml"
    $cfg = Join-Path $ThuMuc "config.toml"

    if (Test-Path $cfg) {
        bo_qua "da co config.toml, khong dung vao"
    } else {
        $mau = Join-Path $ThuMuc "config.example.toml"
        if (-not (Test-Path $mau)) { throw "Khong tim thay config.example.toml trong $ThuMuc." }

        # KHONG sinh mat khau nua: dashboard khong con dang nhap (bo tu 2026-09-22). Ban cu sinh
        # mot mat khau ngau nhien roi in ra DUNG MOT LAN luc cai -- ai khong chep lai ngay thi mat
        # luon duong vao trang, va moi nut Luu tra 403 ma khong noi tai sao. Bat duoc o lan cai
        # that thu hai tren VPS: buoc dau tien cua tab Huong dan (cap token) khong bam duoc.
        #
        # ReadAllText chu KHONG phai `Get-Content -Raw`: Get-Content cua PowerShell 5.1 mac dinh
        # doc bang code page ANSI cua he thong, nen no doc config.example.toml (UTF-8) thanh
        # mojibake roi WriteAllText ben duoi ghi mojibake do ra UTF-8. Ket qua: moi dong chu thich
        # tieng Viet trong config.toml sinh ra deu hong. Khoa va gia tri toan ASCII nen TOML van
        # parse duoc va khong ai phat hien -- cho toi luc co mot gia tri khong phai ASCII.
        $noi = [System.IO.File]::ReadAllText($mau)
        # PHAI la UTF-8 KHONG BOM: bridge/config.py mo file o che do nhi phan roi dua cho
        # tomllib, va BOM se lam tomllib nem loi parse voi mot thong bao khong he nhac toi BOM.
        [System.IO.File]::WriteAllText($cfg, $noi, (New-Object System.Text.UTF8Encoding($false)))

        # Dung SID chu khong dung ten "Administrators"/"SYSTEM": Windows Server ban ngon ngu
        # khac khong co cac ten tieng Anh do.
        icacls $cfg /inheritance:r /grant:r "$($env:USERNAME):(R,W)" "*S-1-5-32-544:(F)" "*S-1-5-18:(F)" | Out-Null
        ok "da tao config.toml"
        Write-Host ""
        Write-Host "        Dashboard KHONG co dang nhap va chi nghe 127.0.0.1 -- ai vao duoc may" -ForegroundColor Yellow
        Write-Host "        nay la sua duoc cau hinh copy. Dung mo cong 8080 ra mang." -ForegroundColor Yellow
    }

    Push-Location $ThuMuc
    try {
        & $venvPy -c "from bridge.config import load_config; load_config()"
        if ($LASTEXITCODE -ne 0) { throw "config.toml khong hop le. Xem thong bao o tren." }
        ok "config.toml hop le"

        # Bo cai KHONG BAO GIO sua config.toml da ton tai. Cai gia phai tra la sau mot lan cap
        # nhat, config.toml cu co the thieu khoa ma config.example.toml vua them -- va thieu
        # khoa thi Bridge chay bang gia tri mac dinh trong im lang. Nen phai noi ra.
        $thieu = & $venvPy -c $script:MaSoSanhKhoa
        if ($LASTEXITCODE -eq 0 -and "$thieu".Trim()) {
            canh "config.toml thieu khoa so voi config.example.toml: $thieu"
            canh "Mo ca hai file, chep khoa con thieu sang, roi chay lai."
        }
    } finally { Pop-Location }
}

# ---------------------------------------------------------------------------------------------
# B9. Database + kiem khoi
# ---------------------------------------------------------------------------------------------
function khoi_tao_va_kiem([string] $venvPy) {
    buoc_moi "Khoi tao database va kiem khoi"
    Push-Location $ThuMuc
    try {
        # `liet-ke` chinh la lenh khoi tao: Database.__init__ tu tao thu muc va tu chay migration.
        & $venvPy -m bridge.admin liet-ke
        if ($LASTEXITCODE -ne 0) { throw "Khong khoi tao duoc database." }
        ok "database da san sang"

        # `clicker` nam trong danh sach nay co chu dich: day la bai bat loi cai khong-editable.
        & $venvPy -c "import bridge, clicker, fastapi, uvicorn, pydantic"
        if ($LASTEXITCODE -ne 0) {
            throw "Import that bai. Rat co the goi da duoc cai khong o che do editable."
        }
        ok "import bridge + clicker OK"

        if ($BoQuaTest) {
            bo_qua "-BoQuaTest"
        } else {
            Write-Host "        Dang chay bo test -- vai phut tren VPS. Moi dau cham la mot test." -ForegroundColor DarkGray
            Write-Host "        Muon bo qua buoc nay: chay lai voi -BoQuaTest." -ForegroundColor DarkGray

            # Dung System.Diagnostics.Process chu khong phai `&` hay Start-Process, va ca hai
            # deu co ly do da do bang thu nghiem:
            #   `&`            -- khong co duong nao dat han. Mot test TREO thi ket cung vinh vien.
            #   Start-Process  -- -ArgumentList noi bang dau cach va KHONG tu them ngoac, nen
            #                     `not cham` bi tach lam hai tham so va pytest bao
            #                     "file or directory not found: cham"; ngoai ra .ExitCode
            #                     tra ve RONG sau WaitForExit(ms), tuc loi hong se LOT qua.
            # Cach duoi day cho ca hai deu dung, va van in dau cham theo thoi gian thuc vi
            # UseShellExecute=$false khong kem chuyen huong thi tien trinh con dung chung console.
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName         = $venvPy
            $psi.Arguments        = '-m pytest -q -m "not cham"'
            $psi.WorkingDirectory = $ThuMuc
            $psi.UseShellExecute  = $false
            $tt = [System.Diagnostics.Process]::Start($psi)
            if (-not $tt.WaitForExit($GiayChoTest * 1000)) {
                try { $tt.Kill() } catch { }
                throw ("Bo test qua $GiayChoTest giay chua xong -- gan nhu chac chan co test TREO, " +
                       "khong phai test hong. Chay lai voi -BoQuaTest de cai tiep, roi bao lai loi nay.")
            }
            if ($tt.ExitCode -ne 0) { throw "Bo test that bai. DUNG trien khai cho toi khi xanh." }
            ok "bo test xanh"
        }
    } finally { Pop-Location }
}

# ---------------------------------------------------------------------------------------------
# B10. Ket thuc
# ---------------------------------------------------------------------------------------------
# Clicker la Scheduled Task, khong phai dich vu: Stop-Service/Start-Service khong dung toi no. Khong
# nap lai o day thi Bridge moi chay cung clicker CU, ma clicker cu tu choi moi loai lenh no khong
# biet (vi du CLOSE_UI) -- nang cap "xong" ma khong co tac dung, va khong ai hay.
function tien_trinh_clicker() {
    # Chi dung ProcessId. KHONG BAO GIO in CommandLine: clicker kieu cu co token trong do.
    return @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -like '*-m clicker*' })
}

function dung_clicker_cu() {
    $cu = @(tien_trinh_clicker)
    if ($cu.Count -eq 0) {
        canh "clicker khong chay, khong co gi de nap lai"
        return
    }
    $pidCu = @($cu | ForEach-Object { [int] $_.ProcessId })
    # Giet HET ca danh sach, ke ca tien trinh con cua launcher trong .venv: con sot mot tien trinh
    # cu giu khoa SingleInstance thi clicker moi thoat ma 3 va chay-clicker.ps1 dung han vong lap.
    foreach ($p in $pidCu) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
    $conSong = @(tien_trinh_clicker | Where-Object { $pidCu -contains [int] $_.ProcessId })
    if ($conSong.Count -gt 0) {
        canh ("KHONG dung duoc clicker cu, PID " + (($conSong | ForEach-Object { $_.ProcessId }) -join ', ') +
              ". No van chay CODE CU. Dung tay trong Task Manager.")
    } else {
        ok ("da dung clicker cu, PID " + ($pidCu -join ', ') + " -- chay-clicker.ps1 se tu bat lai")
    }
    return $pidCu
}

function cho_clicker_moi([int[]] $pidCu) {
    $han = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $han) {
        $moi = @(tien_trinh_clicker | Where-Object { $pidCu -notcontains [int] $_.ProcessId })
        if ($moi.Count -gt 0) {
            ok ("clicker da bat lai bang code moi, PID " + (($moi | ForEach-Object { $_.ProcessId }) -join ', '))
            return
        }
        Start-Sleep -Seconds 3
    }
    # Liet ke MOI tac vu Clicker*: tu D-35 co the co ba cai (clicker, clicker_master, clicker_cl02),
    # va mot goi y chi noi ten "Clicker" se de nguoi van hanh bo lai hai cai kia dang chay code cu.
    $ten = @(Get-ScheduledTask -TaskPath '\CopyBridge\' -ErrorAction SilentlyContinue |
             Where-Object { $_.TaskName -like 'Clicker*' } | ForEach-Object { $_.TaskName })
    if ($ten.Count -eq 0) { $ten = @('Clicker') }
    canh ("clicker chua bat lai sau 45 giay. Bat tay: " +
          (($ten | ForEach-Object {
              "Start-ScheduledTask -TaskPath '\CopyBridge\' -TaskName $_" }) -join '; '))
}

# Cai moi thi chay tiep tro ly NGAY o day, thay vi in ra sau lenh de nguoi dung go tay.
#
# Ly do: nam viec trong khoi "BUOC TIEP THEO" phai lam DUNG THU TU, mot viec can token vua hien
# mot lan, va bo sot bat ky viec nao thi he thong dung xong van khong copy duoc lenh nao -- hong
# trong im lang. Mot lenh duy nhat la cach duy nhat khong bao gio sai thu tu.
#
# `-TuDongDongY` nen tro ly khong hoi gi ve nghiep vu; phan do khai tren dashboard, va tro ly mo
# san trinh duyet o buoc cuoi.
function chay_tro_ly() {
    buoc_moi "Tro ly cai dat"
    if ($CapNhat)     { bo_qua "-CapNhat: khong dung lai he thong dang chay"; return $false }
    if ($BoQuaTroLy)  { bo_qua "-BoQuaTroLy"; return $false }

    $troLy = Join-Path $ThuMuc "scripts\tro-ly.ps1"
    if (-not (Test-Path $troLy)) { canh "khong thay $troLy"; return $false }
    if (-not (la_admin)) {
        # Khong nem: nen da dung xong that. Nhung tro ly can quyen Administrator o buoc dich vu,
        # nen noi ro va de nguoi dung chay lai dung mot lenh.
        canh "khong co quyen Administrator, khong chay duoc tro ly (buoc dich vu can quyen do)."
        canh "Mo lai PowerShell bang 'Run as administrator' roi chay: $troLy -ThuMuc `"$ThuMuc`""
        return $false
    }

    & $troLy -ThuMuc $ThuMuc -TenDichVu $TenDichVu -TuDongDongY
    if ($LASTEXITCODE -ne 0) { canh "tro-ly.ps1 tra ve $LASTEXITCODE -- doc phan tren"; return $false }
    return $true
}

function sau_khi_cap_nhat([string] $commitCu) {
    buoc_moi "Ket thuc cap nhat"
    if (-not $CapNhat) { bo_qua "khong phai -CapNhat"; return }

    # Duong lui in ra duoi day la lenh nguoi ta go luc dang hoang, nen no phai dung hoac
    # phai im -- khong duoc in mot chuoi rac trong ra nhu that. Mot lenh native quen
    # chuyen huong o `truoc_khi_cap_nhat` la du bien $commitCu thanh mang, va da tung xay ra.
    if ($commitCu -is [array]) { $commitCu = $commitCu | Select-Object -Last 1 }
    $commitCu = "$commitCu".Trim()
    if ($commitCu -notmatch '^[0-9a-f]{40}$') {
        if ($commitCu) { canh "khong doc duoc commit cu, bo qua duong lui" }
        $commitCu = ""
    }

    $eaDoi = @()
    if ($commitCu) {
        $eaDoi = @(git -C $ThuMuc diff --name-only "$commitCu..HEAD" -- ea/)
        if ($eaDoi.Count -gt 0) {
            Write-Host ""
            Write-Host "  !! EA DA THAY DOI -- PHAI BIEN DICH LAI VA GAN LAI EA !!" -ForegroundColor Red
            $eaDoi | ForEach-Object { Write-Host "     $_" -ForegroundColor Red }
            Write-Host '     & "C:\Program Files\MetaTrader 5\MetaEditor64.exe" /compile:"<duong-dan>.mq5" /log:"<log>"' -ForegroundColor Yellow
            Write-Host "     Bien dich xong PHAI GO EA KHOI CHART ROI GAN LAI. Doi khung thoi gian" -ForegroundColor Yellow
            Write-Host "     KHONG lam MT5 doc lai .ex5 tu dia." -ForegroundColor Yellow
        } else {
            ok "ea/ khong doi"
        }
        Write-Host "        Duong lui: git -C `"$ThuMuc`" checkout $commitCu" -ForegroundColor DarkGray
    }

    # Nap lai clicker TRUOC khi bat Bridge: luc nay Bridge dang dung nen khong co lenh nao dang bay.
    $pidCu = @(dung_clicker_cu)

    $dv = Get-Service $TenDichVu -ErrorAction SilentlyContinue
    if ($null -ne $dv) {
        # KHONG `Start-Service` tran. SCM bao dich vu da dung TRUOC KHI python.exe con thoat han,
        # nen ban moi len co the thay cong 8787 con bi giu va CO Y khong chay -- Windows chi noi
        # "Failed to start service", khong mot chu nao ve cong. Da xay ra that tren VPS 2026-09-22.
        # khoi-dong-lai.ps1 cho cong duoc nha, giet tien trinh mo coi, roi cho toi khi cong THAT SU
        # co nguoi nghe. Tham so truyen theo TEN: splat MANG truyen theo VI TRI (xem 25efcdb).
        $thamSo = @{ ThuMuc = $ThuMuc; TenDichVu = $TenDichVu }
        & (Join-Path $ThuMuc "scripts\khoi-dong-lai.ps1") @thamSo
        if ($LASTEXITCODE -eq 0) {
            ok "da bat lai dich vu $TenDichVu"
        } else {
            # Khong nem: phan con lai cua buoc nay (bien nhan cho tab Huong dan, duong lui) van co
            # ich, va khoi-dong-lai.ps1 vua in dung ba cho can xem.
            canh "khong bat lai duoc dich vu $TenDichVu (ma thoat $LASTEXITCODE). Doc phan tren."
        }
    } else {
        bo_qua "chua dang ky dich vu (chay scripts\tao-dich-vu.ps1)"
    }

    if ($pidCu.Count -gt 0) { cho_clicker_moi $pidCu }

    # Ghi bien nhan cho trang Huong dan, roi mo no. Day la thu DUY NHAT cho dashboard biet vua co
    # mot lan cap nhat: Bridge khong luu phien ban code nao, va mot agent noi lai thi trong giong
    # nhau du vi EA vua gan lai hay vi dich vu vua khoi dong.
    #
    # `ea/ doi` chi biet duoc o day (git diff giua hai commit), nen phai ghi xuong -- neu khong thi
    # buoc "bien dich lai va gan lai EA" se hien ra o MOI lan cap nhat, va mot canh bao luon hien
    # la mot canh bao khong ai doc.
    $venvPy = Join-Path $ThuMuc ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        Push-Location $ThuMuc
        try {
            $eaCo = if ($eaDoi.Count -gt 0) { 1 } else { 0 }
            & $venvPy -m bridge.admin ghi-moc-cap-nhat --ea-doi $eaCo --tu-commit $commitCu |
                Out-Null
            if ($LASTEXITCODE -eq 0) { ok "da ghi moc cap nhat cho trang Huong dan" }
            else { canh "khong ghi duoc moc cap nhat (ma $LASTEXITCODE)" }
        } finally { Pop-Location }
    }

    $troLy = Join-Path $ThuMuc "scripts\tro-ly.ps1"
    if (Test-Path $troLy) { & $troLy -ThuMuc $ThuMuc -TenDichVu $TenDichVu -ChiMoDashboard }
}

# PATH moi chi co trong tien trinh NAY va trong cac tien trinh mo SAU day. Mot cua so PowerShell
# mo tu truoc luc cai van mang PATH cu, va `git pull` o do bao "not recognized" -- mot thong bao
# khong he nhac toi PATH, nen khong ai noi duoc no ve day. Da xay ra that 2026-09-22: nguoi dung
# khong cap nhat duoc va tuong ban moi chua co tinh nang.
function canh_bao_path_cu() {
    if (-not $script:VuaCaiGit) { return }
    Write-Host ""
    Write-Host " LUU Y: vua cai git trong lan nay." -ForegroundColor Yellow
    Write-Host " Cua so PowerShell nao dang mo TU TRUOC se khong thay git: `git pull` o do se bao" -ForegroundColor Yellow
    Write-Host " 'not recognized'. Mo mot cua so PowerShell MOI, hoac nap lai PATH trong cua so cu:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')" -ForegroundColor DarkGray
}

# CHI chay khi tro ly KHONG chay duoc, va CHI o lan cai dau -- xem cho goi o cuoi file.
#
# Khoi nay truoc day co mot "hoac lam tay, dung thu tu nay" gom sau buoc, trong do co ca lenh
# `them-client`. Hai van de: no la mot ban chi dan SONG SONG voi tab Huong dan (va hai ban song
# song thi se lech -- da lech that), va no in ra man hinh khach dung cai lenh ma ban giao co y
# khong nhac toi (D-42). Gio no chi con la mot con tro.
function in_buoc_tiep() {
    buoc_moi "Xong"
    Write-Host ""
    tach
    Write-Host " BUOC TIEP THEO" -ForegroundColor Cyan
    tach
    Write-Host @"
 Tro ly chua chay (xem ly do o khoi ngay tren). CHAY MOT LENH NAY trong PowerShell
 mo bang "Run as administrator":

      $ThuMuc\scripts\tro-ly.ps1 -ThuMuc "$ThuMuc"

 No tao agent, ghi token clicker thang vao config.toml, tao dong client, dang ky
 dich vu (Bridge bat dau chay o day), bien dich EA va chep vao MT5, roi mo tab
 Huong dan. Chay lai bao nhieu lan cung duoc: buoc nao xong roi se in BO QUA.

 Xong lenh do thi moi viec con lai nam tren tab Huong dan cua dashboard, muc
 "Cai dat lan dau" -- tung buoc, dung thu tu, co nut Chay san.

 Moi lan dang nhap VPS:  $ThuMuc\scripts\kiem-tra.ps1 -ThuMuc "$ThuMuc"
"@
    Write-Host ""
    # Duong chay duoc chinh docs/CAI-DAT-VPS.md khuyen nghi -- tai rieng cai-dat.ps1 roi chay de
    # no tu clone -- dat $PSScriptRoot o Desktop, con canh-bao.txt thi nam trong ban vua clone.
    # Khong do tim o $ThuMuc thi buoc cuoi nem mot cuc loi Get-Content mau do va khoi 7 canh bao
    # "khong lam = mat tien" bien mat, dung cai phan dang ra phai doc ky nhat.
    $canhBao = @(
        (Join-Path $PSScriptRoot "canh-bao.txt"),
        (Join-Path $ThuMuc "scripts\canh-bao.txt")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($canhBao) {
        Get-Content $canhBao | ForEach-Object { Write-Host $_ -ForegroundColor Yellow }
    } else {
        canh "Khong tim thay canh-bao.txt. Doc docs\CAI-DAT-VPS.md muc 'Nhung gi script KHONG lam duoc'."
    }
    if (-not $CapNhat) {
        Write-Host ""
        Write-Host " RUI RO DIEU KHOAN (khong phai ky thuat, khong hien ra o bat ky log nao):" -ForegroundColor Yellow
        Write-Host " Hai tai khoan mo vi the nguoc chieu, cung symbol, cach nhau duoi mot giay, tu" -ForegroundColor Yellow
        Write-Host " CUNG MOT IP la dau vet rat de nhan. Nhieu broker cam hoac huy loi nhuan tu mo" -ForegroundColor Yellow
        Write-Host " hinh nay. Doc dieu khoan cua CA HAI broker truoc khi chay tien that." -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------------------------
try {
    Write-Host ""
    Write-Host " MT5 Copy Bridge -- cai dat (ban $script:PhienBan)" -ForegroundColor Cyan
    Write-Host " Thu muc dich: $ThuMuc" -ForegroundColor DarkGray
    if ($CapNhat) { Write-Host " Che do: CAP NHAT" -ForegroundColor Yellow }

    chan_cai_de_len_ban_dang_chay

    $py    = bao_dam_python
    $coGit = bao_dam_git
    $commitCu = truoc_khi_cap_nhat (Join-Path $ThuMuc ".venv\Scripts\python.exe")

    lay_ma_nguon $coGit
    $venvPy = bao_dam_venv $py
    cai_goi $venvPy
    bao_dam_thu_muc
    bao_dam_config $venvPy
    khoi_tao_va_kiem $venvPy
    # SAU buoc test, khong truoc: bo test doc PROGRESS.md va docs\NOI-BO-nhieu-client.md.
    don_ban_khach
    sau_khi_cap_nhat $commitCu
    # Tro ly da in khoi ket cua rieng no (con tro sang tab Huong dan + canh-bao.txt) va da mo
    # dashboard, nen in tiep khoi "BUOC TIEP THEO" nua chi lam nguoi doc khong biet theo cai nao.
    #
    # `-and (-not $CapNhat)`: `chay_tro_ly` tra $false cho MOI lan -CapNhat, nen truoc day khach
    # bam CAP-NHAT.cmd la nhan tron khoi "BUOC TIEP THEO" cua lan cai DAU -- lenh chay tro ly,
    # lenh them-client, tat ca. Duong cap nhat da co khoi ket rieng: `sau_khi_cap_nhat` bat lai
    # dich vu, ghi moc cap nhat, roi mo tab Huong dan o muc "Sau khi cap nhat code".
    if (-not (chay_tro_ly) -and (-not $CapNhat)) { in_buoc_tiep }
    # In SAU cung, ke ca khi tro ly da in khoi ket cua rieng no: day la thu chan lan cap nhat ke
    # tiep, nen no phai la dong cuoi nguoi dung con nhin thay.
    canh_bao_path_cu
    exit 0
} catch {
    Write-Host ""
    Write-Host " LOI: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
