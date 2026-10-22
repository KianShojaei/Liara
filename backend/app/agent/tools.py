"""Tool implementations. Each registered executor maps 1:1 to a ToolSpec in policy/tiers.

Executors receive validated args and return JSON-serialisable results. Verifiers (for T2
tools) re-probe after the change so the proposal ends as `verified` or `verification_failed`.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from app.deploy.advisor import PlanAdvisor
from app.deploy.analyzer import ProjectAnalyzer
from app.liara.redaction import mask_obj

if TYPE_CHECKING:
    from app.agent.context import Runtime

SETTLE_SECONDS = 3.0


def register_tools(rt: Runtime) -> None:  # noqa: C901 - one registration table on purpose
    client, proposals, verifier = rt.client, rt.proposals, rt.verifier

    # ---------------------------------------------------------------- T0

    async def get_account(args: dict[str, Any]) -> dict[str, Any]:
        me = await client.me()
        return {
            "user": me.user.model_dump(by_alias=False),
            "is_team": me.user.is_team or bool(me.team),
            "plans": [p.model_dump(by_alias=False) for p in me.project_plans()],
        }

    async def get_billing(args: dict[str, Any]) -> dict[str, Any]:
        billing = await client.billing()
        return {"balance": billing.balance, "account_type": billing.account_type}

    async def list_apps(args: dict[str, Any]) -> dict[str, Any]:
        return {"apps": [p.model_dump(by_alias=False) for p in await client.list_projects()]}

    async def get_app(args: dict[str, Any]) -> dict[str, Any]:
        project = await client.get_project(args["app"])
        data = project.model_dump(by_alias=False)
        data["envs"] = mask_obj([e.model_dump() for e in project.envs])
        data["url"] = rt.probe.url_for(project.name)
        return data

    async def get_logs(args: dict[str, Any]) -> dict[str, Any]:
        since = int(time.time()) - int(args.get("minutes", 10)) * 60
        logs = await client.logs(args["app"], since=since)
        return {
            "count": len(logs),
            "lines": [line.model_dump() for line in logs[-int(args.get("limit", 100)) :]],
        }

    async def get_events(args: dict[str, Any]) -> dict[str, Any]:
        end = int(time.time())
        rows = await client.events(
            args["app"],
            start=end - int(args.get("minutes", 60)) * 60,
            end=end,
            search=args.get("search"),
        )
        values = [v for row in rows for v in row.values]
        return {"events": [{"ts": v[0], "text": v[1]} for v in values if len(v) >= 2][-100:]}

    async def get_applets(args: dict[str, Any]) -> dict[str, Any]:
        return {"applets": [a.model_dump() for a in await client.applets(args["app"])]}

    async def get_releases(args: dict[str, Any]) -> dict[str, Any]:
        releases = await client.releases(args["app"], count=int(args.get("count", 10)))
        return {
            "current": releases.current_release,
            "releases": [r.model_dump(by_alias=False) for r in releases.releases],
        }

    async def get_metrics(args: dict[str, Any]) -> dict[str, Any]:
        kind = args.get("kind", "memory")
        since = int(time.time()) - int(args.get("minutes", 30)) * 60
        report = await client.metric(args["app"], kind, since)
        series = report.result[0].points() if report.result else []
        return {
            "kind": kind,
            "points": series[-120:],
            "applet": report.result[0].applet if report.result else "",
        }

    async def get_domains(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "domains": [d.model_dump(by_alias=False) for d in await client.domains(args["app"])]
        }

    async def check_domain(args: dict[str, Any]) -> dict[str, Any]:
        return (await client.check_domain(args["domain_id"])).model_dump(by_alias=False)

    async def get_dns_zone(args: dict[str, Any]) -> dict[str, Any]:
        return (await client.dns_zone(args["zone"])).model_dump(by_alias=False)

    async def http_probe(args: dict[str, Any]) -> dict[str, Any]:
        url = args.get("url") or rt.probe.url_for(args["app"], args.get("path", "/"))
        return await rt.probe.probe_series(url, count=int(args.get("count", 3)))

    async def analyze_project(args: dict[str, Any]) -> dict[str, Any]:
        return (await asyncio.to_thread(ProjectAnalyzer(args["path"]).analyze)).to_dict()

    async def recommend_plan(args: dict[str, Any]) -> dict[str, Any]:
        me, billing = await asyncio.gather(client.me(), client.billing())
        analysis = (
            await asyncio.to_thread(ProjectAnalyzer(args["path"]).analyze)
            if args.get("path")
            else None
        )
        from app.deploy.analyzer import ProjectAnalysis

        analysis = analysis or ProjectAnalysis(path="", platform=args.get("platform", "node"))
        return PlanAdvisor(me.project_plans(), billing.balance).advise(analysis).to_dict()

    async def get_limitations(args: dict[str, Any]) -> dict[str, Any]:
        return {"limitations": rt.knowledge.limitations() if rt.knowledge else []}

    async def search_docs(args: dict[str, Any]) -> dict[str, Any]:
        return (
            {"results": await rt.knowledge.search(args["query"], k=int(args.get("k", 4)))}
            if rt.knowledge
            else {"results": []}
        )

    for name, fn in {
        "get_account": get_account,
        "get_billing": get_billing,
        "list_apps": list_apps,
        "get_app": get_app,
        "get_logs": get_logs,
        "get_events": get_events,
        "get_applets": get_applets,
        "get_releases": get_releases,
        "get_metrics": get_metrics,
        "get_domains": get_domains,
        "check_domain": check_domain,
        "get_dns_zone": get_dns_zone,
        "http_probe": http_probe,
        "analyze_project": analyze_project,
        "recommend_plan": recommend_plan,
        "get_limitations": get_limitations,
        "search_docs": search_docs,
    }.items():
        proposals.register(name, fn)

    # ---------------------------------------------------------------- T1

    async def recheck_dns(args: dict[str, Any]) -> dict[str, Any]:
        await client.dns_check_nameservers(args["zone"])
        return (await client.dns_zone(args["zone"])).model_dump(by_alias=False)

    async def run_health_check(args: dict[str, Any]) -> dict[str, Any]:
        return await verifier.verify_health(args["app"], args.get("health_path", "/"))

    async def set_watch(args: dict[str, Any]) -> dict[str, Any]:
        if rt.watcher is None:
            return {"watching": False, "reason": "watcher disabled"}
        if args.get("enabled", True):
            rt.watcher.watch(args["app"], health_path=args.get("health_path", "/"))
        else:
            rt.watcher.unwatch(args["app"])
        return {"watching": args.get("enabled", True), "apps": rt.watcher.apps()}

    proposals.register("recheck_dns", recheck_dns)
    proposals.register("run_health_check", run_health_check)
    proposals.register("set_watch", set_watch)

    # ---------------------------------------------------------------- T2

    async def verify_health_after(args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(SETTLE_SECONDS)
        return await verifier.verify_health(args["app"], args.get("health_path", "/"))

    async def create_app(args: dict[str, Any]) -> dict[str, Any]:
        await client.create_project(
            args["app"],
            args["plan_id"],
            args["platform"],
            read_only_root_fs=bool(args.get("read_only_root_fs", False)),
        )
        project = await client.get_project(args["app"])
        return {
            "app": project.name,
            "plan_id": project.plan_id,
            "platform": project.platform,
            "url": rt.probe.url_for(project.name),
        }

    async def verify_create_app(args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        project = await client.get_project(args["app"])
        ok = project.plan_id == args["plan_id"]
        return {
            "ok": ok,
            "steps": [
                {
                    "name": "app_exists",
                    "ok": True,
                    "detail": f"{project.name} ({project.platform})",
                },
                {"name": "plan", "ok": ok, "detail": project.plan_id},
            ],
        }

    async def deploy(args: dict[str, Any]) -> dict[str, Any]:
        session_id = args.get("_session_id", "")

        async def on_line(line: str) -> None:
            if session_id:
                rt.emit(session_id, "deploy_log", {"line": line})

        return await rt.deploy_engine.deploy(
            project_path=args["path"],
            app=args["app"],
            port=int(args["port"]),
            platform=args["platform"],
            message=args.get("message", ""),
            on_line=on_line,
        )

    async def verify_deploy(args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        session_id = args.get("_session_id", "")

        def on_state(state: str) -> None:
            if session_id:
                rt.emit(session_id, "deploy_log", {"line": f"release state: {state}"})

        return await verifier.verify_deploy(
            args["app"], result.get("release_id"), args.get("health_path", "/"), on_state=on_state
        )

    async def redeploy_release(args: dict[str, Any]) -> dict[str, Any]:
        return await rt.deploy_engine.redeploy_release(args["app"], args["release_id"])

    async def restart_app(args: dict[str, Any]) -> dict[str, Any]:
        await client.restart(args["app"])
        return {"restarted": args["app"]}

    async def scale_app(args: dict[str, Any]) -> dict[str, Any]:
        await client.scale(args["app"], int(args["scale"]))
        return {"app": args["app"], "scale": int(args["scale"])}

    async def verify_scale(args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(SETTLE_SECONDS)
        project = await client.get_project(args["app"])
        ok = project.scale == int(args["scale"])
        return {
            "ok": ok,
            "steps": [{"name": "scale", "ok": ok, "detail": f"scale={project.scale}"}],
        }

    async def set_env(args: dict[str, Any]) -> dict[str, Any]:
        await client.update_envs(args["app"], dict(args["variables"]))
        return {"app": args["app"], "keys": sorted(args["variables"].keys())}

    async def resize_app(args: dict[str, Any]) -> dict[str, Any]:
        before = await client.metrics_summary(args["app"])
        await client.resize(args["app"], args["plan_id"])
        return {
            "app": args["app"],
            "plan_id": args["plan_id"],
            "baseline": {"cpu": before.cpu, "memory": before.memory},
        }

    async def verify_resize(args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(SETTLE_SECONDS)
        project = await client.get_project(args["app"])
        after = await client.metrics_summary(args["app"])
        health = await verifier.verify_health(args["app"], args.get("health_path", "/"))
        plan_ok = project.plan_id == args["plan_id"]
        return {
            "ok": plan_ok and health["ok"],
            "steps": [{"name": "plan", "ok": plan_ok, "detail": project.plan_id}, *health["steps"]],
            "baseline": result.get("baseline"),
            "after": {"cpu": after.cpu, "memory": after.memory},
        }

    async def add_domain(args: dict[str, Any]) -> dict[str, Any]:
        domain_id = await client.create_domain(args["domain"], args["app"])
        domain = await client.check_domain(domain_id)
        return {
            "domain_id": domain_id,
            "domain": domain.name,
            "cname": domain.cname_record,
            "verification_code": domain.verification_code,
            "status": domain.status,
        }

    async def verify_domain(args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        domain = await client.check_domain(result["domain_id"])
        ok = domain.status.upper() in (
            "SET",
            "ACTIVE",
            "OK",
        ) and domain.certificates_status.upper() in ("OK", "ACTIVE")
        steps = [
            {
                "name": "dns",
                "ok": domain.status.upper() in ("SET", "ACTIVE", "OK"),
                "detail": f"status {domain.status}",
            },
            {
                "name": "ssl",
                "ok": domain.certificates_status.upper() in ("OK", "ACTIVE"),
                "detail": f"certificates {domain.certificates_status}",
            },
        ]
        if ok:
            steps.append(
                {
                    "name": "https",
                    **{
                        k: v
                        for k, v in (await rt.probe.probe(f"https://{domain.name}/")).items()
                        if k in ("ok", "status", "latency_ms")
                    },
                }
            )
        return {"ok": ok and steps[-1]["ok"], "steps": steps, "pending": not ok}

    async def enable_ssl(args: dict[str, Any]) -> dict[str, Any]:
        return await client.enable_ssl(args["domain"])

    async def toggle_setting(args: dict[str, Any]) -> dict[str, Any]:
        project = await client.get_project(args["app"])
        await client.set_setting(project.id, args["setting"], bool(args["enabled"]))
        return {"app": args["app"], "setting": args["setting"], "enabled": bool(args["enabled"])}

    async def create_dns_zone(args: dict[str, Any]) -> dict[str, Any]:
        body = await client._post(
            "/api/v1/zones", base=client._dns_base, json_body={"name": args["zone"]}
        )  # noqa: SLF001
        return body.get("data", body)

    async def create_dns_record(args: dict[str, Any]) -> dict[str, Any]:
        record = await client.dns_create_record(
            args["zone"], args["name"], args["type"], args["contents"], int(args.get("ttl", 300))
        )
        return record.model_dump(by_alias=False)

    async def submit_fix(args: dict[str, Any]) -> dict[str, Any]:
        from app.bridge.fix_brief import apply_patch

        applied = await asyncio.to_thread(apply_patch, args["path"], args["patch"])
        result = await deploy({**args, "message": args.get("message", "fix: coding-agent patch")})
        return {"patch": applied, **result}

    proposals.register("create_app", create_app, verify_create_app)
    proposals.register("deploy", deploy, verify_deploy)
    proposals.register("redeploy_release", redeploy_release, verify_deploy)
    proposals.register("restart_app", restart_app, verify_health_after)
    proposals.register("scale_app", scale_app, verify_scale)
    proposals.register("set_env", set_env, verify_health_after)
    proposals.register("resize_app", resize_app, verify_resize)
    proposals.register("add_domain", add_domain, verify_domain)
    proposals.register("enable_ssl", enable_ssl)
    proposals.register("toggle_setting", toggle_setting, verify_health_after)
    proposals.register("create_dns_zone", create_dns_zone)
    proposals.register("create_dns_record", create_dns_record)
    proposals.register("submit_fix", submit_fix, verify_deploy)

    # ---------------------------------------------------------------- T3 (disabled unless COPILOT_ENABLE_GUARDED)

    async def delete_app(args: dict[str, Any]) -> dict[str, Any]:
        await client.delete_project(args["app"])
        return {"deleted": args["app"]}

    async def delete_domain(args: dict[str, Any]) -> dict[str, Any]:
        await client.delete_domain(args["domain_id"])
        return {"deleted": args["domain_id"]}

    async def disable_ssl(args: dict[str, Any]) -> dict[str, Any]:
        await client.disable_ssl(args["domain_id"])
        return {"ssl_disabled": args["domain_id"]}

    proposals.register("delete_app", delete_app)
    proposals.register("delete_domain", delete_domain)
    proposals.register("disable_ssl", disable_ssl)
    proposals.register("downgrade_app", resize_app, verify_resize)
