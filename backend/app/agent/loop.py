"""Agent loop: route a user message to a deterministic flow, or run a small tool-calling loop.

Order of precedence:
  1. keyword router (works offline, zero LLM cost, predictable demo)
  2. LLM router (small model) when the keyword router is unsure
  3. LLM tool-calling loop (strong model) with T0 tools auto and T2 tools as proposals
  4. without an LLM key: a helpful rule-based answer listing what the copilot can do
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.deploy.wizard import DeployWizard
from app.liara.errors import LiaraError
from app.liara.redaction import mask_obj
from app.llm.prompts import ROUTER_PROMPT, SYSTEM_PROMPT
from app.policy.proposals import Impact
from app.policy.tiers import Tier, all_specs
from app.sre.investigator import Investigator

if TYPE_CHECKING:
    from app.agent.context import Runtime

MAX_TOOL_ROUNDS = 6

KEYWORDS: dict[str, tuple[str, ...]] = {
    "deploy": ("deploy", "دیپلوی", "منتشر", "انتشار", "مستقر", "آپلود پروژه", "بالا بیار"),
    "investigate": (
        "کند",
        "slow",
        "خطا",
        "error",
        "500",
        "بررسی کن",
        "مشکل",
        "down",
        "پایین",
        "کار نمی",
        "باز نمی",
        "incident",
        "چرا",
    ),
    "restart": ("restart", "ری‌استارت", "ریستارت", "ری استارت"),
    "status": ("وضعیت", "status", "سلامت", "health", "چطوره", "چطور است"),
    "logs": ("لاگ", "log"),
    "billing": ("موجودی", "هزینه", "balance", "شارژ", "قیمت", "پلن‌ها", "پلن ها"),
    "resize": ("resize", "ارتقا", "پلن بزرگ", "تغییر پلن", "پلن را"),
    "set_env": ("env", "متغیر", "environment"),
    "domain": ("دامنه", "domain", "dns", "ssl"),
    "scale_off": ("خاموش", "turn off", "stop app"),
    "scale_on": ("روشن", "turn on", "start app"),
    "docs": ("چطور", "how do", "راهنما", "مستندات"),
}


class RouteResult(BaseModel):
    intent: str = "other"
    app: str = ""
    path: str = ""
    domain: str = ""
    plan_id: str = ""
    variables: dict[str, str] = Field(default_factory=dict)
    reason: str = ""
    explicit_app: str = ""  # app named in the message itself (not inherited from the session)


class Agent:
    def __init__(self, rt: Runtime):
        self._rt = rt
        self.wizard = DeployWizard(rt)
        self.investigator = Investigator(rt)
        rt.proposals.register(
            "deploy_project", self.wizard.execute_deploy_project, self.wizard.verify_deploy_project
        )

    # ------------------------------------------------------------ entry

    async def handle(
        self, session_id: str, text: str, *, context: dict[str, Any] | None = None
    ) -> None:
        rt = self._rt
        context = context or {}
        rt.emit(session_id, "message", {"role": "user", "text": text})
        session = rt.store.get_session(session_id) or {}
        route = self._keyword_route(text)
        if route.intent == "other" and rt.llm.available:
            route = await self._llm_route(text)
        route.app = (
            route.app or context.get("app") or session.get("app_name") or await self._default_app()
        )
        route.path = route.path or context.get("path") or session.get("project_path") or ""
        if route.app:
            rt.store.update_session(session_id, app_name=route.app)
        try:
            await self._dispatch(session_id, text, route)
        except LiaraError as exc:
            rt.emit(session_id, "error", {"text": exc.user_message})
        except PermissionError as exc:
            rt.emit(session_id, "error", {"text": f"این عملیات مجاز نیست: {exc}"})

    # ---------------------------------------------------------- routing

    def _keyword_route(self, text: str) -> RouteResult:
        lower = text.lower()
        route = RouteResult()
        for intent, words in KEYWORDS.items():
            if any(w in lower for w in words):
                route.intent = intent
                break
        path = re.search(r"(?:^|\s)((?:~|\.{1,2}|/|[A-Za-z]:[\\/])[^\s]+)", text)
        if path:
            route.path = path.group(1)
        domain = re.search(r"\b([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b", lower)
        if domain and route.intent == "domain":
            route.domain = domain.group(1)
        plan = re.search(r"\b(ir-[a-z0-9-]+|free)\b", lower)
        if plan:
            route.plan_id = plan.group(1)
        for key, value in re.findall(r"\b([A-Z][A-Z0-9_]{2,})\s*=\s*([^\s,]+)", text):
            route.variables[key] = value
        app = re.search(r"(?:app|برنامه|پروژه)\s+([a-z0-9][a-z0-9-]{1,30})", lower)
        if app:
            route.app = route.explicit_app = app.group(1)
        if route.variables and route.intent in ("other", "set_env"):
            route.intent = "set_env"
        return route

    async def _llm_route(self, text: str) -> RouteResult:
        try:
            result: RouteResult = await self._rt.llm.structured(
                RouteResult,
                [{"role": "system", "content": ROUTER_PROMPT}, {"role": "user", "content": text}],
                role="small",
            )  # type: ignore[assignment]
            result.explicit_app = result.app
            return result
        except Exception:  # noqa: BLE001
            return RouteResult()

    async def _default_app(self) -> str:
        try:
            apps = await self._rt.client.list_projects()
        except LiaraError:
            return ""
        allow = self._rt.settings.app_allowlist
        candidates = [a.name for a in apps if not allow or a.name in allow]
        return candidates[0] if len(candidates) == 1 else ""

    # --------------------------------------------------------- dispatch

    async def _dispatch(self, session_id: str, text: str, route: RouteResult) -> None:
        rt = self._rt

        def say(text_out: str, **extra: Any) -> None:
            rt.emit(session_id, "message", {"role": "assistant", "text": text_out, **extra})

        # noqa: E731
        intent = route.intent

        if intent == "deploy":
            if not route.path:
                say(
                    "مسیر پوشه‌ی پروژه را بفرست (مثلاً `./my-site`) تا بررسی‌اش کنم و پلن مناسب را پیشنهاد بدهم."
                )
                return
            say("باشه، پروژه را بررسی می‌کنم و قبل از هر تغییری از شما تأیید می‌گیرم.")
            await self.wizard.start(
                session_id, route.path, app_name=route.explicit_app, plan_id=route.plan_id
            )
            return

        if intent == "investigate":
            if not route.app:
                say("کدام برنامه؟ نام برنامه را بگویید (لیست برنامه‌ها در پنل وضعیت هست).")
                return
            say(f"بررسی {route.app} را شروع می‌کنم؛ این مرحله فقط خواندنی است و چیزی تغییر نمی‌کند.")
            incident = await self.investigator.investigate(
                route.app,
                session_id=session_id,
                trigger="user: " + text[:80],
                project_path=route.path,
            )
            say(incident.get("summary") or "بررسی تمام شد.", incident_id=incident.get("id"))
            return

        if intent == "status":
            if not route.app:
                return await self._list_apps(session_id)
            result = await rt.proposals.run_auto(session_id, "run_health_check", {"app": route.app})
            lines = [
                f"{'✅' if s['ok'] else '❌'} {s['name']}: {s['detail']}" for s in result["steps"]
            ]
            say(
                ("همه چیز سالم است." if result["ok"] else "مشکلی دیده می‌شود.")
                + "\n"
                + "\n".join(lines)
                + f"\nآدرس: {result['url']}",
                status=result,
            )
            return

        if intent == "logs":
            result = await rt.proposals.run_auto(
                session_id, "get_logs", {"app": route.app, "minutes": 10, "limit": 30}
            )
            rt.emit(session_id, "logs", {"app": route.app, **mask_obj(result)})
            say(f"{result['count']} خط لاگ ۱۰ دقیقه‌ی اخیر {route.app} را آوردم.")
            return

        if intent == "billing":
            billing, account = (
                await rt.proposals.run_auto(session_id, "get_billing", {}),
                await rt.proposals.run_auto(session_id, "get_account", {}),
            )
            plans = [
                p for p in account["plans"] if p.get("available") and p.get("region") == "iran"
            ]
            lines = [
                f"- {p['plan_id']}: {p['ram']['amount']}GB RAM، {p['cpu']['amount']} CPU، {p['price']:.0f} تومان/ساعت ({p['price'] * 720:,.0f}/ماه)"
                for p in plans[:6]
            ]
            say(
                f"موجودی حساب: {billing['balance']:,.0f} تومان.\nپلن‌های در دسترس:\n"
                + "\n".join(lines)
                + "\nشارژ حساب فقط از کنسول ممکن است (API اجازه نمی‌دهد).",
                billing=billing,
            )
            return

        if intent == "restart":
            return await self._propose(
                session_id,
                "restart_app",
                {"app": route.app},
                title=f"ری‌استارت {route.app}",
                summary="برنامه چند ثانیه در دسترس نخواهد بود؛ بعد از آن سلامت بررسی می‌شود.",
                impact=Impact(
                    downtime="brief",
                    rollback_plan="نیازی نیست؛ ری‌استارت قابل بازگشت نیست ولی بدون اثر ماندگار است.",
                ),
            )

        if intent in ("scale_off", "scale_on"):
            scale = 0 if intent == "scale_off" else 1
            return await self._propose(
                session_id,
                "scale_app",
                {"app": route.app, "scale": scale},
                title=("خاموش کردن " if scale == 0 else "روشن کردن ") + route.app,
                summary="با خاموش شدن، هزینه‌ی ساعتی متوقف می‌شود و سایت از دسترس خارج می‌شود."
                if scale == 0
                else "برنامه دوباره روشن و در دسترس می‌شود.",
                impact=Impact(
                    downtime="yes" if scale == 0 else "none",
                    rollback_plan="با عملیات معکوس (روشن/خاموش) برمی‌گردد.",
                ),
            )

        if intent == "set_env":
            if not route.variables:
                say(
                    "متغیرها را به شکل `KEY=value` بفرستید (مثلاً `FAULT_MODE=none`). مقادیر حساس در گفتگو ذخیره نمی‌شوند."
                )
                return
            keys = ", ".join(route.variables)
            return await self._propose(
                session_id,
                "set_env",
                {"app": route.app, "variables": route.variables},
                title=f"تنظیم متغیر محیطی روی {route.app}",
                summary=f"متغیرهای {keys} ثبت می‌شوند و برنامه ری‌استارت می‌شود. بعد از آن سلامت و لاگ‌ها بررسی می‌شوند.",
                impact=Impact(downtime="brief", rollback_plan="مقدار قبلی را دوباره تنظیم کنید."),
            )

        if intent == "resize":
            return await self._propose_resize(session_id, route)

        if intent == "domain":
            if not route.domain:
                say("نام دامنه را بفرستید (مثلاً `shop.example.ir`).")
                return
            return await self._propose(
                session_id,
                "add_domain",
                {"app": route.app, "domain": route.domain},
                title=f"اتصال دامنه {route.domain} به {route.app}",
                summary="دامنه در لیارا ثبت می‌شود؛ بعد از آن رکوردهای DNS را به شما نشان می‌دهم تا در پنل DNS ثبت کنید، و وضعیت و گواهی SSL را دنبال می‌کنم.",
                impact=Impact(
                    downtime="none", rollback_plan="حذف دامنه از پنل (عملیات محافظت‌شده)."
                ),
            )

        if intent == "docs":
            results = await rt.proposals.run_auto(session_id, "search_docs", {"query": text})
            if results["results"]:
                say(
                    "این بخش‌های مستندات لیارا مرتبط است:\n"
                    + "\n".join(
                        f"- {r['heading'] or r['source']} — {r['url']}"
                        for r in results["results"][:4]
                    ),
                    docs=results,
                )
                return

        if rt.llm.available:
            return await self._tool_loop(session_id, text, route)
        say(self._capabilities_text())

    async def _list_apps(self, session_id: str) -> None:
        result = await self._rt.proposals.run_auto(session_id, "list_apps", {})
        lines = [
            f"- {a['name']} ({a['platform']}, {a['plan_id']}, {'روشن' if a['scale'] else 'خاموش'})"
            for a in result["apps"]
        ]
        body = (
            "برنامه‌های حساب شما:\n"
            + ("\n".join(lines) or "برنامه‌ای وجود ندارد.")
            + "\nبرای وضعیت دقیق بگویید «وضعیت <نام برنامه>»."
        )
        self._rt.emit(
            session_id, "message", {"role": "assistant", "text": body, "apps": result["apps"]}
        )

    async def _propose(
        self,
        session_id: str,
        tool: str,
        args: dict[str, Any],
        *,
        title: str,
        summary: str,
        impact: Impact,
    ) -> None:
        if not args.get("app") and tool not in ("enable_ssl",):
            self._rt.emit(
                session_id, "message", {"role": "assistant", "text": "نام برنامه را مشخص کنید."}
            )
            return
        _, decision, _ = self._rt.proposals.propose(
            session_id,
            tool,
            {**args, "_session_id": session_id},
            title=title,
            summary=summary,
            impact=impact,
        )
        text = (
            "کارت تأیید آماده است؛ بعد از تأیید شما اجرا و نتیجه بررسی می‌شود."
            if decision.mode == "approval"
            else ("این عملیات مسدود شد: " + "; ".join(decision.reasons))
        )
        self._rt.emit(session_id, "message", {"role": "assistant", "text": text})

    async def _propose_resize(self, session_id: str, route: RouteResult) -> None:
        rt = self._rt
        project, me = await rt.client.get_project(route.app), await rt.client.me()
        plans = sorted(
            (
                p
                for p in me.project_plans()
                if p.available and p.region == "iran" and p.plan_id != "free"
            ),
            key=lambda p: p.price,
        )
        current = next((p for p in plans if p.plan_id == project.plan_id), None)
        target = (
            next((p for p in plans if p.plan_id == route.plan_id), None)
            if route.plan_id
            else next((p for p in plans if current and p.price > current.price), None)
        )
        if target is None:
            rt.emit(
                session_id,
                "message",
                {
                    "role": "assistant",
                    "text": "پلن مقصد را مشخص کنید. پلن‌های در دسترس: "
                    + ", ".join(p.plan_id for p in plans),
                },
            )
            return
        delta = target.price - (current.price if current else project.hourly_price)
        tool = "downgrade_app" if delta < 0 else "resize_app"
        await self._propose(
            session_id,
            tool,
            {"app": route.app, "plan_id": target.plan_id},
            title=f"تغییر پلن {route.app} به {target.plan_id}",
            summary=f"{target.ram.amount}GB RAM و {target.cpu.amount} CPU. هزینه {'+' if delta >= 0 else ''}{delta:.0f} تومان در ساعت ({delta * 720:+,.0f} در ماه). برنامه چند ثانیه ری‌استارت می‌شود و بعد متریک‌ها با قبل مقایسه می‌شوند.",
            impact=Impact(
                cost_delta_hourly=delta,
                cost_delta_monthly=delta * 720,
                downtime="brief",
                rollback_plan=f"بازگشت به پلن {project.plan_id}.",
            ),
        )

    # -------------------------------------------------------- LLM loop

    def _tool_schemas(self) -> list[dict[str, Any]]:
        schemas = []
        for spec in all_specs():
            if spec.tier == Tier.T3 or spec.name in (
                "deploy_project",
                "submit_fix",
                "set_watch",
                "deploy",
                "redeploy_release",
            ):
                continue
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": f"[{spec.tier.value}] {spec.description}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "app": {"type": "string"},
                                "path": {"type": "string"},
                                "minutes": {"type": "integer"},
                                "kind": {"type": "string"},
                                "query": {"type": "string"},
                                "domain": {"type": "string"},
                                "domain_id": {"type": "string"},
                                "plan_id": {"type": "string"},
                                "scale": {"type": "integer"},
                                "variables": {"type": "object"},
                                "setting": {"type": "string"},
                                "enabled": {"type": "boolean"},
                                "zone": {"type": "string"},
                            },
                        },
                    },
                }
            )
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": "start_deploy_wizard",
                    "description": "Start the deploy wizard for a local project folder",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "app": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        )
        return schemas

    async def _tool_loop(self, session_id: str, text: str, route: RouteResult) -> None:
        rt = self._rt
        history = [m["payload"] for m in rt.store.timeline(session_id) if m["kind"] == "message"][
            -12:
        ]
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
                + f"\nCurrent app: {route.app or 'unknown'}. Project path: {route.path or 'unknown'}.",
            }
        ]
        messages += [{"role": m["role"], "content": m["text"]} for m in history[:-1]]
        messages.append({"role": "user", "content": text})
        schemas = self._tool_schemas()
        for _ in range(MAX_TOOL_ROUNDS):
            turn = await rt.llm.chat(messages, role="strong", tools=schemas)
            if not turn.tool_calls:
                rt.emit(session_id, "message", {"role": "assistant", "text": turn.content or "…"})
                return
            messages.append(
                {
                    "role": "assistant",
                    "content": turn.content or "",
                    "tool_calls": [
                        {
                            "id": c.call_id or f"call_{i}",
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                        }
                        for i, c in enumerate(turn.tool_calls)
                    ],
                }
                if rt.settings.llm_action_protocol == "tools"
                else {
                    "role": "assistant",
                    "content": turn.content
                    or json.dumps(
                        {"action": turn.tool_calls[0].name, "args": turn.tool_calls[0].arguments}
                    ),
                }
            )
            for i, call in enumerate(turn.tool_calls):
                result = await self._run_llm_tool(
                    session_id, call.name, {"app": route.app, **call.arguments}
                )
                content = json.dumps(mask_obj(result), ensure_ascii=False)[:6000]
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.call_id or f"call_{i}",
                        "content": content,
                    }
                    if rt.settings.llm_action_protocol == "tools"
                    else {"role": "user", "content": f"TOOL RESULT ({call.name}): {content}"}
                )
                if result.get("status") == "pending_approval":
                    rt.emit(
                        session_id,
                        "message",
                        {
                            "role": "assistant",
                            "text": turn.content
                            or "کارت تأیید آماده است؛ بعد از تأیید شما اجرا می‌شود.",
                        },
                    )
                    return
        rt.emit(
            session_id,
            "message",
            {"role": "assistant", "text": "به سقف مراحل رسیدم؛ درخواست را دقیق‌تر بیان کنید."},
        )

    async def _run_llm_tool(
        self, session_id: str, name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        rt = self._rt
        if name == "start_deploy_wizard":
            state = await self.wizard.start(session_id, args["path"], app_name=args.get("app", ""))
            return {"status": "pending_approval" if state.stage == "proposed" else state.stage}
        if name == "investigate":
            incident = await self.investigator.investigate(
                args["app"], session_id=session_id, trigger="llm"
            )
            return {
                "incident_id": incident.get("id"),
                "summary": incident.get("summary"),
                "hypotheses": incident.get("hypotheses"),
            }
        try:
            spec = next(s for s in all_specs() if s.name == name)
        except StopIteration:
            return {"error": f"unknown tool {name}"}
        if spec.tier in (Tier.T0, Tier.T1):
            try:
                return await rt.proposals.run_auto(session_id, name, args)
            except (LiaraError, PermissionError, KeyError) as exc:
                return {"error": getattr(exc, "user_message", str(exc))}
        proposal, decision, _ = rt.proposals.propose(
            session_id,
            name,
            args,
            title=spec.description,
            summary=f"پیشنهاد مدل: {name} با {mask_obj(args)}",
            impact=Impact(reversibility=spec.reversibility, downtime=spec.downtime),
        )
        return {
            "status": "pending_approval" if decision.mode == "approval" else "blocked",
            "proposal_id": proposal["id"],
            "reasons": decision.reasons,
        }

    @staticmethod
    def _capabilities_text() -> str:
        return (
            "می‌توانم این کارها را انجام دهم:\n"
            "- «دیپلوی ./مسیر-پروژه» — بررسی پروژه، پیشنهاد پلن و دیپلوی با تأیید شما\n"
            "- «وضعیت <برنامه>» — سلامت، آدرس و منابع\n"
            "- «سایت کند شده» یا «خطا می‌دهد» — بررسی لاگ‌ها و متریک‌ها و پیشنهاد راه‌حل\n"
            "- «ری‌استارت <برنامه>»، «KEY=value»، «ارتقا به medium-g2»، «دامنه example.ir»\n"
            "- «موجودی» — موجودی و قیمت پلن‌ها\n"
            "(کلید LLM تنظیم نشده؛ پاسخ‌های آزاد در دسترس نیست ولی همه‌ی عملیات بالا کار می‌کند.)"
        )
