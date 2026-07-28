"""Provider-neutral speech and voice-profile contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import re
from typing import Any

from saathi.voice_os.segmentation import voice_render


MAX_SPEECH_TEXT_CHARS = 4_000
MAX_AUDIO_BYTES = 32 * 1024 * 1024
DEFAULT_RETENTION_SECONDS = 24 * 60 * 60
MAX_IDEMPOTENCY_CHARS = 120
MAX_QUEUE_DEPTH = 8

_LANGUAGE = re.compile(r"^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_SECRET_MARKERS = (
    "authorization: bearer",
    "begin rsa private key",
    "begin openssh private key",
    "password=",
    "api_key=",
    "secret_key=",
)
_MARKDOWN_LINK = re.compile(r"\[([^\]\n]{1,300})\]\((?:https?://|mailto:)[^)]+\)")


class VoiceValidationError(ValueError):
    pass


class SpeechState(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    SYNTHESIZING = "synthesizing"
    STREAMING = "streaming"
    PLAYING = "playing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    EXPIRED = "expired"


TERMINAL_SPEECH_STATES = frozenset(
    {
        SpeechState.COMPLETED,
        SpeechState.CANCELLED,
        SpeechState.FAILED,
        SpeechState.UNAVAILABLE,
        SpeechState.EXPIRED,
    }
)


SPEECH_TRANSITIONS: dict[SpeechState, frozenset[SpeechState]] = {
    SpeechState.QUEUED: frozenset(
        {SpeechState.PREPARING, SpeechState.CANCELLED, SpeechState.EXPIRED}
    ),
    SpeechState.PREPARING: frozenset(
        {
            SpeechState.SYNTHESIZING,
            SpeechState.CANCELLED,
            SpeechState.FAILED,
            SpeechState.UNAVAILABLE,
        }
    ),
    SpeechState.SYNTHESIZING: frozenset(
        {
            SpeechState.STREAMING,
            SpeechState.COMPLETED,
            SpeechState.CANCELLED,
            SpeechState.FAILED,
            SpeechState.UNAVAILABLE,
        }
    ),
    SpeechState.STREAMING: frozenset(
        {
            SpeechState.PLAYING,
            SpeechState.COMPLETED,
            SpeechState.CANCELLED,
            SpeechState.FAILED,
        }
    ),
    SpeechState.PLAYING: frozenset(
        {SpeechState.COMPLETED, SpeechState.CANCELLED, SpeechState.FAILED}
    ),
    SpeechState.COMPLETED: frozenset({SpeechState.EXPIRED}),
    SpeechState.CANCELLED: frozenset(),
    SpeechState.FAILED: frozenset(),
    SpeechState.UNAVAILABLE: frozenset(),
    SpeechState.EXPIRED: frozenset(),
}


def bounded(
    value: Any,
    name: str,
    *,
    maximum: int,
    required: bool = False,
    reject_secrets: bool = False,
) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise VoiceValidationError(f"{name} is required")
    if len(text) > maximum:
        raise VoiceValidationError(f"{name} exceeds {maximum} characters")
    if reject_secrets and any(marker in text.lower() for marker in _SECRET_MARKERS):
        raise VoiceValidationError(f"{name} contains prohibited credential material")
    return text


def safe_identifier(value: Any, name: str, *, required: bool = False) -> str:
    text = bounded(value, name, maximum=160, required=required)
    if text and not _SAFE_ID.fullmatch(text):
        raise VoiceValidationError(f"{name} contains unsupported characters")
    return text


def normalize_language(value: Any) -> str:
    language = bounded(value or "en-US", "language", maximum=16, required=True)
    if not _LANGUAGE.fullmatch(language):
        raise VoiceValidationError("language must be a short BCP-47 style code")
    return language.replace("_", "-")


@dataclass(frozen=True)
class SpeechRequest:
    request_id: str
    organization_id: str
    workspace_id: str
    user_id: str
    source: str
    text: str
    language: str = "en-US"
    voice_id: str = ""
    voice_profile_id: str = ""
    speaking_rate: float = 1.0
    style: str = ""
    output_format: str = "aiff"
    streaming: bool = False
    priority: int = 50
    correlation_id: str = ""
    provider: str = "auto"
    idempotency_key: str = ""

    @classmethod
    def from_payload(cls, ctx, payload: dict[str, Any]) -> "SpeechRequest":
        raw_text = bounded(
            payload.get("text"),
            "text",
            maximum=MAX_SPEECH_TEXT_CHARS,
            required=True,
            reject_secrets=True,
        )
        cleaned = voice_render(_MARKDOWN_LINK.sub(r"\1", raw_text))
        if not cleaned:
            raise VoiceValidationError("text has no speakable content")
        try:
            rate = float(payload.get("speaking_rate", 1.0))
        except (TypeError, ValueError) as exc:
            raise VoiceValidationError("speaking_rate must be numeric") from exc
        if not 0.5 <= rate <= 2.0:
            raise VoiceValidationError("speaking_rate must be between 0.5 and 2.0")
        try:
            priority = int(payload.get("priority", 50))
        except (TypeError, ValueError) as exc:
            raise VoiceValidationError("priority must be an integer") from exc
        if not 0 <= priority <= 100:
            raise VoiceValidationError("priority must be between 0 and 100")
        output_format = str(payload.get("output_format", "aiff")).lower().strip()
        if output_format not in {"aiff", "wav"}:
            raise VoiceValidationError("output_format must be aiff or wav")
        provider = str(payload.get("provider", "auto")).lower().strip()
        if provider not in {"auto", "macos_system", "voxcpm", "unavailable"}:
            raise VoiceValidationError("unknown speech provider")
        return cls(
            request_id=safe_identifier(payload.get("request_id"), "request_id"),
            organization_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            user_id=ctx.user_id,
            source=bounded(payload.get("source", "assistant"), "source", maximum=80),
            text=cleaned,
            language=normalize_language(payload.get("language", "en-US")),
            voice_id=bounded(payload.get("voice_id"), "voice_id", maximum=120),
            voice_profile_id=safe_identifier(
                payload.get("voice_profile_id"), "voice_profile_id"
            ),
            speaking_rate=rate,
            style=bounded(payload.get("style"), "style", maximum=500),
            output_format=output_format,
            streaming=bool(payload.get("streaming", False)),
            priority=priority,
            correlation_id=safe_identifier(
                payload.get("correlation_id"), "correlation_id"
            ),
            provider=provider,
            idempotency_key=bounded(
                payload.get("idempotency_key"),
                "idempotency_key",
                maximum=MAX_IDEMPOTENCY_CHARS,
            ),
        )

    @property
    def text_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def persisted_metadata(self) -> dict[str, Any]:
        """Request metadata safe to persist. The speech text is deliberately absent."""
        return {
            "request_id": self.request_id,
            "source": self.source,
            "language": self.language,
            "voice_id": self.voice_id,
            "voice_profile_id": self.voice_profile_id,
            "speaking_rate": self.speaking_rate,
            "style_present": bool(self.style),
            "output_format": self.output_format,
            "streaming": self.streaming,
            "priority": self.priority,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True)
class ProviderSynthesis:
    provider: str
    output_format: str
    sample_rate: int
    artifact_bytes: int
    duration_seconds: float = 0.0
    first_audio_ms: float = 0.0
    total_ms: float = 0.0
    streaming_state: str = "artifact_ready"


@dataclass(frozen=True)
class SpeechOperation:
    operation_id: str
    organization_id: str
    workspace_id: str
    user_id: str
    state: str
    requested_provider: str
    provider: str = ""
    request_metadata: dict[str, Any] = field(default_factory=dict)
    text_sha256: str = ""
    text_length: int = 0
    artifact_id: str = ""
    artifact_name: str = ""
    output_format: str = "aiff"
    sample_rate: int = 0
    duration_seconds: float = 0.0
    artifact_bytes: int = 0
    streaming_state: str = "not_started"
    fallback_used: bool = False
    fallback_reason: str = ""
    error_category: str = ""
    idempotency_key: str = ""
    cancel_requested: bool = False
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    expires_at: float = 0.0
    updated_at: float = 0.0
    version: int = 1

    def is_terminal(self) -> bool:
        return SpeechState(self.state) in TERMINAL_SPEECH_STATES

    def to_public(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("artifact_name", None)
        data.pop("text_sha256", None)
        data["audio_available"] = bool(
            self.artifact_id and self.state == SpeechState.COMPLETED.value
        )
        return data


@dataclass(frozen=True)
class VoiceProfile:
    profile_id: str
    organization_id: str
    workspace_id: str
    owner_id: str
    display_name: str
    provider: str = "auto"
    provider_voice_id: str = ""
    language: str = "en-US"
    style: str = ""
    rate: float = 1.0
    pitch: float = 0.0
    reference_artifact_id: str = ""
    cloning_consent_state: str = "not_requested"
    module_preference: str = ""
    accessibility_rate: float = 1.0
    status: str = "active"
    builtin: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0
    version: int = 1

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


YETI_STYLE = (
    "Warm, calm, encouraging adult teacher; clear international English; friendly "
    "and confident; medium-low pitch; natural conversational rhythm; moderately "
    "slow pace; precise pronunciation; gentle energy; never theatrical, robotic, "
    "childish, or overly dramatic."
)


def builtin_profiles(org_id: str, workspace_id: str, owner_id: str) -> list[VoiceProfile]:
    return [
        VoiceProfile(
            profile_id="saathi_default",
            organization_id=org_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            display_name="SaathiOS Default",
            provider="auto",
            language="en-US",
            style="Clear, calm, concise local assistant voice.",
            builtin=True,
        ),
        VoiceProfile(
            profile_id="yeti_teacher",
            organization_id=org_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            display_name="Yeti Teacher",
            provider="auto",
            language="en-US",
            style=YETI_STYLE,
            rate=0.9,
            accessibility_rate=0.9,
            builtin=True,
        ),
    ]


def validate_profile_payload(
    payload: dict[str, Any], *, profile_id: str = ""
) -> dict[str, Any]:
    provider = str(payload.get("provider", "auto")).lower().strip()
    if provider not in {"auto", "macos_system", "voxcpm"}:
        raise VoiceValidationError("unknown voice profile provider")
    try:
        rate = float(payload.get("rate", 1.0))
        accessibility_rate = float(payload.get("accessibility_rate", rate))
        pitch = float(payload.get("pitch", 0.0))
    except (TypeError, ValueError) as exc:
        raise VoiceValidationError("rate and pitch values must be numeric") from exc
    if not 0.5 <= rate <= 2.0 or not 0.5 <= accessibility_rate <= 2.0:
        raise VoiceValidationError("speech rate must be between 0.5 and 2.0")
    if not -12.0 <= pitch <= 12.0:
        raise VoiceValidationError("pitch must be between -12 and 12")
    reference = safe_identifier(
        payload.get("reference_artifact_id"), "reference_artifact_id"
    )
    consent = str(payload.get("cloning_consent_state", "not_requested")).strip()
    if consent not in {"not_requested", "revoked"}:
        raise VoiceValidationError(
            "cloning consent cannot be activated in this platform version"
        )
    if reference:
        raise VoiceValidationError(
            "reference voice metadata is disabled until cloning safety is certified"
        )
    status = str(payload.get("status", "active")).lower().strip()
    if status not in {"active", "disabled"}:
        raise VoiceValidationError("profile status must be active or disabled")
    return {
        "profile_id": safe_identifier(profile_id, "profile_id"),
        "display_name": bounded(
            payload.get("display_name"), "display_name", maximum=100, required=True
        ),
        "provider": provider,
        "provider_voice_id": bounded(
            payload.get("provider_voice_id"), "provider_voice_id", maximum=120
        ),
        "language": normalize_language(payload.get("language", "en-US")),
        "style": bounded(payload.get("style"), "style", maximum=500),
        "rate": rate,
        "pitch": pitch,
        "reference_artifact_id": reference,
        "cloning_consent_state": consent,
        "module_preference": bounded(
            payload.get("module_preference"), "module_preference", maximum=80
        ),
        "accessibility_rate": accessibility_rate,
        "status": status,
    }
