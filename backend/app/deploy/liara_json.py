"""Generate / update liara.json (VERIFIED fields: app, platform, port, build location)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.deploy.analyzer import ProjectAnalysis


def build_liara_json(
    analysis: ProjectAnalysis, app_name: str, *, build_location: str = "iran"
) -> dict[str, Any]:
    config: dict[str, Any] = {**analysis.existing_liara_json}
    config.update(
        {
            "app": app_name,
            "platform": analysis.platform,
            "port": analysis.port,
            "build": {**config.get("build", {}), "location": build_location},
        }
    )
    return config


def write_liara_json(path: str | Path, config: dict[str, Any]) -> Path:
    target = Path(path) / "liara.json"
    target.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
