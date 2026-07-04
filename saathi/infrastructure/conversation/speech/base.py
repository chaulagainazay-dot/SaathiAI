"""Speech driver contracts — STT / TTS / VAD / wake-word, provider-agnostic.

Departments never see Whisper / Kokoro / ElevenLabs; the Voice adapter routes to
whichever driver is available. Null/Echo drivers make the pipeline testable with
no audio stack installed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class SttDriver(ABC):
    name: str
    @abstractmethod
    def available(self) -> bool: ...
    @abstractmethod
    def transcribe(self, audio, *, locale: str = "en") -> str: ...


class TtsDriver(ABC):
    name: str
    @abstractmethod
    def available(self) -> bool: ...
    @abstractmethod
    def synthesize(self, text: str, *, locale: str = "en") -> bytes: ...


class VadDriver(ABC):
    name: str
    @abstractmethod
    def available(self) -> bool: ...
    @abstractmethod
    def is_speech(self, frame: bytes) -> bool: ...


# ── null/echo defaults (always available; used for tests + graceful degradation) ─
class EchoStt(SttDriver):
    """Transcribes by echoing text passed as `audio` (str) — deterministic tests."""
    name = "echo"
    def available(self) -> bool: return True
    def transcribe(self, audio, *, locale: str = "en") -> str:
        if isinstance(audio, str):
            return audio
        if isinstance(audio, (bytes, bytearray)):
            return audio.decode("utf-8", "ignore")
        return getattr(audio, "text", "")


class SilentTts(TtsDriver):
    """Encodes text as bytes (a real driver returns audio); never fails."""
    name = "silent"
    def available(self) -> bool: return True
    def synthesize(self, text: str, *, locale: str = "en") -> bytes:
        return text.encode("utf-8")


class EnergyVad(VadDriver):
    """Trivial energy gate — non-empty frame = speech. Replace with Silero."""
    name = "energy"
    def available(self) -> bool: return True
    def is_speech(self, frame: bytes) -> bool:
        return bool(frame) and any(frame)
