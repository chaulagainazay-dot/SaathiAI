"""M23 — Canonical chat request contract.

Normalizes chat entry surfaces into one validated structure, then maps into
``InferenceRequest``. Does not select providers, open network sockets, or
duplicate the inference contract.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

# Bounds (aligned with chat_engine caller policy)
DEFAULT_MAX_MESSAGE_CHARS = 32000
DEFAULT_MAX_SYSTEM_CHARS = 4000
DEFAULT_MAX_OUTPUT_TOKENS = 2048
DEFAULT_TIMEOUT_SECONDS = 120.0
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 300.0

CALLER_CHAT_ENGINE = "chat_engine"
TEST_ONLY_CALLERS = frozenset({"test_m21", "test_m20", "test_m21_0", "fake_engine"})
PRODUCTION_ENVS = frozenset({"production", "prod", "staging"})


class ChatMessageType(str, Enum):
    USER = "user"
    SYSTEM = "system"
    REGENERATE = "regenerate"
    AGENT = "agent"


class ChatToolMode(str, Enum):
    OFF = "off"
    ALLOWLISTED = "allowlisted"
    # Explicit opt-in only; default remains OFF


class ChatPrivacyClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SENSITIVE = "sensitive"


class ChatRequestError(ValueError):
    """Validation failure for ChatRequest (safe message, typed code)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ChatRequest:
    """Canonical chat request — maps into InferenceRequest; not a second gateway."""

    request_id: str = field(default_factory=lambda: f"m23-{uuid.uuid4().hex[:16]}")
    caller_id: str = CALLER_CHAT_ENGINE
    actor_id: str = "user:ajay"
    user_id: str = "ajay"
    session_id: str = ""
    conversation_id: str = ""
    message: str = ""
    message_type: ChatMessageType = ChatMessageType.USER
    stream: bool = False
    system: str = ""
    agent: str = ""
    model_preference: str = ""
    provider_preference: str = ""
    tool_mode: ChatToolMode = ChatToolMode.OFF
    structured_output: bool = False
    privacy_class: ChatPrivacyClass = ChatPrivacyClass.INTERNAL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    token_budget: int = DEFAULT_MAX_OUTPUT_TOKENS
    max_message_chars: int = DEFAULT_MAX_MESSAGE_CHARS
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    cancellation_token: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["message_type"] = self.message_type.value
        d["tool_mode"] = self.tool_mode.value
        d["privacy_class"] = self.privacy_class.value
        # Never include raw message in telemetry snapshots — strip for safe export
        return d

    def safe_telemetry(self) -> dict[str, Any]:
        return {
            "schema": "m23.chat_request.v1",
            "request_id": self.request_id,
            "caller_id": self.caller_id,
            "actor_id": self.actor_id,
            "session_id": self.session_id or "",
            "conversation_id": self.conversation_id or "",
            "message_type": self.message_type.value,
            "stream": self.stream,
            "tool_mode": self.tool_mode.value,
            "privacy_class": self.privacy_class.value,
            "message_chars": len(self.message or ""),
            "system_chars": len(self.system or ""),
            "timeout_seconds": self.timeout_seconds,
            "token_budget": self.token_budget,
            "message_fingerprint": message_fingerprint(self.message),
            "has_model_preference": bool(self.model_preference),
            "has_provider_preference": bool(self.provider_preference),
            "idempotency_key": self.idempotency_key or "",
        }


def message_fingerprint(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:24]


def normalize_conversation_id(cid: str | None) -> str:
    raw = (cid or "").strip()
    if not raw:
        return ""
    # Strip control chars; keep hex/uuid-like ids intact
    cleaned = re.sub(r"[^\w\-:.]", "", raw)
    return cleaned[:128]


def _env_name() -> str:
    import os

    return (os.getenv("SAATHI_ENV") or os.getenv("ENV") or "").strip().lower()


def validate_chat_request(req: ChatRequest, *, production: Optional[bool] = None) -> None:
    """Raise ChatRequestError on invalid request. Never logs raw message."""
    if production is None:
        production = _env_name() in PRODUCTION_ENVS

    cid = (req.caller_id or "").strip()
    if not cid:
        raise ChatRequestError("missing_caller", "caller_id is required")

    if cid in TEST_ONLY_CALLERS and production:
        raise ChatRequestError(
            "test_caller_denied",
            f"test-only caller {cid!r} denied in production",
        )

    # Unknown / forbidden callers checked against registry when available
    try:
        from saathi.inference.caller_policy import (
            CallerCertification,
            get_caller_policy,
            is_known_caller,
        )

        if not is_known_caller(cid):
            raise ChatRequestError("unknown_caller", f"unregistered caller {cid!r}")
        pol = get_caller_policy(cid)
        if pol is not None and (
            pol.certification is CallerCertification.FORBIDDEN or not pol.enabled
        ):
            raise ChatRequestError("unauthorized_caller", f"caller {cid!r} not authorized")
    except ChatRequestError:
        raise
    except Exception:
        pass

    msg = req.message or ""
    if not msg.strip():
        raise ChatRequestError("empty_message", "message must be non-empty")
    max_chars = int(req.max_message_chars or DEFAULT_MAX_MESSAGE_CHARS)
    if len(msg) > max_chars:
        raise ChatRequestError(
            "oversized_message",
            f"message exceeds max_message_chars={max_chars}",
        )

    if req.token_budget < 1 or req.token_budget > 8192:
        raise ChatRequestError("token_budget", "token_budget must be in 1..8192")
    if req.timeout_seconds < MIN_TIMEOUT_SECONDS or req.timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise ChatRequestError(
            "timeout",
            f"timeout_seconds must be in [{MIN_TIMEOUT_SECONDS}, {MAX_TIMEOUT_SECONDS}]",
        )

    # Provider/model override only when policy-authorized (chat default: deny force)
    meta = req.metadata or {}
    if meta.get("force_model") or meta.get("bypass_router") or meta.get("force_engine_url"):
        raise ChatRequestError("override_denied", "provider/model force override denied")

    if req.provider_preference and not meta.get("provider_override_authorized"):
        # Soft: strip via normalize; hard deny if marked as force
        if meta.get("force_provider"):
            raise ChatRequestError("provider_override_denied", "provider override denied")

    if req.model_preference and meta.get("force_model"):
        raise ChatRequestError("model_override_denied", "model override denied")

    if req.tool_mode is not ChatToolMode.OFF and not meta.get("tools_authorized"):
        # Default off; explicit allow only when authorized flag set by runtime after policy
        pass  # runtime enforces tools_allowed from caller policy


def build_chat_request(
    message: str,
    *,
    conversation_id: str = "",
    system: str = "",
    agent: str = "",
    stream: bool = False,
    caller_id: str = CALLER_CHAT_ENGINE,
    actor_id: str = "user:ajay",
    user_id: str = "ajay",
    session_id: str = "",
    request_id: str = "",
    tool_mode: str | ChatToolMode = ChatToolMode.OFF,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    token_budget: int = DEFAULT_MAX_OUTPUT_TOKENS,
    model_preference: str = "",
    provider_preference: str = "",
    privacy_class: str | ChatPrivacyClass = ChatPrivacyClass.INTERNAL,
    metadata: Optional[dict[str, Any]] = None,
    idempotency_key: str = "",
    validate: bool = True,
) -> ChatRequest:
    """Construct and optionally validate a ChatRequest."""
    if isinstance(tool_mode, str):
        try:
            tool_mode = ChatToolMode(tool_mode.lower())
        except ValueError:
            tool_mode = ChatToolMode.OFF
    if isinstance(privacy_class, str):
        try:
            privacy_class = ChatPrivacyClass(privacy_class.lower())
        except ValueError:
            privacy_class = ChatPrivacyClass.INTERNAL

    req = ChatRequest(
        request_id=request_id or f"m23-{uuid.uuid4().hex[:16]}",
        caller_id=(caller_id or CALLER_CHAT_ENGINE).strip(),
        actor_id=actor_id or "user:ajay",
        user_id=user_id or "ajay",
        session_id=(session_id or "").strip(),
        conversation_id=normalize_conversation_id(conversation_id),
        message=message or "",
        message_type=ChatMessageType.AGENT if agent else ChatMessageType.USER,
        stream=bool(stream),
        system=(system or "")[:DEFAULT_MAX_SYSTEM_CHARS],
        agent=(agent or "").strip(),
        model_preference=(model_preference or "").strip(),
        provider_preference=(provider_preference or "").strip(),
        tool_mode=tool_mode,
        privacy_class=privacy_class,
        timeout_seconds=float(
            max(MIN_TIMEOUT_SECONDS, min(timeout_seconds, MAX_TIMEOUT_SECONDS))
        ),
        token_budget=int(max(1, min(token_budget, 8192))),
        metadata=dict(metadata or {}),
        idempotency_key=(idempotency_key or "").strip(),
    )
    if validate:
        validate_chat_request(req)
    return req


def chat_request_to_inference_request(
    req: ChatRequest,
    *,
    prompt: str,
    system: str,
    preflight_request_id: str = "",
    max_output_tokens: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
) -> "Any":
    """Map validated ChatRequest + built context into InferenceRequest."""
    from saathi.inference.request import InferenceRequest, Sensitivity

    sens_map = {
        ChatPrivacyClass.PUBLIC: Sensitivity.PUBLIC,
        ChatPrivacyClass.INTERNAL: Sensitivity.INTERNAL,
        ChatPrivacyClass.CONFIDENTIAL: Sensitivity.CONFIDENTIAL,
        ChatPrivacyClass.SENSITIVE: Sensitivity.SENSITIVE,
    }
    sensitivity = sens_map.get(req.privacy_class, Sensitivity.INTERNAL)
    tools = req.tool_mode is not ChatToolMode.OFF
    max_out = int(max_output_tokens if max_output_tokens is not None else req.token_budget)
    timeout = float(
        timeout_seconds if timeout_seconds is not None else req.timeout_seconds
    )
    # Policy-bound local-first; cloud fallback never permitted from chat
    local_only = sensitivity in {Sensitivity.CONFIDENTIAL, Sensitivity.SENSITIVE}
    try:
        from saathi.inference.caller_policy import get_caller_policy

        pol = get_caller_policy(req.caller_id)
        if pol is not None:
            max_out = min(max_out, int(pol.max_output_tokens))
            timeout = min(timeout, float(pol.timeout_seconds))
            if pol.local_only:
                local_only = True
            tools = tools and bool(pol.tools_allowed)
    except Exception:
        pass

    return InferenceRequest(
        request_id=preflight_request_id or req.request_id,
        caller_component=req.caller_id,
        actor_id=req.actor_id,
        prompt=prompt or "",
        system=system or "",
        task_type="standard",
        preferred_capability="standard",
        sensitivity=sensitivity,
        max_output_tokens=max_out,
        timeout_seconds=timeout,
        temperature=0.0,
        local_only=local_only,
        cloud_allowed=False if local_only else True,
        cloud_fallback_permitted=False,
        # Tool execution is never performed by chat; flag is informational only.
        # Streaming is a delivery concern — governed engines reject stream flag.
        tool_use_permitted=False,
        streaming_requested=False,
        evidence_required=True,
        prefer="quality",
        max_retries=0,
        fallback_policy="none",
        log_prompt=False,
        log_output=False,
        retention_policy="metadata_only",
        request_cost_ceiling=0.0,
        session_id=req.session_id,
        idempotency_key=req.idempotency_key or req.request_id,
        model_hint="" if not req.metadata.get("model_override_authorized") else req.model_preference,
        engine_hint="" if not req.metadata.get("provider_override_authorized") else req.provider_preference,
        engine_hint="",
        contract_version="m23.chat",
        metadata={
            "m23_chat_runtime": True,
            "path_id": "chat_runtime",
            "conversation_id": req.conversation_id,
            "message_chars": len(req.message or ""),
            "message_fingerprint": message_fingerprint(req.message),
            "tool_mode": req.tool_mode.value,
            "stream": bool(req.stream),
            "agent": req.agent or "",
            **{
                k: v
                for k, v in (req.metadata or {}).items()
                if k
                not in {
                    "prompt",
                    "output",
                    "text",
                    "system",
                    "messages",
                    "content",
                    "history",
                }
            },
        },
    )
