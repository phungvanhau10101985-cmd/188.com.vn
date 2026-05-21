@echo off
chcp 65001 >nul
cd /d "%~dp0"

if "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0push-git.ps1"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0push-git.ps1" -Message "%*"
)

if errorlevel 1 pause
