"""ProjectAnalyzer: inspect a local project folder and describe what it needs.

Platform detection mirrors the official CLI (src/utils/detect-platform.ts, VERIFIED):
dotnet, laravel, php, django, flask, python, next, angular, vue, react, node,
wordpress, go, docker, static.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.liara.redaction import is_sensitive_env

DEFAULT_PORTS = {
    "node": 3000,
    "next": 3000,
    "react": 80,
    "vue": 80,
    "angular": 80,
    "static": 80,
    "django": 8000,
    "flask": 5000,
    "python": 8000,
    "laravel": 80,
    "php": 80,
    "dotnet": 80,
    "go": 8080,
    "docker": 80,
    "wordpress": 80,
}
DB_HINTS = {
    "postgres": ("pg", "psycopg", "psycopg2", "asyncpg", "sqlalchemy", "prisma", "postgresql"),
    "mysql": ("mysql", "mysql2", "pymysql", "mysqlclient", "mariadb"),
    "mongodb": ("mongoose", "mongodb", "pymongo", "motor"),
    "redis": ("redis", "ioredis", "aioredis", "bull"),
}
HEALTH_CANDIDATES = ("/health", "/healthz", "/api/health", "/")


@dataclass
class ProjectAnalysis:
    path: str
    platform: str = "static"
    platform_reason: str = ""
    port: int = 80
    port_source: str = "default"
    start_command: str = ""
    env_keys: list[str] = field(default_factory=list)
    secret_env_keys: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    has_dockerfile: bool = False
    has_liara_json: bool = False
    existing_liara_json: dict[str, Any] = field(default_factory=dict)
    health_path: str = "/"
    size_hint: str = "small"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProjectAnalyzer:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    def analyze(self) -> ProjectAnalysis:
        if not self.path.is_dir():
            raise FileNotFoundError(f"project folder not found: {self.path}")
        analysis = ProjectAnalysis(path=str(self.path))
        self._detect_platform(analysis)
        self._detect_port(analysis)
        self._detect_envs(analysis)
        self._detect_databases(analysis)
        self._detect_health_path(analysis)
        self._read_liara_json(analysis)
        self._size_hint(analysis)
        return analysis

    # ----------------------------------------------------------- platform

    def _detect_platform(self, a: ProjectAnalysis) -> None:
        p = self.path
        a.has_dockerfile = (p / "Dockerfile").exists()
        if any(p.glob("*.csproj")):
            a.platform, a.platform_reason = "dotnet", "*.csproj found"
        elif (p / "composer.json").exists():
            composer = self._json(p / "composer.json")
            deps = {**composer.get("require", {}), **composer.get("require-dev", {})}
            a.platform = "laravel" if "laravel/framework" in deps else "php"
            a.platform_reason = "composer.json" + (
                " with laravel/framework" if a.platform == "laravel" else ""
            )
        elif (
            (p / "requirements.txt").exists()
            or (p / "pyproject.toml").exists()
            or (p / "Pipfile").exists()
        ):
            reqs = self._python_requirements()
            if "django" in reqs:
                a.platform, a.platform_reason = "django", "django in requirements"
            elif "flask" in reqs:
                a.platform, a.platform_reason = "flask", "flask in requirements"
            else:
                a.platform, a.platform_reason = "python", "python project (fastapi/other)"
        elif (p / "package.json").exists():
            pkg = self._json(p / "package.json")
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "next" in deps:
                a.platform, a.platform_reason = "next", "next in package.json"
            elif "@angular/core" in deps:
                a.platform, a.platform_reason = "angular", "@angular/core in package.json"
            elif "vue" in deps and "nuxt" not in deps:
                a.platform, a.platform_reason = "vue", "vue in package.json"
            elif (
                "react" in deps
                and "express" not in deps
                and ("react-scripts" in deps or "vite" in deps)
            ):
                a.platform, a.platform_reason = "react", "react (SPA) in package.json"
            else:
                a.platform, a.platform_reason = "node", "package.json (server side node)"
            a.start_command = (pkg.get("scripts") or {}).get("start", "")
        elif (p / "wp-config.php").exists() or (p / "wp-config-sample.php").exists():
            a.platform, a.platform_reason = "wordpress", "wp-config found"
        elif (p / "go.mod").exists():
            a.platform, a.platform_reason = "go", "go.mod found"
        elif a.has_dockerfile:
            a.platform, a.platform_reason = "docker", "Dockerfile only"
        else:
            a.platform, a.platform_reason = "static", "no manifest found, treating as static site"
        if a.has_dockerfile and a.platform != "docker":
            a.warnings.append(
                "Dockerfile exists; Liara will still use the detected platform unless platform=docker is chosen."
            )

    # --------------------------------------------------------------- port

    def _detect_port(self, a: ProjectAnalysis) -> None:
        a.port = DEFAULT_PORTS.get(a.platform, 80)
        candidates: list[Path] = []
        for pattern in (
            "*.js",
            "*.ts",
            "*.mjs",
            "src/*.js",
            "src/*.ts",
            "app.py",
            "main.py",
            "*/main.py",
            "manage.py",
            "server/*.js",
        ):
            candidates.extend(self.path.glob(pattern))
        for file in candidates[:40]:
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")[:20000]
            except OSError:
                continue
            match = re.search(r"(?:PORT\s*\|\|\s*|port\s*[:=]\s*|listen\(\s*)(\d{2,5})", text)
            if match:
                a.port, a.port_source = int(match.group(1)), file.name
                break
        if a.has_dockerfile:
            expose = re.search(
                r"EXPOSE\s+(\d+)", (self.path / "Dockerfile").read_text(errors="ignore")
            )
            if expose:
                a.port, a.port_source = int(expose.group(1)), "Dockerfile EXPOSE"

    # --------------------------------------------------------------- envs

    def env_defaults(self) -> tuple[dict[str, str], dict[str, str]]:
        """Values to prefill the env form: .env first (real values), then .env.example
        defaults. Returned to the UI on demand only; never written to the timeline."""
        values: dict[str, str] = {}
        sources: dict[str, str] = {}
        for name in (".env.example", ".env.sample", ".env.template", ".env.local", ".env"):
            file = self.path / name
            if not file.exists():
                continue
            for line in file.read_text(errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = (part.strip() for part in line.split("=", 1))
                value = value.strip("'\"")
                if value or key not in values:
                    values[key], sources[key] = value, name
        return values, sources

    def platform_version(self) -> str | None:
        """Runtime version hint (node major from package.json engines / .nvmrc; python from
        runtime.txt or .python-version), mirroring the CLI's get-platform-version."""
        pkg = (
            self._json(self.path / "package.json") if (self.path / "package.json").exists() else {}
        )
        node = str((pkg.get("engines") or {}).get("node", ""))
        match = re.search(r"(\d+)", node)
        if match:
            return match.group(1)
        for name in (".nvmrc", ".node-version"):
            if (self.path / name).exists():
                match = re.search(r"(\d+)", (self.path / name).read_text(errors="ignore"))
                if match:
                    return match.group(1)
        for name in ("runtime.txt", ".python-version"):
            if (self.path / name).exists():
                match = re.search(r"(\d+\.\d+)", (self.path / name).read_text(errors="ignore"))
                if match:
                    return match.group(1)
        return None

    def _detect_envs(self, a: ProjectAnalysis) -> None:
        keys: list[str] = []
        for name in (".env.example", ".env.sample", ".env.template"):
            file = self.path / name
            if file.exists():
                for line in file.read_text(errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        keys.append(line.split("=", 1)[0].strip())
        if not keys:
            for file in list(self.path.rglob("*.js"))[:60] + list(self.path.rglob("*.py"))[:60]:
                if "node_modules" in file.parts or ".venv" in file.parts:
                    continue
                text = file.read_text(encoding="utf-8", errors="ignore")
                keys.extend(re.findall(r"process\.env\.([A-Z][A-Z0-9_]+)", text))
                keys.extend(
                    re.findall(r"os\.(?:environ(?:\.get)?|getenv)\(\s*['\"]([A-Z][A-Z0-9_]+)", text)
                )
        a.env_keys = sorted({k for k in keys if k not in ("PORT", "NODE_ENV")})
        a.secret_env_keys = [k for k in a.env_keys if is_sensitive_env(k)]
        if (self.path / ".env").exists():
            a.warnings.append(
                ".env file present in the folder; it will NOT be uploaded, set values through the copilot instead."
            )

    # ---------------------------------------------------------- databases

    def _detect_databases(self, a: ProjectAnalysis) -> None:
        deps: set[str] = set()
        pkg = (
            self._json(self.path / "package.json") if (self.path / "package.json").exists() else {}
        )
        deps.update((pkg.get("dependencies") or {}).keys())
        deps.update(self._python_requirements())
        found = [
            db
            for db, hints in DB_HINTS.items()
            if any(
                dep == h or dep.startswith(h + "-") or dep.startswith(h + "_")
                for dep in deps
                for h in hints
            )
        ]
        for key in a.env_keys:
            upper = key.upper()
            if "DATABASE_URL" in upper or "POSTGRES" in upper:
                found.append("postgres")
            if "MONGO" in upper:
                found.append("mongodb")
            if "REDIS" in upper:
                found.append("redis")
            if "MYSQL" in upper:
                found.append("mysql")
        a.databases = sorted(set(found))

    # -------------------------------------------------------------- health

    def _detect_health_path(self, a: ProjectAnalysis) -> None:
        for file in (
            list(self.path.rglob("*.js"))[:80]
            + list(self.path.rglob("*.py"))[:80]
            + list(self.path.rglob("*.ts"))[:80]
        ):
            if "node_modules" in file.parts:
                continue
            text = file.read_text(encoding="utf-8", errors="ignore")
            for candidate in HEALTH_CANDIDATES[:-1]:
                if f"'{candidate}'" in text or f'"{candidate}"' in text:
                    a.health_path = candidate
                    return
        a.health_path = "/"

    def _read_liara_json(self, a: ProjectAnalysis) -> None:
        file = self.path / "liara.json"
        if file.exists():
            a.has_liara_json = True
            a.existing_liara_json = self._json(file)
            if a.existing_liara_json.get("port"):
                a.port, a.port_source = int(a.existing_liara_json["port"]), "liara.json"
            if a.existing_liara_json.get("platform"):
                a.platform, a.platform_reason = a.existing_liara_json["platform"], "liara.json"

    def _size_hint(self, a: ProjectAnalysis) -> None:
        heavy = {"next", "django", "laravel", "dotnet", "wordpress"}
        a.size_hint = "medium" if a.platform in heavy or a.databases else "small"

    # ------------------------------------------------------------ helpers

    def _json(self, file: Path) -> dict[str, Any]:
        try:
            return json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _python_requirements(self) -> set[str]:
        names: set[str] = set()
        req = self.path / "requirements.txt"
        if req.exists():
            for line in req.read_text(errors="ignore").splitlines():
                line = line.strip().lower()
                if line and not line.startswith(("#", "-")):
                    names.add(re.split(r"[<>=!\[ ;]", line)[0])
        pyproject = self.path / "pyproject.toml"
        if pyproject.exists():
            names.update(
                m.lower()
                for m in re.findall(
                    r'"([A-Za-z0-9_-]+)[<>=~\[]', pyproject.read_text(errors="ignore")
                )
            )
        return names
