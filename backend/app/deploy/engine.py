"""DeployEngine: run a deploy and stream its progress.

Primary path (live): the official CLI, `liara deploy --app .. --port .. --platform .. --path ..`
(flags VERIFIED from the CLI README v9.6.0). The CLI handles packaging, ignore rules and
build logs. Fallback path (mock mode, or CLI not installed): raw API `POST /v2/.../sources`
(multipart tar.gz) then `POST /v2/.../releases` (VERIFIED), which is what the CLI does
internally.
"""

from __future__ import annotations

import asyncio
import io
import logging
import shutil
import tarfile
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.liara.client import LiaraClient
from app.liara.redaction import mask_text

log = logging.getLogger("copilot.deploy")

LineSink = Callable[[str], Awaitable[None] | None]
IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    ".next",
    ".cache",
    ".idea",
    ".vscode",
}
IGNORED_FILES = {".env", ".env.local", ".env.production"}
MAX_SOURCE_BYTES = 250 * 1024 * 1024


class DeployEngine:
    def __init__(
        self,
        client: LiaraClient,
        *,
        cli_bin: str = "liara",
        api_token: str = "",
        team_id: str = "",
        prefer_cli: bool = True,
    ):
        self._client = client
        self._cli_bin = cli_bin
        self._api_token = api_token
        self._team_id = team_id
        self._prefer_cli = prefer_cli

    @property
    def cli_available(self) -> bool:
        return (
            self._prefer_cli and shutil.which(self._cli_bin) is not None and bool(self._api_token)
        )

    async def deploy(
        self,
        *,
        project_path: str,
        app: str,
        port: int,
        platform: str,
        message: str = "",
        on_line: LineSink | None = None,
    ) -> dict[str, Any]:
        emit = on_line or (lambda _line: None)
        if self.cli_available:
            return await self._deploy_with_cli(project_path, app, port, platform, message, emit)
        await _maybe_await(
            emit("CLI not available or mock mode: using the raw API (sources + releases).")
        )
        return await self._deploy_with_api(project_path, app, port, platform, emit)

    # ------------------------------------------------------------------ CLI

    async def _deploy_with_cli(
        self, project_path: str, app: str, port: int, platform: str, message: str, emit: LineSink
    ) -> dict[str, Any]:
        args = [
            self._cli_bin,
            "deploy",
            "--app",
            app,
            "--port",
            str(port),
            "--platform",
            platform,
            "--path",
            project_path,
            "--api-token",
            self._api_token,
            "--no-app-logs",
        ]
        if self._team_id:
            args += ["--team-id", self._team_id]
        if message:
            args += ["-m", message]
        await _maybe_await(
            emit(
                f"$ liara deploy --app {app} --port {port} --platform {platform} --path {project_path}"
            )
        )
        process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        lines: list[str] = []
        assert process.stdout is not None
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            line = mask_text(raw.decode(errors="ignore").rstrip())
            if line:
                lines.append(line)
                await _maybe_await(emit(line))
        code = await process.wait()
        if code != 0:
            raise RuntimeError(f"liara deploy exited with {code}: {' | '.join(lines[-5:])}")
        releases = await self._client.releases(app, count=1)
        release_id = releases.releases[0].id if releases.releases else ""
        return {"method": "cli", "release_id": release_id, "lines": lines[-50:]}

    # ------------------------------------------------------------------ API

    async def _deploy_with_api(
        self, project_path: str, app: str, port: int, platform: str, emit: LineSink
    ) -> dict[str, Any]:
        archive = await asyncio.to_thread(self._pack, Path(project_path))
        try:
            await _maybe_await(emit(f"Packed sources: {archive.stat().st_size // 1024} KB"))
            source_id = await self._client.upload_source(app, archive)
            await _maybe_await(emit(f"Source uploaded (sourceID={source_id[:8]}…)"))
            release_id = await self._client.create_release(app, source_id, port, platform)
            await _maybe_await(emit(f"Release created (releaseID={release_id[:8]}…), building…"))
            return {"method": "api", "release_id": release_id, "source_id": source_id}
        finally:
            archive.unlink(missing_ok=True)

    @staticmethod
    def _pack(project: Path) -> Path:
        if not project.is_dir():
            raise FileNotFoundError(project)
        target = Path(tempfile.mkstemp(suffix=".tar.gz")[1])
        total = 0
        with tarfile.open(target, "w:gz") as tar:
            for file in project.rglob("*"):
                rel = file.relative_to(project)
                if any(part in IGNORED_DIRS for part in rel.parts) or rel.name in IGNORED_FILES:
                    continue
                if file.is_file():
                    total += file.stat().st_size
                    if total > MAX_SOURCE_BYTES:
                        raise RuntimeError(
                            "source folder is larger than 250MB; add a .gitignore or deploy with the CLI"
                        )
                    tar.add(file, arcname=str(rel))
        return target

    # ------------------------------------------------------------ rollback

    async def redeploy_release(
        self, app: str, release_id: str, emit: LineSink | None = None
    ) -> dict[str, Any]:
        """Rollback = redeploy a previous release's source. The API has no 'rollback' endpoint;
        the CLI/console do it by re-releasing the same source. Whether /v2 releases accepts a
        previous sourceID is ASSUMED -> the verifier confirms the outcome either way."""
        emit = emit or (lambda _l: None)
        release = await self._client.get_release(release_id)
        if not release.source_available:
            raise RuntimeError(
                "source of that release is no longer available; redeploy from the project folder instead"
            )
        if not release.source_id:
            raise RuntimeError(
                "release has no sourceID in the API response (TODO(verify)); use a fresh deploy"
            )
        new_id = await self._client.create_release(
            app, release.source_id, release.port or 3000, release.project_type
        )
        await _maybe_await(
            emit(f"Re-released source of {release.tag or release_id[:8]} as {new_id[:8]}…")
        )
        return {"method": "api", "release_id": new_id, "rolled_back_to": release_id}


async def _maybe_await(value: Any) -> None:
    if asyncio.iscoroutine(value):
        await value


def pack_preview(project: Path) -> list[str]:
    """Names that would be uploaded (for the UI preview)."""
    buf = io.StringIO()
    for file in sorted(project.rglob("*")):
        rel = file.relative_to(project)
        if (
            any(part in IGNORED_DIRS for part in rel.parts)
            or rel.name in IGNORED_FILES
            or not file.is_file()
        ):
            continue
        buf.write(str(rel) + "\n")
    return buf.getvalue().splitlines()[:200]
