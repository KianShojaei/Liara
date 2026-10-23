"""Typed views of Liara API responses.

Every model marks its provenance:
  VERIFIED  - field present in the official OpenAPI spec (developers.liara.ir/spec/*.yaml)
              or in the official CLI source (github.com/liara-cloud/cli).
  ASSUMED   - shape inferred; confirm with tools/probe.py output and fix if different.
Unknown extra fields are kept (extra="allow") so nothing from a probe is lost.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        """The real API returns null for many optional fields (e.g. release.finishedAt);
        dropping them lets the field defaults apply instead of failing validation."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


# ---- /v1/me (VERIFIED: spec/me.yaml + cli src/commands/app/create.ts) ----


class PlanResource(_Loose):
    amount: float = 0


class ProjectPlan(_Loose):
    """plans.projects[planID]  (VERIFIED via CLI: available, region, RAM.amount, CPU.amount,
    volume, price (hourly, Toman), storageClass)."""

    plan_id: str = ""
    available: bool = True
    region: str = "iran"
    ram: PlanResource = Field(default_factory=PlanResource, alias="RAM")
    cpu: PlanResource = Field(default_factory=PlanResource, alias="CPU")
    volume: float = 0
    price: float = 0  # hourly price in Toman
    storage_class: str | None = Field(default=None, alias="storageClass")

    @property
    def monthly_price(self) -> float:
        return self.price * 720  # CLI convention: 720 hours per month


class MeUser(_Loose):
    id: str = Field(default="", alias="_id")
    fullname: str = ""
    email: str = ""
    is_team: bool = Field(default=False, alias="isTeam")
    account_type: str = Field(default="", alias="accountType")


class Me(_Loose):
    user: MeUser = Field(default_factory=MeUser)
    team: dict[str, Any] | None = None
    plans: dict[str, Any] = Field(default_factory=dict)
    feature_flags: list[dict[str, Any]] = Field(default_factory=list, alias="featureFlags")

    @property
    def team_balance(self) -> float | None:
        """Team accounts keep the wallet on the team object (VERIFIED spec/me.yaml Team.balance)."""
        if isinstance(self.team, dict) and self.team.get("balance") is not None:
            try:
                return float(self.team["balance"])
            except (TypeError, ValueError):
                return None
        return None

    def bundle_plan_for(self, plan_id: str) -> str | None:
        """Cheapest available feature-bundle plan for a compute plan
        (plans.projectBundlePlans[planID] = {bundleKey: {available, displayPrice}}; VERIFIED CLI)."""
        bundles = (self.plans.get("projectBundlePlans") or {}).get(plan_id) or {}
        candidates = [
            (float(v.get("displayPrice") or 0), k)
            for k, v in bundles.items()
            if isinstance(v, dict) and v.get("available", True)
        ]
        return min(candidates)[1] if candidates else None

    def project_plans(self) -> list[ProjectPlan]:
        raw = self.plans.get("projects", {}) or {}
        plans: list[ProjectPlan] = []
        for plan_id, body in raw.items():
            if not isinstance(body, dict):
                continue
            plan = ProjectPlan.model_validate(body)
            plan.plan_id = plan_id
            plans.append(plan)
        return plans


# ---- /v1/billing (VERIFIED: spec/billing.yaml) ----


class Billing(_Loose):
    balance: float = 0.0
    account_type: str = Field(default="", alias="accountType")
    min_credit_amount: float = Field(default=0, alias="minCreditAmount")


# ---- /v1/projects (VERIFIED: spec/paas.yaml Projects / ProjectAllDetails) ----


class EnvVar(_Loose):
    key: str
    value: str = ""
    encrypted: bool = False


class ProjectSummary(_Loose):
    id: str = Field(default="", alias="_id")
    name: str = Field(default="", alias="project_id")
    platform: str = Field(default="", alias="type")
    status: str = ""
    scale: int = 0
    plan_id: str = Field(default="", alias="planID")
    created_at: str = ""
    is_deployed: bool = Field(default=False, alias="isDeployed")


class ProjectDetails(ProjectSummary):
    default_subdomain: bool = Field(default=True, alias="defaultSubdomain")
    zero_downtime: bool = Field(default=False, alias="zeroDowntime")
    read_only_root_fs: bool = Field(default=False, alias="readOnlyRootFilesystem")
    envs: list[EnvVar] = Field(default_factory=list)
    hourly_price: float = Field(default=0.0, alias="hourlyPrice")
    fixed_ip_status: str = Field(default="", alias="fixedIPStatus")

    @property
    def default_url(self) -> str:
        # ASSUMED default-subdomain pattern (documented in user docs as <app>.liara.run)
        return f"https://{self.name}.liara.run"


# ---- logs / events / applets / releases (VERIFIED shapes) ----


class LogLine(_Loose):
    type: str = "stdout"
    datetime: str = ""
    message: str = ""


class Applet(_Loose):
    id: str = ""
    name: str = ""
    timestamp: str = ""
    state: str = ""
    reason: str = ""
    release: dict[str, Any] = Field(default_factory=dict)


class Release(_Loose):
    id: str = Field(default="", alias="_id")
    type: str = ""
    state: str = (
        ""  # VERIFIED values (CLI): BUILDING PUSHING PUSHED DEPLOYING UNHEALTHY FAILED READY
    )
    port: int | None = None
    tag: str = ""
    created_at: str = Field(default="", alias="createdAt")
    finished_at: str = Field(default="", alias="finishedAt")
    source_available: bool = Field(default=False, alias="sourceAvailable")
    git_info: dict[str, Any] = Field(default_factory=dict, alias="gitInfo")
    message: str = ""  # ASSUMED (release message set with `liara deploy -m`)
    source_id: str = Field(default="", alias="sourceID")  # ASSUMED: needed for rollback
    project_type: str = Field(default="", alias="projectType")


class ReleaseList(_Loose):
    total: int = 0
    current_release: str = Field(default="", alias="currentRelease")
    releases: list[Release] = Field(default_factory=list)


class EventRow(_Loose):
    """Events come as prometheus-style rows: metaData + values[[ts, text], ...] (VERIFIED)."""

    meta_data: dict[str, Any] = Field(default_factory=dict, alias="metaData")
    values: list[list[Any]] = Field(default_factory=list)


# ---- metrics (VERIFIED shape, ASSUMED units) ----


class MetricSeries(_Loose):
    """result[i] = {applet, values: [[ts, "value"], ...]} (VERIFIED). Units ASSUMED:
    cpu in cores (fraction), memory in bytes. The probe prints raw samples to confirm."""

    applet: str = ""
    values: list[list[Any]] = Field(default_factory=list)

    def points(self) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for row in self.values:
            if len(row) >= 2:
                try:
                    out.append((float(row[0]), float(row[1])))
                except (TypeError, ValueError):
                    continue
        return out


class MetricReport(_Loose):
    end: float | None = None
    result: list[MetricSeries] = Field(default_factory=list)


class MetricsSummary(_Loose):
    cpu_usage: list[dict[str, Any]] = Field(default_factory=list, alias="cpuUsage")
    memory_usage: list[dict[str, Any]] = Field(default_factory=list, alias="memoryUsage")
    disks_usage: list[dict[str, Any]] = Field(default_factory=list, alias="disksUsage")

    @staticmethod
    def _last(rows: list[dict[str, Any]]) -> float | None:
        for row in rows:
            value = row.get("value") or []
            if len(value) >= 2:
                try:
                    return float(value[1])
                except (TypeError, ValueError):
                    return None
        return None

    @property
    def cpu(self) -> float | None:
        return self._last(self.cpu_usage)

    @property
    def memory(self) -> float | None:
        return self._last(self.memory_usage)


# ---- domains (VERIFIED: spec/paas.yaml Domains / CheckDomain) ----


class Domain(_Loose):
    id: str = Field(default="", alias="_id")
    name: str = ""
    type: str = ""
    status: str = ""
    certificates_status: str = Field(default="", alias="certificatesStatus")
    cname_record: str = Field(default="", alias="CNameRecord")
    verification_code: str = Field(default="", alias="verificationCode")
    project: dict[str, Any] = Field(default_factory=dict)


# ---- dns-service (VERIFIED: spec/dns.yaml) ----


class DnsZone(_Loose):
    id: str = ""
    name: str = ""
    status: str = ""  # CREATING PENDING ACTIVE DELETING
    current_name_servers: list[str] = Field(default_factory=list, alias="currentNameServers")
    name_servers: list[str] = Field(default_factory=list, alias="nameServers")


class DnsRecord(_Loose):
    id: str = ""
    name: str = ""
    type: str = ""
    ttl: int | None = None
    contents: list[dict[str, Any]] = Field(default_factory=list)


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
