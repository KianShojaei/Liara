"""Project intake: upload an archive, clone a Git repository, or register a local folder.

Projects live under <repo>/data/projects/<name> (gitignored) so the deploy wizard can
analyze and deploy them without the user touching a terminal.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import REPO_ROOT
from app.deploy.analyzer import ProjectAnalyzer
from app.liara.redaction import mask_text

router = APIRouter(prefix="/api/projects")

PROJECTS_DIR = REPO_ROOT / "data" / "projects"
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
NAME_RE = re.compile(r"[^a-z0-9-]+")
GIT_URL_RE = re.compile(r"^(https?://|git@|file://)[\w.@:/\-~]+$")


def _slug(raw: str) -> str:
    slug = NAME_RE.sub("-", raw.lower()).strip("-")[:40]
    if not slug:
        raise HTTPException(400, "invalid project name")
    return slug


def _project_dir(name: str, *, fresh: bool = True) -> Path:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    target = PROJECTS_DIR / name
    if fresh and target.exists():
        shutil.rmtree(target)
    return target


def _safe_members(root: Path, names: list[str]) -> None:
    """Zip-slip guard: every entry must stay inside the target directory."""
    for name in names:
        if not (root / name).resolve().is_relative_to(root.resolve()):
            raise HTTPException(400, f"unsafe path in archive: {name}")


def _strip_single_root(target: Path) -> None:
    """GitHub-style archives wrap everything in one folder; unwrap it."""
    entries = [e for e in target.iterdir() if e.name != "__MACOSX"]
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for child in inner.iterdir():
            shutil.move(str(child), str(target / child.name))
        inner.rmdir()


def _describe(path: Path) -> dict[str, Any]:
    try:
        analysis = ProjectAnalyzer(path).analyze().to_dict()
    except Exception as exc:  # noqa: BLE001
        analysis = {"error": mask_text(str(exc))}
    return {"name": path.name, "path": str(path), "analysis": analysis}


@router.get("")
def list_projects() -> list[dict[str, Any]]:
    if not PROJECTS_DIR.exists():
        return []
    return [_describe(p) for p in sorted(PROJECTS_DIR.iterdir()) if p.is_dir()]


@router.post("/upload")
async def upload_project(file: UploadFile = File(...), name: str = Form("")) -> dict[str, Any]:
    filename = file.filename or "project.zip"
    slug = _slug(name or re.sub(r"\.(zip|tar\.gz|tgz)$", "", filename, flags=re.I))
    target = _project_dir(slug)
    target.mkdir(parents=True)
    archive = target.parent / f".{slug}.upload"
    size = 0
    with archive.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                fh.close()
                archive.unlink(missing_ok=True)
                shutil.rmtree(target, ignore_errors=True)
                raise HTTPException(413, "archive larger than 250MB")
            fh.write(chunk)
    try:
        await asyncio.to_thread(_extract, archive, target, filename)
    except HTTPException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    finally:
        archive.unlink(missing_ok=True)
    return _describe(target)


def _extract(archive: Path, target: Path, filename: str) -> None:
    lower = filename.lower()
    if lower.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            _safe_members(target, zf.namelist())
            zf.extractall(target)
    elif lower.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive, "r:gz") as tf:
            _safe_members(target, tf.getnames())
            tf.extractall(target)
    else:
        raise HTTPException(400, "upload a .zip or .tar.gz archive")
    _strip_single_root(target)


class GitImport(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    branch: str = ""
    name: str = ""


@router.post("/git")
async def import_git(body: GitImport) -> dict[str, Any]:
    if not GIT_URL_RE.match(body.url.strip()):
        raise HTTPException(400, "unsupported git URL")
    if (
        "@" in body.url
        and "://" in body.url
        and ":" in body.url.split("://", 1)[1].split("/", 1)[0]
    ):
        raise HTTPException(
            400, "do not put credentials in the URL; use a public repo or an SSH key"
        )
    repo_name = body.url.rstrip("/").split("/")[-1].removesuffix(".git")
    slug = _slug(body.name or repo_name)
    target = _project_dir(slug)
    args = ["git", "clone", "--depth", "1"]
    if body.branch:
        args += ["--branch", body.branch]
    args += [body.url.strip(), str(target)]
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    try:
        out, _ = await asyncio.wait_for(process.communicate(), timeout=300)
    except TimeoutError:
        process.kill()
        shutil.rmtree(target, ignore_errors=True)
        raise HTTPException(504, "git clone timed out") from None
    if process.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)
        raise HTTPException(
            400, "git clone failed: " + mask_text(out.decode(errors="ignore"))[-400:]
        )
    return _describe(target)


class LocalPath(BaseModel):
    path: str


@router.post("/local")
def register_local(body: LocalPath) -> dict[str, Any]:
    from app.deploy.wizard import resolve_project_path

    path = Path(resolve_project_path(body.path))
    if not path.is_dir():
        raise HTTPException(404, f"folder not found: {path}")
    return _describe(path)


@router.delete("/{name}")
def delete_project(name: str) -> dict[str, Any]:
    target = PROJECTS_DIR / _slug(name)
    if not target.exists():
        raise HTTPException(404, "project not found")
    shutil.rmtree(target)
    return {"deleted": name}
