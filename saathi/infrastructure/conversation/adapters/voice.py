"""Voice adapter — exactly four methods; drivers stay hidden.

    voice.listen(audio) -> text     # STT
    voice.speak(text)   -> bytes    # TTS
    voice.interrupt()               # barge-in: stop speaking, mark interrupted
    voice.stop()                    # end the turn

Internally routes to whichever STT/TTS driver is available (Whisper, Kokoro,
ElevenLabs, …). Departments never know which.
"""
from __future__ import annotations

from ..events import VoiceEvent, emit


class VoiceAdapter:
    def __init__(self, *, stt=None, tts=None, vad=None, bus=None):
        from ..speech import best_stt, best_tts, EnergyVad
        self._stt = stt or best_stt()
        self._tts = tts or best_tts()
        self._vad = vad or EnergyVad()
        self._bus = bus
        self._interrupted = False
        self._speaking = False

    def listen(self, audio, *, locale: str = "en") -> str:
        emit(self._bus, VoiceEvent.STARTED, {"driver": self._stt.name})
        try:
            text = self._stt.transcribe(audio, locale=locale)
            emit(self._bus, VoiceEvent.FINISHED, {"chars": len(text)})
            return text
        except Exception as e:
            emit(self._bus, VoiceEvent.FAILED, {"error": str(e)})
            raise

    def speak(self, text: str, *, locale: str = "en") -> bytes:
        self._interrupted = False
        self._speaking = True
        try:
            return self._tts.synthesize(text, locale=locale)
        finally:
            self._speaking = False

    def interrupt(self) -> None:
        """Barge-in — stop current speech and mark the turn interrupted."""
        if self._speaking or True:
            self._interrupted = True
            self._speaking = False
            emit(self._bus, VoiceEvent.INTERRUPTED, {})

    def stop(self) -> None:
        self._speaking = False

    @property
    def interrupted(self) -> bool:
        return self._interrupted

    def diagnostics(self) -> dict:
        return {"stt": {"driver": self._stt.name, "available": self._stt.available()},
                "tts": {"driver": self._tts.name, "available": self._tts.available()},
                "vad": {"driver": self._vad.name, "available": self._vad.available()}}
