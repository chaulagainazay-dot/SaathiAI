#!/usr/bin/env python3
"""Speaker-disjoint TRAIN / VALIDATION / TEST assignment.

Policy:
- Prefer speaker-disjoint validation and test.
- If fewer than 5 PRODUCT_CLEAN speakers with PASS clips, leave UNASSIGNED
  and mark gate blocked.
- Exact audio SHA duplicates never appear in multiple splits.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
MANIFESTS = CORPUS / "manifests"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=MANIFESTS / "dataset_manifest.jsonl")
    ap.add_argument("--min-speakers", type=int, default=5)
    ap.add_argument("--val-speakers", type=int, default=1)
    ap.add_argument("--test-speakers", type=int, default=1)
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args()

    if not args.manifest.exists():
        report = {
            "status": "NO_MANIFEST",
            "speaker_disjoint": False,
            "training_split_ready": False,
            "message": "No clips to split",
        }
        print(json.dumps(report, indent=2))
        out = args.report or (MANIFESTS / "split_report.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0

    rows = [json.loads(l) for l in args.manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    # Only PRODUCT_CLEAN + PASS
    eligible = [
        r
        for r in rows
        if r.get("bucket") == "PRODUCT_CLEAN" and r.get("qa_status") == "PASS"
    ]
    by_speaker: dict[str, list[dict]] = defaultdict(list)
    for r in eligible:
        by_speaker[r["speaker_id"]].append(r)

    speakers = sorted(by_speaker.keys())
    n_spk = len(speakers)

    if n_spk < args.min_speakers:
        for r in rows:
            if r.get("bucket") == "PRODUCT_CLEAN":
                r["split"] = "UNASSIGNED"
        _write(rows, args.manifest)
        report = {
            "status": "SPEAKER_DIVERSITY_INSUFFICIENT",
            "eligible_speakers": n_spk,
            "min_speakers": args.min_speakers,
            "speaker_disjoint": False,
            "training_split_ready": False,
            "train_speakers": [],
            "val_speakers": [],
            "test_speakers": [],
            "counts": {"TRAIN": 0, "VALIDATION": 0, "TEST": 0, "UNASSIGNED": len(rows)},
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(report, indent=2))
        out = args.report or (MANIFESTS / "split_report.json")
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0

    # Assign last speakers to test/val for stability
    test_spk = speakers[-args.test_speakers :]
    remain = speakers[: -args.test_speakers] if args.test_speakers else speakers
    val_spk = remain[-args.val_speakers :] if args.val_speakers else []
    train_spk = remain[: -args.val_speakers] if args.val_speakers else remain

    # Hash dedupe: first occurrence wins across all splits
    seen_hash: set[str] = set()
    counts = {"TRAIN": 0, "VALIDATION": 0, "TEST": 0, "UNASSIGNED": 0}
    clip_map = {r["clip_id"]: r for r in rows}

    for r in rows:
        if r.get("bucket") != "PRODUCT_CLEAN" or r.get("qa_status") != "PASS":
            r["split"] = "UNASSIGNED"
            counts["UNASSIGNED"] += 1
            continue
        h = r.get("sha256") or ""
        if h and h in seen_hash:
            r["split"] = "UNASSIGNED"
            r["qa_errors"] = list(r.get("qa_errors") or []) + ["duplicate_audio_hash"]
            counts["UNASSIGNED"] += 1
            continue
        if h:
            seen_hash.add(h)
        spk = r["speaker_id"]
        if spk in test_spk:
            r["split"] = "TEST"
            counts["TEST"] += 1
        elif spk in val_spk:
            r["split"] = "VALIDATION"
            counts["VALIDATION"] += 1
        elif spk in train_spk:
            r["split"] = "TRAIN"
            counts["TRAIN"] += 1
        else:
            r["split"] = "UNASSIGNED"
            counts["UNASSIGNED"] += 1

    # Verify speaker-disjoint: no speaker in TRAIN∩TEST or TRAIN∩VAL
    train_set = set(train_spk)
    val_set = set(val_spk)
    test_set = set(test_spk)
    disjoint = (
        not (train_set & val_set)
        and not (train_set & test_set)
        and not (val_set & test_set)
        and len(test_set) >= 1
    )

    _write(rows, args.manifest)
    report = {
        "status": "READY" if disjoint and counts["TRAIN"] > 0 and counts["TEST"] > 0 else "INCOMPLETE",
        "eligible_speakers": n_spk,
        "speaker_disjoint": disjoint,
        "training_split_ready": disjoint and counts["TRAIN"] > 0 and counts["TEST"] > 0,
        "train_speakers": train_spk,
        "val_speakers": val_spk,
        "test_speakers": test_spk,
        "counts": counts,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(report, indent=2))
    out = args.report or (MANIFESTS / "split_report.json")
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


def _write(rows: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
