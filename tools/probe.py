#!/usr/bin/env python3
"""Read-only probe of the Liara API. Run this locally, then paste the REDACTED output back.

    python tools/probe.py                # uses LIARA_API_TOKEN / LIARA_TEAM_ID from .env or env
    python tools/probe.py --app my-app   # also probes logs/metrics/releases of one app
    python tools/probe.py --record       # write redacted fixtures into tools/fixtures/live/

It never prints the token, never writes it to disk, and only calls GET endpoints.
Purpose: confirm base URL, plan catalog shape, metric units/granularity, `since` semantics,
release states and error body format (the "known gaps" in docs/ARCHITECTURE.md).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; we print Persian
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "backend"))

from app.liara.client import FixtureRecorder, LiaraClient  # noqa: E402
from app.liara.errors import LiaraError  # noqa: E402
from app.liara.redaction import mask_obj  # noqa: E402


def _load_env() -> None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def section(title: str, body: object) -> None:
    print(f"\n### {title}")
    print(json.dumps(mask_obj(body), ensure_ascii=False, indent=2, default=str)[:12000])


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default="")
    parser.add_argument("--base", default="")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    _load_env()
    token = os.environ.get("LIARA_API_TOKEN", "")
    if not token:
        print("LIARA_API_TOKEN is not set (put it in .env). Aborting.")
        return 1
    bases = (
        [args.base]
        if args.base
        else [os.environ.get("LIARA_API_BASE", "https://api.liara.ir"), "https://api.iran.liara.ir"]
    )
    recorder = FixtureRecorder(ROOT / "tools" / "fixtures" / "live") if args.record else None
    report: dict[str, object] = {
        "probe_version": 1,
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    for base in bases:
        client = LiaraClient(
            token,
            api_base=base,
            dns_base=os.environ.get("LIARA_DNS_BASE", "https://dns-service.liara.ir"),
            team_id=os.environ.get("LIARA_TEAM_ID", ""),
            recorder=recorder,
        )
        try:
            me = await client.me()
            report["base_url_ok"] = base
            plans = me.project_plans()
            section(
                "account",
                {
                    "base": base,
                    "is_team": me.user.is_team or bool(me.team),
                    "email_masked": (me.user.email[:2] + "***") if me.user.email else "",
                    "feature_flags": [f.get("key") for f in me.feature_flags][:20],
                },
            )
            section(
                "plan catalog (projects)",
                [
                    {
                        "plan_id": p.plan_id,
                        "available": p.available,
                        "region": p.region,
                        "ram": p.ram.amount,
                        "cpu": p.cpu.amount,
                        "volume": p.volume,
                        "hourly_price": p.price,
                        "storage": p.storage_class,
                    }
                    for p in plans
                ],
            )
            raw_plan_keys = sorted(
                {
                    k
                    for v in (me.plans.get("projects") or {}).values()
                    if isinstance(v, dict)
                    for k in v
                }
            )
            section("raw plan keys", raw_plan_keys)
            billing = await client.billing()
            section(
                "billing",
                {
                    **billing.model_dump(),
                    "team_balance": me.team_balance,
                    "effective_balance": await client.account_balance(me),
                },
            )
            apps = await client.list_projects()
            section("apps", [a.model_dump(by_alias=False) for a in apps])
            target = args.app or (apps[0].name if apps else "")
            if target:
                try:
                    await probe_app(client, target)
                except LiaraError as exc:
                    section(f"app probe {target}", {"error": exc.message, "status": exc.status})
            try:
                zones = await client.dns_zones()
                section("dns zones", [z.model_dump(by_alias=False) for z in zones])
            except LiaraError as exc:
                section(
                    "dns zones",
                    {
                        "error": exc.message,
                        "status": exc.status,
                        "note": "dns-service may need LIARA_TEAM_ID or a different host; see docs/LIMITATIONS.md",
                    },
                )
            break
        except LiaraError as exc:
            section(f"base {base}", {"error": exc.message, "status": exc.status})
        finally:
            await client.aclose()

    print("\n### done. Paste everything above (it is redacted) back into the chat.")
    return 0


async def probe_app(client: LiaraClient, app: str) -> None:
    now = int(time.time())
    project = await client.get_project(app)
    section(
        f"project {app}",
        {
            **project.model_dump(by_alias=False, exclude={"envs"}),
            "env_keys": [e.key for e in project.envs],
            "raw_keys": sorted(project.model_dump(by_alias=True).keys()),
        },
    )
    for since in (now - 600, 600, "10m"):
        try:
            logs = await client.logs(app, since=since)
            section(
                f"logs since={since!r}",
                {
                    "count": len(logs),
                    "first": logs[0].model_dump() if logs else None,
                    "last": logs[-1].model_dump() if logs else None,
                },
            )
            break
        except LiaraError as exc:
            section(f"logs since={since!r}", {"error": exc.message, "status": exc.status})
    for kind in ("cpu", "memory"):
        for since in (now - 1800, 1800):
            try:
                report = await client.metric(app, kind, since)
                points = report.result[0].points() if report.result else []
                gaps = [round(b[0] - a[0]) for a, b in zip(points, points[1:], strict=False)][:10]
                section(
                    f"metric {kind} since={since}",
                    {
                        "end": report.end,
                        "series": len(report.result),
                        "points": len(points),
                        "first": points[:2],
                        "last": points[-2:],
                        "sample_gaps_seconds": gaps,
                        "max_value": max((v for _, v in points), default=None),
                    },
                )
                break
            except LiaraError as exc:
                section(
                    f"metric {kind} since={since}", {"error": exc.message, "status": exc.status}
                )
    summary = await client.metrics_summary(app)
    section("metrics summary", summary.model_dump(by_alias=True))
    releases = await client.releases(app, count=5)
    section(
        "releases",
        {
            "total": releases.total,
            "current": releases.current_release,
            "states": [r.state for r in releases.releases],
            "first_raw_keys": sorted(releases.releases[0].model_dump(by_alias=True).keys())
            if releases.releases
            else [],
        },
    )
    if releases.releases:
        try:
            release = await client.get_release(releases.releases[0].id)
            section(
                "release by id",
                {
                    "state": release.state,
                    "source_id_present": bool(release.source_id),
                    "keys": sorted(release.model_dump(by_alias=True).keys()),
                },
            )
        except LiaraError as exc:
            section("release by id", {"error": exc.message, "status": exc.status})
    try:
        applets = await client.applets(app)
        section("applets", [a.model_dump() for a in applets])
    except LiaraError as exc:
        section(
            "applets",
            {
                "error": exc.message,
                "status": exc.status,
                "note": "non-fatal; the copilot skips this check",
            },
        )
    events = await client.events(app, start=now - 3600, end=now)
    section("events", {"rows": len(events), "sample": [v for r in events for v in r.values][:5]})
    domains = await client.domains(app)
    section("domains", [d.model_dump(by_alias=False) for d in domains])
    try:
        bad = await client._request("GET", f"/v1/projects/{app}-does-not-exist-xyz")  # noqa: SLF001
        section("error body format", bad)
    except LiaraError as exc:
        section("error body format", {"status": exc.status, "message": exc.message})


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
