#Requires -Version 5.1
<#
  Push code len GitHub (origin/main) — du an 188.com.vn

  Cach chay:
    powershell -ExecutionPolicy Bypass -File .\push-git.ps1
    powershell -ExecutionPolicy Bypass -File .\push-git.ps1 -Message "Sua import 1688"
    .\push-git.ps1 -StatusOnly

  Neu loi quyen ghi .git: chay fix-git-ownership.cmd (Run as administrator) mot lan.
#>

param(
    [string]$Message = "Cap nhat du an",
    [switch]$StatusOnly
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = $PSScriptRoot
$GitExe = @(
    "C:\Program Files\Git\cmd\git.exe",
    "C:\Program Files (x86)\Git\cmd\git.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $GitExe) {
    Write-Host "[LOI] Khong tim thay git.exe. Cai Git for Windows hoac them vao PATH." -ForegroundColor Red
    exit 1
}

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Invoke-Git {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$GitArgs
    )
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = & $GitExe @GitArgs 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($out) { $out | ForEach-Object { Write-Host $_ } }
    if ($code -ne 0) {
        $text = ($out | Out-String)
        if ($text -match 'dubious ownership|unable to write new index|Permission denied') {
            Write-Host ""
            Write-Host "[LOI] Git khong ghi duoc thu muc .git - chay fix-git-ownership.cmd (Run as administrator) mot lan." -ForegroundColor Red
        }
        throw "git $($GitArgs -join ' ') failed ($code)"
    }
}

Set-Location $Root

Write-Step "Cau hinh safe.directory (mot lan, an toan khi chay lai)"
& $GitExe config --global --add safe.directory "E:/python-code/188-com-vn" 2>$null

Write-Step "Trang thai repo"
Invoke-Git status

if ($StatusOnly) { exit 0 }

try {
    Write-Step "Stage thay doi (bo qua file Excel tam o thu muc goc)"
    $paths = @(
        "backend",
        "frontend",
        "dev-clear-start.ps1",
        "fix-git-ownership.cmd",
        "push-git.cmd",
        "push-git.ps1"
    )
    foreach ($p in $paths) {
        if (Test-Path (Join-Path $Root $p)) {
            Invoke-Git add -A -- $p
        }
    }
    Invoke-Git add -u

    $staged = & $GitExe diff --cached --name-only
    if (-not $staged) {
        Write-Host ""
        Write-Host "[INFO] Khong co thay doi de commit. Push neu da commit truoc do..." -ForegroundColor Yellow
    }
    else {
        Write-Step "Commit: $Message"
        Invoke-Git commit -m $Message
    }

    Write-Step "Push len origin/main"
    Invoke-Git push -u origin main

    Write-Step "Xong"
    Invoke-Git log -1 --oneline
    Invoke-Git status -sb
}
catch {
    Write-Host ""
    Write-Host $_ -ForegroundColor Red
    exit 1
}
