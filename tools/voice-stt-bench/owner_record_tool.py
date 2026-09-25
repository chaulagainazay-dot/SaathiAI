#!/usr/bin/env python3
"""
Owner real-speech recording tool for V-NEXT-2B.3.

- Records locally to ~/.saathi/stt-owner-corpus/ (git-excluded by default)
- Does NOT auto-fill subjective ratings
- Writes manifest + empty rating template for owner

Usage:
  python owner_record_tool.py --list
  python owner_record_tool.py --record cs_owner_001 --seconds 5
  python owner_record_tool.py --check
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OWNER_ROOT = Path.home() / ".saathi" / "stt-owner-corpus"
WAV = OWNER_ROOT / "wav"
MANIFEST = OWNER_ROOT / "manifest.json"
RATINGS = OWNER_ROOT / "owner_ratings.json"

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
]


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"version": "v-next-2b3-owner", "items": [], "created_at": datetime.now(timezone.utc).isoformat()}


def save_manifest(m: dict) -> None:
    OWNER_ROOT.mkdir(parents=True, exist_ok=True)
    WAV.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def record_ffmpeg(out: Path, seconds: float) -> bool:
    """macOS avfoundation default mic → 16k mono wav."""
    # device ":0" is often default mic on macOS with avfoundation
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "avfoundation",
        "-i",
        ":0",
        "-t",
        str(seconds),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-800:], file=sys.stderr)
        return False
    return out.exists() and out.stat().st_size > 1000


def cmd_list() -> int:
    print("Owner prompts (speak naturally; do not auto-rate):\n")
    for p in PROMPTS:
        print(f"  {p['id']:16} [{p['lang']:5}/{p['pace']:6}] {p['text']}")
    print(f"\nStorage: {OWNER_ROOT} (local only)")
    return 0


def cmd_record(prompt_id: str, seconds: float) -> int:
    prompt = next((p for p in PROMPTS if p["id"] == prompt_id), None)
    if not prompt:
        print("Unknown id", prompt_id, file=sys.stderr)
        return 2
    OWNER_ROOT.mkdir(parents=True, exist_ok=True)
    WAV.mkdir(parents=True, exist_ok=True)
    out = WAV / f"{prompt_id}.wav"
    print(f"\n=== RECORD {prompt_id} ({seconds}s) ===")
    print(f"Speak: {prompt['text']}")
    print("Recording from default mic via ffmpeg avfoundation...")
    if not record_ffmpeg(out, seconds):
        print("RECORD_FAILED — check mic permission / ffmpeg avfoundation", file=sys.stderr)
        return 1
    m = load_manifest()
    items = [i for i in m["items"] if i["id"] != prompt_id]
    items.append(
        {
            **prompt,
            "wav": str(out),
            "source": "owner_mic",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "seconds": seconds,
        }
    )
    m["items"] = items
    m["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_manifest(m)
    # rating template — owner fills manually
    ratings = {}
    if RATINGS.exists():
        ratings = json.loads(RATINGS.read_text(encoding="utf-8"))
    ratings.setdefault(
        prompt_id,
        {
            "intent_ok": None,
            "numeric_ok": None,
            "usable_as_primary": None,
            "notes": "",
            "auto_filled": False,
        },
    )
    RATINGS.write_text(json.dumps(ratings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {out}")
    print("Owner ratings template updated — do NOT auto-fill subjective fields.")
    return 0


def cmd_check() -> int:
    m = load_manifest()
    print(f"manifest items: {len(m.get('items', []))}")
    for it in m.get("items", []):
        p = Path(it["wav"])
        print(f"  {it['id']}: exists={p.exists()} size={p.stat().st_size if p.exists() else 0}")
    if RATINGS.exists():
        r = json.loads(RATINGS.read_text(encoding="utf-8"))
        filled = sum(1 for v in r.values() if v.get("intent_ok") is not None)
        print(f"ratings entries: {len(r)} owner-filled intent: {filled}")
    else:
        print("no ratings file yet")
    missing = [p["id"] for p in PROMPTS if not (WAV / f"{p['id']}.wav").exists()]
    print(f"missing recordings: {len(missing)}")
    if missing:
        print("  ", ", ".join(missing[:8]), ("..." if len(missing) > 8 else ""))
    return 0


def cmd_record_all(seconds: float) -> int:
    """Attempt full set — requires owner present at mic."""
    fails = 0
    for p in PROMPTS:
        print("\n" + "=" * 60)
        print(f"NEXT: {p['id']} — {p['text']}")
        print("Press Enter when ready to record, or Ctrl+C to abort...")
        try:
            input()
        except KeyboardInterrupt:
            print("aborted")
            break
        if cmd_record(p["id"], seconds) != 0:
            fails += 1
    return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--record", metavar="ID")
    ap.add_argument("--record-all", action="store_true")
    ap.add_argument("--seconds", type=float, default=5.0)
    args = ap.parse_args()
    if args.list:
        return cmd_list()
    if args.check:
        return cmd_check()
    if args.record:
        return cmd_record(args.record, args.seconds)
    if args.record_all:
        return cmd_record_all(args.seconds)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
