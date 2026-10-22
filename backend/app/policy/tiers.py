"""Risk tiers and the tool registry.

The LLM never executes anything: every side effect goes through a registered tool whose
tier, cost impact, reversibility and downtime are declared here, not decided at runtime.

  T0  read            -> runs automatically
  T1  safe write      -> runs automatically with a visible notice
  T2  needs approval  -> proposal card, human approves in UI/CLI, then execute + verify
  T3  guarded         -> disabled unless COPILOT_ENABLE_GUARDED=true, typed confirmation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

Reversibility = Literal["reversible", "partial", "irreversible"]
Downtime = Literal["none", "brief", "yes"]


class Tier(str, Enum):
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    tier: Tier
    description: str
    cost_impact: Literal["none", "may_change", "increases", "decreases"] = "none"
    reversibility: Reversibility = "reversible"
    downtime: Downtime = "none"
    verification: str = ""  # what "done" means, in plain words
    app_arg: str | None = "app"  # argument that names the target app (for allowlist checks)
    tags: tuple[str, ...] = field(default_factory=tuple)


_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    _REGISTRY[spec.name] = spec
    return spec


def get_spec(name: str) -> ToolSpec:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unregistered tool: {name}") from exc


def all_specs() -> list[ToolSpec]:
    return sorted(_REGISTRY.values(), key=lambda s: (s.tier.value, s.name))


# ----------------------------------------------------------------- T0 reads
for _name, _desc in {
    "get_account": "Account profile, team mode and plan catalog (GET /v1/me)",
    "get_billing": "Wallet balance (GET /v1/billing)",
    "list_apps": "List apps (GET /v1/projects)",
    "get_app": "App details: plan, state, envs (GET /v1/projects/{name})",
    "get_logs": "Recent logs (GET /v1/projects/{name}/logs)",
    "get_events": "Platform events (GET /v1/projects/{name}/events)",
    "get_applets": "Container instances and their state (GET .../applets)",
    "get_releases": "Release history (GET .../releases)",
    "get_metrics": "CPU / memory / network series (GET .../metrics/*)",
    "get_domains": "Domains attached to an app (GET /v1/domains?project=)",
    "check_domain": "Domain DNS / certificate status (GET /v1/domains/{id}/check)",
    "get_dns_zone": "DNS zone and nameserver status (dns-service)",
    "http_probe": "HTTP GET against the app URL (status, latency)",
    "analyze_project": "Inspect the local project folder (platform, port, env, DB needs)",
    "recommend_plan": "Plan options with hourly cost and runway",
    "investigate": "Read-only incident investigation (collect, analyze, rank hypotheses)",
    "get_incident": "Incident status, evidence and hypotheses",
    "get_fix_brief": "FixBrief for the coding agent",
    "search_docs": "Search Liara docs knowledge base",
    "get_limitations": "What the Liara API cannot do (manual steps)",
}.items():
    register(
        ToolSpec(
            _name,
            Tier.T0,
            _desc,
            app_arg="app" if "app" in _desc.lower() or _name.startswith("get_") else None,
        )
    )

# ----------------------------------------------------------- T1 safe writes
register(
    ToolSpec(
        "recheck_dns",
        Tier.T1,
        "Ask Liara to re-check zone nameservers (PUT zones/{zone}/check)",
        app_arg=None,
    )
)
register(
    ToolSpec(
        "run_health_check",
        Tier.T1,
        "Run the deploy/health verification loop for N minutes",
        verification="HTTP 200 on the health path with no error burst",
    )
)
register(ToolSpec("set_watch", Tier.T1, "Start/stop the watcher for an app", app_arg="app"))

# ------------------------------------------------------- T2 needs approval
register(
    ToolSpec(
        "create_app",
        Tier.T2,
        "Create an app (POST /v1/projects)",
        cost_impact="increases",
        reversibility="reversible",
        verification="App appears in the account with the chosen plan",
    )
)
register(
    ToolSpec(
        "deploy",
        Tier.T2,
        "Deploy the local project with the Liara CLI",
        cost_impact="may_change",
        reversibility="partial",
        downtime="brief",
        verification="Release READY, container running, HTTP 200 on health path, no error burst for N minutes",
    )
)
register(
    ToolSpec(
        "redeploy_release",
        Tier.T2,
        "Roll back / forward by redeploying a previous release source",
        reversibility="partial",
        downtime="brief",
        verification="Release READY and health OK",
    )
)
register(
    ToolSpec(
        "restart_app",
        Tier.T2,
        "Restart the app (POST .../actions/restart)",
        downtime="brief",
        verification="Container restarted and health OK",
    )
)
register(
    ToolSpec(
        "scale_app",
        Tier.T2,
        "Turn the app on (1) or off (0)",
        downtime="yes",
        verification="Applet state matches request",
    )
)
register(
    ToolSpec(
        "set_env",
        Tier.T2,
        "Set environment variables (restarts the app)",
        downtime="brief",
        verification="Health OK and clean logs after restart",
    )
)
register(
    ToolSpec(
        "resize_app",
        Tier.T2,
        "Change plan (POST .../resize)",
        cost_impact="may_change",
        downtime="brief",
        verification="Plan applied; metrics compared to baseline",
    )
)
register(
    ToolSpec(
        "add_domain",
        Tier.T2,
        "Attach a custom domain (POST /v1/domains)",
        verification="Domain status SET, certificates OK, HTTPS 200",
    )
)
register(ToolSpec("enable_ssl", Tier.T2, "Provision SSL certificate for a domain", app_arg=None))
register(
    ToolSpec(
        "toggle_setting",
        Tier.T2,
        "zero-downtime / default-subdomain / fixed-ip / read-only toggles",
        cost_impact="may_change",
    )
)
register(ToolSpec("create_dns_zone", Tier.T2, "Create a DNS zone in Liara DNS", app_arg=None))
register(ToolSpec("create_dns_record", Tier.T2, "Create a DNS record", app_arg=None))
register(
    ToolSpec(
        "submit_fix",
        Tier.T2,
        "Apply a coding-agent patch and redeploy",
        downtime="brief",
        verification="Release READY, health OK, symptom gone",
    )
)

# ------------------------------------------------------------ T3 guarded
register(
    ToolSpec(
        "delete_app",
        Tier.T3,
        "Delete an app (DELETE /v1/projects/{name})",
        cost_impact="decreases",
        reversibility="irreversible",
        downtime="yes",
    )
)
register(
    ToolSpec(
        "delete_domain",
        Tier.T3,
        "Remove a domain",
        reversibility="partial",
        downtime="yes",
        app_arg=None,
    )
)
register(ToolSpec("disable_ssl", Tier.T3, "Disable SSL on a domain", downtime="yes", app_arg=None))
register(
    ToolSpec(
        "downgrade_app",
        Tier.T3,
        "Resize to a smaller plan (risk of OOM)",
        cost_impact="decreases",
        downtime="brief",
    )
)

# Composite wizard action: create app (if needed) + env vars + deploy, one approval.
register(
    ToolSpec(
        "deploy_project",
        Tier.T2,
        "Deploy wizard: create app if needed, set env vars, deploy, verify",
        cost_impact="increases",
        reversibility="partial",
        downtime="brief",
        verification="Release READY, container running, HTTP 200 on health path, no error burst",
    )
)
