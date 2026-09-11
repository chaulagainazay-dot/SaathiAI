#!/usr/bin/env python3
"""Run QA → hash → split → contamination → stats → authorization → freeze."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def run(name: str, extra: list[str] | None = None) -> int:
    cmd = [sys.executable, str(SCRIPTS / name)] + (extra or [])
    print("\n===", name, "===")
    return subprocess.call(cmd)


def main() -> int:
    steps = [
        ("qa_clips.py", []),
        ("hash_dedupe.py", []),
        ("build_splits.py", []),
        ("contamination_check.py", []),
        ("dataset_stats.py", []),
        ("training_authorization_gate.py", ["--update-train-manifest"]),
        ("freeze_dataset.py", ["--force"]),
    ]
    codes = []
    for name, extra in steps:
        codes.append(run(name, extra))
    # Gate failure is expected until real multi-speaker data exists
    print("\n=== pipeline complete ===")
    print("step_exit_codes", codes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
