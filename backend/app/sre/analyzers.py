"""Pure analyzers over the RawBundle. No I/O, fully unit-testable with synthetic series.

Each analyzer returns a Finding: a machine-readable signal with a confidence and the exact
evidence (numbers, log lines) that produced it.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC
from typing import Any

from app.sre.collectors import RawBundle

GIB = 1024**3


@dataclass
class Finding:
    kind: str
    severity: str  # info | warning | critical
    confidence: float
    title: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------ helpers


def linear_slope(points: list[tuple[float, float]]) -> float:
    """Least-squares slope (units per second)."""
    n = len(points)
    if n < 3:
        return 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / denom


def monotonic_ratio(points: list[tuple[float, float]]) -> float:
    """Share of consecutive steps that go up (1.0 = strictly growing)."""
    if len(points) < 3:
        return 0.0
    ups = sum(1 for a, b in zip(points, points[1:], strict=False) if b[1] >= a[1])
    return ups / (len(points) - 1)


def zscore_last(points: list[tuple[float, float]], *, baseline_fraction: float = 0.6) -> float:
    if len(points) < 6:
        return 0.0
    values = [p[1] for p in points]
    cut = max(3, int(len(values) * baseline_fraction))
    base = values[:cut]
    mean = sum(base) / len(base)
    var = sum((v - mean) ** 2 for v in base) / len(base)
    std = var**0.5 or 1e-9
    return (values[-1] - mean) / std


_NORMALISE = [
    (re.compile(r"0x[0-9a-f]+"), "0xHEX"),
    (re.compile(r"\b\d+(\.\d+)?(ms|s|kb|mb)?\b"), "N"),
    (re.compile(r"[0-9a-f]{8,}"), "ID"),
    (re.compile(r"\s+"), " "),
]


def normalise_log(message: str) -> str:
    first = message.strip().splitlines()[0] if message.strip() else ""
    for pattern, repl in _NORMALISE:
        first = pattern.sub(repl, first)
    return first[:160]


def extract_stack_frames(message: str) -> list[str]:
    return [
        line.strip() for line in message.splitlines() if line.strip().startswith(("at ", 'File "'))
    ][:5]


# ---------------------------------------------------------------- analyzers


def analyze_saturation(bundle: RawBundle) -> list[Finding]:
    findings: list[Finding] = []
    if bundle.plan is None:
        return findings
    mem_limit = bundle.plan.ram.amount * GIB
    cpu_limit = bundle.plan.cpu.amount
    if bundle.memory and mem_limit:
        last = bundle.memory[-1][1]
        ratio = last / mem_limit
        if ratio >= 0.9:
            findings.append(
                Finding(
                    "memory_saturation",
                    "critical",
                    min(0.95, ratio),
                    f"مصرف حافظه {ratio:.0%} ظرفیت پلن است",
                    {"memory_bytes": last, "limit_bytes": mem_limit, "ratio": round(ratio, 3)},
                )
            )
        elif ratio >= 0.75:
            findings.append(
                Finding(
                    "memory_pressure",
                    "warning",
                    0.6,
                    f"مصرف حافظه {ratio:.0%} ظرفیت پلن است",
                    {"memory_bytes": last, "limit_bytes": mem_limit, "ratio": round(ratio, 3)},
                )
            )
    if bundle.cpu and cpu_limit:
        recent = [v for _, v in bundle.cpu[-8:]]
        avg = sum(recent) / len(recent)
        ratio = avg / cpu_limit
        if ratio >= 0.85:
            findings.append(
                Finding(
                    "cpu_saturation",
                    "critical",
                    min(0.95, ratio),
                    f"مصرف CPU {ratio:.0%} ظرفیت پلن است (میانگین اخیر)",
                    {
                        "cpu_cores_avg": round(avg, 3),
                        "limit_cores": cpu_limit,
                        "ratio": round(ratio, 3),
                    },
                )
            )
    return findings


def analyze_memory_trend(bundle: RawBundle) -> list[Finding]:
    """Leak = sustained growth. Checked on the recent window (last ~5 min) so a fault that
    started a few minutes ago is visible even when the earlier part of the series is flat."""
    points = bundle.memory
    if len(points) < 6:
        return []
    recent = points[-20:] if len(points) >= 20 else points
    smoothed = _smooth(recent)
    slope = linear_slope(smoothed)  # bytes per second
    ratio = monotonic_ratio(smoothed)
    growth_per_min = slope * 60
    limit = bundle.plan.ram.amount * GIB if bundle.plan else 0
    if growth_per_min > 2 * 1024 * 1024 and ratio > 0.75:
        minutes_left = (
            (limit - points[-1][1]) / growth_per_min if limit and growth_per_min > 0 else None
        )
        severity = "critical" if minutes_left is not None and minutes_left < 30 else "warning"
        return [
            Finding(
                "memory_leak",
                severity,
                min(0.9, 0.5 + ratio * 0.4),
                f"حافظه با نرخ ثابت {growth_per_min / 1024 / 1024:.1f}MB در دقیقه رشد می‌کند",
                {
                    "growth_mb_per_min": round(growth_per_min / 1024 / 1024, 2),
                    "monotonic_ratio": round(ratio, 2),
                    "minutes_to_limit": round(minutes_left, 1)
                    if minutes_left is not None
                    else None,
                    "samples": len(recent),
                    "window_seconds": round(recent[-1][0] - recent[0][0]) if len(recent) > 1 else 0,
                },
            )
        ]
    return []


def _smooth(points: list[tuple[float, float]], k: int = 3) -> list[tuple[float, float]]:
    if len(points) < k:
        return points
    out = []
    for i in range(len(points)):
        window = points[max(0, i - k + 1) : i + 1]
        out.append((points[i][0], sum(v for _, v in window) / len(window)))
    return out


def analyze_restarts(bundle: RawBundle) -> list[Finding]:
    findings: list[Finding] = []
    for applet in bundle.applets:
        reason = (applet.reason or "").lower()
        state = (applet.state or "").lower()
        if "oom" in reason:
            findings.append(
                Finding(
                    "oom_kill",
                    "critical",
                    0.95,
                    f"کانتینر {applet.name} به دلیل کمبود حافظه کشته شد (OOMKilled)",
                    {"applet": applet.name, "state": applet.state, "reason": applet.reason},
                )
            )
        elif "crashloop" in reason or (state not in ("running", "ready", "") and reason):
            findings.append(
                Finding(
                    "crash_loop",
                    "critical",
                    0.9,
                    f"کانتینر {applet.name} مدام ری‌استارت می‌شود ({applet.reason})",
                    {"applet": applet.name, "state": applet.state, "reason": applet.reason},
                )
            )
    restarts = [
        t for t, text in bundle.events if "restart" in text.lower() or "crashloop" in text.lower()
    ]
    if len(restarts) >= 3:
        findings.append(
            Finding(
                "restart_loop",
                "critical",
                0.85,
                f"{len(restarts)} ری‌استارت در {bundle.window_minutes} دقیقه‌ی اخیر",
                {"restart_count": len(restarts)},
            )
        )
    return findings


def analyze_errors(bundle: RawBundle) -> list[Finding]:
    logs = bundle.logs
    if not logs:
        return []
    error_lines = [
        line
        for line in logs
        if line.type == "stderr"
        or re.search(r"\b(5\d\d|error|exception|fatal|traceback)\b", line.message, re.I)
    ]
    status_500 = [line for line in logs if re.search(r"\s5\d\d\s", line.message)]
    clusters = Counter(normalise_log(line.message) for line in error_lines)
    findings: list[Finding] = []
    ratio = len(error_lines) / len(logs)
    if error_lines and (ratio >= 0.15 or len(status_500) >= 5):
        top = clusters.most_common(5)
        sample = next(
            (line for line in error_lines if extract_stack_frames(line.message)), error_lines[0]
        )
        findings.append(
            Finding(
                "error_burst",
                "critical" if ratio >= 0.3 else "warning",
                min(0.95, 0.5 + ratio),
                f"{len(error_lines)} خط خطا از {len(logs)} خط لاگ ({ratio:.0%})",
                {
                    "error_ratio": round(ratio, 3),
                    "http_5xx": len(status_500),
                    "clusters": [{"pattern": p, "count": c} for p, c in top],
                    "stack_frames": extract_stack_frames(sample.message),
                    "sample": sample.message[:400],
                },
            )
        )
    oom = [
        line
        for line in logs
        if "heap out of memory" in line.message.lower() or "memoryerror" in line.message.lower()
    ]
    if oom:
        findings.append(
            Finding(
                "oom_in_logs",
                "critical",
                0.95,
                "لاگ‌ها خطای کمبود حافظه را نشان می‌دهند",
                {"sample": oom[-1].message[:300]},
            )
        )
    missing_env = [
        line
        for line in logs
        if re.search(r"missing required env|undefined env|is not set", line.message, re.I)
    ]
    if missing_env:
        match = re.search(r"env\s+([A-Z][A-Z0-9_]+)", missing_env[-1].message)
        findings.append(
            Finding(
                "missing_env",
                "critical",
                0.9,
                "برنامه یک متغیر محیطی لازم را پیدا نمی‌کند",
                {
                    "variable": match.group(1) if match else None,
                    "sample": missing_env[-1].message[:300],
                },
            )
        )
    return findings


def analyze_latency(bundle: RawBundle) -> list[Finding]:
    durations = [
        float(m.group(1))
        for line in bundle.logs
        for m in [re.search(r"\s(\d+(?:\.\d+)?)ms\b", line.message)]
        if m
    ]
    findings: list[Finding] = []
    if len(durations) >= 10:
        head, tail = durations[: len(durations) // 2], durations[len(durations) // 2 :]
        p50_head, p50_tail = sorted(head)[len(head) // 2], sorted(tail)[len(tail) // 2]
        if p50_tail > max(200, 2.5 * p50_head):
            findings.append(
                Finding(
                    "latency_regression",
                    "warning",
                    0.7,
                    f"زمان پاسخ از {p50_head:.0f}ms به {p50_tail:.0f}ms رسیده",
                    {
                        "p50_before_ms": p50_head,
                        "p50_after_ms": p50_tail,
                        "samples": len(durations),
                    },
                )
            )
    probe = bundle.probe
    if probe:
        rate = probe.get("success_rate", 1.0)
        if rate < 0.67:
            findings.append(
                Finding(
                    "http_failing",
                    "critical",
                    0.95,
                    f"فقط {rate:.0%} از درخواست‌های مستقیم موفق بود",
                    {
                        "success_rate": rate,
                        "samples": [
                            {k: s.get(k) for k in ("status", "latency_ms", "error")}
                            for s in probe.get("samples", [])
                        ],
                    },
                )
            )
        elif (probe.get("p50_ms") or 0) > 1500:
            findings.append(
                Finding(
                    "http_slow",
                    "warning",
                    0.7,
                    f"زمان پاسخ مستقیم {probe.get('p50_ms')}ms است",
                    {"p50_ms": probe.get("p50_ms"), "max_ms": probe.get("max_ms")},
                )
            )
    return findings


def analyze_release_correlation(bundle: RawBundle) -> list[Finding]:
    if not bundle.releases:
        return []
    latest = bundle.releases[0]
    created = _parse_ts(latest.created_at) or _parse_ts(latest.finished_at)
    if created is None:
        return []
    age_min = (bundle.collected_at - created) / 60
    unhealthy = latest.state in ("UNHEALTHY", "FAILED")
    if age_min <= bundle.window_minutes * 2 or unhealthy:
        previous = next((r for r in bundle.releases[1:] if r.state == "READY"), None)
        return [
            Finding(
                "recent_release",
                "critical" if unhealthy else "warning",
                0.8 if unhealthy else 0.6,
                f"آخرین نسخه ({latest.tag or latest.id[:8]}) {age_min:.0f} دقیقه پیش منتشر شده و وضعیتش {latest.state} است",
                {
                    "release_id": latest.id,
                    "tag": latest.tag,
                    "state": latest.state,
                    "age_minutes": round(age_min, 1),
                    "message": latest.message or latest.git_info.get("message", ""),
                    "previous_ready_release": {
                        "id": previous.id,
                        "tag": previous.tag,
                        "source_available": previous.source_available,
                    }
                    if previous
                    else None,
                },
            )
        ]
    return []


def _parse_ts(value: str) -> float | None:
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).timestamp()
    except ValueError:
        return None


ANALYZERS = (
    analyze_saturation,
    analyze_memory_trend,
    analyze_restarts,
    analyze_errors,
    analyze_latency,
    analyze_release_correlation,
)


def run_all(bundle: RawBundle) -> list[Finding]:
    findings: list[Finding] = []
    for analyzer in ANALYZERS:
        findings.extend(analyzer(bundle))
    findings.sort(
        key=lambda f: ({"critical": 0, "warning": 1, "info": 2}[f.severity], -f.confidence)
    )
    return findings
