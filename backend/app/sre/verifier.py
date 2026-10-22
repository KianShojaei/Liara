"""IncidentVerifier: after a remediation, re-probe for a while and compare before/after."""

from __future__ import annotations

import asyncio
from typing import Any

from app.sre.analyzers import run_all
from app.sre.collectors import Collector


class IncidentVerifier:
    def __init__(self, collector: Collector):
        self._collector = collector

    async def verify(
        self,
        app: str,
        before: dict[str, Any],
        *,
        rounds: int = 3,
        interval: float = 5.0,
        health_path: str = "/",
        on_round: Any = None,
    ) -> dict[str, Any]:
        snapshots = []
        for i in range(rounds):
            bundle = await self._collector.collect(
                app, window_minutes=5, health_path=health_path, probe_count=2
            )
            findings = run_all(bundle)
            snapshot = {
                "round": i + 1,
                "probe_success": bundle.probe.get("success_rate"),
                "p50_ms": bundle.probe.get("p50_ms"),
                "memory": bundle.memory[-1][1] if bundle.memory else None,
                "cpu": bundle.cpu[-1][1] if bundle.cpu else None,
                "critical_findings": [f.kind for f in findings if f.severity == "critical"],
            }
            snapshots.append(snapshot)
            if on_round:
                result = on_round(snapshot)
                if asyncio.iscoroutine(result):
                    await result
            if i < rounds - 1:
                await asyncio.sleep(interval)
        last = snapshots[-1]
        before_probe = (before.get("probe") or {}).get("success_rate")
        before_mem = (before.get("series") or {}).get("memory") or []
        comparison = {
            "probe_success_before": before_probe,
            "probe_success_after": last["probe_success"],
            "memory_before": before_mem[-1][1] if before_mem else None,
            "memory_after": last["memory"],
            "critical_before": [
                f["kind"] for f in before.get("findings", []) if f["severity"] == "critical"
            ],
            "critical_after": last["critical_findings"],
        }
        ok = (last["probe_success"] is None or last["probe_success"] >= 0.67) and not last[
            "critical_findings"
        ]
        return {
            "ok": ok,
            "rounds": snapshots,
            "comparison": comparison,
            "summary": "علائم برطرف شد."
            if ok
            else "علائم هنوز ادامه دارد: " + ", ".join(last["critical_findings"]),
        }
