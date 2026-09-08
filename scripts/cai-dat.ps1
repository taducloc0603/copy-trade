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
[CmdletBinding()]
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
    [switch] $KhongCaiPython
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

$script:TongBuoc = 11
# Ghi cung trong file chu khong hoi git: tinh huong hong that la mot ban cai-dat.ps1 chep ra
# Desktop cua VPS, nam ngoai moi kho git, bao mot loi da duoc sua tu lau. In so nay ra banner de
# nguoi van hanh doc mot dong la biet minh dang chay ban nao. DOI SO NAY MOI LAN SUA SCRIPT.
$script:PhienBan = "2026-09-08"

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
        winget install --id Python.Python.3.12 --exact --scope machine --silent `
            --accept-package-agreements --accept-source-agreements
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

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        canh "Chua co git, dang cai bang winget"
        winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
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
            & $venvPy -m bridge.admin sao-luu
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

    & $py.exe @($py.args) -m venv (Join-Path $ThuMuc ".venv")
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

        $bytes = New-Object byte[] 24
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $matKhau = ([Convert]::ToBase64String($bytes)) -replace '[+/=]', ''

        # ReadAllText chu KHONG phai `Get-Content -Raw`: Get-Content cua PowerShell 5.1 mac dinh
        # doc bang code page ANSI cua he thong, nen no doc config.example.toml (UTF-8) thanh
        # mojibake roi WriteAllText ben duoi ghi mojibake do ra UTF-8. Ket qua: moi dong chu thich
        # tieng Viet trong config.toml sinh ra deu hong. Khoa va gia tri toan ASCII nen TOML van
        # parse duoc va khong ai phat hien -- cho toi luc co mot gia tri khong phai ASCII.
        $noi = [System.IO.File]::ReadAllText($mau) -replace 'dashboard_password = ""', "dashboard_password = `"$matKhau`""
        # PHAI la UTF-8 KHONG BOM: bridge/config.py mo file o che do nhi phan roi dua cho
        # tomllib, va BOM se lam tomllib nem loi parse voi mot thong bao khong he nhac toi BOM.
        [System.IO.File]::WriteAllText($cfg, $noi, (New-Object System.Text.UTF8Encoding($false)))

        # Dung SID chu khong dung ten "Administrators"/"SYSTEM": Windows Server ban ngon ngu
        # khac khong co cac ten tieng Anh do.
        icacls $cfg /inheritance:r /grant:r "$($env:USERNAME):(R,W)" "*S-1-5-32-544:(F)" "*S-1-5-18:(F)" | Out-Null
        ok "da tao config.toml voi mat khau ngau nhien"
        Write-Host ""
        Write-Host "        Mat khau dashboard: $matKhau" -ForegroundColor Yellow
        Write-Host "        (doc lai duoc trong $cfg -- khac voi token cua agent)" -ForegroundColor DarkGray
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
function sau_khi_cap_nhat([string] $commitCu) {
    buoc_moi "Ket thuc cap nhat"
    if (-not $CapNhat) { bo_qua "khong phai -CapNhat"; return }

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

    $dv = Get-Service $TenDichVu -ErrorAction SilentlyContinue
    if ($null -ne $dv) {
        Start-Service $TenDichVu -ErrorAction Stop
        ok "da bat lai dich vu $TenDichVu"
    } else {
        bo_qua "chua dang ky dich vu (chay scripts\tao-dich-vu.ps1)"
    }
}

function in_buoc_tiep() {
    buoc_moi "Xong"
    $venvPy = ".venv\Scripts\python.exe"
    Write-Host ""
    tach
    Write-Host " BUOC TIEP THEO" -ForegroundColor Cyan
    tach
    Write-Host @"
 CHAY MOT LENH NAY, no hoi xac nhan tung buoc roi tu lam theo dung thu tu:

      $ThuMuc\scripts\tro-ly.ps1 -ThuMuc "$ThuMuc"

 No tao agent, ghi token clicker thang vao config.toml, tao dong client, dang ky
 dich vu (Bridge bat dau chay o day), bien dich EA, cho EA len ONLINE, khai bao
 anh xa symbol, roi chay kiem tra. Chay lai bao nhieu lan cung duoc.

 ---------------------------------------------------------------------------
 Hoac lam tay, DUNG THU TU NAY:

 1. Tao agent va cap token (database moi LUON RONG -- data/ nam trong .gitignore):
      cd "$ThuMuc"
      $venvPy -m bridge.admin them-agent AG-MASTER  --role MASTER  --magic 770001 --login <so-tk-master>
      $venvPy -m bridge.admin them-agent AG-CLIENT  --role CLIENT  --magic 770001 --login <so-tk-client>
      $venvPy -m bridge.admin them-agent AG-CLICKER --role CLICKER --magic 770001 --login <so-tk-client>
    Token tho HIEN DUNG MOT LAN. Token cua AG-CLICKER dat vao muc [clicker] trong config.toml,
    dung dat tren dong lenh -- dong lenh cua tien trinh thi may nao cung doc duoc.

 2. Tao dong client -- THIEU BUOC NAY LA anh-xa-symbol BAO 'Khong co client':
      $venvPy -m bridge.admin them-client CL-01 --agent AG-CLIENT --clicker-agent AG-CLICKER --open-route UI

 3. Dang ky dich vu va tac vu. PHAI LAM TRUOC BUOC 4: day la thu khoi dong Bridge,
    va EA gan len chart khi chua ai nghe cong 8787 se khong bao gio len ONLINE.
      $ThuMuc\scripts\tao-dich-vu.ps1 -ThuMuc "$ThuMuc"

 4. Cai hai terminal MT5, bien dich va gan EA, dien token vao tham so EA.

 5. Khai bao anh xa symbol -- THIEU BUOC NAY LA MOI LENH MASTER BI BO QUA trong im lang:
      $venvPy -m bridge.admin anh-xa-symbol --help
    (can EA Client dang chay va symbol da keo vao Market Watch)

 6. Moi lan dang nhap:
      $ThuMuc\scripts\kiem-tra.ps1 -ThuMuc "$ThuMuc"

 Chi tiet tung buoc: docs\CAI-DAT-VPS.md
"@
    Write-Host ""
    # Duong chay duoc chinh docs/CAI-DAT-VPS.md khuyen nghi -- tai rieng cai-dat.ps1 roi chay de
    # no tu clone -- dat $PSScriptRoot o Desktop, con canh-bao.txt thi nam trong ban vua clone.
    # Khong do tim o $ThuMuc thi buoc cuoi nem mot cuc loi Get-Content mau do va khoi 6 canh bao
    # "khong lam = mat tien" bien mat, dung cai phan dang ra phai doc ky nhat.
    $canhBao = @(
        (Join-Path $PSScriptRoot "canh-bao.txt"),
        (Join-Path $ThuMuc "scripts\canh-bao.txt")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($canhBao) {
        Get-Content $canhBao | ForEach-Object { Write-Host $_ -ForegroundColor Yellow }
    } else {
        canh "Khong tim thay canh-bao.txt. Doc docs\CAI-DAT-VPS.md muc 10 -- 6 viec script KHONG lam duoc."
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

    $py    = bao_dam_python
    $coGit = bao_dam_git
    $commitCu = truoc_khi_cap_nhat (Join-Path $ThuMuc ".venv\Scripts\python.exe")

    lay_ma_nguon $coGit
    $venvPy = bao_dam_venv $py
    cai_goi $venvPy
    bao_dam_thu_muc
    bao_dam_config $venvPy
    khoi_tao_va_kiem $venvPy
    sau_khi_cap_nhat $commitCu
    in_buoc_tiep
    exit 0
} catch {
    Write-Host ""
    Write-Host " LOI: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
