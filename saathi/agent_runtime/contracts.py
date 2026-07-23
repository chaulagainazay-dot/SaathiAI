"""M48.1 — Fail-closed execution contract layer over M10 agent_runtime.

Does **not** replace Orchestrator, RunStore, ExecutionGateway, or RunState.
Adds deterministic request validation, authority classification, approval
policy checks, retry bounds, provider-status honesty, and secret-field
rejection on top of existing models.

Financial execution remains PROHIBITED at the contract layer.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from saathi.agent_runtime.models import (
    APPROVAL_THRESHOLD,
    RiskClass,
    RunState,
    can_transition,
    is_terminal,
    validate_transition,
    IllegalTransition,
)

# ── Authority classes (M48.1 vocabulary; maps onto RiskClass) ─────────────


class AuthorityClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    LOCAL_MUTATION = "LOCAL_MUTATION"
    EXTERNAL_MUTATION = "EXTERNAL_MUTATION"
    FINANCIAL_ADVISORY = "FINANCIAL_ADVISORY"
    FINANCIAL_EXECUTION = "FINANCIAL_EXECUTION"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    SECURITY_SENSITIVE = "SECURITY_SENSITIVE"


class ApprovalRequirement(str, Enum):
    NO_APPROVAL_REQUIRED = "NO_APPROVAL_REQUIRED"
    USER_CONFIRMATION_REQUIRED = "USER_CONFIRMATION_REQUIRED"
    EXPLICIT_APPROVAL_REQUIRED = "EXPLICIT_APPROVAL_REQUIRED"
    OWNER_AUTHORIZATION_REQUIRED = "OWNER_AUTHORIZATION_REQUIRED"
    PROHIBITED = "PROHIBITED"


class ModelResolutionStatus(str, Enum):
    SELECTED = "SELECTED"
    FALLBACK_SELECTED = "FALLBACK_SELECTED"
    UNAVAILABLE = "UNAVAILABLE"
    PROHIBITED = "PROHIBITED"
    CONFIGURATION_MISSING = "CONFIGURATION_MISSING"


class ContractErrorCode(str, Enum):
    MISSING_RUN_ID = "MISSING_RUN_ID"
    MISSING_OBJECTIVE = "MISSING_OBJECTIVE"
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    UNKNOWN_AUTHORITY = "UNKNOWN_AUTHORITY"
    FINANCIAL_EXECUTION_PROHIBITED = "FINANCIAL_EXECUTION_PROHIBITED"
    MISSING_APPROVAL = "MISSING_APPROVAL"
    EXPIRED_APPROVAL = "EXPIRED_APPROVAL"
    REVOKED_APPROVAL = "REVOKED_APPROVAL"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    TERMINAL_RESTART = "TERMINAL_RESTART"
    INVALID_TIMEOUT = "INVALID_TIMEOUT"
    UNBOUNDED_RETRY = "UNBOUNDED_RETRY"
    SECRET_FIELD = "SECRET_FIELD"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_REQUEST = "INVALID_REQUEST"


# Known capability labels registered for agent runtime planning (fail-closed).
KNOWN_CAPABILITIES = frozenset({
    "plan",
    "research",
    "code",
    "review",
    "write",
    "architect",
    "execute_local",
    "chat",
    "memory_read",
    "memory_write_local",
    "diagnostics",
    "ceo_brief",
    "financial_advisory",
    # explicit names that must never execute live
    "financial_execution",
    "trade_execute",
    "broker_order",
    "withdraw",
})

PROHIBITED_CAPABILITIES = frozenset({
    "financial_execution",
    "trade_execute",
    "broker_order",
    "withdraw",
    "enable_leverage",
    "live_trading",
})

# Secret-like keys rejected in request payloads / logs.
_SECRET_KEY_RE = re.compile(
    r"(password|secret|api[_-]?key|private[_-]?key|token|authorization|"
    r"bearer|cookie|credential|ssn|private_key)",
    re.I,
)
_SECRET_VALUE_RE = re.compile(
    r"^(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"-----BEGIN )",
)

MAX_RETRY_BOUNDED = 5
MAX_TIMEOUT_SEC = 3600.0
MIN_TIMEOUT_SEC = 0.1


@dataclass
class ContractViolation:
    code: ContractErrorCode
    message: str
    field: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code.value, "message": self.message, "field": self.field}


@dataclass
class AgentRunRequest:
    """Canonical request envelope for validating a prospective agent run."""

    objective: str
    run_id: str = ""
    mission_id: str = ""
    project_id: str = ""
    workspace_id: str = ""
    agent_id: str = ""
    requested_capability: str = "plan"
    requested_model: str = ""
    authority_class: str = AuthorityClass.READ_ONLY.value
    tool_policy: dict = field(default_factory=dict)
    approval_token: str | None = None
    approval_expires_at: float | None = None  # unix seconds; None = N/A
    approval_revoked: bool = False
    timeout_sec: float = 60.0
    max_retries: int = 2
    input_payload: dict = field(default_factory=dict)
    context_refs: list[str] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
    security_classification: str = "internal"


@dataclass
class ApprovalRecord:
    approval_id: str
    status: str  # pending|granted|denied|expired|revoked
    expires_at: float | None = None
    granted_at: float | None = None
    actor: str = ""


def risk_to_authority(risk: RiskClass) -> AuthorityClass:
    """Map M10 RiskClass onto M48.1 AuthorityClass (never upgrades financial)."""
    return {
        RiskClass.READ_ONLY: AuthorityClass.READ_ONLY,
        RiskClass.LOCAL_REVERSIBLE: AuthorityClass.LOCAL_MUTATION,
        RiskClass.LOCAL_MUTATION: AuthorityClass.LOCAL_MUTATION,
        RiskClass.EXTERNAL_SIDE_EFFECT: AuthorityClass.EXTERNAL_MUTATION,
        RiskClass.HIGH_IMPACT: AuthorityClass.ADMINISTRATIVE,
    }[risk]


def approval_requirement_for(
    authority: AuthorityClass,
    *,
    capability: str = "",
) -> ApprovalRequirement:
    if capability in PROHIBITED_CAPABILITIES or authority == AuthorityClass.FINANCIAL_EXECUTION:
        return ApprovalRequirement.PROHIBITED
    if authority == AuthorityClass.FINANCIAL_ADVISORY:
        return ApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED
    if authority in (
        AuthorityClass.EXTERNAL_MUTATION,
        AuthorityClass.ADMINISTRATIVE,
        AuthorityClass.SECURITY_SENSITIVE,
    ):
        return ApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED
    if authority == AuthorityClass.LOCAL_MUTATION:
        return ApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED
    return ApprovalRequirement.NO_APPROVAL_REQUIRED


def parse_authority(raw: str | AuthorityClass | None) -> AuthorityClass | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, AuthorityClass):
        return raw
    try:
        return AuthorityClass(str(raw))
    except ValueError:
        return None


def _scan_secrets(obj: Any, path: str = "") -> list[ContractViolation]:
    out: list[ContractViolation] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if _SECRET_KEY_RE.search(str(k)):
                out.append(
                    ContractViolation(
                        ContractErrorCode.SECRET_FIELD,
                        f"secret-like field rejected: {p}",
                        field=p,
                    )
                )
            out.extend(_scan_secrets(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_scan_secrets(v, f"{path}[{i}]"))
    elif isinstance(obj, str) and _SECRET_VALUE_RE.search(obj.strip()):
        out.append(
            ContractViolation(
                ContractErrorCode.SECRET_FIELD,
                f"secret-like value rejected at {path or 'payload'}",
                field=path or "payload",
            )
        )
    return out


def validate_run_request(req: AgentRunRequest, *, now: float | None = None) -> list[ContractViolation]:
    """Fail-closed validation. Empty list = allowed to proceed to orchestrator."""
    now = time.time() if now is None else now
    errs: list[ContractViolation] = []

    if not (req.objective or "").strip():
        errs.append(
            ContractViolation(
                ContractErrorCode.MISSING_OBJECTIVE,
                "objective is required",
                field="objective",
            )
        )

    # run_id optional at create; if provided must be non-empty str
    if req.run_id is not None and req.run_id != "" and not str(req.run_id).strip():
        errs.append(
            ContractViolation(
                ContractErrorCode.MISSING_RUN_ID,
                "run_id must be non-empty when provided",
                field="run_id",
            )
        )

    cap = (req.requested_capability or "").strip()
    if not cap or cap not in KNOWN_CAPABILITIES:
        errs.append(
            ContractViolation(
                ContractErrorCode.UNKNOWN_CAPABILITY,
                f"unknown capability '{cap}' denied (fail-closed)",
                field="requested_capability",
            )
        )
    if cap in PROHIBITED_CAPABILITIES:
        errs.append(
            ContractViolation(
                ContractErrorCode.FINANCIAL_EXECUTION_PROHIBITED,
                f"capability '{cap}' is prohibited",
                field="requested_capability",
            )
        )

    auth = parse_authority(req.authority_class)
    if auth is None:
        errs.append(
            ContractViolation(
                ContractErrorCode.UNKNOWN_AUTHORITY,
                f"unknown authority '{req.authority_class}' denied",
                field="authority_class",
            )
        )
        return errs  # further checks depend on authority

    if auth == AuthorityClass.FINANCIAL_EXECUTION:
        errs.append(
            ContractViolation(
                ContractErrorCode.FINANCIAL_EXECUTION_PROHIBITED,
                "FINANCIAL_EXECUTION is prohibited at contract layer",
                field="authority_class",
            )
        )

    need = approval_requirement_for(auth, capability=cap)
    if need == ApprovalRequirement.PROHIBITED:
        errs.append(
            ContractViolation(
                ContractErrorCode.FINANCIAL_EXECUTION_PROHIBITED,
                "action is PROHIBITED",
                field="authority_class",
            )
        )
    elif need in (
        ApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED,
        ApprovalRequirement.OWNER_AUTHORIZATION_REQUIRED,
        ApprovalRequirement.USER_CONFIRMATION_REQUIRED,
    ):
        if not req.approval_token:
            errs.append(
                ContractViolation(
                    ContractErrorCode.MISSING_APPROVAL,
                    "approval required but approval_token missing",
                    field="approval_token",
                )
            )
        if req.approval_revoked:
            errs.append(
                ContractViolation(
                    ContractErrorCode.REVOKED_APPROVAL,
                    "approval has been revoked",
                    field="approval_token",
                )
            )
        if req.approval_expires_at is not None and req.approval_expires_at < now:
            errs.append(
                ContractViolation(
                    ContractErrorCode.EXPIRED_APPROVAL,
                    "approval has expired",
                    field="approval_expires_at",
                )
            )

    try:
        t = float(req.timeout_sec)
    except (TypeError, ValueError):
        t = -1
    if t < MIN_TIMEOUT_SEC or t > MAX_TIMEOUT_SEC:
        errs.append(
            ContractViolation(
                ContractErrorCode.INVALID_TIMEOUT,
                f"timeout_sec must be in [{MIN_TIMEOUT_SEC}, {MAX_TIMEOUT_SEC}]",
                field="timeout_sec",
            )
        )

    try:
        retries = int(req.max_retries)
    except (TypeError, ValueError):
        retries = -1
    if retries < 0 or retries > MAX_RETRY_BOUNDED:
        errs.append(
            ContractViolation(
                ContractErrorCode.UNBOUNDED_RETRY,
                f"max_retries must be 0..{MAX_RETRY_BOUNDED}",
                field="max_retries",
            )
        )

    errs.extend(_scan_secrets(req.input_payload, "input_payload"))
    errs.extend(_scan_secrets(req.tool_policy, "tool_policy"))
    return errs


def validate_state_transition_safe(src: RunState | str, dst: RunState | str) -> list[ContractViolation]:
    """Wrap M10 transitions with contract error codes."""
    try:
        s = src if isinstance(src, RunState) else RunState(src)
        d = dst if isinstance(dst, RunState) else RunState(dst)
    except ValueError as e:
        return [
            ContractViolation(
                ContractErrorCode.INVALID_TRANSITION,
                f"unknown state: {e}",
            )
        ]
    if is_terminal(s) and s != d:
        return [
            ContractViolation(
                ContractErrorCode.TERMINAL_RESTART,
                f"terminal state {s.value} cannot transition to {d.value}",
            )
        ]
    if not can_transition(s, d):
        return [
            ContractViolation(
                ContractErrorCode.INVALID_TRANSITION,
                f"illegal transition {s.value} → {d.value}",
            )
        ]
    return []


def require_transition(src: RunState | str, dst: RunState | str) -> None:
    errs = validate_state_transition_safe(src, dst)
    if errs:
        raise IllegalTransition(errs[0].message)


def classify_provider_status(
    available: bool,
    *,
    configured: bool = True,
    prohibited: bool = False,
    used_fallback: bool = False,
) -> ModelResolutionStatus:
    if prohibited:
        return ModelResolutionStatus.PROHIBITED
    if not configured:
        return ModelResolutionStatus.CONFIGURATION_MISSING
    if not available:
        return ModelResolutionStatus.UNAVAILABLE
    if used_fallback:
        return ModelResolutionStatus.FALLBACK_SELECTED
    return ModelResolutionStatus.SELECTED


def provider_status_is_success(status: ModelResolutionStatus) -> bool:
    """Unavailable / missing config must never be treated as successful selection."""
    return status in (
        ModelResolutionStatus.SELECTED,
        ModelResolutionStatus.FALLBACK_SELECTED,
    )


def validate_approval_record(rec: ApprovalRecord, *, now: float | None = None) -> list[ContractViolation]:
    now = time.time() if now is None else now
    errs: list[ContractViolation] = []
    if rec.status in ("revoked",):
        errs.append(
            ContractViolation(
                ContractErrorCode.REVOKED_APPROVAL,
                "approval revoked",
                field="status",
            )
        )
    if rec.status == "expired" or (
        rec.expires_at is not None and rec.expires_at < now and rec.status != "granted"
    ):
        # granted but past expiry also blocked
        pass
    if rec.expires_at is not None and rec.expires_at < now:
        errs.append(
            ContractViolation(
                ContractErrorCode.EXPIRED_APPROVAL,
                "approval expired",
                field="expires_at",
            )
        )
    if rec.status not in ("granted",) and rec.status != "pending":
        if rec.status in ("denied",):
            errs.append(
                ContractViolation(
                    ContractErrorCode.MISSING_APPROVAL,
                    "approval denied",
                    field="status",
                )
            )
    if rec.status == "pending":
        errs.append(
            ContractViolation(
                ContractErrorCode.MISSING_APPROVAL,
                "approval still pending",
                field="status",
            )
        )
    return errs


def contract_summary() -> dict:
    """Read-only inventory for diagnostics / CLI."""
    return {
        "layer": "M48.1 contracts",
        "canonical_runtime": "saathi.agent_runtime",
        "reuses": [
            "RunState",
            "RiskClass",
            "validate_transition",
            "RunStore",
            "Orchestrator",
            "ExecutionGateway",
        ],
        "authority_classes": [a.value for a in AuthorityClass],
        "approval_requirements": [a.value for a in ApprovalRequirement],
        "model_resolution_statuses": [m.value for m in ModelResolutionStatus],
        "known_capabilities": sorted(KNOWN_CAPABILITIES),
        "prohibited_capabilities": sorted(PROHIBITED_CAPABILITIES),
        "run_states": [s.value for s in RunState],
        "max_retries_bound": MAX_RETRY_BOUNDED,
        "financial_execution": "PROHIBITED",
        "trading_guardian": "ADVISORY_ONLY_UNENGAGED",
    }
