"""Secret masking. Applied before anything reaches logs, the audit trail or the LLM."""

from __future__ import annotations

import re
from typing import Any

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}")
_URL_CRED_RE = re.compile(r"(?i)(\w+://[^/\s:@]+):([^@\s/]+)@")
_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|passwd|pwd)(\s*[:=]\s*)(['\"]?)([^'\"\s,}]{6,})"
)
_QUERY_TOKEN_RE = re.compile(r"(?i)([?&](?:token|api_token|apikey|key)=)[^&\s]+")

SENSITIVE_ENV_HINTS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "KEY",
    "PRIVATE",
    "DSN",
    "DATABASE_URL",
    "URI",
)


def mask_text(text: str) -> str:
    if not text:
        return text
    text = _JWT_RE.sub("<jwt-redacted>", text)
    text = _BEARER_RE.sub("Bearer <redacted>", text)
    text = _URL_CRED_RE.sub(r"\1:<redacted>@", text)
    text = _QUERY_TOKEN_RE.sub(r"\1<redacted>", text)
    text = _KEY_RE.sub(r"\1\2\3<redacted>", text)
    return text


def is_sensitive_env(key: str) -> bool:
    upper = key.upper()
    return any(hint in upper for hint in SENSITIVE_ENV_HINTS)


def mask_env_value(key: str, value: str) -> str:
    if is_sensitive_env(key):
        return "<hidden>"
    return mask_text(value)


def mask_obj(obj: Any) -> Any:
    """Deep-mask strings inside dicts/lists. Env-like {key, value} pairs are masked by key."""
    if isinstance(obj, str):
        return mask_text(obj)
    if isinstance(obj, list):
        return [mask_obj(item) for item in obj]
    if isinstance(obj, dict):
        if "key" in obj and "value" in obj and isinstance(obj.get("key"), str):
            return {**obj, "value": mask_env_value(obj["key"], str(obj.get("value", "")))}
        return {
            k: ("<hidden>" if is_sensitive_env(str(k)) and isinstance(v, str) else mask_obj(v))
            for k, v in obj.items()
        }
    return obj
