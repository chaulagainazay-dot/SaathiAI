"""Render Director — decides HOW to render, never renders pixels itself.

Consumes the Scene Package; for each scene decides the image engine, voice
engine, motion, subtitle, music, transition — and emits a RENDER PACKAGE (a
manifest). A renderer ADAPTER then executes the manifest. Swapping FFmpeg →
Runway/Kling/Veo/Pika is an adapter change; the pipeline never changes. Exactly
the Model Router pattern, for rendering.
"""
from __future__ import annotations

import os
import shutil


# ── engine selection (availability-aware, like the Model Router) ──────────────
def _image_engine() -> str:
    if os.getenv("FLUX_API_URL"):
        return "flux"
    try:
        import importlib.util
        if importlib.util.find_spec("torch") and importlib.util.find_spec("diffusers"):
            return "sdxl"
    except Exception:
        pass
    return "pil-card"          # always available, offline


def _voice_engine() -> str:
    try:
        import importlib.util
        if importlib.util.find_spec("kokoro"):
            return "kokoro"
    except Exception:
        pass
    return "say" if shutil.which("say") else "silent"


# ── renderer adapters (mirror the speech adapters) ────────────────────────────
class _Adapter:
    name = "base"
    def available(self) -> bool: return False
    def execute(self, render_package: dict, assets_dir: str) -> dict: ...


class FFmpegAdapter(_Adapter):
    name = "ffmpeg"
    def available(self) -> bool:
        return bool(shutil.which("ffmpeg"))
    def execute(self, render_package: dict, assets_dir: str) -> dict:
        # Executes Mac-side once per-scene assets (images/voice) exist. Reuses the
        # proven FFmpeg pipeline; here it's the wiring point, not a generator.
        from saathi.tools.render import render_video
        import glob
        images = sorted(glob.glob(os.path.join(assets_dir, "scene-*.png")))
        voice = os.path.join(assets_dir, "narration.wav")
        out = os.path.join(assets_dir, "video.mp4")
        path = render_video(voice=voice if os.path.exists(voice) else None,
                            images=images or None, out=out)
        return {"ok": bool(path), "video": path or "", "adapter": self.name}


class StubAdapter(_Adapter):
    """Premium video engines — inert until configured (Runway/Kling/Veo/Pika)."""
    def __init__(self, name, env):
        self.name, self._env = name, env
    def available(self) -> bool:
        return bool(os.getenv(self._env))
    def execute(self, render_package: dict, assets_dir: str) -> dict:
        return {"ok": False, "adapter": self.name, "error": f"{self._env} not configured"}


ADAPTERS: dict[str, _Adapter] = {
    "ffmpeg": FFmpegAdapter(),
    "runway": StubAdapter("runway", "RUNWAY_API_KEY"),
    "kling": StubAdapter("kling", "KLING_API_KEY"),
    "veo": StubAdapter("veo", "VEO_API_KEY"),
    "pika": StubAdapter("pika", "PIKA_API_KEY"),
}


def available_adapters() -> list[str]:
    return [n for n, a in ADAPTERS.items() if a.available()]


def pick_adapter(prefer: str | None = None) -> str:
    if prefer and ADAPTERS.get(prefer) and ADAPTERS[prefer].available():
        return prefer
    for n in ("runway", "kling", "veo", "pika", "ffmpeg"):   # premium first, ffmpeg always
        if ADAPTERS[n].available():
            return n
    return "ffmpeg"


def plan(scene_package: dict, *, episode: str = "", prefer_adapter: str | None = None) -> dict:
    """Scene Package → Render Package (manifest). Decides engines per scene."""
    img, voice = _image_engine(), _voice_engine()
    scenes = []
    for s in scene_package.get("scenes", []) or []:
        avatar = s.get("purpose") in ("Hook", "CTA") or "Mr. Yeti" in (s.get("background", "") + s.get("image_prompt", ""))
        scenes.append({
            "scene": s.get("scene"), "duration": s.get("duration", 12),
            "kind": "character" if avatar else "supporting",
            "image_engine": img, "voice_engine": voice,
            "image_prompt": s.get("image_prompt", ""), "narration": s.get("narration", ""),
            "motion": s.get("motion", "ken burns"), "camera": s.get("camera", {}),
            "subtitle": True, "subtitle_style": s.get("subtitle_style", ""),
            "music": s.get("music", "curious underscore, low"),
            "transition": s.get("transition", "soft crossfade"),
        })
    adapter = pick_adapter(prefer_adapter)
    return {
        "episode": episode, "adapter": adapter, "scene_count": len(scenes),
        "est_seconds": sum(s["duration"] for s in scenes), "scenes": scenes,
        "music": "assets/music/curious.mp3", "logo": "assets/logo.png",
        "watermark": "pielts.web.app",
        "settings": {"fps": 25, "resolution": "1920x1080", "container": "mp4"},
        "engines": {"image": img, "voice": voice, "adapter": adapter},
    }


def render(render_package: dict, assets_dir: str, *, adapter: str | None = None) -> dict:
    """Execute a Render Package via the chosen adapter (Mac-side, needs assets)."""
    name = adapter or render_package.get("adapter") or pick_adapter()
    a = ADAPTERS.get(name)
    if not a or not a.available():
        return {"ok": False, "error": f"adapter {name!r} unavailable", "available": available_adapters()}
    return a.execute(render_package, assets_dir)
