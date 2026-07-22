"""Normalized inference errors (engine-layer, not governance)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


class InferenceError(Exception):
    """Base class for SaathiOS inference failures."""

    code: str = "inference_error"

    def __init__(self, message: str, *, cause: Optional[BaseException] = None):
        super().__init__(message)
        self.cause = cause


class EngineError(InferenceError):
    code = "engine_error"


class EngineTimeoutError(EngineError):
    code = "engine_timeout"


class EngineUnhealthyError(EngineError):
    code = "engine_unhealthy"


class EngineRetryExhausted(EngineError):
    code = "engine_retry_exhausted"


class CapabilityError(InferenceError):
    code = "capability_error"


class CatalogueError(InferenceError):
    code = "catalogue_error"


@dataclass(frozen=True)
class NormalizedError:
    code: str
    message: str
    retryable: bool
    provider: str = ""
    model: str = ""
    details: Optional[dict] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "provider": self.provider,
            "model": self.model,
            "details": self.details or {},
        }


_TIMEOUT_MARKERS = ("timeout", "timed out", "deadline exceeded")
_UNHEALTHY_MARKERS = ("connection refused", "connect error", "unreachable", "name or service not known")
_RATE_MARKERS = ("rate limit", "rate-limited", "429", "too many requests")


def normalize_error(
    exc: BaseException,
    *,
    provider: str = "",
    model: str = "",
) -> NormalizedError:
    """Map arbitrary exceptions into a stable shape for routing/observability."""
    if isinstance(exc, NormalizedError):
        return exc
    if isinstance(exc, InferenceError):
        retryable = isinstance(exc, (EngineTimeoutError, EngineUnhealthyError))
        return NormalizedError(
            code=getattr(exc, "code", "inference_error"),
            message=str(exc),
            retryable=retryable,
            provider=provider,
            model=model,
        )
    text = str(exc).lower()
    if any(m in text for m in _TIMEOUT_MARKERS) or isinstance(exc, TimeoutError):
        return NormalizedError(
            code="engine_timeout",
            message=str(exc),
            retryable=True,
            provider=provider,
            model=model,
        )
    if any(m in text for m in _UNHEALTHY_MARKERS):
        return NormalizedError(
            code="engine_unhealthy",
            message=str(exc),
            retryable=True,
            provider=provider,
            model=model,
        )
    if any(m in text for m in _RATE_MARKERS):
        return NormalizedError(
            code="rate_limited",
            message=str(exc),
            retryable=True,
            provider=provider,
            model=model,
        )
    return NormalizedError(
        code="engine_error",
        message=str(exc),
        retryable=False,
        provider=provider,
        model=model,
    )
