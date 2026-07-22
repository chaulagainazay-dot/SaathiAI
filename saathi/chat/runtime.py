"""M23 — Canonical governed chat runtime.

Sole production-capable execution path for SaathiOS chat:

  ChatRequest
    → validate
    → preflight (kill / caller policy)
    → context builder (optional; simple prompt path supported)
    → InferenceRequest
    → ModelRouter + governed adapter transport
       OR execute_governed_local_inference when gateway enabled
    → typed ChatCompletionResult

Invariants:
  * No llm.generate from this module
  * No provider SDK / URL / credential reads
  * No caller-level retries or provider fallback lists
  * No cloud fallback enablement
  * No raw prompt/output logging
  * tool_mode defaults off; tools never execute here
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterator, Optional

from saathi.chat.context import (
    CANONICAL_BASE_PROMPT,
    CONTEXT_BUILDER_AUTHORITY,
    ContextBuildResult,
    build_chat_context,
)
from saathi.chat.request import (
    CALLER_CHAT_ENGINE,
    ChatRequest,
    ChatRequestError,
    ChatToolMode,
    build_chat_request,
    chat_request_to_inference_request,
    validate_chat_request,
)
from saathi.chat.stream_events import (
    STREAM_EVENT_AUTHORITY,
    ChatStreamEvent,
    stream_lifecycle,
)

logger = logging.getLogger(__name__)

PATH_ID = "chat_runtime"
GOVERNED_CHAT_DEFAULT = True
LEGACY_CHAT_EXECUTION = False  # unavailable
RUNTIME_AUTHORITY = "saathi.chat.runtime.run_chat_completion"

# Inject signature: (prompt, system) -> {"text", "provider", "tokens"} | str
InjectFn = Callable[[str, str], Any]

# Process-local idempotency (not durable; M24 may extend)
_IDEM: dict[str, "ChatCompletionResult"] = {}
_IDEM_LOCK = threading.Lock()
_IDEM_MAX = 128
_CANCELLED: set[str] = set()
_CANCEL_LOCK = threading.Lock()

# Privacy-safe telemetry ring
_events: list[dict[str, Any]] = []
_MAX_EVENTS = 200
_events_lock = threading.Lock()


@dataclass
class ChatCompletionResult:
    """Typed chat result for engine / API mapping."""

    ok: bool
    text: str = ""
    provider: str = ""
    model: str = ""
    tokens: int = 0
    path_used: str = "governed_chat"
    request_id: str = ""
    conversation_id: str = ""
    error_code: str = ""
    error_message: str = ""
    cancelled: bool = False
    partial: bool = False
    usage: dict[str, Any] = field(default_factory=dict)
    context_meta: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_llm_dict(self) -> dict[str, Any]:
        """Compatibility shape for ChatLLMAdapter / _default_llm."""
        return {
            "text": self.text or "",
            "provider": self.provider or "",
            "tokens": self.tokens or 0,
            "path_used": self.path_used,
            "request_id": self.request_id,
            "model": self.model or "",
            "ok": self.ok,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "cancelled": self.cancelled,
            "partial": self.partial,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def safe_telemetry(self) -> dict[str, Any]:
        return {
            "schema": "m23.chat_result.v1",
            "ok": self.ok,
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "path_used": self.path_used,
            "provider": self.provider,
            "model": self.model,
            "tokens": self.tokens,
            "text_chars": len(self.text or ""),
            "error_code": self.error_code,
            "cancelled": self.cancelled,
            "partial": self.partial,
            # no raw text
        }


def _fp(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:24]


def _emit(event: str, payload: dict[str, Any]) -> None:
    forbidden = {
        "prompt",
        "output",
        "text",
        "system",
        "messages",
        "content",
        "history",
        "api_key",
        "authorization",
    }
    safe = {k: v for k, v in payload.items() if k not in forbidden}
    entry = {"event": event, "ts": time.time(), **safe}
    with _events_lock:
        _events.append(entry)
        if len(_events) > _MAX_EVENTS:
            del _events[: _MAX_EVENTS // 2]
    try:
        from saathi.events import bus

        bus.publish_sync(f"inference.chat.{event}", safe)
    except Exception:
        pass


def recent_chat_runtime_events(limit: int = 40) -> list[dict[str, Any]]:
    with _events_lock:
        return list(_events[-limit:])


def mark_cancelled(request_id: str) -> None:
    rid = (request_id or "").strip()
    if not rid:
        return
    with _CANCEL_LOCK:
        _CANCELLED.add(rid)


def is_cancelled(request_id: str) -> bool:
    with _CANCEL_LOCK:
        return (request_id or "").strip() in _CANCELLED


def clear_cancellation(request_id: str) -> None:
    with _CANCEL_LOCK:
        _CANCELLED.discard((request_id or "").strip())


def _idem_get(key: str) -> Optional[ChatCompletionResult]:
    if not key:
        return None
    with _IDEM_LOCK:
        return _IDEM.get(key)


def _idem_put(key: str, result: ChatCompletionResult) -> None:
    if not key:
        return
    with _IDEM_LOCK:
        _IDEM[key] = result
        if len(_IDEM) > _IDEM_MAX:
            # drop oldest arbitrary keys
            for k in list(_IDEM.keys())[: len(_IDEM) - _IDEM_MAX]:
                _IDEM.pop(k, None)


def map_chat_failure(code: str, message: str = "") -> tuple[str, str]:
    """Map to safe user-facing code + message (no provider body)."""
    catalog = {
        "empty_message": ("INVALID_REQUEST", "Message is required."),
        "oversized_message": ("INVALID_REQUEST", "Message is too long."),
        "missing_caller": ("UNKNOWN_CALLER", "Caller identity is required."),
        "unknown_caller": ("UNKNOWN_CALLER", "Unknown caller."),
        "unauthorized_caller": ("UNAUTHORIZED_CALLER", "Caller not authorized."),
        "test_caller_denied": ("UNAUTHORIZED_CALLER", "Test caller denied."),
        "kill_switch_active": ("PROVIDER_KILLED", "kill switch active — inference denied"),
        "provider_killed": ("PROVIDER_KILLED", "provider killed — inference denied"),
        "privacy_denied": ("PRIVACY_DENIED", "Request denied by privacy policy."),
        "cost_denied": ("COST_DENIED", "Request denied by cost policy."),
        "circuit_open": ("CIRCUIT_OPEN", "Provider circuit is open."),
        "timeout": ("TIMEOUT", "The request timed out."),
        "rate_limit": ("RATE_LIMIT", "Rate limit exceeded."),
        "unreachable": ("UNREACHABLE", "Provider unreachable."),
        "context_limit": ("CONTEXT_LIMIT", "Context limit exceeded."),
        "output_limit": ("OUTPUT_LIMIT", "Output limit exceeded."),
        "malformed_response": ("MALFORMED_RESPONSE", "Provider returned a malformed response."),
        "cancelled": ("CANCELLED", "Request cancelled."),
        "unsupported_capability": ("UNSUPPORTED_CAPABILITY", "Capability not supported."),
        "misconfigured": ("MISCONFIGURED", "Inference is not configured."),
        "no_provider": ("PROVIDER_INTERNAL", "No available provider."),
        "override_denied": ("INVALID_REQUEST", "Override not permitted."),
        "provider_override_denied": ("INVALID_REQUEST", "Provider override denied."),
        "model_override_denied": ("INVALID_REQUEST", "Model override denied."),
        "tool_denied": ("PERMISSION", "Tool use not permitted."),
        "conversation_not_found": ("INVALID_REQUEST", "Conversation not found."),
        "ownership_denied": ("PERMISSION", "Conversation access denied."),
    }
    mapped = catalog.get(code)
    if mapped:
        return mapped
    # Never leak raw provider bodies
    safe = (message or "Chat request failed.")[:200]
    if any(t in safe.lower() for t in ("authorization", "bearer", "api_key", "password")):
        safe = "Provider error (sanitized)."
    return "UNKNOWN_PROVIDER_ERROR", safe


def resolve_conversation_identity(
    conversation_id: str,
    *,
    actor_id: str = "user:ajay",
    store: Any = None,
    require_existing: bool = False,
) -> dict[str, Any]:
    """Explicit conversation identity resolution (no auth redesign).

    Local single-user bound: actor defaults to user:ajay. Unknown IDs fail
    safely when require_existing is True.
    """
    from saathi.chat.request import normalize_conversation_id

    cid = normalize_conversation_id(conversation_id)
    out: dict[str, Any] = {
        "conversation_id": cid,
        "actor_id": actor_id or "user:ajay",
        "ok": True,
        "error_code": "",
    }
    if not cid:
        if require_existing:
            out["ok"] = False
            out["error_code"] = "conversation_not_found"
        return out
    if store is not None:
        conv = store.get_conversation(cid)
        if conv is None or conv.get("deleted"):
            out["ok"] = False
            out["error_code"] = "conversation_not_found"
            return out
        # Ownership: local-only store has no multi-tenant user_id column;
        # bound actor is recorded for telemetry and future enforcement.
        out["conversation"] = {
            "id": conv.get("id"),
            "project_id": conv.get("project_id") or "",
            "deleted": bool(conv.get("deleted")),
        }
    return out


def _preflight(req: ChatRequest, prompt: str, system: str) -> Any:
    from saathi.inference.legacy_facade import preflight_inference

    return preflight_inference(
        caller_id=req.caller_id,
        path_id=PATH_ID,
        prompt=prompt or "",
        system=system or "",
        max_tokens=int(req.token_budget),
        timeout=float(req.timeout_seconds),
    )


def _try_governed_local(ireq: Any) -> Optional[ChatCompletionResult]:
    """Optional local gateway path when M20.2 flags are on."""
    try:
        from saathi.inference.config import load_inference_settings

        settings = load_inference_settings()
        if not (settings.enabled and settings.gateway_enabled):
            return None
        from saathi.inference.caller_policy import is_governed_callable
        from saathi.inference.compat import _run_governed

        if not is_governed_callable(ireq.caller_component):
            return None
        gov = _run_governed(ireq)
        if gov.ok and (gov.output_text or "").strip():
            return ChatCompletionResult(
                ok=True,
                text=gov.output_text or "",
                provider=gov.selected_provider or gov.selected_model or "governed_local",
                model=gov.selected_model or "",
                tokens=int(getattr(gov, "output_tokens", 0) or 0),
                path_used="governed_local",
                request_id=ireq.request_id,
                usage={
                    "output_tokens": getattr(gov, "output_tokens", None),
                    "input_tokens": getattr(gov, "input_tokens", None),
                },
                metadata={"engine": gov.selected_engine or ""},
            )
    except Exception as exc:
        _emit(
            "governed_local_skip",
            {
                "request_id": getattr(ireq, "request_id", ""),
                "error_type": type(exc).__name__,
            },
        )
    return None


def _execute_router_transport(
    ireq: Any,
    prompt: str,
    system: str,
    *,
    cloud_allowed: bool,
) -> ChatCompletionResult:
    """Canonical multi-family path via ModelRouter + http_providers (not llm.generate)."""
    from saathi.model_router import ModelLabel, ModelRouter, Prefer, Privacy
    from saathi.inference.adapters import http_providers as hp

    privacy = Privacy.LOCAL_ONLY if not cloud_allowed else Privacy.CLOUD_OK
    # Respect local_only on request
    if getattr(ireq, "local_only", True):
        privacy = Privacy.LOCAL_ONLY

    max_tok = int(ireq.max_output_tokens)
    timeout_i = int(max(1, min(float(ireq.timeout_seconds), 300)))
    router = ModelRouter(is_available=hp.env_availability)
    chain = router.route(ModelLabel.STANDARD, privacy=privacy, prefer=Prefer.QUALITY)
    if not chain:
        code, msg = map_chat_failure("no_provider", "No available provider")
        return ChatCompletionResult(
            ok=False,
            path_used="governed_chat",
            request_id=ireq.request_id,
            error_code=code,
            error_message=msg,
        )

    last_err: Exception | None = None
    for spec in chain:
        if is_cancelled(ireq.request_id):
            code, msg = map_chat_failure("cancelled")
            return ChatCompletionResult(
                ok=False,
                cancelled=True,
                path_used="governed_chat",
                request_id=ireq.request_id,
                error_code=code,
                error_message=msg,
            )
        fam = spec.name.split("/", 1)[0]
        try:
            from saathi.inference.provider_policy import is_provider_killed

            if is_provider_killed(fam):
                last_err = RuntimeError(f"provider {fam} killed")
                continue
        except Exception:
            pass
        callers = dict(hp.DEFAULT_FAMILY_CALLERS)
        if callers.get(fam) is None:
            continue
        try:
            text, model, usage = hp.invoke_family(
                fam,
                prompt,
                system,
                max_tok,
                timeout_i,
                callers=callers,
            )
            usage = usage or {}
            tokens = int(
                usage.get("output_tokens")
                or usage.get("completion_tokens")
                or usage.get("tokens")
                or 0
            )
            return ChatCompletionResult(
                ok=True,
                text=text or "",
                provider=spec.name,
                model=model or "",
                tokens=tokens,
                path_used="governed_chat",
                request_id=ireq.request_id,
                usage=dict(usage) if isinstance(usage, dict) else {},
                metadata={"family": fam},
            )
        except Exception as e:
            last_err = e
            # No silent retry of same provider; continue chain (router failover)
            # Cost of each attempt is inherent; no chat-specific retry loop.
            continue

    err_s = str(last_err or "no provider")[:200]
    low = err_s.lower()
    if "timeout" in low:
        code, msg = map_chat_failure("timeout", err_s)
    elif "rate" in low:
        code, msg = map_chat_failure("rate_limit", err_s)
    elif "kill" in low:
        code, msg = map_chat_failure("provider_killed", err_s)
    else:
        code, msg = map_chat_failure("no_provider", err_s)
    return ChatCompletionResult(
        ok=False,
        path_used="governed_chat",
        request_id=ireq.request_id,
        error_code=code,
        error_message=msg,
        metadata={"error_type": type(last_err).__name__ if last_err else ""},
    )


def run_chat_completion(
    prompt: str = "",
    system: str = "",
    *,
    chat_request: Optional[ChatRequest] = None,
    message: str = "",
    conversation_id: str = "",
    caller_id: str = CALLER_CHAT_ENGINE,
    stream: bool = False,
    inject_fn: Optional[InjectFn] = None,
    context: Optional[ContextBuildResult] = None,
    skip_validation: bool = False,
) -> ChatCompletionResult:
    """Execute one chat completion through the governed runtime.

    ``inject_fn`` is test-only (path_used=test_injected). Production never
    uses it. ``legacy_fn`` alias is not provided — no legacy path.
    """
    t0 = time.monotonic()

    # Normalize request
    if chat_request is None:
        try:
            chat_request = build_chat_request(
                message or prompt or "",
                conversation_id=conversation_id,
                system=system or "",
                stream=stream,
                caller_id=caller_id,
                validate=not skip_validation,
            )
        except ChatRequestError as e:
            code, msg = map_chat_failure(e.code, e.message)
            return ChatCompletionResult(
                ok=False,
                error_code=code,
                error_message=msg,
                path_used="governed_chat",
                request_id=f"m23-{uuid.uuid4().hex[:16]}",
            )
    else:
        if not skip_validation:
            try:
                validate_chat_request(chat_request)
            except ChatRequestError as e:
                code, msg = map_chat_failure(e.code, e.message)
                return ChatCompletionResult(
                    ok=False,
                    error_code=code,
                    error_message=msg,
                    path_used="governed_chat",
                    request_id=chat_request.request_id,
                    conversation_id=chat_request.conversation_id,
                )

    req = chat_request
    idem_key = req.idempotency_key or ""
    if idem_key:
        cached = _idem_get(idem_key)
        if cached is not None and cached.ok:
            _emit(
                "idempotent_hit",
                {"request_id": req.request_id, "idempotency_key": idem_key[:32]},
            )
            return cached

    # Bound prompt/system
    try:
        from saathi.inference.caller_policy import get_caller_policy

        pol = get_caller_policy(req.caller_id)
        max_in = int(pol.max_input_chars) if pol else 32000
    except Exception:
        max_in = 32000

    if context is not None:
        prompt_b = (context.prompt or "")[:max_in]
        system_b = (context.system or CANONICAL_BASE_PROMPT)[:4000]
        ctx_meta = context.safe_telemetry()
    else:
        prompt_b = (prompt or req.message or "")[:max_in]
        system_b = (
            system or req.system or CANONICAL_BASE_PROMPT
        )[:4000]
        ctx_meta = {
            "history_count": 0,
            "truncated": False,
            "context_source": "direct_prompt",
        }

    if not (prompt_b or "").strip():
        code, msg = map_chat_failure("empty_message")
        return ChatCompletionResult(
            ok=False,
            error_code=code,
            error_message=msg,
            request_id=req.request_id,
            conversation_id=req.conversation_id,
            path_used="governed_chat",
        )

    # Tools default off — chat runtime never executes tools
    if req.tool_mode is not ChatToolMode.OFF:
        try:
            from saathi.inference.caller_policy import get_caller_policy

            pol = get_caller_policy(req.caller_id)
            if pol is None or not pol.tools_allowed:
                code, msg = map_chat_failure("tool_denied")
                return ChatCompletionResult(
                    ok=False,
                    error_code=code,
                    error_message=msg,
                    request_id=req.request_id,
                    path_used="governed_chat",
                )
        except Exception:
            code, msg = map_chat_failure("tool_denied")
            return ChatCompletionResult(
                ok=False,
                error_code=code,
                error_message=msg,
                request_id=req.request_id,
                path_used="governed_chat",
            )

    # Preflight — kill / caller before any provider
    pf = _preflight(req, prompt_b, system_b)
    if not pf.ok:
        code_raw = pf.reason_code or "preflight_denied"
        code, msg = map_chat_failure(code_raw, pf.error_message or "")
        # Prefer preflight text when it already carries kill/policy detail
        detail = pf.error_message or msg or code_raw
        _emit(
            "preflight_denied",
            {
                "request_id": pf.request_id,
                "caller_id": req.caller_id,
                "reason_code": code_raw,
                "prompt_chars": len(prompt_b),
            },
        )
        return ChatCompletionResult(
            ok=False,
            error_code=code,
            error_message=detail,
            request_id=pf.request_id,
            conversation_id=req.conversation_id,
            path_used="governed_chat",
            metadata={"reason_code": code_raw},
        )

    if is_cancelled(pf.request_id) or is_cancelled(req.request_id):
        code, msg = map_chat_failure("cancelled")
        return ChatCompletionResult(
            ok=False,
            cancelled=True,
            error_code=code,
            error_message=msg,
            request_id=pf.request_id,
            conversation_id=req.conversation_id,
            path_used="governed_chat",
        )

    # Build InferenceRequest (never logs raw prompt)
    ireq = chat_request_to_inference_request(
        req,
        prompt=prompt_b,
        system=system_b,
        preflight_request_id=pf.request_id,
        max_output_tokens=int(pf.max_output_tokens),
        timeout_seconds=float(pf.timeout_seconds),
    )

    _emit(
        "execution_start",
        {
            "request_id": pf.request_id,
            "caller_id": req.caller_id,
            "conversation_id": req.conversation_id,
            "prompt_chars": len(prompt_b),
            "system_chars": len(system_b),
            "stream": bool(req.stream),
            "tool_mode": req.tool_mode.value,
            "prompt_fingerprint": _fp(prompt_b),
        },
    )

    # Test inject only
    if inject_fn is not None:
        try:
            raw = inject_fn(prompt_b, system_b)
            if isinstance(raw, dict):
                result = ChatCompletionResult(
                    ok=True,
                    text=str(raw.get("text", "")),
                    provider=str(raw.get("provider", "test_injected")),
                    model=str(raw.get("model", "")),
                    tokens=int(raw.get("tokens", 0) or 0),
                    path_used="test_injected",
                    request_id=pf.request_id,
                    conversation_id=req.conversation_id,
                    context_meta=ctx_meta,
                )
            else:
                result = ChatCompletionResult(
                    ok=True,
                    text=str(raw),
                    provider="test_injected",
                    path_used="test_injected",
                    request_id=pf.request_id,
                    conversation_id=req.conversation_id,
                    context_meta=ctx_meta,
                )
        except Exception as e:
            code, msg = map_chat_failure("no_provider", str(e))
            result = ChatCompletionResult(
                ok=False,
                error_code=code,
                error_message=msg,
                request_id=pf.request_id,
                path_used="test_injected",
            )
        _emit(
            "execution_done",
            {**result.safe_telemetry(), "latency_ms": round((time.monotonic() - t0) * 1000, 2)},
        )
        if result.ok and idem_key:
            _idem_put(idem_key, result)
        return result

    # Prefer governed local gateway when enabled
    local = _try_governed_local(ireq)
    if local is not None:
        local.conversation_id = req.conversation_id
        local.context_meta = ctx_meta
        _emit(
            "execution_done",
            {**local.safe_telemetry(), "latency_ms": round((time.monotonic() - t0) * 1000, 2)},
        )
        if local.ok and idem_key:
            _idem_put(idem_key, local)
        return local

    # Canonical multi-family transport (M22 adapters) — not llm.generate
    result = _execute_router_transport(
        ireq,
        prompt_b,
        system_b,
        cloud_allowed=bool(pf.cloud_allowed),
    )
    result.conversation_id = req.conversation_id
    result.context_meta = ctx_meta
    _emit(
        "execution_done",
        {**result.safe_telemetry(), "latency_ms": round((time.monotonic() - t0) * 1000, 2)},
    )
    if result.ok and idem_key:
        _idem_put(idem_key, result)
    return result


def run_chat_stream(
    prompt: str = "",
    system: str = "",
    *,
    chat_request: Optional[ChatRequest] = None,
    inject_fn: Optional[InjectFn] = None,
    message: Optional[dict[str, Any]] = None,
    execution: Optional[dict[str, Any]] = None,
    citations: Optional[list] = None,
    words_per_chunk: int = 8,
) -> Iterator[ChatStreamEvent]:
    """Non-streaming completion + normalized stream event lifecycle.

    Same governance as run_chat_completion; delivery differs only.
    """
    result = run_chat_completion(
        prompt,
        system,
        chat_request=chat_request,
        inject_fn=inject_fn,
    )
    if result.cancelled:
        yield from stream_lifecycle(
            request_id=result.request_id,
            conversation_id=result.conversation_id,
            cancelled=True,
            full_text=result.text,
        )
        return
    if not result.ok:
        yield from stream_lifecycle(
            request_id=result.request_id,
            conversation_id=result.conversation_id,
            error=RuntimeError(result.error_message or result.error_code),
            full_text=result.text,
        )
        return
    yield from stream_lifecycle(
        request_id=result.request_id,
        conversation_id=result.conversation_id,
        full_text=result.text,
        message=message or {"content": result.text, "role": "assistant"},
        execution=execution,
        citations=citations,
        usage=result.usage or {"tokens": result.tokens},
        words_per_chunk=words_per_chunk,
    )


def chat_runtime_snapshot() -> dict[str, Any]:
    return {
        "schema": "m23.chat_runtime.v1",
        "milestone": "M23",
        "governed_chat_default": GOVERNED_CHAT_DEFAULT,
        "legacy_chat_execution": LEGACY_CHAT_EXECUTION,
        "runtime_authority": RUNTIME_AUTHORITY,
        "context_builder_authority": CONTEXT_BUILDER_AUTHORITY,
        "stream_event_authority": STREAM_EVENT_AUTHORITY,
        "path_id": PATH_ID,
        "caller_id": CALLER_CHAT_ENGINE,
        "production_certified": False,
        "idempotency_entries": len(_IDEM),
    }


def tools_are_separately_governed() -> bool:
    """Chat never executes tools; ExecutionGateway remains authority."""
    return True


def trading_tools_forbidden_in_chat() -> bool:
    return True
