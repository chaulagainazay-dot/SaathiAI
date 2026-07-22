"""M39.3 — Canary-readiness framework (offline; CANARY never granted).

Additive extension of M39. Completes the *operational* canary framework around the
existing read-only eligibility evaluator (`m39.evaluate_canary_eligibility`):
immutable prerequisite set, operator-approval-record format + validator, rollback
triggers, circuit breakers, rollout bounds, and canary exit criteria.

Hard invariant: this module NEVER grants CANARY / ACTIVE / rollout / production /
write. `evaluate_canary_decision` always returns ``grants_canary = False``. Only a
future, explicit, out-of-band operator authorization may flip authority — and only
after live M39 evidence exists. In this offline series live evidence is
NOT_EXERCISED, so the decision is always CANARY_NOT_GRANTED.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from saathi.credentials.leakscan import is_clean
from saathi.credentials.m39 import (
    ALLOWED_ENDPOINTS,
    ALLOWED_METHODS,
    AUTHORITIES,
    NON_PRODUCTION_BANNER,
    PER_SESSION_CALL_BUDGET,
    PROVIDER_ID,
    M39Error,
    _hmac,
    evaluate_canary_eligibility,
)

SCHEMA_VERSION = "m39_3.canary_framework.v1"
_FP_DOMAIN = b"saathi.m39_3.canary_framework.domain.v1"

# ── immutable prerequisites (ordered; deny-by-default) ───────────────────────
# Each prerequisite MUST hold before a canary decision may even be considered.
CANARY_PREREQUISITES: tuple[dict[str, str], ...] = (
    {"id": "PRQ-1", "requirement": "M31–M39 regression green"},
    {"id": "PRQ-2", "requirement": "M39 offline failure gates pass"},
    {"id": "PRQ-3", "requirement": "live single-session PASSED (operator-exercised)"},
    {"id": "PRQ-4", "requirement": "live multi-session PASSED (operator-exercised)"},
    {"id": "PRQ-5", "requirement": "identity qualification confirmed"},
    {"id": "PRQ-6", "requirement": "scope qualification confirmed (read-only)"},
    {"id": "PRQ-7", "requirement": "call budget compliance"},
    {"id": "PRQ-8", "requirement": "SecretHandle + lease cleanup complete"},
    {"id": "PRQ-9", "requirement": "external credential revocation confirmed"},
    {"id": "PRQ-10", "requirement": "repository + runtime leak scans clean"},
    {"id": "PRQ-11", "requirement": "no unresolved terminal failures"},
    {"id": "PRQ-12", "requirement": "evidence complete and reproducible"},
    {"id": "PRQ-13", "requirement": "valid explicit operator canary approval record"},
)
_PRQ_IDS = tuple(p["id"] for p in CANARY_PREREQUISITES)

# ── rollout bounds (bounded canary only) ─────────────────────────────────────
ROLLOUT_MIN_PERCENT = 1
ROLLOUT_MAX_PERCENT = 5  # hard canary ceiling; ACTIVE/full rollout is a separate authority

# ── allowlists (inherited from M39; canary may not widen them) ───────────────
CANARY_ALLOWLISTED_PROVIDER = PROVIDER_ID
CANARY_ALLOWLISTED_ENDPOINTS = tuple(sorted({e.lstrip("/") for e in ALLOWED_ENDPOINTS}))
CANARY_ALLOWLISTED_METHODS = tuple(sorted(ALLOWED_METHODS))

# ── rollback triggers (deterministic; auto-abort conditions) ─────────────────
ROLLBACK_TRIGGERS: tuple[dict[str, Any], ...] = (
    {"id": "RBK-1", "condition": "error_rate_exceeds_budget",
     "threshold": "error_budget_consumed >= 100%", "action": "halt_canary_and_rollback"},
    {"id": "RBK-2", "condition": "auth_denial_spike",
     "threshold": "auth_denials >= 1 (401/403)", "action": "halt_canary_and_rollback"},
    {"id": "RBK-3", "condition": "budget_exhaustion",
     "threshold": "aggregate_calls >= aggregate_budget", "action": "halt_and_reconcile"},
    {"id": "RBK-4", "condition": "kill_switch_tripped",
     "threshold": "SAATHI_M39_KILL_SWITCH active", "action": "immediate_halt"},
    {"id": "RBK-5", "condition": "leak_detected",
     "threshold": "any leak-scan finding", "action": "immediate_halt_and_quarantine"},
    {"id": "RBK-6", "condition": "circuit_breaker_open",
     "threshold": "consecutive_failures >= CBK threshold", "action": "halt_canary"},
    {"id": "RBK-7", "condition": "write_attempt_detected",
     "threshold": "any non-GET / non-allowlisted operation", "action": "immediate_halt_and_alert"},
)

# ── circuit breakers ─────────────────────────────────────────────────────────
CIRCUIT_BREAKERS: tuple[dict[str, Any], ...] = (
    {"id": "CBK-1", "name": "consecutive_failure_breaker",
     "open_condition": "consecutive_failures >= 3", "cooldown": "manual_reset_only"},
    {"id": "CBK-2", "name": "rate_limit_breaker",
     "open_condition": "http_429 observed", "cooldown": "backoff_then_manual_review"},
    {"id": "CBK-3", "name": "secret_resolution_breaker",
     "open_condition": "secret_resolution_failure", "cooldown": "manual_reset_only"},
)

# ── canary exit criteria ─────────────────────────────────────────────────────
CANARY_EXIT_CRITERIA: dict[str, tuple[str, ...]] = {
    "graduate_requires_all": (
        "zero rollback triggers fired",
        "error_budget_consumed < 25%",
        "all sessions within call budget",
        "identity + scope stable across window",
        "explicit operator graduation decision",
    ),
    "abort_if_any": (
        "any rollback trigger fired",
        "any circuit breaker open",
        "any leak finding",
        "operator abort",
    ),
}

# operator canary approval record — required fields (deny-by-default) ──────────
_REQUIRED_APPROVAL_FIELDS = (
    "approval_id",
    "approver_id",
    "milestone",
    "provider",
    "endpoints",
    "methods",
    "rollout_percent",
    "expires_at",
    "explicit_acknowledgements",
    "record_hash",
)
_REQUIRED_APPROVAL_ACKS = (
    "I_AUTHORIZE_BOUNDED_CANARY",
    "I_CONFIRM_LIVE_M39_EVIDENCE_REVIEWED",
    "I_CONFIRM_ROLLBACK_TRIGGERS_ACCEPTED",
    "I_CONFIRM_READ_ONLY_SCOPE",
    "I_ACCEPT_ACCOUNTABILITY_FOR_THIS_AUTHORIZATION",
)


def approval_record_schema() -> dict[str, Any]:
    """Return the required-field schema for an operator canary approval record."""
    return {
        "schema": "m39_3.operator_canary_approval.v1",
        "required_fields": list(_REQUIRED_APPROVAL_FIELDS),
        "required_acknowledgements": list(_REQUIRED_APPROVAL_ACKS),
        "rollout_bounds": {"min_percent": ROLLOUT_MIN_PERCENT, "max_percent": ROLLOUT_MAX_PERCENT},
        "allowlist": {
            "provider": CANARY_ALLOWLISTED_PROVIDER,
            "endpoints": list(CANARY_ALLOWLISTED_ENDPOINTS),
            "methods": list(CANARY_ALLOWLISTED_METHODS),
        },
        "note": "A valid record is a necessary operator input; it does NOT itself "
                "grant CANARY. Authority is applied out-of-band by the operator.",
        "contains_secret_values": False,
    }


def validate_operator_approval_record(record: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Structurally validate an operator approval record. Deny-by-default. No grant."""
    problems: list[str] = []
    if not isinstance(record, dict) or not record:
        return {
            "schema": "m39_3.approval_validation.v1",
            "valid": False,
            "present": False,
            "problems": ["no_operator_approval_record"],
            "grants_canary": False,
            "contains_secret_values": False,
        }

    for f in _REQUIRED_APPROVAL_FIELDS:
        if f not in record or record.get(f) in (None, "", [], {}):
            problems.append(f"missing_field:{f}")

    prov = record.get("provider")
    if prov is not None and prov != CANARY_ALLOWLISTED_PROVIDER:
        problems.append("provider_not_allowlisted")

    eps = record.get("endpoints") or []
    if isinstance(eps, list):
        for e in eps:
            if str(e).lstrip("/") not in CANARY_ALLOWLISTED_ENDPOINTS:
                problems.append("endpoint_not_allowlisted")
                break
    methods = record.get("methods") or []
    if isinstance(methods, list):
        for mth in methods:
            if str(mth).upper() not in CANARY_ALLOWLISTED_METHODS:
                problems.append("method_not_allowlisted")
                break

    rp = record.get("rollout_percent")
    if isinstance(rp, (int, float)):
        if not (ROLLOUT_MIN_PERCENT <= rp <= ROLLOUT_MAX_PERCENT):
            problems.append("rollout_percent_out_of_bounds")
    elif "rollout_percent" not in [p.split(":")[-1] for p in problems]:
        if rp is not None:
            problems.append("rollout_percent_invalid_type")

    acks = record.get("explicit_acknowledgements") or []
    ackset = set(acks) if isinstance(acks, list) else set()
    for a in _REQUIRED_APPROVAL_ACKS:
        if a not in ackset:
            problems.append(f"missing_acknowledgement:{a}")

    valid = not problems
    return {
        "schema": "m39_3.approval_validation.v1",
        "valid": valid,
        "present": True,
        "problems": problems,
        "grants_canary": False,  # a valid record is input, never a grant
        "note": "structural validity only; authority is applied out-of-band by operator",
        "contains_secret_values": False,
    }


def evaluate_prerequisites(state: Optional[dict[str, bool]] = None) -> dict[str, Any]:
    """Report which immutable prerequisites hold. Deny-by-default (unknown = unmet)."""
    st = state or {}
    checks = []
    unmet: list[str] = []
    for prq in CANARY_PREREQUISITES:
        held = bool(st.get(prq["id"], False))
        checks.append({"id": prq["id"], "requirement": prq["requirement"], "held": held})
        if not held:
            unmet.append(prq["id"])
    return {
        "schema": "m39_3.prerequisites.v1",
        "total": len(CANARY_PREREQUISITES),
        "held": len(CANARY_PREREQUISITES) - len(unmet),
        "unmet": unmet,
        "all_met": not unmet,
        "checks": checks,
        "immutable": True,
        "contains_secret_values": False,
    }


def framework_definitions() -> dict[str, Any]:
    """Return the immutable canary framework definitions (triggers/breakers/exit)."""
    return {
        "schema": "m39_3.framework_definitions.v1",
        "rollout_bounds": {"min_percent": ROLLOUT_MIN_PERCENT, "max_percent": ROLLOUT_MAX_PERCENT},
        "allowlist": {
            "provider": CANARY_ALLOWLISTED_PROVIDER,
            "endpoints": list(CANARY_ALLOWLISTED_ENDPOINTS),
            "methods": list(CANARY_ALLOWLISTED_METHODS),
        },
        "rollback_triggers": [dict(t) for t in ROLLBACK_TRIGGERS],
        "circuit_breakers": [dict(c) for c in CIRCUIT_BREAKERS],
        "exit_criteria": {k: list(v) for k, v in CANARY_EXIT_CRITERIA.items()},
        "session_budget_ceiling": PER_SESSION_CALL_BUDGET,
        "contains_secret_values": False,
    }


def evaluate_canary_decision(
    *,
    prerequisite_state: Optional[dict[str, bool]] = None,
    operator_approval_record: Optional[dict[str, Any]] = None,
    eligibility_kwargs: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compose eligibility + prerequisites + approval record. NEVER grants CANARY."""
    elig = evaluate_canary_eligibility(**(eligibility_kwargs or {}))
    prereq = evaluate_prerequisites(prerequisite_state)
    approval = validate_operator_approval_record(operator_approval_record)

    blockers: list[str] = []
    if elig.get("verdict") != "READY_FOR_OPERATOR_CANARY_DECISION":
        blockers.append("eligibility_not_ready")
    if not prereq["all_met"]:
        blockers.append("prerequisites_unmet")
    if not approval["valid"]:
        blockers.append("operator_approval_record_invalid_or_absent")

    # By construction this offline series has live evidence NOT_EXERCISED, so
    # eligibility can never be READY here. The decision is always NOT_GRANTED.
    decision = "CANARY_NOT_GRANTED"
    body = {
        "schema": SCHEMA_VERSION,
        "milestone": "M39.3",
        "decision": decision,
        "grants_canary": False,
        "grants_active": False,
        "grants_rollout": False,
        "grants_production": False,
        "grants_write": False,
        "blockers": blockers,
        "eligibility_verdict": elig.get("verdict"),
        "prerequisites": {"all_met": prereq["all_met"], "unmet": prereq["unmet"]},
        "operator_approval": {"present": approval["present"], "valid": approval["valid"]},
        "framework": framework_definitions(),
        "authorities": dict(AUTHORITIES),
        "banner": NON_PRODUCTION_BANNER,
        "trading_guardian": "UNENGAGED",
        "note": "Readiness is not authorization. Authority is applied out-of-band by "
                "the operator only after live M39 evidence exists. M39.3 never grants.",
        "contains_secret_values": False,
    }
    body["fingerprint"] = _hmac(
        _FP_DOMAIN,
        json.dumps({k: body[k] for k in sorted(body) if k != "fingerprint"},
                   sort_keys=True, separators=(",", ":")).encode(),
        length=24,
    )
    return body


def build_m39_3_evidence() -> dict[str, dict[str, Any]]:
    decision = evaluate_canary_decision()  # default: nothing met → NOT_GRANTED
    return {
        "prerequisites": evaluate_prerequisites(),
        "framework_definitions": framework_definitions(),
        "approval_record_schema": approval_record_schema(),
        "approval_validation_empty": validate_operator_approval_record(None),
        "canary_decision": decision,
        "summary": {
            "schema": "m39_3.summary.v1",
            "milestone": "M39.3",
            "verdict": "CANARY_FRAMEWORK_COMPLETE_CANARY_NOT_GRANTED",
            "decision": decision["decision"],
            "grants_canary": False,
            "authorities": dict(AUTHORITIES),
            "trading_guardian": "UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m39_3_evidence(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m39_3_evidence()
    written: list[str] = []
    for name, body in bodies.items():
        assert is_clean(body), f"m39_3 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out)}
