import random
import time

from app.liara.models import Applet, LogLine, ProjectPlan, Release
from app.sre.analyzers import (
    analyze_errors,
    analyze_memory_trend,
    analyze_release_correlation,
    analyze_restarts,
    analyze_saturation,
    run_all,
)
from app.sre.collectors import RawBundle
from app.sre.hypotheses import rank_hypotheses

PLAN = ProjectPlan.model_validate({"RAM": {"amount": 0.5}, "CPU": {"amount": 1}, "price": 208})


def bundle(**kw) -> RawBundle:
    return RawBundle(app="a", collected_at=time.time(), window_minutes=30, plan=PLAN, **kw)


def test_memory_leak_detected_on_recent_window():
    now = time.time()
    random.seed(1)
    flat = [(now - 1800 + i * 15, 170e6 + random.uniform(-4e6, 4e6)) for i in range(100)]
    rising = [(now - 300 + i * 15, 170e6 + i * 9e6) for i in range(20)]
    findings = analyze_memory_trend(bundle(memory=flat + rising))
    assert findings and findings[0].kind == "memory_leak"
    assert findings[0].evidence["growth_mb_per_min"] > 20


def test_flat_memory_is_not_a_leak():
    now = time.time()
    random.seed(2)
    flat = [(now - 1800 + i * 15, 170e6 + random.uniform(-4e6, 4e6)) for i in range(120)]
    assert analyze_memory_trend(bundle(memory=flat)) == []


def test_saturation_against_plan_limits():
    now = time.time()
    findings = analyze_saturation(
        bundle(memory=[(now, 0.95 * 0.5 * 1024**3)], cpu=[(now - i, 0.95) for i in range(8)])
    )
    kinds = {f.kind for f in findings}
    assert {"memory_saturation", "cpu_saturation"} <= kinds


def test_error_burst_clusters_and_stack():
    logs = [LogLine(type="stdout", message="GET /x 200 12ms") for _ in range(10)]
    logs += [
        LogLine(
            type="stderr",
            message="TypeError: Cannot read properties of undefined (reading 'price')\n    at computeTotal (/app/src/handlers/checkout.js:42:21)",
        )
        for _ in range(6)
    ]
    findings = analyze_errors(bundle(logs=logs))
    burst = next(f for f in findings if f.kind == "error_burst")
    assert burst.evidence["clusters"][0]["count"] == 6
    assert "checkout.js" in burst.evidence["stack_frames"][0]


def test_restart_and_release_correlation_and_ranking():
    now = time.time()
    applets = [Applet(name="a-0", state="Waiting", reason="CrashLoopBackOff")]
    releases = [
        Release.model_validate(
            {
                "_id": "r2",
                "state": "UNHEALTHY",
                "tag": "v2",
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 120)),
            }
        ),
        Release.model_validate(
            {"_id": "r1", "state": "READY", "tag": "v1", "sourceAvailable": True}
        ),
    ]
    b = bundle(
        applets=applets,
        releases=releases,
        logs=[LogLine(type="stderr", message="Error: Missing required env DATABASE_URL")] * 5,
    )
    findings = run_all(b)
    kinds = {f.kind for f in findings}
    assert {"crash_loop", "recent_release", "missing_env"} <= kinds
    hypotheses = rank_hypotheses(findings)
    assert hypotheses[0].id in ("bad_release", "missing_env", "crash_loop")
    assert all(0 <= h.confidence <= 1 for h in hypotheses)
    assert analyze_restarts(b) and analyze_release_correlation(b)
