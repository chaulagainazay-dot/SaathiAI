#!/usr/bin/env python3
"""SHA-256 rehash + exact-duplicate detection for product speech clips."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
MANIFESTS = CORPUS / "manifests"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=MANIFESTS / "dataset_manifest.jsonl")
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--rehash", action="store_true", help="Recompute SHA-256 from disk")
    args = ap.parse_args()

    if not args.manifest.exists():
        report = {
            "status": "NO_MANIFEST",
            "unique_hashes": 0,
            "duplicate_groups": [],
            "duplicate_clip_ids": [],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(report, indent=2))
        out = args.report or (MANIFESTS / "hash_dedupe_report.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0

    rows = [json.loads(l) for l in args.manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_hash: dict[str, list[str]] = defaultdict(list)
    by_clip: dict[str, int] = defaultdict(int)
    missing = 0

    for r in rows:
        cid = r.get("clip_id") or ""
        by_clip[cid] += 1
        path = Path(r.get("audio_path") or "")
        if args.rehash and path.exists():
            digest = sha256_file(path)
            r["sha256"] = digest
        digest = r.get("sha256") or ""
        if not digest:
            missing += 1
            continue
        by_hash[digest].append(cid)

    dup_groups = [
        {"sha256": h, "clip_ids": ids}
        for h, ids in sorted(by_hash.items())
        if len(ids) > 1
    ]
    dup_clip_ids = [cid for cid, n in by_clip.items() if n > 1]

    if args.rehash:
        with args.manifest.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "clips": len(rows),
        "unique_hashes": len(by_hash),
        "missing_hash": missing,
        "duplicate_audio_groups": len(dup_groups),
        "duplicate_groups": dup_groups[:50],
        "duplicate_clip_ids": dup_clip_ids,
        "status": "CLEAN" if not dup_groups and not dup_clip_ids else "DUPLICATES_FOUND",
    }
    print(json.dumps(report, indent=2))
    out = args.report or (MANIFESTS / "hash_dedupe_report.json")
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "CLEAN" or report["status"] == "NO_MANIFEST" else 1


if __name__ == "__main__":
    raise SystemExit(main())
