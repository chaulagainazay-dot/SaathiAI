#!/usr/bin/env python3
"""
Complete owner corpus recordings with energy validation.
Raw audio stays in ~/.saathi/stt-owner-corpus/ (not git).
Does NOT auto-fill subjective ratings.
"""
from __future__ import annotations

import array
import json
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path

OWNER = Path.home() / ".saathi/stt-owner-corpus"
WAV = OWNER / "wav"
MANIFEST = OWNER / "manifest.json"
COMPLETION = OWNER / "completion_report.json"

# Full intentional set (2B.3 + extras for 2B.4)
PROMPTS = [
    {"id": "own_en_001", "lang": "en", "category": "OWNER", "pace": "normal", "text": "Saathi, show my active missions."},
    {"id": "own_en_002", "lang": "en", "category": "OWNER", "pace": "fast", "text": "Stop. Cancel that response."},
    {"id": "own_en_003", "lang": "en", "category": "OWNER", "pace": "quiet", "text": "What is Trading Guardian status?"},
    {"id": "own_ne_001", "lang": "ne", "category": "OWNER", "pace": "slow", "text": "मेरो आजको portfolio risk देखाऊ।"},
    {"id": "own_ne_002", "lang": "ne", "category": "OWNER", "pace": "normal", "text": "आजको market exposure कति छ?"},
    {"id": "own_ne_003", "lang": "ne", "category": "OWNER", "pace": "fast", "text": "मेरो pending approvals के छन्?"},
    {"id": "own_mx_001", "lang": "mixed", "category": "OWNER", "pace": "normal", "text": "आजको portfolio risk explain गर"},
    {"id": "own_mx_002", "lang": "mixed", "category": "OWNER", "pace": "normal", "text": "Trading Guardian को status के छ?"},
    {"id": "own_mx_003", "lang": "mixed", "category": "OWNER", "pace": "normal", "text": "Saathi, current NAV कति छ?"},
    {"id": "own_mx_004", "lang": "mixed", "category": "OWNER", "pace": "fast", "text": "Stop, त्यो action cancel गर"},
    {"id": "own_nm_001", "lang": "en", "category": "OWNER_NUMERIC", "pace": "normal", "text": "Reduce position by five percent."},
    {"id": "own_nm_002", "lang": "mixed", "category": "OWNER_NUMERIC", "pace": "normal", "text": "आजको drawdown fifteen percent छ?"},
    {"id": "own_int_001", "lang": "en", "category": "OWNER_INTERRUPT", "pace": "fast", "text": "Wait. Stop talking."},
    # 2B.4 extras
    {"id": "own_mx_005", "lang": "mixed", "category": "OWNER", "pace": "normal", "text": "आजको NAV र drawdown compare गर"},
    {"id": "own_nm_003", "lang": "en", "category": "OWNER_NUMERIC", "pace": "normal", "text": "Buy five hundred shares."},
    {"id": "own_nm_004", "lang": "mixed", "category": "OWNER_NUMERIC", "pace": "normal", "text": "Position size five percent राख"},
    {"id": "own_nm_005", "lang": "en", "category": "OWNER_NUMERIC", "pace": "normal", "text": "Drawdown is one point five percent."},
]


def rms(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        frames = w.readframes(w.getnframes())
        n = w.getsampwidth()
    if n != 2:
        return 0.0
    samples = array.array("h")
    samples.frombytes(frames)
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5 / 32768.0


def record(path: Path, seconds: float) -> bool:
    cmd = [
        "ffmpeg", "-y", "-f", "avfoundation", "-i", ":0",
        "-t", str(seconds), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and path.exists() and path.stat().st_size > 1000


def main():
    OWNER.mkdir(parents=True, exist_ok=True)
    WAV.mkdir(parents=True, exist_ok=True)
    items = []
    speech_ok = 0
    ambient = 0
    failed = 0
    SPEECH_RMS = 0.01  # heuristic threshold for intentional speech

    for p in PROMPTS:
        out = WAV / f"{p['id']}.wav"
        print(f"\n=== {p['id']} ===\nSPEAK NOW ({p['seconds'] if 'seconds' in p else 5}s): {p['text']}")
        secs = 6.0 if p["lang"] != "en" else 5.0
        if p["id"] in ("own_en_002", "own_int_001"):
            secs = 4.0
        ok = record(out, secs)
        if not ok:
            print("RECORD_FAILED")
            failed += 1
            items.append({**p, "wav": str(out), "status": "FAILED", "rms": None})
            continue
        r = rms(out)
        status = "SPEECH_DETECTED" if r >= SPEECH_RMS else "AMBIENT_OR_SILENT"
        if status == "SPEECH_DETECTED":
            speech_ok += 1
        else:
            ambient += 1
        print(f"  rms={r:.4f} status={status}")
        items.append({
            **p,
            "wav": str(out),
            "source": "owner_mic",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "seconds": secs,
            "rms": r,
            "status": status,
        })

    manifest = {
        "version": "v-next-2b4-owner",
        "items": items,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Subjective ratings not auto-filled. Intentional speech requires human at mic.",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {
        "total": len(PROMPTS),
        "speech_detected": speech_ok,
        "ambient_or_silent": ambient,
        "failed": failed,
        "complete_for_tooling": failed == 0,
        "complete_for_intentional_owner_accent": speech_ok >= 13 and ambient == 0,
        "rms_threshold": SPEECH_RMS,
    }
    COMPLETION.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Aggregate-only copy for repo (no wav paths with user home if preferred - keep ids only)
    agg = {
        "total": report["total"],
        "speech_detected": speech_ok,
        "ambient_or_silent": ambient,
        "failed": failed,
        "complete_for_intentional_owner_accent": report["complete_for_intentional_owner_accent"],
        "prompt_ids": [p["id"] for p in PROMPTS],
        "per_item_status": [{"id": i["id"], "status": i["status"], "rms": i.get("rms")} for i in items],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
