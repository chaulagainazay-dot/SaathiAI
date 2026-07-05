"""Render — images + narration (+ optional music) → MP4 via FFmpeg.

Offline, deterministic, reproducible, zero cost. Ken Burns (slow zoom) per scene,
timed to the narration length, optional ducked background music, optional logo
overlay. No Runway/Kling/HeyGen — those are v0.5 provider swaps behind this same
interface. Returns the output path, or None if FFmpeg is unavailable / no inputs.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

FPS = 25


def render_video(*, voice: str | None, images: list[str] | None, out: str,
                 music: str | None = None, logo: str | None = None) -> str | None:
    if not shutil.which("ffmpeg") or not images:
        return None
    images = [i for i in images if Path(i).exists()]
    if not images:
        return None
    dur = _audio_seconds(voice) if voice else 0.0
    if dur <= 0:
        dur = max(3.0, len(images) * 4.0)          # no audio → 4s/scene default
    per = max(2.0, dur / len(images))
    out_p = Path(out); out_p.parent.mkdir(parents=True, exist_ok=True)

    # 1) build one Ken-Burns clip per image
    tmp = out_p.parent / "_clips"; tmp.mkdir(exist_ok=True)
    clips = []
    for i, img in enumerate(images):
        clip = tmp / f"c{i:02d}.mp4"
        if _ken_burns(img, clip, per):
            clips.append(clip)
    if not clips:
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    # 2) concat clips
    silent = tmp / "silent.mp4"
    listf = tmp / "list.txt"
    listf.write_text("".join(f"file '{c.name}'\n" for c in clips))
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
          "-c", "copy", str(silent)], cwd=tmp)
    if not silent.exists():
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    # 3) mux audio (narration + optional ducked music) + optional logo
    ok = _finalize(silent, out_p, voice=voice, music=music, logo=logo)
    shutil.rmtree(tmp, ignore_errors=True)
    return str(out_p) if (ok and out_p.exists() and out_p.stat().st_size > 0) else None


def _ken_burns(img: str, out: Path, seconds: float) -> bool:
    frames = int(seconds * FPS)
    vf = (f"scale=2400:1350,zoompan=z='min(zoom+0.0007,1.15)':d={frames}"
          f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps={FPS},"
          f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(0.1, seconds-0.4):.2f}:d=0.4")
    return _run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", f"{seconds:.2f}",
                 "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])


def _finalize(silent: Path, out: Path, *, voice, music, logo) -> bool:
    inputs = ["-i", str(silent)]
    audio_idx = []
    if voice and Path(voice).exists():
        inputs += ["-i", voice]; audio_idx.append(("voice", len(audio_idx) + 1))
    if music and Path(music).exists():
        inputs += ["-i", music]; audio_idx.append(("music", len(audio_idx) + 1))

    fc, vlabel = [], "0:v"
    if logo and Path(logo).exists():
        inputs += ["-i", logo]
        li = 1 + len(audio_idx)
        fc.append(f"[{li}:v]scale=220:-1[lg];[0:v][lg]overlay=W-w-40:40[v]")
        vlabel = "[v]"

    cmd = ["ffmpeg", "-y", *inputs]
    if not audio_idx:                       # no audio at all
        if fc:
            cmd += ["-filter_complex", ";".join(fc), "-map", vlabel]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(out)]
        return _run(cmd)

    names = [n for n, _ in audio_idx]
    if "voice" in names and "music" in names:
        vi = dict(audio_idx)["voice"]; mi = dict(audio_idx)["music"]
        fc.append(f"[{mi}:a]volume=0.18[bg];[{vi}:a][bg]amix=inputs=2:duration=first:dropout_transition=2[a]")
        amap = "[a]"
    else:
        only = audio_idx[0][1]
        fc.append(f"[{only}:a]volume=1.0[a]"); amap = "[a]"

    cmd += ["-filter_complex", ";".join(fc), "-map", vlabel, "-map", amap,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)]
    return _run(cmd)


def _audio_seconds(path: str) -> float:
    if not (path and Path(path).exists()):
        return 0.0
    try:
        import soundfile as sf
        info = sf.info(path)
        return info.frames / info.samplerate
    except Exception:
        pass
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", path], capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


def _run(cmd, cwd=None) -> bool:
    try:
        subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True,
                       capture_output=True, timeout=600)
        return True
    except Exception:
        return False
