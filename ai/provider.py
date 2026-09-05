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


class RateLimitError(LLMError):
    """The provider refused the request for quota reasons (HTTP 429).

    Separate from LLMError so the failover chain can tell "try the next model"
    apart from "this request is broken".
    """


class ProviderUnavailableError(LLMError):
    """The provider could not be reached, or failed on its own side (5xx).

    Also worth failing over: nothing about the request is wrong, so another
    provider has a real chance of answering it.
    """


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    # Gemini 3.x returns an opaque "thought signature" alongside each function
    # call and rejects the next request if it isn't echoed back verbatim. Other
    # providers ignore this.
    signature: Optional[str] = None
    # Which model produced the signature. A signature is only valid for that
    # model, so the failover chain uses this to decide whether to replay it.
    signature_model: Optional[str] = None


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

    def __init__(self, api_key: str, model: str = "gemini-3.6-flash"):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self.api_key = api_key
        self.model = model

    def _contents(self, messages: list[dict]) -> list[dict]:
        # Gemini's Content.role accepts only "user" and "model"; tool results ride
        # back in as a user turn carrying functionResponse parts.
        #
        # Gemini 3.x rejects any functionCall part that lacks a thought signature,
        # and a signature is only valid for the model that produced it. So a call
        # made by a different model cannot be replayed as a functionCall at all -
        # it gets flattened to plain text instead, preserving the information
        # without tripping the check. Its matching result is flattened too, since
        # a functionResponse with no functionCall is equally invalid.
        contents: list[dict] = []
        flattened: set[str] = set()

        for msg in messages:
            role = msg["role"]
            if role == "user":
                contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
            elif role == "assistant":
                parts: list[dict] = []
                notes: list[str] = []
                if msg.get("content"):
                    parts.append({"text": msg["content"]})
                for call in msg.get("tool_calls") or []:
                    if call.signature:
                        parts.append({
                            "functionCall": {"name": call.name, "args": call.arguments},
                            "thoughtSignature": call.signature,
                        })
                    else:
                        flattened.add(call.id)
                        notes.append(f"(Called {call.name} with {json.dumps(call.arguments)}.)")
                if notes:
                    parts.append({"text": "\n".join(notes)})
                if parts:
                    contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                if msg.get("tool_call_id") in flattened:
                    contents.append({
                        "role": "user",
                        "parts": [{"text": f"Result of {msg['name']}: {msg['content']}"}],
                    })
                else:
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
            raise ProviderUnavailableError(f"Could not reach Gemini: {exc}") from exc

        if response.status_code != 200:
            raise _http_error("Gemini", response)

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
                tool_calls.append(ToolCall(
                    name=fc.get("name", ""),
                    arguments=fc.get("args") or {},
                    # Sits beside functionCall on the part; older models omit it.
                    signature=part.get("thoughtSignature") or fc.get("thoughtSignature"),
                    signature_model=self.model,
                ))

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
            raise ProviderUnavailableError(f"Could not reach {self.name}: {exc}") from exc

        if response.status_code != 200:
            raise _http_error(self.name, response)

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


def _http_error(provider: str, response: httpx.Response) -> LLMError:
    """Turn a provider error response into an exception a caller can act on."""
    try:
        body = response.json()
        detail = (body.get("error") or {}).get("message") or json.dumps(body)[:300]
    except Exception:
        detail = response.text[:300]

    if response.status_code == 429:
        return RateLimitError(f"{provider} rate limit reached. ({detail})")
    if response.status_code in (401, 403):
        return LLMError(f"{provider} rejected the API key. Check your key in the environment. ({detail})")
    if response.status_code >= 500:
        return ProviderUnavailableError(f"{provider} is having problems ({response.status_code}): {detail}")
    return LLMError(f"{provider} error {response.status_code}: {detail}")


# ========== FAILOVER ==========

def _signatures_for(messages: list[dict], target_model: str) -> list[dict]:
    """Keep only the thought signatures that belong to `target_model`.

    A signature is valid solely for the model that produced it: replaying
    another model's is a 400, and so is dropping a model's own. Since the chain
    can switch models mid-conversation, each call is filtered against whichever
    model is about to be asked.
    """
    adjusted: list[dict] = []
    for msg in messages:
        calls = msg.get("tool_calls")
        if calls and any(c.signature and c.signature_model != target_model for c in calls):
            msg = {**msg, "tool_calls": [
                ToolCall(
                    name=c.name,
                    arguments=c.arguments,
                    id=c.id,
                    signature=c.signature if c.signature_model == target_model else None,
                    signature_model=c.signature_model,
                )
                for c in calls
            ]}
        adjusted.append(msg)
    return adjusted


class FailoverProvider(LLMProvider):
    """Tries each provider in turn, moving on when one is rate limited.

    Free tiers meter per model, so a second model on the same key is usually
    enough to keep working through a burst. Only quota errors advance the chain;
    a genuine failure surfaces immediately rather than being retried five times.
    """

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise LLMError("No AI provider configured")
        self.providers = providers
        self.primary = providers[0]
        self.name = self.primary.name
        self.model = self.primary.model
        # Whichever model last answered. A conversation carries tool calls that
        # only its author can replay, so once one model is answering we stay with
        # it for the rest of the conversation rather than drifting back to the
        # primary the moment its quota frees up.
        self._current: Optional[LLMProvider] = None

    def _order(self) -> list[LLMProvider]:
        if self._current is None or self._current is self.providers[0]:
            return self.providers
        rest = [p for p in self.providers if p is not self._current]
        return [self._current, *rest]

    def generate(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        last_error: Optional[LLMError] = None

        for provider in self._order():
            # Replay only the signatures this particular model issued.
            payload = _signatures_for(messages, provider.model)
            try:
                response = provider.generate(system, payload, tools)
            except (RateLimitError, ProviderUnavailableError) as exc:
                # Nothing wrong with the request itself - let the next one try.
                last_error = exc
                continue
            # Report and stick with whichever model actually answered.
            self._current = provider
            self.name, self.model = provider.name, provider.model
            return response

        assert last_error is not None
        raise type(last_error)(
            f"Every configured model is unavailable right now "
            f"({', '.join(p.model for p in self.providers)}). Last error: {last_error}"
        )


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


# Tried in order when the primary model is rate limited. Free tiers meter per
# model, so these are separate buckets on the same key.
_GEMINI_FALLBACKS = ["gemini-3.5-flash", "gemini-3.1-flash-lite"]


def _build_one(provider: str, model: Optional[str] = None) -> LLMProvider:
    """Build a single provider. `model` overrides whatever the env says."""
    if provider == "gemini":
        return GeminiProvider(
            api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
            model=(model or os.environ.get("AI_MODEL") or "gemini-3.6-flash").strip(),
        )

    if provider in _OPENAI_COMPAT_DEFAULTS:
        base_url, default_model, key_env = _OPENAI_COMPAT_DEFAULTS[provider]
        api_key = os.environ.get(key_env, "").strip()
        if not api_key and provider != "ollama":
            raise LLMError(f"{key_env} is not set")
        return OpenAICompatProvider(
            api_key=api_key,
            model=(model or os.environ.get("AI_MODEL") or default_model).strip(),
            base_url=os.environ.get("AI_BASE_URL", base_url).strip(),
            provider_name=provider,
        )

    raise LLMError(
        f"Unknown AI_PROVIDER '{provider}'. Use one of: gemini, groq, openrouter, ollama."
    )


def get_provider() -> LLMProvider:
    """Build the provider chain: the primary, then whatever can cover for it.

    The chain is AI_PROVIDER's model first, then AI_MODEL_FALLBACKS (or sensible
    per-provider defaults), then any other provider whose key happens to be set.
    """
    primary_name = (os.environ.get("AI_PROVIDER") or "gemini").strip().lower()
    chain: list[LLMProvider] = [_build_one(primary_name)]
    seen = {(chain[0].name, chain[0].model)}

    def add(provider_name: str, model: Optional[str] = None) -> None:
        try:
            candidate = _build_one(provider_name, model)
        except LLMError:
            return  # no key for it, or unknown - just skip
        if (candidate.name, candidate.model) not in seen:
            seen.add((candidate.name, candidate.model))
            chain.append(candidate)

    configured = os.environ.get("AI_MODEL_FALLBACKS", "").strip()
    if configured:
        for model in (m.strip() for m in configured.split(",") if m.strip()):
            add(primary_name, model)
    elif primary_name == "gemini":
        for model in _GEMINI_FALLBACKS:
            add(primary_name, model)

    # A key for another provider is the strongest fallback there is, since its
    # quota is entirely independent.
    if os.environ.get("AI_DISABLE_PROVIDER_FAILOVER", "").strip().lower() not in ("1", "true", "yes"):
        for other in ("groq", "openrouter"):
            if other != primary_name:
                add(other)

    return FailoverProvider(chain) if len(chain) > 1 else chain[0]


def is_configured() -> bool:
    """True when the selected provider has everything it needs to run."""
    try:
        get_provider()
        return True
    except LLMError:
        return False
