@echo off
setlocal
chcp 65001 >nul 2>&1

rem ============================================================================================
rem  MT5 Copy Bridge -- CAP NHAT LEN CODE MOI. Bam dup vao file nay.
rem
rem  File nay di kem ma nguon, nen `git pull` tu cap nhat luon chinh no.
rem
rem  No lam dung ba viec ma truoc day nguoi dung phai tu nho:
rem    1. Xin quyen Administrator (buoc dung/bat dich vu can).
rem    2. NAP LAI PATH. winget cai git xong chi cap nhat PATH trong REGISTRY; mot cua so mo tu
rem       truoc luc cai van mang PATH cu va `git pull` bao "The term 'git' is not recognized" --
rem       mot thong bao khong he nhac toi PATH. Da chan dung mot lan cap nhat that 2026-09-22.
rem    3. Chay dung `cai-dat.ps1 -CapNhat`, voi thu muc la thu muc CHUA CHINH FILE NAY -- khong
rem       doan "C:\CopyBridge", de ban cai o o khac van dung.
rem
rem  KHONG chua logic cap nhat nao: moi thu nam trong scripts\cai-dat.ps1.
rem ============================================================================================

rem %~dp0 co dau \ o cuoi; bo di cho sach duong dan in ra.
set "THU_MUC=%~dp0"
if "%THU_MUC:~-1%"=="\" set "THU_MUC=%THU_MUC:~0,-1%"

net session >nul 2>&1
if errorlevel 1 (
    echo Dang xin quyen Administrator...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

if not exist "%THU_MUC%\scripts\cai-dat.ps1" (
    echo.
    echo  KHONG THAY "%THU_MUC%\scripts\cai-dat.ps1".
    echo  File CAP-NHAT.cmd phai nam o GOC thu muc cai ^(vi du C:\CopyBridge^), khong phai o cho khac.
    goto :ket
)

echo.
echo  ============================================================
echo   MT5 Copy Bridge -- CAP NHAT
echo   Thu muc: %THU_MUC%
echo  ============================================================
echo.

rem MOT loi goi PowerShell lam ca hai viec: nap lai PATH roi chay bo cap nhat trong CUNG tien
rem trinh do. Ban truoc dung `for /f` de doc PATH ve bien cua cmd, va dau `^` noi dong ben trong
rem `for /f` lam ca file TREO -- mot cho mong manh noi tieng cua cmd. Mot lenh, khong noi dong.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User'); if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Host '  CANH BAO: van khong goi duoc git sau khi nap lai PATH. Cai git: winget install --id Git.Git -e' -ForegroundColor Yellow }; & '%THU_MUC%\scripts\cai-dat.ps1' -CapNhat -ThuMuc '%THU_MUC%'; exit $LASTEXITCODE"
set "MA=%ERRORLEVEL%"

echo.
echo  ============================================================
if not "%MA%"=="0" (
    echo   CAP NHAT DUNG GIUA CHUNG ^(ma thoat %MA%^). Doc phan mau do ben tren.
    echo   Dich vu co the dang dung. Bat lai bang:
    echo     %THU_MUC%\scripts\khoi-dong-lai.ps1
) else (
    echo   XONG. Trinh duyet vua mo tab Huong dan - muc "Sau khi cap nhat code".
    echo   Viec dau tien trong do: bam Ctrl+F5 tren moi tab dashboard mo tu TRUOC lan nay.
)
echo  ============================================================

:ket
echo.
pause
endlocal
