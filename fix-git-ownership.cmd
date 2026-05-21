@echo off
chcp 65001 >nul
setlocal

:: Chay file nay bang "Run as administrator" (mot lan) neu git bao dubious ownership
:: hoac "unable to write new index file" / "Permission denied" khi commit.

set "REPO=E:\python-code\188-com-vn"

net session >nul 2>&1
if errorlevel 1 (
  echo [LOI] Can quyen Administrator. Chuot phai file nay ^> Run as administrator
  pause
  exit /b 1
)

echo ==> Doi quyen so huu thu muc repo: %REPO%
takeown /f "%REPO%" /r /d y
if errorlevel 1 goto :fail

echo ==> Cap quyen Full Control cho user hien tai
icacls "%REPO%" /grant "%USERNAME%:(OI)(CI)F" /t
if errorlevel 1 goto :fail

echo ==> Them safe.directory cho Git
git config --global --add safe.directory E:/python-code/188-com-vn

echo.
echo [OK] Da sua quyen. Chay push-git.cmd de commit va push.
pause
exit /b 0

:fail
echo.
echo [LOI] Khong sua duoc quyen. Thu copy repo sang o khac hoac tao lai clone tu GitHub.
pause
exit /b 1
