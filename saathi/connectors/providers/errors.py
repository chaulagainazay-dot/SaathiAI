"""M32 — Provider error taxonomy classification + retry mapping.

Provider error messages are always redacted and bounded before they surface.
Never include tokens, keys, cookies, authorization headers, raw account ids,
raw provider HTML, or huge bodies.
"""
from __future__ import annotations

from typing import Optional

from saathi.connectors.gov.redaction import redact_text
from saathi.connectors.providers.models import ProviderErrorCode, RetryCategory


class ProviderError(Exception):
    """Adapter-internal error carrying a canonical code."""

    def __init__(self, code: ProviderErrorCode, message: str = "", *, retry_after: Optional[float] = None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(f"{code.value}:{message[:120]}")


# HTTP status → canonical error code
_STATUS_MAP: dict[int, ProviderErrorCode] = {
    400: ProviderErrorCode.INVALID_REQUEST,
    401: ProviderErrorCode.AUTHENTICATION_FAILED,
    403: ProviderErrorCode.AUTHORIZATION_FAILED,
    404: ProviderErrorCode.NOT_FOUND,
    409: ProviderErrorCode.CONFLICT,
    422: ProviderErrorCode.INVALID_REQUEST,
    429: ProviderErrorCode.RATE_LIMITED,
    500: ProviderErrorCode.PROVIDER_UNAVAILABLE,
    502: ProviderErrorCode.PROVIDER_UNAVAILABLE,
    503: ProviderErrorCode.PROVIDER_UNAVAILABLE,
    504: ProviderErrorCode.TIMEOUT,
}

# Canonical error code → retry category (deterministic)
_RETRY_MAP: dict[ProviderErrorCode, RetryCategory] = {
    ProviderErrorCode.AUTHENTICATION_FAILED: RetryCategory.REAUTH_REQUIRED,
    ProviderErrorCode.AUTHORIZATION_FAILED: RetryCategory.NO_RETRY,
    ProviderErrorCode.SCOPE_INSUFFICIENT: RetryCategory.NO_RETRY,
    ProviderErrorCode.RATE_LIMITED: RetryCategory.RATE_LIMITED,
    ProviderErrorCode.TIMEOUT: RetryCategory.SAFE_RETRY,
    ProviderErrorCode.CONNECTION_FAILED: RetryCategory.SAFE_RETRY,
    ProviderErrorCode.PROVIDER_UNAVAILABLE: RetryCategory.PROVIDER_UNAVAILABLE,
    ProviderErrorCode.MALFORMED_RESPONSE: RetryCategory.NO_RETRY,
    ProviderErrorCode.INVALID_REQUEST: RetryCategory.NO_RETRY,
    ProviderErrorCode.NOT_FOUND: RetryCategory.NO_RETRY,
    ProviderErrorCode.CONFLICT: RetryCategory.NO_RETRY,
    ProviderErrorCode.DUPLICATE: RetryCategory.NO_RETRY,
    ProviderErrorCode.PARTIAL_SUCCESS: RetryCategory.NO_RETRY,
    ProviderErrorCode.CANCELLED: RetryCategory.CANCELLED,
    ProviderErrorCode.POLICY_BLOCKED: RetryCategory.POLICY_BLOCKED,
    ProviderErrorCode.INTERNAL_ADAPTER_ERROR: RetryCategory.NO_RETRY,
    ProviderErrorCode.UNKNOWN_PROVIDER_ERROR: RetryCategory.NO_RETRY,
}


def classify_status(status_code: int) -> ProviderErrorCode:
    """Map an HTTP-style status to a canonical error code (fail closed to unknown)."""
    if 200 <= status_code < 300:
        # Callers should not classify success here; treat as invalid usage.
        return ProviderErrorCode.UNKNOWN_PROVIDER_ERROR
    return _STATUS_MAP.get(int(status_code), ProviderErrorCode.UNKNOWN_PROVIDER_ERROR)


def classify_exception(exc: BaseException) -> ProviderErrorCode:
    """Map a raw exception to a canonical error code."""
    if isinstance(exc, ProviderError):
        return exc.code
    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError) or "timeout" in name:
        return ProviderErrorCode.TIMEOUT
    if isinstance(exc, (ConnectionError,)) or "connection" in name:
        return ProviderErrorCode.CONNECTION_FAILED
    if "cancel" in name:
        return ProviderErrorCode.CANCELLED
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return ProviderErrorCode.MALFORMED_RESPONSE
    return ProviderErrorCode.UNKNOWN_PROVIDER_ERROR


def retry_category_for(code: ProviderErrorCode) -> RetryCategory:
    return _RETRY_MAP.get(code, RetryCategory.NO_RETRY)


def safe_error_message(code: ProviderErrorCode, raw: str = "") -> str:
    """Bounded, redacted, secret-free error message."""
    base = code.value
    if not raw:
        return base
    return f"{base}: {redact_text(str(raw), max_len=160)}"
