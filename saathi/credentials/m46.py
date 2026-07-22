"""M46 — Separately Authorized Bounded Read-Only Execution Canary.

Composition-only controller above M39–M45. Supports exactly one execution class:

    READ_ONLY_DISPOSABLE_CANARY

It does NOT activate production, enable writes, deploy, expand scope, engage
Trading Guardian, or grant ACTIVE / autonomous / general rollout authority.

Offline maximal state (this milestone's default completion):

    M46_IMPLEMENTED_AWAITING_OPERATOR_AUTHORIZATION

A live canary is intentionally inaccessible until a separate operator
authorization supplies every live prerequisite. Even a successful live canary
stops at CANARY_COMPLETED_PENDING_REVOCATION and never implies production.

Composes:
  * M39 — SecretHandle live session, kill switch, provider allowlist, HMAC;
  * M41/M43 — bounded canary / machine-proof patterns (by reference);
  * M44 — RolloutRequest validation;
  * M45 — RuntimeAttestationSnapshot validation + readiness projection.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.credentials.leakscan import is_clean
from saathi.credentials.m39 import (
    ALLOWED_ENDPOINTS,
    ALLOWED_METHODS,
    AUTHORITIES,
    PROVIDER_ID,
    _hmac,
    kill_switch_active,
)

SCHEMA_VERSION = "m46.bounded_canary.v1"
_FP_DOMAIN = b"saathi.m46.approval.domain.v1"
_PLAN_DOMAIN = b"saathi.m46.execution_plan.domain.v1"
_LEDGER_DOMAIN = b"saathi.m46.ledger.domain.v1"
_EXEC_DOMAIN = b"saathi.m46.execution.domain.v1"

FRAMEWORK_STATE = "M46_IMPLEMENTED_AWAITING_OPERATOR_AUTHORIZATION"
EXECUTION_CLASS = "READ_ONLY_DISPOSABLE_CANARY"
MILESTONE = "M46"

MAX_ROLLOUT_PERCENT = 1
MAX_CALLS = 3
MAX_DURATION_SECONDS = 120
DEFAULT_ERROR_BUDGET = 0
LIVE_ENV_GATE = "SAATHI_M46_LIVE_GATE"

LEDGER_PATH = "docs/evidence/m46/execution_ledger.jsonl"
# Durable one-shot consume registry (operator-local; gitignored *.local.jsonl).
CONSUMED_LEDGER_PATH = "docs/evidence/m46/consumed_authorization.local.jsonl"
EVIDENCE_DIR = "docs/evidence/m46"
APPROVAL_TEMPLATE_PATH = "docs/m46/operator_canary_approval.template.json"
APPROVAL_LOCAL_GLOB = "docs/m46/*.local.json"

# Exact endpoint policy (Model A): IDENTITY_READ binds only to GET /user.
IDENTITY_READ_ENDPOINT = "user"
# Historical M46 canary (approval meta + live /user) classification.
HISTORICAL_ENDPOINT_BINDING_EXCEPTION = "M46_ENDPOINT_BINDING_EXCEPTION"

M43_MACHINE_PATH = "docs/evidence/m43/machine_verified_canary_completion.json"
M43_1_CLOSURE_PATH = "docs/evidence/m43_1/final_cleanup_closure.json"
M44_COMPLETION_PATH = "docs/evidence/m44/framework_completion.json"
M45_COMPLETION_PATH = "docs/evidence/m45/runtime_attestation_completion.json"

NON_PRODUCTION_BANNER = (
    "M46 BOUNDED READ-ONLY DISPOSABLE CANARY\n"
    "NON-PRODUCTION\n"
    "READ-ONLY\n"
    "FAIL-CLOSED\n"
    "DENY-BY-DEFAULT\n"
    "SEPARATE OPERATOR AUTHORIZATION REQUIRED\n"
    "GRANTS NOTHING\n"
    "NO ACTIVE\n"
    "NO PRODUCTION\n"
    "NO WRITE\n"
    "NO DEPLOYMENT\n"
    "NO AUTONOMOUS EXECUTION\n"
    "NO TRADING GUARDIAN\n"
    "ROLLOUT CEILING 1%\n"
    "TRADING GUARDIAN UNENGAGED"
)

FRAMEWORK_AUTHORITY_STATE = {
    "active": "NOT GRANTED",
    "production": "NOT AUTHORIZED",
    "write": "NOT GRANTED",
    "deployment": "NOT GRANTED",
    "rollout_execution": "NOT GRANTED (awaiting separate operator authorization)",
    "autonomous_execution": "NOT GRANTED",
    "scope_expansion": "FORBIDDEN",
    "trading_guardian": "UNENGAGED",
    "framework": "IMPLEMENTED (AWAITING OPERATOR AUTHORIZATION)",
}

M46_ACK_TOKENS = (
    "I_AUTHORIZE_M46_READ_ONLY_DISPOSABLE_CANARY",
    "I_CONFIRM_M44_REQUEST_AND_M45_SNAPSHOT_REVIEWED",
    "I_CONFIRM_ROLLOUT_CEILING_ONE_PERCENT",
    "I_CONFIRM_NO_WRITE_NO_DEPLOY_NO_PRODUCTION",
    "I_CONFIRM_EXTERNAL_REVOCATION_AND_LOCAL_CLEANUP_REQUIRED",
    "I_CONFIRM_SUCCESS_GRANTS_NOTHING",
    "I_CONFIRM_TRADING_GUARDIAN_REMAINS_UNENGAGED",
    "I_ACCEPT_ACCOUNTABILITY_FOR_THIS_BOUNDED_CANARY",
)


class ExecutionState(str, Enum):
    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVAL_VALIDATED = "APPROVAL_VALIDATED"
    PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
    READY_FOR_ONE_COMMAND_LIVE_GATE = "READY_FOR_ONE_COMMAND_LIVE_GATE"
    CANARY_RUNNING = "CANARY_RUNNING"
    CANARY_COMPLETED_PENDING_REVOCATION = "CANARY_COMPLETED_PENDING_REVOCATION"
    REVOCATION_VERIFIED_PENDING_CLEANUP = "REVOCATION_VERIFIED_PENDING_CLEANUP"
    CLOSED_ADVISORY_ONLY = "CLOSED_ADVISORY_ONLY"
    ABORTED = "ABORTED"
    ROLLED_BACK = "ROLLED_BACK"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class M46Verdict(str, Enum):
    DENIED = "M46_DENIED"
    BLOCKED = "M46_BLOCKED"
    AWAITING_OPERATOR_AUTHORIZATION = "M46_IMPLEMENTED_AWAITING_OPERATOR_AUTHORIZATION"
    PREFLIGHT_PASSED = "M46_PREFLIGHT_PASSED"
    READY_FOR_ONE_COMMAND_LIVE_GATE = "M46_READY_FOR_ONE_COMMAND_LIVE_GATE"
    SIMULATED_NOT_LIVE = "M46_SIMULATED_NOT_LIVE"
    CANARY_COMPLETED_PENDING_REVOCATION = "M46_CANARY_COMPLETED_PENDING_EXTERNAL_REVOCATION"
    REVOCATION_VERIFIED_PENDING_CLEANUP = "M46_REVOCATION_VERIFIED_PENDING_CLEANUP"
    CLOSED_ADVISORY_ONLY = "M46_CLOSED_ADVISORY_ONLY"
    ABORTED = "M46_ABORTED"
    ROLLED_BACK = "M46_ROLLED_BACK"
    FAILED = "M46_FAILED"


class M46Error(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


# ── helpers ──────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError, TypeError):
        return None


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def _file_fp(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    try:
        body = json.loads(p.read_text())
    except (ValueError, OSError):
        return ""
    return str(body.get("fingerprint") or body.get("module_fingerprint")
               or _hmac(b"m46.file", _canonical(body), length=24))


def _git_head(base: str | Path = ".") -> str:
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(base),
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _m32_ok() -> bool:
    try:
        from saathi.connectors.providers.models import M32_PROHIBITED_MODES, ExecutionMode
        return (ExecutionMode.CANARY in M32_PROHIBITED_MODES
                and ExecutionMode.ACTIVE in M32_PROHIBITED_MODES)
    except Exception:
        return False


# ── B. Approval record ───────────────────────────────────────────────────────
REQUIRED_APPROVAL_FIELDS = (
    "approval_id", "milestone", "operator_id", "issued_at", "expires_at",
    "provider", "provider_identity_fingerprint",
    "credential_reference_kind", "credential_reference_locator_fingerprint",
    "request_id", "rollout_id",
    "allowed_operation", "allowed_endpoint",
    "maximum_calls", "maximum_duration_seconds", "rollout_percent",
    "read_only", "writes_allowed", "deployment_allowed", "production_allowed",
    "autonomous_execution_allowed", "trading_guardian_allowed",
    "rollback_conditions", "kill_switch_owner", "incident_owner",
    "acknowledgements", "approval_integrity_fingerprint",
)


def approval_core(record: dict[str, Any]) -> dict[str, Any]:
    """Canonical body excluding the integrity fingerprint itself."""
    return {k: record.get(k) for k in REQUIRED_APPROVAL_FIELDS
            if k != "approval_integrity_fingerprint"}


def approval_fingerprint(record: dict[str, Any]) -> str:
    return _hmac(_FP_DOMAIN, _canonical(approval_core(record)), length=32)


def sign_approval(record: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    out["approval_integrity_fingerprint"] = approval_fingerprint(out)
    out["contains_secret_values"] = False
    return out


def approval_template() -> dict[str, Any]:
    """Operator-fill template — intentionally incomplete (deny-by-default)."""
    return {
        "approval_id": "",
        "milestone": MILESTONE,
        "operator_id": "",
        "issued_at": "",
        "expires_at": "",
        "provider": PROVIDER_ID,
        "provider_identity_fingerprint": "",
        "credential_reference_kind": "OS_KEYCHAIN_REFERENCE",
        "credential_reference_locator_fingerprint": "",
        "request_id": "",
        "rollout_id": "",
        "allowed_operation": "IDENTITY_READ",
        "allowed_endpoint": IDENTITY_READ_ENDPOINT,
        "maximum_calls": 1,
        "maximum_duration_seconds": 60,
        "rollout_percent": 1,
        "read_only": True,
        "writes_allowed": False,
        "deployment_allowed": False,
        "production_allowed": False,
        "autonomous_execution_allowed": False,
        "trading_guardian_allowed": False,
        "rollback_conditions": [
            "identity_mismatch", "provider_changed", "unexpected_response",
            "error_budget_exceeded", "kill_switch", "security_alert",
            "manual_operator_stop",
        ],
        "kill_switch_owner": "",
        "incident_owner": "",
        "acknowledgements": [],
        "approval_integrity_fingerprint": "",
        "_required_acknowledgement_tokens": list(M46_ACK_TOKENS),
        "_operator_fill_fields": [
            "approval_id", "operator_id", "issued_at", "expires_at",
            "provider_identity_fingerprint",
            "credential_reference_locator_fingerprint",
            "request_id", "rollout_id", "kill_switch_owner", "incident_owner",
            "acknowledgements", "approval_integrity_fingerprint",
        ],
        "_constraints": {
            "execution_class": EXECUTION_CLASS,
            "maximum_rollout_percent": MAX_ROLLOUT_PERCENT,
            "maximum_calls": MAX_CALLS,
            "writes": "forbidden",
            "deployment": "forbidden",
            "production": "forbidden",
            "trading_guardian": "forbidden",
            "note": "Template only. Not a valid approval. Sign after filling.",
        },
        "contains_secret_values": False,
    }


def validate_approval(
    record: Optional[dict[str, Any]],
    *,
    now: Optional[str] = None,
    seen_approval_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Deny-by-default M46 approval validation. No raw secrets allowed."""
    blockers: list[str] = []
    checks: dict[str, bool] = {}
    if not isinstance(record, dict) or not record:
        return _approval_result(False, ["approval_absent"], checks={"present": False})

    checks["present"] = True
    if not is_clean(record):
        return _approval_result(False, ["leak_detected_in_approval"], checks=checks)

    missing = [f for f in REQUIRED_APPROVAL_FIELDS if f not in record or record.get(f) in (None, "")]
    # allow empty lists? acknowledgements empty is missing content
    if record.get("acknowledgements") in (None, [], ()):
        if "acknowledgements" not in missing:
            missing.append("acknowledgements")
    checks["all_fields_present"] = not missing
    if missing:
        blockers.extend(f"missing:{m}" for m in missing)

    if record.get("milestone") != MILESTONE:
        blockers.append("wrong_milestone")
    checks["milestone_ok"] = record.get("milestone") == MILESTONE

    if record.get("provider") != PROVIDER_ID:
        blockers.append("wrong_provider")
    checks["provider_ok"] = record.get("provider") == PROVIDER_ID

    if record.get("read_only") is not True:
        blockers.append("read_only_not_true")
    for flag, name in (
        ("writes_allowed", "writes_enabled"),
        ("deployment_allowed", "deployment_enabled"),
        ("production_allowed", "production_enabled"),
        ("autonomous_execution_allowed", "autonomous_execution_enabled"),
        ("trading_guardian_allowed", "trading_guardian_enabled"),
    ):
        if record.get(flag) is True:
            blockers.append(name)
        checks[f"{flag}_false"] = record.get(flag) is False

    # percent / budgets
    try:
        pct = int(record.get("rollout_percent"))
    except (TypeError, ValueError):
        pct = -1
        blockers.append("rollout_percent_invalid")
    if pct < 1 or pct > MAX_ROLLOUT_PERCENT:
        blockers.append("rollout_above_ceiling")
    checks["rollout_percent_ok"] = 1 <= pct <= MAX_ROLLOUT_PERCENT

    try:
        calls = int(record.get("maximum_calls"))
    except (TypeError, ValueError):
        calls = -1
    if calls < 1 or calls > MAX_CALLS:
        blockers.append("calls_above_budget")
    checks["calls_ok"] = 1 <= calls <= MAX_CALLS

    try:
        dur = int(record.get("maximum_duration_seconds"))
    except (TypeError, ValueError):
        dur = -1
    if dur < 1 or dur > MAX_DURATION_SECONDS:
        blockers.append("duration_above_budget")
    checks["duration_ok"] = 1 <= dur <= MAX_DURATION_SECONDS

    endpoint = str(record.get("allowed_endpoint") or "").lstrip("/")
    if endpoint not in ALLOWED_ENDPOINTS and endpoint not in ("user", "meta"):
        blockers.append("endpoint_not_allowlisted")
    checks["endpoint_ok"] = endpoint in ALLOWED_ENDPOINTS or endpoint in ("user", "meta")

    op = str(record.get("allowed_operation") or "")
    if op not in ("IDENTITY_READ", "METADATA_READ", "PUBLIC_DATA_READ"):
        blockers.append("operation_not_read_only")
    checks["operation_ok"] = op in ("IDENTITY_READ", "METADATA_READ", "PUBLIC_DATA_READ")
    # Model A: IDENTITY_READ requires exact endpoint user (no silent meta→user map).
    if op == "IDENTITY_READ" and endpoint != IDENTITY_READ_ENDPOINT:
        blockers.append("identity_read_requires_endpoint_user")
        checks["identity_endpoint_exact"] = False
    else:
        checks["identity_endpoint_exact"] = (
            op != "IDENTITY_READ" or endpoint == IDENTITY_READ_ENDPOINT
        )

    # acks
    have = set(record.get("acknowledgements") or [])
    missing_acks = [a for a in M46_ACK_TOKENS if a not in have]
    checks["acknowledgements_complete"] = not missing_acks
    if missing_acks:
        blockers.append("acknowledgements_incomplete")

    # expiry
    now_dt = _parse_iso(now) if now else datetime.now(timezone.utc)
    issued = _parse_iso(record.get("issued_at") or "")
    exp = _parse_iso(record.get("expires_at") or "")
    checks["timestamps_parseable"] = issued is not None and exp is not None
    if not checks["timestamps_parseable"]:
        blockers.append("timestamp_unparseable")
    else:
        if now_dt and exp and now_dt >= exp:
            blockers.append("approval_expired")
        if issued and exp and exp <= issued:
            blockers.append("expiry_not_after_issued")
        if issued and now_dt and issued > now_dt + timedelta(seconds=120):
            blockers.append("issued_in_future")

    # integrity
    expected = approval_fingerprint(record)
    got = str(record.get("approval_integrity_fingerprint") or "")
    checks["integrity_valid"] = bool(got) and got == expected
    if not got:
        blockers.append("approval_unsigned")
    elif got != expected:
        blockers.append("approval_tampered")

    # reuse
    aid = str(record.get("approval_id") or "")
    if seen_approval_ids is not None and aid in seen_approval_ids:
        blockers.append("approval_reused")

    # owners required non-empty when other fields present
    if not str(record.get("operator_id") or "").strip() and "missing:operator_id" not in blockers:
        if "operator_id" not in (record or {}):
            pass
        elif not str(record.get("operator_id") or "").strip():
            blockers.append("wrong_operator")

    valid = not blockers
    return _approval_result(valid, blockers, checks=checks,
                            approval_id=aid, fingerprint=got or expected)


def _approval_result(valid: bool, blockers: list[str], *, checks: dict[str, bool],
                     approval_id: str = "", fingerprint: str = "") -> dict[str, Any]:
    body = {
        "schema": "m46.approval_validation.v1",
        "milestone": MILESTONE,
        "valid": valid,
        "blockers": list(blockers),
        "checks": checks,
        "approval_id": approval_id,
        "fingerprint": fingerprint,
        "authorizes_execution": False,
        "grants_anything": False,
        "contains_secret_values": False,
        "note": "Approval validation only. Never executes.",
    }
    assert is_clean(body)
    return body


# ── C. Execution plan ────────────────────────────────────────────────────────
@dataclass
class ExecutionPlan:
    execution_id: str = ""
    schema_version: str = SCHEMA_VERSION
    execution_class: str = EXECUTION_CLASS
    state: str = ExecutionState.DRAFT.value
    approval_fingerprint: str = ""
    m44_request_fingerprint: str = ""
    m45_snapshot_fingerprint: str = ""
    m43_machine_proof_fingerprint: str = ""
    m43_1_closure_fingerprint: str = ""
    provider: str = PROVIDER_ID
    expected_identity_fingerprint: str = ""
    endpoint: str = "meta"
    exact_read_only_action: str = "GET /meta"
    maximum_call_count: int = 1
    maximum_duration_seconds: int = 60
    rollout_percentage: int = 1
    error_budget: int = DEFAULT_ERROR_BUDGET
    cleanup_requirements: tuple[str, ...] = (
        "external_credential_revocation",
        "local_reference_removal",
        "machine_verify_401",
        "machine_verify_reference_absent",
    )
    external_revocation_required: bool = True
    local_reference_removal_required: bool = True
    rollback_triggers: tuple[str, ...] = (
        "identity_mismatch", "provider_changed", "unexpected_response",
        "error_budget_exceeded", "kill_switch", "security_alert",
        "manual_operator_stop",
    )
    no_write_assertion: bool = True
    no_deploy_assertion: bool = True
    no_production_assertion: bool = True
    no_trading_guardian_assertion: bool = True
    created_at: str = ""
    plan_integrity_fingerprint: str = ""
    contains_secret_values: bool = False

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        d["cleanup_requirements"] = list(self.cleanup_requirements)
        d["rollback_triggers"] = list(self.rollback_triggers)
        return d

    def core(self) -> dict[str, Any]:
        d = self.to_public()
        d.pop("plan_integrity_fingerprint", None)
        d.pop("state", None)
        return d


def plan_fingerprint(plan: ExecutionPlan) -> str:
    return _hmac(_PLAN_DOMAIN, _canonical(plan.core()), length=32)


def sign_plan(plan: ExecutionPlan) -> ExecutionPlan:
    data = plan.to_public()
    out = _plan_from_public(data)
    out.plan_integrity_fingerprint = plan_fingerprint(out)
    return out


def _plan_from_public(data: dict[str, Any]) -> ExecutionPlan:
    allowed = {f.name for f in fields(ExecutionPlan)}
    clean = {k: v for k, v in data.items() if k in allowed}
    for key in ("cleanup_requirements", "rollback_triggers"):
        if key in clean and isinstance(clean[key], list):
            clean[key] = tuple(clean[key])
    return ExecutionPlan(**clean)


def verify_plan_integrity(plan: ExecutionPlan) -> dict[str, Any]:
    reasons: list[str] = []
    expected = plan_fingerprint(plan)
    if not plan.plan_integrity_fingerprint:
        reasons.append("missing_plan_fingerprint")
    elif plan.plan_integrity_fingerprint != expected:
        reasons.append("plan_tampered")
    if plan.execution_class != EXECUTION_CLASS:
        reasons.append("wrong_execution_class")
    if plan.rollout_percentage > MAX_ROLLOUT_PERCENT:
        reasons.append("rollout_above_ceiling")
    if not plan.no_write_assertion or not plan.no_deploy_assertion:
        reasons.append("unsafe_assertions")
    if not plan.no_production_assertion or not plan.no_trading_guardian_assertion:
        reasons.append("unsafe_authority_assertions")
    if not is_clean(plan.to_public()):
        reasons.append("leak_detected")
    return {"valid": not reasons, "reasons": reasons,
            "expected_fingerprint": expected, "contains_secret_values": False}


def create_plan(
    *,
    approval: dict[str, Any],
    m44_request_fingerprint: str,
    m45_snapshot_fingerprint: str,
    m43_machine_proof_fingerprint: str = "",
    m43_1_closure_fingerprint: str = "",
    expected_identity_fingerprint: str = "",
) -> ExecutionPlan:
    """Build a signed execution plan from an approval + evidence bindings."""
    appr_fp = str(approval.get("approval_integrity_fingerprint") or approval_fingerprint(approval))
    eid = _hmac(_EXEC_DOMAIN, (appr_fp + "|" + m44_request_fingerprint + "|"
                               + m45_snapshot_fingerprint).encode(), length=16)
    plan = ExecutionPlan(
        execution_id=eid,
        approval_fingerprint=appr_fp,
        m44_request_fingerprint=m44_request_fingerprint,
        m45_snapshot_fingerprint=m45_snapshot_fingerprint,
        m43_machine_proof_fingerprint=m43_machine_proof_fingerprint or _file_fp(M43_MACHINE_PATH),
        m43_1_closure_fingerprint=m43_1_closure_fingerprint or _file_fp(M43_1_CLOSURE_PATH),
        provider=str(approval.get("provider") or PROVIDER_ID),
        expected_identity_fingerprint=expected_identity_fingerprint or str(
            approval.get("provider_identity_fingerprint") or ""),
        endpoint=str(approval.get("allowed_endpoint") or IDENTITY_READ_ENDPOINT).lstrip("/"),
        exact_read_only_action=(
            f"GET /{str(approval.get('allowed_endpoint') or IDENTITY_READ_ENDPOINT).lstrip('/')}"
        ),
        maximum_call_count=int(approval.get("maximum_calls") or 1),
        maximum_duration_seconds=int(approval.get("maximum_duration_seconds") or 60),
        rollout_percentage=int(approval.get("rollout_percent") or 1),
        error_budget=DEFAULT_ERROR_BUDGET,
        created_at=_now_iso(),
        state=ExecutionState.DRAFT.value,
    )
    return sign_plan(plan)


# ── D. Preflight ─────────────────────────────────────────────────────────────
@dataclass
class PreflightInput:
    approval: Optional[dict[str, Any]] = None
    m44_request: Any = None          # m44.RolloutRequest or None
    m45_snapshot: Any = None         # m45.RuntimeAttestationSnapshot or None
    plan: Optional[ExecutionPlan] = None
    now: Optional[str] = None
    environ: Optional[dict[str, str]] = None
    base: str | Path = "."
    require_clean_repo: bool = False
    expected_commit: Optional[str] = None
    expected_branch: Optional[str] = None
    seen_approval_ids: Optional[set[str]] = None
    seen_plan_ids: Optional[set[str]] = None
    live_gate_requested: bool = False


def preflight(inp: PreflightInput) -> dict[str, Any]:
    """Single fail-closed preflight. Does not execute."""
    blockers: list[str] = []
    checks: dict[str, bool] = {}

    # approval
    av = validate_approval(inp.approval, now=inp.now,
                           seen_approval_ids=inp.seen_approval_ids)
    checks["approval_valid"] = av["valid"]
    if not av["valid"]:
        blockers.append("approval_invalid")
        blockers.extend(f"approval:{b}" for b in av["blockers"][:8])

    # plan integrity
    plan = inp.plan
    if plan is None and inp.approval and inp.m44_request is not None and inp.m45_snapshot is not None:
        try:
            from saathi.credentials import m44 as m44mod
            from saathi.credentials import m45 as m45mod
            req_fp = m44mod.request_fingerprint(inp.m44_request)
            snap_fp = m45mod.snapshot_fingerprint(inp.m45_snapshot)
            plan = create_plan(
                approval=inp.approval or {},
                m44_request_fingerprint=req_fp,
                m45_snapshot_fingerprint=snap_fp,
                expected_identity_fingerprint=str(
                    (inp.approval or {}).get("provider_identity_fingerprint") or ""),
            )
        except Exception as e:
            blockers.append(f"plan_create_failed:{type(e).__name__}")
            plan = None

    if plan is None:
        blockers.append("plan_absent")
        checks["plan_valid"] = False
    else:
        pv = verify_plan_integrity(plan)
        checks["plan_valid"] = pv["valid"]
        if not pv["valid"]:
            blockers.append("plan_invalid")
            blockers.extend(pv["reasons"])
        if inp.seen_plan_ids is not None and plan.execution_id in inp.seen_plan_ids:
            blockers.append("plan_replayed")
        # approval fingerprint bind
        if inp.approval and plan.approval_fingerprint:
            af = str(inp.approval.get("approval_integrity_fingerprint") or "")
            if af and af != plan.approval_fingerprint:
                blockers.append("plan_approval_fingerprint_mismatch")

    # M44 request
    m44_result: dict[str, Any] = {}
    if inp.m44_request is None:
        blockers.append("m44_request_absent")
        checks["m44_valid"] = False
    else:
        try:
            from saathi.credentials import m44 as m44mod
            from saathi.credentials import m45 as m45mod
            runtime = None
            if inp.m45_snapshot is not None:
                # only project if snapshot validates later; still attempt projection
                try:
                    runtime = m45mod.to_m44_runtime_snapshot(
                        inp.m45_snapshot, operator_approval_present=True)
                except Exception:
                    runtime = m44mod.RuntimeSnapshot()
            else:
                runtime = m44mod.RuntimeSnapshot()
            m44_result = m44mod.validate_request(
                inp.m44_request, now=inp.now, runtime=runtime, environ=inp.environ)
            ok = m44_result.get("verdict") == \
                m44mod.M44Verdict.ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY.value
            # Without a good M45 snapshot, gates will fail — expected.
            checks["m44_structure_ok"] = "missing:" not in str(m44_result.get("blockers"))
            checks["m44_advisory_validated"] = bool(ok)
            if not ok:
                # If only runtime gates fail and we have no snapshot, note it
                blockers.append("m44_request_not_validated")
        except Exception as e:
            blockers.append(f"m44_error:{type(e).__name__}")
            checks["m44_valid"] = False

    # M45 snapshot
    m45_result: dict[str, Any] = {}
    if inp.m45_snapshot is None:
        blockers.append("m45_snapshot_absent")
        checks["m45_valid"] = False
    else:
        try:
            from saathi.credentials import m45 as m45mod
            m45_result = m45mod.validate_snapshot(
                inp.m45_snapshot, now=inp.now,
                require_clean_repo=inp.require_clean_repo,
                expected_commit=inp.expected_commit,
                expected_branch=inp.expected_branch,
            )
            ok = m45_result.get("verdict") == \
                m45mod.M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY.value
            checks["m45_valid"] = bool(ok)
            if not ok:
                blockers.append("m45_snapshot_invalid")
        except Exception as e:
            blockers.append(f"m45_error:{type(e).__name__}")
            checks["m45_valid"] = False

    # cross-bind approval ↔ request ↔ snapshot
    if inp.approval and inp.m44_request is not None:
        req_id = getattr(inp.m44_request, "rollout_id", "")
        if inp.approval.get("rollout_id") and inp.approval.get("rollout_id") != req_id:
            blockers.append("approval_request_mismatch")
        if getattr(inp.m44_request, "provider", None) not in (None, PROVIDER_ID):
            blockers.append("request_provider_mismatch")
        if getattr(inp.m44_request, "rollout_percent", 99) > MAX_ROLLOUT_PERCENT:
            blockers.append("request_percent_above_m46_ceiling")

    if inp.approval and inp.m45_snapshot is not None:
        snap_scope = getattr(inp.m45_snapshot, "approved_scope", "")
        # soft: scope must be read-only
        if snap_scope and "read_only" not in str(snap_scope):
            blockers.append("scope_not_read_only")

    # credential reference presence (no secret read)
    if inp.approval:
        kind = str(inp.approval.get("credential_reference_kind") or "")
        loc_fp = str(inp.approval.get("credential_reference_locator_fingerprint") or "")
        if kind in ("", "NONE") or not loc_fp:
            blockers.append("credential_reference_absent")
        checks["credential_reference_present"] = bool(kind not in ("", "NONE") and loc_fp)

    # safety switches from snapshot when present
    if inp.m45_snapshot is not None:
        snap = inp.m45_snapshot
        if getattr(snap, "open_security_alerts", 0) != 0:
            blockers.append("open_security_alerts")
        if getattr(snap, "unresolved_incidents", 0) != 0:
            blockers.append("unresolved_incidents")
        if getattr(snap, "rollback_active", False):
            blockers.append("rollback_active")
        if getattr(snap, "kill_switch_active", False) or kill_switch_active(inp.environ):
            blockers.append("kill_switch_active")
        if getattr(snap, "audit_ledger_state", "intact") != "intact":
            blockers.append("audit_ledger_invalid")
        if getattr(snap, "m32_state", "PROHIBITION_UNCHANGED") != "PROHIBITION_UNCHANGED":
            blockers.append("m32_changed")
        if getattr(snap, "write_operations_allowed", False):
            blockers.append("writes_allowed")
        if getattr(snap, "deployment_allowed", False):
            blockers.append("deployment_allowed")
        if getattr(snap, "rollout_execution_allowed", False):
            blockers.append("rollout_execution_flag_set")
    else:
        if kill_switch_active(inp.environ):
            blockers.append("kill_switch_active")

    if not _m32_ok():
        blockers.append("m32_changed")
    checks["m32_unchanged"] = _m32_ok()

    # durable replay / one-shot consume registry
    if inp.approval:
        try:
            from saathi.credentials import m44 as m44mod
            req_fp = ""
            if inp.m44_request is not None:
                req_fp = m44mod.request_fingerprint(inp.m44_request)
            plan_fp = plan.plan_integrity_fingerprint if plan else ""
            exec_id = plan.execution_id if plan else ""
            cchk = is_authorization_consumed(
                approval_id=str(inp.approval.get("approval_id") or ""),
                approval_integrity_fingerprint=str(
                    inp.approval.get("approval_integrity_fingerprint") or ""),
                request_id=str(inp.approval.get("request_id") or ""),
                request_fingerprint=req_fp,
                rollout_id=str(inp.approval.get("rollout_id") or ""),
                execution_id=exec_id,
                plan_integrity_fingerprint=plan_fp,
            )
            checks["authorization_not_consumed"] = not cchk.get("consumed")
            if cchk.get("consumed"):
                blockers.append("authorization_already_consumed")
                if cchk.get("fail_closed"):
                    blockers.append("consumed_ledger_fail_closed")
        except ConsumedAuthorizationError as e:
            blockers.append(f"consumed_ledger_error:{e.code}")
            checks["authorization_not_consumed"] = False

    # evidence chain
    m43 = _file_fp(Path(inp.base) / M43_MACHINE_PATH)
    m43_1 = _file_fp(Path(inp.base) / M43_1_CLOSURE_PATH)
    m44c = _file_fp(Path(inp.base) / M44_COMPLETION_PATH)
    m45c = _file_fp(Path(inp.base) / M45_COMPLETION_PATH)
    if not m43:
        blockers.append("m43_evidence_missing")
    if not m43_1:
        blockers.append("m43_1_evidence_missing")
    if not m44c:
        blockers.append("m44_evidence_missing")
    if not m45c:
        blockers.append("m45_evidence_missing")
    checks["evidence_chain_present"] = bool(m43 and m43_1 and m44c and m45c)

    # live gate must be off unless explicitly requested for one command
    env = inp.environ if inp.environ is not None else os.environ
    live_env = str(env.get(LIVE_ENV_GATE, "") or "").strip() in ("1", "true", "TRUE", "yes")
    checks["live_gate_disabled_by_default"] = not live_env or inp.live_gate_requested
    if live_env and not inp.live_gate_requested:
        blockers.append("live_gate_env_set_without_explicit_request")

    # unique blockers
    blockers = list(dict.fromkeys(blockers))
    passed = not blockers

    state = (ExecutionState.PREFLIGHT_PASSED.value if passed
             else ExecutionState.BLOCKED.value)
    if passed and inp.live_gate_requested and live_env:
        state = ExecutionState.READY_FOR_ONE_COMMAND_LIVE_GATE.value
        verdict = M46Verdict.READY_FOR_ONE_COMMAND_LIVE_GATE
    elif passed:
        verdict = M46Verdict.PREFLIGHT_PASSED
    else:
        verdict = M46Verdict.BLOCKED

    body = {
        "schema": "m46.preflight.v1",
        "milestone": MILESTONE,
        "verdict": verdict.value,
        "passed": passed,
        "state": state,
        "blockers": blockers,
        "checks": checks,
        "approval_validation": av,
        "m44_validation_summary": {
            "verdict": m44_result.get("verdict"),
            "blockers": m44_result.get("blockers"),
        } if m44_result else None,
        "m45_validation_summary": {
            "verdict": m45_result.get("verdict"),
            "blockers": m45_result.get("blockers"),
        } if m45_result else None,
        "plan": plan.to_public() if plan else None,
        "live_gate_env_active": live_env,
        "live_gate_requested": inp.live_gate_requested,
        "execution_class": EXECUTION_CLASS,
        "authorizes_execution": False,
        "grants_anything": False,
        "alters_runtime_authority": False,
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED" if _m32_ok() else "CHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "contains_secret_values": False,
        "note": ("Preflight only. Live canary requires separate operator action "
                 f"and {LIVE_ENV_GATE}=1 for one command."),
    }
    assert is_clean(body)
    return body


# ── E/F. Execution controller ────────────────────────────────────────────────
@dataclass
class CanaryConfig:
    mode: str = "simulate"  # simulate | live
    approval: Optional[dict[str, Any]] = None
    m44_request: Any = None
    m45_snapshot: Any = None
    plan: Optional[ExecutionPlan] = None
    now: Optional[str] = None
    environ: Optional[dict[str, str]] = None
    base: str | Path = "."
    live_flag: bool = False
    # live secret reference (never the secret itself)
    secret_source_kind: str = ""
    secret_locator: str = ""
    expected_subject_fingerprint: str = ""
    # synthetic hooks for hermetic tests
    synthetic_live_result: Optional[dict[str, Any]] = None
    live_runner: Optional[Callable[..., dict[str, Any]]] = None
    seen_approval_ids: Optional[set[str]] = None
    seen_plan_ids: Optional[set[str]] = None
    persist_ledger: bool = False
    ledger_path: str | Path = LEDGER_PATH
    consumed_ledger_path: str | Path = CONSUMED_LEDGER_PATH
    enforce_durable_consume: bool = True


def run_canary(cfg: Optional[CanaryConfig] = None) -> dict[str, Any]:
    """Execute READ_ONLY_DISPOSABLE_CANARY only when all gates pass.

    Default / offline: simulate or block. Never auto-chains into revocation.
    Successful live result stops at CANARY_COMPLETED_PENDING_REVOCATION.
    """
    cfg = cfg or CanaryConfig()
    pf = preflight(PreflightInput(
        approval=cfg.approval,
        m44_request=cfg.m44_request,
        m45_snapshot=cfg.m45_snapshot,
        plan=cfg.plan,
        now=cfg.now,
        environ=cfg.environ,
        base=cfg.base,
        seen_approval_ids=cfg.seen_approval_ids,
        seen_plan_ids=cfg.seen_plan_ids,
        live_gate_requested=bool(cfg.live_flag and cfg.mode == "live"),
    ))

    if cfg.mode == "simulate":
        return _simulate_canary(cfg, pf)

    # live path
    if not cfg.live_flag:
        return _body(
            M46Verdict.AWAITING_OPERATOR_AUTHORIZATION,
            state=ExecutionState.AWAITING_APPROVAL,
            preflight=pf,
            note="live_flag=false; offline implementation only",
        )

    env = cfg.environ if cfg.environ is not None else os.environ
    if str(env.get(LIVE_ENV_GATE, "") or "").strip() not in ("1", "true", "TRUE", "yes"):
        return _body(
            M46Verdict.AWAITING_OPERATOR_AUTHORIZATION,
            state=ExecutionState.AWAITING_APPROVAL,
            preflight=pf,
            note=f"{LIVE_ENV_GATE} not set; live canary inaccessible",
        )

    if not pf["passed"]:
        return _body(M46Verdict.BLOCKED, state=ExecutionState.BLOCKED, preflight=pf)

    # must have credential reference + locator for live (still no secret in cfg)
    if not cfg.secret_source_kind or not cfg.secret_locator:
        return _body(
            M46Verdict.BLOCKED, state=ExecutionState.BLOCKED, preflight=pf,
            extra_blockers=["live_secret_reference_required"],
        )

    if kill_switch_active(cfg.environ):
        return _body(M46Verdict.ABORTED, state=ExecutionState.ABORTED, preflight=pf,
                     extra_blockers=["kill_switch"])

    # Enforce M46 live scope before any secret resolution / network.
    appr = cfg.approval or {}
    extra_scope: list[str] = []
    try:
        max_calls = int(appr.get("maximum_calls") or 0)
    except (TypeError, ValueError):
        max_calls = 0
    if max_calls != 1:
        extra_scope.append("m46_requires_exactly_one_call")
    op = str(appr.get("allowed_operation") or "")
    if op != "IDENTITY_READ":
        extra_scope.append("m46_operation_must_be_identity_read")
    endpoint = str(appr.get("allowed_endpoint") or "").lstrip("/")
    # Model A: exact endpoint authorization — IDENTITY_READ requires user only.
    if endpoint != IDENTITY_READ_ENDPOINT:
        extra_scope.append("m46_endpoint_must_be_user_for_identity_read")
    try:
        max_dur = int(appr.get("maximum_duration_seconds") or 0)
    except (TypeError, ValueError):
        max_dur = 0
    if max_dur < 1 or max_dur > MAX_DURATION_SECONDS:
        extra_scope.append("m46_duration_out_of_bounds")
    if appr.get("read_only") is not True:
        extra_scope.append("m46_not_read_only")
    for flag, name in (
        ("writes_allowed", "m46_writes_enabled"),
        ("deployment_allowed", "m46_deployment_enabled"),
        ("production_allowed", "m46_production_enabled"),
        ("autonomous_execution_allowed", "m46_autonomous_enabled"),
        ("trading_guardian_allowed", "m46_trading_guardian_enabled"),
    ):
        if appr.get(flag) is True:
            extra_scope.append(name)
    if extra_scope:
        return _body(
            M46Verdict.BLOCKED, state=ExecutionState.BLOCKED, preflight=pf,
            extra_blockers=extra_scope,
        )

    # Durable one-shot: reserve before any provider call (blocks crash-window replay).
    plan_obj = None
    if pf.get("plan"):
        try:
            plan_obj = _plan_from_public(pf["plan"])
        except Exception:
            plan_obj = cfg.plan
    else:
        plan_obj = cfg.plan
    if cfg.enforce_durable_consume:
        try:
            reserve_authorization_attempt(
                approval=appr,
                plan=plan_obj,
                m44_request=cfg.m44_request,
                repository_commit=_git_head(),
                path=cfg.consumed_ledger_path,
            )
        except ConsumedAuthorizationError as e:
            return _body(
                M46Verdict.BLOCKED, state=ExecutionState.BLOCKED, preflight=pf,
                extra_blockers=[f"consume_reserve:{e.code}"],
            )

    # Live runner — compose M39; secrets stay inside SecretHandle path.
    # Hard ceiling: exactly one provider network call (identity / subject bind).
    result: dict[str, Any]
    if cfg.synthetic_live_result is not None:
        result = dict(cfg.synthetic_live_result)
    elif cfg.live_runner is not None:
        result = cfg.live_runner(cfg)
    else:
        try:
            from saathi.credentials import m39
            # Required M39 contract: acknowledgements + hard one-call ceiling.
            # Do not fall back to multi-call behaviour — M46 forbids a second
            # provider network request.
            result = m39.run_live_single_session(
                secret_source_kind=cfg.secret_source_kind,
                secret_locator=cfg.secret_locator,
                acknowledgements=tuple(m39.M39_ACK_TOKENS),
                expected_subject_fingerprint=(
                    cfg.expected_subject_fingerprint
                    or str(appr.get("provider_identity_fingerprint") or "")
                ),
                live_flag=True,
                environ=cfg.environ,
                max_provider_network_calls=1,
                disable_retries=True,
            )
        except TypeError as e:
            # Missing required kwargs (e.g. acknowledgements) or one-call knobs.
            if cfg.enforce_durable_consume and plan_obj:
                try:
                    finalize_authorization_consume(
                        approval_id=str(appr.get("approval_id") or ""),
                        execution_id=plan_obj.execution_id,
                        success=False,
                        terminal_state=ExecutionState.FAILED.value,
                        path=cfg.consumed_ledger_path,
                    )
                except ConsumedAuthorizationError:
                    pass
            return _body(
                M46Verdict.FAILED, state=ExecutionState.FAILED, preflight=pf,
                extra_blockers=[
                    f"live_runner_signature_incompatible:{type(e).__name__}:{e}",
                ],
            )
        except Exception as e:
            if cfg.enforce_durable_consume and plan_obj:
                try:
                    finalize_authorization_consume(
                        approval_id=str(appr.get("approval_id") or ""),
                        execution_id=plan_obj.execution_id,
                        success=False,
                        terminal_state=ExecutionState.FAILED.value,
                        path=cfg.consumed_ledger_path,
                    )
                except ConsumedAuthorizationError:
                    pass
            return _body(
                M46Verdict.FAILED, state=ExecutionState.FAILED, preflight=pf,
                extra_blockers=[f"live_error:{type(e).__name__}:{getattr(e, 'code', '')}"],
            )

    # sanitize result — never include secrets
    try:
        calls_used = int(result.get("provider_network_calls")
                         or result.get("call_budget_used") or 0)
    except (TypeError, ValueError):
        calls_used = -1
    expected_fp = (
        cfg.expected_subject_fingerprint
        or str(appr.get("provider_identity_fingerprint") or "")
    )
    observed_fp = str(result.get("observed_subject_fingerprint") or "")
    identity_bound = bool(result.get("identity_bound",
                                     result.get("endpoint_identity_bound", False)))
    if expected_fp and observed_fp:
        identity_bound = identity_bound or (observed_fp == expected_fp)

    sanitized = {
        "ok": bool(result.get("ok")),
        "live_network": bool(result.get("live_network")),
        "reason": str(result.get("reason") or result.get("verdict") or "")[:200],
        "handle_closed": bool(result.get("handle_closed",
                                         result.get("secret_handle_destroyed", False))),
        "identity_bound": identity_bound,
        "http_status": result.get("http_status"),
        "provider": PROVIDER_ID,
        "read_only": True,
        "provider_network_calls": calls_used,
        "max_provider_network_calls": 1,
        "disable_retries": True,
        "endpoint": "user",  # IDENTITY_READ one-call path (subject bind)
        "operation": "IDENTITY_READ",
        "expected_subject_fingerprint": expected_fp,
        "observed_subject_fingerprint": observed_fp,
        "retries": 0,
    }
    def _finalize_fail(extra: list[str]) -> dict[str, Any]:
        if cfg.enforce_durable_consume and plan_obj:
            try:
                finalize_authorization_consume(
                    approval_id=str(appr.get("approval_id") or ""),
                    execution_id=plan_obj.execution_id,
                    success=False,
                    terminal_state=ExecutionState.FAILED.value,
                    path=cfg.consumed_ledger_path,
                )
            except ConsumedAuthorizationError:
                pass
        return _body(M46Verdict.FAILED, state=ExecutionState.FAILED, preflight=pf,
                     live_result=sanitized, extra_blockers=extra)

    if not is_clean(sanitized):
        return _finalize_fail(["leak_in_live_result"])

    if calls_used < 0 or calls_used > 1:
        return _finalize_fail(["provider_call_budget_violated"])

    if not sanitized["ok"]:
        return _finalize_fail(["live_call_failed"])

    if expected_fp and not identity_bound:
        return _finalize_fail(["identity_mismatch"])

    if not sanitized.get("handle_closed", True):
        return _finalize_fail(["secret_handle_not_destroyed"])

    out = _body(
        M46Verdict.CANARY_COMPLETED_PENDING_REVOCATION,
        state=ExecutionState.CANARY_COMPLETED_PENDING_REVOCATION,
        preflight=pf,
        live_result=sanitized,
        note=("Live canary completed. STOP. Operator must externally revoke the "
              "disposable credential, then run m46-run-revocation. Success grants nothing."),
    )
    # Evidence fingerprint of sanitized live result (no secrets).
    evidence_fp = _hmac(_EXEC_DOMAIN, _canonical(sanitized), length=24)
    out["canary_evidence_fingerprint"] = evidence_fp
    if cfg.enforce_durable_consume and plan_obj:
        try:
            finalize_authorization_consume(
                approval_id=str(appr.get("approval_id") or ""),
                execution_id=plan_obj.execution_id,
                success=True,
                canary_evidence_fingerprint=evidence_fp,
                terminal_state=ExecutionState.CANARY_COMPLETED_PENDING_REVOCATION.value,
                path=cfg.consumed_ledger_path,
            )
            out["authorization_consumed_durable"] = True
        except ConsumedAuthorizationError as e:
            # Provider already ran — still return success but flag ledger fault.
            out["authorization_consumed_durable"] = False
            out["extra_blockers"] = list(out.get("extra_blockers") or []) + [
                f"consume_finalize:{e.code}"
            ]
    if cfg.persist_ledger:
        append_ledger(
            "canary_completed_pending_revocation",
            {"execution_id": (pf.get("plan") or {}).get("execution_id"),
             "verdict": out["verdict"],
             "canary_evidence_fingerprint": evidence_fp},
            cfg.ledger_path,
        )
    return out


def _simulate_canary(cfg: CanaryConfig, pf: dict[str, Any]) -> dict[str, Any]:
    """Credential-free simulation. Never produces live completion evidence."""
    # Cases from Phase J
    if not cfg.approval:
        return _body(M46Verdict.DENIED, state=ExecutionState.BLOCKED, preflight=pf,
                     note="SIMULATED: approval absent", simulated=True)
    if cfg.m45_snapshot is not None:
        try:
            from saathi.credentials import m45 as m45mod
            # if snapshot is simulated provenance, readiness fails
            if getattr(cfg.m45_snapshot, "attestation_provenance", "") in (
                    "SIMULATED", "SELF_REPORTED", "ABSENT"):
                return _body(M46Verdict.SIMULATED_NOT_LIVE, state=ExecutionState.BLOCKED,
                             preflight=pf, simulated=True,
                             note="SIMULATED: snapshot provenance insufficient")
        except Exception:
            pass

    # synthetic controller exercise without network
    synthetic_ok = {
        "ok": True,
        "live_network": False,
        "reason": "simulated_read_only_meta",
        "handle_closed": True,
        "identity_bound": True,
        "http_status": None,
        "provider": PROVIDER_ID,
        "read_only": True,
        "mode": "SIMULATED_NOT_LIVE",
    }
    return _body(
        M46Verdict.SIMULATED_NOT_LIVE,
        state=ExecutionState.BLOCKED if not pf["passed"] else ExecutionState.DRAFT,
        preflight=pf,
        live_result=synthetic_ok,
        simulated=True,
        note=("SIMULATED_NOT_LIVE. Controller wiring exercised. "
              "Cannot produce live completion evidence. Grants nothing."),
    )


def _body(verdict: M46Verdict, *, state: ExecutionState | str,
          preflight: Optional[dict[str, Any]] = None,
          live_result: Optional[dict[str, Any]] = None,
          extra_blockers: Optional[list[str]] = None,
          note: str = "",
          simulated: bool = False) -> dict[str, Any]:
    st = state.value if isinstance(state, ExecutionState) else state
    body = {
        "schema": "m46.canary_result.v1",
        "milestone": MILESTONE,
        "verdict": verdict.value,
        "state": st,
        "execution_class": EXECUTION_CLASS,
        "preflight_passed": bool((preflight or {}).get("passed")),
        "preflight_blockers": list((preflight or {}).get("blockers") or []),
        "extra_blockers": list(extra_blockers or []),
        "live_result": live_result,
        "simulated": simulated,
        "live_canary_occurred": (
            verdict == M46Verdict.CANARY_COMPLETED_PENDING_REVOCATION
            and not simulated
            and bool((live_result or {}).get("live_network"))
        ),
        "authorizes_execution": False,
        "grants_anything": False,
        "grants_active": False,
        "grants_production": False,
        "grants_write": False,
        "grants_deployment": False,
        "alters_runtime_authority": False,
        "requires_external_revocation": verdict == M46Verdict.CANARY_COMPLETED_PENDING_REVOCATION,
        "requires_local_cleanup": verdict in (
            M46Verdict.CANARY_COMPLETED_PENDING_REVOCATION,
            M46Verdict.REVOCATION_VERIFIED_PENDING_CLEANUP,
        ),
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "contains_secret_values": False,
        "note": note or "M46 grants nothing.",
    }
    assert is_clean(body)
    return body


# ── Live canary evidence contract (revocation prerequisite) ──────────────────
# Schema versions accepted for --live-canary-evidence-file. Absent security
# flags are NEVER treated as true.
LIVE_CANARY_EVIDENCE_SCHEMA_CONTROLLER = "m46.canary_result.v1"
LIVE_CANARY_EVIDENCE_SCHEMA_LOCAL = "m46.live_canary_evidence.local.v1"
LIVE_CANARY_EVIDENCE_SCHEMA_POLICY = "m46.fresh_policy_canary.local.v1"
LIVE_CANARY_EVIDENCE_SCHEMA_POLICY_V2 = "m46.fresh_policy_canary.local.v2"

POLICY_CANARY_SUCCESS_STATES = frozenset({
    "M46_FRESH_POLICY_CANARY_VALIDATED_PENDING_EXTERNAL_REVOCATION",
    "M46_CANARY_COMPLETED_PENDING_EXTERNAL_REVOCATION",
    ExecutionState.CANARY_COMPLETED_PENDING_REVOCATION.value,
    M46Verdict.CANARY_COMPLETED_PENDING_REVOCATION.value,
})


def validate_live_canary_evidence(record: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Fail-closed validation of live-canary evidence for revocation CLI.

    Rules:
      * ``live_canary_occurred`` may only authorize when **explicitly True**
        (boolean). Absent / null / string / missing ⇒ not accepted via that field.
      * Versioned policy schemas may prove live success via explicit success
        state + call/endpoint fields without inventing ``live_canary_occurred``.
      * Historical endpoint-exception evidence is NOT accepted as
        policy-conformant success (must not certify wrong endpoint path).
    """
    blockers: list[str] = []
    checks: dict[str, bool] = {}
    if not isinstance(record, dict) or not record:
        return {
            "valid": False,
            "blockers": ["evidence_absent"],
            "checks": {"present": False},
            "schema": "",
            "authorizes_revocation_verification": False,
            "contains_secret_values": False,
        }
    checks["present"] = True
    if not is_clean(record):
        return {
            "valid": False,
            "blockers": ["leak_detected_in_evidence"],
            "checks": checks,
            "schema": str(record.get("schema") or ""),
            "authorizes_revocation_verification": False,
            "contains_secret_values": False,
        }
    schema = str(record.get("schema") or "")
    checks["schema_known"] = schema in {
        LIVE_CANARY_EVIDENCE_SCHEMA_CONTROLLER,
        LIVE_CANARY_EVIDENCE_SCHEMA_LOCAL,
        LIVE_CANARY_EVIDENCE_SCHEMA_POLICY,
        LIVE_CANARY_EVIDENCE_SCHEMA_POLICY_V2,
        "m46.fresh_policy_canary_cli_wrapper.local.v1",
    }
    if not checks["schema_known"] and schema:
        # Unknown schema: only accept explicit live_canary_occurred is True
        checks["schema_known"] = False
        blockers.append("evidence_schema_unknown")
    elif not schema:
        blockers.append("evidence_schema_missing")

    # Explicit flag path (never treat missing as true)
    flag = record.get("live_canary_occurred", None)
    checks["live_canary_occurred_explicit_true"] = flag is True
    checks["live_canary_occurred_absent"] = flag is None or "live_canary_occurred" not in record
    if flag is True:
        checks["live_success_proven"] = True
    elif flag is False:
        checks["live_success_proven"] = False
        blockers.append("live_canary_occurred_false")
    else:
        # absent or wrong type — not proof via flag
        checks["live_success_proven"] = False
        if flag is not None and flag is not False:
            blockers.append("live_canary_occurred_not_boolean")

    # Versioned policy path (v1 lacked live_canary_occurred; accept only with
    # explicit success state + endpoint/operation/call invariants).
    if not checks["live_success_proven"] and schema in (
            LIVE_CANARY_EVIDENCE_SCHEMA_POLICY,
            LIVE_CANARY_EVIDENCE_SCHEMA_POLICY_V2):
        state = str(record.get("resulting_state") or record.get("state")
                    or record.get("verdict") or "")
        calls = record.get("provider_network_calls")
        try:
            calls_i = int(calls) if calls is not None else -1
        except (TypeError, ValueError):
            calls_i = -1
        ep = str(record.get("authorized_endpoint")
                 or record.get("allowed_endpoint") or "").lstrip("/")
        actual = str(record.get("actual_request_endpoint")
                     or record.get("actual_endpoint") or "").lstrip("/")
        op = str(record.get("operation") or record.get("allowed_operation") or "")
        policy_ok = (
            state in POLICY_CANARY_SUCCESS_STATES
            and calls_i == 1
            and ep == IDENTITY_READ_ENDPOINT
            and actual in (IDENTITY_READ_ENDPOINT, f"/{IDENTITY_READ_ENDPOINT}", "user")
            and op == "IDENTITY_READ"
            and record.get("subject_match") is True
        )
        checks["policy_schema_success_proven"] = policy_ok
        if policy_ok:
            checks["live_success_proven"] = True
        else:
            blockers.append("policy_canary_evidence_incomplete")
    else:
        checks["policy_schema_success_proven"] = False

    # Wrapper schema must point to proven live with explicit true only
    if schema == "m46.fresh_policy_canary_cli_wrapper.local.v1":
        if flag is not True:
            blockers.append("wrapper_requires_explicit_live_canary_occurred_true")
            checks["live_success_proven"] = False
        else:
            checks["live_success_proven"] = True

    # Controller / local schemas require explicit True
    if schema in (LIVE_CANARY_EVIDENCE_SCHEMA_CONTROLLER, LIVE_CANARY_EVIDENCE_SCHEMA_LOCAL):
        if flag is not True:
            if checks["live_canary_occurred_absent"]:
                blockers.append("live_canary_occurred_absent")
            checks["live_success_proven"] = False

    # Historical endpoint exception must never authorize revocation of a
    # policy-conformant path by itself.
    if str(record.get("classification") or "") == HISTORICAL_ENDPOINT_BINDING_EXCEPTION:
        if schema not in (LIVE_CANARY_EVIDENCE_SCHEMA_POLICY,
                          LIVE_CANARY_EVIDENCE_SCHEMA_POLICY_V2,
                          LIVE_CANARY_EVIDENCE_SCHEMA_CONTROLLER,
                          LIVE_CANARY_EVIDENCE_SCHEMA_LOCAL):
            blockers.append("historical_endpoint_exception_not_revocation_proof")
            checks["live_success_proven"] = False

    if not checks.get("live_success_proven"):
        if "live_canary_occurred_absent" not in blockers and flag is not True:
            if checks.get("live_canary_occurred_absent"):
                blockers.append("live_canary_occurred_absent")
            elif "policy_canary_evidence_incomplete" not in blockers:
                blockers.append("live_canary_not_proven")

    # de-dupe blockers
    blockers = list(dict.fromkeys(blockers))
    # If success proven, drop pure "not proven" noise from alternate paths
    if checks.get("live_success_proven"):
        blockers = [b for b in blockers if b not in (
            "live_canary_not_proven", "live_canary_occurred_absent",
            "policy_canary_evidence_incomplete", "evidence_schema_unknown",
            "evidence_schema_missing",
        )]
        # unknown schema still blocked even with flag? Allow explicit True on unknown
        if flag is True:
            blockers = [b for b in blockers if b != "evidence_schema_unknown"]

    valid = bool(checks.get("live_success_proven")) and not blockers
    body = {
        "schema": "m46.live_canary_evidence_validation.v1",
        "valid": valid,
        "blockers": blockers,
        "checks": checks,
        "evidence_schema": schema,
        "authorizes_revocation_verification": valid,
        "authorizes_execution": False,
        "grants_anything": False,
        "contains_secret_values": False,
        "note": ("Evidence validation only. Never executes. Absent "
                 "live_canary_occurred is never treated as true."),
    }
    assert is_clean(body)
    return body


def build_policy_canary_evidence(
    *,
    canary_result: dict[str, Any],
    approval: dict[str, Any],
    plan: Optional[ExecutionPlan] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a v2 local policy canary evidence record with explicit live flag."""
    lr = canary_result.get("live_result") or {}
    live_ok = bool(canary_result.get("live_canary_occurred"))
    body: dict[str, Any] = {
        "schema": LIVE_CANARY_EVIDENCE_SCHEMA_POLICY_V2,
        "milestone": MILESTONE,
        "live_canary_occurred": live_ok,
        "resulting_state": (
            "M46_FRESH_POLICY_CANARY_VALIDATED_PENDING_EXTERNAL_REVOCATION"
            if live_ok else str(canary_result.get("verdict") or "FAILED")
        ),
        "verdict": canary_result.get("verdict"),
        "state": canary_result.get("state"),
        "approval_id": str(approval.get("approval_id") or ""),
        "approval_integrity_fingerprint": str(
            approval.get("approval_integrity_fingerprint") or ""),
        "request_id": str(approval.get("request_id") or ""),
        "rollout_id": str(approval.get("rollout_id") or ""),
        "execution_id": (plan.execution_id if plan else
                         str((canary_result.get("plan") or {}).get("execution_id") or "")),
        "plan_integrity_fingerprint": (
            plan.plan_integrity_fingerprint if plan else ""),
        "authorized_endpoint": IDENTITY_READ_ENDPOINT,
        "actual_request_endpoint": "/user",
        "operation": "IDENTITY_READ",
        "provider_network_calls": int(lr.get("provider_network_calls") or 0),
        "retries": int(lr.get("retries") or 0),
        "expected_subject_fingerprint": str(
            lr.get("expected_subject_fingerprint") or ""),
        "observed_subject_fingerprint": str(
            lr.get("observed_subject_fingerprint") or ""),
        "subject_match": bool(
            lr.get("expected_subject_fingerprint")
            and lr.get("expected_subject_fingerprint")
            == lr.get("observed_subject_fingerprint")
        ),
        "identity_bound": bool(lr.get("identity_bound")),
        "canary_evidence_fingerprint": str(
            canary_result.get("canary_evidence_fingerprint") or ""),
        "authorization_consumed_durable": bool(
            canary_result.get("authorization_consumed_durable")),
        "requires_external_revocation": bool(
            canary_result.get("requires_external_revocation")),
        "authorizes_execution": False,
        "grants_anything": False,
        "contains_secret_values": False,
        "classification": "POLICY_CONFORMANT_FRESH_CANARY",
    }
    if extra:
        for k, v in extra.items():
            if k not in body:
                body[k] = v
    assert is_clean(body)
    return body


# ── G. Revocation & cleanup ──────────────────────────────────────────────────
def run_revocation(
    *,
    mode: str = "simulate",
    live_flag: bool = False,
    environ: Optional[dict[str, str]] = None,
    secret_source_kind: str = "",
    secret_locator: str = "",
    synthetic_http_status: Optional[int] = None,
    live_runner: Optional[Callable[..., dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Observe external revocation. Only live HTTP 401 (or conclusive equivalent)
    yields REVOCATION_VERIFIED_PENDING_CLEANUP. Does not auto-cleanup."""
    if mode == "simulate" or not live_flag:
        status = synthetic_http_status
        if status == 401:
            # still simulated — must not claim machine-live
            return {
                "schema": "m46.revocation.v1",
                "milestone": MILESTONE,
                "verdict": M46Verdict.SIMULATED_NOT_LIVE.value,
                "state": ExecutionState.BLOCKED.value,
                "http_401_confirmed": False,
                "simulated_http_status": status,
                "live_network": False,
                "authorizes_execution": False,
                "grants_anything": False,
                "note": "SIMULATED revocation observation. Not machine-live proof.",
                "contains_secret_values": False,
            }
        return {
            "schema": "m46.revocation.v1",
            "milestone": MILESTONE,
            "verdict": M46Verdict.AWAITING_OPERATOR_AUTHORIZATION.value,
            "state": ExecutionState.CANARY_COMPLETED_PENDING_REVOCATION.value,
            "http_401_confirmed": False,
            "live_network": False,
            "authorizes_execution": False,
            "grants_anything": False,
            "note": "Awaiting operator external revocation + explicit live observation.",
            "contains_secret_values": False,
        }

    env = environ if environ is not None else os.environ
    if str(env.get(LIVE_ENV_GATE, "") or "").strip() not in ("1", "true", "TRUE", "yes"):
        return {
            "schema": "m46.revocation.v1",
            "verdict": M46Verdict.BLOCKED.value,
            "http_401_confirmed": False,
            "blockers": ["live_gate_required"],
            "authorizes_execution": False,
            "grants_anything": False,
            "contains_secret_values": False,
        }

    # live observation: expect call to fail with 401 after external revoke
    result: dict[str, Any] = {}
    if live_runner:
        result = live_runner()
    elif synthetic_http_status is not None:
        result = {"ok": synthetic_http_status != 401, "http_status": synthetic_http_status,
                  "live_network": True, "handle_closed": True}
    elif secret_source_kind and secret_locator:
        # Default M39 one-call identity probe (no retries). Reference only.
        try:
            from saathi.credentials import m39
            out = m39.run_live_single_session(
                secret_source_kind=secret_source_kind,
                secret_locator=secret_locator,
                acknowledgements=tuple(m39.M39_ACK_TOKENS),
                live_flag=True,
                environ=env,
                max_provider_network_calls=1,
                disable_retries=True,
                session_id="sess_m46_revocation",
            )
            id_res = out.get("identity_result") or {}
            http_status = out.get("http_status") or id_res.get("http_status")
            fc = str(id_res.get("failure_code") or "")
            if http_status is None and "401" in fc:
                http_status = 401
            result = {
                "ok": bool(out.get("ok")),
                "live_network": bool(out.get("live_network")),
                "http_status": http_status,
                "handle_closed": bool(out.get("handle_closed")),
                "provider_network_calls": int(
                    out.get("provider_network_calls") or out.get("call_budget_used") or 0),
                "reason": str(out.get("reason") or "")[:200],
                "contains_secret_values": False,
            }
        except Exception as e:
            return {
                "schema": "m46.revocation.v1",
                "verdict": M46Verdict.FAILED.value,
                "http_401_confirmed": False,
                "blockers": [f"revocation_runner_error:{type(e).__name__}"],
                "authorizes_execution": False,
                "grants_anything": False,
                "contains_secret_values": False,
            }
    else:
        return {
            "schema": "m46.revocation.v1",
            "verdict": M46Verdict.BLOCKED.value,
            "http_401_confirmed": False,
            "blockers": ["revocation_runner_not_configured",
                         "secret_reference_required"],
            "authorizes_execution": False,
            "grants_anything": False,
            "contains_secret_values": False,
        }

    status = result.get("http_status")
    # 200 after claimed revocation = fail closed
    if status == 200 or result.get("ok") is True:
        return {
            "schema": "m46.revocation.v1",
            "verdict": M46Verdict.FAILED.value,
            "state": ExecutionState.FAILED.value,
            "http_401_confirmed": False,
            "live_network": bool(result.get("live_network")),
            "http_status": status,
            "authorizes_execution": False,
            "grants_anything": False,
            "note": "Token still valid (HTTP 200/ok). External revocation not proven.",
            "contains_secret_values": False,
        }
    if status == 401:
        return {
            "schema": "m46.revocation.v1",
            "verdict": M46Verdict.REVOCATION_VERIFIED_PENDING_CLEANUP.value,
            "state": ExecutionState.REVOCATION_VERIFIED_PENDING_CLEANUP.value,
            "http_401_confirmed": True,
            "live_network": True,
            "http_status": 401,
            "authorizes_execution": False,
            "grants_anything": False,
            "note": "HTTP 401 confirmed. STOP for local reference cleanup verification.",
            "contains_secret_values": False,
        }
    return {
        "schema": "m46.revocation.v1",
        "verdict": M46Verdict.FAILED.value,
        "http_401_confirmed": False,
        "http_status": status,
        "authorizes_execution": False,
        "grants_anything": False,
        "note": "Ambiguous revocation response. Fail closed.",
        "contains_secret_values": False,
    }


def verify_cleanup(
    *,
    reference_lookup: Optional[Callable[[], dict[str, Any]]] = None,
    synthetic_absent: Optional[bool] = None,
) -> dict[str, Any]:
    """Verify local credential reference absence. Exact absence required."""
    if synthetic_absent is True:
        absent = True
        matches = 0
        source = "SYNTHETIC"
    elif synthetic_absent is False:
        absent = False
        matches = 1
        source = "SYNTHETIC"
    elif reference_lookup:
        info = reference_lookup()
        absent = bool(info.get("absent"))
        matches = int(info.get("match_count") or (0 if absent else 1))
        source = "LOOKUP"
    else:
        return {
            "schema": "m46.cleanup.v1",
            "verdict": M46Verdict.AWAITING_OPERATOR_AUTHORIZATION.value,
            "cleanup_verified": False,
            "authorizes_execution": False,
            "grants_anything": False,
            "note": "No lookup provided. Operator must remove reference then re-verify.",
            "contains_secret_values": False,
        }

    if absent and matches == 0:
        return {
            "schema": "m46.cleanup.v1",
            "verdict": M46Verdict.CLOSED_ADVISORY_ONLY.value,
            "state": ExecutionState.CLOSED_ADVISORY_ONLY.value,
            "cleanup_verified": True,
            "match_count": 0,
            "source": source,
            "authorizes_execution": False,
            "grants_anything": False,
            "grants_active": False,
            "grants_production": False,
            "note": "Local reference absent. CLOSED_ADVISORY_ONLY. Grants nothing.",
            "contains_secret_values": False,
        }
    return {
        "schema": "m46.cleanup.v1",
        "verdict": M46Verdict.BLOCKED.value,
        "cleanup_verified": False,
        "match_count": matches,
        "source": source,
        "authorizes_execution": False,
        "grants_anything": False,
        "note": "Local reference still present or matches>0. Cleanup not proven.",
        "contains_secret_values": False,
    }


# ── Durable one-shot consumed-authorization registry ─────────────────────────
# Crash model (fail-closed):
#   * preflight fail → no record
#   * before provider call → write ATTEMPTED under exclusive lock (blocks replay)
#   * provider success → CONSUMED_SUCCESS with evidence fingerprint
#   * provider fail after ATTEMPTED → ATTEMPTED_FAILED (still blocks replay)
#   * crash after ATTEMPTED with no terminal update → treat as consumed (no retry)


class ConsumedAuthorizationError(M46Error):
    pass


def _consumed_lock_path(path: str | Path) -> Path:
    return Path(str(path) + ".lock")


def _with_consumed_lock(path: str | Path, fn: Callable[[], Any]) -> Any:
    """Exclusive file lock around durable consume registry mutations."""
    import fcntl
    lock_p = _consumed_lock_path(path)
    lock_p.parent.mkdir(parents=True, exist_ok=True)
    with lock_p.open("a+") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            return fn()
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def read_consumed_ledger(path: str | Path = CONSUMED_LEDGER_PATH) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise ConsumedAuthorizationError("consumed_ledger_unreadable", str(e)) from e
    out: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as e:
            raise ConsumedAuthorizationError(
                "consumed_ledger_corrupted", f"line={i+1}") from e
        if not isinstance(rec, dict):
            raise ConsumedAuthorizationError("consumed_ledger_corrupted", f"line={i+1}")
        out.append(rec)
    return out


def verify_consumed_ledger_integrity(
    path: str | Path = CONSUMED_LEDGER_PATH,
) -> dict[str, Any]:
    """Fail closed if ledger is unreadable or any record fails integrity."""
    try:
        entries = read_consumed_ledger(path)
    except ConsumedAuthorizationError as e:
        return {"intact": False, "reason": e.code, "detail": e.detail,
                "entries": 0, "contains_secret_values": False}
    for i, e in enumerate(entries):
        expected = _hmac(
            _LEDGER_DOMAIN,
            _canonical({k: v for k, v in e.items() if k != "record_fingerprint"}),
            length=24,
        )
        if e.get("record_fingerprint") != expected:
            return {"intact": False, "reason": "record_fingerprint_mismatch",
                    "broken_at": i, "entries": len(entries),
                    "contains_secret_values": False}
        if not is_clean(e):
            return {"intact": False, "reason": "leak_detected", "broken_at": i,
                    "entries": len(entries), "contains_secret_values": False}
    return {"intact": True, "entries": len(entries), "contains_secret_values": False}


def _ids_from_consumed_entry(e: dict[str, Any]) -> dict[str, str]:
    return {
        "approval_id": str(e.get("approval_id") or ""),
        "approval_integrity_fingerprint": str(
            e.get("approval_integrity_fingerprint") or ""),
        "request_id": str(e.get("request_id") or ""),
        "request_fingerprint": str(e.get("request_fingerprint") or ""),
        "rollout_id": str(e.get("rollout_id") or ""),
        "execution_id": str(e.get("execution_id") or ""),
        "plan_integrity_fingerprint": str(e.get("plan_integrity_fingerprint") or ""),
    }


def is_authorization_consumed(
    *,
    approval_id: str = "",
    approval_integrity_fingerprint: str = "",
    request_id: str = "",
    request_fingerprint: str = "",
    rollout_id: str = "",
    execution_id: str = "",
    plan_integrity_fingerprint: str = "",
    path: str | Path = CONSUMED_LEDGER_PATH,
) -> dict[str, Any]:
    """Return whether any durable consume record matches the given identifiers."""
    integ = verify_consumed_ledger_integrity(path)
    if Path(path).exists() and not integ.get("intact"):
        return {
            "consumed": True,  # fail closed
            "fail_closed": True,
            "reason": integ.get("reason") or "consumed_ledger_invalid",
            "matches": [],
            "contains_secret_values": False,
        }
    if not Path(path).exists():
        return {"consumed": False, "fail_closed": False, "matches": [],
                "contains_secret_values": False}
    keys = {
        "approval_id": approval_id,
        "approval_integrity_fingerprint": approval_integrity_fingerprint,
        "request_id": request_id,
        "request_fingerprint": request_fingerprint,
        "rollout_id": rollout_id,
        "execution_id": execution_id,
        "plan_integrity_fingerprint": plan_integrity_fingerprint,
    }
    matches: list[str] = []
    for e in read_consumed_ledger(path):
        ids = _ids_from_consumed_entry(e)
        for k, v in keys.items():
            if v and ids.get(k) == v:
                matches.append(f"{k}:{e.get('consume_state') or 'UNKNOWN'}")
                break
    return {
        "consumed": bool(matches),
        "fail_closed": False,
        "matches": matches,
        "contains_secret_values": False,
    }


def reserve_authorization_attempt(
    *,
    approval: dict[str, Any],
    plan: Optional[ExecutionPlan],
    m44_request: Any = None,
    repository_commit: str = "",
    path: str | Path = CONSUMED_LEDGER_PATH,
) -> dict[str, Any]:
    """Atomically record ATTEMPTED before any provider call. Blocks if already used."""
    from saathi.credentials import m44 as m44mod

    appr_id = str(approval.get("approval_id") or "")
    appr_fp = str(approval.get("approval_integrity_fingerprint") or "")
    req_id = str(approval.get("request_id") or "")
    rollout_id = str(approval.get("rollout_id") or "")
    req_fp = ""
    if m44_request is not None:
        req_fp = m44mod.request_fingerprint(m44_request)
        rollout_id = rollout_id or str(getattr(m44_request, "rollout_id", "") or "")
    exec_id = plan.execution_id if plan else ""
    plan_fp = plan.plan_integrity_fingerprint if plan else ""
    loc_fp = str(approval.get("credential_reference_locator_fingerprint") or "")
    subj_fp = str(approval.get("provider_identity_fingerprint") or "")

    def _do() -> dict[str, Any]:
        chk = is_authorization_consumed(
            approval_id=appr_id,
            approval_integrity_fingerprint=appr_fp,
            request_id=req_id,
            request_fingerprint=req_fp,
            rollout_id=rollout_id,
            execution_id=exec_id,
            plan_integrity_fingerprint=plan_fp,
            path=path,
        )
        if chk.get("consumed"):
            raise ConsumedAuthorizationError(
                "authorization_already_consumed",
                ",".join(chk.get("matches") or [])[:200],
            )
        rec = {
            "schema": "m46.consumed_authorization.v1",
            "consume_state": "ATTEMPTED",
            "approval_id": appr_id,
            "approval_integrity_fingerprint": appr_fp,
            "request_id": req_id,
            "request_fingerprint": req_fp,
            "rollout_id": rollout_id,
            "execution_id": exec_id,
            "plan_integrity_fingerprint": plan_fp,
            "repository_commit": repository_commit or _git_head(),
            "provider": str(approval.get("provider") or PROVIDER_ID),
            "credential_locator_fingerprint": loc_fp,
            "expected_subject_fingerprint": subj_fp,
            "canary_evidence_fingerprint": "",
            "execution_timestamp": _now_iso(),
            "terminal_state": ExecutionState.CANARY_RUNNING.value,
            "contains_secret_values": False,
        }
        if not is_clean(rec):
            raise ConsumedAuthorizationError("leak_in_consume_record")
        rec["record_fingerprint"] = _hmac(
            _LEDGER_DOMAIN,
            _canonical({k: v for k, v in rec.items() if k != "record_fingerprint"}),
            length=24,
        )
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return rec

    return _with_consumed_lock(path, _do)


def finalize_authorization_consume(
    *,
    approval_id: str,
    execution_id: str,
    success: bool,
    canary_evidence_fingerprint: str = "",
    terminal_state: str = "",
    path: str | Path = CONSUMED_LEDGER_PATH,
) -> dict[str, Any]:
    """Append terminal consume state after provider outcome (append-only)."""
    def _do() -> dict[str, Any]:
        entries = read_consumed_ledger(path)
        base = None
        for e in reversed(entries):
            if (e.get("approval_id") == approval_id
                    and e.get("execution_id") == execution_id):
                base = e
                break
        if base is None:
            raise ConsumedAuthorizationError("consume_attempt_missing")
        rec = {
            "schema": "m46.consumed_authorization.v1",
            "consume_state": "CONSUMED_SUCCESS" if success else "ATTEMPTED_FAILED",
            "approval_id": base.get("approval_id"),
            "approval_integrity_fingerprint": base.get("approval_integrity_fingerprint"),
            "request_id": base.get("request_id"),
            "request_fingerprint": base.get("request_fingerprint"),
            "rollout_id": base.get("rollout_id"),
            "execution_id": base.get("execution_id"),
            "plan_integrity_fingerprint": base.get("plan_integrity_fingerprint"),
            "repository_commit": base.get("repository_commit"),
            "provider": base.get("provider"),
            "credential_locator_fingerprint": base.get("credential_locator_fingerprint"),
            "expected_subject_fingerprint": base.get("expected_subject_fingerprint"),
            "canary_evidence_fingerprint": canary_evidence_fingerprint or "",
            "execution_timestamp": _now_iso(),
            "terminal_state": terminal_state or (
                ExecutionState.CANARY_COMPLETED_PENDING_REVOCATION.value
                if success else ExecutionState.FAILED.value
            ),
            "prior_record_fingerprint": base.get("record_fingerprint"),
            "contains_secret_values": False,
        }
        if not is_clean(rec):
            raise ConsumedAuthorizationError("leak_in_consume_record")
        rec["record_fingerprint"] = _hmac(
            _LEDGER_DOMAIN,
            _canonical({k: v for k, v in rec.items() if k != "record_fingerprint"}),
            length=24,
        )
        p = Path(path)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return rec

    return _with_consumed_lock(path, _do)


# ── ledger ───────────────────────────────────────────────────────────────────
def append_ledger(event: str, payload: dict[str, Any],
                  path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    if not is_clean(payload):
        raise AssertionError("m46 ledger payload not leak-clean")
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
    entry = {"event": event, "prev_fingerprint": prev, "payload": payload, "ts": _now_iso()}
    entry["fingerprint"] = _hmac(
        _LEDGER_DOMAIN,
        _canonical({"event": event, "prev": prev, "payload": payload}),
        length=24)
    assert is_clean(entry)
    with p.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def read_ledger(path: str | Path = LEDGER_PATH) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def verify_ledger_chain(path: str | Path = LEDGER_PATH) -> dict[str, Any]:
    entries = read_ledger(path)
    prev = ""
    for i, e in enumerate(entries):
        if e.get("prev_fingerprint", "") != prev:
            return {"intact": False, "broken_at": i, "reason": "prev_mismatch"}
        expected = _hmac(
            _LEDGER_DOMAIN,
            _canonical({"event": e["event"], "prev": prev, "payload": e["payload"]}),
            length=24)
        if e.get("fingerprint") != expected:
            return {"intact": False, "broken_at": i, "reason": "fingerprint_mismatch"}
        prev = e["fingerprint"]
    return {"intact": True, "entries": len(entries), "contains_secret_values": False}


# ── framework status + evidence ──────────────────────────────────────────────
def framework_status() -> dict[str, Any]:
    denied = validate_approval(None)
    sim = run_canary(CanaryConfig(mode="simulate"))
    return {
        "schema": SCHEMA_VERSION,
        "milestone": MILESTONE,
        "state": FRAMEWORK_STATE,
        "framework_ready": True,
        "execution_class": EXECUTION_CLASS,
        "default_denied": not denied["valid"],
        "live_execution_available": False,
        "live_env_gate": LIVE_ENV_GATE,
        "max_rollout_percent": MAX_ROLLOUT_PERCENT,
        "max_calls": MAX_CALLS,
        "states": [s.value for s in ExecutionState],
        "advisory_only": True,
        "authorizes_execution": False,
        "grants_anything": False,
        "grants_active": False,
        "grants_production": False,
        "grants_write": False,
        "grants_deployment": False,
        "requires_separate_operator_authorization": True,
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED" if _m32_ok() else "CHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "simulation_verdict": sim.get("verdict"),
        "banner": NON_PRODUCTION_BANNER,
        "note": ("Offline implementation complete. Live canary requires fresh "
                 "approval, disposable credential reference, M44 request, M45 "
                 "snapshot, and explicit one-command live gate. Success grants nothing."),
        "contains_secret_values": False,
    }


def module_fingerprint() -> str:
    return _hmac(
        b"m46.module",
        SCHEMA_VERSION.encode(),
        FRAMEWORK_STATE.encode(),
        EXECUTION_CLASS.encode(),
        json.dumps(list(M46_ACK_TOKENS)).encode(),
        json.dumps([s.value for s in ExecutionState], sort_keys=True).encode(),
        length=24,
    )


def simulate() -> dict[str, Any]:
    """Full offline simulation matrix (credential-free)."""
    cases = {}
    # no approval
    cases["no_approval"] = run_canary(CanaryConfig(mode="simulate"))
    # approval-like but invalid
    bad = approval_template()
    cases["template_not_valid"] = validate_approval(bad)
    # simulate with empty request/snapshot
    cases["no_request_no_snapshot"] = run_canary(CanaryConfig(
        mode="simulate", approval=sign_approval(_filled_synthetic_approval())))
    # revocation simulate
    cases["revocation_simulate"] = run_revocation(mode="simulate")
    # cleanup missing
    cases["cleanup_awaiting"] = verify_cleanup()
    body = {
        "schema": "m46.simulation.v1",
        "milestone": MILESTONE,
        "mode": "SIMULATED_NOT_LIVE",
        "cases": cases,
        "authorizes_execution": False,
        "grants_anything": False,
        "live_canary_occurred": False,
        "note": "Offline simulation matrix. No live network. Grants nothing.",
        "contains_secret_values": False,
    }
    assert is_clean(body)
    return body


def _filled_synthetic_approval(**overrides) -> dict[str, Any]:
    """Hermetic synthetic approval body (still must be signed)."""
    base = {
        "approval_id": "SYN-M46-001",
        "milestone": MILESTONE,
        "operator_id": "operator:synthetic",
        "issued_at": "2026-07-22T00:00:00+00:00",
        "expires_at": "2100-01-01T00:00:00+00:00",
        "provider": PROVIDER_ID,
        "provider_identity_fingerprint": "SYN_SUBJECT_FP",
        "credential_reference_kind": "OS_KEYCHAIN_REFERENCE",
        "credential_reference_locator_fingerprint": "SYN_LOCATOR_FP",
        "request_id": "REQ-SYN-1",
        "rollout_id": "R-SYN-1",
        "allowed_operation": "IDENTITY_READ",
        "allowed_endpoint": IDENTITY_READ_ENDPOINT,
        "maximum_calls": 1,
        "maximum_duration_seconds": 60,
        "rollout_percent": 1,
        "read_only": True,
        "writes_allowed": False,
        "deployment_allowed": False,
        "production_allowed": False,
        "autonomous_execution_allowed": False,
        "trading_guardian_allowed": False,
        "rollback_conditions": [
            "identity_mismatch", "kill_switch", "security_alert",
        ],
        "kill_switch_owner": "operator:ks",
        "incident_owner": "operator:inc",
        "acknowledgements": list(M46_ACK_TOKENS),
    }
    base.update(overrides)
    return base


def build_implementation_completion() -> dict[str, Any]:
    status = framework_status()
    m43 = _file_fp(M43_MACHINE_PATH)
    m43_1 = _file_fp(M43_1_CLOSURE_PATH)
    m44c = _file_fp(M44_COMPLETION_PATH)
    m45c = _file_fp(M45_COMPLETION_PATH)
    m42 = ""
    m44_mod = m45_mod = ""
    try:
        from saathi.credentials import m44 as m44mod
        from saathi.credentials import m45 as m45mod
        m42 = str(m44mod.resolve_graduation_state().get("review_fingerprint") or "")
        m44_mod = m44mod.module_fingerprint()
        m45_mod = m45mod.module_fingerprint()
    except Exception:
        pass
    commit = _git_head()
    body = {
        "schema": "m46.implementation_completion.v1",
        "milestone": MILESTONE,
        "verdict": FRAMEWORK_STATE,
        "module_fingerprint": module_fingerprint(),
        "framework_ready": True,
        "live_canary_occurred": False,
        "live_execution_authorized": False,
        "bindings": {
            "m43_machine_fingerprint": m43,
            "m43_1_closure_fingerprint": m43_1,
            "m44_completion_fingerprint": m44c,
            "m45_completion_fingerprint": m45c,
            "m44_module_fingerprint": m44_mod,
            "m45_module_fingerprint": m45_mod,
            "m42_review_fingerprint": m42,
            "repository_commit": commit,
            "m46_module_fingerprint": module_fingerprint(),
        },
        "execution_class": EXECUTION_CLASS,
        "authorizes_execution": False,
        "grants_anything": False,
        "grants_active": False,
        "grants_production": False,
        "grants_write": False,
        "grants_deployment": False,
        "alters_runtime_authority": False,
        "deployment": False,
        "push": False,
        "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
        "authorities": dict(AUTHORITIES),
        "m32_prohibition": "UNCHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "contains_secret_values": False,
        "note": ("M46_IMPLEMENTED_AWAITING_OPERATOR_AUTHORIZATION — offline controller "
                 "implemented, tested, documented. No live canary. Grants nothing."),
    }
    assert is_clean(body)
    return body


def build_m46_evidence() -> dict[str, dict[str, Any]]:
    status = framework_status()
    denied = validate_approval(None)
    sim = simulate()
    tmpl_status = {
        "schema": "m46.authorization_template_status.v1",
        "template_path": APPROVAL_TEMPLATE_PATH,
        "template_is_valid_approval": False,
        "validate_template": validate_approval(approval_template()),
        "contains_secret_values": False,
    }
    completion = build_implementation_completion()
    return {
        "framework_status": status,
        "default_denied": denied,
        "simulation": sim,
        "authorization_template_status": tmpl_status,
        "implementation_completion": completion,
        "summary": {
            "schema": "m46.summary.v1",
            "milestone": MILESTONE,
            "state": FRAMEWORK_STATE,
            "live_canary_occurred": False,
            "module_fingerprint": module_fingerprint(),
            "authorizes_execution": False,
            "grants_anything": False,
            "authority_state": dict(FRAMEWORK_AUTHORITY_STATE),
            "authorities": dict(AUTHORITIES),
            "m32_prohibition": "UNCHANGED",
            "trading_guardian": "UNCHANGED / UNENGAGED",
            "contains_secret_values": False,
        },
    }


def emit_m46_evidence(out_dir: str | Path = EVIDENCE_DIR) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bodies = build_m46_evidence()
    written: list[str] = []
    for name, b in bodies.items():
        assert is_clean(b), f"m46 evidence not leak-clean: {name}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
        written.append(str(p))
    # also write approval template under docs/m46/
    tdir = Path("docs/m46")
    tdir.mkdir(parents=True, exist_ok=True)
    tp = tdir / "operator_canary_approval.template.json"
    tpl = approval_template()
    assert is_clean(tpl)
    tp.write_text(json.dumps(tpl, indent=2, sort_keys=True) + "\n")
    written.append(str(tp))
    return {"written": written, "count": len(written), "dir": str(out),
            "state": FRAMEWORK_STATE, "module_fingerprint": module_fingerprint(),
            "contains_secret_values": False}
