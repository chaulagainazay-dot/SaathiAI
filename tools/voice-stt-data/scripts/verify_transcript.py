#!/usr/bin/env python3
"""Human transcript verification helper.

Marks human_verified=true only when an operator supplies the verified transcript.
LLMs must not call this to invent corrections.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

CORPUS = Path.home() / ".saathi" / "stt-product-corpus"
MANIFESTS = CORPUS / "manifests"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip-id", required=True)
    ap.add_argument("--transcript", required=True, help="What the speaker actually said")
    ap.add_argument("--manifest", type=Path, default=MANIFESTS / "dataset_manifest.jsonl")
    ap.add_argument("--canonical-number", default=None)
    args = ap.parse_args()

    if not args.manifest.exists():
        print("No manifest")
        return 2
    rows = [json.loads(l) for l in args.manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    found = False
    for r in rows:
        if r.get("clip_id") == args.clip_id:
            r["transcript"] = args.transcript
            r["human_verified"] = True
            r["transcript_verified_at"] = datetime.now(timezone.utc).isoformat()
            if args.canonical_number is not None:
                r["canonical_number"] = args.canonical_number
            found = True
            break
    if not found:
        print("clip not found:", args.clip_id)
        return 2
    with args.manifest.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("verified", args.clip_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
