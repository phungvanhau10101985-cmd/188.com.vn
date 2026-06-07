# Update DATABASE_POOL_* and category cache TTL in backend/.env (Windows).
# Usage: powershell -File deploy/apply-db-pool.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root "backend\.env"

if (-not (Test-Path $EnvFile)) {
    $Example = Join-Path $Root "backend\.env.example"
    if (-not (Test-Path $Example)) {
        Write-Error "Missing backend\.env - copy from backend\.env.example first."
    }
    Copy-Item $Example $EnvFile
    Write-Host "+ created backend\.env from .env.example"
}

$bak = "${EnvFile}.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
Copy-Item $EnvFile $bak
Write-Host "Backup: $bak"

$settings = [ordered]@{
    DATABASE_POOL_SIZE                               = "10"
    DATABASE_MAX_OVERFLOW                            = "15"
    DATABASE_POOL_TIMEOUT                            = "20"
    DATABASE_POOL_RECYCLE                            = "1800"
    DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS   = "35"
    DATABASE_STATEMENT_TIMEOUT_SECONDS               = "0"
    DATABASE_POOL_RELIEF_ENABLED                     = "true"
    DATABASE_POOL_RELIEF_INTERVAL_SECONDS            = "15"
    DATABASE_POOL_RELIEF_MIN_IDLE_SECONDS            = "22"
    DATABASE_POOL_RELIEF_AGGRESSIVE_MIN_IDLE_SECONDS = "18"
    DATABASE_POOL_RELIEF_TRIGGER_IDLE_COUNT          = "14"
    CATEGORY_MENU_TREE_TTL_SECONDS                   = "600"
    CATEGORY_CATALOG_TILES_TTL_SECONDS               = "600"
    SETTINGS_DB_PROBE_ON_LOAD                        = "false"
}

$lines = [System.Collections.Generic.List[string]]@(Get-Content $EnvFile -Encoding UTF8)
$addedAny = $false

foreach ($key in $settings.Keys) {
    $val = $settings[$key]
    $pat = "^\s*$([regex]::Escape($key))="
    $idx = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pat) {
            $idx = $i
            break
        }
    }
    if ($idx -ge 0) {
        $lines[$idx] = "${key}=${val}"
        Write-Host "updated ${key}=${val}"
    } else {
        if (-not $addedAny) {
            if ($lines.Count -gt 0 -and $lines[-1].Trim() -ne "") { $lines.Add("") }
            $lines.Add("# DB tuning (pool 25 + idle-in-xact relief)")
            $addedAny = $true
        }
        $lines.Add("${key}=${val}")
        Write-Host "added   ${key}=${val}"
    }
}

Set-Content -Path $EnvFile -Value $lines -Encoding UTF8
Write-Host ""
Write-Host "Done: $EnvFile"
Write-Host "Local: restart uvicorn. VPS: bash deploy/relieve-db-after-restart.sh"
