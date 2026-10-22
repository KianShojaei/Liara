"""EvidenceBundle: the compact, redacted JSON that hypotheses, the UI and the LLM all consume."""

from __future__ import annotations

from typing import Any

from app.liara.redaction import mask_obj
from app.sre.analyzers import Finding
from app.sre.collectors import RawBundle

MAX_SERIES_POINTS = 60
MAX_LOG_LINES = 12


def downsample(
    points: list[tuple[float, float]], limit: int = MAX_SERIES_POINTS
) -> list[list[float]]:
    if len(points) <= limit:
        return [[round(t), round(v, 3)] for t, v in points]
    step = len(points) / limit
    return [
        [round(points[int(i * step)][0]), round(points[int(i * step)][1], 3)] for i in range(limit)
    ]


def build_evidence(bundle: RawBundle, findings: list[Finding]) -> dict[str, Any]:
    plan = bundle.plan
    project = bundle.project
    error_lines = [line for line in bundle.logs if line.type == "stderr"][-MAX_LOG_LINES:]
    evidence = {
        "app": bundle.app,
        "collected_at": round(bundle.collected_at),
        "window_minutes": bundle.window_minutes,
        "plan": {
            "id": plan.plan_id,
            "ram_gb": plan.ram.amount,
            "cpu_cores": plan.cpu.amount,
            "hourly_price": plan.price,
        }
        if plan
        else None,
        "project": {
            "platform": project.platform,
            "status": project.status,
            "scale": project.scale,
            "is_deployed": project.is_deployed,
        }
        if project
        else None,
        "series": {"cpu": downsample(bundle.cpu), "memory": downsample(bundle.memory)},
        "probe": {k: bundle.probe.get(k) for k in ("success_rate", "p50_ms", "max_ms", "url")}
        if bundle.probe
        else None,
        "applets": [
            {
                "name": a.name,
                "state": a.state,
                "reason": a.reason,
                "release": a.release.get("tag", ""),
            }
            for a in bundle.applets
        ],
        "releases": [
            {
                "id": r.id,
                "tag": r.tag,
                "state": r.state,
                "created_at": r.created_at,
                "message": r.message or r.git_info.get("message", ""),
                "source_available": r.source_available,
            }
            for r in bundle.releases[:5]
        ],
        "events": [{"ts": round(t), "text": text} for t, text in bundle.events[-15:]],
        "log_stats": {
            "total": len(bundle.logs),
            "stderr": sum(1 for line in bundle.logs if line.type == "stderr"),
        },
        "error_samples": [
            {"ts": line.datetime, "message": line.message[:400]} for line in error_lines
        ],
        "findings": [f.to_dict() for f in findings],
        "collection_errors": bundle.errors,
    }
    return mask_obj(evidence)
