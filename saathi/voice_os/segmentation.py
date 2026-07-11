"""M12 voice-friendly text rendering + response segmentation.

Segments assistant text into speakable chunks by sentence/clause boundary,
excluding code blocks, tables, and reducing markdown/citation noise so TTS
doesn't read raw formatting symbols aloud.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_URL = re.compile(r"https?://\S+")
_CITATION = re.compile(r"\[mem:[a-f0-9]+\]|\[chunk_ref:[^\]]+\]|\[\d+\]")
_MD_SYMBOLS = re.compile(r"[*_#>~]+")
_MULTI_WS = re.compile(r"\s+")

MAX_SEGMENT_CHARS = 220
MIN_SEGMENT_CHARS = 4


def voice_render(text: str) -> str:
    """Strip formatting noise the ear should never hear."""
    t = _CODE_BLOCK.sub(" (code omitted) ", text)
    t = _TABLE_ROW.sub(" ", t)
    t = _INLINE_CODE.sub(r"\1", t)
    t = _CITATION.sub("", t)
    t = _URL.sub("a link", t)
    t = _MD_SYMBOLS.sub("", t)
    t = _MULTI_WS.sub(" ", t).strip()
    return t


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def segment_for_speech(text: str, *, max_len: int = MAX_SEGMENT_CHARS,
                       min_len: int = MIN_SEGMENT_CHARS) -> list[str]:
    """Split cleaned text into TTS-ready segments at sentence boundaries,
    merging short trailing fragments and hard-wrapping overlong sentences."""
    cleaned = voice_render(text)
    if not cleaned:
        return []
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(cleaned) if s.strip()]
    if not sentences:
        sentences = [cleaned]

    segments: list[str] = []
    buf = ""
    for s in sentences:
        if len(s) > max_len:
            # hard-wrap overlong sentence at clause boundaries (commas)
            parts = s.split(", ")
            piece = ""
            for p in parts:
                if len(piece) + len(p) + 2 > max_len and piece:
                    segments.append(piece.strip())
                    piece = p
                else:
                    piece = f"{piece}, {p}" if piece else p
            if piece:
                s = piece
        if len(buf) + len(s) + 1 <= max_len:
            buf = f"{buf} {s}".strip()
        else:
            if buf:
                segments.append(buf)
            buf = s
    if buf:
        segments.append(buf)

    # merge segments shorter than min_len into the previous one
    merged: list[str] = []
    for seg in segments:
        if merged and len(seg) < min_len:
            merged[-1] = f"{merged[-1]} {seg}"
        else:
            merged.append(seg)
    return merged
