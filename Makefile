.PHONY: setup dev-up test lint mock backend frontend demo

setup:            ## install backend (venv) and frontend deps
	cd backend && uv venv .venv && uv pip install -p .venv/bin/python -e ".[dev]"
	cd frontend && npm install
	cd demo/shop-demo && npm install

dev-up:           ## start mock Liara (8081), demo app (3000) and backend (8000)
	bash scripts/dev_up.sh

mock:             ## mock Liara API only
	backend/.venv/bin/python -m uvicorn tools.mock_liara.server:app --port 8081

backend:          ## backend only (reads .env)
	cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

frontend:         ## vite dev server (proxies /api to 8000)
	cd frontend && npm run dev

demo:             ## sample app with a fault toggle: make demo FAULT_MODE=leak
	cd demo/shop-demo && FAULT_MODE=$(FAULT_MODE) PORT=3000 node src/index.js

test:
	cd backend && .venv/bin/python -m pytest -q

lint:
	cd backend && .venv/bin/ruff check app tests ../tools && .venv/bin/ruff format --check app tests ../tools
