"""Runtime configuration. Secrets come only from the environment / a local .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", Path(".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Liara
    liara_api_token: str = ""
    liara_team_id: str = ""
    liara_api_base: str = "https://api.liara.ir"
    liara_dns_base: str = "https://dns-service.liara.ir"
    liara_cli_bin: str = "liara"

    # LLM
    boxapi_api_key: str = ""
    llm_base_url: str = "https://ai.boxapi.ir/ai/v1"
    llm_strong_model: str = "gpt-6-luna"
    llm_small_model: str = "gpt-5.4-mini"
    llm_embedding_model: str = "text-embedding-3-small"
    llm_action_protocol: Literal["tools", "json"] = "tools"
    llm_timeout_seconds: float = 60.0

    # Runtime
    copilot_mode: Literal["live", "mock"] = "mock"
    mock_liara_base: str = "http://127.0.0.1:8081"
    copilot_db_path: str = "./data/copilot.sqlite"
    copilot_dry_run: bool = False
    copilot_app_allowlist: str = ""
    copilot_cost_guard_hourly: float = 5000.0
    copilot_enable_guarded: bool = False
    copilot_host: str = "127.0.0.1"
    copilot_port: int = 8000

    # Watcher
    watcher_enabled: bool = True
    watcher_interval_seconds: int = Field(default=20, ge=5)

    # Coding-agent bridge
    coding_agent_cmd: str = ""

    @property
    def api_base(self) -> str:
        return self.mock_liara_base if self.copilot_mode == "mock" else self.liara_api_base

    @property
    def dns_base(self) -> str:
        return f"{self.mock_liara_base}/dns" if self.copilot_mode == "mock" else self.liara_dns_base

    @property
    def app_allowlist(self) -> set[str]:
        return {a.strip() for a in self.copilot_app_allowlist.split(",") if a.strip()}

    @property
    def llm_available(self) -> bool:
        return bool(self.boxapi_api_key)

    @property
    def db_path(self) -> Path:
        path = Path(self.copilot_db_path)
        if not path.is_absolute():
            path = REPO_ROOT / "backend" / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
