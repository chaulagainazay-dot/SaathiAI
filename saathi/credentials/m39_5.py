"""M39.5 — Monitoring & incident response (offline; local/synthetic signals only).

Additive extension of M39. Defines the observability + incident surface for the
M39 external-provider validation surface: structured audit-event contracts and a
fail-closed validator, alert definitions and a deterministic detector over local
synthetic signals, a metrics contract, incident severity definitions, and incident
+ recovery runbooks.

No live transport is used. No secret value is ever accepted in an event; the
validator rejects any event that claims to carry one. Authorities unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from saathi.credentials.leakscan import is_clean, scan
from saathi.credentials.m39 import (
    AUTHORITIES,
    NON_PRODUCTION_BANNER,
    M39Error,
    _hmac,
)

SCHEMA_VERSION = "m39_5.monitoring_incident.v1"
_FP_DOMAIN = b"saathi.m39_5.monitoring_incident.domain.v1"

# ── audit-event contracts ────────────────────────────────────────────────────
# Every M39-surface event must be privacy-safe and carry no secret value.
_COMMON_REQUIRED = ("event_type", "session_id", "privacy_safe", "contains_secret_values")
AUDIT_EVENT_CONTRACTS: dict[str, dict[str, Any]] = {
    "m39.single_session_complete": {"required": _COMMON_REQUIRED + ("ok", "reason")},
    "m39.single_session_blocked": {"required": _COMMON_REQUIRED + ("reason",)},
    "m39.single_session_failed": {"required": _COMMON_REQUIRED + ("reason",)},
    "m39.multi_session_complete": {"required": _COMMON_REQUIRED + ("ok",)},
    "m39.budget_exhausted": {"required": _COMMON_REQUIRED + ("reason",)},
    "m39.kill_switch_tripped": {"required": _COMMON_REQUIRED + ("reason",)},
    "m39.external_revocation_recorded": {"required": _COMMON_REQUIRED + ("status",)},
    "m39.leak_detected": {"required": _COMMON_REQUIRED + ("reason",)},
}
# fields that must never appear in an audit event (would carry a secret)
_FORBIDDEN_EVENT_FIELDS = ("secret", "token", "api_key", "authorization", "password", "value")


def audit_event_contracts() -> dict[str, Any]:
    return {
        "schema": "m39_5.audit_contracts.v1",
        "event_types": sorted(AUDIT_EVENT_CONTRACTS),
        "common_required": list(_COMMON_REQUIRED),
        "forbidden_fields": list(_FORBIDDEN_EVENT_FIELDS),
        "contains_secret_values": False,
    }


def validate_audit_event(event: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Validate one audit event against its contract. Fail closed. No secret allowed."""
    problems: list[str] = []
    if not isinstance(event, dict) or not event:
        return {"schema": "m39_5.event_validation.v1", "valid": False,
                "problems": ["empty_event"], "contains_secret_values": False}

    etype = event.get("event_type")
    contract = AUDIT_EVENT_CONTRACTS.get(etype)
    if contract is None:
        problems.append("unknown_event_type")
    else:
        for f in contract["required"]:
            if f not in event:
                problems.append(f"missing_field:{f}")

    if event.get("privacy_safe") is not True:
        problems.append("not_privacy_safe")
    if event.get("contains_secret_values") is not False:
        problems.append("claims_secret_values")
    for f in _FORBIDDEN_EVENT_FIELDS:
        if f in event:
            problems.append(f"forbidden_field:{f}")
    # deep leak scan of the event content
    if not is_clean(event):
        problems.append("leak_detected")

    return {
        "schema": "m39_5.event_validation.v1",
        "valid": not problems,
        "event_type": etype,
        "problems": problems,
        "contains_secret_values": False,
    }


# ── alert definitions ────────────────────────────────────────────────────────
ALERT_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"id": "ALT-1", "name": "stuck_run", "severity": "SEV2",
     "signal": "session_age_seconds", "condition": ">= stuck_threshold_seconds"},
    {"id": "ALT-2", "name": "budget_exhaustion", "severity": "SEV3",
     "signal": "aggregate_calls_used", "condition": ">= aggregate_budget"},
    {"id": "ALT-3", "name": "authorization_denial", "severity": "SEV2",
     "signal": "auth_denials", "condition": ">= 1"},
    {"id": "ALT-4", "name": "secret_resolution_failure", "severity": "SEV1",
     "signal": "secret_resolution_failures", "condition": ">= 1"},
    {"id": "ALT-5", "name": "lease_leak", "severity": "SEV1",
     "signal": "open_leases_after_cleanup", "condition": ">= 1"},
    {"id": "ALT-6", "name": "leak_finding", "severity": "SEV1",
     "signal": "leak_findings", "condition": ">= 1"},
    {"id": "ALT-7", "name": "kill_switch_tripped", "severity": "SEV2",
     "signal": "kill_switch_active", "condition": "== true"},
    {"id": "ALT-8", "name": "provider_failure_rate", "severity": "SEV2",
     "signal": "provider_failure_rate", "condition": ">= 0.5"},
    {"id": "ALT-9", "name": "canary_escalation_attempt", "severity": "SEV1",
     "signal": "canary_grant_attempts", "condition": ">= 1"},
)

# default thresholds (bounded; operator may tighten, never loosen past ceilings)
DEFAULT_THRESHOLDS = {
    "stuck_threshold_seconds": 300,
    "aggregate_budget": 12,
}


def alert_definitions() -> dict[str, Any]:
    return {
        "schema": "m39_5.alert_definitions.v1",
        "alerts": [dict(a) for a in ALERT_DEFINITIONS],
        "default_thresholds": dict(DEFAULT_THRESHOLDS),
        "contains_secret_values": False,
    }


def detect_alerts(
    signals: Optional[dict[str, Any]] = None,
    *,
    thresholds: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Deterministically evaluate alert conditions over local synthetic signals."""
    s = signals or {}
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    fired: list[dict[str, Any]] = []

    def _num(key: str) -> float:
        v = s.get(key, 0)
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    checks = {
        "ALT-1": _num("session_age_seconds") >= th["stuck_threshold_seconds"],
        "ALT-2": _num("aggregate_calls_used") >= th["aggregate_budget"],
        "ALT-3": _num("auth_denials") >= 1,
        "ALT-4": _num("secret_resolution_failures") >= 1,
        "ALT-5": _num("open_leases_after_cleanup") >= 1,
        "ALT-6": _num("leak_findings") >= 1,
        "ALT-7": bool(s.get("kill_switch_active", False)),
        "ALT-8": _num("provider_failure_rate") >= 0.5,
        "ALT-9": _num("canary_grant_attempts") >= 1,
    }
    for a in ALERT_DEFINITIONS:
        if checks.get(a["id"]):
            fired.append({"id": a["id"], "name": a["name"], "severity": a["severity"]})

    max_sev = min((int(f["severity"][3:]) for f in fired), default=0)  # SEV1 highest
    return {
        "schema": "m39_5.alert_evaluation.v1",
        "fired": fired,
        "fired_count": len(fired),
        "highest_severity": f"SEV{max_sev}" if max_sev else "NONE",
        "thresholds": th,
        "contains_secret_values": False,
    }


# ── metrics contract ─────────────────────────────────────────────────────────
def metrics_contract() -> dict[str, Any]:
    return {
        "schema": "m39_5.metrics_contract.v1",
        "metrics": [
            {"name": "m39_sessions_total", "type": "counter"},
            {"name": "m39_sessions_failed_total", "type": "counter"},
            {"name": "m39_calls_used", "type": "gauge"},
            {"name": "m39_auth_denials_total", "type": "counter"},
            {"name": "m39_secret_resolution_failures_total", "type": "counter"},
            {"name": "m39_open_leases", "type": "gauge"},
            {"name": "m39_leak_findings_total", "type": "counter"},
            {"name": "m39_kill_switch_active", "type": "gauge"},
        ],
        "redaction": "no labels may carry secret values; provider/reason only",
        "contains_secret_values": False,
    }


# ── incident severity + runbooks ─────────────────────────────────────────────
def incident_severity_definitions() -> dict[str, Any]:
    return {
        "schema": "m39_5.incident_severity.v1",
        "levels": [
            {"level": "SEV1", "meaning": "secret exposure risk, lease leak, or canary escalation attempt",
             "response": "immediate halt + kill switch + operator page"},
            {"level": "SEV2", "meaning": "stuck run, auth denial, kill-switch trip, provider failure",
             "response": "halt affected sessions + investigate"},
            {"level": "SEV3", "meaning": "budget exhaustion / degraded but contained",
             "response": "reconcile + throttle"},
        ],
        "contains_secret_values": False,
    }


def incident_runbook() -> dict[str, Any]:
    return {
        "schema": "m39_5.incident_runbook.v1",
        "steps": [
            {"id": "INC-1", "action": "Trip kill switch (SAATHI_M39_KILL_SWITCH=1)"},
            {"id": "INC-2", "action": "Classify severity via incident_severity_definitions"},
            {"id": "INC-3", "action": "For SEV1 secret risk: run leak scans; quarantine evidence"},
            {"id": "INC-4", "action": "Halt affected sessions; confirm SecretHandle/lease closure"},
            {"id": "INC-5", "action": "Operator revokes disposable credential externally"},
            {"id": "INC-6", "action": "Record incident; attach redacted audit events only"},
        ],
        "escalation": "page operator for any SEV1; Trading Guardian remains unengaged",
        "contains_secret_values": False,
    }


def recovery_runbook() -> dict[str, Any]:
    return {
        "schema": "m39_5.recovery_runbook.v1",
        "steps": [
            {"id": "REC-1", "action": "Confirm kill switch state and no open leases"},
            {"id": "REC-2", "action": "Reconcile sessions from evidence (never reopen secrets)"},
            {"id": "REC-3", "action": "Re-run M31–M39.x regression + offline gates"},
            {"id": "REC-4", "action": "Re-run leak scans; confirm clean"},
            {"id": "REC-5", "action": "Reset breakers only after root-cause documented"},
            {"id": "REC-6", "action": "Resume only with explicit operator authorization"},
        ],
        "evidence_retention": "retain redacted incident evidence; never store secret values",
        "contains_secret_values": False,
    }


def build_m39_5_evidence() -> dict[str, dict[str, Any]]:
    # a clean sample event and a deliberately bad one (to prove the validator)
    good = validate_audit_event({
        "event_type": "m39.single_session_blocked", "session_id": "sess",
        "privacy_safe": True, "contains_secret_values": False, "reason": "live_feature_flag_missing",
    })
    bad = validate_audit_event({
        "event_type": "m39.single_session_blocked", "session_id": "sess",
        "privacy_safe": True, "contains_secret_values": False, "reason": "x",
        "token": "REDACTED_SHOULD_NOT_BE_HERE",
    })
    no_alerts = detect_alerts({})
    some_alerts = detect_alerts({
        "secret_resolution_failures": 1, "auth_denials": 2, "aggregate_calls_used": 12,
    })
    return {
        "audit_contracts": audit_event_contracts(),
        "event_validation_good": good,
        "event_validation_forbidden_field": bad,
        "alert_definitions": alert_definitions(),
        "alert_eval_quiet": no_alerts,
        "alert_eval_active": some_alerts,
        "metrics_contract": metrics_contract(),
        "incident_severity": incident_severity_definitions(),
        "incident_runbook": incident_runbook(),
        "recovery_runbook": recovery_runbook(),
        "summary": {
            "schema": "m39_5.summary.v1",
            "milestone": "M39.5",
            "verdict": "MONITORING_INCIDENT_SURFACE_COMPLETE_OFFLINE",
            "authorities": dict(AUTHORITIES),
            "banner": NON_PRODUCTION_BANNER,
            "trading_guardian": "UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m39_5_evidence(out_dir: str | Path) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m39_5_evidence()
    written: list[str] = []
    for name, b in bodies.items():
        assert is_clean(b), f"m39_5 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out)}
