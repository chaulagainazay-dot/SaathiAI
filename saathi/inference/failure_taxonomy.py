"""M21.2 — Typed inference failure taxonomy for retry/failover/circuit decisions.

Authentication and permission failures are never ordinary soft fallback.
Policy denials do not count as provider circuit failures.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


class FailureClass(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    TERMINAL = "terminal"


class FailureType(str, Enum):
    # Policy / hard denials
    UNKNOWN_CALLER = "unknown_caller"
    PROVIDER_NOT_ALLOWED = "provider_not_allowed"
    MODEL_NOT_ALLOWED = "model_not_allowed"
    CAPABILITY_NOT_SUPPORTED = "capability_not_supported"
    PRIVACY_DENIED = "privacy_denied"
    COST_DENIED = "cost_denied"
    CLOUD_DENIED = "cloud_denied"
    TOOL_DENIED = "tool_denied"
    STREAMING_DENIED = "streaming_denied"
    AUTHORIZATION_DENIED = "authorization_denied"
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    CIRCUIT_OPEN = "circuit_open"
    PRODUCTION_CERTIFICATION_REQUIRED = "production_certification_required"
    INVALID_REQUEST = "invalid_request"
    TRADING_ISOLATION = "trading_isolation"
    # Provider / runtime
    PROVIDER_UNREACHABLE = "provider_unreachable"
    PROVIDER_TIMEOUT = "provider_timeout"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION_FAILED = "authentication_failed"
    PERMISSION_FAILED = "permission_failed"
    MODEL_NOT_FOUND = "model_not_found"
    CONTEXT_LIMIT_EXCEEDED = "context_limit_exceeded"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    MALFORMED_RESPONSE = "malformed_response"
    STRUCTURED_OUTPUT_FAILED = "structured_output_failed"
    PROVIDER_INTERNAL_ERROR = "provider_internal_error"
    LOCAL_RUNTIME_UNAVAILABLE = "local_runtime_unavailable"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    CANCELLED = "cancelled"
    UNKNOWN_PROVIDER_ERROR = "unknown_provider_error"


@dataclass(frozen=True)
class FailureSpec:
    failure_type: FailureType
    failure_class: FailureClass
    retryable: bool
    same_provider_retry: bool
    failover_eligible: bool
    cloud_fallback_eligible: bool
    circuit_impact: bool  # counts toward provider circuit failures
    operator_message: str
    user_category: str
    telemetry_category: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["failure_type"] = self.failure_type.value
        d["failure_class"] = self.failure_class.value
        return d


def _spec(
    ft: FailureType,
    cls: FailureClass,
    *,
    retryable: bool,
    same: bool,
    failover: bool,
    cloud: bool,
    circuit: bool,
    op: str,
    user: str,
    telem: str,
) -> FailureSpec:
    return FailureSpec(
        failure_type=ft,
        failure_class=cls,
        retryable=retryable,
        same_provider_retry=same,
        failover_eligible=failover,
        cloud_fallback_eligible=cloud,
        circuit_impact=circuit,
        operator_message=op,
        user_category=user,
        telemetry_category=telem,
    )


# Canonical table
FAILURE_SPECS: dict[FailureType, FailureSpec] = {
    FailureType.UNKNOWN_CALLER: _spec(
        FailureType.UNKNOWN_CALLER, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Unknown caller denied", user="authorization", telem="policy_hard",
    ),
    FailureType.PROVIDER_NOT_ALLOWED: _spec(
        FailureType.PROVIDER_NOT_ALLOWED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Provider not allowed by policy", user="policy", telem="policy_hard",
    ),
    FailureType.MODEL_NOT_ALLOWED: _spec(
        FailureType.MODEL_NOT_ALLOWED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Model not allowed", user="policy", telem="policy_hard",
    ),
    FailureType.CAPABILITY_NOT_SUPPORTED: _spec(
        FailureType.CAPABILITY_NOT_SUPPORTED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Capability not supported", user="capability", telem="policy_hard",
    ),
    FailureType.PRIVACY_DENIED: _spec(
        FailureType.PRIVACY_DENIED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Privacy policy denied provider/request", user="privacy", telem="policy_hard",
    ),
    FailureType.COST_DENIED: _spec(
        FailureType.COST_DENIED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Cost policy denied", user="cost", telem="policy_hard",
    ),
    FailureType.CLOUD_DENIED: _spec(
        FailureType.CLOUD_DENIED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Cloud path denied", user="policy", telem="policy_hard",
    ),
    FailureType.TOOL_DENIED: _spec(
        FailureType.TOOL_DENIED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Tool use denied", user="capability", telem="policy_hard",
    ),
    FailureType.STREAMING_DENIED: _spec(
        FailureType.STREAMING_DENIED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Streaming denied", user="capability", telem="policy_hard",
    ),
    FailureType.AUTHORIZATION_DENIED: _spec(
        FailureType.AUTHORIZATION_DENIED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Authorization denied", user="authorization", telem="policy_hard",
    ),
    FailureType.KILL_SWITCH_ACTIVE: _spec(
        FailureType.KILL_SWITCH_ACTIVE, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Kill switch active", user="unavailable", telem="kill_switch",
    ),
    FailureType.CIRCUIT_OPEN: _spec(
        FailureType.CIRCUIT_OPEN, FailureClass.SOFT,
        retryable=False, same=False, failover=True, cloud=False, circuit=False,
        op="Circuit open for provider", user="unavailable", telem="circuit",
    ),
    FailureType.PRODUCTION_CERTIFICATION_REQUIRED: _spec(
        FailureType.PRODUCTION_CERTIFICATION_REQUIRED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Production certification required", user="policy", telem="policy_hard",
    ),
    FailureType.INVALID_REQUEST: _spec(
        FailureType.INVALID_REQUEST, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Invalid request", user="invalid", telem="policy_hard",
    ),
    FailureType.TRADING_ISOLATION: _spec(
        FailureType.TRADING_ISOLATION, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Trading isolation — inference cannot authorize trading",
        user="authorization", telem="trading_isolation",
    ),
    FailureType.PROVIDER_UNREACHABLE: _spec(
        FailureType.PROVIDER_UNREACHABLE, FailureClass.SOFT,
        retryable=True, same=True, failover=True, cloud=False, circuit=True,
        op="Provider unreachable", user="unavailable", telem="provider_soft",
    ),
    FailureType.PROVIDER_TIMEOUT: _spec(
        FailureType.PROVIDER_TIMEOUT, FailureClass.SOFT,
        retryable=True, same=True, failover=True, cloud=False, circuit=True,
        op="Provider timeout", user="timeout", telem="provider_soft",
    ),
    FailureType.RATE_LIMITED: _spec(
        FailureType.RATE_LIMITED, FailureClass.SOFT,
        retryable=True, same=True, failover=True, cloud=False, circuit=True,
        op="Rate limited", user="rate_limit", telem="provider_soft",
    ),
    # Auth: explicit — not ordinary soft fallback (could conceal bad credentials)
    FailureType.AUTHENTICATION_FAILED: _spec(
        FailureType.AUTHENTICATION_FAILED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=True,
        op="Authentication failed (no soft fallback)", user="authorization",
        telem="provider_auth",
    ),
    FailureType.PERMISSION_FAILED: _spec(
        FailureType.PERMISSION_FAILED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=True,
        op="Permission failed", user="authorization", telem="provider_auth",
    ),
    FailureType.MODEL_NOT_FOUND: _spec(
        FailureType.MODEL_NOT_FOUND, FailureClass.SOFT,
        retryable=False, same=False, failover=True, cloud=False, circuit=False,
        op="Model not found", user="unavailable", telem="provider_soft",
    ),
    # Context limit: do not failover blindly (incompatible replacement risk)
    FailureType.CONTEXT_LIMIT_EXCEEDED: _spec(
        FailureType.CONTEXT_LIMIT_EXCEEDED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Context limit exceeded", user="limit", telem="provider_limit",
    ),
    FailureType.OUTPUT_LIMIT_EXCEEDED: _spec(
        FailureType.OUTPUT_LIMIT_EXCEEDED, FailureClass.HARD,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Output limit exceeded", user="limit", telem="provider_limit",
    ),
    FailureType.MALFORMED_RESPONSE: _spec(
        FailureType.MALFORMED_RESPONSE, FailureClass.SOFT,
        retryable=True, same=True, failover=True, cloud=False, circuit=True,
        op="Malformed provider response", user="error", telem="provider_soft",
    ),
    FailureType.STRUCTURED_OUTPUT_FAILED: _spec(
        FailureType.STRUCTURED_OUTPUT_FAILED, FailureClass.SOFT,
        retryable=True, same=True, failover=True, cloud=False, circuit=True,
        op="Structured output failed", user="error", telem="provider_soft",
    ),
    FailureType.PROVIDER_INTERNAL_ERROR: _spec(
        FailureType.PROVIDER_INTERNAL_ERROR, FailureClass.SOFT,
        retryable=True, same=True, failover=True, cloud=False, circuit=True,
        op="Provider internal error", user="error", telem="provider_soft",
    ),
    FailureType.LOCAL_RUNTIME_UNAVAILABLE: _spec(
        FailureType.LOCAL_RUNTIME_UNAVAILABLE, FailureClass.SOFT,
        retryable=True, same=True, failover=True, cloud=False, circuit=True,
        op="Local runtime unavailable", user="unavailable", telem="provider_soft",
    ),
    FailureType.RESOURCE_EXHAUSTED: _spec(
        FailureType.RESOURCE_EXHAUSTED, FailureClass.SOFT,
        retryable=True, same=False, failover=True, cloud=False, circuit=True,
        op="Resource exhausted", user="unavailable", telem="provider_soft",
    ),
    FailureType.CANCELLED: _spec(
        FailureType.CANCELLED, FailureClass.TERMINAL,
        retryable=False, same=False, failover=False, cloud=False, circuit=False,
        op="Cancelled", user="cancelled", telem="cancelled",
    ),
    FailureType.UNKNOWN_PROVIDER_ERROR: _spec(
        FailureType.UNKNOWN_PROVIDER_ERROR, FailureClass.SOFT,
        retryable=False, same=False, failover=False, cloud=False, circuit=True,
        op="Unknown provider error (conservative)", user="error", telem="provider_unknown",
    ),
}


def get_failure_spec(failure_type: FailureType | str) -> FailureSpec:
    if isinstance(failure_type, str):
        try:
            failure_type = FailureType(failure_type)
        except ValueError:
            return FAILURE_SPECS[FailureType.UNKNOWN_PROVIDER_ERROR]
    return FAILURE_SPECS.get(failure_type, FAILURE_SPECS[FailureType.UNKNOWN_PROVIDER_ERROR])


_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]+"),
    re.compile(r"sk-[a-zA-Z0-9]{10,}"),
)


def redact_error_message(message: str, *, max_len: int = 240) -> str:
    text = str(message or "")
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    text = text.replace("\n", " ").strip()
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def classify_exception(exc: BaseException, *, provider: str = "") -> FailureType:
    """Map runtime exceptions to taxonomy (conservative defaults)."""
    text = str(exc).lower()
    name = type(exc).__name__.lower()
    if "timeout" in text or "timed out" in text or isinstance(exc, TimeoutError):
        return FailureType.PROVIDER_TIMEOUT
    if any(m in text for m in ("connection refused", "unreachable", "connect error", "name or service")):
        return FailureType.PROVIDER_UNREACHABLE
    if "429" in text or "rate limit" in text or "too many requests" in text:
        return FailureType.RATE_LIMITED
    if "401" in text or "unauthorized" in text or "invalid api key" in text or "authentication" in text:
        return FailureType.AUTHENTICATION_FAILED
    if "403" in text or "forbidden" in text or "permission" in text:
        return FailureType.PERMISSION_FAILED
    if "model not found" in text or "not found" in text and "model" in text:
        return FailureType.MODEL_NOT_FOUND
    if "context" in text and ("limit" in text or "length" in text or "too long" in text):
        return FailureType.CONTEXT_LIMIT_EXCEEDED
    if "cancelled" in text or name == "cancellederror":
        return FailureType.CANCELLED
    return FailureType.UNKNOWN_PROVIDER_ERROR


def taxonomy_snapshot() -> dict[str, Any]:
    return {
        "schema": "m21.2.failure_taxonomy.v1",
        "milestone": "M21.2",
        "count": len(FAILURE_SPECS),
        "failures": {k.value: v.to_dict() for k, v in FAILURE_SPECS.items()},
        "hard_never_fallback": sorted(
            ft.value for ft, s in FAILURE_SPECS.items() if not s.failover_eligible and s.failure_class is FailureClass.HARD
        ),
        "retryable": sorted(ft.value for ft, s in FAILURE_SPECS.items() if s.retryable),
        "circuit_impact": sorted(ft.value for ft, s in FAILURE_SPECS.items() if s.circuit_impact),
    }
