"""Conversation diagnostics — the dashboard's Conversation section.

    Conversation
    ─────────────
    Voice 🟢  Whisper 🟢  TTS 🟢  Wake Word 🟡
    Latency 620 ms   Sessions 4   Interruptions 2
"""
from __future__ import annotations


def _light(ok: bool) -> str:
    return "🟢" if ok else "🔴"


def snapshot(engine=None, voice=None) -> dict:
    """Conversation-layer health. Pass the live engine/voice, or defaults are probed."""
    if voice is None:
        try:
            from .adapters.voice import VoiceAdapter
            voice = VoiceAdapter()
        except Exception:
            voice = None

    vd = voice.diagnostics() if voice is not None else {}
    stt = vd.get("stt", {})
    tts = vd.get("tts", {})
    sessions = engine.sessions.count() if engine is not None else 0
    return {
        "voice": {"available": bool(vd), "light": _light(bool(vd))},
        "stt": {"driver": stt.get("driver"), "available": stt.get("available", False),
                "light": _light(stt.get("available", False))},
        "tts": {"driver": tts.get("driver"), "available": tts.get("available", False),
                "light": _light(tts.get("available", False))},
        "wakeword": {"available": False, "light": "🟡"},   # OpenWakeWord/Porcupine — Phase later
        "sessions": sessions,
    }
