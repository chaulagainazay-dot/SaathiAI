"""Test baseline — machine-readable quality record.

Stored at data/repair_baseline.json. Updated ONLY after the full validation
ladder succeeds (`update_baseline` is called by the loop/CLI exclusively on
full success — never on partial results).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BASELINE_PATH = ROOT / "data" / "repair_baseline.json"


def read_baseline(path: Path | None = None) -> dict:
    p = path or BASELINE_PATH
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def update_baseline(*, branch: str, commit: str, passed: int, failed: int,
                    skipped: int, collection_errors: int, duration_sec: float,
                    server_import: bool, route_count: int,
                    path: Path | None = None,
                    full_success: bool = False) -> dict:
    """Write the baseline. Refuses unless `full_success` is explicitly True.

    `full_success` must only be set by a caller that has completed the entire
    validation ladder (focused + full suite + server import + route count).
    """
    if not full_success:
        raise ValueError("baseline may only be updated after full validation success")
    p = path or BASELINE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "branch": branch, "commit": commit,
        "passed": passed, "failed": failed, "skipped": skipped,
        "collection_errors": collection_errors,
        "duration_sec": round(duration_sec, 1),
        "server_import": server_import, "route_count": route_count,
        "timestamp": time.time(),
    }
    p.write_text(json.dumps(data, indent=1))
    return data
