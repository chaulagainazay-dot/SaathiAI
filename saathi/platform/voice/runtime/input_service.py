"""VoiceInputService — microphone lifecycle authority (server-side).

Actual device capture is browser-owned (explicit gesture, loopback only).
This service tracks mode/state, bounds, VAD, cancellation, and recovery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Sequence

from saathi.platform.voice.models import VoiceValidationError

from .models import (
    MAX_AUDIO_UPLOAD_BYTES,
    MAX_RECORDING_SECONDS,
    InputMode,
    InputState,
)
from .vad import VadConfig, VoiceActivityDetector


@dataclass
class InputSession:
    mode: str = InputMode.IDLE.value
    state: str = InputState.IDLE.value
    sample_rate: int = 16_000
    max_recording_seconds: float = 30.0
    started_at: float = 0.0
    permission_granted: bool = False
    error: str = ""
    bytes_received: int = 0
    frames_received: int = 0
    cancel_requested: bool = False
    vad_events: list[dict[str, Any]] = field(default_factory=list)


class VoiceInputService:
    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        max_recording_seconds: float = 30.0,
        silence_timeout_ms: float = 900.0,
        min_speech_ms: float = 150.0,
    ):
        self.sample_rate = sample_rate
        self.max_recording_seconds = max(
            1.0, min(float(max_recording_seconds), MAX_RECORDING_SECONDS)
        )
        self.vad = VoiceActivityDetector(
            VadConfig(
                silence_timeout_ms=silence_timeout_ms,
                min_speech_ms=min_speech_ms,
            )
        )
        self._session = InputSession(
            sample_rate=self.sample_rate,
            max_recording_seconds=self.max_recording_seconds,
        )

    @property
    def state(self) -> str:
        return self._session.state

    @property
    def mode(self) -> str:
        return self._session.mode

    def snapshot(self) -> dict[str, Any]:
        s = self._session
        return {
            "mode": s.mode,
            "state": s.state,
            "sample_rate": s.sample_rate,
            "max_recording_seconds": s.max_recording_seconds,
            "started_at": s.started_at,
            "permission_granted": s.permission_granted,
            "error": s.error,
            "bytes_received": s.bytes_received,
            "frames_received": s.frames_received,
            "cancel_requested": s.cancel_requested,
            "vad_events": list(s.vad_events[-20:]),
            "background_recording": False,
            "hidden_activation": False,
            "loopback_only": True,
        }

    def set_permission(self, granted: bool) -> dict[str, Any]:
        self._session.permission_granted = bool(granted)
        if not granted and self._session.state in {
            InputState.LISTENING.value,
            InputState.RECORDING.value,
        }:
            self._session.state = InputState.ERROR.value
            self._session.error = "microphone_permission_denied"
        return self.snapshot()

    def start(
        self,
        mode: str = InputMode.TOGGLE.value,
        *,
        permission_granted: bool = True,
    ) -> dict[str, Any]:
        if mode not in {m.value for m in InputMode if m != InputMode.IDLE}:
            raise VoiceValidationError("unsupported input mode")
        if not permission_granted:
            self._session.state = InputState.ERROR.value
            self._session.error = "microphone_permission_required"
            self._session.permission_granted = False
            return self.snapshot()
        self.vad.reset()
        self._session = InputSession(
            mode=mode,
            state=InputState.LISTENING.value
            if mode == InputMode.PUSH_TO_TALK.value
            else InputState.RECORDING.value,
            sample_rate=self.sample_rate,
            max_recording_seconds=self.max_recording_seconds,
            started_at=time.time(),
            permission_granted=True,
        )
        return self.snapshot()

    def mark_recording(self) -> dict[str, Any]:
        if self._session.state not in {
            InputState.LISTENING.value,
            InputState.RECORDING.value,
        }:
            raise VoiceValidationError("cannot record from current input state")
        self._session.state = InputState.RECORDING.value
        if not self._session.started_at:
            self._session.started_at = time.time()
        return self.snapshot()

    def ingest_pcm(
        self,
        samples: Sequence[float],
        *,
        listening_for_interruption: bool = False,
    ) -> dict[str, Any]:
        if self._session.cancel_requested:
            self._session.state = InputState.CANCELLED.value
            return {**self.snapshot(), "vad": None}
        if self._session.state not in {
            InputState.LISTENING.value,
            InputState.RECORDING.value,
        }:
            raise VoiceValidationError("input is not capturing")
        elapsed = time.time() - (self._session.started_at or time.time())
        if elapsed > self._session.max_recording_seconds:
            self._session.state = InputState.PROCESSING.value
            return {
                **self.snapshot(),
                "vad": None,
                "bounded_duration_reached": True,
            }
        self._session.frames_received += 1
        self._session.bytes_received += len(samples) * 4
        if self._session.bytes_received > MAX_AUDIO_UPLOAD_BYTES:
            self._session.state = InputState.ERROR.value
            self._session.error = "audio_memory_limit"
            raise VoiceValidationError("audio memory limit exceeded")
        result = self.vad.process(
            samples,
            sample_rate=self._session.sample_rate,
            listening_for_interruption=listening_for_interruption,
        )
        event = {
            "speech_started": result.speech_started,
            "speech_ended": result.speech_ended,
            "silence_timeout": result.silence_timeout,
            "interruption_detected": result.interruption_detected,
            "false_positive_suppressed": result.false_positive_suppressed,
            "speech_ms": result.speech_ms,
            "silence_ms": result.silence_ms,
        }
        self._session.vad_events.append(event)
        if result.speech_started and self._session.state == InputState.LISTENING.value:
            self._session.state = InputState.RECORDING.value
        if result.silence_timeout or result.speech_ended:
            self._session.state = InputState.PROCESSING.value
        return {**self.snapshot(), "vad": event}

    def stop(self, *, process: bool = True) -> dict[str, Any]:
        if self._session.state in {InputState.IDLE.value, InputState.CANCELLED.value}:
            return self.snapshot()
        self._session.state = (
            InputState.PROCESSING.value if process else InputState.IDLE.value
        )
        return self.snapshot()

    def cancel(self) -> dict[str, Any]:
        self._session.cancel_requested = True
        self._session.state = InputState.CANCELLED.value
        self.vad.reset()
        return self.snapshot()

    def finish_processing(self) -> dict[str, Any]:
        self._session.state = InputState.IDLE.value
        self._session.mode = InputMode.IDLE.value
        self.vad.reset()
        return self.snapshot()

    def fail(self, error: str) -> dict[str, Any]:
        self._session.state = InputState.ERROR.value
        self._session.error = (error or "input_error")[:120]
        return self.snapshot()

    def restart_recovery(self) -> dict[str, Any]:
        """Safe cleanup + return to idle after error/cancel/timeout."""
        self.vad.reset()
        self._session = InputSession(
            sample_rate=self.sample_rate,
            max_recording_seconds=self.max_recording_seconds,
            permission_granted=self._session.permission_granted,
        )
        return self.snapshot()
