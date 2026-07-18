#!/usr/bin/env python3
"""M37 — Deterministic offline security-certification evidence generator.

No network, no Keychain, no live credentials.
  .venv/bin/python scripts/m37_generate_evidence.py --offline
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saathi.credentials import m37
from saathi.credentials.leakscan import is_clean

REL = "docs/evidence/m37"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="M37 evidence generator")
    p.add_argument("--offline", action="store_true", default=True)
    p.add_argument("--evidence-dir", default=REL)
    args = p.parse_args(argv)

    result = m37.run_m37_validation(live_exercised=False)
    if not result.get("ok"):
        print(json.dumps({"ok": False, "reason": "validation_failed", "cert": result.get("certification")}))
        return 3
    if not is_clean(result):
        print(json.dumps({"ok": False, "error": "leak_detected"}))
        return 2

    # Stabilize volatile session ids for deterministic-ish evidence
    life = dict(result["lifecycle"])
    life["session_id"] = "sess_m37_synth_0001"
    for ev in life.get("events") or []:
        if isinstance(ev, dict) and "session_id" in ev:
            ev["session_id"] = "sess_m37_synth_0001"

    bodies = {
        "baseline": {
            "milestone": "M37",
            "schema": m37.SCHEMA_VERSION,
            "mode": "offline_synthetic_fixture",
            "live_network": False,
            "fingerprint": m37.compute_m37_fingerprint(),
            "starting_head_note": "see M37_FINAL_REPORT",
        },
        "provider_model": result["provider"],
        "lifecycle": life,
        "negative_validation": result["negative"],
        "security_certification": result["certification"],
        "m36_regression": {"ok": result["m36_regression_ok"]},
        "call_budget": life.get("call_budget") or {},
        "sandbox_validation": {
            "provider_id": "github_meta",
            "identity_ok": (life.get("identity_result") or {}).get("ok"),
            "operation_ok": (life.get("operation_result") or {}).get("ok"),
            "handle_closed": life.get("handle_closed"),
            "lease_revoked": life.get("lease_revoked"),
            "live_exercised": False,
        },
        "authorities": result["authorities"],
        "leak_scan": {"clean": True, "findings": [], "raw_secrets_found": 0},
        "validation_summary": m37.validation_summary_body(result),
        "verification_fingerprint": {"fingerprint": m37.compute_m37_fingerprint()},
        "regression": {
            "m36_ok": result["m36_regression_ok"],
            "m37_ok": result["ok"],
            "negative_passed": result["negative"]["passed"],
            "negative_total": result["negative"]["total"],
        },
    }
    written = m37.write_m37_evidence(bodies, evidence_dir=args.evidence_dir)
    print(json.dumps({
        "ok": True,
        "mode": "offline",
        "written": written,
        "certification": result["certification"]["state"],
        "fingerprint": m37.compute_m37_fingerprint(),
        "live_exercised": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
