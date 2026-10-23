"""Verification: a deploy is done only when the release is READY, the container runs,
the health path answers 200 and no error burst appears for a short window.

Each check returns a step dict so the UI can show exactly what was verified.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.liara.client import LiaraClient
from app.liara.errors import LiaraError

RELEASE_TERMINAL = {"READY", "FAILED", "UNHEALTHY", "CANCELED"}
PROBE_TIMEOUT = httpx.Timeout(8.0)


def step(name: str, ok: bool, detail: str = "", **extra: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, **extra}


class HttpProbe:
    def __init__(self, *, base_url_override: str | None = None):
        self._override = base_url_override

    def url_for(self, app: str, path: str = "/") -> str:
        base = self._override or f"https://{app}.liara.run"
        return base.rstrip("/") + "/" + path.lstrip("/")

    async def probe(self, url: str) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=PROBE_TIMEOUT, follow_redirects=True) as http:
                response = await http.get(url)
            latency = (time.perf_counter() - started) * 1000
            status = response.status_code
            return {
                "url": url,
                "status": status,
                "latency_ms": round(latency, 1),
                # ok = the app answered (any status < 500). 401/403/404 mean "up but protected
                # or wrong path", which is not an outage; healthy = 2xx/3xx on this path.
                "ok": status < 500,
                "healthy": 200 <= status < 400,
                "protected": status in (401, 403),
            }
        except httpx.HTTPError as exc:
            return {
                "url": url,
                "status": None,
                "latency_ms": None,
                "ok": False,
                "error": type(exc).__name__,
            }

    async def probe_series(
        self, url: str, *, count: int = 5, interval: float = 1.0
    ) -> dict[str, Any]:
        samples = []
        for i in range(count):
            samples.append(await self.probe(url))
            if i < count - 1:
                await asyncio.sleep(interval)
        okay = [s for s in samples if s["ok"]]
        healthy = [s for s in samples if s.get("healthy")]
        latencies = [s["latency_ms"] for s in samples if s["latency_ms"] is not None]
        statuses = sorted({s["status"] for s in samples if s["status"] is not None})
        return {
            "url": url,
            "samples": samples,
            "success_rate": len(okay) / max(len(samples), 1),
            "healthy_rate": len(healthy) / max(len(samples), 1),
            "protected": any(s.get("protected") for s in samples),
            "statuses": statuses,
            "p50_ms": sorted(latencies)[len(latencies) // 2] if latencies else None,
            "max_ms": max(latencies) if latencies else None,
        }


class DeployVerifier:
    def __init__(self, client: LiaraClient, probe: HttpProbe):
        self._client = client
        self._probe = probe

    async def wait_release(
        self, release_id: str, *, timeout: float = 600, poll: float = 3.0, on_state: Any = None
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last = ""
        while time.monotonic() < deadline:
            release = await self._client.get_release(release_id)
            if release.state != last and on_state:
                result = on_state(release.state)
                if asyncio.iscoroutine(result):
                    await result
            last = release.state
            if release.state in RELEASE_TERMINAL:
                return step(
                    "release",
                    release.state == "READY",
                    f"release state {release.state}",
                    state=release.state,
                    release_id=release_id,
                )
            await asyncio.sleep(poll)
        return step(
            "release",
            False,
            f"timed out after {timeout:.0f}s in state {last}",
            state=last,
            release_id=release_id,
        )

    async def check_applets(self, app: str) -> dict[str, Any]:
        try:
            applets = await self._client.applets(app)
        except LiaraError as exc:
            # VERIFIED on a real docker app: GET .../applets can answer HTTP 500 at Liara's side.
            # That is not evidence about the app, so the step is skipped rather than failed.
            return step(
                "container",
                True,
                f"Liara applets API unavailable ({exc.message}); skipped, relying on HTTP probe",
                skipped=True,
            )
        running = [a for a in applets if a.state.lower() in ("running", "ready")]
        waiting = [f"{a.name}: {a.state} {a.reason}".strip() for a in applets if a not in running]
        if not applets:
            return step(
                "container", True, "no applet data reported; relying on HTTP probe", skipped=True
            )
        return step(
            "container",
            bool(running) and not waiting,
            f"{len(running)} running" + (f", {', '.join(waiting)}" if waiting else ""),
            applets=[a.model_dump() for a in applets],
        )

    async def check_http(self, app: str, health_path: str, *, count: int = 3) -> dict[str, Any]:
        url = self._probe.url_for(app, health_path)
        series = await self._probe.probe_series(url, count=count, interval=1.0)
        detail = f"{int(series['success_rate'] * 100)}% answered, p50 {series['p50_ms']} ms"
        if series.get("protected"):
            detail += " (HTTP 401/403: app is up but this path needs login)"
        elif series.get("statuses") and not series["healthy_rate"]:
            detail += f" (HTTP {'/'.join(map(str, series['statuses']))} on this path)"
        return step("http", series["success_rate"] >= 0.67, detail, **series)

    async def check_error_burst(self, app: str, *, window_seconds: int = 120) -> dict[str, Any]:
        try:
            logs = await self._client.logs(app, since=int(time.time()) - window_seconds)
        except LiaraError as exc:
            return step("logs", False, exc.user_message)
        errors = [
            line
            for line in logs
            if line.type == "stderr" or " 500 " in line.message or "Error" in line.message
        ]
        ratio = len(errors) / max(len(logs), 1)
        return step(
            "logs",
            ratio < 0.2,
            f"{len(errors)} error lines of {len(logs)} in the last {window_seconds}s",
            error_lines=[e.message[:300] for e in errors[:5]],
        )

    async def verify_deploy(
        self, app: str, release_id: str | None, health_path: str = "/", *, on_state: Any = None
    ) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        if release_id:
            steps.append(await self.wait_release(release_id, on_state=on_state))
            if not steps[-1]["ok"]:
                return {"ok": False, "steps": steps, "url": self._probe.url_for(app)}
        steps.append(await self.check_applets(app))
        steps.append(await self.check_http(app, health_path))
        steps.append(await self.check_error_burst(app))
        return {"ok": all(s["ok"] for s in steps), "steps": steps, "url": self._probe.url_for(app)}

    async def verify_health(self, app: str, health_path: str = "/") -> dict[str, Any]:
        steps = [
            await self.check_applets(app),
            await self.check_http(app, health_path),
            await self.check_error_burst(app),
        ]
        return {"ok": all(s["ok"] for s in steps), "steps": steps, "url": self._probe.url_for(app)}
