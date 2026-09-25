#!/usr/bin/env python3
"""QA a JSONL training manifest (metadata only; audio paths may be local)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ALLOWED_BUCKETS = {"PRODUCT_CLEAN", "OWNER_PRIVATE", "RESEARCH_ONLY", "REJECTED"}
REQUIRED = {"utt_id", "audio_path", "text", "bucket", "speaker_id", "lang"}


def qa_item(obj: dict, line_no: int) -> list[str]:
    errs = []
    missing = REQUIRED - set(obj)
    if missing:
        errs.append(f"L{line_no}: missing {sorted(missing)}")
    b = obj.get("bucket")
    if b not in ALLOWED_BUCKETS:
        errs.append(f"L{line_no}: bad bucket {b!r}")
    if b == "PRODUCT_CLEAN" and obj.get("commercial_training_ok") is False:
        errs.append(f"L{line_no}: PRODUCT_CLEAN but commercial_training_ok=false")
    if obj.get("lang") not in ("en", "ne", "mixed", None):
        errs.append(f"L{line_no}: unexpected lang {obj.get('lang')!r}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--require-product-clean-count", type=int, default=0)
    args = ap.parse_args()
    if not args.manifest.exists():
        print(f"MISSING {args.manifest}", file=sys.stderr)
        return 1
    errors = []
    n_pc = 0
    with args.manifest.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            errors.extend(qa_item(obj, i))
            if obj.get("bucket") == "PRODUCT_CLEAN":
                n_pc += 1
    if n_pc < args.require_product_clean_count:
        errors.append(
            f"product_clean count {n_pc} < required {args.require_product_clean_count}"
        )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    print(f"QA_OK lines product_clean={n_pc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
