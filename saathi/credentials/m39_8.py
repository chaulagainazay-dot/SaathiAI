"""M39.8 — Final operator package manifest (offline; machine-readable index).

Additive extension of M39. Assembles a deterministic, leak-clean manifest that
indexes the entire M39.x offline surface for the operator: milestones, docs,
evidence directories, CLI commands, required acknowledgements, the read-only
permission model (minimum + prohibited), authority state, known limitations,
residual risks, and the go-live checklist. Companion to
`docs/M39_8_OPERATOR_PACKAGE.md`.

Contains no secret values. Grants nothing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from saathi.credentials.leakscan import is_clean
from saathi.credentials import m39_7
from saathi.credentials.m39 import (
    ALLOWED_ENDPOINTS,
    ALLOWED_METHODS,
    AUTHORITIES,
    ENV_KILL_SWITCH,
    ENV_LIVE_FLAG,
    NON_PRODUCTION_BANNER,
    PER_SESSION_CALL_BUDGET,
    PROVIDER_ID,
    M39_ACK_TOKENS,
    _hmac,
    compute_m39_fingerprint,
)

SCHEMA_VERSION = "m39_8.operator_package.v1"
_FP_DOMAIN = b"saathi.m39_8.operator_package.domain.v1"

MILESTONES = (
    {"id": "M39", "title": "Live disposable sandbox validation (offline certified, live blocked)",
     "doc": "docs/M39_LIVE_VALIDATION_RUNBOOK.md", "evidence": "docs/evidence/m39/"},
    {"id": "M39.1", "title": "Operator dry-run tooling",
     "doc": "docs/M39_1_OPERATOR_TOOLING.md", "evidence": "docs/evidence/m39_1/"},
    {"id": "M39.2", "title": "Failure-mode simulation",
     "doc": "docs/M39_2_FAILURE_SIMULATION.md", "evidence": "docs/evidence/m39_2/"},
    {"id": "M39.3", "title": "Canary-readiness framework (never grants)",
     "doc": "docs/M39_3_CANARY_FRAMEWORK.md", "evidence": "docs/evidence/m39_3/"},
    {"id": "M39.4", "title": "Deployment & rollback preparation",
     "doc": "docs/M39_4_DEPLOY_ROLLBACK.md", "evidence": "docs/evidence/m39_4/"},
    {"id": "M39.5", "title": "Monitoring & incident response",
     "doc": "docs/M39_5_MONITORING_INCIDENT.md", "evidence": "docs/evidence/m39_5/"},
    {"id": "M39.6", "title": "Adversarial / negative security coverage",
     "doc": "docs/M39_6_ADVERSARIAL_TESTS.md", "evidence": ""},
    {"id": "M39.7", "title": "Reproducibility & clean-environment validation",
     "doc": "docs/M39_7_REPRODUCIBILITY.md", "evidence": "docs/evidence/m39_7/"},
    {"id": "M39.8", "title": "Final operator package",
     "doc": "docs/M39_8_OPERATOR_PACKAGE.md", "evidence": "docs/evidence/m39_8/"},
)

PERMISSION_MODEL = {
    "provider": PROVIDER_ID,
    "minimum_required": {
        "endpoints": sorted({e.lstrip("/") for e in ALLOWED_ENDPOINTS}),
        "methods": sorted(ALLOWED_METHODS),
        "scope": "read-only identity + metadata",
    },
    "prohibited": [
        "repository write",
        "organization admin",
        "billing",
        "package / deploy / workflow secret write",
        "any non-GET method",
        "any endpoint outside /user, /meta",
    ],
    "disposable_token_requirements": [
        "disposable / revocable",
        "sandbox account where possible",
        "minimum read-only permissions",
        "revoked immediately after validation",
    ],
}

KNOWN_LIMITATIONS = (
    "live single-session: NOT_EXERCISED",
    "live multi-session: NOT_EXERCISED",
    "external credential revocation: NOT_EXERCISED",
    "live encrypted-store wiring: NOT_EXERCISED",
    "SIMULATION covers transport faults but not real provider behavior",
)

RESIDUAL_RISKS = (
    "operator supplies a non-disposable or over-scoped token (mitigated by acks + preflight)",
    "operator forgets external revocation (mitigated by M39.1 checklist + M39.5 alert)",
    "encrypted-store backend requires operator wiring before live use",
)

GO_LIVE_CHECKLIST = (
    "M31-M39.7 regression green",
    "offline failure gates pass",
    "leak scans clean",
    "deployment config validates (fail-closed)",
    "operator supplies disposable secret REFERENCE (never a raw secret)",
    f"export {ENV_LIVE_FLAG}=1 for the live window only",
    "all 10 runtime acknowledgements provided",
    "run bounded live single + multi session (github_meta GET /user,/meta)",
    "confirm external credential revocation",
    "evaluate canary ELIGIBILITY (separate explicit operator authorization required)",
    f"trip {ENV_KILL_SWITCH} to stop at any time",
)


def build_operator_package() -> dict[str, Any]:
    repro = m39_7.reproduce_all()
    body = {
        "schema": SCHEMA_VERSION,
        "milestone": "M39.8",
        "title": "SaathiOS M39 Live-Validation Operator Package",
        "banner": NON_PRODUCTION_BANNER,
        "architecture_summary": (
            "M39 composes M31-M38 (SecretHandle, leases, authorization, registry, "
            "sandbox isolation, provider abstraction, M33/M34 transport) to exercise "
            "a bounded read-only external provider under operator control. M39.1-M39.7 "
            "add offline operator tooling, simulation, canary framework, deploy/rollback "
            "prep, monitoring, adversarial coverage, and reproducibility."
        ),
        "trust_boundaries": [
            "secret VALUE never enters CLI, evidence, events, or logs (reference only)",
            "external network only after preflight + flag + acks + secret ref",
            "read-only provider surface; no writes; no financial/trading provider",
            "authority (CANARY/ACTIVE/rollout/production/write) applied out-of-band only",
        ],
        "milestones": [dict(m) for m in MILESTONES],
        "required_acknowledgements": list(M39_ACK_TOKENS),
        "permission_model": PERMISSION_MODEL,
        "environment_flags": {"live_flag": ENV_LIVE_FLAG, "kill_switch": ENV_KILL_SWITCH},
        "session_budget_ceiling": PER_SESSION_CALL_BUDGET,
        "procedures": {
            "reference_setup": "docs/M39_SECRET_REFERENCE_SETUP.md",
            "live_validation": "docs/M39_LIVE_VALIDATION_RUNBOOK.md",
            "interruption_recovery": "docs/M39_INTERRUPTION_AND_RECOVERY.md",
            "revocation": "M39.1 revocation checklist (m39-1-revocation-checklist)",
            "canary_decision": "docs/M39_3_CANARY_FRAMEWORK.md",
            "deployment": "docs/M39_4_DEPLOY_ROLLBACK.md",
            "rollback": "docs/M39_4_DEPLOY_ROLLBACK.md (m39-4-rollback-plan)",
            "incident_response": "docs/M39_5_MONITORING_INCIDENT.md",
        },
        "evidence_interpretation": {
            "live_statuses": "NOT_EXERCISED means the live path was never run (fail-closed)",
            "canary_verdict": "BLOCKED_OPERATOR_SECRET_REQUIRED until live evidence + operator authorization",
            "fingerprints": "deterministic; identical across runs proves reproducibility",
        },
        "known_limitations": list(KNOWN_LIMITATIONS),
        "residual_risks": list(RESIDUAL_RISKS),
        "go_live_checklist": list(GO_LIVE_CHECKLIST),
        "authority_state": {
            "LIVE_PROVIDER_CERTIFICATION": "NOT GRANTED",
            "CANARY": "NOT GRANTED",
            "ACTIVE": "NOT GRANTED",
            "PRODUCTION_DEPLOYMENT": "NOT AUTHORIZED",
            **{k: v for k, v in AUTHORITIES.items()},
        },
        "reproducibility": {
            "all_reproducible": repro["all_reproducible"],
            "all_clean": repro["all_clean"],
        },
        "m39_fingerprint": compute_m39_fingerprint(),
        "trading_guardian": "UNENGAGED",
        "contains_secret_values": False,
    }
    body["fingerprint"] = _hmac(
        _FP_DOMAIN,
        json.dumps({k: body[k] for k in sorted(body)
                    if k not in ("fingerprint", "reproducibility")},
                   sort_keys=True, separators=(",", ":")).encode(),
        length=24,
    )
    return body


def build_m39_8_evidence() -> dict[str, dict[str, Any]]:
    pkg = build_operator_package()
    return {
        "operator_package": pkg,
        "summary": {
            "schema": "m39_8.summary.v1",
            "milestone": "M39.8",
            "verdict": "OPERATOR_PACKAGE_COMPLETE",
            "authority_state": pkg["authority_state"],
            "trading_guardian": "UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m39_8_evidence(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m39_8_evidence()
    written: list[str] = []
    for name, b in bodies.items():
        assert is_clean(b), f"m39_8 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out)}
