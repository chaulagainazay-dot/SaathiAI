#!/usr/bin/env python3
"""Dataset statistics for product-clean speech corpus (local audio root)."""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
MANIFESTS = CORPUS / "manifests"
CONSENTS = CORPUS / "consents"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=MANIFESTS / "dataset_manifest.jsonl")
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args()

    rows: list[dict] = []
    if args.manifest.exists():
        rows = [json.loads(l) for l in args.manifest.read_text(encoding="utf-8").splitlines() if l.strip()]

    consents = []
    if CONSENTS.exists():
        for p in CONSENTS.glob("spk_*.json"):
            consents.append(json.loads(p.read_text(encoding="utf-8")))

    durations = [float(r.get("duration") or 0) for r in rows if r.get("duration")]
    speakers = sorted({r.get("speaker_id") for r in rows if r.get("speaker_id")})
    by_lang = Counter(r.get("language_class") for r in rows)
    by_bucket = Counter(r.get("bucket") for r in rows)
    by_split = Counter(r.get("split") for r in rows)
    by_qa = Counter(r.get("qa_status") for r in rows)
    numeric = sum(1 for r in rows if r.get("contains_numbers"))
    financial = sum(1 for r in rows if r.get("contains_financial_terms"))
    mix = by_lang.get("MIX", 0)
    commercial_speakers = sum(1 for c in consents if c.get("commercial_model_training_allowed"))

    per_speaker_clips: dict[str, int] = Counter(r.get("speaker_id") for r in rows)
    per_speaker_hours: dict[str, float] = defaultdict(float)
    for r in rows:
        per_speaker_hours[r.get("speaker_id") or "?"] += float(r.get("duration") or 0) / 3600.0

    devices = Counter(r.get("device_label") or "unknown" for r in rows)
    noise = Counter(r.get("noise_class") or "unknown" for r in rows)

    total_hours = sum(durations) / 3600.0 if durations else 0.0
    warnings: list[str] = []
    if len(speakers) < 5:
        warnings.append("speaker_count_below_5")
    if mix < 500:
        warnings.append("mix_clips_below_500")
    if numeric < 200:
        warnings.append("numeric_clips_below_200")
    if commercial_speakers < 5:
        warnings.append("commercial_consent_speakers_below_5")
    if not rows:
        warnings.append("zero_clips")
    if durations and statistics.mean(durations) < 0.5:
        warnings.append("very_short_average_duration")

    # imbalance: any speaker >50% of clips
    if rows and per_speaker_clips:
        top = max(per_speaker_clips.values())
        if top / len(rows) > 0.5:
            warnings.append("speaker_imbalance_over_50pct")

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "speaker_count": len(speakers),
        "speakers": speakers,
        "consent_count": len(consents),
        "commercial_consent_speakers": commercial_speakers,
        "clips": len(rows),
        "hours": round(total_hours, 4),
        "average_duration_s": round(statistics.mean(durations), 3) if durations else 0.0,
        "median_duration_s": round(statistics.median(durations), 3) if durations else 0.0,
        "language_class": dict(by_lang),
        "EN": by_lang.get("EN", 0),
        "NE": by_lang.get("NE", 0),
        "MIX": mix,
        "numeric_clips": numeric,
        "financial_clips": financial,
        "bucket": dict(by_bucket),
        "split": dict(by_split),
        "qa_status": dict(by_qa),
        "clips_per_speaker": dict(per_speaker_clips),
        "hours_per_speaker": {k: round(v, 4) for k, v in per_speaker_hours.items()},
        "device_distribution": dict(devices),
        "noise_class_distribution": dict(noise),
        "warnings": warnings,
    }
    print(json.dumps(report, indent=2))
    out = args.report or (MANIFESTS / "dataset_statistics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
