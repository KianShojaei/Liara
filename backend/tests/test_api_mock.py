"""End-to-end through the HTTP API against the in-process mock Liara server."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from tools.mock_liara.server import app as mock_app
from tools.mock_liara.server import state as mock_state

from app.agent.context import build_runtime
from app.agent.loop import Agent
from app.api.routes import router
from app.config import Settings


@pytest.fixture
async def api(tmp_path, monkeypatch):
    mock_state.reset()
    settings = Settings(
        copilot_mode="mock",
        mock_liara_base="http://mock",
        copilot_db_path=str(tmp_path / "db.sqlite"),
        boxapi_api_key="",
        liara_api_token="",
        watcher_enabled=False,
        _env_file=None,
    )
    runtime = build_runtime(settings, probe_base_url="http://mock/__probe")
    # route the LiaraClient's httpx into the ASGI mock app
    runtime.client._http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mock_app),
        base_url="http://mock",
        headers={"Authorization": "Bearer t"},
    )

    async def fake_probe(url):
        return {"url": url, "status": 200, "latency_ms": 5.0, "ok": True}

    runtime.probe.probe = fake_probe  # type: ignore[method-assign]
    app = FastAPI()
    app.include_router(router)
    app.state.runtime = runtime
    app.state.agent = Agent(runtime)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api"
    ) as client:
        yield client, runtime
    await runtime.client.aclose()
    runtime.store.close()


async def wait_kind(client, session_id, kind, timeout=20):
    for _ in range(timeout * 10):
        events = (await client.get(f"/api/sessions/{session_id}/timeline")).json()
        if any(e["kind"] == kind for e in events):
            return events
        await asyncio.sleep(0.1)
    raise AssertionError(f"no {kind} event")


@pytest.mark.asyncio
async def test_status_and_restart_flow(api):
    client, runtime = api
    assert (await client.get("/api/status")).json()["ok"]
    session = (await client.post("/api/sessions", json={"title": "t"})).json()
    await client.post(
        f"/api/sessions/{session['id']}/messages", json={"text": "ری‌استارت shop-demo"}
    )
    events = await wait_kind(client, session["id"], "proposal")
    proposal = next(e["payload"] for e in events if e["kind"] == "proposal")
    assert proposal["tool"] == "restart_app" and proposal["status"] == "pending_approval"
    assert (await client.post(f"/api/proposals/{proposal['id']}/approve", json={})).json()[
        "status"
    ] == "approved"
    assert (
        await client.post(f"/api/proposals/{proposal['id']}/approve", json={})
    ).status_code == 409
    events = await wait_kind(client, session["id"], "verification")
    assert next(e["payload"] for e in events if e["kind"] == "verification")["ok"]
    assert any("POST /v1/projects/shop-demo/actions/restart" == r for r in mock_state.request_log)


@pytest.mark.asyncio
async def test_investigation_finds_memory_leak(api):
    client, _ = api
    mock_state.set_scenario("shop-demo", "memory_leak", minutes_ago=4)
    session = (await client.post("/api/sessions", json={"title": "t"})).json()
    await client.post(f"/api/sessions/{session['id']}/investigate", json={"app": "shop-demo"})
    events = await wait_kind(client, session["id"], "remediation")
    hypotheses = next(e["payload"] for e in events if e["kind"] == "hypotheses")
    assert hypotheses["items"][0]["id"] == "memory_leak"
    remediation = next(e["payload"] for e in events if e["kind"] == "remediation")
    assert {o["tool"] for o in remediation["options"]} >= {"restart_app", "resize_app"}
    incident = (await client.get("/api/incidents")).json()[0]
    brief = (await client.get(f"/api/incidents/{incident['id']}/fix-brief")).json()
    assert "memory" in brief["fix_direction"].lower()


@pytest.mark.asyncio
async def test_deploy_wizard_creates_app_and_verifies(api, tmp_path):
    client, _ = api
    project = tmp_path / "site"
    project.mkdir()
    (project / "package.json").write_text(
        '{"dependencies": {"express": "4"}, "scripts": {"start": "node index.js"}}'
    )
    (project / "index.js").write_text("app.listen(4000)")
    session = (await client.post("/api/sessions", json={"title": "d"})).json()
    await client.post(
        f"/api/sessions/{session['id']}/messages", json={"text": f"دیپلوی {project} برنامه newsite"}
    )
    events = await wait_kind(client, session["id"], "proposal")
    plan = next(e["payload"] for e in events if e["kind"] == "plan_options")
    assert plan["recommended_plan_id"] == "small-g2" and plan["app_exists"] is False
    proposal = next(e["payload"] for e in events if e["kind"] == "proposal")
    assert proposal["args"]["create"] and proposal["args"]["port"] == 4000
    await client.post(f"/api/proposals/{proposal['id']}/approve", json={})
    events = await wait_kind(client, session["id"], "success", timeout=40)
    assert "newsite" in mock_state.projects
    steps = [
        e["payload"]["name"]
        for e in events
        if e["kind"] == "step" and e["payload"]["status"] == "done"
    ]
    assert steps == ["create_app", "liara_json", "deploy", "verify"]
