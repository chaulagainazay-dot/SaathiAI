"""M39.7 — Reproducibility & clean-environment validation (offline).

Additive extension of M39. Proves the M39.x offline surface is reproducible and
self-contained: every evidence builder is deterministic (built twice, compared
canonically), the M39.x modules import only allowlisted top-level packages (no
undeclared third-party / network dependency at import), and the documented CLI
command contract is enumerable.

No production code is changed by this module; it only inspects and re-builds.
Authorities unchanged.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any, Callable

from saathi.credentials import m39_1, m39_2, m39_3, m39_4, m39_5
from saathi.credentials.leakscan import is_clean
from saathi.credentials.m39 import AUTHORITIES, NON_PRODUCTION_BANNER, _hmac

SCHEMA_VERSION = "m39_7.reproducibility.v1"
_FP_DOMAIN = b"saathi.m39_7.reproducibility.domain.v1"

# evidence builders across the offline series (deterministic dict -> dict)
EVIDENCE_BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "m39_1": m39_1.build_m39_1_evidence,
    "m39_2": m39_2.build_m39_2_evidence,
    "m39_3": m39_3.build_m39_3_evidence,
    "m39_4": m39_4.build_m39_4_evidence,
    "m39_5": m39_5.build_m39_5_evidence,
}

# M39.x modules that must remain self-contained
_M39X_MODULES = ("m39", "m39_1", "m39_2", "m39_3", "m39_4", "m39_5", "m39_7")

# top-level packages the M39.x modules are allowed to import
_ALLOWED_IMPORT_ROOTS = frozenset({
    # stdlib used across the series
    "__future__", "ast", "hashlib", "hmac", "json", "os", "re", "subprocess",
    "sys", "threading", "time", "dataclasses", "enum", "pathlib", "typing",
    "importlib",
    # first-party
    "saathi",
})

# documented CLI commands for the M39.x offline surface (contract)
DOCUMENTED_CLI_COMMANDS = (
    "m39-preflight", "m39-evaluate-canary-eligibility",
    "m39-1-plan", "m39-1-preview", "m39-1-backend-availability",
    "m39-1-revocation-checklist", "m39-1-diagnostics", "m39-1-emit-evidence",
    "m39-2-simulate-fault", "m39-2-simulation-matrix", "m39-2-emit-evidence",
    "m39-3-prerequisites", "m39-3-framework", "m39-3-approval-schema",
    "m39-3-validate-approval", "m39-3-canary-decision", "m39-3-emit-evidence",
    "m39-4-validate-config", "m39-4-release-checklist", "m39-4-rollback-plan",
    "m39-4-backward-compat", "m39-4-emit-evidence",
    "m39-5-audit-contracts", "m39-5-validate-event", "m39-5-alert-definitions",
    "m39-5-detect-alerts", "m39-5-incident-runbook", "m39-5-recovery-runbook",
    "m39-5-emit-evidence",
)


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def reproduce_evidence(name: str) -> dict[str, Any]:
    """Build one evidence set twice and compare canonically."""
    builder = EVIDENCE_BUILDERS.get(name)
    if builder is None:
        return {"name": name, "reproducible": False, "reason": "unknown_builder"}
    a = builder()
    b = builder()
    match = _canon(a) == _canon(b)
    return {
        "name": name,
        "reproducible": match,
        "clean": all(is_clean(v) for v in a.values()),
        "fingerprint": _hmac(_FP_DOMAIN, _canon(a).encode(), length=24),
    }


def reproduce_all() -> dict[str, Any]:
    results = [reproduce_evidence(n) for n in EVIDENCE_BUILDERS]
    return {
        "schema": "m39_7.reproduce_all.v1",
        "results": results,
        "all_reproducible": all(r["reproducible"] for r in results),
        "all_clean": all(r["clean"] for r in results),
        "count": len(results),
        "contains_secret_values": False,
    }


def _module_path(mod_name: str) -> Path:
    return Path(__file__).parent / f"{mod_name}.py"


def validate_dependencies() -> dict[str, Any]:
    """Assert M39.x modules import only allowlisted top-level packages."""
    violations: list[dict[str, str]] = []
    checked: list[str] = []
    for mod in _M39X_MODULES:
        path = _module_path(mod)
        if not path.exists():
            violations.append({"module": mod, "issue": "module_file_missing"})
            continue
        checked.append(mod)
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in _ALLOWED_IMPORT_ROOTS:
                        violations.append({"module": mod, "import": alias.name})
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if node.level == 0 and root and root not in _ALLOWED_IMPORT_ROOTS:
                    violations.append({"module": mod, "import": node.module or ""})
    return {
        "schema": "m39_7.dependencies.v1",
        "checked": checked,
        "self_contained": not violations,
        "violations": violations,
        "allowed_roots": sorted(_ALLOWED_IMPORT_ROOTS),
        "contains_secret_values": False,
    }


def cli_contract() -> dict[str, Any]:
    """Return the documented CLI command contract for the M39.x offline surface."""
    return {
        "schema": "m39_7.cli_contract.v1",
        "commands": list(DOCUMENTED_CLI_COMMANDS),
        "count": len(DOCUMENTED_CLI_COMMANDS),
        "contains_secret_values": False,
    }


def build_m39_7_evidence() -> dict[str, dict[str, Any]]:
    repro = reproduce_all()
    deps = validate_dependencies()
    contract = cli_contract()
    verdict = (
        "REPRODUCIBLE_AND_SELF_CONTAINED"
        if (repro["all_reproducible"] and repro["all_clean"] and deps["self_contained"])
        else "REPRODUCIBILITY_ISSUE"
    )
    return {
        "reproduce_all": repro,
        "dependencies": deps,
        "cli_contract": contract,
        "summary": {
            "schema": "m39_7.summary.v1",
            "milestone": "M39.7",
            "verdict": verdict,
            "python_version": ".".join(str(x) for x in sys.version_info[:2]),
            "authorities": dict(AUTHORITIES),
            "banner": NON_PRODUCTION_BANNER,
            "trading_guardian": "UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m39_7_evidence(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m39_7_evidence()
    written: list[str] = []
    for name, b in bodies.items():
        assert is_clean(b), f"m39_7 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out)}
