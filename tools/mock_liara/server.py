"""Mock Liara API for local development and a fully offline demo.

Replays the VERIFIED response shapes from the official OpenAPI spec and lets you script
faults so the SRE flow has something real to diagnose:

    POST /__mock/scenario {"app": "shop-demo", "scenario": "memory_leak" | "cpu_saturation"
                           | "error_burst" | "bad_release" | "healthy"}
    POST /__mock/reset

Run:  uvicorn tools.mock_liara.server:app --port 8081
"""

from __future__ import annotations

import math
import random
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Mock Liara API")

SCENARIOS = {"healthy", "memory_leak", "cpu_saturation", "error_burst", "bad_release"}


# Plan ids, resources and hourly prices VERIFIED against a real account via tools/probe.py
# (October 2026). Only the plans marked available on that account are listed as available.
def _plan(
    ram: float,
    cpu: float,
    volume: float,
    price: float,
    *,
    available: bool = True,
    region: str = "iran",
) -> dict[str, Any]:
    return {
        "available": available,
        "region": region,
        "RAM": {"amount": ram},
        "CPU": {"amount": cpu},
        "volume": volume,
        "price": price,
        "storageClass": "SSD",
    }


PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "free": {**_plan(0.125, 0.125, 0, 0, available=False), "storageClass": None},
    "ir-mini": _plan(0.25, 0.25, 2.5, 763.88, available=False),
    "ir-small": _plan(0.5, 0.5, 5, 1319.44),
    "ir-medium": _plan(1, 1, 10, 2291.66),
    "standard-base": _plan(2, 1, 20, 4097.22),
    "standard-plus": _plan(4, 2, 40, 7361.11),
    "pro": _plan(8, 4, 80, 12777.77),
    "mini-g2": _plan(0.25, 0.25, 2.5, 381.94, available=False),
    "small-g2": _plan(0.5, 0.5, 5, 659.72),
    "medium-g2": _plan(1, 1, 10, 1145.83),
    "standard-base-g2": _plan(2, 1, 20, 2048.61),
    "standard-plus-g2": _plan(4, 2, 40, 3680.55),
    "pro-g2": _plan(8, 4, 80, 6388.88),
    "small": _plan(0.5, 0.25, 2.5, 100, available=False, region="germany"),
}

PLAN_MEMORY_BYTES = {pid: int(p["RAM"]["amount"] * 1024**3) for pid, p in PLAN_CATALOG.items()}


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


class MockState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.balance = 999_553.0
        self.projects: dict[str, dict[str, Any]] = {}
        self.releases: dict[str, dict[str, Any]] = {}
        self.domains: dict[str, dict[str, Any]] = {}
        self.zones: dict[str, dict[str, Any]] = {}
        self.scenarios: dict[str, dict[str, Any]] = {}
        self.events: dict[str, list[tuple[float, str]]] = {}
        self.request_log: list[str] = []
        self._seed()

    def _seed(self) -> None:
        self.add_project("shop-demo", "node", "small-g2", deployed=True)
        self.add_release("shop-demo", "READY", "v1", message="v1 initial release", age=3600)

    def add_project(
        self, name: str, platform: str, plan: str, *, deployed: bool = False
    ) -> dict[str, Any]:
        project = {
            "_id": uuid.uuid4().hex[:24],
            "project_id": name,
            "type": platform,
            "status": "running" if deployed else "created",
            "defaultSubdomain": True,
            "readOnlyRootFilesystem": False,
            "zeroDowntime": False,
            "scale": 1,
            "envs": [
                {
                    "key": "NODE_ENV",
                    "value": "production",
                    "encrypted": False,
                    "_id": uuid.uuid4().hex[:24],
                }
            ],
            "planID": plan,
            "fixedIPStatus": "disabled",
            "created_at": _iso(time.time()),
            "node": {"_id": "node1", "IP": "10.0.0.1"},
            "hourlyPrice": PLAN_CATALOG[plan]["price"],
            "isDeployed": deployed,
            "reservedDiskSpace": 0,
        }
        self.projects[name] = project
        self.scenarios.setdefault(name, {"scenario": "healthy", "since": time.time()})
        self.events.setdefault(name, []).append((time.time(), f"Project {name} created"))
        return project

    def add_release(
        self, app_name: str, state: str, tag: str, *, message: str = "", age: float = 0
    ) -> dict[str, Any]:
        release = {
            "_id": uuid.uuid4().hex[:24],
            "type": "SOURCE",
            "imageName": f"registry.liara.ir/{app_name}:{tag}",
            "projectType": self.projects[app_name]["type"],
            "state": state,
            "port": 3000,
            "gitInfo": {
                "branch": "main",
                "message": message or tag,
                "commit": uuid.uuid4().hex[:7],
                "committedAt": _iso(time.time() - age),
                "remote": None,
                "author": {"email": None, "name": None},
                "tags": [],
            },
            "client": "CLI 9.6.0",
            "finishedAt": _iso(time.time() - age),
            "createdAt": _iso(time.time() - age - 40),
            "tag": tag,
            "sourceID": uuid.uuid4().hex[:24],
            "sourceAvailable": True,
            "message": message or tag,
            "_app": app_name,
            "_created_ts": time.time() - age,
        }
        self.releases[release["_id"]] = release
        self.events[app_name].append((time.time() - age, f"Release {tag} is {state}"))
        return release

    def set_scenario(self, app_name: str, scenario: str, minutes_ago: float = 0) -> None:
        if app_name not in self.projects:
            raise KeyError(app_name)
        self.scenarios[app_name] = {"scenario": scenario, "since": time.time() - minutes_ago * 60}
        self.events[app_name].append((time.time(), f"[mock] scenario set to {scenario}"))
        if scenario == "bad_release":
            self.add_release(app_name, "UNHEALTHY", "v3", message="v3 broken config")
            self.events[app_name].append((time.time(), "Container restarted: CrashLoopBackOff"))

    def app_releases(self, app_name: str) -> list[dict[str, Any]]:
        rel = [r for r in self.releases.values() if r["_app"] == app_name]
        rel.sort(key=lambda r: r["_created_ts"], reverse=True)
        return rel


state = MockState()


def _public(release: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in release.items() if not k.startswith("_") or k == "_id"}


@app.middleware("http")
async def _record(request: Request, call_next):  # type: ignore[no-untyped-def]
    if not request.url.path.startswith("/__mock"):
        state.request_log.append(f"{request.method} {request.url.path}")
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"message": "Missing authentication"}, status_code=401)
    return await call_next(request)


# ----------------------------------------------------------------- mock control


class ScenarioBody(BaseModel):
    app: str
    scenario: str
    minutes_ago: float = 0  # pretend the fault started earlier so trends are visible at once


@app.post("/__mock/scenario")
def set_scenario(body: ScenarioBody) -> dict[str, Any]:
    if body.scenario not in SCENARIOS:
        raise HTTPException(400, f"unknown scenario, use one of {sorted(SCENARIOS)}")
    try:
        state.set_scenario(body.app, body.scenario, body.minutes_ago)
    except KeyError:
        raise HTTPException(404, "app not found") from None
    return {"ok": True, "app": body.app, "scenario": body.scenario}


@app.post("/__mock/reset")
def reset() -> dict[str, Any]:
    state.reset()
    return {"ok": True}


@app.get("/__mock/requests")
def requests_log() -> dict[str, Any]:
    return {"requests": state.request_log[-200:]}


# ----------------------------------------------------------------- account


@app.get("/v1/me")
def me() -> dict[str, Any]:
    return {
        "user": {
            "_id": "u1",
            "fullname": "Demo User",
            "email": "demo@example.com",
            "isTeam": False,
            "accountType": "normal",
        },
        "featureFlags": [],
        "plans": {
            "projects": PLAN_CATALOG,
            "databases": {},
            "projectBundlePlans": {"free": {}, "standard": {}},
        },
    }


@app.get("/v1/billing")
def billing() -> dict[str, Any]:
    return {
        "user": {
            "balance": state.balance,
            "accountType": "normal",
            "minCreditAmount": 10000,
            "isManualMinCredit": False,
            "minCreditLastNotifiedAt": None,
        }
    }


# ----------------------------------------------------------------- projects


def _project_or_404(name: str) -> dict[str, Any]:
    project = state.projects.get(name)
    if project is None:
        raise HTTPException(404, "App does not exists.")
    return project


@app.get("/v1/projects")
def list_projects() -> dict[str, Any]:
    keys = ("_id", "project_id", "type", "status", "scale", "planID", "created_at", "isDeployed")
    return {"projects": [{k: p[k] for k in keys} for p in state.projects.values()]}


class CreateApp(BaseModel):
    name: str
    planID: str
    platform: str
    readOnlyRootFilesystem: bool = False
    network: str | None = None


@app.post("/v1/projects")
def create_project(body: CreateApp) -> dict[str, Any]:
    if body.name in state.projects:
        raise HTTPException(409, "Conflict")
    if body.planID not in PLAN_CATALOG:
        raise HTTPException(400, "Bad request: unknown planID")
    state.add_project(body.name, body.platform, body.planID)
    return {}


@app.get("/v1/projects/{name}")
def get_project(name: str) -> dict[str, Any]:
    return {"project": _project_or_404(name)}


@app.delete("/v1/projects/{name}")
def delete_project(name: str) -> dict[str, Any]:
    _project_or_404(name)
    del state.projects[name]
    return {}


class ScaleBody(BaseModel):
    scale: int


@app.post("/v1/projects/{name}/actions/scale")
def scale_project(name: str, body: ScaleBody) -> dict[str, Any]:
    project = _project_or_404(name)
    project["scale"] = body.scale
    project["status"] = "running" if body.scale else "stopped"
    state.events[name].append((time.time(), f"Scale set to {body.scale}"))
    return {}


@app.post("/v1/projects/{name}/actions/restart")
def restart_project(name: str) -> dict[str, Any]:
    _project_or_404(name)
    state.events[name].append((time.time(), "Restart requested by user"))
    # A restart clears a memory leak / cpu storm until it builds up again
    scenario = state.scenarios[name]["scenario"]
    if scenario in ("memory_leak", "cpu_saturation"):
        state.scenarios[name]["since"] = time.time()
    return {}


class ResizeBody(BaseModel):
    planID: str


@app.post("/v1/projects/{name}/resize")
def resize_project(name: str, body: ResizeBody) -> dict[str, Any]:
    project = _project_or_404(name)
    if body.planID not in PLAN_CATALOG:
        raise HTTPException(400, "unknown planID")
    project["planID"] = body.planID
    project["hourlyPrice"] = PLAN_CATALOG[body.planID]["price"]
    state.events[name].append((time.time(), f"Plan changed to {body.planID}"))
    return {}


class EnvBody(BaseModel):
    project: str
    variables: list[dict[str, str]]


@app.post("/v1/projects/update-envs")
def update_envs(body: EnvBody) -> dict[str, Any]:
    project = _project_or_404(body.project)
    existing = {e["key"]: e for e in project["envs"]}
    for var in body.variables:
        existing[var["key"]] = {
            "key": var["key"],
            "value": var["value"],
            "encrypted": False,
            "_id": uuid.uuid4().hex[:24],
        }
    project["envs"] = list(existing.values())
    state.events[body.project].append((time.time(), "Environment variables updated"))
    # Toggling FAULT_MODE in the demo app resolves the fault in the mock too.
    fault = existing.get("FAULT_MODE", {}).get("value")
    if fault == "none":
        state.scenarios[body.project] = {"scenario": "healthy", "since": time.time()}
    return {"message": "Envs updated successfully."}


@app.post("/v1/projects/{pid}/{setting}/{status}")
def toggle_setting(pid: str, setting: str, status: str) -> dict[str, Any]:
    if setting not in {"zero-downtime", "default-subdomain", "fixed-ip", "read-only"}:
        raise HTTPException(404, "unknown setting")
    for project in state.projects.values():
        if project["_id"] == pid:
            key = {
                "zero-downtime": "zeroDowntime",
                "default-subdomain": "defaultSubdomain",
                "read-only": "readOnlyRootFilesystem",
                "fixed-ip": "fixedIPStatus",
            }[setting]
            project[key] = (
                (status == "enable")
                if key != "fixedIPStatus"
                else ("enabled" if status == "enable" else "disabled")
            )
            return {"IP": "185.0.0.1"} if setting == "fixed-ip" else {}
    raise HTTPException(404, "App does not exists.")


# ----------------------------------------------------------------- deploy


@app.post("/v2/projects/{name}/sources")
async def upload_source(name: str, request: Request) -> dict[str, Any]:
    _project_or_404(name)
    await request.body()
    return {"sourceID": uuid.uuid4().hex[:24]}


class ReleaseBody(BaseModel):
    sourceID: str
    port: int
    type: str


@app.post("/v2/projects/{name}/releases")
def create_release(name: str, body: ReleaseBody) -> dict[str, Any]:
    project = _project_or_404(name)
    tag = f"v{len(state.app_releases(name)) + 1}"
    release = state.add_release(name, "BUILDING", tag, message=f"{tag} via API")
    release["_deploy_started"] = time.time()
    project["isDeployed"] = True
    project["status"] = "running"
    return {"releaseID": release["_id"]}


@app.get("/v1/releases/{release_id}")
def get_release(release_id: str) -> dict[str, Any]:
    release = state.releases.get(release_id)
    if release is None:
        raise HTTPException(404, "Release not found")
    started = release.get("_deploy_started")
    if started is not None and release["state"] in ("BUILDING", "PUSHING", "DEPLOYING"):
        elapsed = time.time() - started
        release["state"] = "BUILDING" if elapsed < 3 else "DEPLOYING" if elapsed < 6 else "READY"
        if release["state"] == "READY":
            release["finishedAt"] = _iso(time.time())
            state.events[release["_app"]].append(
                (time.time(), f"Release {release['tag']} is READY")
            )
    return {"release": _public(release)}


# ----------------------------------------------------------------- observability


def _scenario(name: str) -> tuple[str, float]:
    sc = state.scenarios.get(name, {"scenario": "healthy", "since": time.time()})
    return sc["scenario"], sc["since"]


def _memory_at(name: str, ts: float) -> float:
    plan = state.projects[name]["planID"]
    limit = PLAN_MEMORY_BYTES[plan]
    scenario, since = _scenario(name)
    base = limit * 0.32 + random.uniform(-0.01, 0.01) * limit
    if scenario == "memory_leak" and ts >= since:
        minutes = (ts - since) / 60
        base += min(limit * 0.62, limit * 0.11 * minutes)
    return max(0.0, base)


def _cpu_at(name: str, ts: float) -> float:
    plan = state.projects[name]["planID"]
    cores = PLAN_CATALOG[plan]["CPU"]["amount"]
    scenario, since = _scenario(name)
    base = cores * (0.08 + 0.03 * math.sin(ts / 30))
    if scenario == "cpu_saturation" and ts >= since:
        base = cores * 0.97
    return max(0.0, base)


def _series(name: str, fn, since: int, step: int = 15) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    now = int(time.time())
    start = int(since) if since > 10_000_000 else now - int(since)
    points = [[ts, f"{fn(name, ts):.4f}"] for ts in range(max(start, now - 3600), now + 1, step)]
    return {"end": now, "result": [{"applet": f"{name}-0", "values": points}]}


@app.get("/v1/projects/{name}/metrics/summary")
def metrics_summary(name: str) -> dict[str, Any]:
    _project_or_404(name)
    now = int(time.time())
    return {
        "cpuUsage": [{"value": [now, f"{_cpu_at(name, now):.4f}"], "applet": f"{name}-0"}],
        "memoryUsage": [{"value": [now, f"{_memory_at(name, now):.0f}"], "applet": f"{name}-0"}],
        "disksUsage": [],
    }


@app.get("/v1/projects/{name}/metrics/{kind}")
def metrics(name: str, kind: str, since: int = Query(...)) -> dict[str, Any]:
    _project_or_404(name)
    if kind == "cpu":
        return _series(name, _cpu_at, since)
    if kind == "memory":
        return _series(name, _memory_at, since)
    if kind in ("network-receive", "network-transmit"):
        return _series(name, lambda n, ts: 2000 + 500 * math.sin(ts / 60), since)
    raise HTTPException(404, "unknown metric")


@app.get("/v1/projects/{name}/logs")
def logs(name: str, since: str = Query(...)) -> list[dict[str, Any]]:
    _project_or_404(name)
    scenario, started = _scenario(name)
    now = time.time()
    rows: list[dict[str, Any]] = []
    for i in range(40):
        ts = now - (40 - i) * 3
        rows.append(
            {
                "type": "stdout",
                "datetime": _iso(ts),
                "message": f"GET /api/products 200 {random.randint(12, 40)}ms",
            }
        )
        if scenario == "error_burst" and ts > started and i % 2 == 0:
            rows.append(
                {
                    "type": "stderr",
                    "datetime": _iso(ts),
                    "message": "TypeError: Cannot read properties of undefined (reading 'price')\n    at computeTotal (/app/src/handlers/checkout.js:42:21)\n    at /app/src/routes/checkout.js:18:5",
                }
            )
            rows.append(
                {"type": "stdout", "datetime": _iso(ts), "message": "POST /api/checkout 500 3ms"}
            )
        if scenario == "memory_leak" and ts > started and i % 7 == 0:
            rows.append(
                {
                    "type": "stdout",
                    "datetime": _iso(ts),
                    "message": f"GET /api/products 200 {random.randint(300, 900)}ms",
                }
            )
            rows.append(
                {
                    "type": "stderr",
                    "datetime": _iso(ts),
                    "message": "[warn] cache size growing: entries=%d" % (10000 + i * 900),
                }
            )
        if scenario == "cpu_saturation" and ts > started and i % 5 == 0:
            rows.append(
                {
                    "type": "stdout",
                    "datetime": _iso(ts),
                    "message": f"GET /slow 200 {random.randint(1500, 4000)}ms",
                }
            )
        if scenario == "bad_release" and ts > started and i % 6 == 0:
            rows.append(
                {
                    "type": "stderr",
                    "datetime": _iso(ts),
                    "message": "Error: Missing required env DATABASE_URL\n    at bootstrap (/app/src/index.js:12:11)",
                }
            )
    if scenario == "memory_leak" and now - started > 240:
        rows.append(
            {
                "type": "stderr",
                "datetime": _iso(now),
                "message": "FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory",
            }
        )
    return rows


@app.get("/v1/projects/{name}/events")
def events(
    name: str, search: str | None = None, start: float | None = None, end: float | None = None
) -> dict[str, Any]:
    _project_or_404(name)
    rows = state.events.get(name, [])
    values = [
        [str(int(ts)), text]
        for ts, text in rows
        if (start is None or ts >= start)
        and (end is None or ts <= end)
        and (not search or search.lower() in text.lower())
    ]
    return {"data": [{"metaData": {"app": name}, "values": values}]}


@app.get("/v1/projects/{name}/applets")
def applets(name: str) -> dict[str, Any]:
    _project_or_404(name)
    scenario, started = _scenario(name)
    current = state.app_releases(name)[0] if state.app_releases(name) else None
    applet_state, reason = "Running", ""
    if scenario == "bad_release":
        applet_state, reason = "Waiting", "CrashLoopBackOff"
    elif scenario == "memory_leak" and time.time() - started > 300:
        applet_state, reason = "Waiting", "OOMKilled"
    return {
        "applets": [
            {
                "id": f"{name}-0",
                "name": f"{name}-0",
                "timestamp": _iso(time.time()),
                "state": applet_state,
                "reason": reason,
                "release": {
                    "releaseID": current["_id"] if current else "",
                    "tag": current["tag"] if current else "",
                },
            }
        ]
    }


@app.get("/v1/projects/{name}/releases")
def releases(name: str, page: int = 1, count: int = 10) -> dict[str, Any]:
    _project_or_404(name)
    rel = state.app_releases(name)
    ready = [r for r in rel if r["state"] == "READY"]
    return {
        "total": len(rel),
        "currentRelease": rel[0]["_id"] if rel else "",
        "readyReleasesCount": len(ready),
        "releases": [_public(r) for r in rel[(page - 1) * count : page * count]],
        "platform": state.projects[name]["type"],
    }


# ----------------------------------------------------------------- domains


@app.get("/v1/domains")
def list_domains(project: str = Query(...)) -> dict[str, Any]:
    return {"domains": [d for d in state.domains.values() if d["project"]["project_id"] == project]}


class DomainBody(BaseModel):
    name: str
    project: str
    type: str = "PROJECT"


@app.post("/v1/domains", status_code=201)
def create_domain(body: DomainBody) -> dict[str, Any]:
    project = _project_or_404(body.project)
    if any(d["name"] == body.name for d in state.domains.values()):
        raise HTTPException(409, "Conflict")
    domain = {
        "_id": uuid.uuid4().hex[:24],
        "name": body.name,
        "type": body.type,
        "project": {"_id": project["_id"], "project_id": body.project},
        "status": "PENDING",
        "certificatesStatus": "PENDING",
        "redirectTo": "",
        "redirectStatus": 0,
        "created_at": _iso(time.time()),
        "CNameRecord": f"{body.project}.liara.run",
        "verificationCode": uuid.uuid4().hex[:16],
        "_checks": 0,
    }
    state.domains[domain["_id"]] = domain
    return {"domain": {"_id": domain["_id"]}}


@app.get("/v1/domains/{domain_id}/check")
def check_domain(domain_id: str) -> dict[str, Any]:
    domain = state.domains.get(domain_id)
    if domain is None:
        raise HTTPException(404, "Domain does not exists.")
    domain["_checks"] += 1
    if domain["_checks"] >= 2:
        domain["status"] = "SET"
        domain["certificatesStatus"] = "OK" if domain["_checks"] >= 3 else "PENDING"
    return {"domain": {k: v for k, v in domain.items() if not k.startswith("_") or k == "_id"}}


@app.post("/v1/domains/provision-ssl-certs")
def enable_ssl(body: dict[str, str]) -> dict[str, Any]:
    for domain in state.domains.values():
        if domain["name"] == body.get("domain"):
            domain["certificatesStatus"] = "OK"
            return {"code": "ok"}
    raise HTTPException(404, "Domain does not exists.")


# ----------------------------------------------------------------- dns-service (mounted under /dns)


@app.get("/dns/api/v1/zones")
def dns_zones() -> dict[str, Any]:
    return {"status": "success", "data": list(state.zones.values())}


@app.post("/dns/api/v1/zones", status_code=201)
def dns_create_zone(body: dict[str, str]) -> dict[str, Any]:
    name = body["name"]
    if name in state.zones:
        raise HTTPException(409, "Conflict")
    zone = {
        "id": uuid.uuid4().hex[:24],
        "name": name,
        "status": "PENDING",
        "currentNameServers": ["ns1.registrar.example"],
        "nameServers": ["ns1.liara.ir", "ns2.liara.ir"],
        "lastCheckAt": "",
        "createdAt": _iso(time.time()),
        "_checks": 0,
    }
    state.zones[name] = zone
    return {"status": "success", "data": zone}


@app.get("/dns/api/v1/zones/{zone}")
def dns_zone(zone: str) -> dict[str, Any]:
    if zone not in state.zones:
        raise HTTPException(404, "Zone does not exists.")
    return {"status": "success", "data": state.zones[zone]}


@app.put("/dns/api/v1/zones/{zone}/check", status_code=201)
def dns_check(zone: str) -> dict[str, Any]:
    z = state.zones.get(zone)
    if z is None or z["status"] != "PENDING":
        raise HTTPException(404, "Zone does not exists or its status is not pending")
    z["_checks"] += 1
    z["lastCheckAt"] = _iso(time.time())
    if z["_checks"] >= 2:
        z["status"] = "ACTIVE"
        z["currentNameServers"] = z["nameServers"]
    return {"status": "success", "data": "Your request has been submitted."}


@app.get("/dns/api/v1/zones/{zone}/dns-records")
def dns_records(zone: str) -> dict[str, Any]:
    if zone not in state.zones:
        raise HTTPException(404, "Zone Not Found")
    return {"status": "success", "data": state.zones[zone].setdefault("_records", [])}


@app.post("/dns/api/v1/zones/{zone}/dns-records", status_code=201)
def dns_create_record(zone: str, body: dict[str, Any]) -> dict[str, Any]:
    if zone not in state.zones:
        raise HTTPException(404, "Zone does not exists.")
    record = {"id": uuid.uuid4().hex[:24], **body}
    state.zones[zone].setdefault("_records", []).append(record)
    return {"status": "success", "data": record}
