"""Proposal lifecycle: Proposal -> Approval -> Execute -> Verify -> Audit.

A ProposalService never knows how a tool is implemented; it is handed an `Executor`
callable per tool. That keeps the human-in-the-loop gate in one place for the web UI,
the CLI and the MCP server alike.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.liara.redaction import mask_obj
from app.policy.engine import Decision, PolicyEngine
from app.policy.tiers import get_spec
from app.store.db import Store, new_id

log = logging.getLogger("copilot.proposals")

ToolResult = dict[str, Any]
Executor = Callable[[dict[str, Any]], Awaitable[ToolResult]]
Verifier = Callable[[dict[str, Any], ToolResult], Awaitable[dict[str, Any]]]
EventSink = Callable[[str, str, dict[str, Any]], None]  # (session_id, kind, payload)

STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_BLOCKED = "blocked"
STATUS_RUNNING = "running"
STATUS_EXECUTED = "executed"
STATUS_FAILED = "failed"
STATUS_VERIFIED = "verified"
STATUS_VERIFY_FAILED = "verification_failed"


@dataclass
class Impact:
    cost_delta_hourly: float = 0.0
    cost_delta_monthly: float = 0.0
    reversibility: str = "reversible"
    downtime: str = "none"
    rollback_plan: str = ""
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_delta_hourly": round(self.cost_delta_hourly, 2),
            "cost_delta_monthly": round(self.cost_delta_monthly, 2),
            "reversibility": self.reversibility,
            "downtime": self.downtime,
            "rollback_plan": self.rollback_plan,
            "notes": self.notes or [],
        }


class ProposalService:
    def __init__(self, store: Store, policy: PolicyEngine, *, emit: EventSink | None = None):
        self.store = store
        self.policy = policy
        self._executors: dict[str, Executor] = {}
        self._verifiers: dict[str, Verifier] = {}
        self._emit = emit or (lambda *_: None)

    def register(self, tool: str, executor: Executor, verifier: Verifier | None = None) -> None:
        get_spec(tool)  # raises on unknown tool
        self._executors[tool] = executor
        if verifier:
            self._verifiers[tool] = verifier

    # ----------------------------------------------------------- propose

    def propose(
        self,
        session_id: str,
        tool: str,
        args: dict[str, Any],
        *,
        title: str,
        summary: str,
        impact: Impact | None = None,
        incident_id: str | None = None,
    ) -> tuple[dict[str, Any], Decision, str | None]:
        """Creates a proposal row. Returns (proposal, decision, approval_token).

        The approval token is returned only so the *human* channel (UI/CLI) can hand it back;
        it is never written to the timeline payload seen by the model."""
        impact = impact or Impact()
        spec = get_spec(tool)
        impact.reversibility = impact.reversibility or spec.reversibility
        impact.downtime = impact.downtime or spec.downtime
        decision = self.policy.decide(tool, args, cost_delta_hourly=impact.cost_delta_hourly)

        proposal_id = new_id("prp")
        token, token_hash = (None, None)
        if decision.mode == "approval":
            token, token_hash = self.policy.issue_approval_token(proposal_id)
            # Human channel only: the raw token is handed to the web UI / CLI through the local
            # store, never through MCP or the model, so an agent cannot approve its own proposal.
            self.store.put_human_token(proposal_id, token)
        status = {"approval": STATUS_PENDING, "blocked": STATUS_BLOCKED}.get(
            decision.mode, STATUS_APPROVED
        )

        proposal = self.store.create_proposal(
            {
                "id": proposal_id,
                "session_id": session_id,
                "status": status,
                "tool": tool,
                "args": mask_obj(args) if tool != "set_env" else args,
                "tier": decision.tier.value,
                "title": title,
                "summary": summary,
                "impact": impact.to_dict(),
                "idempotency_key": f"{proposal_id}:{self.policy.idempotency_key(tool, args)}",
                "approval_token_hash": token_hash,
                "incident_id": incident_id,
            }
        )
        self.store.audit(
            actor="agent",
            action="propose",
            outcome=status,
            tool=tool,
            tier=decision.tier.value,
            proposal_id=proposal_id,
            session_id=session_id,
            detail={"reasons": decision.reasons, "args": mask_obj(args)},
        )
        self._emit(session_id, "proposal", self.public_view(proposal, decision))
        return proposal, decision, token

    @staticmethod
    def public_view(proposal: dict[str, Any], decision: Decision | None = None) -> dict[str, Any]:
        view = {
            k: v for k, v in proposal.items() if k not in ("approval_token_hash", "idempotency_key")
        }
        if decision:
            view["decision"] = {
                "mode": decision.mode,
                "reasons": decision.reasons,
                "typed_confirmation": decision.requires_typed_confirmation,
            }
        if view.get("tool") == "set_env":
            view["args"] = mask_obj(view["args"])
        return view

    # ----------------------------------------------------------- approve

    def approve(
        self,
        proposal_id: str,
        token: str,
        *,
        actor: str = "human",
        typed_confirmation: str | None = None,
    ) -> dict[str, Any]:
        proposal = self._require(proposal_id)
        if proposal["status"] != STATUS_PENDING:
            raise PermissionError(f"proposal is {proposal['status']}, not pending")
        if not self.policy.verify_approval_token(
            proposal_id, token, proposal.get("approval_token_hash")
        ):
            self.store.audit(
                actor=actor,
                action="approve",
                outcome="rejected_bad_token",
                proposal_id=proposal_id,
                session_id=proposal["session_id"],
            )
            raise PermissionError("invalid approval token")
        if proposal["tier"] == "T3" and typed_confirmation != proposal["args"].get(
            "app", "CONFIRM"
        ):
            raise PermissionError("typed confirmation did not match")
        # single use: drop the hash so the same token cannot be replayed
        self.store.update_proposal(proposal_id, status=STATUS_APPROVED, approval_token_hash=None)
        self.store.audit(
            actor=actor,
            action="approve",
            outcome="approved",
            tool=proposal["tool"],
            tier=proposal["tier"],
            proposal_id=proposal_id,
            session_id=proposal["session_id"],
        )
        self._emit(
            proposal["session_id"],
            "proposal_update",
            {"id": proposal_id, "status": STATUS_APPROVED},
        )
        return self._require(proposal_id)

    def human_token(self, proposal_id: str) -> str | None:
        """Single-use: the token is forgotten the first time it is handed out."""
        return self.store.pop_human_token(proposal_id)

    def reject(self, proposal_id: str, *, actor: str = "human", reason: str = "") -> dict[str, Any]:
        proposal = self._require(proposal_id)
        self.store.update_proposal(
            proposal_id, status=STATUS_REJECTED, approval_token_hash=None, result={"reason": reason}
        )
        self.store.audit(
            actor=actor,
            action="reject",
            outcome="rejected",
            tool=proposal["tool"],
            tier=proposal["tier"],
            proposal_id=proposal_id,
            session_id=proposal["session_id"],
            detail={"reason": reason},
        )
        self._emit(
            proposal["session_id"],
            "proposal_update",
            {"id": proposal_id, "status": STATUS_REJECTED, "reason": reason},
        )
        return self._require(proposal_id)

    # ----------------------------------------------------------- execute

    async def execute(self, proposal_id: str, *, actor: str = "system") -> dict[str, Any]:
        proposal = self._require(proposal_id)
        if proposal["status"] != STATUS_APPROVED:
            raise PermissionError(f"proposal is {proposal['status']}, cannot execute")
        executor = self._executors.get(proposal["tool"])
        if executor is None:
            raise KeyError(f"no executor for {proposal['tool']}")
        session_id = proposal["session_id"]
        self.store.update_proposal(proposal_id, status=STATUS_RUNNING)
        self._emit(session_id, "proposal_update", {"id": proposal_id, "status": STATUS_RUNNING})

        if self.policy.config.dry_run:
            result: ToolResult = {
                "dry_run": True,
                "would_call": proposal["tool"],
                "args": mask_obj(proposal["args"]),
            }
        else:
            try:
                result = await executor(proposal["args"])
            except Exception as exc:  # noqa: BLE001 - every failure must be visible
                message = getattr(exc, "user_message", str(exc))
                self.store.update_proposal(
                    proposal_id, status=STATUS_FAILED, result={"error": message}
                )
                self.store.audit(
                    actor=actor,
                    action="execute",
                    outcome="failed",
                    tool=proposal["tool"],
                    tier=proposal["tier"],
                    proposal_id=proposal_id,
                    session_id=session_id,
                    detail={"error": message},
                )
                self._emit(
                    session_id,
                    "proposal_update",
                    {"id": proposal_id, "status": STATUS_FAILED, "error": message},
                )
                return self._require(proposal_id)

        self.store.update_proposal(proposal_id, status=STATUS_EXECUTED, result=mask_obj(result))
        self.store.audit(
            actor=actor,
            action="execute",
            outcome="executed",
            tool=proposal["tool"],
            tier=proposal["tier"],
            proposal_id=proposal_id,
            session_id=session_id,
            detail={"result": mask_obj(result)},
        )
        self._emit(
            session_id,
            "proposal_update",
            {"id": proposal_id, "status": STATUS_EXECUTED, "result": mask_obj(result)},
        )

        verifier = self._verifiers.get(proposal["tool"])
        if verifier and not self.policy.config.dry_run:
            verification = await verifier(proposal["args"], result)
            status = STATUS_VERIFIED if verification.get("ok") else STATUS_VERIFY_FAILED
            self.store.update_proposal(proposal_id, status=status, verification=verification)
            self.store.audit(
                actor="verifier",
                action="verify",
                outcome=status,
                tool=proposal["tool"],
                tier=proposal["tier"],
                proposal_id=proposal_id,
                session_id=session_id,
                detail=verification,
            )
            self._emit(
                session_id,
                "verification",
                {"proposal_id": proposal_id, "status": status, **verification},
            )
        return self._require(proposal_id)

    async def run_auto(
        self, session_id: str, tool: str, args: dict[str, Any], *, title: str = ""
    ) -> ToolResult:
        """T0/T1 path: policy check, execute immediately, audit, emit a notice for T1."""
        decision = self.policy.decide(tool, args)
        if not decision.allowed_now:
            raise PermissionError("; ".join(decision.reasons) or f"{tool} needs approval")
        executor = self._executors[tool]
        if decision.mode == "notice":
            self._emit(
                session_id,
                "notice",
                {
                    "tool": tool,
                    "title": title or get_spec(tool).description,
                    "args": mask_obj(args),
                },
            )
        try:
            result = await executor(args)
        except Exception as exc:  # noqa: BLE001
            message = getattr(exc, "user_message", str(exc))
            self.store.audit(
                actor="agent",
                action="run",
                outcome="failed",
                tool=tool,
                tier=decision.tier.value,
                session_id=session_id,
                detail={"error": message, "args": mask_obj(args)},
            )
            raise
        if decision.mode == "notice":
            self.store.audit(
                actor="agent",
                action="run",
                outcome="ok",
                tool=tool,
                tier=decision.tier.value,
                session_id=session_id,
                detail={"args": mask_obj(args)},
            )
        return result

    # ------------------------------------------------------------ helpers

    def _require(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            raise KeyError(f"unknown proposal {proposal_id}")
        return proposal
