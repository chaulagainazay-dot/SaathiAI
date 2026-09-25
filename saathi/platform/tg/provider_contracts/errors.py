"""Provider-independent error taxonomy for offline provider contracts."""
from __future__ import annotations

from enum import Enum
from typing import Any


class ProviderErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    INVALID_RESPONSE = "invalid_response"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    CAPABILITY_FORBIDDEN = "capability_forbidden"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"
    FIXTURE_MISSING = "fixture_missing"
    FIXTURE_CONFLICT = "fixture_conflict"
    TIMEOUT_SIMULATION = "timeout_simulation"
    REPLAY_INTEGRITY_FAILURE = "replay_integrity_failure"
    INVALID_SESSION_STATE = "invalid_session_state"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    TRANSPORT_FORBIDDEN = "transport_forbidden"
    CONTRACT_VIOLATION = "contract_violation"

    # Backward-compatible symbolic aliases for the first draft of M320–M327.
    TIMEOUT = "timeout_simulation"
    UNAVAILABLE = "provider_unavailable"
    UNSUPPORTED = "unsupported_capability"
    CAPABILITY_DENIED = "capability_forbidden"
    REPLAY_MISS = "fixture_missing"
    SESSION_UNAVAILABLE = "invalid_session_state"


RETRYABLE_CODES = frozenset({
    ProviderErrorCode.TIMEOUT_SIMULATION,
    ProviderErrorCode.PROVIDER_UNAVAILABLE,
    ProviderErrorCode.TRANSPORT_UNAVAILABLE,
})


class ProviderContractError(ValueError):
    def __init__(
        self,
        code: ProviderErrorCode | str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ):
        self.code = ProviderErrorCode(code)
        self.message = message
        self.details = details or {}
        super().__init__(f"{self.code.value}: {message}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.code in RETRYABLE_CODES,
            "details": dict(self.details),
            "provider_independent": True,
        }


def normalize_error(exc: Exception) -> ProviderContractError:
    if isinstance(exc, ProviderContractError):
        return exc
    if isinstance(exc, TimeoutError):
        return ProviderContractError(
            ProviderErrorCode.TIMEOUT_SIMULATION,
            "Synthetic offline timeout was simulated",
        )
    if isinstance(exc, ConnectionError):
        return ProviderContractError(
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            "Offline provider is unavailable",
        )
    if isinstance(exc, NotImplementedError):
        return ProviderContractError(
            ProviderErrorCode.UNSUPPORTED_CAPABILITY,
            "Provider operation is unsupported",
        )
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return ProviderContractError(ProviderErrorCode.INVALID_REQUEST, "Provider request is invalid")
    return ProviderContractError(
        ProviderErrorCode.CONTRACT_VIOLATION,
        "Provider contract failed closed",
    )
