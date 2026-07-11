"""M12 Voice OS — canonical typed session/turn models + state machines.

Voice never calls a model provider or tool directly: every turn resolves
through saathi.chat.engine.ChatEngine and, for approvals, through
saathi.agent_runtime.orchestrator.Orchestrator — the same gateway-only paths
M8/M10 already enforce.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class SessionState(str, Enum):
    CREATED = "created"
    CONNECTING = "connecting"
    READY = "ready"
    LISTENING = "listening"
    SPEECH_DETECTED = "speech_detected"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    PAUSED = "paused"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


_TERMINAL = {SessionState.COMPLETED, SessionState.CANCELLED, SessionState.FAILED}

_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.CREATED: {SessionState.CONNECTING, SessionState.CANCELLED, SessionState.FAILED},
    SessionState.CONNECTING: {SessionState.READY, SessionState.FAILED, SessionState.CANCELLED},
    SessionState.READY: {SessionState.LISTENING, SessionState.PAUSED,
                         SessionState.CANCELLED, SessionState.COMPLETED},
    SessionState.LISTENING: {SessionState.SPEECH_DETECTED, SessionState.PAUSED,
                             SessionState.CANCELLED, SessionState.RECOVERING,
                             SessionState.FAILED},
    SessionState.SPEECH_DETECTED: {SessionState.TRANSCRIBING, SessionState.LISTENING,
                                   SessionState.CANCELLED},
    SessionState.TRANSCRIBING: {SessionState.PROCESSING, SessionState.LISTENING,
                                SessionState.RECOVERING, SessionState.FAILED,
                                SessionState.CANCELLED},
    SessionState.PROCESSING: {SessionState.SPEAKING, SessionState.READY,
                              SessionState.INTERRUPTED, SessionState.FAILED,
                              SessionState.CANCELLED},
    SessionState.SPEAKING: {SessionState.READY, SessionState.LISTENING,
                            SessionState.INTERRUPTED, SessionState.PAUSED,
                            SessionState.CANCELLED, SessionState.COMPLETED},
    SessionState.INTERRUPTED: {SessionState.LISTENING, SessionState.READY,
                               SessionState.CANCELLED},
    SessionState.PAUSED: {SessionState.LISTENING, SessionState.READY,
                          SessionState.CANCELLED, SessionState.COMPLETED},
    SessionState.RECOVERING: {SessionState.READY, SessionState.LISTENING,
                              SessionState.FAILED, SessionState.CANCELLED},
    **{s: set() for s in _TERMINAL},
}


def is_terminal(state: SessionState) -> bool:
    return state in _TERMINAL


def can_transition(src: SessionState, dst: SessionState) -> bool:
    return dst in _TRANSITIONS.get(src, set())


class IllegalVoiceTransition(Exception):
    pass


def validate_transition(src: SessionState, dst: SessionState) -> None:
    if not can_transition(src, dst):
        raise IllegalVoiceTransition(f"illegal transition {src.value} → {dst.value}")


class TurnMode(str, Enum):
    HANDS_FREE = "hands_free"
    PUSH_TO_TALK = "push_to_talk"
    MANUAL = "manual"


class ChatMode(str, Enum):
    SOLO = "solo"
    TEAM = "team"


@dataclass
class VoiceSettings:
    stt_provider: str = "auto"
    tts_provider: str = "auto"
    voice: str = "default"
    input_language: str = "en"
    output_language: str = "en"
    turn_mode: TurnMode = TurnMode.HANDS_FREE
    silence_timeout_ms: int = 900
    vad_sensitivity: float = 0.5
    speech_rate: float = 1.0
    auto_playback: bool = True
    confirm_before_team: bool = False
    retain_raw_audio: bool = False   # opt-in only — privacy default OFF

    def to_dict(self) -> dict:
        d = asdict(self)
        d["turn_mode"] = self.turn_mode.value
        return d


@dataclass
class LatencyBreakdown:
    mic_ready_ms: float = 0.0
    speech_start_ms: float = 0.0
    speech_end_ms: float = 0.0
    transcript_final_ms: float = 0.0
    chat_submit_ms: float = 0.0
    memory_retrieval_ms: float = 0.0
    first_response_ms: float = 0.0
    first_tts_ms: float = 0.0
    first_audio_ms: float = 0.0
    turn_total_ms: float = 0.0
    bargein_stop_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)
