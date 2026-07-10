"""Critical regression manifest — the checks that must never silently break.

Stored as JSON (`saathi/repair/critical_checks.json`). Each check has a stable
id, pytest targets (validated node ids, no shell), subsystem, and blocking
flag. `run_critical_checks()` executes them via the existing verify runner.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from saathi.repair import verify as verify_mod

ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = Path(__file__).resolve().parent / "critical_checks.json"

# pytest node ids only — path[::test]. Blocks shell metacharacters.
_NODE_RE = re.compile(r"^[\w./-]+(::[\w\[\]-]+)*$")


@dataclass
class CriticalCheck:
    id: str
    targets: list[str]
    subsystem: str
    blocking: bool = True


def validate_node_id(node: str) -> bool:
    return bool(_NODE_RE.match(node))


def load_manifest(path: Path | None = None) -> list[CriticalCheck]:
    p = path or MANIFEST_PATH
    data = json.loads(p.read_text())
    checks = []
    for row in data.get("critical_checks", []):
        targets = [t for t in row.get("targets", []) if validate_node_id(t)]
        if targets:
            checks.append(CriticalCheck(id=row["id"], targets=targets,
                                        subsystem=row.get("subsystem", ""),
                                        blocking=bool(row.get("blocking", True))))
    return checks


def run_critical_checks(path: Path | None = None,
                        runner=None) -> dict:
    """Run every check. Returns {id: {"ok": bool, ...}, "_all_ok": bool}."""
    run = runner or verify_mod.run_pytest
    results: dict = {}
    all_ok = True
    for chk in load_manifest(path):
        out = run(chk.targets)
        ok = out.ran and out.failed == 0 and out.errors == 0
        results[chk.id] = {"ok": ok, "subsystem": chk.subsystem,
                           "blocking": chk.blocking, **out.to_dict()}
        if chk.blocking and not ok:
            all_ok = False
    # server import + route count are always part of the critical set
    import_ok, routes = verify_mod.server_smoke()
    results["server.import"] = {"ok": import_ok, "routes": routes,
                                "subsystem": "server", "blocking": True}
    if not import_ok:
        all_ok = False
    results["_all_ok"] = all_ok
    return results
