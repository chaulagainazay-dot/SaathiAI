"""Speech drivers — STT / TTS / VAD behind provider-agnostic contracts."""
from .base import (SttDriver, TtsDriver, VadDriver, EchoStt, SilentTts, EnergyVad)
from .whisper import WhisperStt
from .kokoro import KokoroTts


def best_stt() -> SttDriver:
    """Prefer a real installed STT; fall back to echo (deterministic)."""
    w = WhisperStt()
    return w if w.available() else EchoStt()


def best_tts() -> TtsDriver:
    k = KokoroTts()
    return k if k.available() else SilentTts()


__all__ = ["SttDriver", "TtsDriver", "VadDriver", "EchoStt", "SilentTts",
           "EnergyVad", "WhisperStt", "KokoroTts", "best_stt", "best_tts"]
