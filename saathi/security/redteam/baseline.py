"""M15.2 security baseline + comparison (machine-readable, redacted)."""
from __future__ import annotations

import json
import time
from pathlib import Path

from saathi.security.redteam.config import (
    redact_obj, HACKAGENT_PINNED_VERSION,
)
from saathi.security.redteam.runner import run_all, ROOT

BASELINE = ROOT / "security" / "redteam" / "baselines" / "baseline.json"


def generate(config=None, path: Path | None = None) -> dict:
    result = run_all(config)
    fps = {f["finding_id"]: (not f["boundary_held"]) for f in result["findings"]}
    doc = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "corpus_version": result["summary"]["corpus_version"],
        "hackagent_pinned": HACKAGENT_PINNED_VERSION,
        "hackagent_status": "environment_blocked",
        "totals": {
            "attacks": result["summary"]["total_attacks"],
            "boundaries_held": result["summary"]["boundaries_held"],
            "confirmed_vulnerabilities": result["summary"]["confirmed_vulnerabilities"],
            "release_blocking": result["summary"]["release_blocking"],
        },
        "fingerprints": fps,
    }
    doc = redact_obj(doc)
    p = path or BASELINE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2))
    return doc


def load(path: Path | None = None) -> dict | None:
    p = path or BASELINE
    if not p.exists():
        return None
    return json.loads(p.read_text())


def compare(config=None, path: Path | None = None) -> dict:
    prev = load(path)
    current = run_all(config)
    cur_fps = {f["finding_id"]: (not f["boundary_held"]) for f in current["findings"]}
    if prev is None:
        return {"status": "no_baseline", "current": current["summary"]}
    prev_fps = prev.get("fingerprints", {})
    new_vulns = [k for k, v in cur_fps.items() if v and not prev_fps.get(k, False)]
    resolved = [k for k, v in prev_fps.items() if v and not cur_fps.get(k, False)]
    recurring = [k for k, v in cur_fps.items() if v and prev_fps.get(k, False)]
    return {
        "status": "compared",
        "new_vulnerabilities": new_vulns,
        "resolved": resolved,
        "recurring": recurring,
        "current_summary": current["summary"],
        "regression": len(new_vulns) > 0,
    }
