@echo off
REM Chay script PowerShell: xoa cache, khoi dong backend + frontend + ngrok.
REM Vi du: dev-clear-start.bat
REM        dev-clear-start.bat -KillAllNode   (dung moi node.exe / esbuild — dong het project Node khac truoc)
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev-clear-start.ps1" %*
if errorlevel 1 pause
exit /b %errorlevel%
