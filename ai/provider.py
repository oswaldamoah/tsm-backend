"""
LLM provider adapters.

The rest of the AI package speaks one neutral message format (below) and hands
providers tool definitions in plain JSON Schema. Each adapter translates to and
from its wire format, so swapping AI_PROVIDER swaps the model without touching
the agent loop or the tools.

Neutral message format (list of dicts):
    {"role": "user",      "content": "..."}
    {"role": "assistant", "content": "..." | None, "tool_calls": [ToolCall, ...]}
    {"role": "tool",      "tool_call_id": "...", "name": "...", "content": "<json>"}
"""

from dataclasses import dataclass, field
from typing import Any, Optional
import json
import os
import uuid

import httpx


# Providers get a hard timeout so a slow free-tier endpoint can't pin a worker.
# Gemini Flash answers well inside this even with a few tool round-trips.
REQUEST_TIMEOUT = float(os.environ.get("AI_REQUEST_TIMEOUT", "60"))


class LLMError(RuntimeError):
    """Raised when the provider is misconfigured or returns an unusable response."""


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class LLMResponse:
    text: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider:
    """Interface implemented by every adapter."""

    name = "base"
    model = ""

    def generate(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        raise NotImplementedError


# ========== GEMINI ==========

# Gemini's Schema type is a proto enum, so JSON Schema's lowercase type names and
# its validation-only keywords (additionalProperties, $schema, ...) are rejected.
_GEMINI_ALLOWED_SCHEMA_KEYS = {
    "type", "description", "enum", "items", "properties", "required", "nullable", "format",
}


def _to_gemini_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return schema
    out: dict = {}
    for key, value in schema.items():
        if key not in _GEMINI_ALLOWED_SCHEMA_KEYS:
            continue
        if key == "type" and isinstance(value, str):
            out[key] = value.upper()
        elif key == "properties" and isinstance(value, dict):
            out[key] = {k: _to_gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            out[key] = _to_gemini_schema(value)
        else:
            out[key] = value
    return out


class GeminiProvider(LLMProvider):
    """Google AI Studio (generativelanguage.googleapis.com) - free tier."""

    name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self.api_key = api_key
        self.model = model

    def _contents(self, messages: list[dict]) -> list[dict]:
        # Gemini's Content.role accepts only "user" and "model"; tool results ride
        # back in as a user turn carrying functionResponse parts.
        contents: list[dict] = []
        for msg in messages:
            role = msg["role"]
            if role == "user":
                contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
            elif role == "assistant":
                parts: list[dict] = []
                if msg.get("content"):
                    parts.append({"text": msg["content"]})
                for call in msg.get("tool_calls") or []:
                    parts.append({"functionCall": {"name": call.name, "args": call.arguments}})
                if parts:
                    contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": msg["name"],
                            "response": {"result": json.loads(msg["content"])},
                        }
                    }],
                })
        return contents

    def generate(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        payload: dict = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": self._contents(messages),
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096},
        }
        if tools:
            payload["tools"] = [{
                "functionDeclarations": [
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": _to_gemini_schema(t["parameters"]),
                    }
                    for t in tools
                ]
            }]

        url = f"{self.BASE_URL}/{self.model}:generateContent"
        try:
            response = httpx.post(
                url,
                json=payload,
                headers={"x-goog-api-key": self.api_key},
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach Gemini: {exc}") from exc

        if response.status_code != 200:
            raise LLMError(_describe_http_error("Gemini", response))

        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            # Usually a safety block; the reason lives in promptFeedback.
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise LLMError(f"Gemini returned no answer ({reason})")

        text_chunks: list[str] = []
        tool_calls: list[ToolCall] = []
        for part in candidates[0].get("content", {}).get("parts", []) or []:
            if "text" in part:
                text_chunks.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(ToolCall(name=fc.get("name", ""), arguments=fc.get("args") or {}))

        return LLMResponse(text="".join(text_chunks).strip() or None, tool_calls=tool_calls)


# ========== OPENAI-COMPATIBLE (Groq / OpenRouter / Ollama / ...) ==========

class OpenAICompatProvider(LLMProvider):
    """Any endpoint speaking the OpenAI chat-completions schema."""

    name = "openai-compatible"

    def __init__(self, api_key: str, model: str, base_url: str, provider_name: str = "openai-compatible"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.name = provider_name

    def _messages(self, system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg["role"]
            if role == "assistant":
                entry: dict = {"role": "assistant", "content": msg.get("content") or ""}
                calls = msg.get("tool_calls") or []
                if calls:
                    entry["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                        }
                        for c in calls
                    ]
                out.append(entry)
            elif role == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "name": msg["name"],
                    "content": msg["content"],
                })
            else:
                out.append({"role": "user", "content": msg["content"]})
        return out

    def generate(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": self._messages(system, messages),
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["parameters"],
                    },
                }
                for t in tools
            ]

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach {self.name}: {exc}") from exc

        if response.status_code != 200:
            raise LLMError(_describe_http_error(self.name, response))

        choices = response.json().get("choices") or []
        if not choices:
            raise LLMError(f"{self.name} returned no answer")

        message = choices[0].get("message") or {}
        tool_calls = []
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            try:
                arguments = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                ToolCall(
                    id=call.get("id") or uuid.uuid4().hex[:12],
                    name=fn.get("name", ""),
                    arguments=arguments,
                )
            )

        return LLMResponse(text=(message.get("content") or "").strip() or None, tool_calls=tool_calls)


def _describe_http_error(provider: str, response: httpx.Response) -> str:
    """Turn a provider error body into something a user can act on."""
    try:
        body = response.json()
        detail = (body.get("error") or {}).get("message") or json.dumps(body)[:300]
    except Exception:
        detail = response.text[:300]

    if response.status_code == 429:
        return f"{provider} free-tier rate limit reached. Try again in a minute. ({detail})"
    if response.status_code in (401, 403):
        return f"{provider} rejected the API key. Check your key in the environment. ({detail})"
    return f"{provider} error {response.status_code}: {detail}"


# ========== FACTORY ==========

_OPENAI_COMPAT_DEFAULTS = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "meta-llama/llama-3.3-70b-instruct:free",
        "OPENROUTER_API_KEY",
    ),
    "ollama": ("http://localhost:11434/v1", "llama3.1", "OLLAMA_API_KEY"),
}


def get_provider() -> LLMProvider:
    """Build the provider named by AI_PROVIDER (default: gemini)."""
    provider = (os.environ.get("AI_PROVIDER") or "gemini").strip().lower()

    if provider == "gemini":
        return GeminiProvider(
            api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
            model=os.environ.get("AI_MODEL", "gemini-2.5-flash").strip(),
        )

    if provider in _OPENAI_COMPAT_DEFAULTS:
        base_url, default_model, key_env = _OPENAI_COMPAT_DEFAULTS[provider]
        api_key = os.environ.get(key_env, "").strip()
        if not api_key and provider != "ollama":
            raise LLMError(f"{key_env} is not set")
        return OpenAICompatProvider(
            api_key=api_key,
            model=os.environ.get("AI_MODEL", default_model).strip(),
            base_url=os.environ.get("AI_BASE_URL", base_url).strip(),
            provider_name=provider,
        )

    raise LLMError(
        f"Unknown AI_PROVIDER '{provider}'. Use one of: gemini, groq, openrouter, ollama."
    )


def is_configured() -> bool:
    """True when the selected provider has everything it needs to run."""
    try:
        get_provider()
        return True
    except LLMError:
        return False
