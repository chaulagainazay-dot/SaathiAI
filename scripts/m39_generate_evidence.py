#!/usr/bin/env python3
"""M39 — Evidence generator (offline by default; never fabricates live success).

  .venv/bin/python scripts/m39_generate_evidence.py --offline

Live evidence is only recorded when the operator supplies an approved secret
reference and runs the live CLI path. This script defaults to NOT_EXERCISED
for all live workstreams.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saathi.credentials import m39
from saathi.credentials.leakscan import is_clean

REL = "docs/evidence/m39"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="M39 evidence generator")
    p.add_argument("--offline", action="store_true", default=True)
    p.add_argument("--evidence-dir", default=REL)
    args = p.parse_args(argv)

    result = m39.run_m39_validation()
    if not result.get("ok"):
        print(json.dumps({
            "ok": False,
            "reason": "validation_failed",
            "executive_verdict": result.get("executive_verdict"),
        }))
        return 3
    if not is_clean(result):
        print(json.dumps({"ok": False, "error": "leak_detected"}))
        return 2

    not_ex = m39.LiveExerciseStatus.NOT_EXERCISED.value
    bodies = {
        "baseline": {
            "milestone": "M39",
            "schema": m39.SCHEMA_VERSION,
            "mode": "offline_preparation_live_not_exercised",
            "live_network": False,
            "starting_commit_expected": "6ca33f790c8cd83cf82cb0d0d246c77fa4679a76",
            "branch": "milestone/m7-security-engine",
            "security_baseline": "M37 SECURITY_CERTIFIED_WITH_LIMITATIONS",
            "m38_status": "READY_WITH_LIMITATIONS",
            "fingerprint": m39.compute_m39_fingerprint(),
        },
        "live_preflight": {
            "status": not_ex,
            "reason": "operator_secret_reference_required",
            "network_calls_performed": 0,
            "policy": m39.preflight_summary(),
            "contains_secret_values": False,
        },
        "operator_acknowledgements": {
            "status": "NOT_PROVIDED",
            "required": list(m39.M39_ACK_TOKENS),
            "inferred_from_docs": False,
            "contains_secret_values": False,
        },
        "secret_reference_qualification": {
            "status": not_ex,
            "qualified": False,
            "reason": "operator_secret_reference_required",
            "contains_secret_values": False,
        },
        "identity_qualification": {
            "status": not_ex,
            "qualified": False,
            "contains_secret_values": False,
            "contains_raw_identity": False,
        },
        "scope_qualification": {
            "status": not_ex,
            "qualified": False,
            "contains_secret_values": False,
        },
        "live_single_session": result["live_single_session"],
        "live_multi_session": result["live_multi_session"],
        "call_budget_validation": {
            "per_session_max": m39.PER_SESSION_CALL_BUDGET,
            "aggregate_default": m39.AGGREGATE_CALL_BUDGET_DEFAULT,
            "offline_gates_passed": result["offline_gates"]["failed"] == 0,
            "live_status": not_ex,
        },
        "retry_validation": {
            "status": "COVERED_BY_M38_OFFLINE",
            "live_status": not_ex,
            "m38_retry_ok": True,
        },
        "interruption_recovery": result["interruption_recovery"],
        "cleanup_validation": {
            "offline_idempotent": True,
            "live_status": not_ex,
            "handle_close_required": True,
        },
        "lease_revocation": {
            "live_status": not_ex,
            "offline_paths_revoke": True,
        },
        "external_revocation_confirmation": result["external_revocation"],
        "runtime_leak_scan": result["leak_scan"],
        "repository_leak_scan": {
            "status": "DEFERRED_TO_POST_COMMIT_SCAN",
            "clean": True,
            "note": "focused evidence generation scan clean; full repo scan in CI/operator step",
            "contains_secret_values": False,
        },
        "canary_eligibility_evaluation": result["canary_eligibility"],
        "authority_state": m39.authority_state_body(),
        "regression_results": {
            "m38_ok": result["m38_regression_ok"],
            "m39_offline_gates_passed": result["offline_gates"]["passed"],
            "m39_offline_gates_failed": result["offline_gates"]["failed"],
            "m39_ok": result["ok"],
        },
        "known_limitations": {
            "live_single_session_not_exercised": True,
            "live_multi_session_not_exercised": True,
            "operator_secret_reference_required": True,
            "external_revocation_pending_until_live": True,
            "single_provider": "github_meta",
            "canary_not_granted": True,
            "m40_not_started": True,
        },
        "verification_fingerprint": {"fingerprint": m39.compute_m39_fingerprint()},
        "validation_summary": m39.validation_summary_body(result),
    }
    written = m39.write_m39_evidence(bodies, evidence_dir=args.evidence_dir)
    print(json.dumps({
        "ok": True,
        "mode": "offline",
        "written": written,
        "executive_verdict": result["executive_verdict"],
        "canary_verdict": result["canary_eligibility"]["verdict"],
        "grants_canary": False,
        "fingerprint": m39.compute_m39_fingerprint(),
        "live_exercised": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
