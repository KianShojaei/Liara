"""LLMGateway: provider-agnostic OpenAI-compatible client (BoxAPI by default).

* model routing: `strong` for planning/diagnosis, `small` for routing/summaries
* two action protocols behind one interface: native tool calling, or a JSON action per turn
  (for models whose tool calling is unreliable; see tools/llm_bench.py)
* JSON-schema outputs with validation + one repair round
* retries with timeouts, token accounting, and redaction of every string that goes out
* degrades gracefully: without a key, `available` is False and callers use rule-based paths
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.liara.redaction import mask_obj, mask_text

log = logging.getLogger("copilot.llm")

ModelRole = Literal["strong", "small"]
MAX_ATTEMPTS = 2


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    def add(self, usage: Any) -> None:
        self.calls += 1
        if usage is None:
            return
        self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
        self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = ""


@dataclass
class ChatTurn:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None


class LLMGateway:
    def __init__(self, settings: Settings):
        self._settings = settings
        self.usage = Usage()
        self._client: Any = None
        if settings.llm_available:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=settings.boxapi_api_key,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout_seconds,
                max_retries=1,
            )

    @property
    def available(self) -> bool:
        return self._client is not None

    def model(self, role: ModelRole) -> str:
        return (
            self._settings.llm_strong_model if role == "strong" else self._settings.llm_small_model
        )

    # ---------------------------------------------------------------- chat

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        role: ModelRole = "small",
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> ChatTurn:
        if not self.available:
            raise RuntimeError("LLM not configured (BOXAPI_API_KEY missing)")
        safe_messages = [
            {
                **m,
                "content": mask_text(m["content"])
                if isinstance(m.get("content"), str)
                else m.get("content"),
            }
            for m in messages
        ]
        kwargs: dict[str, Any] = {
            "model": self.model(role),
            "messages": safe_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        use_native_tools = bool(tools) and self._settings.llm_action_protocol == "tools"
        if use_native_tools:
            kwargs["tools"] = tools
        elif tools:
            kwargs["messages"] = [
                safe_messages[0],
                {"role": "system", "content": _json_protocol_prompt(tools)},
                *safe_messages[1:],
            ]

        last_error: Exception | None = None
        for _ in range(MAX_ATTEMPTS):
            try:
                response = await self._client.chat.completions.create(**kwargs)
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                log.warning("LLM call failed: %s", mask_text(str(exc)))
        else:
            raise RuntimeError(f"LLM unavailable: {mask_text(str(last_error))}")

        self.usage.add(getattr(response, "usage", None))
        choice = response.choices[0].message
        turn = ChatTurn(content=choice.content or "", raw=response)
        if use_native_tools and getattr(choice, "tool_calls", None):
            for call in choice.tool_calls:
                turn.tool_calls.append(
                    ToolCall(call.function.name, _loads(call.function.arguments), call.id)
                )
        elif tools:
            action = _extract_json(turn.content)
            if isinstance(action, dict) and action.get("action") and action["action"] != "final":
                turn.tool_calls.append(
                    ToolCall(str(action["action"]), dict(action.get("args") or {}))
                )
                turn.content = str(action.get("say", ""))
            elif isinstance(action, dict) and action.get("action") == "final":
                turn.content = str(action.get("say", turn.content))
        return turn

    # ---------------------------------------------------------- structured

    async def structured(
        self,
        schema: type[BaseModel],
        messages: list[dict[str, Any]],
        *,
        role: ModelRole = "strong",
        temperature: float = 0.1,
    ) -> BaseModel:
        """Ask for JSON matching `schema`; validate; on failure ask once for a repair."""
        json_schema = schema.model_json_schema()
        prompt = {
            "role": "system",
            "content": "Respond with a single JSON object only, no prose, matching this JSON schema:\n"
            + json.dumps(json_schema, ensure_ascii=False),
        }
        turn = await self.chat(
            [prompt, *messages], role=role, temperature=temperature, max_tokens=2000
        )
        try:
            return schema.model_validate(_extract_json(turn.content))
        except (ValidationError, TypeError, ValueError) as exc:
            repair = {
                "role": "user",
                "content": f"Your JSON was invalid: {str(exc)[:500]}. Return only a corrected JSON object.",
            }
            turn = await self.chat(
                [prompt, *messages, {"role": "assistant", "content": turn.content}, repair],
                role=role,
                temperature=0,
                max_tokens=2000,
            )
            return schema.model_validate(_extract_json(turn.content))

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.available:
            raise RuntimeError("LLM not configured")
        response = await self._client.embeddings.create(
            model=self._settings.llm_embedding_model, input=[mask_text(t) for t in texts]
        )
        self.usage.add(getattr(response, "usage", None))
        return [d.embedding for d in response.data]

    async def summarize(self, text: str, *, instruction: str, max_tokens: int = 400) -> str:
        turn = await self.chat(
            [
                {"role": "system", "content": instruction},
                {"role": "user", "content": mask_text(text)[:12000]},
            ],
            role="small",
            max_tokens=max_tokens,
        )
        return turn.content.strip()


# ------------------------------------------------------------------ helpers


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fence.group(1) if fence else text
    try:
        return json.loads(candidate)
    except ValueError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            return json.loads(candidate[start : end + 1])
        raise


def _json_protocol_prompt(tools: list[dict[str, Any]]) -> str:
    catalogue = [
        {
            "name": t["function"]["name"],
            "description": t["function"].get("description", ""),
            "parameters": t["function"].get("parameters", {}),
        }
        for t in tools
    ]
    return (
        "ACTION PROTOCOL: you cannot call tools natively. Each turn reply with exactly one JSON object:\n"
        '{"action": "<tool name>", "args": {...}, "say": "<one short Persian sentence for the user>"}\n'
        'or, when finished: {"action": "final", "say": "<your full answer in Persian>"}.\n'
        "Available tools:\n" + json.dumps(catalogue, ensure_ascii=False)
    )


def safe_for_model(obj: Any) -> Any:
    return mask_obj(obj)
