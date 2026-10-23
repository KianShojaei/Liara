"""Thin CLI: the same flows as the web UI, for terminals and demos.

copilot status                 account, balance, apps
copilot deploy ./my-site       deploy wizard (prints the proposal, asks for approval)
copilot investigate shop-demo  read-only incident investigation
copilot proposals              list pending proposals
copilot approve <id>           approve + execute + verify a proposal
copilot audit                  last audit rows
copilot chat "..."             send a message to the agent and print the timeline
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import typer

from app.agent.context import Runtime, build_runtime
from app.agent.loop import Agent
from app.liara.redaction import mask_obj

app = typer.Typer(help="Liara Ops Copilot CLI", no_args_is_help=True)


def _boot() -> tuple[Runtime, Agent]:
    rt = build_runtime()
    return rt, Agent(rt)


def _print(obj: Any) -> None:
    typer.echo(json.dumps(mask_obj(obj), ensure_ascii=False, indent=2, default=str))


def _print_timeline(rt: Runtime, session_id: str, after: int = 0) -> None:
    for event in rt.store.timeline(session_id, after_seq=after):
        payload = event["payload"]
        text = (
            payload.get("text")
            or payload.get("title")
            or payload.get("line")
            or payload.get("summary")
            or payload.get("stage")
            or ""
        )
        if event["kind"] == "proposal":
            text = f"{payload['id']} [{payload['tier']}] {payload['title']} -> {payload['status']}\n{payload['summary']}"
        if event["kind"] == "hypotheses":
            text = "\n".join(f"- {h['cause']} ({h['confidence']:.0%})" for h in payload["items"])
        if event["kind"] == "remediation":
            text = "\n".join(
                f"- {o['title']} [{o['risk']}] {o['rationale']}" for o in payload["options"]
            )
        typer.echo(f"[{event['kind']}] {text}")


async def _chat(text: str, session_title: str) -> None:
    rt, agent = _boot()
    try:
        session = rt.store.create_session(title=session_title)
        await agent.handle(session["id"], text)
        _print_timeline(rt, session["id"])
        pending = rt.store.list_proposals(session_id=session["id"], status="pending_approval")
        for proposal in pending:
            if typer.confirm(f"Approve '{proposal['title']}'?", default=False):
                token = rt.proposals.human_token(proposal["id"]) or ""
                rt.proposals.approve(proposal["id"], token, actor="cli")
                seq = len(rt.store.timeline(session["id"]))
                await rt.proposals.execute(proposal["id"], actor="cli")
                _print_timeline(rt, session["id"], after=seq)
    finally:
        await rt.aclose()


@app.command()
def chat(text: str) -> None:
    """Send a message to the copilot."""
    asyncio.run(_chat(text, "cli chat"))


@app.command()
def deploy(
    path: str, app_name: str = typer.Option("", "--app"), plan: str = typer.Option("", "--plan")
) -> None:
    """Run the deploy wizard for a project folder."""
    message = (
        f"دیپلوی {path}"
        + (f" برنامه {app_name}" if app_name else "")
        + (f" {plan}" if plan else "")
    )
    asyncio.run(_chat(message, "cli deploy"))


@app.command()
def investigate(app_name: str) -> None:
    """Read-only investigation of an app."""
    asyncio.run(_chat(f"بررسی کن {app_name} مشکل دارد", "cli investigate"))


@app.command()
def status() -> None:
    """Account, balance and apps."""

    async def run() -> None:
        rt, _ = _boot()
        try:
            me, apps = await asyncio.gather(rt.client.me(), rt.client.list_projects())
            balance = await rt.client.account_balance(me)
            _print(
                {
                    "mode": rt.settings.copilot_mode,
                    "user": me.user.email or me.user.fullname,
                    "team": bool(me.team),
                    "balance": balance,
                    "apps": [a.model_dump(by_alias=False) for a in apps],
                }
            )
        finally:
            await rt.aclose()

    asyncio.run(run())


@app.command()
def proposals(status_filter: str = typer.Option("pending_approval", "--status")) -> None:
    """List proposals."""
    rt = build_runtime()
    try:
        for proposal in rt.store.list_proposals(status=status_filter or None):
            typer.echo(
                f"{proposal['id']}  [{proposal['tier']}] {proposal['status']:18} {proposal['tool']:16} {proposal['title']}"
            )
    finally:
        rt.store.close()


@app.command()
def approve(
    proposal_id: str,
    confirmation: str = typer.Option("", "--confirm", help="typed confirmation for T3"),
) -> None:
    """Approve, execute and verify a proposal."""

    async def run() -> None:
        rt, _agent = _boot()
        try:
            token = rt.proposals.human_token(proposal_id)
            if token is None:
                typer.echo(
                    "No approval token: the proposal is not pending or was already approved/rejected."
                )
                raise typer.Exit(1)
            rt.proposals.approve(
                proposal_id, token, actor="cli", typed_confirmation=confirmation or None
            )
            _print(rt.proposals.public_view(await rt.proposals.execute(proposal_id, actor="cli")))
        finally:
            await rt.aclose()

    asyncio.run(run())


@app.command()
def audit(limit: int = 30) -> None:
    """Show the append-only audit log."""
    rt = build_runtime()
    try:
        for row in rt.store.audit_log(limit=limit):
            typer.echo(
                f"{row['ts']}  {row['actor']:10} {row['action']:12} {row['outcome']:20} {row.get('tool') or '':16} {row.get('proposal_id') or ''}"
            )
    finally:
        rt.store.close()


@app.command()
def limitations() -> None:
    """What the API cannot do."""
    from app.config import get_settings
    from app.knowledge.rag import KnowledgeBase

    for item in KnowledgeBase(get_settings()).limitations():
        typer.echo(f"- {item['title']}: {item['summary']}")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the web backend."""
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port)


if __name__ == "__main__":
    app()
