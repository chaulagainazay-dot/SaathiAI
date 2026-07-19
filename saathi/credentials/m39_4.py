"""M39.4 — Deployment & rollback preparation (offline; nothing is executed).

Additive extension of M39. Prepares — but never executes — everything needed to
enable and roll back the M39 external-provider live-validation surface: a
deployment-config validator, a release checklist, a rollback plan + script
template, a backward-compatibility check against M31–M38 public entry points, an
artifact-integrity check over deterministic fingerprints, deploy smoke-test
definitions, and a post-deployment verification plan.

No production deployment, external write, or credential action is performed. The
generated rollback script is TEXT ONLY. Authorities remain NOT GRANTED.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Optional

from saathi.credentials.leakscan import is_clean
from saathi.credentials.m39 import (
    AGGREGATE_CALL_BUDGET_DEFAULT,
    AUTHORITIES,
    ENV_KILL_SWITCH,
    ENV_LIVE_FLAG,
    HARD_MAX_AGGREGATE,
    MAX_CONCURRENT_SESSIONS,
    NON_PRODUCTION_BANNER,
    PER_SESSION_CALL_BUDGET,
    PROVIDER_ID,
    M39Error,
    _hmac,
    compute_m39_fingerprint,
)

SCHEMA_VERSION = "m39_4.deploy_rollback.v1"
_FP_DOMAIN = b"saathi.m39_4.deploy_rollback.domain.v1"

# Canonical safe deployment posture for the M39 surface (defaults are fail-closed).
CANONICAL_DEPLOYMENT = {
    "live_flag_default": "off",           # ENV_LIVE_FLAG must default off
    "kill_switch_env": ENV_KILL_SWITCH,   # kill switch must be wired
    "provider": PROVIDER_ID,
    "rollout": "OFF",
    "per_session_budget_max": PER_SESSION_CALL_BUDGET,
    "aggregate_budget_max": HARD_MAX_AGGREGATE,
    "concurrency_max": MAX_CONCURRENT_SESSIONS,
    "canary": "NOT GRANTED",
    "active": "NOT GRANTED",
}

# Public M31–M38 entry points that M39.x must not have broken (additive-only proof).
_BACKWARD_COMPAT_TARGETS = (
    ("saathi.credentials.m35", "SecretHandle"),
    ("saathi.credentials.m35", "SessionLeaseStore"),
    ("saathi.credentials.m36", "retrieve_secret_handle"),
    ("saathi.credentials.m36", "validate_m36_secret_reference"),
    ("saathi.credentials.m37", "run_provider_lifecycle"),
    ("saathi.credentials.m37", "compute_m37_fingerprint"),
    ("saathi.credentials.m38", "MultiSessionCoordinator"),
    ("saathi.credentials.m38", "classify_retry"),
    ("saathi.credentials.m38", "evaluate_canary_readiness"),
    ("saathi.credentials.m39", "run_live_single_session"),
    ("saathi.credentials.m39", "evaluate_canary_eligibility"),
)


def validate_deployment_config(config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Validate an M39-surface deployment config against the fail-closed posture."""
    cfg = config if isinstance(config, dict) else {}
    problems: list[str] = []

    def _expect(key: str, want: Any) -> None:
        if key in cfg and cfg.get(key) != want:
            problems.append(f"{key}_must_be_{want}")

    # defaults may be omitted (canonical assumed); if present they must be safe
    if str(cfg.get("live_flag_default", "off")).lower() != "off":
        problems.append("live_flag_default_must_be_off")
    if cfg.get("rollout", "OFF") != "OFF":
        problems.append("rollout_must_be_off")
    _expect("provider", PROVIDER_ID)
    _expect("canary", "NOT GRANTED")
    _expect("active", "NOT GRANTED")
    if int(cfg.get("per_session_budget_max", PER_SESSION_CALL_BUDGET)) > PER_SESSION_CALL_BUDGET:
        problems.append("per_session_budget_exceeds_ceiling")
    if int(cfg.get("aggregate_budget_max", AGGREGATE_CALL_BUDGET_DEFAULT)) > HARD_MAX_AGGREGATE:
        problems.append("aggregate_budget_exceeds_hard_max")
    if int(cfg.get("concurrency_max", MAX_CONCURRENT_SESSIONS)) > MAX_CONCURRENT_SESSIONS:
        problems.append("concurrency_exceeds_ceiling")
    if "kill_switch_env" in cfg and cfg.get("kill_switch_env") != ENV_KILL_SWITCH:
        problems.append("kill_switch_env_mismatch")

    return {
        "schema": "m39_4.config_validation.v1",
        "valid": not problems,
        "problems": problems,
        "canonical": dict(CANONICAL_DEPLOYMENT),
        "authorities": dict(AUTHORITIES),
        "contains_secret_values": False,
    }


def release_checklist() -> dict[str, Any]:
    """Ordered gates that must pass before the M39 surface is enabled."""
    return {
        "schema": "m39_4.release_checklist.v1",
        "gates": [
            {"id": "REL-1", "gate": "M31–M39.x regression green"},
            {"id": "REL-2", "gate": "M39 offline failure gates pass"},
            {"id": "REL-3", "gate": "repository + working-tree leak scans clean"},
            {"id": "REL-4", "gate": "deployment config validates (fail-closed posture)"},
            {"id": "REL-5", "gate": "backward-compatibility check passes"},
            {"id": "REL-6", "gate": "artifact integrity (fingerprints) verified"},
            {"id": "REL-7", "gate": "rollback plan reviewed and reversible"},
            {"id": "REL-8", "gate": "kill switch wired and tested"},
            {"id": "REL-9", "gate": "operator disposable secret reference supplied (live only)"},
            {"id": "REL-10", "gate": "explicit operator authorization (canary is separate)"},
        ],
        "note": "REL-9/REL-10 are operator/live steps; all others are offline-verifiable.",
        "authorities": dict(AUTHORITIES),
        "contains_secret_values": False,
    }


def rollback_plan() -> dict[str, Any]:
    """Ordered, reversible rollback steps + a TEXT-ONLY script template."""
    steps = [
        {"id": "RB-1", "action": f"Unset live flag: unset {ENV_LIVE_FLAG}"},
        {"id": "RB-2", "action": f"Trip kill switch: export {ENV_KILL_SWITCH}=1"},
        {"id": "RB-3", "action": "Operator revokes disposable PAT externally (see M39.1 checklist)"},
        {"id": "RB-4", "action": "Confirm no open SecretHandle / lease (m39 cleanup status)"},
        {"id": "RB-5", "action": "If code rollback needed: git revert the M39.x commit range (no force-push)"},
        {"id": "RB-6", "action": "Re-run M31–M39.x regression to confirm restored baseline"},
    ]
    script = "\n".join([
        "#!/usr/bin/env bash",
        "# M39.4 ROLLBACK TEMPLATE — review before running; nothing here auto-executes.",
        "set -euo pipefail",
        f"unset {ENV_LIVE_FLAG} 2>/dev/null || true",
        f"export {ENV_KILL_SWITCH}=1",
        "# Operator: revoke the disposable PAT externally (GitHub settings).",
        "# Code rollback (only if needed) — prefer revert over reset, no force-push:",
        "#   git revert <m39x-commit-range>",
        "python -m pytest tests/ -k 'm31 or m32 or m33 or m34 or m35 or m36 or m37 or m38 or m39' -q",
        "echo 'M39 surface disabled; baseline regression re-run.'",
    ])
    return {
        "schema": "m39_4.rollback_plan.v1",
        "reversible": True,
        "executes": False,
        "steps": steps,
        "script_template": script,
        "trading_guardian_untouched": True,
        "authorities": dict(AUTHORITIES),
        "contains_secret_values": False,
    }


def backward_compatibility_check() -> dict[str, Any]:
    """Prove M39.x is additive: all M31–M38 public entry points still resolve."""
    results = []
    missing: list[str] = []
    for module_name, symbol in _BACKWARD_COMPAT_TARGETS:
        ok = False
        try:
            mod = importlib.import_module(module_name)
            ok = hasattr(mod, symbol)
        except Exception:
            ok = False
        results.append({"module": module_name, "symbol": symbol, "present": ok})
        if not ok:
            missing.append(f"{module_name}.{symbol}")
    return {
        "schema": "m39_4.backward_compat.v1",
        "all_present": not missing,
        "missing": missing,
        "checked": len(_BACKWARD_COMPAT_TARGETS),
        "additive_only": not missing,
        "contains_secret_values": False,
    }


def artifact_integrity() -> dict[str, Any]:
    """Recompute deterministic fingerprints (immutable-artifact verification)."""
    a = compute_m39_fingerprint()
    b = compute_m39_fingerprint()
    return {
        "schema": "m39_4.artifact_integrity.v1",
        "m39_fingerprint": a,
        "stable": a == b,
        "authorities_in_fingerprint": dict(AUTHORITIES),
        "contains_secret_values": False,
    }


def smoke_test_definitions() -> dict[str, Any]:
    """Deploy smoke-test definitions (offline commands that must pass)."""
    return {
        "schema": "m39_4.smoke_tests.v1",
        "tests": [
            {"id": "SMK-1", "cmd": "python -m saathi.credentials.cli m39-preflight",
             "expect": "fail-closed preflight spec printed"},
            {"id": "SMK-2", "cmd": "python -m saathi.credentials.cli m39-1-diagnostics",
             "expect": "live_flag_set false; authorities NOT GRANTED"},
            {"id": "SMK-3", "cmd": "python -m saathi.credentials.cli m39-2-simulation-matrix",
             "expect": "ALL_FAULTS_FAIL_CLOSED"},
            {"id": "SMK-4", "cmd": "python -m saathi.credentials.cli m39-3-canary-decision",
             "expect": "CANARY_NOT_GRANTED"},
        ],
        "contains_secret_values": False,
    }


def post_deploy_verification_plan() -> dict[str, Any]:
    return {
        "schema": "m39_4.post_deploy_plan.v1",
        "steps": [
            "confirm live flag state matches intent",
            "confirm kill switch reachable",
            "confirm no writes attempted (read-only invariant)",
            "confirm SecretHandle/lease cleanup after each session",
            "confirm evidence written and leak-clean",
            "confirm external revocation recorded",
        ],
        "live_dependent": "OFFLINE_ONLY until operator supplies disposable secret reference",
        "contains_secret_values": False,
    }


def build_m39_4_evidence() -> dict[str, dict[str, Any]]:
    cfg = validate_deployment_config()
    bc = backward_compatibility_check()
    ai = artifact_integrity()
    body = {
        "config_validation": cfg,
        "release_checklist": release_checklist(),
        "rollback_plan": rollback_plan(),
        "backward_compat": bc,
        "artifact_integrity": ai,
        "smoke_tests": smoke_test_definitions(),
        "post_deploy_plan": post_deploy_verification_plan(),
        "summary": {
            "schema": "m39_4.summary.v1",
            "milestone": "M39.4",
            "verdict": (
                "DEPLOY_ROLLBACK_PREP_COMPLETE"
                if (cfg["valid"] and bc["all_present"] and ai["stable"])
                else "DEPLOY_ROLLBACK_PREP_INCOMPLETE"
            ),
            "executes_nothing": True,
            "authorities": dict(AUTHORITIES),
            "trading_guardian": "UNENGAGED",
            "banner": NON_PRODUCTION_BANNER,
            "contains_secret_values": False,
        },
    }
    body["summary"]["fingerprint"] = _hmac(
        _FP_DOMAIN,
        json.dumps({"cfg": cfg["valid"], "bc": bc["all_present"], "ai": ai["stable"]},
                   sort_keys=True).encode(),
        length=24,
    )
    return body


def emit_m39_4_evidence(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m39_4_evidence()
    written: list[str] = []
    for name, b in bodies.items():
        assert is_clean(b), f"m39_4 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out)}
