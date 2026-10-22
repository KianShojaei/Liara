#!/usr/bin/env bash
# Dev helper: start mock Liara, the demo app and the backend in the background (logs in /tmp).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/backend/.venv/bin/python"
pkill -f "tools.mock_liara.server" 2>/dev/null || true
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "shop-demo/src/index.js" 2>/dev/null || true
sleep 1
(cd "$ROOT" && nohup "$PY" -m uvicorn tools.mock_liara.server:app --port 8081 > /tmp/mock.log 2>&1 &)
(cd "$ROOT/demo/shop-demo" && FAULT_MODE="${FAULT_MODE:-none}" PORT=3000 nohup node src/index.js > /tmp/demo.log 2>&1 &)
(cd "$ROOT/backend" && DEMO_APP_URL=http://127.0.0.1:3000 nohup "$PY" -m uvicorn app.main:app --port 8000 > /tmp/backend.log 2>&1 &)
sleep 4
curl -sf localhost:8081/__mock/requests >/dev/null && echo "mock   : up (8081)"
curl -sf localhost:3000/health >/dev/null && echo "demo   : up (3000)"
curl -sf localhost:8000/healthz >/dev/null && echo "backend: up (8000)"
