"""Collectors: gather everything the analyzers need, in parallel, tolerating partial failure."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.deploy.verifier import HttpProbe
from app.liara.client import LiaraClient
from app.liara.errors import LiaraError
from app.liara.models import Applet, EventRow, LogLine, ProjectDetails, ProjectPlan, Release


@dataclass
class RawBundle:
    app: str
    collected_at: float
    window_minutes: int
    project: ProjectDetails | None = None
    plan: ProjectPlan | None = None
    logs: list[LogLine] = field(default_factory=list)
    events: list[tuple[float, str]] = field(default_factory=list)
    cpu: list[tuple[float, float]] = field(default_factory=list)
    memory: list[tuple[float, float]] = field(default_factory=list)
    releases: list[Release] = field(default_factory=list)
    applets: list[Applet] = field(default_factory=list)
    probe: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class Collector:
    def __init__(self, client: LiaraClient, probe: HttpProbe):
        self._client = client
        self._probe = probe

    async def collect(
        self, app: str, *, window_minutes: int = 30, health_path: str = "/", probe_count: int = 3
    ) -> RawBundle:
        now = time.time()
        since = int(now) - window_minutes * 60
        bundle = RawBundle(app=app, collected_at=now, window_minutes=window_minutes)
        results = await asyncio.gather(
            self._client.get_project(app),
            self._client.me(),
            self._client.logs(app, since=since),
            self._client.events(app, start=since, end=int(now)),
            self._client.metric(app, "cpu", since),
            self._client.metric(app, "memory", since),
            self._client.releases(app, count=10),
            self._client.applets(app),
            self._probe.probe_series(
                self._probe.url_for(app, health_path), count=probe_count, interval=0.5
            ),
            return_exceptions=True,
        )
        names = ("project", "me", "logs", "events", "cpu", "memory", "releases", "applets", "probe")
        for name, value in zip(names, results, strict=True):
            if isinstance(value, Exception):
                bundle.errors.append(f"{name}: {getattr(value, 'user_message', str(value))}")
                continue
            if name == "project":
                bundle.project = value
            elif name == "me" and bundle.project is not None:
                bundle.plan = next(
                    (p for p in value.project_plans() if p.plan_id == bundle.project.plan_id), None
                )
            elif name == "logs":
                bundle.logs = value
            elif name == "events":
                bundle.events = _flatten_events(value)
            elif name in ("cpu", "memory"):
                setattr(bundle, name, value.result[0].points() if value.result else [])
            elif name == "releases":
                bundle.releases = value.releases
            elif name == "applets":
                bundle.applets = value
            elif name == "probe":
                bundle.probe = value
        if bundle.project is None and bundle.plan is None and not bundle.errors:
            bundle.errors.append("project details unavailable")
        return bundle


def _flatten_events(rows: list[EventRow]) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for row in rows:
        for value in row.values:
            if len(value) >= 2:
                try:
                    out.append((float(value[0]), str(value[1])))
                except (TypeError, ValueError):
                    continue
    out.sort()
    return out


_ = LiaraError  # re-exported for callers that want to catch collector errors
