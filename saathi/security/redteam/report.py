"""M15.2 sanitized red-team report generation."""
from __future__ import annotations

import time

from saathi.security.redteam.config import redact_obj
from saathi.security.redteam.runner import run_all, run_suite
from saathi.security.redteam.hackagent import availability


def build_report(*, suite: str | None = None, config=None) -> dict:
    result = run_suite(suite=suite, config=config) if suite else run_all(config)
    s = result["summary"]
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "suite": s["suite"],
        "corpus_version": s["corpus_version"],
        "hackagent": availability(),
        "totals": {
            "attacks": s["total_attacks"],
            "boundaries_held": s["boundaries_held"],
            "confirmed_vulnerabilities": s["confirmed_vulnerabilities"],
            "confirmed_by_severity": s["confirmed_by_severity"],
            "release_blocking": s["release_blocking"],
        },
        "verdict": _verdict(s),
        # only failed (vulnerable) findings are surfaced in detail, redacted
        "confirmed_findings": [redact_obj(f) for f in result["findings"]
                               if not f["boundary_held"]],
        "evidence_note": "deterministic probes authoritative; HackAgent advisory only",
    }
    return report


def _verdict(summary: dict) -> str:
    if summary["release_blocking"] > 0:
        return "SECURITY NOT READY"
    if summary["confirmed_vulnerabilities"] > 0:
        return "SECURITY DEVELOPMENT READY"
    return "SECURITY STAGING READY"


def release_gate(config=None) -> dict:
    """Release gate: no Critical/High confirmed findings. Deterministic only."""
    result = run_all(config)
    s = result["summary"]
    return {
        "passed": s["release_blocking"] == 0,
        "release_blocking": s["release_blocking"],
        "release_blocking_ids": s["release_blocking_ids"],
        "confirmed_vulnerabilities": s["confirmed_vulnerabilities"],
        "verdict": _verdict(s),
    }
