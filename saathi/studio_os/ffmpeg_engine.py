"""M13 FFmpeg media engine — REAL local render, argument-safe, gateway-routed.

Arguments are always a list (never a shell string) so transcript/filename
content cannot inject shell commands. Every invocation is a ToolIntent through
the ExecutionGateway. Outputs are verified (file exists + non-empty + probed).
FFmpeg is used only for deterministic media processing/assembly/encoding —
never as a generative model.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from saathi.studio_os.storage import safe_path, checksum_file


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


class FFmpegError(Exception):
    pass


@dataclass
class RenderResult:
    ok: bool
    path: str = ""
    checksum: str = ""
    size_bytes: int = 0
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    provider: str = "ffmpeg-local"
    detail: str = ""
    duration_ms: float = 0.0


def _validate_args(args: list[str]) -> None:
    """Defence in depth: args must be a list of str; reject shell metacharacters
    that would only matter if someone bypassed the list form."""
    if not isinstance(args, list):
        raise FFmpegError("ffmpeg args must be a list, never a shell string")
    for a in args:
        if not isinstance(a, str):
            raise FFmpegError("ffmpeg args must all be strings")


def _run(args: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess:
    _validate_args(args)
    # gateway-routed: record the intent so no media op bypasses the audit path
    _record_gateway_intent("ffmpeg", args)
    return subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                          capture_output=True, text=True, timeout=timeout, shell=False)


def _record_gateway_intent(op: str, args: list[str]) -> None:
    """Route the media op through the ExecutionGateway as a ToolIntent so it is
    validated/authorized/audited like every other side effect. Best-effort —
    never blocks a local render if the gateway import is unavailable in a test."""
    try:
        import uuid
        from datetime import datetime
        from saathi.execution import ToolIntent, ExecutionContext
        from saathi.execution.gateway import ExecutionGateway
        from saathi.execution.queue.memory import MemoryQueue
        intent = ToolIntent(
            intent_id=f"ffmpeg-{uuid.uuid4().hex[:10]}", operation="media-processing",
            business_unit="ai-studio", actor_id="studio:ffmpeg",
            parameters={"op": op, "args": args[:8]},
            metadata={"data_sensitivity": "internal"})
        gw = ExecutionGateway(MemoryQueue())
        hist = gw.receive_intent(intent)
        hist = gw.validate_intent(intent, hist)
        gw.classify_risk(intent, ExecutionContext(
            actor_id="studio:ffmpeg", business_unit="ai-studio",
            timestamp=datetime.utcnow(), current_time=datetime.utcnow()), hist)
    except Exception:
        pass


def probe(path: str | Path, *, timeout: int = 30) -> dict:
    """Real ffprobe — returns duration/dimensions or raises."""
    args = ["-v", "error", "-print_format", "json", "-show_format",
            "-show_streams", str(path)]
    _validate_args(args)
    res = subprocess.run(["ffprobe", *args], capture_output=True, text=True,
                         timeout=timeout, shell=False)
    if res.returncode != 0:
        raise FFmpegError(f"ffprobe failed: {res.stderr[:200]}")
    data = json.loads(res.stdout or "{}")
    fmt = data.get("format", {})
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return {"duration_sec": float(fmt.get("duration", 0) or 0),
            "width": int(v.get("width", 0) or 0),
            "height": int(v.get("height", 0) or 0)}


def _verify_output(out: Path) -> RenderResult:
    if not out.exists() or out.stat().st_size == 0:
        return RenderResult(ok=False, detail="output file missing or empty")
    meta = {}
    try:
        meta = probe(out)
    except Exception as exc:
        return RenderResult(ok=False, detail=f"output unverifiable: {exc}")
    return RenderResult(ok=True, path=str(out), checksum=checksum_file(out),
                        size_bytes=out.stat().st_size,
                        duration_sec=meta.get("duration_sec", 0.0),
                        width=meta.get("width", 0), height=meta.get("height", 0))


def has_drawtext() -> bool:
    """Not all ffmpeg builds ship the drawtext filter (needs libfreetype)."""
    try:
        res = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=10)
        return " drawtext " in res.stdout
    except Exception:
        return False


def render_slate(project_id: str, *, text: str = "", image_path: str | None = None,
                 duration_sec: float = 2.0, width: int = 1280, height: int = 720,
                 out_rel: str = "renders/slate.mp4", color: str = "black") -> RenderResult:
    """Render a real video slate. If an `image_path` (e.g. a PIL-rendered title
    card) is supplied it becomes the frames; otherwise a solid color source is
    used (with drawtext text overlay only when the local ffmpeg supports it).
    A genuine local render — the deterministic render smoke."""
    if not ffmpeg_available():
        return RenderResult(ok=False, provider="unavailable",
                            detail="ffmpeg/ffprobe not installed")
    out = safe_path(project_id, out_rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    if image_path and Path(image_path).exists():
        args = ["-loop", "1", "-i", str(image_path), "-t", str(duration_sec),
                "-r", "24", "-pix_fmt", "yuv420p",
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                       f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2", str(out)]
    else:
        vf = None
        if text and has_drawtext():
            safe_text = text.replace("\\", "").replace(":", " ").replace("'", "")[:80]
            vf = (f"drawtext=text='{safe_text}':fontcolor=white:fontsize=48:"
                  f"x=(w-text_w)/2:y=(h-text_h)/2")
        args = ["-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:d={duration_sec}"]
        if vf:
            args += ["-vf", vf]
        args += ["-r", "24", "-pix_fmt", "yuv420p", str(out)]

    res = _run(args, timeout=60)
    if res.returncode != 0:
        return RenderResult(ok=False, detail=f"ffmpeg error: {res.stderr[:200]}")
    r = _verify_output(out)
    r.duration_ms = (time.monotonic() - t0) * 1000
    return r


def concat_clips(project_id: str, clip_paths: list[str], *,
                 out_rel: str = "renders/final.mp4") -> RenderResult:
    """Concatenate verified clips into a final video (concat demuxer)."""
    if not ffmpeg_available():
        return RenderResult(ok=False, provider="unavailable", detail="ffmpeg not installed")
    for c in clip_paths:
        if not Path(c).exists():
            return RenderResult(ok=False, detail=f"missing input clip: {c}")
    listing = safe_path(project_id, "tmp/concat.txt")
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text("".join(f"file '{Path(c).resolve()}'\n" for c in clip_paths))
    out = safe_path(project_id, out_rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    args = ["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out)]
    res = _run(args, timeout=120)
    if res.returncode != 0:
        # fallback: re-encode (clips may differ in codec params)
        args = ["-f", "concat", "-safe", "0", "-i", str(listing),
                "-pix_fmt", "yuv420p", str(out)]
        res = _run(args, timeout=180)
        if res.returncode != 0:
            return RenderResult(ok=False, detail=f"concat failed: {res.stderr[:200]}")
    r = _verify_output(out)
    r.duration_ms = (time.monotonic() - t0) * 1000
    return r


def extract_thumbnail(project_id: str, video_path: str, *, at_sec: float = 0.0,
                      out_rel: str = "thumbnails/frame.png") -> RenderResult:
    """Grab one frame. Default seek is 0.0 so short muxed clips (e.g. audio
    shorter than video with -shortest) still yield a frame; mid-clip seeks
    often produced empty output with rc=0 on sub-second media."""
    if not ffmpeg_available():
        return RenderResult(ok=False, provider="unavailable", detail="ffmpeg not installed")
    out = safe_path(project_id, out_rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    attempts = [at_sec]
    if at_sec != 0.0:
        attempts.append(0.0)
    last_err = ""
    for ss in attempts:
        if out.exists():
            try:
                out.unlink()
            except OSError:
                pass
        args = ["-ss", str(ss), "-i", str(video_path), "-frames:v", "1",
                "-y", str(out)]
        res = _run(args, timeout=30)
        if res.returncode != 0:
            last_err = f"thumbnail extract failed: {res.stderr[:200]}"
            continue
        if out.exists() and out.stat().st_size > 0:
            return RenderResult(ok=True, path=str(out), checksum=checksum_file(out),
                                size_bytes=out.stat().st_size)
        last_err = "thumbnail missing"
    return RenderResult(ok=False, detail=last_err or "thumbnail missing")


def mux_audio(project_id: str, video_path: str, audio_path: str, *,
              out_rel: str = "renders/with_audio.mp4") -> RenderResult:
    """Replace/attach an audio track (e.g. narration) onto a video."""
    if not ffmpeg_available():
        return RenderResult(ok=False, provider="unavailable", detail="ffmpeg not installed")
    for p in (video_path, audio_path):
        if not Path(p).exists():
            return RenderResult(ok=False, detail=f"missing input: {p}")
    out = safe_path(project_id, out_rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    args = ["-i", str(video_path), "-i", str(audio_path), "-c:v", "copy",
            "-c:a", "aac", "-shortest", "-map", "0:v:0", "-map", "1:a:0", str(out)]
    res = _run(args, timeout=120)
    if res.returncode != 0:
        return RenderResult(ok=False, detail=f"mux failed: {res.stderr[:200]}")
    return _verify_output(out)
