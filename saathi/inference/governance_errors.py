"""M24 — Typed provider-governance failures (privacy-safe codes)."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class GovernanceErrorCode(str, Enum):
    BUDGET_DENIED = "BUDGET_DENIED"
    RESERVATION_CONFLICT = "RESERVATION_CONFLICT"
    RESERVATION_EXPIRED = "RESERVATION_EXPIRED"
    RESERVATION_INVALID_STATE = "RESERVATION_INVALID_STATE"
    SETTLEMENT_CONFLICT = "SETTLEMENT_CONFLICT"
    COST_UNKNOWN = "COST_UNKNOWN"
    COST_CURRENCY_MISMATCH = "COST_CURRENCY_MISMATCH"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    HALF_OPEN_BUSY = "HALF_OPEN_BUSY"
    GOVERNANCE_STORE_UNAVAILABLE = "GOVERNANCE_STORE_UNAVAILABLE"
    GOVERNANCE_STATE_CONFLICT = "GOVERNANCE_STATE_CONFLICT"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    OPERATOR_AUTH_REQUIRED = "OPERATOR_AUTH_REQUIRED"
    OPERATOR_OVERRIDE_INVALID = "OPERATOR_OVERRIDE_INVALID"
    FLOAT_MONEY_REJECTED = "FLOAT_MONEY_REJECTED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"


class GovernanceError(Exception):
    """Fail-closed governance error. Never carries prompts/secrets."""

    def __init__(
        self,
        code: GovernanceErrorCode | str,
        message: str = "",
        *,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.code = code.value if isinstance(code, GovernanceErrorCode) else str(code)
        self.message = message or self.code
        self.details = dict(details or {})
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }
