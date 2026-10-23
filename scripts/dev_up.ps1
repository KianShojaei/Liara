# Windows helper: starts mock Liara (8081), the demo app (3000), the backend (8000) and the UI (5173),
# each in its own PowerShell window. Run from the repository root:  .\scripts\dev_up.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "backend\.venv not found. Run: cd backend; uv venv .venv; uv pip install -p .venv\Scripts\python.exe -e `".[dev]`""; exit 1 }
if (-not (Test-Path (Join-Path $root ".env"))) { Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env"); Write-Host ".env created from .env.example - put your keys there (never in .env.example)." }

# Stop whatever still listens on our ports from a previous run (WinError 10048 otherwise).
function Stop-Port($port) {
  $pids = @()
  try { $pids += (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess) } catch { }
  # Fallback that works without the NetTCPIP module: parse netstat.
  $pids += (netstat -ano | Select-String ":$port\s" | ForEach-Object { ($_ -split '\s+')[-1] })
  foreach ($procId in ($pids | Where-Object { $_ -match '^\d+$' -and $_ -ne '0' } | Sort-Object -Unique)) {
    Write-Host "Stopping process $procId on port $port"
    taskkill /F /PID $procId 2>$null | Out-Null
  }
}
foreach ($port in 8081, 3000, 8000, 5173) { Stop-Port $port }
Start-Sleep 1

# If 8000 is still busy (e.g. a system service), fall back to another backend port.
$backendPort = 8000
try { if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop) { $backendPort = 8010 } } catch { }
if ($backendPort -ne 8000) { Write-Host "Port 8000 still busy; backend will use $backendPort" }

function Start-Window($title, $workdir, $command) {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='$title'; Set-Location '$workdir'; $command"
}

Start-Window "mock-liara" $root "& '$py' -m uvicorn tools.mock_liara.server:app --port 8081"
Start-Window "shop-demo" (Join-Path $root "demo\shop-demo") "if (-not (Test-Path node_modules)) { npm install }; `$env:FAULT_MODE='none'; `$env:PORT='3000'; node src\index.js"
foreach ($i in 1..20) { try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8081/__mock/requests" -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 1 } }
Start-Window "backend" (Join-Path $root "backend") "`$env:DEMO_APP_URL='http://127.0.0.1:3000'; & '$py' -m uvicorn app.main:app --port $backendPort"
Start-Window "frontend" (Join-Path $root "frontend") "if (-not (Test-Path node_modules)) { npm install }; `$env:COPILOT_PORT='$backendPort'; npm run dev"
Start-Sleep 6
Start-Process "http://localhost:5173"
Write-Host "Started: mock :8081, demo :3000, backend :$backendPort, UI http://localhost:5173"
