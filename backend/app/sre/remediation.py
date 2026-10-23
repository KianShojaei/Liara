"""RemediationPlanner: concrete options with risk, cost, reversibility -> policy tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.sre.hypotheses import Hypothesis


@dataclass
class RemediationOption:
    id: str
    title: str
    tool: str
    args: dict[str, Any]
    risk: str  # low | medium | high
    cost_delta_hourly: float
    reversibility: str
    downtime: str
    rationale: str
    recommended: bool = False
    requires: str = ""  # e.g. "coding agent" or "previous release source"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RemediationPlan:
    options: list[RemediationOption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"options": [o.to_dict() for o in self.options]}


def plan_remediation(
    app: str,
    hypotheses: list[Hypothesis],
    evidence: dict[str, Any],
    *,
    plan_catalog: list[dict[str, Any]],
    current_plan_id: str,
    current_hourly: float,
    project_path: str = "",
) -> RemediationPlan:
    wanted: list[str] = []
    for h in hypotheses[:3]:
        for remedy in h.suggested_remedies:
            if remedy not in wanted:
                wanted.append(remedy)
    options: list[RemediationOption] = []
    releases = evidence.get("releases") or []
    previous = next(
        (r for r in releases[1:] if r.get("state") == "READY" and r.get("source_available")), None
    )
    missing_env = next(
        (f for f in evidence.get("findings", []) if f["kind"] == "missing_env"), None
    )

    for remedy in wanted:
        if remedy == "rollback" and previous:
            options.append(
                RemediationOption(
                    "rollback",
                    f"بازگشت به نسخه‌ی {previous.get('tag') or previous['id'][:8]}",
                    "redeploy_release",
                    {"app": app, "release_id": previous["id"]},
                    "low",
                    0.0,
                    "reversible",
                    "brief",
                    "نسخه‌ی قبلی سالم بود؛ سریع‌ترین راه برای برگرداندن سایت.",
                    requires="previous release source",
                )
            )
        elif remedy == "restart":
            options.append(
                RemediationOption(
                    "restart",
                    "ری‌استارت برنامه",
                    "restart_app",
                    {"app": app},
                    "low",
                    0.0,
                    "reversible",
                    "brief",
                    "علائم را موقتاً رفع می‌کند (مثلاً حافظه آزاد می‌شود) ولی علت را برطرف نمی‌کند.",
                )
            )
        elif remedy == "resize":
            bigger = _next_plan(plan_catalog, current_plan_id)
            if bigger:
                options.append(
                    RemediationOption(
                        "resize",
                        f"ارتقا به پلن {bigger['plan_id']} ({bigger['ram_gb']}GB RAM / {bigger['cpu_cores']} CPU)",
                        "resize_app",
                        {"app": app, "plan_id": bigger["plan_id"]},
                        "medium",
                        bigger["hourly_price"] - current_hourly,
                        "reversible",
                        "brief",
                        f"هزینه از {current_hourly:.0f} به {bigger['hourly_price']:.0f} تومان در ساعت می‌رسد. اگر علت نشت حافظه باشد فقط زمان می‌خرد.",
                    )
                )
        elif remedy == "config_fix" and missing_env and missing_env["evidence"].get("variable"):
            var = missing_env["evidence"]["variable"]
            options.append(
                RemediationOption(
                    "config_fix",
                    f"تنظیم متغیر محیطی {var}",
                    "set_env",
                    {"app": app, "variables": {var: ""}},
                    "low",
                    0.0,
                    "reversible",
                    "brief",
                    "مقدار را در کارت تأیید وارد کنید؛ برنامه بعد از ذخیره ری‌استارت می‌شود.",
                )
            )
        elif remedy == "code_fix":
            options.append(
                RemediationOption(
                    "code_fix",
                    "ارسال FixBrief به ایجنت کدنویسی و دیپلوی اصلاح",
                    "submit_fix",
                    {"app": app, "path": project_path},
                    "medium",
                    0.0,
                    "partial",
                    "brief",
                    "علت ریشه‌ای را در کد برطرف می‌کند؛ پچ قبل از دیپلوی به شما نشان داده می‌شود.",
                    requires="coding agent",
                )
            )
        elif remedy == "turn_on" and (evidence.get("project") or {}).get("scale") == 0:
            options.append(
                RemediationOption(
                    "turn_on",
                    "روشن کردن برنامه",
                    "scale_app",
                    {"app": app, "scale": 1},
                    "low",
                    current_hourly,
                    "reversible",
                    "none",
                    "برنامه خاموش است (scale=0)؛ با روشن شدن، هزینه‌ی ساعتی دوباره شروع می‌شود.",
                )
            )
        elif remedy == "health_path":
            options.append(
                RemediationOption(
                    "health_path",
                    "تنظیم مسیر بررسی سلامت روی /health و پایش دوباره",
                    "set_watch",
                    {"app": app, "enabled": True, "health_path": "/health"},
                    "low",
                    0.0,
                    "reversible",
                    "none",
                    "هیچ تغییری روی برنامه نمی‌دهد؛ فقط پایش را روی یک مسیر عمومی می‌برد تا هشدار اشتباه ندهد.",
                )
            )
        elif remedy == "check_domain":
            options.append(
                RemediationOption(
                    "check_domain",
                    "بررسی وضعیت دامنه و گواهی",
                    "get_domains",
                    {"app": app},
                    "low",
                    0.0,
                    "reversible",
                    "none",
                    "فقط خواندنی.",
                )
            )
    if options:
        options[0].recommended = True
    return RemediationPlan(options)


def _next_plan(catalog: list[dict[str, Any]], current: str) -> dict[str, Any] | None:
    ordered = sorted(
        (p for p in catalog if p.get("available", True) and p.get("plan_id") != "free"),
        key=lambda p: (p.get("hourly_price", 0), p.get("ram_gb", 0)),
    )
    ids = [p["plan_id"] for p in ordered]
    if current in ids and ids.index(current) + 1 < len(ids):
        return ordered[ids.index(current) + 1]
    return ordered[0] if ordered and current not in ids else None
