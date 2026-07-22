"""Repair journal — per-run JSON + Markdown reports in artifacts/repairs/.

Reports never contain secrets: all strings pass through redact() and env
values are represented as presence booleans upstream.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from saathi.repair.secrets_scan import redact

ROOT = Path(__file__).resolve().parent.parent.parent
JOURNAL_DIR = ROOT / "artifacts" / "repairs"


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def write_run_report(payload: dict, *, directory: Path | None = None) -> tuple[Path, Path]:
    """Write repair-<stamp>.json + .md. Returns (json_path, md_path)."""
    d = directory or JOURNAL_DIR
    d.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    jpath = d / f"repair-{stamp}.json"
    mpath = d / f"repair-{stamp}.md"

    def _clean(v):
        if isinstance(v, str):
            return redact(v)
        if isinstance(v, list):
            return [_clean(x) for x in v]
        if isinstance(v, dict):
            return {k: _clean(x) for k, x in v.items()}
        return v

    safe = _clean(payload)
    jpath.write_text(json.dumps(safe, indent=1, default=str))

    md = [f"# Repair run — {stamp}", ""]
    for key in ("incident_id", "status", "category", "policy", "risk",
                "root_cause", "message", "repair_commit", "rollback_ref",
                "recommended_next_action"):
        if safe.get(key):
            md.append(f"- **{key}**: {safe[key]}")
    if safe.get("files_changed"):
        md.append("\n## Files changed")
        md += [f"- {f}" for f in safe["files_changed"]]
    if safe.get("tests"):
        md.append("\n## Tests")
        md.append(f"```json\n{json.dumps(safe['tests'], indent=1)}\n```")
    if safe.get("validation"):
        md.append("\n## Validation")
        md.append(f"```json\n{json.dumps(safe['validation'], indent=1, default=str)}\n```")
    mpath.write_text("\n".join(md) + "\n")
    return jpath, mpath


def latest_report(directory: Path | None = None) -> dict | None:
    d = directory or JOURNAL_DIR
    if not d.exists():
        return None
    files = sorted(d.glob("repair-*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text())
    except Exception:
        return None
