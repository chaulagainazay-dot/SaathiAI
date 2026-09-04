"""NVIDIA hosted inference — an optional remote high-capability tier.

Serves `moonshotai/kimi-k3` and other NVIDIA-hosted models through
`https://integrate.api.nvidia.com/v1/chat/completions`, which speaks the
OpenAI chat-completions dialect.

**Why this is not `openai_compat.py`.** That adapter speaks the same dialect and
the temptation is to point it here. It is deliberately loopback-only -- its
allowlist is `127.0.0.1/localhost/::1` and its whole purpose is keeping
OpenAI-compatible traffic local. Widening that allowlist to admit a remote host
would turn an SSRF control into a permissive one for every caller of that
adapter. A separate engine in the same layer costs one file; weakening a
security boundary to save it costs the boundary.

**What this engine is, and is not.** It implements `InferenceEngine` like every
other adapter: it executes and reports. It owns no routing, no policy and no
authority. A model served here can produce text and propose tool calls; whether
any of that becomes an action is decided downstream by ToolIntent,
ExecutionGateway, approval and Trading Guardian, none of which this module
imports or can reach. K3 can think. It cannot authorize.

**Optional by construction.** No import-time network, no import-time
credential read, and `health()` reports unavailable rather than raising when
`NVIDIA_API_KEY` is absent. SaathiOS starts and runs without any of this.
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

from saathi.inference.engine import (
    CostEstimate,
    EngineCapabilities,
    GenerateResult,
    InferenceEngine,
    StreamChunk,
)
from saathi.inference.errors import (
    EngineError,
    EngineTimeoutError,
    EngineUnhealthyError,
)

#: The endpoint this engine speaks to. A constant, not caller-supplied: an
#: engine whose destination can be set per request is an SSRF primitive.
NVIDIA_CHAT_COMPLETIONS_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

#: Credential env name. Reported by name; the value is never read into a log,
#: an error, a result or a health payload.
NVIDIA_API_KEY_ENV = "NVIDIA_API_KEY"

#: Models this engine will serve. A closed list: an engine that will serve any
#: string a caller passes is an open proxy to a paid API.
KIMI_K3 = "moonshotai/kimi-k3"
SUPPORTED_MODELS: frozenset[str] = frozenset({KIMI_K3})

#: Bounded defaults. The reference request uses `max_tokens=16384` and
#: `reasoning_effort="max"`; both are the *ceiling* of what the provider allows,
#: not a sensible default for every call. Adopting them wholesale would make
#: every trivial completion slow and expensive.
DEFAULT_MAX_TOKENS = 1024
MAX_ALLOWED_TOKENS = 16384
DEFAULT_TIMEOUT_SEC = 60.0

#: Reasoning depth, expressed in SaathiOS terms and mapped at the boundary, so
#: callers never pass provider vocabulary through the application.
REASONING_EFFORT = {
    "LOW": "low",
    "NORMAL": "medium",
    "HIGH": "high",
    "MAX": "max",
}
DEFAULT_REASONING = "NORMAL"


class NvidiaConfigError(EngineError):
    """Configuration is missing or invalid. Never carries a credential value."""


def api_key_present() -> bool:
    """Whether a usable credential is configured. Never returns or logs it.

    Mirrors the placeholder convention the other cloud transports use: a value
    beginning `YOUR` is a template someone has not filled in, not a key.
    """
    value = os.getenv(NVIDIA_API_KEY_ENV, "")
    return bool(value) and not value.startswith("YOUR")


def _api_key() -> str:
    if not api_key_present():
        # The message names the variable, never its content, and never echoes
        # whatever placeholder happens to be set.
        raise NvidiaConfigError(
            f"MISCONFIGURED: {NVIDIA_API_KEY_ENV} is not configured")
    return os.getenv(NVIDIA_API_KEY_ENV, "")


# ── image URLs are a security boundary ─────────────────────────────────────

def validate_image_url(url: str, *, resolver=None) -> tuple[bool, str]:
    """Whether an image URL may be handed to the provider.

    The provider fetches whatever URL we send it, so an unvalidated one turns
    this engine into a request forgery primitive aimed at someone else's
    network. Reuses the repository's canonical SSRF classifier rather than
    inventing a second opinion about which addresses are private.

    Returns `(ok, reason_code)`; the reason is bounded and safe to log.
    """
    from saathi.connectors.providers.external.dns_ssrf import (
        classify_address,
        default_resolver,
    )

    raw = (url or "").strip()
    if not raw:
        return False, "empty_url"
    try:
        parsed = urlparse(raw)
    except Exception:
        return False, "invalid_url"
    if parsed.scheme not in {"http", "https"}:
        # file://, data:, gopher:// and friends are not image sources here.
        return False, "scheme_not_http"
    if parsed.username or parsed.password:
        return False, "userinfo_forbidden"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "missing_host"

    resolve = resolver or default_resolver
    try:
        addresses = resolve(host)
    except Exception:
        return False, "dns_failed"
    if not addresses:
        return False, "dns_empty"
    # Every resolved address must be public. One private answer is enough to
    # refuse -- a name that resolves to both is the interesting attack.
    for address in addresses:
        category = classify_address(address)
        if category != "public":
            return False, f"blocked_{category}"
    return True, "ok"


# ── canonical messages -> provider payload ─────────────────────────────────

def to_provider_messages(messages: Sequence[dict[str, Any]], *,
                         resolver=None) -> list[dict[str, Any]]:
    """Translate SaathiOS messages into the provider's wire shape.

    Plain-string content passes through, which is the overwhelming majority.
    A list of content parts is treated as multimodal and each image part's URL
    is validated before it leaves the process; a part that fails validation is
    dropped and replaced with a note, because sending it is the thing being
    prevented and failing the whole turn would make one bad attachment lose the
    conversation.

    This translation lives here on purpose: provider payload shapes must not
    leak into the conversation layer, or every caller ends up knowing what
    NVIDIA wants.
    """
    out: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = message.get("content")
        if isinstance(content, str) or content is None:
            out.append({"role": role, "content": content or ""})
            continue

        parts: list[dict[str, Any]] = []
        for part in content:
            if not isinstance(part, dict):
                parts.append({"type": "text", "text": str(part)})
                continue
            kind = part.get("type")
            if kind == "text":
                parts.append({"type": "text", "text": str(part.get("text", ""))})
            elif kind == "image_url":
                url = ((part.get("image_url") or {}).get("url")
                       if isinstance(part.get("image_url"), dict)
                       else part.get("image_url"))
                ok, reason = validate_image_url(str(url or ""), resolver=resolver)
                if ok:
                    parts.append({"type": "image_url", "image_url": {"url": url}})
                else:
                    parts.append({"type": "text",
                                  "text": f"[image omitted: {reason}]"})
            else:
                # Unknown part types are described, not forwarded: passing
                # through a shape we do not understand is how a payload
                # injection reaches a provider.
                parts.append({"type": "text", "text": f"[unsupported part: {kind}]"})
        out.append({"role": role, "content": parts})
    return out


def build_payload(messages: Sequence[dict[str, Any]], *, model: str,
                  temperature: float = 0.7, max_tokens: int = DEFAULT_MAX_TOKENS,
                  stream: bool = False, reasoning: str = DEFAULT_REASONING,
                  seed: Optional[int] = None, tools: Optional[list] = None,
                  resolver=None) -> dict[str, Any]:
    """The request body. Bounded, and not a passthrough of caller kwargs.

    Callers get the parameters SaathiOS models; they do not get to set arbitrary
    provider fields, because an engine that forwards an unfiltered dict is an
    engine whose behaviour is defined by whoever calls it.
    """
    effort = REASONING_EFFORT.get(str(reasoning).upper())
    if effort is None:
        raise NvidiaConfigError(
            f"unknown reasoning level {reasoning!r};"
            f" expected one of {sorted(REASONING_EFFORT)}")

    payload: dict[str, Any] = {
        "model": model,
        "messages": to_provider_messages(messages, resolver=resolver),
        "max_tokens": max(1, min(int(max_tokens), MAX_ALLOWED_TOKENS)),
        "temperature": float(temperature),
        "stream": bool(stream),
        "reasoning_effort": effort,
    }
    if seed is not None:
        payload["seed"] = int(seed)
    if tools:
        payload["tools"] = tools
    return payload


# ── response parsing ───────────────────────────────────────────────────────

def parse_completion(body: dict[str, Any]) -> tuple[str, str, dict, list]:
    """(visible_text, finish_reason, usage, tool_calls) from a non-stream body.

    `reasoning_content`, when the provider returns it, is deliberately NOT part
    of the visible text. It is the model's private working, and putting it in
    the assistant message would surface chain-of-thought in chat, logs and
    audit. Callers that genuinely need it for provider continuation can read it
    from `GenerateResult.raw`.
    """
    choices = body.get("choices") or []
    if not choices:
        return "", "error", body.get("usage") or {}, []
    message = (choices[0] or {}).get("message") or {}
    text = message.get("content") or ""
    if isinstance(text, list):  # some providers return parts even for output
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    finish = (choices[0] or {}).get("finish_reason") or "stop"
    return text, finish, body.get("usage") or {}, list(message.get("tool_calls") or [])


def parse_sse_line(line: str) -> Optional[dict[str, Any]]:
    """One SSE line into a delta dict, or None when there is nothing to yield.

    Tolerant by design: keep-alives, comments, blank lines and malformed JSON
    are skipped rather than raising. A stream that dies on one bad frame is
    worse than one that drops it -- and a provider that emits a partial line is
    not an event worth crashing a conversation over.
    """
    raw = (line or "").strip()
    if not raw or raw.startswith(":"):
        return None
    if raw.startswith("data:"):
        raw = raw[5:].strip()
    if not raw or raw == "[DONE]":
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def chunk_from_delta(event: dict[str, Any]) -> Optional[StreamChunk]:
    """A provider delta as a canonical `StreamChunk`, or None if it carries none.

    Reasoning deltas are consumed and not emitted as content, for the same
    reason `parse_completion` withholds `reasoning_content`.
    """
    choices = event.get("choices") or []
    if not choices:
        usage = event.get("usage")
        return StreamChunk(usage=usage) if usage else None
    choice = choices[0] or {}
    delta = choice.get("delta") or {}
    content = delta.get("content")
    tool_calls = delta.get("tool_calls")
    finish = choice.get("finish_reason")
    if content is None and not tool_calls and not finish:
        return None
    return StreamChunk(content=content, finish_reason=finish,
                       tool_calls=list(tool_calls) if tool_calls else None,
                       usage=event.get("usage"))


class NvidiaEngine(InferenceEngine):
    """NVIDIA-hosted models, as an ordinary SaathiOS engine."""

    engine_id = "nvidia"
    is_cloud = True

    def __init__(self, *, model: str = KIMI_K3, timeout: float = DEFAULT_TIMEOUT_SEC,
                 url: str = NVIDIA_CHAT_COMPLETIONS_URL):
        self.model = model
        self.timeout = float(timeout)
        # Fixed at construction, never per request.
        self._url = url

    def can_serve(self, model: str) -> bool:
        return model in SUPPORTED_MODELS

    async def capabilities(self) -> EngineCapabilities:
        """Claimed from the request contract, not aspirationally.

        `tool_calling` and `structured_output` are reported False: the supplied
        contract demonstrates neither, and claiming a capability the router may
        act on without evidence is how a request gets sent somewhere it cannot
        be served. They move to True when a live qualification shows them.
        """
        return EngineCapabilities(
            streaming=True, vision=True, tool_calling=False,
            structured_output=False, audio=False, local=False,
            max_context_window=None,
            notes="NVIDIA hosted; capabilities pending live qualification")

    async def health(self) -> dict[str, Any]:
        """Reports unavailable rather than raising when unconfigured.

        An optional remote tier that throws on a health probe makes itself a
        startup dependency, which is exactly what it must not be.
        """
        ok = api_key_present()
        return {"ok": ok, "engine_id": self.engine_id, "is_cloud": True,
                "model": self.model,
                "reason": "" if ok else f"{NVIDIA_API_KEY_ENV}_missing"}

    async def list_models(self) -> list[str]:
        return sorted(SUPPORTED_MODELS)

    async def estimate_cost(self, *, model: str, prompt_tokens: int = 0,
                            completion_tokens: int = 0) -> CostEstimate:
        # No published per-token price is encoded here. Inventing dollars would
        # be worse than admitting the number is unknown.
        return CostEstimate(known=False, notes="NVIDIA hosted pricing not configured")

    async def generate(self, messages: Sequence[dict[str, Any]], *, model: str,
                       temperature: float = 0.7, max_tokens: int = DEFAULT_MAX_TOKENS,
                       timeout: Optional[float] = None, **kwargs: Any) -> GenerateResult:
        import httpx

        if not self.can_serve(model):
            raise NvidiaConfigError(f"model not served by this engine: {model}")
        key = _api_key()
        payload = build_payload(
            messages, model=model, temperature=temperature, max_tokens=max_tokens,
            stream=False, reasoning=kwargs.get("reasoning", DEFAULT_REASONING),
            seed=kwargs.get("seed"), tools=kwargs.get("tools"),
            resolver=kwargs.get("resolver"))

        started = time.perf_counter()
        try:
            response = httpx.post(
                self._url,
                headers={"Authorization": f"Bearer {key}",
                         "Accept": "application/json"},
                json=payload, timeout=timeout or self.timeout)
        except Exception as exc:
            raise _transport_error(exc) from exc
        _raise_for_status(response.status_code)

        try:
            body = response.json()
        except Exception as exc:
            raise EngineError("nvidia returned a non-JSON body") from exc

        text, finish, usage, tool_calls = parse_completion(body)
        return GenerateResult(
            text=text, model=model, engine_id=self.engine_id, usage=usage,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            finish_reason=finish,
            # Provider continuation state lives here, not in `text`.
            raw={"tool_calls": tool_calls,
                 "reasoning_present": bool(
                     ((body.get("choices") or [{}])[0].get("message") or {})
                     .get("reasoning_content"))})

    async def stream(self, messages: Sequence[dict[str, Any]], *, model: str,
                     temperature: float = 0.7, max_tokens: int = DEFAULT_MAX_TOKENS,
                     timeout: Optional[float] = None,
                     **kwargs: Any) -> AsyncIterator[StreamChunk]:
        import httpx

        if not self.can_serve(model):
            raise NvidiaConfigError(f"model not served by this engine: {model}")
        key = _api_key()
        payload = build_payload(
            messages, model=model, temperature=temperature, max_tokens=max_tokens,
            stream=True, reasoning=kwargs.get("reasoning", DEFAULT_REASONING),
            seed=kwargs.get("seed"), tools=kwargs.get("tools"),
            resolver=kwargs.get("resolver"))

        try:
            with httpx.stream(
                "POST", self._url,
                headers={"Authorization": f"Bearer {key}",
                         "Accept": "text/event-stream"},
                json=payload, timeout=timeout or self.timeout,
            ) as response:
                _raise_for_status(response.status_code)
                for line in response.iter_lines():
                    event = parse_sse_line(line)
                    if event is None:
                        continue
                    chunk = chunk_from_delta(event)
                    if chunk is not None:
                        yield chunk
        except (EngineError, EngineTimeoutError, EngineUnhealthyError):
            raise
        except Exception as exc:
            # A stream that dies mid-flight is a normalized engine failure, not
            # an httpx traceback surfacing in a conversation.
            raise _transport_error(exc) from exc


def _raise_for_status(status: int) -> None:
    """Map provider status codes onto the engine error vocabulary.

    401/403 are unhealthy rather than generic errors so the router can mark the
    provider degraded instead of retrying a credential that will not improve.
    """
    if status < 400:
        return
    if status in (401, 403):
        raise EngineUnhealthyError(f"nvidia rejected the credential (HTTP {status})")
    if status == 404:
        raise EngineError("nvidia: model or endpoint not found (HTTP 404)")
    if status == 429:
        raise EngineUnhealthyError("nvidia rate limited (HTTP 429)")
    if status >= 500:
        raise EngineUnhealthyError(f"nvidia upstream error (HTTP {status})")
    raise EngineError(f"nvidia request failed (HTTP {status})")


def _transport_error(exc: BaseException) -> EngineError:
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text or isinstance(exc, TimeoutError):
        return EngineTimeoutError(f"nvidia request timed out: {type(exc).__name__}")
    return EngineUnhealthyError(f"nvidia transport failure: {type(exc).__name__}")
