#!/usr/bin/env python3
"""
Whisper Small LoRA training entrypoint — readiness package.

Hard-refuses unless TRAINING_MANIFEST.training_authorized is true.
Does NOT launch paid jobs. Do not run production training on the 8 GB Mac.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, default=ROOT / "configs/lora_whisper_small.yaml")
    ap.add_argument("--dry-run", action="store_true", help="Print plan only")
    args = ap.parse_args()

    # Hard gate
    rc = subprocess.call([sys.executable, str(ROOT / "scripts/validate_authorization.py")])
    if rc != 0:
        print(
            "Refusing train: authorization gate failed.\n"
            "Complete product-clean multi-speaker mixed data + owner auth first.",
            file=sys.stderr,
        )
        return rc

    if args.dry_run:
        print("DRY_RUN would train with", args.config)
        return 0

    # Real training body intentionally not executed without explicit future authorization
    # and installed training deps (transformers/peft/datasets).
    print(
        "AUTHORIZED path reached — implement/execute remote GPU job per HUGGINGFACE_JOBS_PLAN.md",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
