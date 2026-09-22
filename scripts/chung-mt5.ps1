<#
.SYNOPSIS
    Tim thu muc du lieu cua cac terminal MT5. Dung chung cho go-bo.ps1 va bien-dich-ea.ps1.

.DESCRIPTION
    Tach ra mot cho vi hai script lam hai viec NGUOC nhau tren cung mot danh sach: go-bo.ps1 XOA
    file EA trong do, bien-dich-ea.ps1 CHEP file EA vao do. Hai ban quet khac nhau thi se co file
    chep vao mot cho ma lan go khong dung toi -- va mot .ex5 cu con sot lai la mot EA chay code cu.

    Dot-source: `. (Join-Path $PSScriptRoot "chung-mt5.ps1")`
#>

Set-StrictMode -Version Latest

function thu_muc_du_lieu_mt5() {
    <#
    .SYNOPSIS
        Moi thu muc du lieu MT5 tren may, bat ke ai dang chay script nay.
    #>
    # Moi terminal MT5 mot thu muc du lieu rieng duoi <profile>\AppData\Roaming\MetaQuotes\Terminal\
    # <hash>. Ban portable thi du lieu nam ngay trong thu muc cai, nen quet ca hai cho.
    #
    # KHONG dung $env:APPDATA. Nut Chay tren dashboard sinh tien trinh con cua DICH VU, chay bang
    # LocalSystem hoac tai khoan autologon -- $env:APPDATA cua no khong phai cua nguoi dang ngoi
    # truoc may, nen no se tim thay 0 terminal roi bao xong. Quet moi ho so nguoi dung thi ai chay
    # cung ra cung mot danh sach.
    $goc = @()
    $hoSo = Join-Path $env:SystemDrive "Users"
    if (Test-Path $hoSo) {
        $goc += @(Get-ChildItem $hoSo -Directory -ErrorAction SilentlyContinue |
                  ForEach-Object { Join-Path $_.FullName "AppData\Roaming\MetaQuotes\Terminal" })
    }
    $goc += @("C:\Program Files", "C:\Program Files (x86)")

    $ket = @()
    foreach ($g in $goc) {
        if (-not (Test-Path $g)) { continue }
        $ket += @(Get-ChildItem $g -Directory -ErrorAction SilentlyContinue |
                  Where-Object { Test-Path (Join-Path $_.FullName "MQL5") } |
                  ForEach-Object { $_.FullName })
    }
    # Sort -Unique: mot may co the co ca ban portable lan ban cai thuong tro toi cung mot cho.
    return @($ket | Sort-Object -Unique)
}
