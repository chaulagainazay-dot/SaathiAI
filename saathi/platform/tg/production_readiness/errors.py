"""Normalized error surface for the M328–M335 operations layer."""
from __future__ import annotations

from enum import Enum
from typing import Any

from saathi.platform.tg.production_readiness.models import (
    BOUNDARY_VALUES,
    SCHEMA_VERSION,
)


class OperationsErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    COMPONENT_UNKNOWN = "component_unknown"
    ALERT_UNKNOWN = "alert_unknown"
    ALERT_TRANSITION_INVALID = "alert_transition_invalid"
    SNAPSHOT_UNKNOWN = "snapshot_unknown"
    INTEGRITY_MISMATCH = "integrity_mismatch"
    DIAGNOSTIC_UNAVAILABLE = "diagnostic_unavailable"
    FORBIDDEN_DESTINATION = "forbidden_destination"
    FORBIDDEN_FIELD = "forbidden_field"
    FORBIDDEN_CONTROL = "forbidden_control"
    LOAD_PROFILE_UNKNOWN = "load_profile_unknown"
    INTERNAL = "internal"


RETRYABLE_CODES = frozenset({OperationsErrorCode.INTERNAL})


class OperationsError(Exception):
    def __init__(
        self,
        code: OperationsErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
            "retryable": self.code in RETRYABLE_CODES,
            "schema_version": SCHEMA_VERSION,
            "grants_authority": False,
        }


def normalize_error(exc: Exception) -> OperationsError:
    if isinstance(exc, OperationsError):
        return exc
    if isinstance(exc, (KeyError, ValueError, TypeError)):
        return OperationsError(
            OperationsErrorCode.INVALID_REQUEST,
            "Operations request was rejected",
            details={"exception": type(exc).__name__},
        )
    return OperationsError(
        OperationsErrorCode.INTERNAL,
        "Operations engine encountered an internal fault",
        details={"exception": type(exc).__name__},
    )


def error_envelope(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "error",
        "error": normalize_error(exc).to_dict(),
        "schema_version": SCHEMA_VERSION,
        **BOUNDARY_VALUES,
    }
