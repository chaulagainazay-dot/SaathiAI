#!/usr/bin/env python3
"""Ensure train manifest IDs do not collide with locked eval corpora."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_EVAL = [
    REPO / "tools/voice-stt-bench/corpus/manifest.json",
    REPO / "tools/voice-stt-bench/corpus/codeswitch/manifest.json",
]


def load_eval_ids(paths: list[Path]) -> set[str]:
    ids: set[str] = set()
    for p in paths:
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        for it in data.get("items", []):
            if it.get("id"):
                ids.add(str(it["id"]))
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--eval", type=Path, nargs="*", default=DEFAULT_EVAL)
    args = ap.parse_args()
    eval_ids = load_eval_ids(list(args.eval))
    if not args.train.exists():
        # empty train is OK for readiness (data insufficient)
        print("TRAIN_MANIFEST_ABSENT (ok for readiness phase)")
        return 0
    collisions = []
    with args.train.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            uid = str(obj.get("utt_id") or obj.get("id") or "")
            if uid in eval_ids:
                collisions.append(uid)
    if collisions:
        print("CONTAMINATION", collisions[:20], file=sys.stderr)
        return 2
    print(f"NO_CONTAMINATION eval_ids={len(eval_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
