"""Investigator: the read-only incident pipeline, streamed as timeline events.

collect -> analyze -> evidence -> hypotheses (rules + optional LLM) -> remediation options
Persisted on the incident row so the UI, CLI and MCP all read the same thing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.sre.analyzers import run_all
from app.sre.collectors import Collector
from app.sre.evidence import build_evidence
from app.sre.hypotheses import rank_hypotheses, refine_with_llm
from app.sre.remediation import plan_remediation

if TYPE_CHECKING:
    from app.agent.context import Runtime


class Investigator:
    def __init__(self, rt: Runtime):
        self._rt = rt
        self.collector = Collector(rt.client, rt.probe)

    async def investigate(
        self,
        app: str,
        *,
        session_id: str,
        trigger: str = "user",
        window_minutes: int = 30,
        health_path: str = "/",
        project_path: str = "",
        incident_id: str | None = None,
    ) -> dict[str, Any]:
        rt = self._rt
        incident = (
            rt.store.get_incident(incident_id) if incident_id else rt.store.open_incident_for(app)
        )
        if incident is None:
            incident = rt.store.create_incident(
                app_name=app, trigger=trigger, session_id=session_id
            )
            rt.emit(
                session_id,
                "incident",
                {"id": incident["id"], "app": app, "status": "open", "trigger": trigger},
            )
        inc_id = incident["id"]

        rt.emit(
            session_id,
            "status",
            {
                "stage": "collecting",
                "text": f"در حال جمع‌آوری لاگ‌ها، رویدادها و متریک‌های {app} ({window_minutes} دقیقه‌ی اخیر)…",
            },
        )
        bundle = await self.collector.collect(
            app, window_minutes=window_minutes, health_path=health_path
        )
        for err in bundle.errors:
            rt.emit(session_id, "notice", {"title": "بخشی از داده‌ها در دسترس نبود", "detail": err})

        rt.emit(session_id, "status", {"stage": "analyzing", "text": "در حال تحلیل الگوها…"})
        findings = run_all(bundle)
        evidence = build_evidence(bundle, findings)
        rt.emit(session_id, "evidence", {"incident_id": inc_id, **evidence})

        hypotheses = rank_hypotheses(findings)
        hypotheses, summary = await refine_with_llm(rt.llm, evidence, hypotheses)
        rt.emit(
            session_id,
            "hypotheses",
            {
                "incident_id": inc_id,
                "items": [h.to_dict() for h in hypotheses],
                "summary": summary or _rule_summary(hypotheses),
            },
        )

        catalog = []
        try:
            me = await rt.client.me()
            catalog = [
                {
                    "plan_id": p.plan_id,
                    "ram_gb": p.ram.amount,
                    "cpu_cores": p.cpu.amount,
                    "hourly_price": p.price,
                    "available": p.available and p.region == "iran",
                }
                for p in me.project_plans()
            ]
        except Exception:  # noqa: BLE001
            pass
        session = rt.store.get_session(session_id) or {}
        remediation = plan_remediation(
            app,
            hypotheses,
            evidence,
            plan_catalog=catalog,
            current_plan_id=bundle.project.plan_id if bundle.project else "",
            current_hourly=bundle.project.hourly_price if bundle.project else 0.0,
            project_path=project_path or session.get("project_path", ""),
        )
        rt.emit(session_id, "remediation", {"incident_id": inc_id, **remediation.to_dict()})

        rt.store.update_incident(
            inc_id,
            evidence=evidence,
            hypotheses=[h.to_dict() for h in hypotheses],
            remediation=remediation.to_dict(),
            summary=summary or _rule_summary(hypotheses),
            status="investigated",
        )
        rt.store.audit(
            actor="investigator",
            action="investigate",
            outcome="investigated",
            session_id=session_id,
            detail={
                "incident_id": inc_id,
                "findings": [f.kind for f in findings],
                "top": hypotheses[0].id if hypotheses else None,
            },
        )
        return rt.store.get_incident(inc_id) or {}


def _rule_summary(hypotheses: list[Any]) -> str:
    if not hypotheses:
        return "نشانه‌ی غیرعادی پیدا نشد؛ سرویس سالم به نظر می‌رسد."
    top = hypotheses[0]
    return f"محتمل‌ترین علت: {top.cause} (اطمینان {top.confidence:.0%}). {top.explanation}"
