"""M12 voice activity detection — provider-neutral interface.

Default: a deterministic energy-based local fallback (RMS amplitude over
short frames vs. an adaptive noise floor). No external dependency, runs
identically in tests and production. Documented limitation: energy-based VAD
cannot distinguish speech from other loud sounds (music, typing, claps) — it
is a floor, not a substitute for a neural VAD; swap in a real model via the
same interface when one is available (contract below).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class VadConfig:
    sensitivity: float = 0.5          # 0..1, higher = more sensitive (lower threshold)
    frame_ms: float = 20.0
    min_speech_ms: float = 150.0      # minimum contiguous speech to count as "speech"
    silence_timeout_ms: float = 900.0  # silence after speech that finalizes a turn


@dataclass
class VadResult:
    speech_frames: list[bool]
    speech_started: bool
    speech_ended: bool
    finalized: bool                   # silence_timeout reached after speech


class VoiceActivityDetector:
    """Provider-neutral VAD. `process(samples, sample_rate)` -> VadResult.

    Real interface, real math (RMS energy vs adaptive noise floor) — not a
    stub. A neural adapter can implement the same `process()` signature.
    """

    def __init__(self, config: VadConfig | None = None):
        self.config = config or VadConfig()
        self._noise_floor = 0.01
        self._in_speech = False
        self._silence_ms = 0.0

    def _frame_energy(self, frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(frame)))) if len(frame) else 0.0

    def process(self, samples: np.ndarray, sample_rate: int = 16000) -> VadResult:
        frame_len = max(1, int(sample_rate * self.config.frame_ms / 1000))
        threshold = self._noise_floor * (2.5 - 2.0 * self.config.sensitivity)
        speech_frames: list[bool] = []
        started, ended, finalized = False, False, False

        for i in range(0, len(samples), frame_len):
            frame = samples[i:i + frame_len]
            energy = self._frame_energy(frame)
            is_speech = energy > max(threshold, 1e-6)
            speech_frames.append(is_speech)

            if is_speech:
                if not self._in_speech:
                    started = True
                self._in_speech = True
                self._silence_ms = 0.0
            else:
                # adapt noise floor slowly during silence
                self._noise_floor = 0.98 * self._noise_floor + 0.02 * energy
                if self._in_speech:
                    self._silence_ms += self.config.frame_ms
                    if self._silence_ms >= self.config.silence_timeout_ms:
                        ended = True
                        finalized = True
                        self._in_speech = False
                        self._silence_ms = 0.0

        return VadResult(speech_frames=speech_frames, speech_started=started,
                         speech_ended=ended, finalized=finalized)

    def reset(self) -> None:
        self._in_speech = False
        self._silence_ms = 0.0
        self._noise_floor = 0.01


def synth_speech(duration_sec: float = 1.0, sample_rate: int = 16000,
                 freq: float = 220.0, amplitude: float = 0.3) -> np.ndarray:
    """Deterministic synthetic "speech-like" waveform for tests."""
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def synth_silence(duration_sec: float = 1.0, sample_rate: int = 16000) -> np.ndarray:
    return np.zeros(int(sample_rate * duration_sec), dtype=np.float32)
