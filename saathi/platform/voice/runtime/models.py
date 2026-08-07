"""Real-time voice conversation contracts.

Extends the M74 speech-output foundation without replacing SpeechService.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any

from saathi.platform.voice.models import (
    VoiceValidationError,
    bounded,
    normalize_language,
    safe_identifier,
)


MAX_TRANSCRIPT_CHARS = 8_000
MAX_PARTIAL_CHARS = 2_000
MAX_HISTORY_TURNS = 40
MAX_SESSIONS_PER_USER = 8
MAX_RECORDING_SECONDS = 60
MIN_RECORDING_SECONDS = 0.15
DEFAULT_SAMPLE_RATE = 16_000
MAX_SAMPLE_RATE = 48_000
MAX_AUDIO_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_QUEUE_PLAYBACK = 4
DEFAULT_SILENCE_TIMEOUT_MS = 900.0
DEFAULT_MIN_SPEECH_MS = 150.0
SESSION_TTL_SECONDS = 2 * 60 * 60

_SAFE_MODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,39}$")


class InputMode(str, Enum):
    IDLE = "idle"
    PUSH_TO_TALK = "push_to_talk"
    HOLD_TO_TALK = "hold_to_talk"
    TOGGLE = "toggle"


class InputState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    RECORDING = "recording"
    PROCESSING = "processing"
    ERROR = "error"
    CANCELLED = "cancelled"


class ConversationState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    RESPONDING = "RESPONDING"
    INTERRUPTED = "INTERRUPTED"
    FINISHED = "FINISHED"
    FAILED = "FAILED"


TERMINAL_CONVERSATION_STATES = frozenset(
    {
        ConversationState.FINISHED,
        ConversationState.FAILED,
    }
)


CONVERSATION_TRANSITIONS: dict[ConversationState, frozenset[ConversationState]] = {
    ConversationState.IDLE: frozenset(
        {
            ConversationState.LISTENING,
            ConversationState.FAILED,
            ConversationState.FINISHED,
        }
    ),
    ConversationState.LISTENING: frozenset(
        {
            ConversationState.THINKING,
            ConversationState.INTERRUPTED,
            ConversationState.FINISHED,
            ConversationState.FAILED,
            ConversationState.IDLE,
        }
    ),
    ConversationState.THINKING: frozenset(
        {
            ConversationState.RESPONDING,
            ConversationState.INTERRUPTED,
            ConversationState.FAILED,
            ConversationState.FINISHED,
        }
    ),
    ConversationState.RESPONDING: frozenset(
        {
            ConversationState.LISTENING,
            ConversationState.INTERRUPTED,
            ConversationState.FINISHED,
            ConversationState.FAILED,
            ConversationState.IDLE,
        }
    ),
    ConversationState.INTERRUPTED: frozenset(
        {
            ConversationState.LISTENING,
            ConversationState.THINKING,
            ConversationState.FINISHED,
            ConversationState.FAILED,
            ConversationState.IDLE,
        }
    ),
    ConversationState.FINISHED: frozenset(),
    ConversationState.FAILED: frozenset({ConversationState.IDLE, ConversationState.LISTENING}),
}


class PlaybackState(str, Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


class TranscriptRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class TranscriptEntry:
    entry_id: str
    role: str
    text: str
    is_partial: bool = False
    is_final: bool = True
    provider: str = ""
    confidence: float = 0.0
    speech_operation_id: str = ""
    created_at: float = 0.0
    interrupted: bool = False

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InterruptionRecord:
    interruption_id: str
    reason: str
    from_state: str
    to_state: str
    preserved_text: str = ""
    created_at: float = 0.0

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConversationSession:
    session_id: str
    organization_id: str
    workspace_id: str
    user_id: str
    conversation_id: str = ""
    state: str = ConversationState.IDLE.value
    input_mode: str = InputMode.TOGGLE.value
    input_state: str = InputState.IDLE.value
    playback_state: str = PlaybackState.IDLE.value
    stt_provider: str = "auto"
    voice_profile_id: str = "yeti_teacher"
    sample_rate: int = DEFAULT_SAMPLE_RATE
    max_recording_seconds: float = 30.0
    silence_timeout_ms: float = DEFAULT_SILENCE_TIMEOUT_MS
    min_speech_ms: float = DEFAULT_MIN_SPEECH_MS
    partial_user_transcript: str = ""
    partial_assistant_response: str = ""
    active_speech_operation_id: str = ""
    active_playback_id: str = ""
    error_category: str = ""
    error_message: str = ""
    evidence_id: str = ""
    project_id: str = ""
    locale: str = "en-US"
    yeti_mode: str = "general"  # general | ielts | saathios_help | hcg | trading_guidance
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    last_activity_at: float = 0.0
    expires_at: float = 0.0
    transcript: list[TranscriptEntry] = field(default_factory=list)
    interruptions: list[InterruptionRecord] = field(default_factory=list)

    def to_public(self, *, include_history: bool = True) -> dict[str, Any]:
        payload = {
            "session_id": self.session_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "state": self.state,
            "input_mode": self.input_mode,
            "input_state": self.input_state,
            "playback_state": self.playback_state,
            "stt_provider": self.stt_provider,
            "voice_profile_id": self.voice_profile_id,
            "sample_rate": self.sample_rate,
            "max_recording_seconds": self.max_recording_seconds,
            "silence_timeout_ms": self.silence_timeout_ms,
            "min_speech_ms": self.min_speech_ms,
            "partial_user_transcript": self.partial_user_transcript,
            "partial_assistant_response": self.partial_assistant_response,
            "active_speech_operation_id": self.active_speech_operation_id,
            "active_playback_id": self.active_playback_id,
            "error_category": self.error_category,
            "error_message": self.error_message,
            "evidence_id": self.evidence_id,
            "project_id": self.project_id,
            "locale": self.locale,
            "yeti_mode": self.yeti_mode,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_activity_at": self.last_activity_at,
            "expires_at": self.expires_at,
            "terminal": ConversationState(self.state) in TERMINAL_CONVERSATION_STATES,
        }
        if include_history:
            payload["transcript"] = [entry.to_public() for entry in self.transcript[-MAX_HISTORY_TURNS:]]
            payload["interruptions"] = [
                item.to_public() for item in self.interruptions[-20:]
            ]
        return payload


def validate_session_create(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("input_mode") or InputMode.TOGGLE.value).strip().lower()
    if mode not in {m.value for m in InputMode}:
        raise VoiceValidationError("unsupported input_mode")
    stt = str(payload.get("stt_provider") or "auto").strip().lower()
    if stt not in {"auto", "macos_speech", "whisper_compatible", "browser", "unavailable"}:
        raise VoiceValidationError("unsupported stt_provider")
    try:
        sample_rate = int(payload.get("sample_rate") or DEFAULT_SAMPLE_RATE)
        max_recording = float(payload.get("max_recording_seconds") or 30.0)
        silence_ms = float(payload.get("silence_timeout_ms") or DEFAULT_SILENCE_TIMEOUT_MS)
        min_speech = float(payload.get("min_speech_ms") or DEFAULT_MIN_SPEECH_MS)
    except (TypeError, ValueError) as exc:
        raise VoiceValidationError("numeric session settings are invalid") from exc
    if not 8_000 <= sample_rate <= MAX_SAMPLE_RATE:
        raise VoiceValidationError("sample_rate must be between 8000 and 48000")
    if not 1.0 <= max_recording <= MAX_RECORDING_SECONDS:
        raise VoiceValidationError(
            f"max_recording_seconds must be between 1 and {MAX_RECORDING_SECONDS}"
        )
    if not 200.0 <= silence_ms <= 5_000.0:
        raise VoiceValidationError("silence_timeout_ms must be between 200 and 5000")
    if not 50.0 <= min_speech <= 2_000.0:
        raise VoiceValidationError("min_speech_ms must be between 50 and 2000")
    yeti_mode = str(payload.get("yeti_mode") or "general").strip().lower()
    if yeti_mode not in {
        "general",
        "ielts",
        "saathios_help",
        "hcg",
        "trading_guidance",
    }:
        raise VoiceValidationError("unsupported yeti_mode")
    locale = normalize_language(payload.get("locale") or "en-US")
    return {
        "input_mode": mode,
        "stt_provider": stt,
        "voice_profile_id": safe_identifier(
            payload.get("voice_profile_id") or "yeti_teacher",
            "voice_profile_id",
            required=True,
        ),
        "sample_rate": sample_rate,
        "max_recording_seconds": max_recording,
        "silence_timeout_ms": silence_ms,
        "min_speech_ms": min_speech,
        "conversation_id": safe_identifier(
            payload.get("conversation_id"), "conversation_id"
        ),
        "project_id": safe_identifier(payload.get("project_id"), "project_id"),
        "locale": locale,
        "yeti_mode": yeti_mode,
    }


def validate_transcript_text(text: Any, *, partial: bool = False) -> str:
    limit = MAX_PARTIAL_CHARS if partial else MAX_TRANSCRIPT_CHARS
    return bounded(
        text,
        "transcript",
        maximum=limit,
        required=not partial,
        reject_secrets=True,
    )


def yeti_system_preamble(mode: str) -> str:
    base = (
        "You are Yeti, the warm conversational voice of SaathiOS. Speak naturally, "
        "concisely, and helpfully. Remember the current conversation. Never use "
        "emotional manipulation, pressure, or deceptive urgency."
    )
    extras = {
        "ielts": " Support IELTS coaching with clear band-focused guidance.",
        "saathios_help": " Help the user navigate and understand SaathiOS features.",
        "hcg": " Support HCG business questions with practical local-first advice.",
        "trading_guidance": (
            " Provide educational trading guidance only. Never place trades, "
            "override Trading Guardian, or claim live financial authority."
        ),
        "general": " Answer conversationally across everyday assistant topics.",
    }
    return base + extras.get(mode, extras["general"])
