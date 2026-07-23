"""M49.1 — Fail-closed tool execution contracts.

Code-owned manifests and request/result models. Callers cannot override
authority or side-effect class. Aligns authority vocabulary with M48
``AuthorityClass`` without replacing agent runtime contracts.
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# ── Enumerations ──────────────────────────────────────────────────────────


class ToolAuthorityClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    LOCAL_MUTATION = "LOCAL_MUTATION"
    EXTERNAL_MUTATION = "EXTERNAL_MUTATION"
    SECURITY_SENSITIVE = "SECURITY_SENSITIVE"
    FINANCIAL_ADVISORY = "FINANCIAL_ADVISORY"
    FINANCIAL_EXECUTION = "FINANCIAL_EXECUTION"
    # Explicit unknown must never be treated as safe
    UNKNOWN = "UNKNOWN"


class ToolSideEffectClass(str, Enum):
    NO_SIDE_EFFECT = "NO_SIDE_EFFECT"
    LOCAL_REVERSIBLE = "LOCAL_REVERSIBLE"
    LOCAL_IRREVERSIBLE = "LOCAL_IRREVERSIBLE"
    EXTERNAL_REVERSIBLE = "EXTERNAL_REVERSIBLE"
    EXTERNAL_IRREVERSIBLE = "EXTERNAL_IRREVERSIBLE"
    FINANCIAL_ADVISORY = "FINANCIAL_ADVISORY"
    FINANCIAL_EXECUTION = "FINANCIAL_EXECUTION"
    UNKNOWN = "UNKNOWN"


class ToolCancellationSupport(str, Enum):
    HARD_CANCEL_SUPPORTED = "HARD_CANCEL_SUPPORTED"
    COOPERATIVE_CANCEL_SUPPORTED = "COOPERATIVE_CANCEL_SUPPORTED"
    TIMEOUT_ONLY = "TIMEOUT_ONLY"
    NOT_CANCELLABLE = "NOT_CANCELLABLE"
    UNKNOWN = "UNKNOWN"


class ToolRetryClass(str, Enum):
    RETRYABLE_TRANSIENT = "RETRYABLE_TRANSIENT"
    RETRYABLE_RATE_LIMIT = "RETRYABLE_RATE_LIMIT"
    RETRYABLE_PROVIDER_UNAVAILABLE = "RETRYABLE_PROVIDER_UNAVAILABLE"
    NOT_RETRYABLE_VALIDATION = "NOT_RETRYABLE_VALIDATION"
    NOT_RETRYABLE_AUTHORITY = "NOT_RETRYABLE_AUTHORITY"
    NOT_RETRYABLE_APPROVAL = "NOT_RETRYABLE_APPROVAL"
    NOT_RETRYABLE_CANCELLATION = "NOT_RETRYABLE_CANCELLATION"
    NOT_RETRYABLE_TIMEOUT_UNKNOWN = "NOT_RETRYABLE_TIMEOUT_UNKNOWN"
    NOT_RETRYABLE_UNCERTAIN_MUTATION = "NOT_RETRYABLE_UNCERTAIN_MUTATION"
    NOT_RETRYABLE_PROHIBITED = "NOT_RETRYABLE_PROHIBITED"
    NEVER = "NEVER"
    BOUNDED_SAFE = "BOUNDED_SAFE"


class ToolIdempotencyClass(str, Enum):
    NATURALLY_IDEMPOTENT = "NATURALLY_IDEMPOTENT"
    IDEMPOTENCY_KEY_REQUIRED = "IDEMPOTENCY_KEY_REQUIRED"
    NON_IDEMPOTENT = "NON_IDEMPOTENT"
    UNKNOWN = "UNKNOWN"


class ToolAvailability(str, Enum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    PROHIBITED = "PROHIBITED"


class ToolOutcomeClass(str, Enum):
    SUCCESS_CONFIRMED = "SUCCESS_CONFIRMED"
    FAILURE_CONFIRMED = "FAILURE_CONFIRMED"
    CANCELLED_CONFIRMED = "CANCELLED_CONFIRMED"
    TIMEOUT_CONFIRMED = "TIMEOUT_CONFIRMED"
    SIDE_EFFECT_UNKNOWN = "SIDE_EFFECT_UNKNOWN"
    TOOL_OUTCOME_UNKNOWN = "TOOL_OUTCOME_UNKNOWN"
    BLOCKED = "BLOCKED"
    PROHIBITED = "PROHIBITED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class ToolSecretPolicy(str, Enum):
    NO_SECRET = "NO_SECRET"
    OPTIONAL_SECRET_REFERENCE = "OPTIONAL_SECRET_REFERENCE"
    REQUIRED_SECRET_REFERENCE = "REQUIRED_SECRET_REFERENCE"
    BROKERED_CLIENT_ONLY = "BROKERED_CLIENT_ONLY"
    PROHIBITED = "PROHIBITED"


class ToolApprovalRequirement(str, Enum):
    NO_APPROVAL_REQUIRED = "NO_APPROVAL_REQUIRED"
    USER_CONFIRMATION_REQUIRED = "USER_CONFIRMATION_REQUIRED"
    EXPLICIT_APPROVAL_REQUIRED = "EXPLICIT_APPROVAL_REQUIRED"
    OWNER_AUTHORIZATION_REQUIRED = "OWNER_AUTHORIZATION_REQUIRED"
    PROHIBITED = "PROHIBITED"


class ToolErrorCode(str, Enum):
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_DISABLED = "TOOL_DISABLED"
    TOOL_MANIFEST_INVALID = "TOOL_MANIFEST_INVALID"
    TOOL_INPUT_INVALID = "TOOL_INPUT_INVALID"
    TOOL_OUTPUT_INVALID = "TOOL_OUTPUT_INVALID"
    TOOL_AUTHORITY_DENIED = "TOOL_AUTHORITY_DENIED"
    TOOL_APPROVAL_REQUIRED = "TOOL_APPROVAL_REQUIRED"
    TOOL_APPROVAL_EXPIRED = "TOOL_APPROVAL_EXPIRED"
    TOOL_APPROVAL_REVOKED = "TOOL_APPROVAL_REVOKED"
    TOOL_SECRET_POLICY_VIOLATION = "TOOL_SECRET_POLICY_VIOLATION"
    TOOL_CANCELLED = "TOOL_CANCELLED"
    TOOL_CANCELLATION_UNCONFIRMED = "TOOL_CANCELLATION_UNCONFIRMED"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_OUTCOME_UNKNOWN = "TOOL_OUTCOME_UNKNOWN"
    TOOL_RETRY_EXHAUSTED = "TOOL_RETRY_EXHAUSTED"
    TOOL_IDEMPOTENCY_CONFLICT = "TOOL_IDEMPOTENCY_CONFLICT"
    TOOL_SIDE_EFFECT_PROHIBITED = "TOOL_SIDE_EFFECT_PROHIBITED"
    TOOL_FINANCIAL_EXECUTION_PROHIBITED = "TOOL_FINANCIAL_EXECUTION_PROHIBITED"
    TOOL_DEADLINE_EXCEEDED = "TOOL_DEADLINE_EXCEEDED"
    TOOL_CAPABILITY_MISMATCH = "TOOL_CAPABILITY_MISMATCH"
    TOOL_ADAPTER_ERROR = "TOOL_ADAPTER_ERROR"
    TOOL_REGISTRY_ERROR = "TOOL_REGISTRY_ERROR"


# ── Policies ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TimeoutPolicy:
    default_sec: float = 30.0
    max_sec: float = 300.0
    grace_sec: float = 2.0

    def effective(self, requested: float | None, parent_deadline: float | None) -> float:
        t = float(requested if requested is not None else self.default_sec)
        if t <= 0:
            return 0.0
        t = min(t, self.max_sec)
        if parent_deadline is not None and parent_deadline > 0:
            remaining = parent_deadline - time.time()
            if remaining <= 0:
                return 0.0
            t = min(t, remaining)
        return t


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    retry_class: ToolRetryClass = ToolRetryClass.NEVER
    allow_retry_on_timeout: bool = False


@dataclass(frozen=True)
class IdempotencyPolicy:
    klass: ToolIdempotencyClass = ToolIdempotencyClass.NATURALLY_IDEMPOTENT
    require_key: bool = False


@dataclass(frozen=True)
class EvidencePolicy:
    record_input: bool = True
    record_output: bool = True
    redact: bool = True


@dataclass(frozen=True)
class RedactionPolicy:
    redact_secret_keys: bool = True
    redact_secret_values: bool = True
    max_payload_chars: int = 4000


# ── Manifest (code-owned) ─────────────────────────────────────────────────


@dataclass
class ToolManifest:
    tool_id: str
    version: str
    display_name: str
    description: str
    domain: str
    capabilities: tuple[str, ...]
    authority_class: ToolAuthorityClass
    side_effect_class: ToolSideEffectClass
    approval_requirement: ToolApprovalRequirement
    secret_policy: ToolSecretPolicy
    input_schema: dict
    output_schema: dict
    timeout_policy: TimeoutPolicy = field(default_factory=TimeoutPolicy)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    idempotency_policy: IdempotencyPolicy = field(default_factory=IdempotencyPolicy)
    cancellation_support: ToolCancellationSupport = ToolCancellationSupport.TIMEOUT_ONLY
    evidence_policy: EvidencePolicy = field(default_factory=EvidencePolicy)
    redaction_policy: RedactionPolicy = field(default_factory=RedactionPolicy)
    enabled: bool = True
    availability: ToolAvailability = ToolAvailability.ENABLED

    def key(self) -> str:
        return f"{self.tool_id}@{self.version}"

    def to_public_dict(self) -> dict:
        """Safe summary for diagnostics (no secrets, no adapter internals)."""
        return {
            "tool_id": self.tool_id,
            "version": self.version,
            "display_name": self.display_name,
            "description": self.description[:500],
            "domain": self.domain,
            "capabilities": list(self.capabilities),
            "authority_class": self.authority_class.value,
            "side_effect_class": self.side_effect_class.value,
            "approval_requirement": self.approval_requirement.value,
            "secret_policy": self.secret_policy.value,
            "cancellation_support": self.cancellation_support.value,
            "idempotency": self.idempotency_policy.klass.value,
            "enabled": self.enabled,
            "availability": self.availability.value,
            "timeout_default_sec": self.timeout_policy.default_sec,
            "timeout_max_sec": self.timeout_policy.max_sec,
        }


# ── Request / approval / result ───────────────────────────────────────────


@dataclass
class ToolApprovalReference:
    """Server-side approval reference — never UI-only authority."""

    approval_id: str = ""
    actor: str = ""
    capability: str = ""
    tool_id: str = ""
    run_id: str = ""
    mission_id: str = ""
    side_effect_class: str = ""
    expires_at: float = 0.0
    revoked: bool = False
    active: bool = True

    def is_valid_for(
        self,
        *,
        tool_id: str,
        capability: str,
        run_id: str,
        side_effect: ToolSideEffectClass,
        now: float | None = None,
    ) -> tuple[bool, ToolErrorCode | None]:
        now = now if now is not None else time.time()
        if not self.approval_id or not self.active:
            return False, ToolErrorCode.TOOL_APPROVAL_REQUIRED
        if self.revoked:
            return False, ToolErrorCode.TOOL_APPROVAL_REVOKED
        if self.expires_at and self.expires_at < now:
            return False, ToolErrorCode.TOOL_APPROVAL_EXPIRED
        if self.tool_id and self.tool_id != tool_id:
            return False, ToolErrorCode.TOOL_APPROVAL_REQUIRED
        if self.capability and capability and self.capability != capability:
            return False, ToolErrorCode.TOOL_APPROVAL_REQUIRED
        if self.run_id and run_id and self.run_id != run_id:
            return False, ToolErrorCode.TOOL_APPROVAL_REQUIRED
        if self.side_effect_class and self.side_effect_class != side_effect.value:
            return False, ToolErrorCode.TOOL_APPROVAL_REQUIRED
        return True, None


@dataclass
class ToolExecutionRequest:
    run_id: str
    tool_id: str
    arguments: dict
    attempt: int = 1
    tool_version: str = ""
    call_id: str = field(default_factory=lambda: "tc_" + uuid.uuid4().hex[:16])
    idempotency_key: str = ""
    capability: str = ""
    requested_by: str = "user:ajay"
    approval_reference: ToolApprovalReference | None = None
    deadline: float = 0.0
    parent_task_id: str = ""
    trace_id: str = ""
    timeout_sec: float | None = None
    # Callers MUST NOT supply authority/side_effect — ignored if present
    _caller_authority_ignored: str = ""
    _caller_side_effect_ignored: str = ""

    def normalized_args(self) -> dict:
        return dict(self.arguments or {})


@dataclass
class ToolExecutionResult:
    tool_id: str
    tool_version: str
    call_id: str
    status: str  # accepted | rejected | completed | failed | cancelled | timed_out | blocked
    outcome_class: ToolOutcomeClass
    data: dict = field(default_factory=dict)
    safe_message: str = ""
    error_code: str = ""
    retryable: bool = False
    side_effect_confirmed: bool = False
    cancellation_confirmed: bool = False
    timeout_detected: bool = False
    evidence_references: list[str] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0
    duration_ms: float = 0.0
    events: list[str] = field(default_factory=list)
    retry_class: str = ""
    authority_class: str = ""
    side_effect_class: str = ""
    adapter_invoked: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["outcome_class"] = self.outcome_class.value
        return d

    @property
    def ok(self) -> bool:
        return self.outcome_class == ToolOutcomeClass.SUCCESS_CONFIRMED


# ── Manifest validation ───────────────────────────────────────────────────


_REQUIRED_SCHEMA_KEYS = ("type",)


def validate_manifest(m: ToolManifest) -> list[str]:
    errs: list[str] = []
    if not m.tool_id or not re.match(r"^[a-z][a-z0-9_.-]{1,63}$", m.tool_id):
        errs.append("tool_id invalid")
    if not m.version:
        errs.append("version required")
    if not m.display_name:
        errs.append("display_name required")
    if not m.domain:
        errs.append("domain required")
    if not m.capabilities:
        errs.append("capabilities required")
    if m.authority_class == ToolAuthorityClass.UNKNOWN:
        errs.append("authority UNKNOWN not registerable")
    if m.side_effect_class == ToolSideEffectClass.UNKNOWN:
        errs.append("side_effect UNKNOWN not registerable")
    if m.cancellation_support == ToolCancellationSupport.UNKNOWN:
        errs.append("cancellation UNKNOWN not registerable")
    if m.idempotency_policy.klass == ToolIdempotencyClass.UNKNOWN:
        errs.append("idempotency UNKNOWN not registerable")
    if not isinstance(m.input_schema, dict) or "type" not in m.input_schema:
        errs.append("input_schema must include type")
    if not isinstance(m.output_schema, dict) or "type" not in m.output_schema:
        errs.append("output_schema must include type")
    if (
        m.authority_class == ToolAuthorityClass.FINANCIAL_EXECUTION
        or m.side_effect_class == ToolSideEffectClass.FINANCIAL_EXECUTION
    ):
        if m.approval_requirement != ToolApprovalRequirement.PROHIBITED:
            errs.append("financial execution must be PROHIBITED")
        if m.availability != ToolAvailability.PROHIBITED:
            errs.append("financial execution availability must be PROHIBITED")
    return errs


def default_approval_for(authority: ToolAuthorityClass) -> ToolApprovalRequirement:
    if authority == ToolAuthorityClass.READ_ONLY:
        return ToolApprovalRequirement.NO_APPROVAL_REQUIRED
    if authority == ToolAuthorityClass.FINANCIAL_EXECUTION:
        return ToolApprovalRequirement.PROHIBITED
    if authority == ToolAuthorityClass.FINANCIAL_ADVISORY:
        return ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED
    if authority in (
        ToolAuthorityClass.EXTERNAL_MUTATION,
        ToolAuthorityClass.SECURITY_SENSITIVE,
        ToolAuthorityClass.LOCAL_MUTATION,
    ):
        return ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED
    return ToolApprovalRequirement.PROHIBITED


# Adapter type: (arguments, context) -> dict with keys data|error|cancelled|timeout|side_effect_confirmed
ToolAdapterFn = Callable[[dict, "BoundedToolContext"], dict]


# Avoid circular import for type hints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from saathi.tool_runtime.context import BoundedToolContext
