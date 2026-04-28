#Requires -Version 5.1
<#
  Xoá cache, rồi khởi động local: backend (uvicorn), frontend (Next.js), ngrok.
  Cấu hình cổng ở biến bên dưới (mặc định: backend 8000, frontend 3000; trùng với .env / NEXT_PUBLIC_API_BASE_URL).
  Chạy: powershell -ExecutionPolicy Bypass -File .\dev-clear-start.ps1
  Nếu .next vẫn khóa: powershell -ExecutionPolicy Bypass -File .\dev-clear-start.ps1 -KillAllNode
    (dừng mọi node.exe trên máy — đóng hết dự án Node khác trước khi chạy)
#>

param(
    [switch]$KillAllNode
)

$ErrorActionPreference = "Continue"

# --- Cấu hình ---
$BackendPort  = 8000
$FrontendPort = 3000
# ngrok mở tunnel tới frontend (cùng cổng dev Next)

$Root         = $PSScriptRoot
$BackendDir   = Join-Path $Root "backend"
$FrontendDir  = Join-Path $Root "frontend"

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Stop-ProcessOnPort([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conns) { return }
    $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $pids) {
        if ($procId -and $procId -ne 0) {
            try {
                Stop-Process -Id $procId -Force -ErrorAction Stop
                Write-Host ('  Da dung process PID {0} (port {1})' -f $procId, $Port)
            } catch {
                $errText = if ($null -ne $_.Exception) { $_.Exception.Message } else { $_.ToString() }
                Write-Host ('  Khong the dung PID {0} - {1}' -f $procId, $errText) -ForegroundColor Yellow
            }
        }
    }
}

function Normalize-PathForMatch([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return '' }
    try {
        $x = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    } catch {
        $x = $Path
    }
    return ($x.TrimEnd('\', '/')).Replace('\', '/').ToLowerInvariant()
}

# Next/Webpack giữ lock trong .next; cần dừng mọi node.exe có command line trỏ tới thư mục frontend (so khớp không phân biệt hoa thường).
function Stop-NodeProcessesForDirectory([string]$Dir) {
    if (-not (Test-Path -LiteralPath $Dir)) { return }
    $needle = Normalize-PathForMatch $Dir
    if (-not $needle) { return }
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue
    } catch {
        $procs = $null
    }
    if (-not $procs) { return }
    foreach ($p in @($procs)) {
        $cmd = ([string]$p.CommandLine).Replace('\', '/').ToLowerInvariant()
        if (-not $cmd) { continue }
        if ($cmd -notlike "*$needle*") { continue }
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host ('  Da dung node.exe PID {0} (lien quan frontend)' -f $p.ProcessId)
        } catch {
            Write-Host ('  Khong the dung node PID {0}' -f $p.ProcessId) -ForegroundColor Yellow
        }
    }
}

# Xóa thư mục “cứng đầu” trên Windows: làm rỗng bằng robocopy MIR rồi rmdir.
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
    } catch {
        return $false
    } finally {
        Remove-Item -LiteralPath $empty -Force -Recurse -ErrorAction SilentlyContinue
    }
}

# rd /s /q đôi khi xóa được khi Remove-Item báo lỗi.
function Remove-DirViaCmd([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    $quoted = '"' + ($Path -replace '/', '\') + '"'
    $null = & cmd.exe /c "rd /s /q $quoted 2>nul"
    return -not (Test-Path -LiteralPath $Path)
}

# Cấp quyền cho user hiện tại (cần quyền admin một số máy; lỗi thì bỏ qua).
function Try-ResetAclForTree([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $user = $env:USERNAME
    if (-not $user) { return }
    $null = & takeown.exe /F $Path /R /D Y 2>$null
    $grant = "${user}:(OI)(CI)F"
    $null = & icacls.exe $Path /grant $grant /T /C /Q 2>$null
}

# Đổi tên thư mục: Next.js vẫn chạy bình thường với .next mới; thư mục cũ xóa sau.
function Move-DirAsideStale([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $parent = Split-Path -Parent $Path
    $leaf = Split-Path -Leaf $Path
    $dest = Join-Path $parent ('{0}.stale.{1}' -f $leaf, (Get-Date -Format 'yyyyMMdd-HHmmss'))
    try {
        Move-Item -LiteralPath $Path -Destination $dest -Force -ErrorAction Stop
        Write-Host ('  OK: Da doi ten {0} -> {1} — Next se tao {0} moi. Ban co the xoa thu muc *.stale sau khi dong Cursor.' -f $Label, (Split-Path -Leaf $dest)) -ForegroundColor Green
        return $true
    } catch {
        return $false
    }
}

function Stop-EsbuildForDirectory([string]$Dir) {
    $needle = Normalize-PathForMatch $Dir
    if (-not $needle) { return }
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name = 'esbuild.exe'" -ErrorAction SilentlyContinue
    } catch {
        return
    }
    foreach ($p in @($procs)) {
        $cmd = ([string]$p.CommandLine).Replace('\', '/').ToLowerInvariant()
        if (-not $cmd) { continue }
        if ($cmd -notlike "*$needle*") { continue }
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            Write-Host ('  Da dung esbuild.exe PID {0}' -f $p.ProcessId)
        } catch { }
    }
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
                Write-Host ('  Chua xoa duoc {0}, cho giai phong file ({1}/{2})...' -f $Label, ($i + 1), $max) -ForegroundColor Yellow
                Start-Sleep -Seconds 2
            } else {
                Write-Host "  Thu robocopy de lam rong thu muc (Windows)..." -ForegroundColor Yellow
                if (Clear-DirWithRobocopy -Path $Path) {
                    Write-Host "  Da xoa: $Label (sau robocopy)"
                    return
                }
                Write-Host "  Thu takeown/icacls + xoa lai..." -ForegroundColor Yellow
                Try-ResetAclForTree -Path $Path
                Start-Sleep -Seconds 1
                if (Remove-DirViaCmd -Path $Path) {
                    Write-Host "  Da xoa: $Label (sau rd /s /q)"
                    return
                }
                try {
                    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
                    Write-Host "  Da xoa: $Label (sau icacls)"
                    return
                } catch { }
                Write-Host "  Thu doi ten thu muc (giai phong ten .next cho Next)..." -ForegroundColor Yellow
                if (Move-DirAsideStale -Path $Path -Label $Label) { return }
                Write-Host "  LOI: Van khong xoa/doi ten duoc $Label. Chay: .\dev-clear-start.ps1 -KillAllNode (va dong het cua so CMD dang npm run dev), hoac thoat Cursor roi xoa/ doi ten tay thu muc .next." -ForegroundColor Red
            }
        }
    }
}

Write-Step "Dang giai phong port $BackendPort, $FrontendPort va dung ngrok cu..."
Stop-ProcessOnPort -Port $BackendPort
Stop-ProcessOnPort -Port $FrontendPort
$ng = Get-Process -Name "ngrok" -ErrorAction SilentlyContinue
if ($ng) {
    $ng | Stop-Process -Force
    Write-Host "  Da dung ngrok.exe"
}

Write-Step "Dung node.exe lien quan thu muc frontend (giai phong lock .next)..."
if ($KillAllNode) {
    Write-Host "  -KillAllNode: taskkill node.exe, esbuild.exe ..." -ForegroundColor Yellow
    $null = & taskkill.exe /F /IM node.exe /T 2>$null
    $null = & taskkill.exe /F /IM esbuild.exe /T 2>$null
    Start-Sleep -Seconds 2
} elseif (Test-Path $FrontendDir) {
    Stop-NodeProcessesForDirectory -Dir $FrontendDir
    Stop-EsbuildForDirectory -Dir $FrontendDir
    Start-Sleep -Seconds 1
    Stop-NodeProcessesForDirectory -Dir $FrontendDir
    Stop-EsbuildForDirectory -Dir $FrontendDir
}
Start-Sleep -Seconds 5

Write-Step "Xoa cache frontend (Next.js)..."
if (Test-Path $FrontendDir) {
    Remove-DirIfExists (Join-Path $FrontendDir ".next") ".next"
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

Write-Step "Khoi dong backend (port $BackendPort)..."
if (Test-Path (Join-Path $BackendDir "main.py")) {
    $backendCmd = "cd /d `"$BackendDir`" && python -m uvicorn main:app --reload --host 0.0.0.0 --port $BackendPort"
    Start-Process cmd -ArgumentList @("/k", $backendCmd) -WindowStyle Normal
} else {
    Write-Host "  Khong co backend\main.py" -ForegroundColor Red
}

Write-Step "Khoi dong frontend (port $FrontendPort)..."
if (Test-Path (Join-Path $FrontendDir "package.json")) {
    $feCmd = "cd /d `"$FrontendDir`" && npm run dev -- -p $FrontendPort"
    Start-Process cmd -ArgumentList @("/k", $feCmd) -WindowStyle Normal
} else {
    Write-Host "  Khong co frontend\package.json" -ForegroundColor Red
}

Start-Sleep -Seconds 2

Write-Step "Khoi dong ngrok (http -> frontend port $FrontendPort)..."
$ngrokPath = Get-Command ngrok -ErrorAction SilentlyContinue
if ($ngrokPath) {
    $ngCmd = "ngrok http $FrontendPort"
    Start-Process cmd -ArgumentList @("/k", $ngCmd) -WindowStyle Normal
} else {
    Write-Host "  KHONG tim thay 'ngrok' trong PATH. Cai dat hoac them vao PATH." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Xong. Kiem tra cua so CMD: BACKEND, FRONTEND, ngrok." -ForegroundColor Green
Write-Host "  API:  http://127.0.0.1:$BackendPort/docs" -ForegroundColor Gray
Write-Host "  Web:  http://127.0.0.1:$FrontendPort" -ForegroundColor Gray
