"""FastAPI entrypoint: `uvicorn app.main:app --reload --port 8000`."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agent.context import build_runtime
from app.agent.loop import Agent
from app.api.routes import router
from app.config import REPO_ROOT, get_settings
from app.watcher.scheduler import Watcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    settings = get_settings()
    runtime = build_runtime(settings)
    if settings.watcher_enabled:
        runtime.watcher = Watcher(runtime, interval=settings.watcher_interval_seconds)
    app.state.runtime = runtime
    app.state.agent = Agent(runtime)
    logging.getLogger("copilot").info(
        "mode=%s llm=%s db=%s", settings.copilot_mode, runtime.llm.available, settings.db_path
    )
    try:
        yield
    finally:
        await runtime.aclose()


app = FastAPI(title="Liara Ops Copilot", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Mounted last so API routes and /healthz take precedence over the static UI.
_frontend_dist = REPO_ROOT / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="ui")
