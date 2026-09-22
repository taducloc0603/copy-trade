@echo off
setlocal
chcp 65001 >nul 2>&1

rem ============================================================================================
rem  MT5 Copy Bridge -- CAI DAT LAN DAU. Bam dup vao file nay.
rem
rem  Vi sao .cmd chu khong .ps1: Windows mac dinh MO .ps1 BANG NOTEPAD khi bam dup. Mot file huong
rem  dan nguoi dung "bam dup de chay" ma bam dup ra Notepad la mot file hong. .cmd thi bam dup la
rem  chay, tu xin quyen Administrator duoc, va dung lai duoc de doc ket qua.
rem
rem  File nay KHONG chua logic cai dat nao. No tai scripts\cai-dat.ps1 tu GitHub roi chay. Chep
rem  logic sang day la tao ban thu hai se lech voi ban that.
rem
rem  Dua file nay len VPS: chay MOT dong nay trong PowerShell hoac Command Prompt --
rem    curl -L -o "%USERPROFILE%\Desktop\CAI-DAT.cmd" https://raw.githubusercontent.com/taducloc0603/copy-trade/main/CAI-DAT.cmd
rem  roi bam dup no tren Desktop.
rem ============================================================================================

set "THU_MUC=C:\CopyBridge"
set "URL=https://raw.githubusercontent.com/taducloc0603/copy-trade/main/scripts/cai-dat.ps1"
set "TAM=%TEMP%\cai-dat-copybridge.ps1"

rem -- Quyen Administrator. Cai Python/git/dich vu deu can, va thieu no thi script that bai o giua
rem -- chung, de lai mot ban cai do dang -- te hon la khong bat dau.
net session >nul 2>&1
if errorlevel 1 (
    echo Dang xin quyen Administrator...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo  ============================================================
echo   MT5 Copy Bridge -- CAI DAT LAN DAU
echo   Thu muc dich: %THU_MUC%
echo  ============================================================
echo.
echo  Dang tai bo cai tu GitHub...

rem TLS 1.2 tuong minh: PowerShell 5.1 mac dinh dung SSL3/TLS1 va bi GitHub tu choi.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest '%URL%' -OutFile '%TAM%' -UseBasicParsing"
if errorlevel 1 (
    echo.
    echo  KHONG TAI DUOC bo cai. VPS co the dang chan mang ra ngoai.
    echo  Thu mo dia chi nay bang trinh duyet tren chinh VPS:
    echo    %URL%
    goto :ket
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%TAM%" -ThuMuc "%THU_MUC%"

echo.
echo  ============================================================
if errorlevel 1 (
    echo   CAI DAT DUNG GIUA CHUNG. Doc phan mau do ben tren.
    echo   Chay lai file nay bao nhieu lan cung duoc: buoc nao xong roi se in BO QUA.
) else (
    echo   XONG. Tu gio, moi lan cap nhat thi bam dup:
    echo     %THU_MUC%\CAP-NHAT.cmd
)
echo  ============================================================

:ket
echo.
pause
endlocal
