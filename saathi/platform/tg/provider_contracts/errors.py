"""Provider-independent error taxonomy for offline provider contracts."""
from __future__ import annotations

from enum import Enum
from typing import Any


class ProviderErrorCode(str, Enum):
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    INVALID_REQUEST = "invalid_request"
    CAPABILITY_DENIED = "capability_denied"
    REPLAY_MISS = "replay_miss"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    SESSION_UNAVAILABLE = "session_unavailable"
    TRANSPORT_FORBIDDEN = "transport_forbidden"
    CONTRACT_VIOLATION = "contract_violation"


RETRYABLE_CODES = frozenset({
    ProviderErrorCode.TIMEOUT,
    ProviderErrorCode.UNAVAILABLE,
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
        return ProviderContractError(ProviderErrorCode.TIMEOUT, "Offline provider request timed out")
    if isinstance(exc, ConnectionError):
        return ProviderContractError(ProviderErrorCode.UNAVAILABLE, "Offline provider is unavailable")
    if isinstance(exc, NotImplementedError):
        return ProviderContractError(ProviderErrorCode.UNSUPPORTED, "Provider operation is unsupported")
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return ProviderContractError(ProviderErrorCode.INVALID_REQUEST, "Provider request is invalid")
    return ProviderContractError(
        ProviderErrorCode.CONTRACT_VIOLATION,
        "Provider contract failed closed",
    )
