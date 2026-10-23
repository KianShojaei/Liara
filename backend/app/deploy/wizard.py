"""Deploy wizard: a deterministic state machine. The LLM only explains; code decides.

States: analyzing -> advising -> balance_check -> (manual_step: charge) -> env_form ->
        proposed -> (human approval) -> executing (live stepper) -> verified | failed

Every transition is a timeline event so the UI can render cards and the audit shows the path.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.deploy.advisor import PlanAdvice, PlanAdvisor
from app.deploy.analyzer import ProjectAnalysis, ProjectAnalyzer
from app.deploy.liara_json import build_liara_json, write_liara_json
from app.liara.errors import LiaraConflict, LiaraError, LiaraNotFound
from app.policy.proposals import Impact

if TYPE_CHECKING:
    from app.agent.context import Runtime


@dataclass
class WizardState:
    session_id: str
    project_path: str
    app_name: str
    stage: str = "idle"
    analysis: ProjectAnalysis | None = None
    advice: PlanAdvice | None = None
    plan_id: str = ""
    app_exists: bool = False
    env_values: dict[str, str] = field(default_factory=dict)
    proposal_id: str = ""
    domain: str = ""
    approval_token: str = ""  # handed to the human UI only


class DeployWizard:
    def __init__(self, rt: Runtime):
        self._rt = rt
        self._states: dict[str, WizardState] = {}

    def state(self, session_id: str) -> WizardState | None:
        return self._states.get(session_id)

    # ----------------------------------------------------------------- start

    async def start(
        self,
        session_id: str,
        project_path: str,
        *,
        app_name: str = "",
        plan_id: str = "",
        domain: str = "",
    ) -> WizardState:
        rt = self._rt
        project_path = resolve_project_path(project_path)
        state = WizardState(
            session_id, project_path, app_name or _slug(project_path), domain=domain
        )
        self._states[session_id] = state
        rt.store.update_session(
            session_id, mode="deploy", project_path=project_path, app_name=state.app_name
        )

        state.stage = "analyzing"
        rt.emit(session_id, "status", {"stage": "analyzing", "text": "در حال بررسی پوشه‌ی پروژه…"})
        try:
            analysis = await asyncio.to_thread(ProjectAnalyzer(project_path).analyze)
        except FileNotFoundError as exc:
            state.stage = "failed"
            rt.emit(session_id, "error", {"text": f"پوشه پیدا نشد: {exc}"})
            return state
        state.analysis = analysis
        rt.emit(
            session_id,
            "analysis",
            {**analysis.to_dict(), "explanation": await self._explain_analysis(analysis)},
        )

        state.stage = "advising"
        try:
            me = await rt.client.me()
            balance = await rt.client.account_balance(me)
        except LiaraError as exc:
            state.stage = "failed"
            rt.emit(session_id, "error", {"text": exc.user_message})
            return state
        state.app_exists = await self._app_exists(state.app_name)
        advice = PlanAdvisor(me.project_plans(), balance).advise(analysis)
        state.advice = advice
        state.plan_id = plan_id or advice.recommended_plan_id
        rt.emit(
            session_id,
            "plan_options",
            {**advice.to_dict(), "app_name": state.app_name, "app_exists": state.app_exists},
        )

        if not advice.balance_ok or advice.low_balance:
            state.stage = "balance_check"
            rt.emit(
                session_id,
                "manual_step",
                {
                    **(rt.knowledge.limitation("charge_account") or {}),
                    "reason": advice.balance_message,
                    "blocking": not advice.balance_ok,
                    "resume": "wizard_resume",
                },
            )
            if not advice.balance_ok:
                return state

        return await self._collect_env_or_propose(state)

    async def resume(self, session_id: str) -> WizardState:
        """Called when the human presses 'Done' on a manual-step card."""
        state = self._require(session_id)
        if state.stage == "balance_check":
            assert state.analysis and state.advice
            me = await self._rt.client.me()
            balance = await self._rt.client.account_balance(me)
            state.advice = PlanAdvisor(me.project_plans(), balance).advise(state.analysis)
            self._rt.emit(
                session_id,
                "plan_options",
                {
                    **state.advice.to_dict(),
                    "app_name": state.app_name,
                    "app_exists": state.app_exists,
                    "refreshed": True,
                },
            )
            if not state.advice.balance_ok:
                self._rt.emit(
                    session_id,
                    "message",
                    {
                        "role": "assistant",
                        "text": "موجودی هنوز کافی نیست. بعد از شارژ دوباره «انجام شد» را بزنید.",
                    },
                )
                return state
            return await self._collect_env_or_propose(state)
        return state

    async def provide_env(self, session_id: str, values: dict[str, str]) -> WizardState:
        state = self._require(session_id)
        state.env_values.update({k: v for k, v in values.items() if v != ""})
        return await self._propose(state)

    async def choose_plan(self, session_id: str, plan_id: str) -> WizardState:
        state = self._require(session_id)
        state.plan_id = plan_id
        if state.stage == "proposed":
            return await self._propose(state)
        return state

    # ---------------------------------------------------------------- steps

    async def _collect_env_or_propose(self, state: WizardState) -> WizardState:
        assert state.analysis
        if state.analysis.env_keys and not state.env_values:
            state.stage = "env_form"
            self._rt.emit(
                state.session_id,
                "env_form",
                {
                    "keys": state.analysis.env_keys,
                    "secret_keys": state.analysis.secret_env_keys,
                    "text": "این متغیرهای محیطی در پروژه استفاده شده‌اند. مقدارها را وارد کنید (مقادیر حساس فقط به لیارا ارسال می‌شوند و در گفتگو ذخیره نمی‌شوند).",
                },
            )
            return state
        return await self._propose(state)

    async def _propose(self, state: WizardState) -> WizardState:
        rt = self._rt
        assert state.analysis and state.advice
        option = next((o for o in state.advice.options if o.plan_id == state.plan_id), None)
        hourly = option.hourly_price if option else 0.0
        steps = []
        if not state.app_exists:
            steps.append(
                f"ساخت برنامه «{state.app_name}» با پلن {state.plan_id} ({state.analysis.platform})"
            )
        if state.env_values:
            steps.append(f"ثبت {len(state.env_values)} متغیر محیطی")
        steps.append(f"دیپلوی از پوشه‌ی پروژه روی پورت {state.analysis.port}")
        steps.append(f"بررسی سلامت روی مسیر {state.analysis.health_path}")
        summary = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
        impact = Impact(
            cost_delta_hourly=hourly if not state.app_exists else 0.0,
            cost_delta_monthly=(hourly * 720) if not state.app_exists else 0.0,
            reversibility="partial",
            downtime="brief" if state.app_exists else "none",
            rollback_plan="در صورت خرابی: بازگشت به نسخه‌ی قبلی (redeploy) یا خاموش کردن برنامه؛ هزینه‌ی برنامه با حذف متوقف می‌شود.",
            notes=[f"زمان باقی‌مانده با این پلن: {option.runway_label}" if option else ""],
        )
        args = {
            "app": state.app_name,
            "path": state.project_path,
            "plan_id": state.plan_id,
            "platform": state.analysis.platform,
            "port": state.analysis.port,
            "variables": state.env_values,
            "health_path": state.analysis.health_path,
            "create": not state.app_exists,
            "_session_id": state.session_id,
        }
        proposal, decision, token = rt.proposals.propose(
            state.session_id,
            "deploy_project",
            args,
            title=f"دیپلوی {state.app_name}",
            summary=summary,
            impact=impact,
        )
        state.proposal_id, state.approval_token, state.stage = (
            proposal["id"],
            token or "",
            "proposed" if decision.mode == "approval" else "blocked",
        )
        if decision.mode == "blocked":
            rt.emit(
                state.session_id,
                "error",
                {"text": "این عملیات توسط سیاست‌ها مسدود شد: " + "; ".join(decision.reasons)},
            )
        return state

    # ------------------------------------------------------------ executor

    async def execute_deploy_project(self, args: dict[str, Any]) -> dict[str, Any]:
        """Executor for the composite tool. Emits `step` events for the live stepper."""
        rt = self._rt
        session_id = args.get("_session_id", "")
        app, path = args["app"], args["path"]

        def step(name: str, status: str, detail: str = "") -> None:
            if session_id:
                rt.emit(session_id, "step", {"name": name, "status": status, "detail": detail})

        if args.get("create"):
            step("create_app", "running", f"plan {args['plan_id']}")
            me = await rt.client.me()
            bundle = me.bundle_plan_for(args["plan_id"])
            try:
                await rt.client.create_project(
                    app, args["plan_id"], args["platform"], bundle_plan_id=bundle
                )
            except LiaraConflict:
                raise RuntimeError(
                    f"نام «{app}» قبلاً در لیارا گرفته شده است؛ یک نام یکتا انتخاب کنید و دوباره دیپلوی را شروع کنید."
                ) from None
            step("create_app", "done", rt.probe.url_for(app))
        if args.get("variables"):
            step("set_env", "running", ", ".join(sorted(args["variables"])))
            await rt.client.update_envs(app, dict(args["variables"]))
            step("set_env", "done")
        step("liara_json", "running")
        config = build_liara_json(_analysis_for(path, args), app)
        await asyncio.to_thread(write_liara_json, path, config)
        step("liara_json", "done", "liara.json نوشته شد")

        step("deploy", "running")

        async def on_line(line: str) -> None:
            if session_id:
                rt.emit(session_id, "deploy_log", {"line": line})

        result = await rt.deploy_engine.deploy(
            project_path=path,
            app=app,
            port=int(args["port"]),
            platform=args["platform"],
            on_line=on_line,
        )
        step("deploy", "done", f"release {str(result.get('release_id', ''))[:8]}")
        return {**result, "app": app, "url": rt.probe.url_for(app)}

    async def verify_deploy_project(
        self, args: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]:
        rt = self._rt
        session_id = args.get("_session_id", "")
        if session_id:
            rt.emit(session_id, "step", {"name": "verify", "status": "running"})

        def on_state(state: str) -> None:
            if session_id:
                rt.emit(session_id, "deploy_log", {"line": f"release state: {state}"})

        verification = await rt.verifier.verify_deploy(
            args["app"], result.get("release_id"), args.get("health_path", "/"), on_state=on_state
        )
        if session_id:
            rt.emit(
                session_id,
                "step",
                {"name": "verify", "status": "done" if verification["ok"] else "failed"},
            )
            rt.emit(
                session_id,
                "success" if verification["ok"] else "error",
                {
                    "text": (
                        "برنامه با موفقیت دیپلوی شد."
                        if verification["ok"]
                        else "دیپلوی انجام شد ولی بررسی سلامت موفق نبود."
                    ),
                    "url": verification["url"],
                    "app": args["app"],
                    "steps": verification["steps"],
                },
            )
            if verification["ok"] and rt.watcher is not None:
                rt.watcher.watch(
                    args["app"], health_path=args.get("health_path", "/"), session_id=session_id
                )
        state = self._states.get(session_id)
        if state:
            state.stage = "verified" if verification["ok"] else "failed"
        return verification

    # -------------------------------------------------------------- helpers

    async def _app_exists(self, name: str) -> bool:
        try:
            await self._rt.client.get_project(name)
            return True
        except LiaraNotFound:
            return False

    async def _explain_analysis(self, analysis: ProjectAnalysis) -> str:
        fallback = (
            f"پروژه‌ی شما یک برنامه‌ی {analysis.platform} است که روی پورت {analysis.port} اجرا می‌شود"
            + (f" و به {', '.join(analysis.databases)} نیاز دارد" if analysis.databases else "")
            + (f". {len(analysis.env_keys)} متغیر محیطی پیدا شد." if analysis.env_keys else ".")
        )
        llm = self._rt.llm
        if llm is None or not llm.available:
            return fallback
        try:
            return await llm.summarize(
                str(analysis.to_dict()),
                instruction="You explain a project analysis to a non-technical site owner in two short Persian sentences. No jargon, no markdown.",
            )
        except Exception:  # noqa: BLE001
            return fallback

    def _require(self, session_id: str) -> WizardState:
        state = self._states.get(session_id)
        if state is None:
            raise KeyError("no deploy wizard in this session")
        return state


def resolve_project_path(path: str) -> str:
    """Relative paths are resolved against the repository root first (the backend usually
    runs from backend/), then against the current directory."""
    from pathlib import Path

    from app.config import REPO_ROOT

    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    for base in (REPO_ROOT / "data" / "projects", REPO_ROOT, Path.cwd()):
        if (base / candidate).is_dir():
            return str((base / candidate).resolve())
    return str((REPO_ROOT / candidate).resolve())


def _slug(path: str) -> str:
    import re
    from pathlib import Path

    name = re.sub(r"[^a-z0-9-]", "-", Path(path).resolve().name.lower()).strip("-")
    return (name or "app")[:30]


def _analysis_for(path: str, args: dict[str, Any]) -> ProjectAnalysis:
    analysis = ProjectAnalyzer(path).analyze()
    analysis.platform, analysis.port = args["platform"], int(args["port"])
    return analysis
