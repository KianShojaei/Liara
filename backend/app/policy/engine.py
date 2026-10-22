"""Policy decisions: who may run what, and under which guard.

PolicyEngine.decide(tool, args) -> Decision
  mode: "auto" | "notice" | "approval" | "blocked"
Guards applied in order: registry tier, guarded-tools switch, app allowlist, cost guard,
dry-run. Approvals are single-use HMAC tokens bound to a proposal id; the LLM never sees
them, so a model cannot approve its own action.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from typing import Any, Literal

from app.policy.tiers import Tier, ToolSpec, get_spec

DecisionMode = Literal["auto", "notice", "approval", "blocked"]


@dataclass
class Decision:
    mode: DecisionMode
    tier: Tier
    reasons: list[str] = field(default_factory=list)
    requires_typed_confirmation: bool = False

    @property
    def allowed_now(self) -> bool:
        return self.mode in ("auto", "notice")


@dataclass
class PolicyConfig:
    app_allowlist: set[str] = field(default_factory=set)
    cost_guard_hourly: float = 5000.0
    enable_guarded: bool = False
    dry_run: bool = False


class PolicyEngine:
    def __init__(self, config: PolicyConfig, *, secret: bytes | None = None):
        self.config = config
        self._secret = secret or secrets.token_bytes(32)

    # ------------------------------------------------------------- decide

    def decide(
        self, tool: str, args: dict[str, Any], *, cost_delta_hourly: float = 0.0
    ) -> Decision:
        spec = get_spec(tool)
        reasons: list[str] = []

        if not self._app_allowed(spec, args):
            return Decision(
                "blocked",
                spec.tier,
                [f"app '{args.get(spec.app_arg or '')}' is outside COPILOT_APP_ALLOWLIST"],
            )

        if spec.tier == Tier.T3 and not self.config.enable_guarded:
            return Decision(
                "blocked",
                spec.tier,
                ["guarded (T3) actions are disabled; set COPILOT_ENABLE_GUARDED=true"],
            )

        if cost_delta_hourly > self.config.cost_guard_hourly:
            return Decision(
                "blocked",
                spec.tier,
                [
                    f"cost guard: +{cost_delta_hourly:.0f} Toman/h exceeds the limit of {self.config.cost_guard_hourly:.0f}"
                ],
            )

        if spec.tier == Tier.T0:
            return Decision("auto", spec.tier, reasons)
        if spec.tier == Tier.T1:
            return Decision("notice", spec.tier, ["low-risk write, runs with a visible notice"])
        if spec.tier == Tier.T2:
            reasons.append("state-changing action: needs your approval")
            if self.config.dry_run:
                reasons.append("dry-run mode: execution will be simulated")
            return Decision("approval", spec.tier, reasons)
        return Decision(
            "approval",
            spec.tier,
            ["guarded action: typed confirmation required"],
            requires_typed_confirmation=True,
        )

    def _app_allowed(self, spec: ToolSpec, args: dict[str, Any]) -> bool:
        if not self.config.app_allowlist or spec.app_arg is None:
            return True
        target = args.get(spec.app_arg)
        return target is None or target in self.config.app_allowlist

    # ----------------------------------------------------------- approvals

    def issue_approval_token(self, proposal_id: str) -> tuple[str, str]:
        """Returns (token, token_hash). The token goes to the human UI only; the hash is stored."""
        nonce = secrets.token_hex(8)
        signature = hmac.new(
            self._secret, f"{proposal_id}:{nonce}".encode(), hashlib.sha256
        ).hexdigest()[:32]
        token = f"{nonce}.{signature}"
        return token, self.hash_token(token)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def verify_approval_token(self, proposal_id: str, token: str, stored_hash: str | None) -> bool:
        if not token or not stored_hash:
            return False
        if not hmac.compare_digest(self.hash_token(token), stored_hash):
            return False
        try:
            nonce, signature = token.split(".", 1)
        except ValueError:
            return False
        expected = hmac.new(
            self._secret, f"{proposal_id}:{nonce}".encode(), hashlib.sha256
        ).hexdigest()[:32]
        return hmac.compare_digest(signature, expected)

    @staticmethod
    def idempotency_key(tool: str, args: dict[str, Any]) -> str:
        import json

        canonical = json.dumps({"tool": tool, "args": args}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()[:24]
