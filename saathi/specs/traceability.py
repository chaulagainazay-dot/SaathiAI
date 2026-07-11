"""Traceability + convergence gate for SaathiOS spec-driven delivery.

A milestone's traceability.json lists requirements, each with a stable ID, an
implementing artifact (file path), and a test node id. The convergence gate
fails if any requirement is missing its artifact file or its test file, or if a
requirement id is malformed. This is the deterministic enforcement of
Constitution Article VII.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_ID_RE = re.compile(r"^M\d+-[A-Z]+-\d{3}$")


def load_traceability(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def validate_traceability(doc: dict) -> list[str]:
    """Return a list of problems (empty == valid)."""
    problems: list[str] = []
    seen: set[str] = set()
    for req in doc.get("requirements", []):
        rid = req.get("id", "")
        if not _ID_RE.match(rid):
            problems.append(f"malformed requirement id: {rid!r}")
        if rid in seen:
            problems.append(f"duplicate requirement id: {rid}")
        seen.add(rid)
        art = req.get("artifact", "")
        if not art or not (ROOT / art).exists():
            problems.append(f"{rid}: artifact missing ({art})")
        test = req.get("test", "")
        test_file = test.split("::", 1)[0] if test else ""
        if not test_file or not (ROOT / test_file).exists():
            problems.append(f"{rid}: test file missing ({test_file})")
    if not doc.get("requirements"):
        problems.append("no requirements declared")
    return problems


def converge(path: str | Path) -> dict:
    """Run the convergence gate over a traceability file."""
    doc = load_traceability(path)
    problems = validate_traceability(doc)
    reqs = doc.get("requirements", [])
    return {
        "milestone": doc.get("milestone"),
        "constitution_version": doc.get("constitution_version"),
        "requirements": len(reqs),
        "problems": problems,
        "verdict": "CONVERGED" if not problems else "NOT_CONVERGED",
    }
