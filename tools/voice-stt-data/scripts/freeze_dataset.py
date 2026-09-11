#!/usr/bin/env python3
"""Freeze SAATHI_STT_PRODUCT_CORPUS_V1 metadata when authorization gate passes.

Never freezes raw audio into Git — only manifests, hashes, and summary stats.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
MANIFESTS = CORPUS / "manifests"
REPO = Path(__file__).resolve().parents[3]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--auth-report",
        type=Path,
        default=MANIFESTS / "training_authorization_report.json",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO / "docs" / "voice-next-2b6" / "DATASET_FREEZE.json",
    )
    ap.add_argument("--force", action="store_true", help="Write freeze even if gate failed (mark NOT_FROZEN)")
    args = ap.parse_args()

    if not args.auth_report.exists():
        print("Run training_authorization_gate.py first")
        return 2
    auth = json.loads(args.auth_report.read_text(encoding="utf-8"))
    authorized = auth.get("training_authorized") is True and auth.get("verdict") == "WHISPER_CS_LORA_TRAINING_AUTHORIZED"

    man_path = MANIFESTS / "dataset_manifest.jsonl"
    man_sha = None
    clip_count = 0
    speakers: set[str] = set()
    hours = 0.0
    if man_path.exists():
        raw = man_path.read_bytes()
        man_sha = sha256_bytes(raw)
        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            o = json.loads(line)
            clip_count += 1
            speakers.add(o.get("speaker_id") or "")
            hours += float(o.get("duration") or 0) / 3600.0

    freeze = {
        "dataset_version": "SAATHI_STT_PRODUCT_CORPUS_V1" if authorized else None,
        "frozen": bool(authorized),
        "frozen_at": datetime.now(timezone.utc).isoformat() if authorized else None,
        "status": "FROZEN" if authorized else "NOT_FROZEN",
        "reason": None if authorized else auth.get("verdict"),
        "manifest_sha256": man_sha,
        "speaker_count": len({s for s in speakers if s}),
        "clip_count": clip_count,
        "hours": round(hours, 4),
        "license_summary": {
            "product_training": "speaker commercial consent required",
            "redistribution_default": False,
            "common_voice_ne": "CC0 support role only (not mirrored in repo)",
        },
        "consent_summary": auth.get("observed", {}),
        "split_summary": {},
        "gate_verdict": auth.get("verdict"),
        "raw_audio_in_git": False,
        "raw_audio_root": str(CORPUS),
    }
    if (MANIFESTS / "split_report.json").exists():
        freeze["split_summary"] = json.loads((MANIFESTS / "split_report.json").read_text(encoding="utf-8"))

    if not authorized and not args.force:
        print("Gate not authorized — writing NOT_FROZEN record")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    # also local
    local = MANIFESTS / "dataset_freeze.json"
    local.write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(freeze, indent=2))
    return 0 if authorized or args.force else 2


if __name__ == "__main__":
    raise SystemExit(main())
