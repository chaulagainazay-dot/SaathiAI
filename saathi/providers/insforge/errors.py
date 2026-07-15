"""Stable error categories for InsForge pilot (no secrets in messages)."""
from __future__ import annotations

from enum import Enum


class InsForgeErrorCategory(str, Enum):
    PROVIDER_DISABLED = "provider_disabled"
    CONFIGURATION_INVALID = "configuration_invalid"
    AUTHENTICATION_FAILED = "authentication_failed"
    PERMISSION_DENIED = "permission_denied"
    CONNECTION_FAILED = "connection_failed"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    RESPONSE_TOO_LARGE = "response_too_large"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    SECURITY_POLICY_DENIED = "security_policy_denied"
    SANITIZATION_FAILED = "sanitization_failed"
    WRITE_FORBIDDEN = "write_forbidden"


class InsForgeError(Exception):
    """Typed failure; ``detail`` must never contain credentials."""

    def __init__(
        self,
        category: InsForgeErrorCategory | str,
        detail: str = "",
        *,
        status_code: int | None = None,
    ):
        if isinstance(category, InsForgeErrorCategory):
            self.category = category
        else:
            try:
                self.category = InsForgeErrorCategory(category)
            except ValueError:
                self.category = InsForgeErrorCategory.PROVIDER_UNAVAILABLE
        self.detail = (detail or "")[:300]
        self.status_code = status_code
        super().__init__(f"{self.category.value}: {self.detail}")

    def to_dict(self) -> dict:
        return {
            "ok": False,
            "error_category": self.category.value,
            "detail": self.detail,
            "status_code": self.status_code,
        }
