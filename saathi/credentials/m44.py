"""M44 — Limited Rollout Authorization Framework (composition-only; fail-closed).

M44 builds the complete infrastructure required to *authorize* future limited
rollouts. It does NOT activate production, deploy, enable writes, expand scope, or
grant any authority. Its maximal output is advisory:

    ROLLOUT_AUTHORIZATION_FRAMEWORK_READY

—never PRODUCTION_READY. (Legacy alias: ROLL_OUT_AUTHORIZATION_FRAMEWORK_READY.)
Even a fully valid rollout authorization request yields
only ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY: a machine-checked statement that
*if* an operator later chooses to execute, the request is well-formed, bounded, and
evidence-backed. Execution still requires a completely separate operator
authorization outside M44.

It composes existing systems only:
  * M39 authorities / kill switch / fingerprint domain / provider identity;
  * M39.3 operator approval records (referenced by fingerprint, never inlined);
  * M43 machine-verified canary proof (referenced by fingerprint);
  * M42 graduation review (referenced by fingerprint).
No parallel credential system, no new secret storage, no new provider permissions.

Hard invariants (never weakened from M31–M43):
  * deny-by-default: an empty / partial request is DENIED;
  * deterministic: same inputs -> same verdict + fingerprint;
  * bounded: rollout percent constrained by a discrete per-policy ceiling;
  * reversible: every authorization names a rollback owner + rollback contract;
  * least privilege: read-only single provider `github_meta` only;
  * auditable: immutable, hash-chained ledger + read-only audit API;
  * no secrets: requests, ledger, and evidence are leak-scanned;
  * M32 provider-runtime prohibition UNCHANGED; Trading Guardian UNENGAGED.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from saathi.credentials.leakscan import is_clean
from saathi.credentials.m39 import (
    AUTHORITIES,
    PROVIDER_ID,
    _hmac,
    kill_switch_active,
)

SCHEMA_VERSION = "m44.rollout_authorization.v1"
_FP_DOMAIN = b"saathi.m44.rollout_authorization.domain.v1"
_SIG_DOMAIN = b"saathi.m44.operator_signature.domain.v1"
_LEDGER_DOMAIN = b"saathi.m44.rollout_ledger.domain.v1"

# Canonical framework-state name. `ROLL_OUT_...` is a documented legacy alias kept
# for any consumer of the earlier (uncommitted) M44 spelling; the canonical name is
# the single-word ROLLOUT form.
FRAMEWORK_STATE = "ROLLOUT_AUTHORIZATION_FRAMEWORK_READY"
FRAMEWORK_STATE_LEGACY_ALIAS = "ROLL_OUT_AUTHORIZATION_FRAMEWORK_READY"

LEDGER_PATH = "docs/evidence/m44/rollout_ledger.jsonl"
EVIDENCE_DIR = "docs/evidence/m44"

# Reference locations for the evidence chain (read-only; referenced by fingerprint).
M43_MACHINE_RECORD_PATH = "docs/evidence/m43/machine_verified_canary_completion.json"
M42_GRADUATION_PATH = "docs/evidence/m42/graduation_recommendation.json"

NON_PRODUCTION_BANNER = (
    "M44 LIMITED ROLLOUT AUTHORIZATION FRAMEWORK\n"
    "NON-PRODUCTION\n"
    "READ-ONLY\n"
    "FAIL-CLOSED\n"
    "DENY-BY-DEFAULT\n"
    "AUTHORIZATION FRAMEWORK ONLY\n"
    "GRANTS NOTHING\n"
    "NO ACTIVE\n"
    "NO PRODUCTION\n"
    "NO WRITE\n"
    "NO ROLLOUT EXECUTION\n"
    "NO SCOPE EXPANSION\n"
    "SEPARATE OPERATOR AUTHORIZATION REQUIRED TO EXECUTE\n"
    "TRADING GUARDIAN UNENGAGED"
)

# Framework-level authority state — every field explicitly NOT GRANTED / advisory.
FRAMEWORK_AUTHORITY_STATE = {
    "active": "NOT GRANTED",
    "production": "NOT AUTHORIZED",
    "write": "NOT GRANTED",
    "rollout_execution": "NOT GRANTED",
    "rollout_full": "NOT GRANTED",
    "scope_expansion": "FORBIDDEN",
    "provider_permissions": "UNCHANGED",
    "framework": "READY (ADVISORY ONLY)",
}

# Eight runtime acknowledgements an operator must attach to a rollout request.
M44_ACK_TOKENS = (
    "I_CONFIRM_FRAMEWORK_READINESS_IS_NOT_AUTHORIZATION",
    "I_CONFIRM_NO_PRODUCTION_ACTIVATION",
    "I_CONFIRM_NO_WRITE_AUTHORITY",
    "I_CONFIRM_ROLLBACK_OWNER_ASSIGNED",
    "I_CONFIRM_INCIDENT_OWNER_ASSIGNED",
    "I_CONFIRM_BOUNDED_REVERSIBLE_ROLLOUT",
    "I_CONFIRM_SEPARATE_EXECUTION_AUTHORIZATION_REQUIRED",
    "I_CONFIRM_TRADING_GUARDIAN_REMAINS_UNENGAGED",
)

# Discrete rollout ceilings the framework understands (percent). No other value is
# a valid rollout percent anywhere in M44; a policy further restricts this set.
ALLOWED_ROLLOUT_PERCENTS = (0, 1, 2, 5, 10, 25, 50, 100)

RISK_LEVELS = ("low", "medium", "high", "critical")

# Read-only scope universe. Least privilege: single provider, GET identity/meta only.
ALLOWED_SCOPES = frozenset({"read_only:github_meta:/user", "read_only:github_meta:/meta"})


class M44Error(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


class M44Verdict(str, Enum):
    ROLLOUT_DENIED = "ROLLOUT_DENIED"                       # deny-by-default / gated
    ROLLOUT_REQUEST_INCOMPLETE = "ROLLOUT_REQUEST_INCOMPLETE"
    ROLLOUT_VALIDATION_FAILED = "ROLLOUT_VALIDATION_FAILED"
    ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY = (
        "ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY"
    )


# ── 2. Rollout policy objects (extensible registry) ──────────────────────────
@dataclass(frozen=True)
class RolloutPolicy:
    """A bounded, least-privilege authorization envelope. Grants no execution.

    permits_live_execution is ALWAYS False in M44: policies describe what a *future*
    operator authorization would be allowed to request, never what M44 may run.
    """
    name: str
    max_percent: int
    allowed_percents: tuple[int, ...]
    allowed_scopes: frozenset[str]
    allowed_providers: frozenset[str]
    allowed_risk_levels: frozenset[str]
    required_acknowledgements: tuple[str, ...]
    requires_machine_proof: bool
    requires_closed_credential: bool
    requires_graduation_recommended: bool
    permits_live_execution: bool = False  # invariant: never True

    def fingerprint(self) -> str:
        return _hmac(
            b"policy",
            json.dumps({
                "name": self.name, "max_percent": self.max_percent,
                "allowed_percents": list(self.allowed_percents),
                "allowed_scopes": sorted(self.allowed_scopes),
                "allowed_providers": sorted(self.allowed_providers),
                "allowed_risk_levels": sorted(self.allowed_risk_levels),
                "required_acknowledgements": list(self.required_acknowledgements),
                "requires_machine_proof": self.requires_machine_proof,
                "requires_closed_credential": self.requires_closed_credential,
                "requires_graduation_recommended": self.requires_graduation_recommended,
                "permits_live_execution": self.permits_live_execution,
            }, sort_keys=True).encode(),
            length=24,
        )


_ALL_ACKS = M44_ACK_TOKENS


def _policy(name, max_percent, allowed_percents, *, providers=(PROVIDER_ID,),
           scopes=ALLOWED_SCOPES, risk=RISK_LEVELS, machine_proof=True,
           closed_credential=True, graduation=True) -> RolloutPolicy:
    return RolloutPolicy(
        name=name, max_percent=max_percent, allowed_percents=tuple(allowed_percents),
        allowed_scopes=frozenset(scopes), allowed_providers=frozenset(providers),
        allowed_risk_levels=frozenset(risk), required_acknowledgements=_ALL_ACKS,
        requires_machine_proof=machine_proof, requires_closed_credential=closed_credential,
        requires_graduation_recommended=graduation, permits_live_execution=False,
    )


# Built-in policies. DryRun / Simulation require no live evidence (0% only); the
# rest require the full machine-proof + closed-credential + graduation chain.
POLICIES: dict[str, RolloutPolicy] = {
    "ReadOnlyLimited": _policy("ReadOnlyLimited", 5, (1, 2, 5)),
    "ReadOnlyExtended": _policy("ReadOnlyExtended", 25, (1, 2, 5, 10, 25)),
    "ProductionCandidate": _policy(
        "ProductionCandidate", 10, (1, 2, 5, 10), risk=("low", "medium")),
    "EmergencyRollback": _policy(
        "EmergencyRollback", 0, (0,), graduation=False),
    "IncidentRecovery": _policy(
        "IncidentRecovery", 5, (1, 2, 5), risk=("high", "critical")),
    "DryRun": _policy(
        "DryRun", 0, (0,), machine_proof=False, closed_credential=False, graduation=False),
    "Simulation": _policy(
        "Simulation", 0, (0,), machine_proof=False, closed_credential=False, graduation=False),
}


def register_policy(policy: RolloutPolicy) -> None:
    """Extensibility hook. Rejects any policy that would permit live execution."""
    if policy.permits_live_execution:
        raise M44Error("policy_permits_live_execution_forbidden", policy.name)
    if not (0 <= policy.max_percent <= 100):
        raise M44Error("policy_max_percent_out_of_bounds", policy.name)
    for p in policy.allowed_percents:
        if p not in ALLOWED_ROLLOUT_PERCENTS or p > policy.max_percent:
            raise M44Error("policy_allowed_percent_out_of_bounds", f"{policy.name}:{p}")
    POLICIES[policy.name] = policy


def get_policy(name: str) -> RolloutPolicy:
    pol = POLICIES.get(name)
    if pol is None:
        raise M44Error("unknown_policy", name)
    return pol


# ── 1. Rollout authorization request (all mandatory fields) ──────────────────
MANDATORY_FIELDS = (
    "rollout_id", "operator_identity", "approval_timestamp", "expiration",
    "purpose", "scope", "provider", "resource", "rollout_percent", "risk_level",
    "rollback_owner", "incident_owner", "policy",
    "approval_fingerprints", "evidence_fingerprints",
)


@dataclass
class RolloutRequest:
    rollout_id: str = ""
    operator_identity: str = ""
    approval_timestamp: str = ""          # ISO-8601 UTC
    expiration: str = ""                  # ISO-8601 UTC
    purpose: str = ""
    scope: str = ""
    provider: str = ""
    resource: str = ""
    rollout_percent: Optional[int] = None
    risk_level: str = ""
    rollback_owner: str = ""
    incident_owner: str = ""
    policy: str = ""
    approval_fingerprints: tuple[str, ...] = ()
    evidence_fingerprints: tuple[str, ...] = ()
    acknowledgements: tuple[str, ...] = ()
    operator_signature: str = ""
    contains_secret_values: bool = False  # marker only; enforced by leak scan

    def core(self) -> dict[str, Any]:
        """Canonical signed core (excludes the signature itself)."""
        return {
            "rollout_id": self.rollout_id,
            "operator_identity": self.operator_identity,
            "approval_timestamp": self.approval_timestamp,
            "expiration": self.expiration,
            "purpose": self.purpose,
            "scope": self.scope,
            "provider": self.provider,
            "resource": self.resource,
            "rollout_percent": self.rollout_percent,
            "risk_level": self.risk_level,
            "rollback_owner": self.rollback_owner,
            "incident_owner": self.incident_owner,
            "policy": self.policy,
            "approval_fingerprints": list(self.approval_fingerprints),
            "evidence_fingerprints": list(self.evidence_fingerprints),
            "acknowledgements": list(self.acknowledgements),
        }

    def missing_fields(self) -> list[str]:
        out: list[str] = []
        for f in MANDATORY_FIELDS:
            v = getattr(self, f)
            if v is None or (isinstance(v, (str, tuple, list)) and len(v) == 0):
                out.append(f)
        return out

    def to_public(self) -> dict[str, Any]:
        """Leak-safe projection (references + fingerprints only, never secrets)."""
        d = self.core()
        d["operator_signature"] = self.operator_signature
        d["contains_secret_values"] = False
        return d


def sign_request(request: RolloutRequest, operator_identity: Optional[str] = None) -> str:
    """Deterministic operator signature over the canonical core. Tamper-evident:
    any change to a signed field invalidates the signature."""
    ident = (operator_identity or request.operator_identity).encode()
    body = json.dumps(request.core(), sort_keys=True, default=str).encode()
    return _hmac(_SIG_DOMAIN, ident, body, length=32)


def request_fingerprint(request: RolloutRequest) -> str:
    return _hmac(
        _FP_DOMAIN,
        json.dumps(request.to_public(), sort_keys=True, default=str).encode(),
        length=24,
    )


# ── 4. Percentage guard ──────────────────────────────────────────────────────
def check_percentage(policy: RolloutPolicy, percent: Any) -> list[str]:
    """Reject missing / non-integer / negative / above-ceiling / off-policy percents."""
    blockers: list[str] = []
    if percent is None:
        return ["percentage_missing"]
    if isinstance(percent, bool) or not isinstance(percent, int):
        return ["percentage_not_integer"]        # fractional / non-int is forbidden
    if percent < 0:
        blockers.append("percentage_negative")
    if percent not in ALLOWED_ROLLOUT_PERCENTS:
        blockers.append("percentage_not_an_allowed_ceiling")
    if percent > policy.max_percent:
        blockers.append("percentage_above_policy_ceiling")
    if percent not in policy.allowed_percents:
        blockers.append("percentage_not_permitted_by_policy")
    return blockers


# ── 5. Runtime safety gates ──────────────────────────────────────────────────
@dataclass
class RuntimeSnapshot:
    identity_drift: bool = False
    provider_mismatch: bool = False
    credential_mismatch: bool = False
    rollback_active: bool = False
    kill_switch_active: bool = False
    incident_unresolved: bool = False
    security_alert_open: bool = False
    trading_guardian_active: bool = False
    m32_prohibition_violated: bool = False
    machine_proof_present: bool = False
    operator_approval_present: bool = False


def runtime_gate_blockers(snap: RuntimeSnapshot,
                          environ: Optional[dict[str, str]] = None) -> list[str]:
    """Deny-by-default runtime gate. Any unsafe condition blocks; missing machine
    proof or missing operator approval blocks. Returns [] only when fully safe."""
    blockers: list[str] = []
    if snap.identity_drift:
        blockers.append("identity_drift")
    if snap.provider_mismatch:
        blockers.append("provider_mismatch")
    if snap.credential_mismatch:
        blockers.append("credential_mismatch")
    if snap.rollback_active:
        blockers.append("rollback_active")
    if snap.kill_switch_active or kill_switch_active(environ):
        blockers.append("kill_switch_active")
    if snap.incident_unresolved:
        blockers.append("incident_unresolved")
    if snap.security_alert_open:
        blockers.append("security_alert_open")
    if snap.trading_guardian_active:
        blockers.append("trading_guardian_active")
    if snap.m32_prohibition_violated:
        blockers.append("m32_prohibition_violated")
    if not snap.machine_proof_present:
        blockers.append("machine_proof_absent")
    if not snap.operator_approval_present:
        blockers.append("operator_approval_absent")
    return blockers


# ── 6. Rollback contracts (deterministic triggers) ───────────────────────────
class RollbackTrigger(str, Enum):
    IDENTITY_MISMATCH = "identity_mismatch"
    PROVIDER_CHANGED = "provider_changed"
    UNEXPECTED_RESPONSE = "unexpected_response"
    ERROR_BUDGET_EXCEEDED = "error_budget_exceeded"
    POLICY_VIOLATION = "policy_violation"
    KILL_SWITCH = "kill_switch"
    SECURITY_ALERT = "security_alert"
    MANUAL_OPERATOR_STOP = "manual_operator_stop"


ROLLBACK_TRIGGERS = tuple(t.value for t in RollbackTrigger)


def evaluate_rollback(signals: dict[str, Any]) -> dict[str, Any]:
    """Deterministic rollback decision. Any fired trigger => rollback required."""
    fired = [t.value for t in RollbackTrigger if bool(signals.get(t.value))]
    return {
        "rollback_required": bool(fired),
        "triggers_fired": fired,
        "deterministic": True,
        "rollback_kind": "automatic" if fired else "none",
    }


# Provenance classes (M44's own verdict on an artifact, never a trusted string).
PROV_MACHINE_PROOF = "MACHINE_PROOF"
PROV_OPERATOR_ATTESTED = "OPERATOR_ATTESTED"
PROV_SIMULATED = "SIMULATED"
PROV_ABSENT = "ABSENT"


# ── evidence chain (referenced by fingerprint; read-only) ────────────────────
@dataclass
class EvidenceDescriptor:
    fingerprint: str
    kind: str
    machine_verified_live: bool = False
    credential_lifecycle_closed: bool = False
    graduation_recommended: bool = False
    provenance: str = "REFERENCE"


def verify_machine_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Independently verify an M43 machine record's provenance — never trust a
    state-name string. Requires MACHINE source, machine_verified + _live, a CLOSED
    credential lifecycle, and the Phase 6 HTTP 401 destruction proof.

    A simulated/rehearsal record (source SIMULATED_REHEARSAL, machine_verified_live
    False) and an operator-attested record both fail this check, fail-closed.
    """
    reasons: list[str] = []
    if not rec:
        return {"verified": False, "reasons": ["machine_record_absent"],
                "provenance": PROV_ABSENT, "lifecycle_closed": False}
    source = rec.get("source")
    if source in ("SIMULATED_REHEARSAL", "SIMULATED"):
        reasons.append("source_simulated")
    elif source != "MACHINE":
        reasons.append("source_not_machine")
    if rec.get("machine_verified") is not True:
        reasons.append("not_machine_verified")
    if rec.get("machine_verified_live") is not True:
        reasons.append("not_machine_verified_live")
    lifecycle = rec.get("credential_lifecycle", {}) or {}
    lifecycle_closed = lifecycle.get("status") == "CLOSED"
    if not lifecycle_closed:
        reasons.append("credential_lifecycle_not_closed")
    if lifecycle.get("http_401_confirmed") is not True:
        reasons.append("http_401_not_confirmed")   # Phase 6 destruction proof
    if rec.get("contains_secret_values") is True:
        reasons.append("contains_secret_values")
    # Provider binding: a machine record for any other provider cannot clear
    # github_meta graduation criteria (identity of the attested system).
    provider = rec.get("provider")
    if provider is not None and provider != PROVIDER_ID:
        reasons.append("provider_mismatch")
    # Scope signal (when present) must remain unchanged / read-only canary.
    signals = rec.get("machine_signals") or rec.get("operator_reported_signals") or {}
    scope_sig = signals.get("scope")
    if scope_sig is not None and scope_sig not in ("unchanged", "read_only", "bounded"):
        reasons.append("scope_mismatch")
    identity_sig = signals.get("identity")
    if identity_sig is not None and identity_sig not in ("unchanged",):
        reasons.append("identity_mismatch")
    provenance = (PROV_MACHINE_PROOF if not reasons
                  else (PROV_SIMULATED if "source_simulated" in reasons
                        else PROV_OPERATOR_ATTESTED))
    return {"verified": not reasons, "reasons": reasons,
            "provenance": provenance, "lifecycle_closed": lifecycle_closed}


def _m42_evidence_base(base: Path) -> Path:
    """Map an M44 resolution base (repo root or evidence root) to m42's base.

    m42.load_evidence expects a directory containing m40/, m41/, m43/ children.
    M44 callers typically pass the repository root; hermetic tests may pass a
    temporary tree with the same layout under docs/evidence/.
    """
    candidate = base / "docs" / "evidence"
    if candidate.is_dir():
        return candidate
    if (base / "m40").is_dir() or (base / "m43").is_dir() or (base / "m41").is_dir():
        return base
    return candidate  # default layout even if absent (m42 fails closed)


def resolve_graduation_state(base: str | Path = ".") -> dict[str, Any]:
    """Authoritative, machine-override-aware graduation state.

    Derived from the LIVE m42 review — whose loader (`m42.load_evidence`) already
    prefers the M43 machine record over the operator-attested / stale artifact — AND
    from M44's own independent verification of that machine record. Never derived
    from the stale stored `graduation_recommendation.json` string.

    graduation_recommended is True only when BOTH the live review recommends
    graduation AND the machine record independently verifies (defence in depth):
    a stale or fabricated string cannot alone satisfy the criterion.

    Both the machine-record path and the m42 review are resolved relative to
    `base` so hermetic tests cannot accidentally inherit the real repository.
    """
    base = Path(base)
    machine: dict[str, Any] = {}
    machine_fp = ""
    m43p = base / M43_MACHINE_RECORD_PATH
    if not m43p.exists():
        # Also accept m42-style relative layout under base (docs/evidence omitted).
        alt = base / "m43" / "machine_verified_canary_completion.json"
        if alt.exists():
            m43p = alt
    if m43p.exists():
        try:
            machine = json.loads(m43p.read_text())
        except (ValueError, OSError):
            machine = {}
        machine_fp = str(machine.get("fingerprint", ""))
    mver = verify_machine_record(machine)

    review: dict[str, Any] = {}
    try:
        from saathi.credentials import m42
        review = m42.run_graduation_review(base=str(_m42_evidence_base(base)))
    except Exception as e:  # never let a review error grant anything
        review = {"recommendation": "GRADUATION_REVIEW_UNAVAILABLE", "error": type(e).__name__}
    review_reco = review.get("recommendation")
    review_fp = str(review.get("fingerprint", ""))

    recommended = (review_reco == "GRADUATION_RECOMMENDED") and mver["verified"]
    return {
        "recommendation": review_reco,
        "review_fingerprint": review_fp,
        "machine_record_fingerprint": machine_fp,
        "machine_record_verified": mver["verified"],
        "machine_record_reasons": mver["reasons"],
        "machine_lifecycle_closed": mver["lifecycle_closed"],
        "provenance": mver["provenance"],
        "graduation_recommended": recommended,
        "stale_static_file_not_trusted": M42_GRADUATION_PATH,
        "m42_evidence_base": str(_m42_evidence_base(base)),
        "note": ("Graduation is derived from the live machine-override-aware M42 "
                 "review plus independent M43 machine-record verification; the "
                 "stored graduation_recommendation.json is not trusted as a string."),
    }


def load_evidence_index(base: str | Path = ".") -> dict[str, EvidenceDescriptor]:
    """Read-only evidence index keyed by fingerprint. Resolves the GENUINE
    machine-proof-backed state (not the stale stored M42 file). Never returns
    secrets; only public provenance markers M44 has independently verified."""
    base = Path(base)
    index: dict[str, EvidenceDescriptor] = {}
    state = resolve_graduation_state(base)

    mfp = state["machine_record_fingerprint"]
    if mfp:
        index[mfp] = EvidenceDescriptor(
            fingerprint=mfp, kind="m43_machine_canary",
            machine_verified_live=state["machine_record_verified"],
            credential_lifecycle_closed=state["machine_lifecycle_closed"],
            provenance=state["provenance"],
        )

    rfp = state["review_fingerprint"]
    if rfp:
        index[rfp] = EvidenceDescriptor(
            fingerprint=rfp, kind="m42_graduation",
            graduation_recommended=state["graduation_recommended"],
            provenance=(PROV_MACHINE_PROOF if state["graduation_recommended"]
                        else state["provenance"]),
        )
    return index


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


# ── 3. Rollout validator ─────────────────────────────────────────────────────
def validate_request(
    request: RolloutRequest,
    *,
    now: Optional[str] = None,
    evidence_index: Optional[dict[str, EvidenceDescriptor]] = None,
    runtime: Optional[RuntimeSnapshot] = None,
    environ: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Fail-closed validation. Returns an advisory verdict; NEVER grants execution.

    The maximal verdict is ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY, meaning the
    request is well-formed, bounded, and evidence-backed — a future operator may then
    seek a separate execution authorization. M44 itself authorizes nothing to run.
    """
    blockers: list[str] = []
    checks: dict[str, bool] = {}

    # (a) completeness — deny-by-default on any missing mandatory field.
    missing = request.missing_fields()
    checks["all_mandatory_fields_present"] = not missing
    if missing:
        return _validation_result(
            request, M44Verdict.ROLLOUT_REQUEST_INCOMPLETE,
            blockers=[f"missing:{m}" for m in missing], checks=checks)

    # (b) policy resolves.
    try:
        policy = get_policy(request.policy)
    except M44Error:
        return _validation_result(
            request, M44Verdict.ROLLOUT_VALIDATION_FAILED,
            blockers=[f"unknown_policy:{request.policy}"], checks=checks)
    checks["policy_known"] = True
    checks["policy_grants_no_live_execution"] = not policy.permits_live_execution
    if policy.permits_live_execution:  # invariant guard (unreachable for built-ins)
        blockers.append("policy_permits_live_execution_forbidden")

    # (c) provider / identity / scope / risk.
    checks["provider_matches"] = request.provider == PROVIDER_ID
    if request.provider != PROVIDER_ID:
        blockers.append("provider_mismatch")
    checks["provider_allowed_by_policy"] = request.provider in policy.allowed_providers
    if request.provider not in policy.allowed_providers:
        blockers.append("provider_not_allowed_by_policy")

    checks["scope_allowed"] = request.scope in policy.allowed_scopes
    if request.scope not in policy.allowed_scopes:
        blockers.append("scope_not_allowed")

    checks["risk_level_known"] = request.risk_level in RISK_LEVELS
    checks["risk_level_allowed_by_policy"] = request.risk_level in policy.allowed_risk_levels
    if request.risk_level not in policy.allowed_risk_levels:
        blockers.append("risk_level_not_allowed")

    # (d) percentage guard.
    pct_blockers = check_percentage(policy, request.rollout_percent)
    checks["percentage_within_policy"] = not pct_blockers
    blockers.extend(pct_blockers)

    # (e) expiration (not expired; approval precedes expiration).
    now_dt = _parse_iso(now) if now else datetime.now(timezone.utc)
    exp_dt = _parse_iso(request.expiration)
    appr_dt = _parse_iso(request.approval_timestamp)
    checks["expiration_parseable"] = exp_dt is not None
    checks["approval_parseable"] = appr_dt is not None
    if exp_dt is None or appr_dt is None or now_dt is None:
        blockers.append("timestamp_unparseable")
    else:
        not_expired = now_dt < exp_dt
        checks["not_expired"] = not_expired
        if not not_expired:
            blockers.append("authorization_expired")
        ordered = appr_dt <= exp_dt
        checks["approval_before_expiration"] = ordered
        if not ordered:
            blockers.append("approval_after_expiration")

    # (f) acknowledgements — must cover every required token.
    have = set(request.acknowledgements)
    missing_acks = [a for a in policy.required_acknowledgements if a not in have]
    checks["acknowledgements_complete"] = not missing_acks
    if missing_acks:
        blockers.append("acknowledgements_incomplete")

    # (g) operator signature — recompute + compare (tamper-evident).
    expected_sig = sign_request(request)
    sig_ok = bool(request.operator_signature) and request.operator_signature == expected_sig
    checks["operator_signature_valid"] = sig_ok
    if not sig_ok:
        blockers.append("operator_signature_invalid")

    # (h) approval reference present.
    checks["approval_reference_present"] = bool(request.approval_fingerprints)
    if not request.approval_fingerprints:
        blockers.append("approval_reference_missing")

    # (i) evidence chain — machine proof + closed credential + graduation as required.
    index = evidence_index if evidence_index is not None else load_evidence_index()
    referenced = [index[fp] for fp in request.evidence_fingerprints if fp in index]
    checks["evidence_fingerprints_resolve"] = (
        len(referenced) == len(request.evidence_fingerprints) and bool(referenced))
    if len(referenced) != len(request.evidence_fingerprints) or not referenced:
        blockers.append("evidence_chain_unresolved")

    if policy.requires_machine_proof:
        has_proof = any(d.machine_verified_live for d in referenced)
        checks["machine_proof_present"] = has_proof
        if not has_proof:
            blockers.append("machine_proof_absent")
    if policy.requires_closed_credential:
        closed = any(d.credential_lifecycle_closed for d in referenced)
        checks["credential_lifecycle_closed"] = closed
        if not closed:
            blockers.append("credential_lifecycle_not_closed")
    if policy.requires_graduation_recommended:
        grad = any(d.graduation_recommended for d in referenced)
        checks["graduation_recommended"] = grad
        if not grad:
            blockers.append("graduation_not_recommended")

    evidence_provenance = sorted({d.provenance for d in referenced}) or [PROV_ABSENT]

    # (j) runtime safety gates.
    runtime = runtime or RuntimeSnapshot()
    gate_blockers = runtime_gate_blockers(runtime, environ)
    checks["runtime_gates_clear"] = not gate_blockers
    blockers.extend(f"gate:{b}" for b in gate_blockers)

    verdict = (M44Verdict.ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY
               if not blockers else M44Verdict.ROLLOUT_VALIDATION_FAILED)
    return _validation_result(request, verdict, blockers=blockers, checks=checks,
                              policy=policy, evidence_provenance=evidence_provenance)


def _validation_result(request: RolloutRequest, verdict: M44Verdict, *,
                       blockers: list[str], checks: dict[str, bool],
                       policy: Optional[RolloutPolicy] = None,
                       evidence_provenance: Optional[list[str]] = None) -> dict[str, Any]:
    advisory = verdict == M44Verdict.ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY
    result = {
        "schema": SCHEMA_VERSION,
        "milestone": "M44",
        "rollout_id": request.rollout_id,
        "verdict": verdict.value,
        "advisory_only": True,
        "authorizes_execution": False,      # invariant: always False
        "alters_runtime_authority": False,  # invariant: always False
        "grants_anything": False,
        "grants_active": False,
        "grants_production": False,
        "grants_write": False,
        "expands_scope": False,
        "requires_separate_execution_authorization": True,
        "evidence_provenance": evidence_provenance or [PROV_ABSENT],
        "blockers": sorted(set(blockers)),
        "checks": checks,
        "policy": request.policy,
        "policy_fingerprint": policy.fingerprint() if policy else "",
        "request_fingerprint": request_fingerprint(request),
        "provider": PROVIDER_ID,
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "note": (
            "Advisory only. A VALIDATED verdict means the request is well-formed, "
            "bounded, and evidence-backed; it does NOT authorize any rollout to run. "
            "Execution requires a completely separate operator authorization."
        ) if advisory else (
            "Fail-closed: request denied / invalid. Nothing authorized."
        ),
        "contains_secret_values": False,
    }
    result["fingerprint"] = _hmac(
        _FP_DOMAIN,
        json.dumps({"rollout_id": request.rollout_id, "verdict": verdict.value,
                    "blockers": sorted(set(blockers))}, sort_keys=True).encode(),
        length=24)
    return result


# ── 7. Rollout ledger (append-only, hash-chained, immutable) ─────────────────
class LedgerEvent(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    ROLLBACK = "ROLLBACK"
    ABORTED = "ABORTED"
    REVIEWED = "REVIEWED"


def _ledger_entry(prev_fp: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "schema": "m44.rollout_ledger.v1",
        "event": event,
        "prev_fingerprint": prev_fp,
        "payload": payload,
        "contains_secret_values": False,
    }
    entry["fingerprint"] = _hmac(
        _LEDGER_DOMAIN,
        json.dumps({"event": event, "prev": prev_fp, "payload": payload},
                   sort_keys=True, default=str).encode(),
        length=24)
    return entry


def append_ledger(event: LedgerEvent, payload: dict[str, Any],
                  path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    """Append one immutable, hash-chained entry. The chain makes prior-entry
    tampering detectable (each entry commits to the previous fingerprint)."""
    assert is_clean(payload), "ledger payload not leak-clean"
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prev_fp = ""
    if p.exists():
        lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
        if lines:
            prev_fp = json.loads(lines[-1]).get("fingerprint", "")
    entry = _ledger_entry(prev_fp, event.value, payload)
    with p.open("a") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def read_ledger(path: str | Path = LEDGER_PATH) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def verify_ledger_chain(path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    """Recompute the hash chain; report the first break (tamper-evidence)."""
    entries = read_ledger(path)
    prev_fp = ""
    for i, entry in enumerate(entries):
        expected = _ledger_entry(
            entry.get("prev_fingerprint", ""), entry.get("event", ""),
            entry.get("payload", {}))["fingerprint"]
        if entry.get("prev_fingerprint", "") != prev_fp:
            return {"intact": False, "broken_at": i, "reason": "prev_fingerprint_mismatch"}
        if entry.get("fingerprint") != expected:
            return {"intact": False, "broken_at": i, "reason": "fingerprint_mismatch"}
        prev_fp = entry.get("fingerprint", "")
    return {"intact": True, "entries": len(entries)}


# ── 8. Audit API (read-only; never exposes secrets) ──────────────────────────
def audit_show_rollout(rollout_id: str, path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    events = [e for e in read_ledger(path) if e.get("payload", {}).get("rollout_id") == rollout_id]
    return {"rollout_id": rollout_id, "events": events, "count": len(events),
            "contains_secret_values": False}


def audit_show_approvals(rollout_id: str, path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    fps: list[str] = []
    for e in read_ledger(path):
        pl = e.get("payload", {})
        if pl.get("rollout_id") == rollout_id:
            fps.extend(pl.get("approval_fingerprints", []))
    return {"rollout_id": rollout_id, "approval_fingerprints": sorted(set(fps)),
            "contains_secret_values": False}


def audit_show_evidence_chain(rollout_id: str, path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    fps: list[str] = []
    for e in read_ledger(path):
        pl = e.get("payload", {})
        if pl.get("rollout_id") == rollout_id:
            fps.extend(pl.get("evidence_fingerprints", []))
    return {"rollout_id": rollout_id, "evidence_fingerprints": sorted(set(fps)),
            "contains_secret_values": False}


def audit_show_validation(rollout_id: str, path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    for e in reversed(read_ledger(path)):
        pl = e.get("payload", {})
        if pl.get("rollout_id") == rollout_id and e.get("event") in (
                LedgerEvent.VALIDATED.value, LedgerEvent.DENIED.value):
            return {"rollout_id": rollout_id, "event": e.get("event"),
                    "verdict": pl.get("verdict"), "blockers": pl.get("blockers", []),
                    "contains_secret_values": False}
    return {"rollout_id": rollout_id, "event": None, "contains_secret_values": False}


def audit_show_rollback_history(rollout_id: str, path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    hist = [e for e in read_ledger(path)
            if e.get("payload", {}).get("rollout_id") == rollout_id
            and e.get("event") == LedgerEvent.ROLLBACK.value]
    return {"rollout_id": rollout_id, "rollbacks": hist, "count": len(hist),
            "contains_secret_values": False}


def audit_show_incident_history(rollout_id: str, path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    hist = [e for e in read_ledger(path)
            if e.get("payload", {}).get("rollout_id") == rollout_id
            and e.get("event") in (LedgerEvent.ABORTED.value, LedgerEvent.ROLLBACK.value)]
    return {"rollout_id": rollout_id, "incidents": hist, "count": len(hist),
            "contains_secret_values": False}


# ── high-level operations (framework only; grant nothing) ────────────────────
def create_rollout(request: RolloutRequest, *, path: str | Path = LEDGER_PATH,
                   persist: bool = False) -> dict[str, Any]:
    """Record a rollout *request*. Recording is not authorization and not execution."""
    payload = {
        "rollout_id": request.rollout_id,
        "operator_identity": request.operator_identity,
        "policy": request.policy,
        "provider": request.provider,
        "scope": request.scope,
        "rollout_percent": request.rollout_percent,
        "risk_level": request.risk_level,
        "rollback_owner": request.rollback_owner,
        "incident_owner": request.incident_owner,
        "approval_fingerprints": list(request.approval_fingerprints),
        "evidence_fingerprints": list(request.evidence_fingerprints),
        "request_fingerprint": request_fingerprint(request),
        "authorizes_execution": False,
    }
    entry = append_ledger(LedgerEvent.CREATED, payload, path) if persist else _ledger_entry(
        "", LedgerEvent.CREATED.value, payload)
    return {"created": True, "rollout_id": request.rollout_id, "persisted": persist,
            "ledger_entry": entry, "authorizes_execution": False,
            "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
            "contains_secret_values": False}


def review_rollout(request: RolloutRequest, *, path: str | Path = LEDGER_PATH,
                   persist: bool = False, **kwargs: Any) -> dict[str, Any]:
    """Validate + summarize a request for operator review. Advisory only."""
    result = validate_request(request, **kwargs)
    if persist:
        event = (LedgerEvent.VALIDATED
                 if result["verdict"] == M44Verdict.ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY.value
                 else LedgerEvent.DENIED)
        append_ledger(event, {
            "rollout_id": request.rollout_id, "verdict": result["verdict"],
            "blockers": result["blockers"],
            "approval_fingerprints": list(request.approval_fingerprints),
            "evidence_fingerprints": list(request.evidence_fingerprints),
        }, path)
    return result


# ── framework self-check + evidence ──────────────────────────────────────────
def framework_status() -> dict[str, Any]:
    """Prove the framework is wired and fail-closed WITHOUT authorizing anything.

    Emits ROLLOUT_AUTHORIZATION_FRAMEWORK_READY (advisory; legacy alias
    ROLL_OUT_AUTHORIZATION_FRAMEWORK_READY). Confirms a default/empty
    request is denied and that no authority is granted anywhere.
    """
    empty = validate_request(RolloutRequest())
    default_denied = empty["verdict"] == M44Verdict.ROLLOUT_REQUEST_INCOMPLETE.value
    components = {
        "authorization_engine": True,
        "rollout_policies": len(POLICIES),
        "validator": True,
        "percentage_guard": True,
        "runtime_safety_gates": True,
        "rollback_engine": len(ROLLBACK_TRIGGERS),
        "rollout_ledger": True,
        "audit_api": True,
    }
    graduation = resolve_graduation_state()
    return {
        "schema": SCHEMA_VERSION,
        "milestone": "M44",
        "state": FRAMEWORK_STATE,
        "state_legacy_alias": FRAMEWORK_STATE_LEGACY_ALIAS,
        "framework_ready": all(bool(v) for v in components.values()),
        "default_request_denied": default_denied,
        "components": components,
        "policies": sorted(POLICIES),
        "allowed_rollout_percents": list(ALLOWED_ROLLOUT_PERCENTS),
        "rollback_triggers": list(ROLLBACK_TRIGGERS),
        # Current genuine advisory graduation state (machine-override-aware; NOT the
        # stale stored graduation_recommendation.json string).
        "current_graduation_state": {
            "recommendation": graduation["recommendation"],
            "provenance": graduation["provenance"],
            "graduation_recommended_advisory": graduation["graduation_recommended"],
            "machine_record_verified": graduation["machine_record_verified"],
            "machine_record_fingerprint": graduation["machine_record_fingerprint"],
            "m42_review_fingerprint": graduation["review_fingerprint"],
        },
        "advisory_only": True,
        "authorizes_execution": False,
        "alters_runtime_authority": False,
        "grants_anything": False,
        "grants_active": False,
        "grants_production": False,
        "grants_write": False,
        "expands_scope": False,
        "requires_separate_execution_authorization": True,
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "banner": NON_PRODUCTION_BANNER,
        "note": ("Framework infrastructure is ready. This state is advisory and grants "
                 "no ACTIVE / PRODUCTION / WRITE / ROLLOUT EXECUTION. A graduation "
                 "recommendation is advisory only — not authorization. Any future "
                 "rollout requires a completely separate operator authorization."),
        "contains_secret_values": False,
    }


def simulate(policy_name: str = "Simulation") -> dict[str, Any]:
    """Offline SIMULATED walkthrough. Produces no live effect and grants nothing."""
    policy = get_policy(policy_name)
    req = _synthetic_request(policy_name)
    result = validate_request(
        req, now="2000-01-01T00:00:00+00:00",
        evidence_index=_synthetic_evidence_index(),
        runtime=RuntimeSnapshot(machine_proof_present=True, operator_approval_present=True),
    )
    rollback = evaluate_rollback({RollbackTrigger.UNEXPECTED_RESPONSE.value: True})
    return {
        "schema": "m44.simulation.v1",
        "milestone": "M44",
        "mode": "SIMULATED_NOT_LIVE",
        "policy": policy_name,
        "policy_fingerprint": policy.fingerprint(),
        "validation": result,
        "rollback_example": rollback,
        "authorizes_execution": False,
        "alters_runtime_authority": False,
        "grants_anything": False,
        "advisory_only": True,
        "note": "SIMULATED. Proves the framework wiring; no live rollout, no authority.",
        "contains_secret_values": False,
    }


def _synthetic_evidence_index() -> dict[str, EvidenceDescriptor]:
    return {
        "SYNTH_M43_FP": EvidenceDescriptor(
            "SYNTH_M43_FP", "m43_machine_canary",
            machine_verified_live=True, credential_lifecycle_closed=True,
            provenance=PROV_MACHINE_PROOF),
        "SYNTH_M42_FP": EvidenceDescriptor(
            "SYNTH_M42_FP", "m42_graduation", graduation_recommended=True,
            provenance=PROV_MACHINE_PROOF),
    }


def _synthetic_request(policy_name: str) -> RolloutRequest:
    policy = get_policy(policy_name)
    pct = policy.allowed_percents[-1] if policy.allowed_percents else 0
    scope = sorted(policy.allowed_scopes)[0]
    risk = sorted(policy.allowed_risk_levels)[0]
    req = RolloutRequest(
        rollout_id="SIM-0001",
        operator_identity="operator:simulation",
        approval_timestamp="1999-12-31T00:00:00+00:00",
        expiration="2100-01-01T00:00:00+00:00",
        purpose="framework simulation",
        scope=scope, provider=PROVIDER_ID, resource="github_meta:/meta",
        rollout_percent=pct, risk_level=risk,
        rollback_owner="operator:rollback", incident_owner="operator:incident",
        policy=policy_name,
        approval_fingerprints=("SYNTH_APPROVAL_FP",),
        evidence_fingerprints=("SYNTH_M43_FP", "SYNTH_M42_FP"),
        acknowledgements=M44_ACK_TOKENS,
    )
    req.operator_signature = sign_request(req)
    return req


def module_fingerprint() -> str:
    """Non-secret structural fingerprint of the M44 module surface (schema + policies)."""
    return _hmac(
        b"m44.module",
        SCHEMA_VERSION.encode(),
        FRAMEWORK_STATE.encode(),
        json.dumps(sorted(POLICIES), sort_keys=True).encode(),
        json.dumps(list(ALLOWED_ROLLOUT_PERCENTS)).encode(),
        json.dumps(list(ROLLBACK_TRIGGERS), sort_keys=True).encode(),
        length=24,
    )


def build_framework_completion() -> dict[str, Any]:
    """Sanitized M44/M44.1 completion record. Grants nothing; records integration state."""
    status = framework_status()
    gs = resolve_graduation_state()
    denied = validate_request(RolloutRequest())
    return {
        "schema": "m44.framework_completion.v1",
        "milestone": "M44",
        "submilestone": "M44.1",
        "verdict": FRAMEWORK_STATE,
        "state_legacy_alias": FRAMEWORK_STATE_LEGACY_ALIAS,
        "module_fingerprint": module_fingerprint(),
        "framework_ready": status["framework_ready"],
        "default_request_denied": denied["verdict"] ==
            M44Verdict.ROLLOUT_REQUEST_INCOMPLETE.value,
        "evidence_resolution": {
            "stale_static_file_not_trusted": gs["stale_static_file_not_trusted"],
            "m42_evidence_base": gs.get("m42_evidence_base"),
            "machine_record_fingerprint": gs["machine_record_fingerprint"],
            "machine_record_verified": gs["machine_record_verified"],
            "machine_record_reasons": gs["machine_record_reasons"],
            "m42_review_fingerprint": gs["review_fingerprint"],
            "m42_recommendation": gs["recommendation"],
            "provenance": gs["provenance"],
            "graduation_recommended_advisory": gs["graduation_recommended"],
            "precedence": [
                "ignore docs/evidence/m42/graduation_recommendation.json (stale string)",
                "prefer docs/evidence/m43/machine_verified_canary_completion.json via m42 machine_override",
                "independently verify_machine_record (source/live/CLOSED/401/provider)",
                "require BOTH live GRADUATION_RECOMMENDED AND verified machine record",
            ],
        },
        "m43_1_closure_binding": {
            "machine_record_path": M43_MACHINE_RECORD_PATH,
            "machine_record_fingerprint": gs["machine_record_fingerprint"],
            "phase7_record":
                "docs/evidence/m43_1/m42_revalidation_phase_graduation_recommended_pending_cleanup.json",
            "phase8_record": "docs/evidence/m43_1/final_cleanup_closure.json",
            "note": "M43.1 records are audit bindings; M44 verifies the live M43 machine record + M42 review.",
        },
        "authorizes_execution": False,
        "alters_runtime_authority": False,
        "grants_anything": False,
        "runtime_execution_authority": False,
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "deployment": False,
        "push": False,
        "contains_secret_values": False,
        "note": ("M44_CLOSED_FRAMEWORK_READY_ADVISORY_ONLY — authorization framework "
                 "implemented, integrated with post-M43.1 machine-proof evidence, tested, "
                 "documented. Grants no rollout execution authority."),
    }


def build_m44_evidence() -> dict[str, dict[str, Any]]:
    status = framework_status()
    denied_default = validate_request(RolloutRequest())
    sim = simulate("Simulation")
    completion = build_framework_completion()
    return {
        "framework_status": status,
        "default_request_denied": denied_default,
        "simulation": sim,
        "framework_completion": completion,
        "summary": {
            "schema": "m44.summary.v1", "milestone": "M44",
            "state": FRAMEWORK_STATE,
            "state_legacy_alias": FRAMEWORK_STATE_LEGACY_ALIAS,
            "framework_ready": status["framework_ready"],
            "default_request_denied": denied_default["verdict"] ==
                M44Verdict.ROLLOUT_REQUEST_INCOMPLETE.value,
            "current_graduation_state": status["current_graduation_state"],
            "module_fingerprint": completion["module_fingerprint"],
            "authorizes_execution": False,
            "alters_runtime_authority": False,
            "grants_anything": False,
            "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
            "authorities": dict(AUTHORITIES),
            "m32_prohibition": "UNCHANGED",
            "trading_guardian": "UNCHANGED / UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m44_evidence(out_dir: str | Path = EVIDENCE_DIR) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m44_evidence()
    written: list[str] = []
    for name, b in bodies.items():
        assert is_clean(b), f"m44 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out),
            "state": FRAMEWORK_STATE, "module_fingerprint": module_fingerprint(),
            "contains_secret_values": False}
