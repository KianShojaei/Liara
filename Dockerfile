# Liara Ops Copilot: multi-stage image (UI build -> Python runtime). Platform: docker.
# Build: docker build -t liara-ops-copilot .   Run: docker run -p 8000:8000 --env-file .env liara-ops-copilot

FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# git: project import from Git URLs; curl: health checks
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
RUN pip install ./backend
COPY tools tools
COPY demo/shop-demo demo/shop-demo
COPY --from=ui /ui/dist frontend/dist
# Persistent state (SQLite, imported projects). Mount a Liara disk at /app/data to keep it across deploys.
RUN mkdir -p /app/data/projects
ENV COPILOT_DB_PATH=/app/data/copilot.sqlite COPILOT_HOST=0.0.0.0 COPILOT_PORT=8000 COPILOT_MODE=live
EXPOSE 8000
WORKDIR /app/backend
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD curl -fsS http://127.0.0.1:${COPILOT_PORT}/healthz || exit 1
CMD ["sh", "-c", "python -m uvicorn app.main:app --host ${COPILOT_HOST} --port ${COPILOT_PORT} --proxy-headers --forwarded-allow-ips='*'"]
