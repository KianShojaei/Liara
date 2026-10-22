"""PlanAdvisor: pick plans from the live catalog (GET /v1/me) and explain cost + runway.

Prices are never hard-coded (web prices are stale); the catalog comes from the API.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.deploy.analyzer import ProjectAnalysis
from app.liara.models import ProjectPlan

HOURS_PER_MONTH = 720
LOW_BALANCE_HOURS = 48  # warn when runway drops below two days


@dataclass
class PlanOption:
    plan_id: str
    ram_gb: float
    cpu_cores: float
    disk_gb: float
    hourly_price: float
    monthly_price: float
    runway_hours: float | None
    runway_label: str
    recommended: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlanAdvice:
    options: list[PlanOption]
    recommended_plan_id: str
    balance: float
    balance_ok: bool
    balance_message: str
    low_balance: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "options": [o.to_dict() for o in self.options],
            "recommended_plan_id": self.recommended_plan_id,
            "balance": self.balance,
            "balance_ok": self.balance_ok,
            "balance_message": self.balance_message,
            "low_balance": self.low_balance,
        }


def runway(balance: float, hourly: float) -> tuple[float | None, str]:
    if hourly <= 0:
        return None, "رایگان"
    hours = balance / hourly
    if hours < 1:
        return hours, "کمتر از یک ساعت"
    if hours < 48:
        return hours, f"حدود {hours:.0f} ساعت"
    return hours, f"حدود {hours / 24:.0f} روز"


class PlanAdvisor:
    def __init__(self, catalog: list[ProjectPlan], balance: float, *, region: str = "iran"):
        self.catalog = [p for p in catalog if p.available and p.region == region]
        self.balance = balance

    def advise(self, analysis: ProjectAnalysis, *, current_hourly: float = 0.0) -> PlanAdvice:
        min_ram = self._min_ram(analysis)
        candidates = sorted(self.catalog, key=lambda p: (p.price, p.ram.amount))
        options: list[PlanOption] = []
        for plan in candidates:
            hours, label = runway(self.balance, plan.price + current_hourly)
            option = PlanOption(
                plan.plan_id,
                plan.ram.amount,
                plan.cpu.amount,
                plan.volume,
                plan.price,
                plan.monthly_price,
                hours,
                label,
            )
            if plan.ram.amount < min_ram:
                option.reasons.append(
                    f"RAM کمتر از حداقل {min_ram}GB برای پلتفرم {analysis.platform}"
                )
            if plan.plan_id == "free":
                option.reasons.append("پلن رایگان: مناسب تست، نه برای سایت واقعی")
            options.append(option)

        fitting = [o for o in options if o.ram_gb >= min_ram and o.plan_id != "free"]
        affordable = [
            o for o in fitting if o.runway_hours is None or o.runway_hours >= LOW_BALANCE_HOURS
        ]
        chosen = (affordable or fitting or options)[0]
        chosen.recommended = True
        chosen.reasons.insert(
            0, f"کمترین هزینه‌ای که نیاز {analysis.platform} ({min_ram}GB RAM) را پوشش می‌دهد"
        )
        if not affordable and fitting:
            chosen.reasons.append("موجودی برای بیش از دو روز کافی نیست؛ شارژ حساب توصیه می‌شود")

        low = chosen.runway_hours is not None and chosen.runway_hours < LOW_BALANCE_HOURS
        ok = chosen.runway_hours is None or chosen.runway_hours >= 1
        message = (
            "موجودی کافی است."
            if ok and not low
            else (
                "موجودی برای کمتر از دو روز کافی است؛ حساب را در کنسول شارژ کنید."
                if ok
                else "موجودی برای اجرای این پلن کافی نیست؛ حساب را در کنسول شارژ کنید."
            )
        )
        return PlanAdvice(options, chosen.plan_id, self.balance, ok, message, low)

    @staticmethod
    def _min_ram(analysis: ProjectAnalysis) -> float:
        heavy = {
            "next": 1.0,
            "django": 0.5,
            "laravel": 1.0,
            "dotnet": 1.0,
            "wordpress": 1.0,
            "node": 0.5,
            "python": 0.5,
            "flask": 0.5,
            "go": 0.25,
            "docker": 0.5,
        }
        base = heavy.get(analysis.platform, 0.25)
        if analysis.size_hint == "medium" and base < 1.0:
            base = max(base, 0.5)
        return base

    def plan(self, plan_id: str) -> ProjectPlan | None:
        return next((p for p in self.catalog if p.plan_id == plan_id), None)
