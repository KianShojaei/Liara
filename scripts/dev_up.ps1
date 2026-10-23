# Windows helper: starts mock Liara (8081), the demo app (3000), the backend (8000) and the UI (5173),
# each in its own PowerShell window. Run from the repository root:  .\scripts\dev_up.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "backend\.venv not found. Run: cd backend; uv venv .venv; uv pip install -p .venv\Scripts\python.exe -e `".[dev]`""; exit 1 }
if (-not (Test-Path (Join-Path $root ".env"))) { Copy-Item (Join-Path $root ".env.example") (Join-Path $root ".env"); Write-Host ".env created from .env.example - put your keys there (never in .env.example)." }

# Stop whatever still listens on our ports from a previous run (WinError 10048 otherwise).
foreach ($port in 8081, 3000, 8000, 5173) {
  try {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop | ForEach-Object {
      Write-Host "Stopping process $($_.OwningProcess) on port $port"
      Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
  } catch { }
}
Start-Sleep 1

function Start-Window($title, $workdir, $command) {
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.UI.RawUI.WindowTitle='$title'; Set-Location '$workdir'; $command"
}

Start-Window "mock-liara" $root "& '$py' -m uvicorn tools.mock_liara.server:app --port 8081"
Start-Window "shop-demo" (Join-Path $root "demo\shop-demo") "if (-not (Test-Path node_modules)) { npm install }; `$env:FAULT_MODE='none'; `$env:PORT='3000'; node src\index.js"
foreach ($i in 1..20) { try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8081/__mock/requests" -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 1 } }
Start-Window "backend" (Join-Path $root "backend") "`$env:DEMO_APP_URL='http://127.0.0.1:3000'; & '$py' -m uvicorn app.main:app --port 8000"
Start-Window "frontend" (Join-Path $root "frontend") "if (-not (Test-Path node_modules)) { npm install }; npm run dev"
Start-Sleep 6
Start-Process "http://localhost:5173"
Write-Host "Started: mock :8081, demo :3000, backend :8000, UI http://localhost:5173"
