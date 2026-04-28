@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================
echo   CHAY DU AN 1 (188-com-vn)
echo ========================================
echo.

REM ========================
REM CẤU HÌNH DỰ ÁN 1 (DỰ ÁN NÀY)
REM ========================
set "PROJECT1_ROOT=G:\python-code\188-com-vn"
set "PROJECT1_FRONTEND_DIR=%PROJECT1_ROOT%\frontend"
set "PROJECT1_BACKEND_DIR=%PROJECT1_ROOT%\backend"
set "PROJECT1_FRONTEND_CMD=npm run dev -- -p 3002"
set "PROJECT1_BACKEND_CMD=python -m uvicorn main:app --reload --port 8002"
set "PROJECT1_NGROK_PORT=3002"

REM ========================
REM CẤU HÌNH DỰ ÁN 2 (DỰ ÁN KHÁC)
REM ========================
set "PROJECT2_ROOT=G:\python-code\Thu-do-online"
set "PROJECT2_FRONTEND_DIR=%PROJECT2_ROOT%"
set "PROJECT2_BACKEND_DIR=%PROJECT2_ROOT%\backend"
set "PROJECT2_FRONTEND_CMD=npm run dev -- -p 3001"
set "PROJECT2_BACKEND_CMD=python -m uvicorn main:app --reload --port 8001"
set "PROJECT2_NGROK_PORT=3001"

REM ========================
REM DỪNG HẾT PROCESS CŨ
REM ========================
echo [1/4] Dung tat ca Node.js, tsx, ngrok, uvicorn...
taskkill /F /IM node.exe 2>nul
taskkill /F /IM ngrok.exe 2>nul
taskkill /F /IM tsx.exe 2>nul
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul
echo       Da dung
echo.

goto RUN_PROJECT1

REM ========================
REM RUN PROJECT 1
REM ========================
:RUN_PROJECT1
echo [2/4] Xoa cache du an 1...
echo       FRONTEND: %PROJECT1_FRONTEND_DIR%
echo       BACKEND:  %PROJECT1_BACKEND_DIR%
if exist "%PROJECT1_FRONTEND_DIR%\.next" (
    rmdir /s /q "%PROJECT1_FRONTEND_DIR%\.next"
    echo       .next da xoa
) else (
    echo       .next khong ton tai
)
if exist "%PROJECT1_FRONTEND_DIR%\node_modules\.cache" (
    rmdir /s /q "%PROJECT1_FRONTEND_DIR%\node_modules\.cache"
    echo       node_modules\.cache da xoa
) else (
    echo       Khong co node_modules\.cache
)
if exist "%PROJECT1_FRONTEND_DIR%\.turbo" (
    rmdir /s /q "%PROJECT1_FRONTEND_DIR%\.turbo"
    echo       .turbo da xoa
) else (
    echo       Khong co .turbo
)
echo.
echo [3/4] Khoi dong du an 1...
if exist "%PROJECT1_BACKEND_DIR%\main.py" (
    start "PROJECT1 BACKEND" cmd /k "cd /d "%PROJECT1_BACKEND_DIR%" && %PROJECT1_BACKEND_CMD%"
) else (
    echo       Khong tim thay backend du an 1
)
if exist "%PROJECT1_FRONTEND_DIR%\package.json" (
    start "PROJECT1 FRONTEND" cmd /k "cd /d "%PROJECT1_FRONTEND_DIR%" && %PROJECT1_FRONTEND_CMD%"
) else (
    echo       Khong tim thay frontend du an 1
)
echo       Du an 1 dang khoi dong...
timeout /t 3 /nobreak >nul
echo.
echo [4/4] Khoi dong ngrok...
start "ngrok-3000" cmd /k "ngrok http %PROJECT1_NGROK_PORT%"
:END
echo.
echo ========================================
echo   XONG. DA KHOI DONG DU AN.
echo ========================================
pause
