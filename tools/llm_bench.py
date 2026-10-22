#!/usr/bin/env python3
"""Benchmark BoxAPI models for what the copilot needs: tool calling, JSON-schema output,
streaming, latency and Persian quality. Prints a table and a recommended config.

    python tools/llm_bench.py                       # all candidate models
    python tools/llm_bench.py --models gpt-6-astra gpt-5-mini
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

CANDIDATES = [
    "gpt-6.1-sol",
    "gpt-6-astra",
    "gpt-6-luna",
    "gpt-6-sol",
    "gpt-5-mini",
    "gpt-5.6-luna",
    "gpt-5.6-terra",
    "gpt-5.6-sol",
    "gpt-5.4-mini",
    "gpt-5.3-codex",
]
TOOL = {
    "type": "function",
    "function": {
        "name": "get_logs",
        "description": "Fetch recent logs of an app",
        "parameters": {
            "type": "object",
            "properties": {"app": {"type": "string"}, "minutes": {"type": "integer"}},
            "required": ["app"],
        },
    },
}
SCHEMA_PROMPT = 'Return only JSON: {"intent": "deploy|investigate|status", "app": string}. Message: "سایت shop-demo کند شده"'


def _load_env() -> None:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


async def bench(client, model: str) -> dict[str, object]:  # type: ignore[no-untyped-def]
    from app.llm.gateway import compat_create

    row: dict[str, object] = {"model": model}
    # 1. tool calling
    t = time.perf_counter()
    try:
        r = await compat_create(
            client,
            dict(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": "Show me the last 5 minutes of logs for app shop-demo",
                    }
                ],
                tools=[TOOL],
                temperature=0,
                max_tokens=200,
            ),
        )
        calls = r.choices[0].message.tool_calls or []
        row["tool_call"] = (
            bool(calls)
            and calls[0].function.name == "get_logs"
            and "shop-demo" in (calls[0].function.arguments or "")
        )
        row["tool_latency_s"] = round(time.perf_counter() - t, 2)
    except Exception as exc:  # noqa: BLE001
        row["tool_call"], row["tool_error"] = False, str(exc)[:300]
    # 2. JSON output
    t = time.perf_counter()
    try:
        r = await compat_create(
            client,
            dict(
                model=model,
                messages=[{"role": "user", "content": SCHEMA_PROMPT}],
                temperature=0,
                max_tokens=120,
            ),
        )
        text = r.choices[0].message.content or ""
        start, end = text.find("{"), text.rfind("}")
        parsed = json.loads(text[start : end + 1])
        row["json"] = parsed.get("intent") == "investigate" and parsed.get("app") == "shop-demo"
        row["json_latency_s"] = round(time.perf_counter() - t, 2)
    except Exception as exc:  # noqa: BLE001
        row["json"], row["json_error"] = False, str(exc)[:300]
    # 3. streaming
    try:
        chunks = 0
        async for _ in await compat_create(
            client,
            dict(
                model=model,
                messages=[{"role": "user", "content": "Count from 1 to 5."}],
                stream=True,
                max_tokens=40,
            ),
        ):
            chunks += 1
        row["streaming"] = chunks > 1
    except Exception as exc:  # noqa: BLE001
        row["streaming"], row["stream_error"] = False, str(exc)[:300]
    # 4. Persian quality (manual read)
    try:
        r = await compat_create(
            client,
            dict(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": "در دو جمله‌ی ساده به صاحب یک سایت توضیح بده نشت حافظه یعنی چه.",
                    }
                ],
                temperature=0.3,
                max_tokens=120,
            ),
        )
        row["persian_sample"] = (
            (r.choices[0].message.content or "").strip().replace("\n", " ")[:140]
        )
    except Exception as exc:  # noqa: BLE001
        row["persian_sample"] = f"error: {str(exc)[:300]}"
    return row


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=CANDIDATES)
    args = parser.parse_args()
    _load_env()
    key = os.environ.get("BOXAPI_API_KEY", "")
    if not key:
        print("BOXAPI_API_KEY not set (.env). Aborting.")
        return 1
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=key,
        base_url=os.environ.get("LLM_BASE_URL", "https://ai.boxapi.ir/ai/v1"),
        timeout=60,
        max_retries=0,
    )
    rows = [await bench(client, m) for m in args.models]
    print(f"{'model':16} {'tools':6} {'json':6} {'stream':7} {'t_tool':7} {'t_json':7}  persian")
    for r in rows:
        print(
            f"{r['model']:16} {str(r.get('tool_call')):6} {str(r.get('json')):6} {str(r.get('streaming')):7} {str(r.get('tool_latency_s', '-')):7} {str(r.get('json_latency_s', '-')):7}  {r.get('persian_sample', '')[:70]}"
        )
    strong = next(
        (
            r["model"]
            for r in rows
            if r.get("tool_call") and r.get("json") and "mini" not in str(r["model"])
        ),
        None,
    )
    small = next((r["model"] for r in rows if r.get("json") and "mini" in str(r["model"])), None)
    print("\nRecommended .env:")
    print(f"LLM_STRONG_MODEL={strong or 'gpt-6-astra'}")
    print(f"LLM_SMALL_MODEL={small or 'gpt-5-mini'}")
    print(f"LLM_ACTION_PROTOCOL={'tools' if strong else 'json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
