"""M32 — Governed provider-adapter models (identity, context, result, taxonomies).

A *provider adapter* is a bounded, provider-neutral boundary that sits ABOVE the
M27 connector adapter transport. It never determines execution authority:
authority stays with policy, approval, ExecutionGateway, the connector runtime,
M30 certification, rollout, and M31 account/credential readiness.

All enums fail closed: an unknown side-effect class, data classification, or
provider identity is rejected rather than defaulted to something permissive.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

M32_SCHEMA_VERSION = "m32.provider.v1"


# ── Execution modes (kept strictly distinct) ─────────────────────────────────
class ExecutionMode(str, Enum):
    DRY_RUN = "DRY_RUN"        # validate; no provider execution
    SIMULATION = "SIMULATION"  # deterministic local provider behaviour
    SHADOW = "SHADOW"          # safe sandbox/read-only path; non-authoritative
    CANARY = "CANARY"          # PROHIBITED in M32
    ACTIVE = "ACTIVE"          # PROHIBITED in M32


# Modes M32 is permitted to actually execute
M32_ALLOWED_MODES = frozenset({
    ExecutionMode.DRY_RUN, ExecutionMode.SIMULATION, ExecutionMode.SHADOW,
})
M32_PROHIBITED_MODES = frozenset({ExecutionMode.CANARY, ExecutionMode.ACTIVE})


# ── Result status taxonomy ───────────────────────────────────────────────────
class ProviderStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CANCELLED = "cancelled"
    DENIED = "denied"
    DRY_RUN = "dry_run"
    SHADOW = "shadow"


# ── Canonical provider error taxonomy ────────────────────────────────────────
class ProviderErrorCode(str, Enum):
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    SCOPE_INSUFFICIENT = "SCOPE_INSUFFICIENT"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    DUPLICATE = "DUPLICATE"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    CANCELLED = "CANCELLED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    INTERNAL_ADAPTER_ERROR = "INTERNAL_ADAPTER_ERROR"
    UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"


# ── Deterministic retry classification ───────────────────────────────────────
class RetryCategory(str, Enum):
    NO_RETRY = "NO_RETRY"
    SAFE_RETRY = "SAFE_RETRY"
    RETRY_AFTER = "RETRY_AFTER"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    CANCELLED = "CANCELLED"


# Categories that MAY retry when the operation is idempotent + budget/deadline remain
RETRYABLE_CATEGORIES = frozenset({
    RetryCategory.SAFE_RETRY,
    RetryCategory.RETRY_AFTER,
    RetryCategory.RATE_LIMITED,
    RetryCategory.PROVIDER_UNAVAILABLE,
})


# ── External side-effect classification ──────────────────────────────────────
class ProviderSideEffectClass(str, Enum):
    NONE = "NONE"
    READ_ONLY = "READ_ONLY"
    REVERSIBLE_WRITE = "REVERSIBLE_WRITE"
    IRREVERSIBLE_WRITE = "IRREVERSIBLE_WRITE"
    FINANCIAL = "FINANCIAL"
    SECURITY_SENSITIVE = "SECURITY_SENSITIVE"
    ACCOUNT_MUTATION = "ACCOUNT_MUTATION"


M32_PERMITTED_SIDE_EFFECTS = frozenset({
    ProviderSideEffectClass.NONE, ProviderSideEffectClass.READ_ONLY,
})
M32_PROHIBITED_SIDE_EFFECTS = frozenset({
    ProviderSideEffectClass.REVERSIBLE_WRITE,
    ProviderSideEffectClass.IRREVERSIBLE_WRITE,
    ProviderSideEffectClass.FINANCIAL,
    ProviderSideEffectClass.SECURITY_SENSITIVE,
    ProviderSideEffectClass.ACCOUNT_MUTATION,
})


# ── Data classification ──────────────────────────────────────────────────────
class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    PERSONAL = "PERSONAL"
    AUTH_SECRET = "AUTH_SECRET"
    FINANCIAL = "FINANCIAL"
    HEALTH = "HEALTH"
    SECURITY_SENSITIVE = "SECURITY_SENSITIVE"
    PROHIBITED = "PROHIBITED"


M32_PERMITTED_DATA_CLASSES = frozenset({
    DataClassification.PUBLIC, DataClassification.INTERNAL,
})


# ── Provider health states (distinct from connector health & account readiness)
class ProviderHealthState(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_BLOCKED = "AUTH_BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"
    MISCONFIGURED = "MISCONFIGURED"
    QUARANTINED = "QUARANTINED"
    DISABLED = "DISABLED"


HEALTHY_STATES = frozenset({ProviderHealthState.HEALTHY, ProviderHealthState.DEGRADED})


# ── Provider verification states ─────────────────────────────────────────────
class ProviderVerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SIMULATION_VERIFIED = "SIMULATION_VERIFIED"
    SHADOW_VERIFIED_WITH_LIMITATIONS = "SHADOW_VERIFIED_WITH_LIMITATIONS"
    STALE = "STALE"
    REVOKED = "REVOKED"
    FAILED = "FAILED"


# States that count as verified-enough to be an execution eligibility input
VERIFIED_STATES = frozenset({
    ProviderVerificationState.SIMULATION_VERIFIED,
    ProviderVerificationState.SHADOW_VERIFIED_WITH_LIMITATIONS,
})
# The highest verification state M32 may claim
M32_MAX_VERIFICATION = ProviderVerificationState.SHADOW_VERIFIED_WITH_LIMITATIONS


# ── Prohibited provider patterns (financial / trading — fail closed) ─────────
PROHIBITED_PROVIDER_PATTERNS = frozenset({
    "trade", "order", "broker", "exchange", "wallet", "withdraw", "transfer",
    "payment", "bank", "financial", "leverage", "margin", "futures", "crypto",
    "binance", "brokerage", "spot", "settlement", "payout",
})

# Prohibited provider category ids (display-name independent)
PROHIBITED_PROVIDER_IDS = frozenset({
    "gmail", "google_calendar", "slack", "facebook", "instagram",
    "youtube_publish", "linkedin_publish",
})


def provider_is_prohibited(provider_id: str, *, capabilities: tuple[str, ...] = ()) -> Optional[str]:
    """Return a reason string if a provider id/capabilities are prohibited, else None."""
    pid = (provider_id or "").strip().lower()
    if not pid:
        return "empty_provider_id"
    if pid in PROHIBITED_PROVIDER_IDS:
        return f"prohibited_provider_id:{pid}"
    for pat in PROHIBITED_PROVIDER_PATTERNS:
        if pat in pid:
            return f"prohibited_pattern:{pat}"
    for cap in capabilities or ():
        lc = str(cap).lower()
        for pat in PROHIBITED_PROVIDER_PATTERNS:
            if pat in lc:
                return f"prohibited_capability_pattern:{pat}"
    return None


# ── Rate-limit metadata ──────────────────────────────────────────────────────
@dataclass
class RateLimit:
    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset_at: Optional[float] = None
    retry_after: Optional[float] = None
    source: str = "none"          # header|policy|none
    confidence: str = "unknown"   # high|low|unknown

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Provider identity (extends M29 manifest identity) ────────────────────────
@dataclass
class ProviderIdentity:
    provider_id: str
    provider_version: str = "1.0.0"
    adapter_version: str = "1.0.0"
    connector_id: str = ""
    transport: str = "local_simulator"   # local_simulator|http|inprocess
    base_endpoint_class: str = "loopback"  # loopback|https|inprocess
    environment: str = "test"             # test|sandbox|dev|local ; production disabled
    auth_profile: str = "none"
    capabilities: tuple[str, ...] = ()
    side_effect_class: str = ProviderSideEffectClass.READ_ONLY.value
    rate_limit_profile: str = "default"
    data_classification: str = DataClassification.PUBLIC.value
    display_name: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.capabilities, list):
            self.capabilities = tuple(self.capabilities)
        if not self.display_name:
            self.display_name = self.provider_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProviderIdentity":
        return cls(
            provider_id=str(d["provider_id"]),
            provider_version=str(d.get("provider_version") or "1.0.0"),
            adapter_version=str(d.get("adapter_version") or "1.0.0"),
            connector_id=str(d.get("connector_id") or ""),
            transport=str(d.get("transport") or "local_simulator"),
            base_endpoint_class=str(d.get("base_endpoint_class") or "loopback"),
            environment=str(d.get("environment") or "test"),
            auth_profile=str(d.get("auth_profile") or "none"),
            capabilities=tuple(d.get("capabilities") or ()),
            side_effect_class=str(d.get("side_effect_class") or ProviderSideEffectClass.READ_ONLY.value),
            rate_limit_profile=str(d.get("rate_limit_profile") or "default"),
            data_classification=str(d.get("data_classification") or DataClassification.PUBLIC.value),
            display_name=str(d.get("display_name") or ""),
        )


# ── Provider execution context (input to the adapter boundary) ───────────────
@dataclass
class ProviderExecutionContext:
    connector_id: str
    provider_id: str
    operation: str
    request_id: str = ""
    idempotency_key: str = ""
    deadline: float = 5.0            # total deadline seconds (bounded)
    approved_capabilities: tuple[str, ...] = ()
    account_link: str = ""           # empty for credential-free pilot
    credential_lease: str = ""       # empty for credential-free pilot
    safe_metadata: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    mode: str = ExecutionMode.SIMULATION.value

    def __post_init__(self) -> None:
        if isinstance(self.approved_capabilities, list):
            self.approved_capabilities = tuple(self.approved_capabilities)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Provider adapter result (output of the adapter boundary) ─────────────────
@dataclass
class ProviderAdapterResult:
    status: str
    provider_id: str = ""
    operation: str = ""
    provider_request_id_safe: str = ""
    normalized_data: dict[str, Any] = field(default_factory=dict)
    safe_metadata: dict[str, Any] = field(default_factory=dict)
    rate_limit: Optional[dict[str, Any]] = None
    latency_ms: float = 0.0
    retryability: str = RetryCategory.NO_RETRY.value
    side_effect_class: str = ProviderSideEffectClass.READ_ONLY.value
    evidence_refs: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    error_code: str = ""
    safe_message: str = ""
    attempts: int = 0
    mode: str = ExecutionMode.SIMULATION.value
    authoritative: bool = False   # SHADOW/SIMULATION output is never authoritative
    request_fingerprint: str = ""

    @property
    def ok(self) -> bool:
        return self.status in (ProviderStatus.SUCCESS.value, ProviderStatus.DRY_RUN.value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Provider incident + event taxonomies (safe strings only)
PROVIDER_EVENTS = frozenset({
    "provider.adapter_registered",
    "provider.verification_started",
    "provider.verification_completed",
    "provider.verification_stale",
    "provider.shadow_started",
    "provider.shadow_completed",
    "provider.rate_limited",
    "provider.degraded",
    "provider.unavailable",
    "provider.quarantined",
    "provider.recovered",
    "provider.response_rejected",
    "provider.redaction_blocked",
})

PROVIDER_INCIDENT_TYPES = frozenset({
    "provider_contract_violation",
    "provider_secret_leak",
    "provider_response_oversized",
    "provider_response_malformed",
    "provider_identity_mismatch",
    "provider_rate_limit_exhausted",
    "provider_retry_budget_exhausted",
    "provider_timeout",
    "provider_quarantined",
    "provider_shadow_policy_violation",
    "provider_unapproved_side_effect",
    "provider_endpoint_policy_violation",
})
