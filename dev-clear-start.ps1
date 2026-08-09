#Requires -Version 5.1
<#
  Xoá cache, rồi khởi động local: backend (uvicorn), frontend (Next.js), ngrok.
  Cấu hình cổng ở biến bên dưới (mặc định: backend 8001, frontend 3001 — trùng deploy/update-vps.sh 188.com.vn).

  An toàn với Thu-do-online (dev :3000, deploy/update-vps.sh riêng): chỉ dừng process LISTEN trên
  8001/3001 nếu command line thuộc thư mục backend/frontend repo này. Không taskkill toàn bộ node.exe
  trừ khi -KillAllNode (và khi đó vẫn chỉ node/esbuild trong thư mục frontend 188-com-vn).

  Cách chạy:
    powershell -ExecutionPolicy Bypass -File .\dev-clear-start.ps1
    .\dev-clear-start.ps1 -KillAllNode    # chi node/esbuild trong frontend repo nay
    .\dev-clear-start.ps1 -NoNgrok        # bo qua ngrok
    .\dev-clear-start.ps1 -OnlyClean      # chi xoa cache, khong khoi dong
    .\dev-clear-start.ps1 -StopOnly       # chi dong local (nhanh, khong xoa cache)
#>

param(
    [switch]$KillAllNode,
    [switch]$NoNgrok,
    [switch]$OnlyClean,
    [switch]$StopOnly
)

$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# --- Cấu hình ---
$BackendPort  = 8001
$FrontendPort = 3001
# Thu-do-online dev mac dinh :3000 — khong dung cho 188-com-vn (deploy/update-vps.sh Thu-do-online).
$ProtectedForeignPorts = @(3000)

$Root         = $PSScriptRoot
$BackendDir   = Join-Path $Root "backend"
$FrontendDir  = Join-Path $Root "frontend"
$ProjectNeedle = ""
$BackendNeedle = ""
$FrontendNeedle = ""

function Initialize-ProjectNeedles {
    $script:ProjectNeedle = Normalize-PathForMatch $Root
    $script:BackendNeedle = Normalize-PathForMatch $BackendDir
    $script:FrontendNeedle = Normalize-PathForMatch $FrontendDir
}

function Test-ForeignProjectCommandLine([string]$CommandLine) {
    $cmd = ([string]$CommandLine).Replace('\', '/').ToLowerInvariant()
    if (-not $cmd) { return $false }
    # Khong dong process Thu-do-online / NanoAI (deploy/update-vps.sh rieng).
    return ($cmd -like '*thu-do-online*' -or $cmd -like '*thudo-online*')
}

function Test-ProcessBelongsTo188Repo {
    param(
        [int]$ProcessId,
        [ValidateSet('backend', 'frontend', 'any')]
        [string]$Scope = 'any'
    )
    if (-not $ProcessId -or $ProcessId -le 0) { return $false }
    try {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    } catch { return $false }
    $cmd = [string]$p.CommandLine
    if (Test-ForeignProjectCommandLine $cmd) { return $false }
    $norm = $cmd.Replace('\', '/').ToLowerInvariant()
    if (-not $norm) { return $false }
    if ($Scope -eq 'backend') {
        return ($norm -like "*$BackendNeedle*" -or $norm -like "*$ProjectNeedle/backend*")
    }
    if ($Scope -eq 'frontend') {
        return ($norm -like "*$FrontendNeedle*" -or $norm -like "*$ProjectNeedle/frontend*")
    }
    return ($norm -like "*$ProjectNeedle*")
}

function Stop-ProcessOnPortForProject {
    param(
        [int]$Port,
        [ValidateSet('backend', 'frontend')]
        [string]$Scope
    )
    if ($ProtectedForeignPorts -contains $Port) {
        Write-Host ("  Bo qua port {0} (thuoc du an khac, vd Thu-do-online :3000)" -f $Port) -ForegroundColor DarkGray
        return
    }
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return }
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        if (-not (Test-ProcessBelongsTo188Repo -ProcessId $procId -Scope $Scope)) {
            Write-Host ("  Bo qua PID {0} (port {1} - khong thuoc 188-com-vn {2})" -f $procId, $Port, $Scope) -ForegroundColor DarkGray
            continue
        }
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Host ("  Da dung process PID {0} (188-com-vn LISTEN {1})" -f $procId, $Port)
        } catch {
            $errText = if ($null -ne $_.Exception) { $_.Exception.Message } else { $_.ToString() }
            Write-Host ("  Khong the dung PID {0} - {1}" -f $procId, $errText) -ForegroundColor Yellow
        }
    }
}

function Stop-PythonProcessesForDirectory([string]$Dir) {
    if (-not (Test-Path -LiteralPath $Dir)) { return }
    $needle = Normalize-PathForMatch $Dir
    if (-not $needle) { return }
    try { $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue }
    catch { return }
    foreach ($p in @($procs)) {
        $cmd = [string]$p.CommandLine
        if (Test-ForeignProjectCommandLine $cmd) { continue }
        $norm = $cmd.Replace('\', '/').ToLowerInvariant()
        if (-not $norm -or $norm -notlike "*$needle*") { continue }
        if ($norm -notmatch 'uvicorn|main:app') { continue }
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host ("  Da dung python.exe PID {0} (backend 188-com-vn)" -f $p.ProcessId)
        } catch {
            Write-Host ("  Khong the dung python PID {0}" -f $p.ProcessId) -ForegroundColor Yellow
        }
    }
}

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

# Chi dung ngrok forward toi dung local port (vd ngrok http 3001). Khong dong tunnel khac port.
function Stop-NgrokForwardingLocalPort([int]$LocalPort) {
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name = 'ngrok.exe'" -ErrorAction SilentlyContinue
    } catch { return }
    if (-not $procs) { return }
    $esc = [regex]::Escape([string]$LocalPort)
    # Vi du CLI: ngrok http 3001  |  ngrok.exe http 3001 --region=...
    $rx = "(?i)\s$esc(?:\s|$|[`"])"
    foreach ($p in @($procs)) {
        $cmd = [string]$p.CommandLine
        if ([string]::IsNullOrWhiteSpace($cmd)) { continue }
        if ($cmd -notmatch $rx) { continue }
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host ("  Da dung ngrok.exe PID {0} (forward toi localhost:{1})" -f $p.ProcessId, $LocalPort)
        } catch {
            Write-Host ("  Khong the dung ngrok PID {0}" -f $p.ProcessId) -ForegroundColor Yellow
        }
    }
}

function Normalize-PathForMatch([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    try { $x = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path }
    catch { $x = $Path }
    return ($x.TrimEnd('\', '/')).Replace('\', '/').ToLowerInvariant()
}

function Stop-NodeProcessesForDirectory([string]$Dir) {
    if (-not (Test-Path -LiteralPath $Dir)) { return }
    $needle = Normalize-PathForMatch $Dir
    if (-not $needle) { return }
    try { $procs = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue }
    catch { $procs = $null }
    if (-not $procs) { return }
    foreach ($p in @($procs)) {
        $cmd = ([string]$p.CommandLine)
        if (Test-ForeignProjectCommandLine $cmd) { continue }
        $cmd = $cmd.Replace('\', '/').ToLowerInvariant()
        if (-not $cmd) { continue }
        if ($cmd -notlike "*$needle*") { continue }
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host ("  Da dung node.exe PID {0} (lien quan frontend)" -f $p.ProcessId)
        } catch {
            Write-Host ("  Khong the dung node PID {0}" -f $p.ProcessId) -ForegroundColor Yellow
        }
    }
}

function Stop-EsbuildForDirectory([string]$Dir) {
    $needle = Normalize-PathForMatch $Dir
    if (-not $needle) { return }
    try { $procs = Get-CimInstance Win32_Process -Filter "Name = 'esbuild.exe'" -ErrorAction SilentlyContinue }
    catch { return }
    foreach ($p in @($procs)) {
        $cmd = ([string]$p.CommandLine)
        if (Test-ForeignProjectCommandLine $cmd) { continue }
        $cmd = $cmd.Replace('\', '/').ToLowerInvariant()
        if (-not $cmd) { continue }
        if ($cmd -notlike "*$needle*") { continue }
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host ("  Da dung esbuild.exe PID {0}" -f $p.ProcessId)
        } catch { }
    }
}

function Clear-DirWithRobocopy([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    $parent = Split-Path -Parent $Path
    if (-not $parent) { return $false }
    $stamp = [Guid]::NewGuid().ToString('N').Substring(0, 12)
    $empty = Join-Path $parent ("__empty_robocopy_$stamp")
    try {
        New-Item -ItemType Directory -Path $empty -Force | Out-Null
        $null = & robocopy.exe $empty $Path /MIR /NFL /NDL /NJH /NJS /NP /R:0 /W:0
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return $true
    } catch { return $false }
    finally { Remove-Item -LiteralPath $empty -Force -Recurse -ErrorAction SilentlyContinue }
}

function Remove-DirViaCmd([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    $quoted = '"' + ($Path -replace '/', '\') + '"'
    $null = & cmd.exe /c "rd /s /q $quoted 2>nul"
    return -not (Test-Path -LiteralPath $Path)
}

function Try-ResetAclForTree([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $user = $env:USERNAME
    if (-not $user) { return }
    $null = & takeown.exe /F $Path /R /D Y 2>$null
    $grant = "${user}:(OI)(CI)F"
    $null = & icacls.exe $Path /grant $grant /T /C /Q 2>$null
}

function Move-DirAsideStale([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $parent = Split-Path -Parent $Path
    $leaf = Split-Path -Leaf $Path
    $dest = Join-Path $parent ('{0}.stale.{1}' -f $leaf, (Get-Date -Format 'yyyyMMdd-HHmmss'))
    try {
        Move-Item -LiteralPath $Path -Destination $dest -Force -ErrorAction Stop
        Write-Host ("  OK: Da doi ten {0} -> {1} (Next se tao moi). Co the xoa thu muc *.stale sau." -f $Label, (Split-Path -Leaf $dest)) -ForegroundColor Green
        return $true
    } catch { return $false }
}

function Remove-DirIfExists([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Host "  Bo qua (khong co): $Label"
        return
    }
    $max = 6
    for ($i = 0; $i -lt $max; $i++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            Write-Host "  Da xoa: $Label"
            return
        } catch {
            if ($i -lt $max - 1) {
                Write-Host ("  Chua xoa duoc {0}, cho giai phong file ({1}/{2})..." -f $Label, ($i + 1), $max) -ForegroundColor Yellow
                Start-Sleep -Seconds 2
            } else {
                Write-Host "  Thu robocopy de lam rong thu muc..." -ForegroundColor Yellow
                if (Clear-DirWithRobocopy -Path $Path) { Write-Host "  Da xoa: $Label (sau robocopy)"; return }
                Write-Host "  Thu takeown/icacls + xoa lai..." -ForegroundColor Yellow
                Try-ResetAclForTree -Path $Path
                Start-Sleep -Seconds 1
                if (Remove-DirViaCmd -Path $Path) { Write-Host "  Da xoa: $Label (sau rd /s /q)"; return }
                try {
                    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
                    Write-Host "  Da xoa: $Label (sau icacls)"; return
                } catch { }
                Write-Host "  Thu doi ten thu muc (giai phong .next cho Next)..." -ForegroundColor Yellow
                if (Move-DirAsideStale -Path $Path -Label $Label) { return }
                Write-Host "  LOI: Khong xoa/doi ten duoc $Label. Chay lai script hoac dong Cursor roi xoa tay." -ForegroundColor Red
            }
        }
    }
}

# ===========================================================================
Initialize-ProjectNeedles

Write-Step "Giai phong port 188-com-vn (LISTEN $BackendPort backend, $FrontendPort frontend) - bo qua Thu-do-online :3000..."
Stop-ProcessOnPortForProject -Port $BackendPort -Scope 'backend'
Stop-ProcessOnPortForProject -Port $FrontendPort -Scope 'frontend'
Stop-PythonProcessesForDirectory -Dir $BackendDir
Stop-NgrokForwardingLocalPort -LocalPort $FrontendPort

Write-Step "Dung node.exe lien quan thu muc frontend 188-com-vn (giai phong lock .next)..."
if ($KillAllNode) {
    Write-Host "  -KillAllNode: chi node/esbuild trong frontend repo nay (khong dong Thu-do-online)." -ForegroundColor Yellow
    if (Test-Path $FrontendDir) {
        Stop-NodeProcessesForDirectory -Dir $FrontendDir
        Stop-EsbuildForDirectory -Dir $FrontendDir
        Start-Sleep -Seconds 1
        Stop-NodeProcessesForDirectory -Dir $FrontendDir
        Stop-EsbuildForDirectory -Dir $FrontendDir
    }
    Start-Sleep -Seconds 2
} elseif (Test-Path $FrontendDir) {
    Stop-NodeProcessesForDirectory -Dir $FrontendDir
    Stop-EsbuildForDirectory -Dir $FrontendDir
    Start-Sleep -Seconds 1
    Stop-NodeProcessesForDirectory -Dir $FrontendDir
    Stop-EsbuildForDirectory -Dir $FrontendDir
}
Start-Sleep -Seconds 1

if ($StopOnly) {
    Write-Host ""
    Write-Host "Xong (-StopOnly). Da dong backend/frontend local 188-com-vn." -ForegroundColor Green
    exit 0
}

Start-Sleep -Seconds 2

Write-Step "Xoa cache frontend (Next.js)..."
if (Test-Path $FrontendDir) {
    Remove-DirIfExists (Join-Path $FrontendDir ".next") ".next"
    Remove-DirIfExists (Join-Path $FrontendDir ".next-dev") ".next-dev"
    Remove-DirIfExists (Join-Path $FrontendDir ".next-run") ".next-run"
    Remove-DirIfExists (Join-Path $FrontendDir "node_modules\.cache") "node_modules\.cache"
    Remove-DirIfExists (Join-Path $FrontendDir ".turbo") ".turbo"
} else {
    Write-Host "  KHONG tim thay thu muc frontend: $FrontendDir" -ForegroundColor Red
}

Write-Step "Xoa cache Python (backend)..."
if (Test-Path $BackendDir) {
    Get-ChildItem -Path $BackendDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    Write-Host "  Da xoa cac thu muc __pycache__ duoi backend"
    foreach ($name in @(".pytest_cache", ".mypy_cache", ".ruff_cache")) {
        $p = Join-Path $BackendDir $name
        if (Test-Path $p) {
            Remove-Item $p -Recurse -Force
            Write-Host "  Da xoa: $name"
        }
    }
} else {
    Write-Host "  KHONG tim thay thu muc backend: $BackendDir" -ForegroundColor Red
}

if ($OnlyClean) {
    Write-Host ""
    Write-Host "Xong (-OnlyClean). Bo qua khoi dong backend/frontend/ngrok." -ForegroundColor Green
    exit 0
}

# Cảnh báo nếu .env.local đang trỏ production — gây 503/treo upload khi dev local.
$envLocal = Join-Path $FrontendDir ".env.local"
if (Test-Path -LiteralPath $envLocal) {
    $envText = Get-Content -LiteralPath $envLocal -Raw -ErrorAction SilentlyContinue
    if ($envText -match '(?im)^\s*NEXT_PUBLIC_API_BASE_URL\s*=\s*https?://[^/\s#]*188\.com\.vn') {
        Write-Host ""
        Write-Host "  [!] frontend/.env.local dang tro https://188.com.vn/api/v1." -ForegroundColor Yellow
        Write-Host "      DEV LOCAL nen dung http://localhost:${BackendPort}/api/v1 de tranh 503/treo upload." -ForegroundColor Yellow
    }
}

$NodeDir      = Join-Path $env:LOCALAPPDATA "Programs\nodejs"
$NgrokDir     = Join-Path $env:LOCALAPPDATA "Programs\ngrok"
$PythonDir    = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"
$PythonScripts = Join-Path $PythonDir "Scripts"

function Get-DevPathPrefix {
    $parts = @($NodeDir, $NgrokDir, $PythonDir, $PythonScripts) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    if (-not $parts) { return "" }
    return ('set "PATH=' + (($parts -join ';') + ';%PATH%" && '))
}

# Mỗi cửa sổ CMD chạy 1 chuỗi lệnh: `cd ... && <lệnh>` — dùng `cmd.exe /c start "TITLE" cmd /k "..."` để set title.
function Start-CmdWindow([string]$Title, [string]$Command) {
    $cmd = (Get-DevPathPrefix) + $Command
    # Truyền cmd /c "start "TITLE" cmd /k <cmd>" qua Start-Process — tránh PowerShell tự động xử lý '&'.
    $payload = 'start "' + $Title + '" cmd.exe /k "' + $cmd + '"'
    Start-Process cmd.exe -ArgumentList @('/c', $payload) -WindowStyle Normal
}

Write-Step "Khoi dong backend (port $BackendPort)..."
if (Test-Path (Join-Path $BackendDir "main.py")) {
    $venvPy = Join-Path $BackendDir ".venv\Scripts\python.exe"
    $pyExe = if (Test-Path -LiteralPath $venvPy) { ('"' + $venvPy + '"') } else { "python" }
    # Không dùng --reload trên Windows local: reloader có thể để lại nhiều child process
    # cùng giữ port 8001, khiến UI gọi vào process cũ chưa nạp patch Playwright.
    $beCmd = 'cd /d "' + $BackendDir + '" && ' + $pyExe + ' -m uvicorn main:app --host 0.0.0.0 --port ' + $BackendPort
    Start-CmdWindow -Title ("BACKEND " + $BackendPort) -Command $beCmd
} else {
    Write-Host "  Khong co backend\main.py" -ForegroundColor Red
}

Write-Step "Khoi dong frontend (port $FrontendPort)..."
if (Test-Path (Join-Path $FrontendDir "package.json")) {
    # package.json: "dev" = node scripts/next-dev.cjs (ep -p 3001).
    $feCmd = 'cd /d "' + $FrontendDir + '" && set NEXT_DIST_DIR=.next-run&& npm run dev'
    Start-CmdWindow -Title ("FRONTEND " + $FrontendPort) -Command $feCmd
} else {
    Write-Host "  Khong co frontend\package.json" -ForegroundColor Red
}

Start-Sleep -Seconds 2

if ($NoNgrok) {
    Write-Host ""
    Write-Host "Bo qua ngrok (-NoNgrok)." -ForegroundColor DarkGray
} else {
    Write-Step "Khoi dong ngrok (http -> frontend port $FrontendPort)..."
    $ngrokPath = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($ngrokPath) {
        $ngCmd = 'ngrok http ' + $FrontendPort
        Start-CmdWindow -Title ("NGROK " + $FrontendPort) -Command $ngCmd
    } else {
        Write-Host "  KHONG tim thay 'ngrok' trong PATH. Bo qua. Dung -NoNgrok de an canh bao." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Xong. Kiem tra cua so CMD: BACKEND / FRONTEND / NGROK (neu co)." -ForegroundColor Green
Write-Host "  Thu-do-online (:3000) va deploy/update-vps.sh cua du an do - khong bi script nay dong." -ForegroundColor DarkGray
Write-Host "  API:      http://127.0.0.1:${BackendPort}/docs" -ForegroundColor Gray
Write-Host "  Web:      http://localhost:${FrontendPort}/admin/products" -ForegroundColor Gray
Write-Host "  Health:   curl http://127.0.0.1:${BackendPort}/health" -ForegroundColor DarkGray
