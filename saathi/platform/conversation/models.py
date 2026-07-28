"""Provider-neutral conversation contracts for SaathiOS Live Conversational Intelligence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
import time
from typing import Any

MAX_USER_MESSAGE_CHARS = 4_000
MAX_SYSTEM_CHARS = 6_000
MAX_HISTORY_TURNS = 16
MAX_CONTEXT_CHARS = 12_000
MAX_RESPONSE_CHARS = 4_000
MAX_TOKENS_DEFAULT = 512
MAX_TOKENS_CEILING = 1_024
GENERATION_TIMEOUT_SEC = 60.0
MAX_CONCURRENT_GENERATIONS = 2
MAX_STREAM_EVENTS = 500
SUMMARY_TRIGGER_TURNS = 12

_SECRET_MARKERS = (
    "authorization: bearer",
    "begin rsa private key",
    "api_key=",
    "secret_key=",
    "password=",
)


class ConversationValidationError(ValueError):
    pass


class StreamEventType(str, Enum):
    STARTED = "started"
    TEXT_DELTA = "text_delta"
    SEGMENT_READY = "segment_ready"
    INTENT_PROPOSED = "intent_proposed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    LATE_CHUNK_REJECTED = "late_chunk_rejected"


class ActionKind(str, Enum):
    INFORMATIONAL = "informational"
    SUGGESTED_ACTION = "suggested_action"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"
    EXECUTED = "executed"  # never set by model path; only platform after gateway
    FAILED = "failed"


@dataclass
class ConversationMessage:
    role: str  # system | user | assistant
    content: str
    created_at: float = field(default_factory=time.time)
    interrupted: bool = False
    provider: str = ""
    model: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content[:MAX_RESPONSE_CHARS],
            "created_at": self.created_at,
            "interrupted": self.interrupted,
            "provider": self.provider,
            "model": self.model,
        }


@dataclass
class ConversationRequest:
    request_id: str
    organization_id: str
    workspace_id: str
    user_id: str
    message: str
    session_id: str = ""
    conversation_id: str = ""
    yeti_mode: str = "general"
    locale: str = "en-US"
    history: list[ConversationMessage] = field(default_factory=list)
    project_id: str = ""
    mission_id: str = ""
    module_context: str = ""
    max_tokens: int = MAX_TOKENS_DEFAULT
    timeout_seconds: float = GENERATION_TIMEOUT_SEC
    stream: bool = True
    provider: str = "auto"
    correlation_id: str = ""

    def to_safe_audit(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "yeti_mode": self.yeti_mode,
            "message_chars": len(self.message or ""),
            "history_turns": len(self.history),
            "max_tokens": self.max_tokens,
            "provider": self.provider,
            "stream": self.stream,
        }


@dataclass
class ConversationStreamEvent:
    event: str
    request_id: str
    text: str = ""
    partial: bool = False
    provider: str = ""
    model: str = ""
    sequence: int = 0
    cancelled: bool = False
    error_code: str = ""
    error_message: str = ""
    action_kind: str = ActionKind.INFORMATIONAL.value
    intent: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_public(self) -> dict[str, Any]:
        out = {
            "event": self.event,
            "request_id": self.request_id,
            "text": self.text,
            "partial": self.partial,
            "provider": self.provider,
            "model": self.model,
            "sequence": self.sequence,
            "cancelled": self.cancelled,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "action_kind": self.action_kind,
            "ts": self.ts,
        }
        if self.intent:
            out["intent"] = {
                k: v
                for k, v in self.intent.items()
                if k not in {"raw", "provider_payload", "credentials"}
            }
        return out


@dataclass
class ConversationResult:
    ok: bool
    request_id: str
    text: str = ""
    provider: str = ""
    model: str = ""
    streamed: bool = False
    cancelled: bool = False
    partial: bool = False
    error_code: str = ""
    error_message: str = ""
    action_kind: str = ActionKind.INFORMATIONAL.value
    intent: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    intelligence_kind: str = "model"  # model | unavailable | test_injected

    def to_public(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "request_id": self.request_id,
            "text": self.text[:MAX_RESPONSE_CHARS],
            "provider": self.provider,
            "model": self.model,
            "streamed": self.streamed,
            "cancelled": self.cancelled,
            "partial": self.partial,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "action_kind": self.action_kind,
            "intent": self.intent,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "intelligence_kind": self.intelligence_kind,
            "text_chars": len(self.text or ""),
        }


def bounded_text(value: Any, name: str, *, maximum: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ConversationValidationError(f"{name} is required")
    if len(text) > maximum:
        raise ConversationValidationError(f"{name} exceeds {maximum} characters")
    if any(m in text.lower() for m in _SECRET_MARKERS):
        raise ConversationValidationError(f"{name} contains prohibited credential material")
    return text


def sanitize_for_speech(text: str) -> str:
    """Strip fragments that should not be spoken mid-stream."""
    t = text or ""
    t = re.sub(r"https?://\S+", " a link ", t)
    t = re.sub(r"`[^`]+`", " code ", t)
    t = re.sub(r"```[\s\S]*?```", " code omitted ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_safe_speech_segment(text: str) -> bool:
    cleaned = (text or "").strip()
    if len(cleaned) < 4:
        return False
    if "http://" in cleaned or "https://" in cleaned:
        return False
    if "```" in cleaned:
        return False
    # Prefer complete sentences for TTS
    return cleaned[-1:] in ".!?" or len(cleaned) >= 80
