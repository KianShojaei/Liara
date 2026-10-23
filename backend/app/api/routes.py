"""HTTP + SSE API consumed by the web UI (and usable with curl)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.agent.context import Runtime
from app.agent.loop import Agent
from app.api.schemas import (
    ApproveProposal,
    CreateSession,
    ManualStepDone,
    RejectProposal,
    Remediate,
    RunCodingAgent,
    SendMessage,
    StartInvestigation,
    WizardEnv,
    WizardPlan,
    WizardStart,
)
from app.bridge.fix_brief import build_fix_brief, load_demo_patch, run_coding_agent, write_fix_brief
from app.deploy.advisor import runway
from app.liara.errors import LiaraError
from app.liara.redaction import mask_obj
from app.policy.proposals import Impact
from app.policy.tiers import all_specs
from app.sre.verifier import IncidentVerifier

router = APIRouter(prefix="/api")


def _rt(request: Request) -> Runtime:
    return request.app.state.runtime


def _agent(request: Request) -> Agent:
    return request.app.state.agent


# ----------------------------------------------------------------- sessions


@router.post("/sessions")
def create_session(body: CreateSession, request: Request) -> dict[str, Any]:
    return _rt(request).store.create_session(
        title=body.title, app_name=body.app, project_path=body.path
    )


@router.get("/sessions")
def list_sessions(request: Request) -> list[dict[str, Any]]:
    return _rt(request).store.list_sessions()


@router.get("/sessions/{session_id}/timeline")
def timeline(session_id: str, request: Request, after: int = 0) -> list[dict[str, Any]]:
    rt = _rt(request)
    if rt.store.get_session(session_id) is None:
        raise HTTPException(404, "session not found")
    return rt.store.timeline(session_id, after_seq=after)


@router.get("/sessions/{session_id}/events")
async def events(session_id: str, request: Request) -> EventSourceResponse:
    rt = _rt(request)
    queue = rt.bus.subscribe(session_id)

    async def generator():  # type: ignore[no-untyped-def]
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {
                        "event": event.get("kind", "event"),
                        "data": json.dumps(event, ensure_ascii=False),
                    }
                except TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            rt.bus.unsubscribe(session_id, queue)

    return EventSourceResponse(generator())


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: SendMessage, request: Request) -> dict[str, Any]:
    rt = _rt(request)
    if rt.store.get_session(session_id) is None:
        raise HTTPException(404, "session not found")
    asyncio.create_task(
        _agent(request).handle(session_id, body.text, context={"app": body.app, "path": body.path})
    )
    return {"accepted": True}


# ---------------------------------------------------------------- proposals


@router.get("/proposals")
def list_proposals(
    request: Request, session_id: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    return [
        _rt(request).proposals.public_view(p)
        for p in _rt(request).store.list_proposals(session_id=session_id, status=status)
    ]


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, request: Request) -> dict[str, Any]:
    proposal = _rt(request).store.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(404, "proposal not found")
    return _rt(request).proposals.public_view(proposal)


@router.post("/proposals/{proposal_id}/approve")
async def approve(proposal_id: str, body: ApproveProposal, request: Request) -> dict[str, Any]:
    rt = _rt(request)
    token = rt.proposals.human_token(proposal_id)
    if token is None:
        raise HTTPException(
            409, "no approval token available for this proposal (already used or not pending)"
        )
    try:
        if body.edited_args:
            proposal = rt.store.get_proposal(proposal_id) or {}
            merged = {**proposal.get("args", {}), **body.edited_args}
            if "variables" in body.edited_args and isinstance(
                proposal.get("args", {}).get("variables"), dict
            ):
                merged["variables"] = {
                    **proposal["args"]["variables"],
                    **body.edited_args["variables"],
                }
            rt.store.update_proposal(proposal_id, args=merged)
        proposal = rt.proposals.approve(
            proposal_id, token, typed_confirmation=body.typed_confirmation
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    asyncio.create_task(rt.proposals.execute(proposal_id))
    return rt.proposals.public_view(proposal)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str, body: RejectProposal, request: Request) -> dict[str, Any]:
    rt = _rt(request)
    rt.proposals.human_token(proposal_id)
    try:
        return rt.proposals.public_view(rt.proposals.reject(proposal_id, reason=body.reason))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


# ------------------------------------------------------------------- wizard


@router.post("/sessions/{session_id}/wizard/start")
async def wizard_start(session_id: str, body: WizardStart, request: Request) -> dict[str, Any]:
    """Start the deploy wizard for an uploaded/cloned/local project (UI intake panel)."""
    rt = _rt(request)
    if rt.store.get_session(session_id) is None:
        raise HTTPException(404, "session not found")
    rt.emit(
        session_id,
        "message",
        {
            "role": "user",
            "text": f"دیپلوی {body.path}" + (f" با نام {body.app}" if body.app else ""),
        },
    )
    asyncio.create_task(
        _agent(request).wizard.start(session_id, body.path, app_name=body.app, plan_id=body.plan_id)
    )
    return {"accepted": True}


@router.get("/sessions/{session_id}/wizard/env-defaults")
async def wizard_env_defaults(session_id: str, request: Request) -> dict[str, Any]:
    """Prefill values read from the project's .env / .env.example. Served on demand only and
    never written to the timeline or audit, so secrets stay out of the local DB."""
    from app.deploy.analyzer import ProjectAnalyzer

    state = _agent(request).wizard.state(session_id)
    if state is None:
        raise HTTPException(404, "no deploy wizard in this session")
    values, sources = await asyncio.to_thread(ProjectAnalyzer(state.project_path).env_defaults)
    keys = state.analysis.env_keys if state.analysis else list(values)
    return {
        "values": {k: values.get(k, "") for k in keys},
        "sources": {k: sources.get(k, "") for k in keys},
    }


@router.post("/sessions/{session_id}/wizard/env")
async def wizard_env(session_id: str, body: WizardEnv, request: Request) -> dict[str, Any]:
    state = await _agent(request).wizard.provide_env(session_id, body.values)
    return {"stage": state.stage, "proposal_id": state.proposal_id}


@router.post("/sessions/{session_id}/wizard/plan")
async def wizard_plan(session_id: str, body: WizardPlan, request: Request) -> dict[str, Any]:
    state = await _agent(request).wizard.choose_plan(session_id, body.plan_id)
    return {"stage": state.stage, "plan_id": state.plan_id}


@router.post("/sessions/{session_id}/wizard/resume")
async def wizard_resume(session_id: str, request: Request) -> dict[str, Any]:
    state = await _agent(request).wizard.resume(session_id)
    return {"stage": state.stage}


@router.post("/manual-steps/done")
async def manual_step_done(body: ManualStepDone, request: Request) -> dict[str, Any]:
    """The human pressed 'Done' on a manual-step card: re-verify with the registered tool."""
    rt = _rt(request)
    limitation = rt.knowledge.limitation(body.limitation_id) or {}
    rt.store.audit(
        actor="human",
        action="manual_step_done",
        outcome="ok",
        session_id=body.session_id,
        detail={"limitation": body.limitation_id},
    )
    if body.limitation_id == "charge_account":
        state = (
            await _agent(request).wizard.resume(body.session_id)
            if _agent(request).wizard.state(body.session_id)
            else None
        )
        billing = await rt.client.billing()
        rt.emit(
            body.session_id,
            "message",
            {"role": "assistant", "text": f"موجودی فعلی: {billing.balance:,.0f} تومان."},
        )
        return {"stage": state.stage if state else "n/a", "balance": billing.balance}
    tool = limitation.get("verify_tool")
    if tool and body.context:
        result = await rt.proposals.run_auto(body.session_id, tool, body.context)
        rt.emit(
            body.session_id,
            "verification",
            {
                "manual_step": body.limitation_id,
                "ok": bool(result.get("status") in ("SET", "ACTIVE", "OK") or result.get("ok")),
                **mask_obj(result),
            },
        )
        return result
    return {"ok": True}


# ------------------------------------------------------------------- status


@router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    rt = _rt(request)
    try:
        apps, billing, me = await asyncio.gather(
            rt.client.list_projects(), rt.client.billing(), rt.client.me()
        )
    except LiaraError as exc:
        return {
            "ok": False,
            "error": exc.user_message,
            "mode": rt.settings.copilot_mode,
            "llm": rt.llm.available,
            "balance": 0,
            "hourly_burn": 0,
            "runway_hours": None,
            "runway_label": "—",
            "apps": [],
            "watcher": rt.watcher.status() if rt.watcher else {"running": False},
            "circuit_open": rt.client.circuit_open,
            "circuit_seconds_left": round(rt.client.circuit_seconds_left),
            "last_error": rt.client.last_error,
            "api_base": rt.settings.api_base,
        }
    allow = rt.settings.app_allowlist
    prices = {p.plan_id: p.price for p in me.project_plans()}
    burn = sum(prices.get(a.plan_id, 0.0) for a in apps if a.scale)
    hours, label = runway(billing.balance, burn) if burn else (None, "—")
    return {
        "ok": True,
        "mode": rt.settings.copilot_mode,
        "llm": rt.llm.available,
        "balance": billing.balance,
        "hourly_burn": burn,
        "runway_hours": hours,
        "runway_label": label,
        "apps": [
            {
                **a.model_dump(by_alias=False),
                "allowed": not allow or a.name in allow,
                "url": rt.probe.url_for(a.name),
            }
            for a in apps
        ],
        "watcher": rt.watcher.status() if rt.watcher else {"running": False},
        "circuit_open": rt.client.circuit_open,
        "circuit_seconds_left": round(rt.client.circuit_seconds_left),
        "last_error": rt.client.last_error,
        "api_base": rt.settings.api_base,
    }


@router.get("/apps/{app}/overview")
async def app_overview(app: str, request: Request) -> dict[str, Any]:
    rt = _rt(request)
    since = int(time.time()) - 1800
    project, cpu, memory, summary, probe, me = await asyncio.gather(
        rt.client.get_project(app),
        rt.client.metric(app, "cpu", since),
        rt.client.metric(app, "memory", since),
        rt.client.metrics_summary(app),
        rt.probe.probe(rt.probe.url_for(app)),
        rt.client.me(),
        return_exceptions=True,
    )
    if isinstance(project, Exception):
        raise HTTPException(404, getattr(project, "user_message", str(project)))
    plan = (
        next((p for p in me.project_plans() if p.plan_id == project.plan_id), None)
        if not isinstance(me, Exception)
        else None
    )
    return {
        "app": project.model_dump(by_alias=False, exclude={"envs"}),
        "env_keys": [e.key for e in project.envs],
        "plan": plan.model_dump(by_alias=False) if plan else None,
        "url": rt.probe.url_for(app),
        "cpu": cpu.result[0].points()[-60:]
        if not isinstance(cpu, Exception) and cpu.result
        else [],
        "memory": memory.result[0].points()[-60:]
        if not isinstance(memory, Exception) and memory.result
        else [],
        "now": {"cpu": summary.cpu, "memory": summary.memory}
        if not isinstance(summary, Exception)
        else None,
        "probe": probe if not isinstance(probe, Exception) else None,
        "watching": app in (rt.watcher.apps() if rt.watcher else []),
        "snapshots": rt.store.snapshots(app, since_ts=time.time() - 1800)[-90:],
    }


# ---------------------------------------------------------------- incidents


@router.get("/incidents")
def list_incidents(
    request: Request, app: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    return _rt(request).store.list_incidents(app_name=app, status=status)


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, request: Request) -> dict[str, Any]:
    incident = _rt(request).store.get_incident(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    return incident


@router.post("/sessions/{session_id}/investigate")
async def investigate(
    session_id: str, body: StartInvestigation, request: Request
) -> dict[str, Any]:
    rt = _rt(request)
    rt.store.update_session(session_id, app_name=body.app, mode="investigate")
    asyncio.create_task(
        _agent(request).investigator.investigate(
            body.app,
            session_id=session_id,
            trigger="ui",
            window_minutes=body.window_minutes,
            health_path=body.health_path,
        )
    )
    return {"accepted": True}


@router.post("/incidents/{incident_id}/verify")
async def verify_incident(incident_id: str, request: Request) -> dict[str, Any]:
    rt = _rt(request)
    incident = rt.store.get_incident(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    session_id = (
        incident["session_id"]
        or rt.store.create_session(title="verify", app_name=incident["app_name"])["id"]
    )
    verifier = IncidentVerifier(_agent(request).investigator.collector)
    result = await verifier.verify(
        incident["app_name"],
        incident.get("evidence") or {},
        on_round=lambda s: rt.emit(session_id, "verify_round", s),
    )
    rt.store.update_incident(
        incident_id, status="resolved" if result["ok"] else "investigated", closed_at=None
    )
    rt.emit(session_id, "verification", {"incident_id": incident_id, **result})
    return result


@router.post("/incidents/{incident_id}/remediate")
async def remediate(incident_id: str, body: Remediate, request: Request) -> dict[str, Any]:
    """Turn a remediation option of an investigated incident into a proposal (approval card)."""
    rt = _rt(request)
    incident = rt.store.get_incident(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    options = (incident.get("remediation") or {}).get("options", [])
    option = next((o for o in options if o["id"] == body.option_id), None)
    if option is None:
        raise HTTPException(404, "option not found")
    session_id = (
        body.session_id
        or incident["session_id"]
        or rt.store.create_session(title="remediation", app_name=incident["app_name"])["id"]
    )
    args = {**option["args"], **(body.edited_args or {}), "_session_id": session_id}
    if option["tool"] == "submit_fix":
        raise HTTPException(400, "use /incidents/{id}/run-coding-agent for code fixes")
    impact = Impact(
        cost_delta_hourly=option["cost_delta_hourly"],
        cost_delta_monthly=option["cost_delta_hourly"] * 720,
        reversibility=option["reversibility"],
        downtime=option["downtime"],
        rollback_plan=option.get("rationale", ""),
        notes=[f"ریسک: {option['risk']}"],
    )
    proposal, decision, _ = rt.proposals.propose(
        session_id,
        option["tool"],
        args,
        title=option["title"],
        summary=option["rationale"],
        impact=impact,
        incident_id=incident_id,
    )
    return {**rt.proposals.public_view(proposal, decision), "session_id": session_id}


@router.post("/incidents/{incident_id}/close")
def close_incident(incident_id: str, request: Request) -> dict[str, Any]:
    rt = _rt(request)
    incident = rt.store.get_incident(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    from app.store.db import now_iso

    rt.store.update_incident(incident_id, status="closed", closed_at=now_iso())
    if incident["session_id"]:
        rt.emit(
            incident["session_id"],
            "incident",
            {
                "id": incident_id,
                "app": incident["app_name"],
                "status": "closed",
                "summary": incident.get("summary"),
            },
        )
    rt.store.audit(
        actor="human",
        action="close_incident",
        outcome="closed",
        session_id=incident["session_id"],
        detail={"incident_id": incident_id},
    )
    return rt.store.get_incident(incident_id) or {}


@router.get("/incidents/{incident_id}/fix-brief")
def fix_brief(incident_id: str, request: Request) -> dict[str, Any]:
    rt = _rt(request)
    incident = rt.store.get_incident(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    brief = build_fix_brief(incident)
    rt.store.update_incident(incident_id, fix_brief=brief)
    return brief


@router.post("/incidents/{incident_id}/run-coding-agent")
async def run_agent(incident_id: str, body: RunCodingAgent, request: Request) -> dict[str, Any]:
    rt = _rt(request)
    incident = rt.store.get_incident(incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    session_id = (
        incident["session_id"]
        or rt.store.create_session(title="fix", app_name=incident["app_name"])["id"]
    )
    project_path = body.project_path or (rt.store.get_session(session_id) or {}).get(
        "project_path", ""
    )
    if not project_path:
        raise HTTPException(400, "project_path is required")
    brief = build_fix_brief(incident)
    brief_path = write_fix_brief(brief, Path(rt.settings.db_path).parent / "fix-briefs")
    rt.emit(session_id, "fix_brief", {"incident_id": incident_id, "path": str(brief_path), **brief})
    if body.demo_patch or not rt.settings.coding_agent_cmd:
        patch = load_demo_patch(project_path)
        result = {
            "ok": bool(patch),
            "branch": "demo",
            "patch": patch,
            "log": "deterministic demo patch"
            if patch
            else "no coding agent configured and no demo patch found",
        }
    else:
        result = await run_coding_agent(
            rt.settings.coding_agent_cmd, brief_path, project_path, incident_id
        )
    rt.emit(session_id, "patch", {"incident_id": incident_id, **mask_obj(result)})
    if result.get("ok") and result.get("patch"):
        proposal, decision, _ = rt.proposals.propose(
            session_id,
            "submit_fix",
            {
                "app": incident["app_name"],
                "path": project_path,
                "patch": result["patch"],
                "platform": (incident.get("evidence") or {})
                .get("project", {})
                .get("platform", "node"),
                "port": 3000,
                "_session_id": session_id,
            },
            title="اعمال پچ ایجنت کدنویسی و دیپلوی",
            summary="پچ بالا روی پروژه اعمال و نسخه‌ی جدید دیپلوی می‌شود؛ بعد از آن سلامت و علائم دوباره بررسی می‌شوند.",
            impact=Impact(
                reversibility="partial",
                downtime="brief",
                rollback_plan="بازگشت به نسخه‌ی قبلی (redeploy).",
            ),
            incident_id=incident_id,
        )
        result["proposal_id"] = proposal["id"]
        result["decision"] = decision.mode
    return mask_obj(result)


# ------------------------------------------------------------- misc / meta


@router.get("/audit")
def audit(
    request: Request, session_id: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    return _rt(request).store.audit_log(limit=limit, session_id=session_id)


@router.get("/limitations")
def limitations(request: Request) -> list[dict[str, Any]]:
    return _rt(request).knowledge.limitations()


@router.get("/policy/tools")
def policy_tools(request: Request) -> list[dict[str, Any]]:
    rt = _rt(request)
    return [
        {
            "name": s.name,
            "tier": s.tier.value,
            "description": s.description,
            "cost_impact": s.cost_impact,
            "reversibility": s.reversibility,
            "downtime": s.downtime,
            "verification": s.verification,
            "enabled": s.tier.value != "T3" or rt.settings.copilot_enable_guarded,
        }
        for s in all_specs()
    ]


@router.get("/watcher")
def watcher(request: Request) -> dict[str, Any]:
    rt = _rt(request)
    return rt.watcher.status() if rt.watcher else {"running": False}


@router.post("/watcher/{app}")
async def watch_app(
    app: str, request: Request, enabled: bool = True, session_id: str = ""
) -> dict[str, Any]:
    rt = _rt(request)
    if rt.watcher is None:
        raise HTTPException(400, "watcher disabled")
    if enabled:
        rt.watcher.watch(app, session_id=session_id)
    else:
        rt.watcher.unwatch(app)
    return rt.watcher.status()
