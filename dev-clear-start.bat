@echo off
REM Chay dev-clear-start.ps1: xoa cache, roi mo backend uvicorn + Next + ngrok.
REM Cong mac dinh trong .ps1: API 8001, frontend 3001 (dong bo voi frontend/package.json va NEXT_PUBLIC_*).
REM Vi du: dev-clear-start.bat
REM        dev-clear-start.bat -KillAllNode   (tat node.exe/esbuild lien quan; can than cac Node khac)
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev-clear-start.ps1" %*
if errorlevel 1 pause
exit /b %errorlevel%
