"""M13 provider abstraction — image / video / TTS.

Real-local adapters (verified, no external service):
- PILImageProvider: genuinely renders a title-card/placeholder PNG via Pillow.
- FFmpegVideoProvider: genuinely renders a real video slate via the FFmpeg
  engine (which is itself gateway-routed).
- SayNarrationProvider: reuses M12's real macOS `say` TTS for narration.
Deterministic adapters (tests/CI). Cloud adapters (Flux/Veo/HeyGen/ComfyUI/
OpenAI/Gemini) are contract-ready extension points — NOT configured here, never
marked tested. A provider job is never "complete" until its output file exists
and is checksummed.
"""
from __future__ import annotations

import io
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from saathi.studio_os.storage import safe_path, checksum_file


def _silent_wav_bytes(*, duration_sec: float = 0.5, rate: int = 8000) -> bytes:
    """Minimal mono 16-bit PCM silence — ffmpeg-muxable without host TTS."""
    nframes = max(1, int(rate * duration_sec))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * nframes)
    return buf.getvalue()


@dataclass
class GenResult:
    ok: bool
    kind: str            # image|video|voice
    path: str = ""
    checksum: str = ""
    size_bytes: int = 0
    provider: str = ""
    cost_usd: float = 0.0
    duration_sec: float = 0.0
    detail: str = ""


class ImageProvider:
    name = "base"

    def available(self) -> bool:
        return False

    def generate(self, project_id: str, *, prompt: str, out_rel: str,
                 width: int = 1280, height: int = 720, seed: int = 0) -> GenResult:
        raise NotImplementedError


class DeterministicImageProvider(ImageProvider):
    name = "deterministic"

    def available(self) -> bool:
        return True

    def generate(self, project_id, *, prompt, out_rel, width=1280, height=720, seed=0):
        out = safe_path(project_id, out_rel)
        out.parent.mkdir(parents=True, exist_ok=True)
        # deterministic bytes derived from prompt+seed — no real pixels
        payload = f"IMG:{width}x{height}:{seed}:{prompt}".encode()
        out.write_bytes(payload)
        return GenResult(ok=True, kind="image", path=str(out),
                        checksum=checksum_file(out), size_bytes=out.stat().st_size,
                        provider=self.name)


class PILImageProvider(ImageProvider):
    """Real local image generation via Pillow — genuine PNG pixels."""
    name = "pillow"

    def available(self) -> bool:
        try:
            import PIL  # noqa: F401
            return True
        except Exception:
            return False

    def generate(self, project_id, *, prompt, out_rel, width=1280, height=720, seed=0):
        from PIL import Image, ImageDraw
        import hashlib
        out = safe_path(project_id, out_rel)
        out.parent.mkdir(parents=True, exist_ok=True)
        # deterministic-but-real: background color seeded from prompt, title text
        h = int(hashlib.md5(f"{prompt}{seed}".encode()).hexdigest(), 16)
        bg = ((h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF)
        img = Image.new("RGB", (width, height), bg)
        draw = ImageDraw.Draw(img)
        title = (prompt or "SaathiOS")[:60]
        draw.rectangle([40, height // 2 - 60, width - 40, height // 2 + 60],
                       fill=(0, 0, 0))
        draw.text((60, height // 2 - 20), title, fill=(255, 255, 255))
        img.save(out, "PNG")
        return GenResult(ok=True, kind="image", path=str(out),
                        checksum=checksum_file(out), size_bytes=out.stat().st_size,
                        provider=self.name)


class VideoProvider:
    name = "base"

    def available(self) -> bool:
        return False

    def generate(self, project_id, *, prompt, out_rel, duration_sec=2.0,
                 image_path=None) -> GenResult:
        raise NotImplementedError


class DeterministicVideoProvider(VideoProvider):
    name = "deterministic"

    def available(self) -> bool:
        return True

    def generate(self, project_id, *, prompt, out_rel, duration_sec=2.0, image_path=None):
        out = safe_path(project_id, out_rel)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(f"VIDEO:{duration_sec}:{prompt}".encode())
        return GenResult(ok=True, kind="video", path=str(out),
                        checksum=checksum_file(out), size_bytes=out.stat().st_size,
                        provider=self.name, duration_sec=duration_sec)


class FFmpegVideoProvider(VideoProvider):
    """Real local video via the gateway-routed FFmpeg engine."""
    name = "ffmpeg-local"

    def available(self) -> bool:
        from saathi.studio_os.ffmpeg_engine import ffmpeg_available
        return ffmpeg_available()

    def generate(self, project_id, *, prompt, out_rel, duration_sec=2.0, image_path=None):
        from saathi.studio_os.ffmpeg_engine import render_slate
        r = render_slate(project_id, text=prompt, image_path=image_path,
                         duration_sec=duration_sec, out_rel=out_rel)
        return GenResult(ok=r.ok, kind="video", path=r.path, checksum=r.checksum,
                        size_bytes=r.size_bytes, provider=self.name,
                        duration_sec=r.duration_sec, detail=r.detail)


class NarrationProvider:
    name = "base"

    def available(self) -> bool:
        return False

    def generate(self, project_id, *, text, out_rel, voice="default") -> GenResult:
        raise NotImplementedError


class DeterministicNarrationProvider(NarrationProvider):
    """Credential-free offline narration: minimal valid silent WAV so assemble
    mux works on Linux CI (no macOS `say`) without claiming real TTS quality."""
    name = "deterministic"

    def available(self) -> bool:
        return True

    def generate(self, project_id, *, text, out_rel, voice="default"):
        out = safe_path(project_id, out_rel)
        # Always emit .wav — writing text to .aiff broke ffmpeg mux on Linux CI.
        if out.suffix.lower() not in (".wav", ".wave"):
            out = out.with_suffix(".wav")
        out.parent.mkdir(parents=True, exist_ok=True)
        # ≥2s so mux -shortest keeps a usable video length for thumbnail seeks
        out.write_bytes(_silent_wav_bytes(duration_sec=2.0))
        return GenResult(ok=True, kind="voice", path=str(out),
                        checksum=checksum_file(out), size_bytes=out.stat().st_size,
                        provider=self.name,
                        detail=f"silent_wav voice={voice} text_len={len(text or '')}")


class SayNarrationProvider(NarrationProvider):
    """Real narration via M12's macOS `say` TTS (shared provider contract)."""
    name = "say"

    def available(self) -> bool:
        from saathi.voice_os.tts import SayTTS
        return SayTTS().available()

    def generate(self, project_id, *, text, out_rel, voice="default"):
        from saathi.voice_os.tts import SayTTS
        res = SayTTS().synthesize(text, voice=voice)
        out = safe_path(project_id, out_rel)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(res.audio)
        return GenResult(ok=len(res.audio) > 0, kind="voice", path=str(out),
                        checksum=checksum_file(out), size_bytes=out.stat().st_size,
                        provider=self.name)


# ── registries + capability matrix ─────────────────────────────────────────
_IMAGE = {"deterministic": DeterministicImageProvider(), "pillow": PILImageProvider()}
_VIDEO = {"deterministic": DeterministicVideoProvider(), "ffmpeg-local": FFmpegVideoProvider()}
_VOICE = {"deterministic": DeterministicNarrationProvider(), "say": SayNarrationProvider()}


def image_provider(prefer: str = "auto") -> ImageProvider:
    if prefer in _IMAGE and _IMAGE[prefer].available():
        return _IMAGE[prefer]
    return _IMAGE["pillow"] if _IMAGE["pillow"].available() else _IMAGE["deterministic"]


def video_provider(prefer: str = "auto") -> VideoProvider:
    if prefer in _VIDEO and _VIDEO[prefer].available():
        return _VIDEO[prefer]
    return _VIDEO["ffmpeg-local"] if _VIDEO["ffmpeg-local"].available() else _VIDEO["deterministic"]


def narration_provider(prefer: str = "auto") -> NarrationProvider:
    if prefer in _VOICE and _VOICE[prefer].available():
        return _VOICE[prefer]
    return _VOICE["say"] if _VOICE["say"].available() else _VOICE["deterministic"]


def capability_matrix() -> dict:
    """Every provider's status — configured is NEVER conflated with tested."""
    def rows(reg, kind):
        out = []
        for name, p in reg.items():
            out.append({"name": name, "kind": kind, "configured": True,
                       "available": p.available(),
                       "local": name in ("pillow", "ffmpeg-local", "say", "deterministic")})
        # honest markers for the cloud providers we did NOT wire
        for cloud in {"image": ["flux", "openai-image", "gemini-image", "comfyui"],
                      "video": ["veo/flow", "heygen", "comfyui-video"],
                      "voice": ["openai-tts", "elevenlabs"]}.get(kind, []):
            out.append({"name": cloud, "kind": kind, "configured": False,
                       "available": False, "local": False,
                       "note": "contract-ready extension point; not configured/tested"})
        return out
    return {"image": rows(_IMAGE, "image"), "video": rows(_VIDEO, "video"),
            "voice": rows(_VOICE, "voice")}
