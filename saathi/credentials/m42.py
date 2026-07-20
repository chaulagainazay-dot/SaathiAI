"""M42 — Canary Evidence Review & Graduation Decision (composition-only).

M42 is an evidence-review / decision-support layer. It GRANTS NOTHING. It reads the
M40 live-certification evidence and the M41 canary + closure evidence, reuses the
M39.3 graduation criteria and M39.5 alert contracts, checks provenance and
consistency, and emits a deterministic, fail-closed graduation recommendation:
GRADUATION_RECOMMENDED / GRADUATION_NOT_RECOMMENDED / GRADUATION_BLOCKED.

It performs no network call, resolves no credential, mutates no provider, and does
not alter any runtime authority, flag, policy, or execution mode. Operator
attestation is never accepted where machine proof is required.
"""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from saathi.credentials.leakscan import is_clean
from saathi.credentials import m39_3, m39_5
from saathi.credentials.m39 import PROVIDER_ID, ALLOWED_ENDPOINTS, ALLOWED_METHODS, _hmac

SCHEMA_VERSION = "m42.graduation_review.v1"
_FP_DOMAIN = b"saathi.m42.graduation_review.domain.v1"

EVIDENCE_BASE = "docs/evidence"


class Provenance(str, Enum):
    MACHINE_PROOF = "MACHINE_PROOF"
    OPERATOR_ATTESTED = "OPERATOR_ATTESTED"
    SIMULATED = "SIMULATED_NOT_LIVE"
    REFERENCE = "REFERENCE"
    MISSING = "MISSING"


class ArtifactStatus(str, Enum):
    PRESENT_VALID = "PRESENT_VALID"
    PRESENT_INVALID = "PRESENT_INVALID"
    MISSING = "MISSING"
    INCONSISTENT = "INCONSISTENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class GraduationVerdict(str, Enum):
    GRADUATION_RECOMMENDED = "GRADUATION_RECOMMENDED"
    GRADUATION_NOT_RECOMMENDED = "GRADUATION_NOT_RECOMMENDED"
    GRADUATION_BLOCKED = "GRADUATION_BLOCKED"


FORBIDDEN_AUTHORITY = ("ACTIVE", "PRODUCTION", "WRITE", "FULL_ROLLOUT",
                       "SCOPE_EXPANSION", "TRADING_GUARDIAN")

# ── required evidence artifacts (relative to EVIDENCE_BASE) ───────────────────
# provenance = the bar this artifact is expected to meet.
REQUIRED_ARTIFACTS: tuple[dict[str, Any], ...] = (
    {"key": "m40_live_cert", "path": "m40/live_certification_record.json",
     "mandatory": True, "expected_provenance": Provenance.MACHINE_PROOF},
    {"key": "m40_validation", "path": "m40/live_certification_validation_phase.json",
     "mandatory": True, "expected_provenance": Provenance.MACHINE_PROOF},
    {"key": "m40_revocation", "path": "m40/live_certification_revocation_phase.json",
     "mandatory": True, "expected_provenance": Provenance.MACHINE_PROOF},
    {"key": "m41_bounded_canary", "path": "m41/operator_attested_canary_completion.json",
     "mandatory": True, "expected_provenance": Provenance.MACHINE_PROOF},
    {"key": "m41_rehearsal", "path": "m41/canary_rehearsal_bounded.json",
     "mandatory": False, "expected_provenance": Provenance.SIMULATED},
    {"key": "m41_rollback_proof", "path": "m41/canary_rehearsal_auto_rollback.json",
     "mandatory": False, "expected_provenance": Provenance.SIMULATED},
    {"key": "m41_summary", "path": "m41/summary.json",
     "mandatory": False, "expected_provenance": Provenance.SIMULATED},
)


def _classify_provenance(key: str, body: dict[str, Any]) -> str:
    if body.get("source") == "OPERATOR_ATTESTED" or body.get("machine_verified_live") is False:
        return Provenance.OPERATOR_ATTESTED.value
    st = str(body.get("verdict", "")) + str(body.get("status", ""))
    if "SIMULATED_NOT_LIVE" in st or body.get("mode") == "rehearsal":
        return Provenance.SIMULATED.value
    if body.get("live_exercised") is True or body.get("live_certified") is True:
        return Provenance.MACHINE_PROOF.value
    if "m40" in key and body.get("schema", "").startswith("m40"):
        return Provenance.MACHINE_PROOF.value
    return Provenance.REFERENCE.value


# ── 1. evidence inventory ────────────────────────────────────────────────────
def load_evidence(base: str | Path = EVIDENCE_BASE) -> dict[str, Any]:
    """Load required artifacts from disk. Never raises; records load errors."""
    base = Path(base)
    loaded: dict[str, Any] = {}
    for spec in REQUIRED_ARTIFACTS:
        p = base / spec["path"]
        entry: dict[str, Any] = {"path": str(p), "spec": spec["key"]}
        try:
            entry["body"] = json.loads(p.read_text())
            entry["read_error"] = None
        except FileNotFoundError:
            entry["body"] = None
            entry["read_error"] = "missing"
        except Exception as e:  # malformed JSON, etc.
            entry["body"] = None
            entry["read_error"] = f"unreadable:{type(e).__name__}"
        loaded[spec["key"]] = entry
    return loaded


def build_inventory(loaded: dict[str, Any]) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    mandatory_missing: list[str] = []
    any_invalid = False
    for spec in REQUIRED_ARTIFACTS:
        entry = loaded.get(spec["key"], {})
        body = entry.get("body")
        err = entry.get("read_error")
        if err == "missing":
            status, prov = ArtifactStatus.MISSING, Provenance.MISSING.value
        elif err:  # unreadable / malformed
            status, prov = ArtifactStatus.PRESENT_INVALID, Provenance.MISSING.value
        elif not isinstance(body, dict) or not body:
            status, prov = ArtifactStatus.PRESENT_INVALID, Provenance.MISSING.value
        elif not is_clean(body):
            status, prov = ArtifactStatus.PRESENT_INVALID, Provenance.MISSING.value
        else:
            prov = _classify_provenance(spec["key"], body)
            status = ArtifactStatus.PRESENT_VALID
            # provenance gap: machine proof required but only attested/simulated
            if (spec["expected_provenance"] == Provenance.MACHINE_PROOF
                    and prov != Provenance.MACHINE_PROOF.value):
                status = ArtifactStatus.INCONSISTENT
        artifacts.append({
            "key": spec["key"], "path": entry.get("path"),
            "mandatory": spec["mandatory"],
            "expected_provenance": spec["expected_provenance"].value,
            "observed_provenance": prov,
            "status": status.value,
        })
        if spec["mandatory"] and status in (ArtifactStatus.MISSING, ArtifactStatus.PRESENT_INVALID):
            mandatory_missing.append(spec["key"])
        if status == ArtifactStatus.PRESENT_INVALID:
            any_invalid = True
    return {
        "schema": "m42.evidence_inventory.v1",
        "artifacts": artifacts,
        "mandatory_missing": mandatory_missing,
        "any_invalid": any_invalid,
        "blocked": bool(mandatory_missing) or any_invalid,
        "contains_secret_values": False,
    }


# ── 2. evidence-chain consistency ────────────────────────────────────────────
def check_consistency(loaded: dict[str, Any]) -> dict[str, Any]:
    cert = (loaded.get("m40_live_cert") or {}).get("body") or {}
    canary = (loaded.get("m41_bounded_canary") or {}).get("body") or {}
    mismatches: list[str] = []

    def _same(field: str, a: Any, b: Any) -> None:
        if a is not None and b is not None and a != b:
            mismatches.append(field)

    # provider / read-only / identity across cert and canary
    _same("provider", cert.get("provider"), canary.get("provider"))
    if cert.get("provider") not in (None, PROVIDER_ID):
        mismatches.append("provider_not_allowlisted")
    if cert.get("read_only") is False or canary.get("mode") not in (None, "read_only_canary"):
        mismatches.append("read_only_scope_drift")

    # authority: nothing prohibited may be granted anywhere
    for src, body in (("cert", cert), ("canary", canary)):
        if body.get("grants_active") or body.get("grants_production") or body.get("grants_write"):
            mismatches.append(f"{src}_prohibited_grant")
        auth = body.get("authority_state", {})
        for k, v in auth.items():
            ku = str(k).upper()
            if ku in ("ACTIVE", "WRITE") and "NOT" not in str(v).upper():
                mismatches.append(f"{src}_active_or_write_granted")
            if ku in ("PRODUCTION", "PRODUCTION_DEPLOYMENT") and "NOT" not in str(v).upper():
                mismatches.append(f"{src}_production_granted")
        tg = str(body.get("trading_guardian", "")).upper()
        if tg and "UNENGAGED" not in tg:
            mismatches.append(f"{src}_trading_guardian_engaged")

    # M40 must prove real live execution + revocation
    if not (cert.get("live_certified") and cert.get("live_exercised")):
        mismatches.append("m40_not_live_certified")
    rev = cert.get("revocation_phase", {})
    if not rev.get("http_401_confirmed"):
        mismatches.append("m40_revocation_not_proven")

    # M32 prohibition must remain declared unchanged in canary evidence
    if canary.get("m32_canary_execution_mode") not in (None, "PROHIBITION_UNCHANGED"):
        mismatches.append("m32_prohibition_altered")

    return {
        "schema": "m42.consistency.v1",
        "consistent": not mismatches,
        "mismatches": sorted(set(mismatches)),
        "provider": cert.get("provider"),
        "identity_fingerprint_present": bool(cert.get("account_subject_fingerprint")),
        "contains_secret_values": False,
    }


# ── 3. graduation criteria evaluator (reuses M39.3) ──────────────────────────
def _crit(cid, desc, source, observed, expected, ok, severity, rationale, *,
          machine_required=False, provenance=Provenance.MACHINE_PROOF.value):
    status = "PASS" if ok else ("BLOCKED" if observed is None else "FAIL")
    return {"id": cid, "description": desc, "evidence_source": source,
            "observed": observed, "expected": expected, "status": status,
            "severity": severity, "rationale": rationale,
            "machine_proof_required": machine_required, "provenance": provenance}


def evaluate_criteria(loaded: dict[str, Any]) -> dict[str, Any]:
    cert = (loaded.get("m40_live_cert") or {}).get("body") or {}
    canary_entry = loaded.get("m41_bounded_canary") or {}
    canary = canary_entry.get("body") or {}
    canary_prov = _classify_provenance("m41_bounded_canary", canary) if canary else Provenance.MISSING.value
    reev = canary.get("machine_reevaluation", {})
    lifecycle = canary.get("credential_lifecycle", {})

    crits = [
        _crit("GC-1", "M40 real-provider live certification passed",
              "m40_live_cert", cert.get("decision"), "LIVE_CERTIFIED",
              cert.get("decision") == "LIVE_CERTIFIED", "SEV1",
              "M40 executed the real provider in-session", machine_required=True),
        _crit("GC-2", "M40 proved real live execution",
              "m40_live_cert", cert.get("live_exercised"), True,
              cert.get("live_exercised") is True, "SEV1",
              "live_exercised true", machine_required=True),
        _crit("GC-3", "External revocation effective (http 401)",
              "m40_revocation", (cert.get("revocation_phase") or {}).get("http_401_confirmed"),
              True, (cert.get("revocation_phase") or {}).get("http_401_confirmed") is True,
              "SEV1", "post-revocation retry returned 401", machine_required=True),
        _crit("GC-4", "Provider is github_meta, read-only",
              "m40_live_cert", (cert.get("provider"), cert.get("read_only")),
              (PROVIDER_ID, True),
              cert.get("provider") == PROVIDER_ID and cert.get("read_only") is True,
              "SEV1", "allowlisted read-only provider"),
        _crit("GC-5", "No write operations",
              "m40_live_cert", cert.get("writes"), [],
              cert.get("writes") in ([], None), "SEV1", "writes empty"),
        _crit("GC-6", "M41 bounded canary completed",
              "m41_bounded_canary", canary.get("verdict_reported_by_operator"),
              "CANARY_ACTIVE_BOUNDED",
              canary.get("verdict_reported_by_operator") == "CANARY_ACTIVE_BOUNDED",
              "SEV1", "operator-reported bounded completion",
              machine_required=True, provenance=canary_prov),
        _crit("GC-7", "No unresolved M39.5 alerts during canary",
              "m41_bounded_canary", reev.get("m39_5_alerts_fired"), 0,
              reev.get("m39_5_alerts_fired") == 0, "SEV2",
              "machine re-evaluation of reported signals", provenance=canary_prov),
        _crit("GC-8", "No rollback-triggering condition",
              "m41_bounded_canary", reev.get("m41_should_rollback"), False,
              reev.get("m41_should_rollback") is False, "SEV2",
              "rollback evaluator", provenance=canary_prov),
        _crit("GC-9", "Identity + scope stable",
              "m41_bounded_canary",
              (canary.get("operator_reported_signals", {}).get("identity"),
               canary.get("operator_reported_signals", {}).get("scope")),
              ("unchanged", "unchanged"),
              canary.get("operator_reported_signals", {}).get("identity") == "unchanged"
              and canary.get("operator_reported_signals", {}).get("scope") == "unchanged",
              "SEV2", "operator-reported identity/scope", provenance=canary_prov),
        _crit("GC-10", "Credential lifecycle closed",
              "m41_bounded_canary", lifecycle.get("status"), "CLOSED",
              lifecycle.get("status") == "CLOSED", "SEV1",
              "operator-attested closure", provenance=canary_prov),
        _crit("GC-11", "No prohibited authority granted",
              "chain", (cert.get("grants_active"), cert.get("grants_production"),
                        canary.get("grants_active"), canary.get("grants_production"),
                        canary.get("grants_write")),
              (False, False, False, False, False),
              not any([cert.get("grants_active"), cert.get("grants_production"),
                       canary.get("grants_active"), canary.get("grants_production"),
                       canary.get("grants_write")]),
              "SEV1", "all grants_* false"),
        _crit("GC-12", "Trading Guardian unengaged",
              "chain", cert.get("trading_guardian"), "UNCHANGED / UNENGAGED",
              "UNENGAGED" in str(cert.get("trading_guardian", "")).upper()
              and "UNENGAGED" in str(canary.get("trading_guardian", "")).upper(),
              "SEV1", "TG unengaged in cert + canary"),
        _crit("GC-13", "M32 CANARY/ACTIVE prohibition unchanged",
              "runtime", _m32_prohibition_intact(), True, _m32_prohibition_intact(),
              "SEV1", "ExecutionMode.CANARY/ACTIVE still prohibited"),
        _crit("GC-14", "Kill switch + auto-rollback available",
              "m41_bounded_canary",
              (canary.get("operator_reported_signals", {}).get("kill_switch"),
               canary.get("operator_reported_signals", {}).get("automatic_rollback")),
              ("tested", "armed"),
              canary.get("operator_reported_signals", {}).get("kill_switch") == "tested"
              and canary.get("operator_reported_signals", {}).get("automatic_rollback") == "armed",
              "SEV2", "operator-reported", provenance=canary_prov),
    ]
    total = len(crits)
    passed = sum(1 for c in crits if c["status"] == "PASS")
    failed = sum(1 for c in crits if c["status"] == "FAIL")
    blocked = sum(1 for c in crits if c["status"] == "BLOCKED")
    return {
        "schema": "m42.criteria_evaluation.v1",
        "criteria": crits, "total": total, "passed": passed,
        "failed": failed, "blocked": blocked,
        "graduate_requires_all": list(m39_3.CANARY_EXIT_CRITERIA["graduate_requires_all"]),
        "all_pass": failed == 0 and blocked == 0,
        "contains_secret_values": False,
    }


def _m32_prohibition_intact() -> bool:
    try:
        from saathi.connectors.providers.models import M32_PROHIBITED_MODES, ExecutionMode
        return (ExecutionMode.CANARY in M32_PROHIBITED_MODES
                and ExecutionMode.ACTIVE in M32_PROHIBITED_MODES)
    except Exception:
        return False


# ── 4. abort-condition evaluator ─────────────────────────────────────────────
def evaluate_abort(loaded: dict[str, Any], consistency: dict[str, Any],
                   inventory: dict[str, Any]) -> dict[str, Any]:
    cert = (loaded.get("m40_live_cert") or {}).get("body") or {}
    canary = (loaded.get("m41_bounded_canary") or {}).get("body") or {}
    reev = canary.get("machine_reevaluation", {})
    conditions: list[dict[str, Any]] = []

    def _add(cid, desc, present, severity="SEV1"):
        conditions.append({"id": cid, "description": desc,
                           "present": bool(present), "severity": severity})

    # provenance abort: operator attestation where machine proof required
    canary_prov = _classify_provenance("m41_bounded_canary", canary) if canary else Provenance.MISSING.value
    _add("AB-PROV", "M41 bounded-canary completion is operator-attested, not machine-proven",
         canary_prov == Provenance.OPERATOR_ATTESTED.value)
    _add("AB-1", "Unresolved M39.5 alert", reev.get("m39_5_alerts_fired", 0) not in (0, None), "SEV2")
    _add("AB-2", "Rollback-triggering condition present", bool(reev.get("m41_should_rollback")))
    _add("AB-3", "Identity drift",
         canary.get("operator_reported_signals", {}).get("identity") not in ("unchanged", None))
    _add("AB-4", "Scope drift",
         canary.get("operator_reported_signals", {}).get("scope") not in ("unchanged", None))
    _add("AB-5", "Write / production / active authority observed",
         any([cert.get("grants_active"), cert.get("grants_production"), cert.get("grants_write"),
              canary.get("grants_active"), canary.get("grants_production"), canary.get("grants_write")]))
    _add("AB-6", "Revocation proof missing",
         not (cert.get("revocation_phase") or {}).get("http_401_confirmed"))
    _add("AB-7", "Credential lifecycle not closed",
         (canary.get("credential_lifecycle") or {}).get("status") != "CLOSED")
    _add("AB-8", "Evidence inconsistent", not consistency["consistent"])
    _add("AB-9", "Mandatory evidence missing or invalid", inventory["blocked"])
    _add("AB-10", "Simulated result substituted for live proof (M40)",
         "SIMULATED" in str(cert.get("verdict", "")) or cert.get("live_exercised") is not True)
    _add("AB-11", "Trading Guardian engaged",
         "UNENGAGED" not in str(cert.get("trading_guardian", "UNENGAGED")).upper())

    present = [c["id"] for c in conditions if c["present"]]
    return {
        "schema": "m42.abort_evaluation.v1",
        "conditions": conditions,
        "present": present,
        "any_present": bool(present),
        "contains_secret_values": False,
    }


# ── 5. recommendation ────────────────────────────────────────────────────────
def _evidence_digest(loaded: dict[str, Any]) -> str:
    parts = []
    for spec in REQUIRED_ARTIFACTS:
        b = (loaded.get(spec["key"]) or {}).get("body")
        fp = (b or {}).get("fingerprint") if isinstance(b, dict) else None
        parts.append(f"{spec['key']}={fp or 'none'}")
    return _hmac(_FP_DOMAIN, "|".join(parts).encode(), length=32)


def build_recommendation(loaded: dict[str, Any]) -> dict[str, Any]:
    inventory = build_inventory(loaded)
    consistency = check_consistency(loaded)
    criteria = evaluate_criteria(loaded)
    abort = evaluate_abort(loaded, consistency, inventory)

    # verdict logic — fail closed
    if inventory["blocked"] or not _structurally_reviewable(loaded):
        verdict = GraduationVerdict.GRADUATION_BLOCKED.value
    elif abort["any_present"] or not criteria["all_pass"] or not consistency["consistent"]:
        verdict = GraduationVerdict.GRADUATION_NOT_RECOMMENDED.value
    else:
        verdict = GraduationVerdict.GRADUATION_RECOMMENDED.value

    cert = (loaded.get("m40_live_cert") or {}).get("body") or {}
    digest = _evidence_digest(loaded)
    body = {
        "schema": SCHEMA_VERSION,
        "milestone": "M42",
        "review_id": _hmac(_FP_DOMAIN, ("review:" + digest).encode(), length=16),
        "provider": cert.get("provider") or PROVIDER_ID,
        "capability": "read-only metadata validation",
        "reviewed_baseline": {"m40": "LIVE_CERTIFIED", "m41": "bounded_canary_attested"},
        "evidence_digest": digest,
        "criteria_total": criteria["total"],
        "criteria_passed": criteria["passed"],
        "criteria_failed": criteria["failed"],
        "criteria_blocked": criteria["blocked"],
        "abort_conditions_present": abort["present"],
        "recommendation": verdict,
        "recommended_maximum_future_authority": (
            "Operator may SEPARATELY consider a future read-only limited rollout for "
            "github_meta, only after machine-verified bounded-canary evidence exists."
        ),
        "explicitly_not_granted": list(FORBIDDEN_AUTHORITY),
        "residual_risks": _residual_risks(abort, criteria, loaded),
        "required_operator_actions": _required_actions(verdict, abort, loaded),
        "review_timestamp": "deterministic:evidence-digest-derived",
        "grants_anything": False,
        "alters_runtime_authority": False,
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "inventory": inventory,
        "consistency": consistency,
        "criteria": criteria,
        "abort": abort,
        "contains_secret_values": False,
    }
    body["fingerprint"] = _hmac(
        _FP_DOMAIN,
        json.dumps({"v": verdict, "digest": digest,
                    "passed": criteria["passed"], "failed": criteria["failed"],
                    "abort": abort["present"]}, sort_keys=True).encode(),
        length=24)
    return body


def _structurally_reviewable(loaded: dict[str, Any]) -> bool:
    for spec in REQUIRED_ARTIFACTS:
        if not spec["mandatory"]:
            continue
        entry = loaded.get(spec["key"], {})
        body = entry.get("body")
        if entry.get("read_error") or not isinstance(body, dict) or not body:
            return False
        if not is_clean(body):
            return False
    return True


def _residual_risks(abort, criteria, loaded) -> list[str]:
    risks = []
    canary = (loaded.get("m41_bounded_canary") or {}).get("body") or {}
    if _classify_provenance("m41_bounded_canary", canary) == Provenance.OPERATOR_ATTESTED.value:
        risks.append("M41 bounded-canary completion is operator-attested, not machine-verified in-repo")
    if (canary.get("credential_lifecycle") or {}).get("machine_verified_here") is False:
        risks.append("external credential revocation is operator-attested (ran in operator environment)")
    risks.append("recommendation is advisory only; no runtime authority is changed")
    return risks


def _required_actions(verdict, abort, loaded) -> list[str]:
    actions = []
    if verdict == GraduationVerdict.GRADUATION_BLOCKED.value:
        actions.append("supply the missing/valid mandatory evidence artifacts, then re-review")
    if "AB-PROV" in abort["present"]:
        actions.append("produce MACHINE-verified M41 bounded-canary evidence (re-run the bounded "
                       "canary in-session capturing machine evidence, as M40 did) to lift the "
                       "operator-attestation provenance gap")
    actions.append("any future rollout requires a SEPARATE explicit operator authorization; "
                   "M42 grants nothing")
    return actions


# ── top-level review ─────────────────────────────────────────────────────────
def run_graduation_review(base: str | Path = EVIDENCE_BASE,
                          loaded: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    ev = loaded if loaded is not None else load_evidence(base)
    return build_recommendation(ev)


def build_m42_evidence(base: str | Path = EVIDENCE_BASE) -> dict[str, dict[str, Any]]:
    loaded = load_evidence(base)
    rec = build_recommendation(loaded)
    return {
        "evidence_inventory": rec["inventory"],
        "criteria_evaluation": rec["criteria"],
        "abort_condition_evaluation": rec["abort"],
        "graduation_recommendation": {k: v for k, v in rec.items()
                                      if k not in ("inventory", "criteria", "abort")},
        "summary": {
            "schema": "m42.summary.v1",
            "milestone": "M42",
            "recommendation": rec["recommendation"],
            "grants_anything": False,
            "explicitly_not_granted": list(FORBIDDEN_AUTHORITY),
            "trading_guardian": "UNCHANGED / UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m42_evidence(out_dir: str | Path, *, base: str | Path = EVIDENCE_BASE) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m42_evidence(base)
    written: list[str] = []
    for name, b in bodies.items():
        assert is_clean(b), f"m42 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out)}
