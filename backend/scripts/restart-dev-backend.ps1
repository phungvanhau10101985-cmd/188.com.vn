# Dừng process chiếm cổng 8001 và khởi động lại FastAPI dev (có newsletter + warm-up).
$ErrorActionPreference = "Continue"
$port = 8001
$backendDir = Split-Path -Parent $PSScriptRoot

Write-Host "==> Tim process dang listen port $port..."
$pids = @()
try {
  $pids = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
} catch {
  $pids = netstat -ano | Select-String ":$port\s+.*LISTENING" | ForEach-Object {
    ($_ -split '\s+')[-1]
  } | Sort-Object -Unique
}

foreach ($procId in $pids) {
  if ($procId -match '^\d+$' -and [int]$procId -gt 0) {
    Write-Host "==> Dung PID $procId..."
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    taskkill /F /PID $procId 2>$null | Out-Null
  }
}

Start-Sleep -Seconds 2

Write-Host "==> Khoi dong uvicorn tai $backendDir ..."
Set-Location $backendDir
python -m uvicorn main:app --host 127.0.0.1 --port $port --reload
