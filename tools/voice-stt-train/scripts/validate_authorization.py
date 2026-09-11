#!/usr/bin/env python3
"""Refuse training unless hard authorization + data thresholds are met."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "TRAINING_MANIFEST.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs/lora_whisper_small.yaml")
    args = ap.parse_args()
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if m.get("training_authorized") is not True:
        print("BLOCKED: training_authorized=false in TRAINING_MANIFEST.json", file=sys.stderr)
        print("PRODUCT_CLEAN_DATA_INSUFFICIENT_FOR_TRAINING", file=sys.stderr)
        return 2
    if m.get("paid_job_authorized") is not True and "--force-local" not in sys.argv:
        print("BLOCKED: paid_job_authorized=false", file=sys.stderr)
        return 3
    datasets = m.get("datasets", {}).get("product_clean") or []
    if len(datasets) < 1:
        print("BLOCKED: no product_clean datasets registered", file=sys.stderr)
        return 4
    print("AUTHORIZATION_OK (still requires human operator to launch job)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
