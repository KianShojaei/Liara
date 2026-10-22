"""Runtime wiring: one place that builds the store, client, policy, proposals and engines.

Used by the FastAPI app, the CLI and the MCP server so all three share identical behaviour.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings, get_settings
from app.deploy.engine import DeployEngine
from app.deploy.verifier import DeployVerifier, HttpProbe
from app.liara.client import LiaraClient, build_client
from app.policy.engine import PolicyConfig, PolicyEngine
from app.policy.proposals import ProposalService
from app.store.db import Store

Listener = Callable[[dict[str, Any]], None]


class EventBus:
    """Fan-out of timeline events to SSE subscribers (per session)."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if session_id in self._queues and queue in self._queues[session_id]:
            self._queues[session_id].remove(queue)

    def publish(self, session_id: str, event: dict[str, Any]) -> None:
        for queue in list(self._queues.get(session_id, [])) + list(self._queues.get("*", [])):
            queue.put_nowait(event)


@dataclass
class Runtime:
    settings: Settings
    store: Store
    client: LiaraClient
    policy: PolicyEngine
    proposals: ProposalService
    probe: HttpProbe
    verifier: DeployVerifier
    deploy_engine: DeployEngine
    bus: EventBus = field(default_factory=EventBus)
    llm: Any = None  # LLMGateway | None, attached lazily to avoid import cycles
    knowledge: Any = None
    watcher: Any = None

    def emit(self, session_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = self.store.append_event(session_id, kind, payload)
        self.bus.publish(session_id, event)
        return event

    async def aclose(self) -> None:
        if self.watcher is not None:
            await self.watcher.stop()
        await self.client.aclose()
        self.store.close()


def build_runtime(
    settings: Settings | None = None, *, probe_base_url: str | None = None
) -> Runtime:
    settings = settings or get_settings()
    store = Store(settings.db_path)
    client = build_client(settings)
    policy = PolicyEngine(
        PolicyConfig(
            app_allowlist=settings.app_allowlist,
            cost_guard_hourly=settings.copilot_cost_guard_hourly,
            enable_guarded=settings.copilot_enable_guarded,
            dry_run=settings.copilot_dry_run,
        ),
        secret=store.get_or_create_secret(),
    )
    bus = EventBus()

    def emit(session_id: str, kind: str, payload: dict[str, Any]) -> None:
        bus.publish(session_id, store.append_event(session_id, kind, payload))

    proposals = ProposalService(store, policy, emit=emit)
    probe = HttpProbe(
        base_url_override=probe_base_url
        or (None if settings.copilot_mode == "live" else _mock_probe_base(settings))
    )
    verifier = DeployVerifier(client, probe)
    engine = DeployEngine(
        client,
        cli_bin=settings.liara_cli_bin,
        api_token=settings.liara_api_token,
        team_id=settings.liara_team_id,
        prefer_cli=settings.copilot_mode == "live",
    )
    runtime = Runtime(
        settings=settings,
        store=store,
        client=client,
        policy=policy,
        proposals=proposals,
        probe=probe,
        verifier=verifier,
        deploy_engine=engine,
        bus=bus,
    )

    from app.agent.tools import register_tools  # local import: tools need the runtime type
    from app.knowledge.rag import KnowledgeBase
    from app.llm.gateway import LLMGateway

    runtime.llm = LLMGateway(settings)
    runtime.knowledge = KnowledgeBase(settings)
    register_tools(runtime)
    return runtime


def _mock_probe_base(settings: Settings) -> str | None:
    """In mock mode the demo app runs locally; probe it there (DEMO_APP_URL) if set."""
    import os

    return os.environ.get("DEMO_APP_URL") or None
