@echo off
REM ============================================================
REM  dev-clear-start.bat — DEV LOCAL 188.com.vn
REM  - Giai phong LISTEN tren port backend/frontend (mac dinh 8001 + 3001); chi tat ngrok neu CLI forward dung port frontend
REM  - Khoi dong backend uvicorn (8001) + Next (3001) + ngrok (neu co)
REM
REM  Cach dung:
REM    dev-clear-start.bat                   (chay binh thuong)
REM    dev-clear-start.bat -KillAllNode      (tat HET node.exe — can than)
REM    dev-clear-start.bat -NoNgrok          (khong mo ngrok)
REM    dev-clear-start.bat -OnlyClean        (chi xoa cache, khong khoi dong)
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev-clear-start.ps1" %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
    echo.
    echo [!] Script ket thuc voi loi %EC%. Xem thong bao tren cua so PowerShell.
    pause
)
exit /b %EC%
