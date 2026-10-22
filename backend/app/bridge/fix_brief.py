"""CodingAgentBridge: turn an investigated incident into a FixBrief a coding agent can act on.

Adapters:
  * MCP tools get_incident / get_fix_brief / submit_fix_result (see app/mcp_server.py)
  * CODING_AGENT_CMD: a configurable command run on branch fix/incident-<id> with the brief
    path in $FIX_BRIEF; whatever it writes to stdout is treated as a unified diff proposal
  * deterministic demo-patch mode: a patch file supplied by the demo, so the demo never
    depends on a live agent
Any returned patch is only *proposed*; applying it + redeploying is a T2 `submit_fix`.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from app.liara.redaction import mask_text


def build_fix_brief(incident: dict[str, Any]) -> dict[str, Any]:
    evidence = incident.get("evidence") or {}
    hypotheses = incident.get("hypotheses") or []
    top = hypotheses[0] if hypotheses else {}
    findings = evidence.get("findings") or []
    frames = next(
        (
            f["evidence"].get("stack_frames")
            for f in findings
            if f.get("evidence", {}).get("stack_frames")
        ),
        [],
    )
    error_cluster = next(
        (f["evidence"].get("clusters") for f in findings if f["kind"] == "error_burst"), []
    )
    suspected_files = sorted({_frame_file(fr) for fr in frames if _frame_file(fr)})
    return {
        "incident_id": incident["id"],
        "app": incident["app_name"],
        "opened_at": incident["opened_at"],
        "symptom": incident.get("summary") or top.get("cause", ""),
        "timeline": [e["text"] for e in evidence.get("events", [])][-10:],
        "evidence": {
            "findings": [
                {"kind": f["kind"], "title": f["title"], "evidence": f.get("evidence")}
                for f in findings
            ],
            "error_clusters": error_cluster,
            "stack_frames": frames,
            "releases": evidence.get("releases", [])[:3],
            "probe": evidence.get("probe"),
        },
        "suspected_cause": top.get("cause", ""),
        "confidence": top.get("confidence", 0),
        "suspected_files": suspected_files,
        "fix_direction": _fix_direction(top.get("id", ""), findings),
        "acceptance_criteria": [
            "health path returns HTTP 200 for 3 consecutive probes",
            "no stderr burst for 2 minutes after deploy",
            "memory stays flat (slope < 1MB/min) for 5 minutes"
            if top.get("id") == "memory_leak"
            else "error cluster count drops to zero",
            "all existing tests pass",
        ],
        "constraints": [
            "do not change the public API",
            "keep the change minimal and reviewable",
            "never commit secrets; env vars come from Liara settings",
        ],
    }


def _frame_file(frame: str) -> str:
    import re

    match = re.search(r"\(?(/[^:()\s]+|[A-Za-z0-9_./-]+\.(?:js|ts|py|php|go))[:\d]*", frame)
    if not match:
        return ""
    path = match.group(1)
    return path.replace("/app/", "", 1) if path.startswith("/app/") else path


def _fix_direction(hypothesis_id: str, findings: list[dict[str, Any]]) -> str:
    return {
        "memory_leak": "Find unbounded in-memory growth (caches, arrays, listeners) on the hot handler; bound it or move it out of process.",
        "app_bug": "Fix the exception at the top stack frame; add a null/undefined guard and a regression test.",
        "missing_env": "Read the variable with a clear error at startup and document it in .env.example; the value itself is set in Liara.",
        "bad_release": "Diff the latest release against the previous READY one; revert the offending change or fix forward.",
        "under_provisioned": "Profile the slow path; add caching or pagination before resizing the plan.",
        "memory_limit": "Reduce baseline memory (lazy-load, streaming) or justify a bigger plan.",
        "crash_loop": "Check startup: port binding, required env, migrations; make startup fail loudly with a clear message.",
    }.get(hypothesis_id, "Investigate the top finding and propose a minimal fix.")


def write_fix_brief(brief: dict[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"fix-brief-{brief['incident_id']}.json"
    target.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


async def run_coding_agent(
    command: str, brief_path: Path, project_path: str, incident_id: str, *, timeout: float = 600
) -> dict[str, Any]:
    """Runs CODING_AGENT_CMD inside the project on a fresh branch; stdout is the proposed diff."""
    branch = f"fix/incident-{incident_id}"
    env = {**os.environ, "FIX_BRIEF": str(brief_path), "FIX_BRANCH": branch}
    subprocess.run(
        ["git", "checkout", "-B", branch], cwd=project_path, check=False, capture_output=True
    )
    process = await asyncio.create_subprocess_shell(
        command,
        cwd=project_path,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        return {"ok": False, "error": "coding agent timed out", "branch": branch}
    diff = subprocess.run(
        ["git", "diff"], cwd=project_path, capture_output=True, text=True, check=False
    ).stdout
    return {
        "ok": process.returncode == 0,
        "branch": branch,
        "patch": diff or out.decode(errors="ignore"),
        "log": mask_text(err.decode(errors="ignore")[-2000:]),
    }


def apply_patch(project_path: str, patch: str) -> dict[str, Any]:
    """Applies a unified diff with `git apply` (dry-run first). Returns files touched."""
    if not patch.strip():
        return {"applied": False, "files": [], "reason": "empty patch"}
    check = subprocess.run(
        ["git", "apply", "--check", "-"],
        cwd=project_path,
        input=patch,
        text=True,
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        raise RuntimeError(f"patch does not apply: {check.stderr.strip()[:400]}")
    subprocess.run(
        ["git", "apply", "-"],
        cwd=project_path,
        input=patch,
        text=True,
        check=True,
        capture_output=True,
    )
    files = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=project_path,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    return {"applied": True, "files": files}


def load_demo_patch(project_path: str) -> str:
    """Deterministic demo mode: demo/shop-demo/patches/fix-memory-leak.patch if present."""
    candidate = Path(project_path) / "patches" / "fix-memory-leak.patch"
    return candidate.read_text(encoding="utf-8") if candidate.exists() else ""
