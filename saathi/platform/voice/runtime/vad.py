"""Energy-based Voice Activity Detector for the centralized Voice Runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import DEFAULT_MIN_SPEECH_MS, DEFAULT_SILENCE_TIMEOUT_MS


@dataclass
class VadConfig:
    sensitivity: float = 0.5
    frame_ms: float = 20.0
    min_speech_ms: float = DEFAULT_MIN_SPEECH_MS
    silence_timeout_ms: float = DEFAULT_SILENCE_TIMEOUT_MS
    # False-positive protection: require contiguous speech frames
    min_speech_frames: int = 3
    # Interruption detection threshold while assistant is speaking
    interruption_energy_multiplier: float = 2.2


@dataclass
class VadResult:
    speech_frames: list[bool]
    speech_started: bool
    speech_ended: bool
    silence_timeout: bool
    interruption_detected: bool
    speech_ms: float
    silence_ms: float
    false_positive_suppressed: bool = False


class VoiceActivityDetector:
    """Provider-neutral VAD used by VoiceInputService and interruption paths.

    Real RMS energy vs adaptive noise floor. Not a neural VAD; swap-compatible
    via the same process() signature.
    """

    def __init__(self, config: VadConfig | None = None):
        self.config = config or VadConfig()
        self._noise_floor = 0.01
        self._in_speech = False
        self._silence_ms = 0.0
        self._speech_ms = 0.0
        self._contiguous_speech_frames = 0

    def process(
        self,
        samples: Sequence[float],
        sample_rate: int = 16_000,
        *,
        listening_for_interruption: bool = False,
    ) -> VadResult:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        frame_len = max(1, int(sample_rate * self.config.frame_ms / 1000))
        threshold = self._noise_floor * (2.5 - 2.0 * max(0.0, min(1.0, self.config.sensitivity)))
        speech_frames: list[bool] = []
        started = ended = timeout = interruption = false_positive = False

        for index in range(0, len(samples), frame_len):
            frame = samples[index : index + frame_len]
            energy = self._frame_energy(frame)
            is_speech = energy > max(threshold, 1e-6)
            speech_frames.append(is_speech)

            if is_speech:
                self._contiguous_speech_frames += 1
                if not self._in_speech:
                    if self._contiguous_speech_frames >= max(1, self.config.min_speech_frames):
                        self._in_speech = True
                        started = True
                        self._speech_ms = self.config.frame_ms * self._contiguous_speech_frames
                        if listening_for_interruption:
                            if energy >= threshold * self.config.interruption_energy_multiplier:
                                interruption = True
                    else:
                        # Hold start until min frames — false-positive protection
                        false_positive = True
                else:
                    self._speech_ms += self.config.frame_ms
                self._silence_ms = 0.0
            else:
                self._contiguous_speech_frames = 0
                self._noise_floor = 0.98 * self._noise_floor + 0.02 * energy
                if self._in_speech:
                    self._silence_ms += self.config.frame_ms
                    if self._silence_ms >= self.config.silence_timeout_ms:
                        if self._speech_ms >= self.config.min_speech_ms:
                            ended = True
                            timeout = True
                        else:
                            false_positive = True
                        self._in_speech = False
                        self._silence_ms = 0.0
                        self._speech_ms = 0.0

        return VadResult(
            speech_frames=speech_frames,
            speech_started=started,
            speech_ended=ended,
            silence_timeout=timeout,
            interruption_detected=interruption,
            speech_ms=self._speech_ms,
            silence_ms=self._silence_ms,
            false_positive_suppressed=false_positive,
        )

    @staticmethod
    def _frame_energy(frame: Sequence[float]) -> float:
        if not frame:
            return 0.0
        total = 0.0
        for sample in frame:
            value = float(sample)
            total += value * value
        return (total / len(frame)) ** 0.5

    def reset(self) -> None:
        self._noise_floor = 0.01
        self._in_speech = False
        self._silence_ms = 0.0
        self._speech_ms = 0.0
        self._contiguous_speech_frames = 0
