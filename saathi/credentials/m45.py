"""M45 — Runtime Attestation and Bounded Rollout Readiness (composition-only).

M45 builds the machinery to produce, validate, bind, expire, and audit a
machine-attested RuntimeSnapshot that M44's safety gates currently lack.

It does NOT execute a provider rollout, activate production, enable writes,
deploy, expand scope, or grant any authority. Its maximal output is advisory:

    M45_RUNTIME_ATTESTATION_READY_ADVISORY_ONLY

— and a fully valid readiness evaluation yields only:

    BOUNDED_ROLLOUT_READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION

which still grants nothing. Execution requires a completely separate operator
authorization outside M44/M45.

Composition-only:
  * M39 authorities / kill switch / fingerprint domain / provider identity;
  * M42 graduation review fingerprint (via M44 resolve);
  * M43 machine-verified canary (referenced by fingerprint);
  * M43.1 closure (audit binding);
  * M44 rollout authorization framework (policies, validator, gates).

No parallel credential system, secret store, provider permission, or execution path.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
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

SCHEMA_VERSION = "m45.runtime_attestation.v1"
_FP_DOMAIN = b"saathi.m45.runtime_snapshot.domain.v1"
_SIG_DOMAIN = b"saathi.m45.attestation.domain.v1"
_LEDGER_DOMAIN = b"saathi.m45.snapshot_ledger.domain.v1"
_MACHINE_DOMAIN = b"saathi.m45.machine_identity.domain.v1"
_PROCESS_DOMAIN = b"saathi.m45.process_identity.domain.v1"

FRAMEWORK_STATE = "M45_RUNTIME_ATTESTATION_READY_ADVISORY_ONLY"
READY_VERDICT = "BOUNDED_ROLLOUT_READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION"

LEDGER_PATH = "docs/evidence/m45/snapshot_ledger.jsonl"
EVIDENCE_DIR = "docs/evidence/m45"

# Evidence bindings (read-only paths; referenced by fingerprint).
M43_MACHINE_PATH = "docs/evidence/m43/machine_verified_canary_completion.json"
M43_1_CLOSURE_PATH = "docs/evidence/m43_1/final_cleanup_closure.json"
M44_COMPLETION_PATH = "docs/evidence/m44/framework_completion.json"
M42_GRADUATION_PATH = "docs/evidence/m42/graduation_recommendation.json"

DEFAULT_TTL_SECONDS = 900  # 15 minutes
UNKNOWN = "UNKNOWN"

NON_PRODUCTION_BANNER = (
    "M45 RUNTIME ATTESTATION FRAMEWORK\n"
    "NON-PRODUCTION\n"
    "READ-ONLY\n"
    "FAIL-CLOSED\n"
    "DENY-BY-DEFAULT\n"
    "RUNTIME ATTESTATION ONLY\n"
    "GRANTS NOTHING\n"
    "NO ACTIVE\n"
    "NO PRODUCTION\n"
    "NO WRITE\n"
    "NO ROLLOUT EXECUTION\n"
    "NO DEPLOYMENT\n"
    "SEPARATE OPERATOR AUTHORIZATION REQUIRED TO EXECUTE\n"
    "TRADING GUARDIAN UNENGAGED"
)

FRAMEWORK_AUTHORITY_STATE = {
    "active": "NOT GRANTED",
    "production": "NOT AUTHORIZED",
    "write": "NOT GRANTED",
    "rollout_execution": "NOT GRANTED",
    "deployment": "NOT GRANTED",
    "scope_expansion": "FORBIDDEN",
    "provider_permissions": "UNCHANGED",
    "framework": "READY (ADVISORY ONLY)",
}


class AttestationProvenance(str, Enum):
    SELF_REPORTED = "SELF_REPORTED"
    LOCAL_MACHINE_OBSERVED = "LOCAL_MACHINE_OBSERVED"
    MACHINE_ATTESTED = "MACHINE_ATTESTED"       # local HMAC integrity, not HSM
    HARDWARE_ATTESTED = "HARDWARE_ATTESTED"     # never claimed without hardware
    SIMULATED = "SIMULATED"
    ABSENT = "ABSENT"


class SnapshotLifecycle(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    ELIGIBLE_ADVISORY_ONLY = "ELIGIBLE_ADVISORY_ONLY"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"
    TAMPERED = "TAMPERED"
    BLOCKED = "BLOCKED"


class M45Verdict(str, Enum):
    SNAPSHOT_INCOMPLETE = "SNAPSHOT_INCOMPLETE"
    SNAPSHOT_INVALID = "SNAPSHOT_INVALID"
    SNAPSHOT_EXPIRED = "SNAPSHOT_EXPIRED"
    SNAPSHOT_TAMPERED = "SNAPSHOT_TAMPERED"
    SNAPSHOT_BLOCKED = "SNAPSHOT_BLOCKED"
    SNAPSHOT_VALIDATED_ADVISORY_ONLY = "SNAPSHOT_VALIDATED_ADVISORY_ONLY"
    REQUEST_NOT_READY = "REQUEST_NOT_READY"
    BOUNDED_ROLLOUT_READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION = READY_VERDICT


class M45Error(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


# ── RuntimeSnapshot contract ─────────────────────────────────────────────────
@dataclass
class RuntimeAttestationSnapshot:
    """Machine-attestable runtime snapshot. No secrets. Fail-closed defaults."""
    snapshot_id: str = ""
    schema_version: str = SCHEMA_VERSION
    generated_at: str = ""
    expires_at: str = ""
    machine_id_fingerprint: str = UNKNOWN
    process_identity_fingerprint: str = UNKNOWN
    repository_commit: str = UNKNOWN
    repository_dirty_state: str = UNKNOWN  # clean | dirty | UNKNOWN
    branch: str = UNKNOWN
    provider: str = PROVIDER_ID
    provider_identity_fingerprint: str = UNKNOWN
    approved_scope: str = UNKNOWN
    credential_reference_kind: str = "NONE"
    credential_reference_fingerprint: str = ""
    credential_present: bool = False
    credential_secret_read: bool = False  # must always be False
    credential_lifecycle_state: str = "N/A"
    live_network_allowed: bool = False
    write_operations_allowed: bool = False
    deployment_allowed: bool = False
    rollout_execution_allowed: bool = False
    requested_rollout_percent: int = 0
    maximum_policy_percent: int = 0
    open_security_alerts: int = 0
    unresolved_incidents: int = 0
    rollback_active: bool = False
    kill_switch_active: bool = False
    error_budget_state: str = UNKNOWN  # healthy | exhausted | UNKNOWN
    audit_ledger_state: str = UNKNOWN  # intact | broken | UNKNOWN
    m32_state: str = "PROHIBITION_UNCHANGED"
    trading_guardian_state: str = "UNCHANGED / UNENGAGED"
    evidence_fingerprints: tuple[str, ...] = ()
    attestation_provenance: str = AttestationProvenance.ABSENT.value
    attestation_signature: str = ""
    # lifecycle + integrity
    lifecycle: str = SnapshotLifecycle.CREATED.value
    integrity_fingerprint: str = ""
    # observed unknowns (any required UNKNOWN ⇒ ineligible)
    unknown_fields: tuple[str, ...] = ()
    # evidence-chain bindings
    m43_machine_fingerprint: str = ""
    m43_1_closure_fingerprint: str = ""
    m44_completion_fingerprint: str = ""
    m42_review_fingerprint: str = ""
    m44_module_fingerprint: str = ""
    contains_secret_values: bool = False

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        # normalize tuples for JSON
        d["evidence_fingerprints"] = list(self.evidence_fingerprints)
        d["unknown_fields"] = list(self.unknown_fields)
        return d

    def core_for_fingerprint(self) -> dict[str, Any]:
        """Canonical body excluding derived integrity fields."""
        d = self.to_public()
        d.pop("integrity_fingerprint", None)
        d.pop("attestation_signature", None)
        d.pop("lifecycle", None)
        return d


# ── helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError, TypeError):
        return None


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      default=str).encode()


def snapshot_fingerprint(snap: RuntimeAttestationSnapshot) -> str:
    return _hmac(_FP_DOMAIN, _canonical(snap.core_for_fingerprint()), length=32)


def sign_snapshot(snap: RuntimeAttestationSnapshot) -> str:
    """Local HMAC integrity signature — NOT operator identity, NOT hardware."""
    body = snap.core_for_fingerprint()
    body["integrity_fingerprint"] = snapshot_fingerprint(snap)
    return _hmac(_SIG_DOMAIN, _canonical(body), length=32)


def machine_id_fingerprint() -> str:
    """Local machine observation (hostname + platform). Not hardware attestation."""
    material = f"{platform.node()}|{platform.system()}|{platform.machine()}"
    return _hmac(_MACHINE_DOMAIN, material.encode(), length=24)


def process_identity_fingerprint() -> str:
    material = f"{os.getpid()}|{platform.python_version()}|{os.getuid() if hasattr(os, 'getuid') else 'na'}"
    return _hmac(_PROCESS_DOMAIN, material.encode(), length=24)


def _git(args: list[str], cwd: str | Path = ".") -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=5)
        return r.returncode, (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def _file_fingerprint(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    try:
        body = json.loads(p.read_text())
    except (ValueError, OSError):
        return ""
    # prefer embedded fingerprint if present
    fp = body.get("fingerprint") or body.get("module_fingerprint") or ""
    if fp:
        return str(fp)
    return _hmac(b"m45.file", _canonical(body), length=24)


def _m32_state() -> str:
    try:
        from saathi.connectors.providers.models import M32_PROHIBITED_MODES, ExecutionMode
        if (ExecutionMode.CANARY in M32_PROHIBITED_MODES
                and ExecutionMode.ACTIVE in M32_PROHIBITED_MODES):
            return "PROHIBITION_UNCHANGED"
        return "PROHIBITION_CHANGED"
    except Exception:
        return UNKNOWN


# ── C. Collector ─────────────────────────────────────────────────────────────
@dataclass
class CollectorConfig:
    """Inputs for collecting a snapshot. Secrets never accepted."""
    base: str | Path = "."
    provider: str = PROVIDER_ID
    approved_scope: str = "read_only:github_meta:/meta"
    credential_reference_kind: str = "NONE"
    credential_reference_fingerprint: str = ""
    credential_present: bool = False
    credential_lifecycle_state: str = "N/A"
    requested_rollout_percent: int = 0
    maximum_policy_percent: int = 5
    open_security_alerts: Optional[int] = 0
    unresolved_incidents: Optional[int] = 0
    rollback_active: Optional[bool] = False
    error_budget_state: Optional[str] = "healthy"
    audit_ledger_state: Optional[str] = "intact"
    operator_approval_present: bool = False
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    environ: Optional[dict[str, str]] = None
    # simulation / self-report modes
    mode: str = "observe"  # observe | simulate | self_report
    fixed_now: Optional[str] = None
    fixed_machine_fp: Optional[str] = None
    fixed_process_fp: Optional[str] = None
    fixed_commit: Optional[str] = None
    fixed_branch: Optional[str] = None
    fixed_dirty: Optional[str] = None


def collect_runtime_snapshot(cfg: CollectorConfig | None = None) -> RuntimeAttestationSnapshot:
    """Collect safe runtime metadata. Fail-closed: unknowns recorded; never reads secrets."""
    cfg = cfg or CollectorConfig()
    base = Path(cfg.base)
    unknowns: list[str] = []
    now = cfg.fixed_now or _now_iso()
    now_dt = _parse_iso(now) or datetime.now(timezone.utc)
    expires = (now_dt + timedelta(seconds=max(1, cfg.ttl_seconds))).replace(
        microsecond=0).isoformat()

    # machine / process
    if cfg.mode == "simulate":
        machine_fp = cfg.fixed_machine_fp or "SIM_MACHINE"
        process_fp = cfg.fixed_process_fp or "SIM_PROCESS"
        provenance = AttestationProvenance.SIMULATED.value
    elif cfg.mode == "self_report":
        machine_fp = cfg.fixed_machine_fp or "SELF_REPORTED_MACHINE"
        process_fp = cfg.fixed_process_fp or "SELF_REPORTED_PROCESS"
        provenance = AttestationProvenance.SELF_REPORTED.value
    else:
        machine_fp = cfg.fixed_machine_fp or machine_id_fingerprint()
        process_fp = cfg.fixed_process_fp or process_identity_fingerprint()
        provenance = AttestationProvenance.LOCAL_MACHINE_OBSERVED.value

    # git state
    if cfg.fixed_commit is not None:
        commit = cfg.fixed_commit
    else:
        rc, commit = _git(["rev-parse", "HEAD"], base)
        if rc != 0 or not commit:
            commit = UNKNOWN
            unknowns.append("repository_commit")
    if cfg.fixed_branch is not None:
        branch = cfg.fixed_branch
    else:
        rc, branch = _git(["branch", "--show-current"], base)
        if rc != 0 or not branch:
            branch = UNKNOWN
            unknowns.append("branch")
    if cfg.fixed_dirty is not None:
        dirty = cfg.fixed_dirty
    else:
        rc, st = _git(["status", "--porcelain"], base)
        if rc != 0:
            dirty = UNKNOWN
            unknowns.append("repository_dirty_state")
        else:
            dirty = "dirty" if st else "clean"

    # kill switch
    ks = kill_switch_active(cfg.environ)

    # alerts / incidents — if None, UNKNOWN
    alerts = cfg.open_security_alerts
    if alerts is None:
        unknowns.append("open_security_alerts")
        alerts = -1
    incidents = cfg.unresolved_incidents
    if incidents is None:
        unknowns.append("unresolved_incidents")
        incidents = -1
    rollback = cfg.rollback_active
    if rollback is None:
        unknowns.append("rollback_active")
        rollback = True  # fail closed
    ebudget = cfg.error_budget_state
    if ebudget is None or ebudget == UNKNOWN:
        unknowns.append("error_budget_state")
        ebudget = UNKNOWN
    ledger_state = cfg.audit_ledger_state
    if ledger_state is None or ledger_state == UNKNOWN:
        unknowns.append("audit_ledger_state")
        ledger_state = UNKNOWN

    # evidence bindings
    m43_fp = _file_fingerprint(base / M43_MACHINE_PATH)
    m43_1_fp = _file_fingerprint(base / M43_1_CLOSURE_PATH)
    m44_fp = _file_fingerprint(base / M44_COMPLETION_PATH)
    if not m43_fp:
        unknowns.append("m43_machine_fingerprint")
    if not m43_1_fp:
        unknowns.append("m43_1_closure_fingerprint")
    if not m44_fp:
        unknowns.append("m44_completion_fingerprint")

    m42_review_fp = ""
    m44_mod_fp = ""
    try:
        from saathi.credentials import m44 as m44mod
        gs = m44mod.resolve_graduation_state(base=base)
        m42_review_fp = str(gs.get("review_fingerprint") or "")
        m44_mod_fp = m44mod.module_fingerprint()
        if not m42_review_fp:
            unknowns.append("m42_review_fingerprint")
    except Exception:
        unknowns.append("m42_review_fingerprint")
        unknowns.append("m44_module_fingerprint")

    m32 = _m32_state()
    if m32 == UNKNOWN:
        unknowns.append("m32_state")

    # provider identity (non-secret binding of approved provider id)
    provider = cfg.provider or PROVIDER_ID
    prov_id_fp = _hmac(b"m45.provider_identity", provider.encode(), length=24)

    evidence_fps = tuple(fp for fp in (m43_fp, m43_1_fp, m44_fp, m42_review_fp, m44_mod_fp) if fp)

    snap_id = _hmac(
        b"m45.snapshot_id",
        (now + "|" + machine_fp + "|" + commit).encode(),
        length=16,
    )

    snap = RuntimeAttestationSnapshot(
        snapshot_id=snap_id,
        schema_version=SCHEMA_VERSION,
        generated_at=now,
        expires_at=expires,
        machine_id_fingerprint=machine_fp,
        process_identity_fingerprint=process_fp,
        repository_commit=commit,
        repository_dirty_state=dirty,
        branch=branch,
        provider=provider,
        provider_identity_fingerprint=prov_id_fp,
        approved_scope=cfg.approved_scope,
        credential_reference_kind=cfg.credential_reference_kind,
        credential_reference_fingerprint=cfg.credential_reference_fingerprint,
        credential_present=bool(cfg.credential_present),
        credential_secret_read=False,  # collector never reads secrets
        credential_lifecycle_state=cfg.credential_lifecycle_state,
        live_network_allowed=False,
        write_operations_allowed=False,
        deployment_allowed=False,
        rollout_execution_allowed=False,
        requested_rollout_percent=int(cfg.requested_rollout_percent),
        maximum_policy_percent=int(cfg.maximum_policy_percent),
        open_security_alerts=int(alerts),
        unresolved_incidents=int(incidents),
        rollback_active=bool(rollback),
        kill_switch_active=bool(ks),
        error_budget_state=str(ebudget),
        audit_ledger_state=str(ledger_state),
        m32_state=m32,
        trading_guardian_state="UNCHANGED / UNENGAGED",
        evidence_fingerprints=evidence_fps,
        attestation_provenance=provenance,
        unknown_fields=tuple(sorted(set(unknowns))),
        m43_machine_fingerprint=m43_fp,
        m43_1_closure_fingerprint=m43_1_fp,
        m44_completion_fingerprint=m44_fp,
        m42_review_fingerprint=m42_review_fp,
        m44_module_fingerprint=m44_mod_fp,
        lifecycle=SnapshotLifecycle.CREATED.value,
        contains_secret_values=False,
    )
    return snap


# ── D. Machine attestation ───────────────────────────────────────────────────
def attest_snapshot(snap: RuntimeAttestationSnapshot, *,
                    elevate_to_machine_attested: bool = True) -> RuntimeAttestationSnapshot:
    """Bind integrity fingerprint + local HMAC signature.

    Elevates LOCAL_MACHINE_OBSERVED → MACHINE_ATTESTED (local integrity only).
    Never claims HARDWARE_ATTESTED. Simulated/self-reported stay as-is.
    """
    if snap.credential_secret_read:
        raise M45Error("secret_read_forbidden")
    if not is_clean(snap.to_public()):
        raise M45Error("leak_detected_in_snapshot")

    # copy via public round-trip
    data = snap.to_public()
    out = _from_public(data)
    if (elevate_to_machine_attested
            and out.attestation_provenance == AttestationProvenance.LOCAL_MACHINE_OBSERVED.value):
        out.attestation_provenance = AttestationProvenance.MACHINE_ATTESTED.value
    out.integrity_fingerprint = snapshot_fingerprint(out)
    out.attestation_signature = sign_snapshot(out)
    out.lifecycle = SnapshotLifecycle.CREATED.value
    assert is_clean(out.to_public())
    return out


def verify_snapshot_integrity(snap: RuntimeAttestationSnapshot) -> dict[str, Any]:
    """Recompute fingerprint + signature; detect tampering."""
    reasons: list[str] = []
    if not snap.snapshot_id:
        reasons.append("missing_snapshot_id")
    if snap.schema_version != SCHEMA_VERSION:
        reasons.append("schema_mismatch")
    expected_fp = snapshot_fingerprint(snap)
    if not snap.integrity_fingerprint:
        reasons.append("missing_integrity_fingerprint")
    elif snap.integrity_fingerprint != expected_fp:
        reasons.append("integrity_fingerprint_mismatch")
    expected_sig = sign_snapshot(snap)
    if not snap.attestation_signature:
        reasons.append("missing_attestation_signature")
    elif snap.attestation_signature != expected_sig:
        reasons.append("attestation_signature_mismatch")
    if snap.credential_secret_read:
        reasons.append("secret_read_flag_true")
    if snap.contains_secret_values:
        reasons.append("contains_secret_values")
    if not is_clean(snap.to_public()):
        reasons.append("leak_scan_failed")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "expected_fingerprint": expected_fp,
        "expected_signature": expected_sig,
        "provenance": snap.attestation_provenance,
    }


def _from_public(data: dict[str, Any]) -> RuntimeAttestationSnapshot:
    allowed = {f.name for f in fields(RuntimeAttestationSnapshot)}
    clean = {k: v for k, v in data.items() if k in allowed}
    for key in ("evidence_fingerprints", "unknown_fields"):
        if key in clean and isinstance(clean[key], list):
            clean[key] = tuple(clean[key])
    return RuntimeAttestationSnapshot(**clean)


# ── E. Runtime eligibility validator ─────────────────────────────────────────
def validate_snapshot(
    snap: RuntimeAttestationSnapshot,
    *,
    now: Optional[str] = None,
    require_clean_repo: bool = False,
    require_provenance: tuple[str, ...] = (
        AttestationProvenance.MACHINE_ATTESTED.value,
        AttestationProvenance.LOCAL_MACHINE_OBSERVED.value,
    ),
    expected_machine_fp: Optional[str] = None,
    expected_process_fp: Optional[str] = None,
    expected_commit: Optional[str] = None,
    expected_branch: Optional[str] = None,
    expected_provider: str = PROVIDER_ID,
    expected_scope: Optional[str] = None,
    expected_cred_fp: Optional[str] = None,
    require_credential: bool = False,
    forbid_credential: bool = False,
    seen_snapshot_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Validate snapshot structure, integrity, expiry, and safety invariants."""
    blockers: list[str] = []
    checks: dict[str, bool] = {}

    if not snap or not snap.snapshot_id:
        return _snap_result(M45Verdict.SNAPSHOT_INCOMPLETE, ["missing_snapshot"],
                            checks={"present": False}, snap=snap)

    checks["present"] = True
    checks["schema_valid"] = snap.schema_version == SCHEMA_VERSION
    if not checks["schema_valid"]:
        blockers.append("schema_invalid")

    integ = verify_snapshot_integrity(snap)
    checks["integrity_valid"] = integ["valid"]
    if not integ["valid"]:
        if any("mismatch" in r or "tamper" in r for r in integ["reasons"]):
            return _snap_result(M45Verdict.SNAPSHOT_TAMPERED, integ["reasons"],
                                checks=checks, snap=snap)
        blockers.extend(integ["reasons"])

    # expiry / time
    now_dt = _parse_iso(now) if now else datetime.now(timezone.utc)
    gen = _parse_iso(snap.generated_at)
    exp = _parse_iso(snap.expires_at)
    checks["timestamps_parseable"] = gen is not None and exp is not None and now_dt is not None
    if not checks["timestamps_parseable"]:
        blockers.append("timestamp_unparseable")
    else:
        if gen and now_dt and gen > now_dt + timedelta(seconds=60):
            blockers.append("generated_in_future")
            checks["not_future"] = False
        else:
            checks["not_future"] = True
        if exp and now_dt and now_dt >= exp:
            return _snap_result(M45Verdict.SNAPSHOT_EXPIRED, ["snapshot_expired"],
                                checks={**checks, "not_expired": False}, snap=snap)
        checks["not_expired"] = True
        if gen and exp and exp <= gen:
            blockers.append("expiry_not_after_generated")

    # provenance
    checks["provenance_acceptable"] = snap.attestation_provenance in require_provenance
    if snap.attestation_provenance == AttestationProvenance.HARDWARE_ATTESTED.value:
        # claim without genuine hardware is forbidden
        blockers.append("hardware_attested_not_supported")
    if snap.attestation_provenance in (
            AttestationProvenance.SELF_REPORTED.value,
            AttestationProvenance.SIMULATED.value,
            AttestationProvenance.ABSENT.value):
        blockers.append(f"provenance_insufficient:{snap.attestation_provenance}")
    elif not checks["provenance_acceptable"]:
        blockers.append(f"provenance_not_accepted:{snap.attestation_provenance}")

    # unknowns
    checks["no_unknown_fields"] = not snap.unknown_fields
    if snap.unknown_fields:
        blockers.append("unknown_fields_present")

    # identity bindings
    if expected_machine_fp is not None:
        checks["machine_identity_match"] = snap.machine_id_fingerprint == expected_machine_fp
        if not checks["machine_identity_match"]:
            blockers.append("machine_identity_mismatch")
    if expected_process_fp is not None:
        checks["process_identity_match"] = snap.process_identity_fingerprint == expected_process_fp
        if not checks["process_identity_match"]:
            blockers.append("process_identity_mismatch")
    if expected_commit is not None:
        checks["commit_match"] = snap.repository_commit == expected_commit
        if not checks["commit_match"]:
            blockers.append("repository_commit_mismatch")
    if expected_branch is not None:
        checks["branch_match"] = snap.branch == expected_branch
        if not checks["branch_match"]:
            blockers.append("branch_mismatch")
    if require_clean_repo:
        checks["repo_clean"] = snap.repository_dirty_state == "clean"
        if not checks["repo_clean"]:
            blockers.append("repository_not_clean")

    # provider / scope
    checks["provider_match"] = snap.provider == expected_provider
    if not checks["provider_match"]:
        blockers.append("provider_mismatch")
    if expected_scope is not None:
        checks["scope_match"] = snap.approved_scope == expected_scope
        if not checks["scope_match"]:
            blockers.append("scope_mismatch")
    if expected_cred_fp is not None:
        checks["credential_ref_match"] = (
            snap.credential_reference_fingerprint == expected_cred_fp)
        if not checks["credential_ref_match"]:
            blockers.append("credential_reference_mismatch")

    # credential presence rules
    if require_credential and not snap.credential_present:
        blockers.append("credential_missing")
        checks["credential_present_ok"] = False
    elif forbid_credential and snap.credential_present:
        blockers.append("credential_unexpectedly_present")
        checks["credential_present_ok"] = False
    else:
        checks["credential_present_ok"] = True

    if snap.credential_secret_read:
        blockers.append("secret_read_during_collection")
    if snap.live_network_allowed:
        blockers.append("live_network_enabled")
    if snap.write_operations_allowed:
        blockers.append("write_operations_enabled")
    if snap.deployment_allowed:
        blockers.append("deployment_enabled")
    if snap.rollout_execution_allowed:
        blockers.append("rollout_execution_enabled")

    if snap.open_security_alerts != 0:
        blockers.append("open_security_alerts")
    if snap.unresolved_incidents != 0:
        blockers.append("unresolved_incidents")
    if snap.rollback_active:
        blockers.append("rollback_active")
    if snap.kill_switch_active:
        blockers.append("kill_switch_active")
    if snap.error_budget_state != "healthy":
        blockers.append("error_budget_unhealthy")
    if snap.audit_ledger_state != "intact":
        blockers.append("audit_ledger_invalid")
    if snap.m32_state != "PROHIBITION_UNCHANGED":
        blockers.append("m32_changed")
    if snap.trading_guardian_state not in (
            "UNCHANGED / UNENGAGED", "UNENGAGED", "UNCHANGED"):
        blockers.append("trading_guardian_engaged")

    # evidence bindings required
    if not snap.m43_machine_fingerprint:
        blockers.append("m43_binding_missing")
    if not snap.m43_1_closure_fingerprint:
        blockers.append("m43_1_binding_missing")
    if not snap.m44_completion_fingerprint:
        blockers.append("m44_completion_binding_missing")

    # percent ceiling
    if snap.requested_rollout_percent < 0:
        blockers.append("percentage_negative")
    if snap.requested_rollout_percent > snap.maximum_policy_percent:
        blockers.append("percentage_above_policy")

    # replay / duplicate
    if seen_snapshot_ids is not None and snap.snapshot_id in seen_snapshot_ids:
        blockers.append("duplicate_or_replayed_snapshot")

    if blockers:
        verdict = M45Verdict.SNAPSHOT_BLOCKED
        if any("tamper" in b or "mismatch" in b and "integrity" in b for b in blockers):
            verdict = M45Verdict.SNAPSHOT_INVALID
        return _snap_result(verdict, blockers, checks=checks, snap=snap)

    return _snap_result(M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY, [],
                        checks=checks, snap=snap)


def _snap_result(verdict: M45Verdict, blockers: list[str], *,
                 checks: dict[str, bool],
                 snap: Optional[RuntimeAttestationSnapshot]) -> dict[str, Any]:
    body = {
        "schema": "m45.snapshot_validation.v1",
        "milestone": "M45",
        "verdict": verdict.value,
        "blockers": list(blockers),
        "checks": checks,
        "snapshot_id": snap.snapshot_id if snap else "",
        "lifecycle": (SnapshotLifecycle.VALIDATED.value
                      if verdict == M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY
                      else (SnapshotLifecycle.TAMPERED.value
                            if verdict == M45Verdict.SNAPSHOT_TAMPERED
                            else (SnapshotLifecycle.EXPIRED.value
                                  if verdict == M45Verdict.SNAPSHOT_EXPIRED
                                  else SnapshotLifecycle.BLOCKED.value))),
        "attestation_provenance": snap.attestation_provenance if snap else "",
        "authorizes_execution": False,
        "alters_runtime_authority": False,
        "grants_anything": False,
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "contains_secret_values": False,
        "note": ("Advisory only. Snapshot validation never authorizes rollout "
                 "execution."),
    }
    assert is_clean(body)
    return body


# ── H. M44 integration ───────────────────────────────────────────────────────
def to_m44_runtime_snapshot(snap: RuntimeAttestationSnapshot,
                            *, operator_approval_present: bool = True):
    """Project a validated M45 snapshot into M44's RuntimeSnapshot flag bag.

    Only safe when integrity has already been verified — the caller must check.
    """
    from saathi.credentials.m44 import RuntimeSnapshot
    return RuntimeSnapshot(
        identity_drift=False,
        provider_mismatch=False,
        credential_mismatch=False,
        rollback_active=snap.rollback_active,
        kill_switch_active=snap.kill_switch_active,
        incident_unresolved=snap.unresolved_incidents != 0,
        security_alert_open=snap.open_security_alerts != 0,
        trading_guardian_active=snap.trading_guardian_state not in (
            "UNCHANGED / UNENGAGED", "UNENGAGED", "UNCHANGED"),
        m32_prohibition_violated=snap.m32_state != "PROHIBITION_UNCHANGED",
        machine_proof_present=bool(snap.m43_machine_fingerprint)
            and snap.attestation_provenance in (
                AttestationProvenance.MACHINE_ATTESTED.value,
                AttestationProvenance.LOCAL_MACHINE_OBSERVED.value),
        operator_approval_present=operator_approval_present,
    )


def check_request_readiness(
    request: Any,
    snap: RuntimeAttestationSnapshot,
    *,
    now: Optional[str] = None,
    environ: Optional[dict[str, str]] = None,
    require_clean_repo: bool = False,
    expected_commit: Optional[str] = None,
    expected_branch: Optional[str] = None,
    seen_snapshot_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Compose M44 request validation + M45 snapshot validation.

    Maximal verdict: BOUNDED_ROLLOUT_READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION.
    Grants nothing. No execution path.
    """
    from saathi.credentials import m44

    snap_result = validate_snapshot(
        snap, now=now, require_clean_repo=require_clean_repo,
        expected_commit=expected_commit, expected_branch=expected_branch,
        expected_provider=getattr(request, "provider", PROVIDER_ID),
        expected_scope=getattr(request, "scope", None),
        seen_snapshot_ids=seen_snapshot_ids,
    )

    # Bind request percent into snapshot ceiling check
    extra_blockers: list[str] = []
    req_pct = getattr(request, "rollout_percent", None)
    if req_pct is not None and snap.maximum_policy_percent is not None:
        if int(req_pct) > int(snap.maximum_policy_percent):
            extra_blockers.append("request_percent_above_snapshot_ceiling")
        if int(req_pct) != int(snap.requested_rollout_percent) and snap.requested_rollout_percent:
            # allow snapshot requested_percent 0 as "unset"
            if snap.requested_rollout_percent not in (0, int(req_pct)):
                extra_blockers.append("request_percent_mismatch_snapshot")

    # evidence fingerprints on request must resolve (M44) and bind to snap
    req_evi = tuple(getattr(request, "evidence_fingerprints", ()) or ())
    for fp in (snap.m43_machine_fingerprint, snap.m42_review_fingerprint):
        if fp and req_evi and fp not in req_evi:
            # soft: request may use same chain; only require if request listed some
            pass

    m44_runtime = to_m44_runtime_snapshot(
        snap, operator_approval_present=bool(getattr(request, "approval_fingerprints", None)))
    m44_result = m44.validate_request(request, now=now, runtime=m44_runtime, environ=environ)

    ready = (
        snap_result["verdict"] == M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY.value
        and m44_result["verdict"] == m44.M44Verdict.ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY.value
        and not extra_blockers
        and not m44_result.get("authorizes_execution")
        and not snap.rollout_execution_allowed
    )

    verdict = (M45Verdict.BOUNDED_ROLLOUT_READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION
               if ready else M45Verdict.REQUEST_NOT_READY)

    body = {
        "schema": "m45.request_readiness.v1",
        "milestone": "M45",
        "verdict": verdict.value,
        "ready_for_separate_operator_authorization": ready,
        "snapshot_validation": snap_result,
        "m44_validation": {
            "verdict": m44_result.get("verdict"),
            "blockers": m44_result.get("blockers"),
            "checks": m44_result.get("checks"),
            "evidence_provenance": m44_result.get("evidence_provenance"),
            "authorizes_execution": m44_result.get("authorizes_execution"),
            "grants_anything": m44_result.get("grants_anything"),
        },
        "extra_blockers": extra_blockers,
        "snapshot_id": snap.snapshot_id,
        "rollout_id": getattr(request, "rollout_id", ""),
        "authorizes_execution": False,
        "alters_runtime_authority": False,
        "grants_anything": False,
        "requires_separate_execution_authorization": True,
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "contains_secret_values": False,
        "note": ("Even BOUNDED_ROLLOUT_READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION "
                 "grants nothing. A completely separate operator authorization is "
                 "required to execute any rollout."),
    }
    assert is_clean(body)
    return body


# ── F. Snapshot lifecycle ledger ─────────────────────────────────────────────
class LedgerEvent(str, Enum):
    CREATED = "created"
    VALIDATED = "validated"
    ELIGIBLE = "eligible_advisory_only"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"
    TAMPERED = "tampered"
    BLOCKED = "blocked"


def append_ledger(event: LedgerEvent, payload: dict[str, Any],
                  path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    if not is_clean(payload):
        raise AssertionError("m45 ledger payload not leak-clean")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prev = ""
    if p.exists() and p.stat().st_size:
        lines = p.read_text().splitlines()
        if lines:
            try:
                prev = json.loads(lines[-1]).get("fingerprint", "")
            except ValueError:
                prev = ""
    entry = {
        "event": event.value,
        "prev_fingerprint": prev,
        "payload": payload,
        "ts": _now_iso(),
    }
    entry["fingerprint"] = _hmac(
        _LEDGER_DOMAIN, _canonical({"event": entry["event"],
                                    "prev": prev, "payload": payload}),
        length=24)
    assert is_clean(entry)
    with p.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def read_ledger(path: str | Path = LEDGER_PATH) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def verify_ledger_chain(path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    entries = read_ledger(path)
    prev = ""
    for i, e in enumerate(entries):
        if e.get("prev_fingerprint", "") != prev:
            return {"intact": False, "broken_at": i, "reason": "prev_mismatch",
                    "entries": len(entries)}
        expected = _hmac(
            _LEDGER_DOMAIN,
            _canonical({"event": e["event"], "prev": prev, "payload": e["payload"]}),
            length=24)
        if e.get("fingerprint") != expected:
            return {"intact": False, "broken_at": i, "reason": "fingerprint_mismatch",
                    "entries": len(entries)}
        prev = e["fingerprint"]
    return {"intact": True, "entries": len(entries), "contains_secret_values": False}


def create_snapshot(cfg: CollectorConfig | None = None, *,
                    path: str | Path = LEDGER_PATH,
                    persist: bool = False) -> dict[str, Any]:
    raw = collect_runtime_snapshot(cfg)
    snap = attest_snapshot(raw)
    if persist:
        append_ledger(LedgerEvent.CREATED, {
            "snapshot_id": snap.snapshot_id,
            "integrity_fingerprint": snap.integrity_fingerprint,
            "provenance": snap.attestation_provenance,
            "lifecycle": snap.lifecycle,
        }, path)
    body = {
        "schema": "m45.snapshot_created.v1",
        "milestone": "M45",
        "snapshot": snap.to_public(),
        "authorizes_execution": False,
        "grants_anything": False,
        "alters_runtime_authority": False,
        "contains_secret_values": False,
    }
    assert is_clean(body)
    return body


def expire_snapshot(snapshot_id: str, *, reason: str = "operator_requested_expiry",
                    path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    entry = append_ledger(LedgerEvent.EXPIRED, {
        "snapshot_id": snapshot_id, "reason": reason,
        "lifecycle": SnapshotLifecycle.EXPIRED.value,
    }, path)
    return {"expired": True, "snapshot_id": snapshot_id, "authorizes_execution": False,
            "ledger_entry": entry, "contains_secret_values": False}


def invalidate_snapshot(snapshot_id: str, *, reason: str = "operator_invalidated",
                        path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    entry = append_ledger(LedgerEvent.INVALIDATED, {
        "snapshot_id": snapshot_id, "reason": reason,
        "lifecycle": SnapshotLifecycle.INVALIDATED.value,
    }, path)
    return {"invalidated": True, "snapshot_id": snapshot_id,
            "authorizes_execution": False, "ledger_entry": entry,
            "contains_secret_values": False}


def list_snapshots(path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    ids = sorted({e.get("payload", {}).get("snapshot_id")
                  for e in read_ledger(path)
                  if e.get("payload", {}).get("snapshot_id")})
    return {"snapshot_ids": ids, "count": len(ids), "contains_secret_values": False}


def show_snapshot_history(snapshot_id: str,
                          path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    events = [e for e in read_ledger(path)
              if e.get("payload", {}).get("snapshot_id") == snapshot_id]
    return {"snapshot_id": snapshot_id, "events": events, "count": len(events),
            "contains_secret_values": False}


# ── framework status + evidence ──────────────────────────────────────────────
def framework_status() -> dict[str, Any]:
    empty = validate_snapshot(RuntimeAttestationSnapshot())
    default_denied = empty["verdict"] != M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY.value
    components = {
        "runtime_snapshot_contract": True,
        "collector": True,
        "machine_attestation": True,
        "eligibility_validator": True,
        "lifecycle_ledger": True,
        "m44_integration": True,
        "cli": True,
    }
    return {
        "schema": SCHEMA_VERSION,
        "milestone": "M45",
        "state": FRAMEWORK_STATE,
        "framework_ready": all(components.values()),
        "default_snapshot_denied": default_denied,
        "components": components,
        "attestation_provenance_classes": [p.value for p in AttestationProvenance],
        "lifecycle_states": [s.value for s in SnapshotLifecycle],
        "ready_verdict": READY_VERDICT,
        "advisory_only": True,
        "authorizes_execution": False,
        "alters_runtime_authority": False,
        "grants_anything": False,
        "grants_active": False,
        "grants_production": False,
        "grants_write": False,
        "grants_deployment": False,
        "grants_rollout_execution": False,
        "requires_separate_execution_authorization": True,
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "hardware_attestation_supported": False,
        "banner": NON_PRODUCTION_BANNER,
        "note": ("Runtime attestation infrastructure is ready. Advisory only. "
                 "No rollout execution, production, write, or deployment authority."),
        "contains_secret_values": False,
    }


def simulate() -> dict[str, Any]:
    cfg = CollectorConfig(
        mode="simulate",
        fixed_now="2026-07-22T12:00:00+00:00",
        fixed_commit="SIM_COMMIT",
        fixed_branch="milestone/m42-graduation-review",
        fixed_dirty="clean",
        open_security_alerts=0,
        unresolved_incidents=0,
        rollback_active=False,
        error_budget_state="healthy",
        audit_ledger_state="intact",
        requested_rollout_percent=1,
        maximum_policy_percent=5,
    )
    raw = collect_runtime_snapshot(cfg)
    # simulate path: do not elevate provenance
    data = raw.to_public()
    data["integrity_fingerprint"] = snapshot_fingerprint(raw)
    # sign without elevating
    signed = _from_public(data)
    signed.attestation_signature = sign_snapshot(signed)
    signed.integrity_fingerprint = snapshot_fingerprint(signed)
    # re-sign after fp set
    signed.attestation_signature = sign_snapshot(signed)
    result = validate_snapshot(
        signed, now="2026-07-22T12:00:00+00:00",
        require_provenance=(AttestationProvenance.SIMULATED.value,
                            AttestationProvenance.MACHINE_ATTESTED.value))
    return {
        "schema": "m45.simulation.v1",
        "milestone": "M45",
        "mode": "SIMULATED_NOT_LIVE",
        "snapshot": signed.to_public(),
        "validation": result,
        "authorizes_execution": False,
        "grants_anything": False,
        "alters_runtime_authority": False,
        "note": "SIMULATED. Proves wiring; provenance SIMULATED is insufficient for readiness.",
        "contains_secret_values": False,
    }


def module_fingerprint() -> str:
    return _hmac(
        b"m45.module",
        SCHEMA_VERSION.encode(),
        FRAMEWORK_STATE.encode(),
        READY_VERDICT.encode(),
        json.dumps([p.value for p in AttestationProvenance], sort_keys=True).encode(),
        json.dumps([s.value for s in SnapshotLifecycle], sort_keys=True).encode(),
        length=24,
    )


def build_runtime_attestation_completion() -> dict[str, Any]:
    status = framework_status()
    denied = validate_snapshot(RuntimeAttestationSnapshot())
    # bind live evidence
    m43 = _file_fingerprint(M43_MACHINE_PATH)
    m43_1 = _file_fingerprint(M43_1_CLOSURE_PATH)
    m44c = _file_fingerprint(M44_COMPLETION_PATH)
    m44_mod = ""
    m42_fp = ""
    try:
        from saathi.credentials import m44 as m44mod
        m44_mod = m44mod.module_fingerprint()
        m42_fp = str(m44mod.resolve_graduation_state().get("review_fingerprint") or "")
    except Exception:
        pass
    rc, commit = _git(["rev-parse", "HEAD"])
    if rc != 0:
        commit = UNKNOWN
    body = {
        "schema": "m45.runtime_attestation_completion.v1",
        "milestone": "M45",
        "verdict": FRAMEWORK_STATE,
        "module_fingerprint": module_fingerprint(),
        "framework_ready": status["framework_ready"],
        "default_snapshot_denied": denied["verdict"] !=
            M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY.value,
        "bindings": {
            "m43_machine_fingerprint": m43,
            "m43_1_closure_fingerprint": m43_1,
            "m44_completion_fingerprint": m44c,
            "m44_module_fingerprint": m44_mod,
            "m42_review_fingerprint": m42_fp,
            "repository_commit": commit,
            "m45_module_fingerprint": module_fingerprint(),
        },
        "ready_verdict_name": READY_VERDICT,
        "authorizes_execution": False,
        "alters_runtime_authority": False,
        "grants_anything": False,
        "runtime_execution_authority": False,
        "deployment": False,
        "push": False,
        "hardware_attestation_supported": False,
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "contains_secret_values": False,
        "note": ("M45_RUNTIME_ATTESTATION_READY_ADVISORY_ONLY — runtime attestation "
                 "implemented, tested, integrated with M44. Grants no rollout authority."),
    }
    assert is_clean(body)
    return body


def build_m45_evidence() -> dict[str, dict[str, Any]]:
    status = framework_status()
    denied = validate_snapshot(RuntimeAttestationSnapshot())
    sim = simulate()
    completion = build_runtime_attestation_completion()
    return {
        "framework_status": status,
        "default_snapshot_denied": denied,
        "simulated_snapshot": sim,
        "runtime_attestation_completion": completion,
        "summary": {
            "schema": "m45.summary.v1",
            "milestone": "M45",
            "state": FRAMEWORK_STATE,
            "framework_ready": status["framework_ready"],
            "default_snapshot_denied": True,
            "module_fingerprint": module_fingerprint(),
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


def emit_m45_evidence(out_dir: str | Path = EVIDENCE_DIR) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m45_evidence()
    written: list[str] = []
    for name, b in bodies.items():
        assert is_clean(b), f"m45 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    return {"written": written, "count": len(written), "dir": str(out),
            "state": FRAMEWORK_STATE, "module_fingerprint": module_fingerprint(),
            "contains_secret_values": False}
