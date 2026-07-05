"""Background music selector — no API, just a folder of royalty-free tracks.

Drop your own royalty-free / CC0 tracks into assets/music/ named by mood
(calm.mp3, mystery.mp3, energetic.mp3, emotional.mp3). The selector maps the
Creative Director's mood to a file; if the folder is empty it returns None and
the renderer simply produces video without music. We never bundle or download
copyrighted audio.
"""
from __future__ import annotations

import os
from pathlib import Path

_MOOD_ALIASES = {
    "curious": "mystery", "mysterious": "mystery",
    "upbeat": "energetic", "energetic": "energetic",
    "calm": "calm", "gentle": "calm", "friendly": "calm",
    "emotional": "emotional", "warm": "emotional",
}


def music_dir() -> Path:
    env = os.getenv("SAATHI_MUSIC_DIR")
    return Path(env).expanduser() if env else Path(os.path.expanduser("~/SaathiAI/assets/music"))


def select(mood: str | None = None) -> str | None:
    d = music_dir()
    if not d.is_dir():
        return None
    tracks = sorted([p for p in d.iterdir() if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}])
    if not tracks:
        return None
    want = _MOOD_ALIASES.get((mood or "").lower(), (mood or "").lower())
    for p in tracks:
        if p.stem.lower() == want:
            return str(p)
    return str(tracks[0])  # deterministic fallback: first track
