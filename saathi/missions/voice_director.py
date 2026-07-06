"""Voice Director — turns a Mission's active voice into a Voice Package.

Like the Render Director emits a Render Package and never renders pixels, the Voice
Director reads the Mission → Brand → active Voice, layers the scene emotion and
episode objective on top, and emits a provider-agnostic Voice Package. TTS adapters
(Kokoro/say/XTTS/ElevenLabs/OpenAI/HeyGen) consume the package; the Director never
calls a specific engine. Swap providers = swap an adapter, pipeline unchanged.

    Mission → Brand → Voice Studio → Active Voice → Scene Emotion → Objective
            → Voice Package → TTS
"""
from __future__ import annotations

import shutil

# provider adapters: available() gates on real capability, keyed stubs stay inert
_PROVIDERS = {
    "kokoro": lambda: _has_module("kokoro") or _has_module("kokoro_onnx"),
    "say": lambda: bool(shutil.which("say")),          # macOS built-in
    "xtts": lambda: _has_module("TTS"),
    "elevenlabs": lambda: bool(_env("ELEVENLABS_API_KEY")),
    "openai": lambda: bool(_env("OPENAI_API_KEY")),
    "heygen": lambda: bool(_env("HEYGEN_API_KEY")),
    "silent": lambda: True,                             # last-resort fallback
}
# preference order when the profile's provider isn't available
_PREFERENCE = ["kokoro", "xtts", "elevenlabs", "openai", "say", "silent"]


def _has_module(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


def _env(key: str) -> str:
    import os
    return os.getenv(key, "")


def available_providers() -> list[str]:
    return [p for p, ok in _PROVIDERS.items() if _safe(ok)]


def _safe(fn) -> bool:
    try:
        return bool(fn())
    except Exception:
        return False


def pick_provider(prefer: str = "") -> str:
    avail = available_providers()
    if prefer and prefer in avail:
        return prefer
    for p in _PREFERENCE:
        if p in avail:
            return p
    return "silent"


# map a scene emotion onto light SSML-style delivery hints (provider-neutral)
_EMOTION_HINTS = {
    "excited": {"rate": 1.1, "pitch": "+2", "emphasis": "strong"},
    "calm": {"rate": 0.95, "pitch": "-1", "emphasis": "reduced"},
    "encouraging": {"rate": 1.0, "pitch": "+1", "emphasis": "moderate"},
    "serious": {"rate": 0.97, "pitch": "0", "emphasis": "moderate"},
    "warm": {"rate": 1.0, "pitch": "+1", "emphasis": "moderate"},
}


def package(mission_id: str, *, scene_emotion: str = "", objective: str = "",
            prefer_provider: str = "", store=None) -> dict:
    """Active voice + scene emotion + objective → provider-agnostic Voice Package."""
    from saathi.missions.brand import default_store as b_store
    bs = store or b_store()
    voice = bs.active_voice(mission_id)

    if not voice:
        base = {"name": "", "provider": "", "language": "English", "accent": "",
                "style": "narrator", "emotion": "neutral", "speed": 1.0, "pitch": "medium"}
        voice_id, version = "", 0
    else:
        base = voice
        voice_id, version = voice.get("id", ""), voice.get("version", 0)

    emotion = scene_emotion or base.get("emotion", "neutral")
    hints = _EMOTION_HINTS.get(emotion.split(",")[0].strip().lower(), _EMOTION_HINTS["warm"])
    provider = pick_provider(prefer_provider or base.get("provider", ""))

    return {
        "mission_id": mission_id,
        "voice_id": voice_id,
        "voice_name": base.get("name", ""),
        "version": version,
        "provider": provider,
        "requested_provider": base.get("provider", ""),
        "language": base.get("language", "English"),
        "accent": base.get("accent", ""),
        "style": base.get("style", "narrator"),
        "base_emotion": base.get("emotion", "neutral"),
        "scene_emotion": emotion,
        "objective": objective,
        "speed": base.get("speed", 1.0),
        "pitch": base.get("pitch", "medium"),
        "delivery": hints,
        "providers_available": available_providers(),
        "has_active_voice": bool(voice),
        "note": "" if voice else "No active voice for this Mission — register one in Voice Studio.",
    }
