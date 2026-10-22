"""MCP server exposing the same policy-gated tools to IDEs and coding agents.

Run (stdio):            python -m app.mcp_server
Run (streamable http):  python -m app.mcp_server --http --port 8765

Claude Code example:
  claude mcp add liara-ops -- /path/to/backend/.venv/bin/python -m app.mcp_server

Safety: mutating tools never execute here. They return {"status": "pending_approval",
"proposal_id": ...}; approval happens only in the web UI or CLI (human channel). There is
no approve tool on purpose, so a model can never approve its own action.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from app.agent.context import Runtime, build_runtime
from app.bridge.fix_brief import build_fix_brief
from app.liara.redaction import mask_obj
from app.policy.proposals import Impact
from app.policy.tiers import Tier, all_specs, get_spec
from app.sre.investigator import Investigator

server = MCPServer(
    "liara-ops-copilot",
    instructions="Operations copilot for Liara. Read tools run immediately; state-changing tools return pending_approval and must be approved by the human in the Copilot UI.",
)

_runtime: Runtime | None = None
_session_id: str = ""


def _rt() -> Runtime:
    global _runtime, _session_id
    if _runtime is None:
        _runtime = build_runtime()
        from app.agent.loop import Agent

        Agent(_runtime)  # registers composite executors
        _session_id = _runtime.store.create_session(title="MCP session", mode="mcp")["id"]
    return _runtime


def _dump(value: Any) -> str:
    return json.dumps(mask_obj(value), ensure_ascii=False, default=str)


async def _run_read(tool: str, args: dict[str, Any]) -> str:
    rt = _rt()
    try:
        return _dump(await rt.proposals.run_auto(_session_id, tool, args))
    except Exception as exc:  # noqa: BLE001
        return _dump({"error": getattr(exc, "user_message", str(exc))})


def _propose(tool: str, args: dict[str, Any], title: str, summary: str) -> str:
    rt = _rt()
    spec = get_spec(tool)
    proposal, decision, _token = rt.proposals.propose(
        _session_id,
        tool,
        args,
        title=title,
        summary=summary,
        impact=Impact(reversibility=spec.reversibility, downtime=spec.downtime),
    )
    return _dump(
        {
            "status": "pending_approval" if decision.mode == "approval" else "blocked",
            "proposal_id": proposal["id"],
            "tier": decision.tier.value,
            "reasons": decision.reasons,
            "approve_in": "Copilot web UI -> approval card, or: copilot approve " + proposal["id"],
        }
    )


# ------------------------------------------------------------------ reads (T0)


@server.tool(description="Account profile, team mode and the live plan catalog (GET /v1/me).")
async def get_account() -> str:
    return await _run_read("get_account", {})


@server.tool(description="Wallet balance (GET /v1/billing). Charging is NOT possible via API.")
async def get_billing() -> str:
    return await _run_read("get_billing", {})


@server.tool(description="List apps in the account.")
async def list_apps() -> str:
    return await _run_read("list_apps", {})


@server.tool(description="App details: plan, state, env keys (values masked).")
async def get_app(app: str) -> str:
    return await _run_read("get_app", {"app": app})


@server.tool(description="Recent logs of an app (last N minutes).")
async def get_logs(app: str, minutes: int = 10, limit: int = 100) -> str:
    return await _run_read("get_logs", {"app": app, "minutes": minutes, "limit": limit})


@server.tool(description="Metric series: kind in cpu|memory|network-receive|network-transmit.")
async def get_metrics(app: str, kind: str = "memory", minutes: int = 30) -> str:
    return await _run_read("get_metrics", {"app": app, "kind": kind, "minutes": minutes})


@server.tool(description="Release history of an app.")
async def get_releases(app: str, count: int = 10) -> str:
    return await _run_read("get_releases", {"app": app, "count": count})


@server.tool(
    description="Health check: container state, HTTP probe, error burst (runs now, read-only)."
)
async def health_check(app: str, health_path: str = "/") -> str:
    return await _run_read("run_health_check", {"app": app, "health_path": health_path})


@server.tool(description="Analyze a local project folder: platform, port, env keys, DB needs.")
async def analyze_project(path: str) -> str:
    return await _run_read("analyze_project", {"path": path})


@server.tool(description="Plan recommendation with hourly cost and runway for a project folder.")
async def recommend_plan(path: str) -> str:
    return await _run_read("recommend_plan", {"path": path})


@server.tool(description="What the Liara API cannot do (manual steps).")
async def get_limitations() -> str:
    return await _run_read("get_limitations", {})


# ------------------------------------------------------------- incidents (T0)


@server.tool(
    description="Run a read-only incident investigation and return evidence, ranked hypotheses and remediation options."
)
async def investigate(app: str, window_minutes: int = 30) -> str:
    rt = _rt()
    incident = await Investigator(rt).investigate(
        app, session_id=_session_id, trigger="mcp", window_minutes=window_minutes
    )
    return _dump(
        {k: incident.get(k) for k in ("id", "status", "summary", "hypotheses", "remediation")}
    )


@server.tool(
    description="Get an incident (evidence, hypotheses, remediation) by id, or the latest open one for an app."
)
async def get_incident(incident_id: str = "", app: str = "") -> str:
    rt = _rt()
    incident = (
        rt.store.get_incident(incident_id)
        if incident_id
        else (rt.store.list_incidents(app_name=app or None, limit=1) or [None])[0]
    )
    return _dump(incident or {"error": "no incident found"})


@server.tool(
    description="FixBrief for a coding agent: symptom, timeline, evidence, suspected files, fix direction, acceptance criteria."
)
async def get_fix_brief(incident_id: str) -> str:
    rt = _rt()
    incident = rt.store.get_incident(incident_id)
    if incident is None:
        return _dump({"error": "incident not found"})
    brief = build_fix_brief(incident)
    rt.store.update_incident(incident_id, fix_brief=brief)
    return _dump(brief)


@server.tool(
    description="Submit the result of a fix (unified diff + notes). Creates a pending_approval proposal to apply the patch and redeploy; the human approves in the UI."
)
async def submit_fix_result(
    incident_id: str, project_path: str, patch: str, notes: str = ""
) -> str:
    rt = _rt()
    incident = rt.store.get_incident(incident_id)
    if incident is None:
        return _dump({"error": "incident not found"})
    rt.emit(
        _session_id,
        "patch",
        {
            "incident_id": incident_id,
            "patch": patch,
            "notes": notes,
            "ok": True,
            "branch": "coding-agent",
        },
    )
    platform = ((incident.get("evidence") or {}).get("project") or {}).get("platform", "node")
    return _propose(
        "submit_fix",
        {
            "app": incident["app_name"],
            "path": project_path,
            "patch": patch,
            "platform": platform,
            "port": 3000,
            "_session_id": _session_id,
        },
        "اعمال پچ ایجنت کدنویسی و دیپلوی",
        notes or "پچ ارسال‌شده توسط ایجنت کدنویسی",
    )


# ---------------------------------------------------------- mutations (T2)


@server.tool(description="[needs approval] Restart an app.")
async def restart_app(app: str) -> str:
    return _propose("restart_app", {"app": app}, f"ری‌استارت {app}", "درخواست از طریق MCP")


@server.tool(description="[needs approval] Set environment variables (restarts the app).")
async def set_env(app: str, variables: dict[str, str]) -> str:
    return _propose(
        "set_env",
        {"app": app, "variables": variables},
        f"تنظیم متغیر محیطی روی {app}",
        "درخواست از طریق MCP: " + ", ".join(variables),
    )


@server.tool(description="[needs approval] Change plan.")
async def resize_app(app: str, plan_id: str) -> str:
    return _propose(
        "resize_app",
        {"app": app, "plan_id": plan_id},
        f"تغییر پلن {app} به {plan_id}",
        "درخواست از طریق MCP",
    )


@server.tool(description="[needs approval] Turn an app on (1) or off (0).")
async def scale_app(app: str, scale: int) -> str:
    return _propose(
        "scale_app",
        {"app": app, "scale": scale},
        ("روشن" if scale else "خاموش") + f" کردن {app}",
        "درخواست از طریق MCP",
    )


@server.tool(
    description="[needs approval] Deploy a local project folder to an app (creates the app if needed)."
)
async def deploy_project(
    path: str, app: str, plan_id: str = "", platform: str = "", port: int = 0
) -> str:
    rt = _rt()
    analysis = await rt.proposals.run_auto(_session_id, "analyze_project", {"path": path})
    args = {
        "app": app,
        "path": path,
        "plan_id": plan_id or "ir-small",
        "platform": platform or analysis["platform"],
        "port": port or analysis["port"],
        "variables": {},
        "health_path": analysis["health_path"],
        "create": True,
        "_session_id": _session_id,
    }
    try:
        await rt.client.get_project(app)
        args["create"] = False
    except Exception:  # noqa: BLE001
        pass
    return _propose("deploy_project", args, f"دیپلوی {app}", "درخواست از طریق MCP")


@server.tool(
    description="Proposal status (pending_approval, approved, executed, verified, failed...)."
)
async def get_proposal(proposal_id: str) -> str:
    rt = _rt()
    proposal = rt.store.get_proposal(proposal_id)
    return _dump(rt.proposals.public_view(proposal) if proposal else {"error": "not found"})


@server.tool(description="Policy registry: every tool with its risk tier and metadata.")
async def list_policy() -> str:
    return _dump(
        [
            {
                "name": s.name,
                "tier": s.tier.value,
                "description": s.description,
                "enabled": s.tier != Tier.T3 or _rt().settings.copilot_enable_guarded,
            }
            for s in all_specs()
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--http", action="store_true", help="serve over streamable HTTP instead of stdio"
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.http:
        server.settings.port = args.port
        server.run(transport="streamable-http")
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
