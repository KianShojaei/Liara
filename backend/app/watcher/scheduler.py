"""Watcher: lightweight asyncio poller. Liara has no alert/webhook API, so we poll
health, summary metrics and events into a SQLite ring buffer and apply threshold,
slope and z-score rules. On a trip it opens an incident and runs a read-only investigation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.sre.analyzers import GIB, linear_slope, zscore_last

if TYPE_CHECKING:
    from app.agent.context import Runtime

log = logging.getLogger("copilot.watcher")

COOLDOWN_SECONDS = 600


@dataclass
class Watch:
    app: str
    health_path: str = "/"
    session_id: str = ""
    last_incident_at: float = 0.0
    consecutive_http_failures: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)


class Watcher:
    def __init__(self, rt: Runtime, *, interval: float = 20.0):
        self._rt = rt
        self._interval = interval
        self._watches: dict[str, Watch] = {}
        self._task: asyncio.Task[None] | None = None
        self._plan_cache: dict[str, tuple[float, float]] = {}
        # Created inside the running app, so sync routes (threadpool) can still start the loop.
        self._loop = asyncio.get_running_loop()

    # ------------------------------------------------------------ control

    def watch(self, app: str, *, health_path: str = "/", session_id: str = "") -> None:
        watch = self._watches.setdefault(app, Watch(app))
        watch.health_path, watch.session_id = health_path, session_id or watch.session_id
        self._loop.call_soon_threadsafe(self._ensure_running)

    def _ensure_running(self) -> None:
        if self._task is None or self._task.done():
            self._task = self._loop.create_task(self._run(), name="copilot-watcher")

    def unwatch(self, app: str) -> None:
        self._watches.pop(app, None)

    def apps(self) -> list[str]:
        return sorted(self._watches)

    def status(self) -> dict[str, Any]:
        return {
            "running": self._task is not None and not self._task.done(),
            "interval": self._interval,
            "apps": [
                {
                    "app": w.app,
                    "session_id": w.session_id,
                    "last": (w.history[-1] if w.history else None),
                }
                for w in self._watches.values()
            ],
        }

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    # --------------------------------------------------------------- loop

    async def _run(self) -> None:
        while True:
            for watch in list(self._watches.values()):
                try:
                    await self._tick(watch)
                except Exception as exc:  # noqa: BLE001
                    log.warning("watcher tick failed for %s: %s", watch.app, exc)
            await asyncio.sleep(self._interval)

    async def _tick(self, watch: Watch) -> None:
        rt = self._rt
        now = time.time()
        summary, probe = await asyncio.gather(
            rt.client.metrics_summary(watch.app),
            rt.probe.probe(rt.probe.url_for(watch.app, watch.health_path)),
            return_exceptions=True,
        )
        sample: dict[str, Any] = {"cpu": None, "memory": None, "http_ok": None, "latency_ms": None}
        if not isinstance(summary, Exception):
            sample["cpu"], sample["memory"] = summary.cpu, summary.memory
        if not isinstance(probe, Exception):
            sample["http_ok"], sample["latency_ms"], sample["http_status"] = (
                probe["ok"],
                probe["latency_ms"],
                probe.get("status"),
            )
        rt.store.add_snapshot(watch.app, now, sample)
        watch.history = rt.store.snapshots(watch.app, since_ts=now - 1800)
        watch.consecutive_http_failures = (
            watch.consecutive_http_failures + 1 if sample["http_ok"] is False else 0
        )
        rt.bus.publish(
            "*",
            {
                "kind": "watch_sample",
                "payload": {"app": watch.app, "ts": now, **sample},
                "session_id": watch.session_id,
            },
        )

        reasons = await self._evaluate(watch)
        if (
            reasons
            and now - watch.last_incident_at > COOLDOWN_SECONDS
            and rt.store.open_incident_for(watch.app) is None
        ):
            watch.last_incident_at = now
            await self._open_incident(watch, reasons)

    async def _evaluate(self, watch: Watch) -> list[str]:
        reasons: list[str] = []
        mem_points = [(h["ts"], h["memory"]) for h in watch.history if h.get("memory") is not None]
        cpu_points = [(h["ts"], h["cpu"]) for h in watch.history if h.get("cpu") is not None]
        limit_ram, limit_cpu = await self._limits(watch.app)
        if watch.consecutive_http_failures >= 3:
            reasons.append(
                f"health check {watch.consecutive_http_failures} بار پشت سر هم ناموفق بود"
            )
        if mem_points and limit_ram and mem_points[-1][1] / (limit_ram * GIB) > 0.9:
            reasons.append("حافظه بالای ۹۰٪ ظرفیت پلن")
        if (
            len(mem_points) >= 6
            and linear_slope(mem_points) * 60 > 3 * 1024 * 1024
            and zscore_last(mem_points) > 2.5
        ):
            reasons.append("رشد غیرعادی و پیوسته‌ی حافظه")
        if (
            len(cpu_points) >= 4
            and limit_cpu
            and sum(v for _, v in cpu_points[-4:]) / 4 / limit_cpu > 0.9
        ):
            reasons.append("CPU بالای ۹۰٪ ظرفیت پلن")
        latencies = [
            (h["ts"], h["latency_ms"]) for h in watch.history if h.get("latency_ms") is not None
        ]
        if len(latencies) >= 8 and zscore_last(latencies) > 3 and latencies[-1][1] > 1000:
            reasons.append("جهش زمان پاسخ")
        return reasons

    async def _limits(self, app: str) -> tuple[float, float]:
        cached = self._plan_cache.get(app)
        if cached:
            return cached
        try:
            project, me = await asyncio.gather(
                self._rt.client.get_project(app), self._rt.client.me()
            )
            plan = next((p for p in me.project_plans() if p.plan_id == project.plan_id), None)
            limits = (plan.ram.amount, plan.cpu.amount) if plan else (0.0, 0.0)
        except Exception:  # noqa: BLE001
            limits = (0.0, 0.0)
        self._plan_cache[app] = limits
        return limits

    async def _open_incident(self, watch: Watch, reasons: list[str]) -> None:
        rt = self._rt
        session_id = (
            watch.session_id
            or rt.store.create_session(
                title=f"Incident {watch.app}", mode="investigate", app_name=watch.app
            )["id"]
        )
        watch.session_id = session_id
        incident = rt.store.create_incident(
            app_name=watch.app,
            trigger="watcher: " + "; ".join(reasons),
            session_id=session_id,
            summary="; ".join(reasons),
        )
        rt.emit(
            session_id,
            "incident",
            {
                "id": incident["id"],
                "app": watch.app,
                "status": "open",
                "trigger": "watcher",
                "reasons": reasons,
            },
        )
        rt.emit(
            session_id,
            "message",
            {
                "role": "assistant",
                "text": f"هشدار Watcher برای {watch.app}: "
                + "؛ ".join(reasons)
                + ". بررسی خودکار (فقط خواندنی) شروع شد.",
            },
        )
        from app.sre.investigator import Investigator

        await Investigator(rt).investigate(
            watch.app,
            session_id=session_id,
            trigger="watcher",
            health_path=watch.health_path,
            incident_id=incident["id"],
        )
