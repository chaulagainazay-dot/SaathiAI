"""Risk engine domain models and reason codes."""
from __future__ import annotations

import time as _time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from saathi.platform.fund_ledger.money import D, q_money, q_price, q_qty


class RiskState(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    BREACHED = "BREACHED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class LimitSeverity(str, Enum):
    HARD_LIMIT = "HARD_LIMIT"
    SOFT_WARNING = "SOFT_WARNING"
    INFORMATIONAL = "INFORMATIONAL"


class RiskResult(str, Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


# Deterministic reason codes (agents may translate later)
REASON_MAX_POSITION_WEIGHT_EXCEEDED = "MAX_POSITION_WEIGHT_EXCEEDED"
REASON_MAX_TOP3_CONCENTRATION = "MAX_TOP3_CONCENTRATION"
REASON_MAX_TOP5_CONCENTRATION = "MAX_TOP5_CONCENTRATION"
REASON_DAILY_LOSS_LIMIT_EXCEEDED = "DAILY_LOSS_LIMIT_EXCEEDED"
REASON_WEEKLY_LOSS_LIMIT_EXCEEDED = "WEEKLY_LOSS_LIMIT_EXCEEDED"
REASON_MAX_DRAWDOWN_EXCEEDED = "MAX_DRAWDOWN_EXCEEDED"
REASON_MIN_CASH_BUFFER_BREACH = "MIN_CASH_BUFFER_BREACH"
REASON_GROSS_EXPOSURE_LIMIT = "GROSS_EXPOSURE_LIMIT"
REASON_NET_EXPOSURE_LIMIT = "NET_EXPOSURE_LIMIT"
REASON_MAX_TRADE_NOTIONAL = "MAX_TRADE_NOTIONAL"
REASON_STALE_MARKET_DATA = "STALE_MARKET_DATA"
REASON_LEDGER_UNRECONCILED = "LEDGER_UNRECONCILED"
REASON_NAV_MISSING = "NAV_MISSING"
REASON_PRICE_MISSING = "PRICE_MISSING"
REASON_INVALID_QUANTITY = "INVALID_QUANTITY"
REASON_INVALID_STOP = "INVALID_STOP"
REASON_BUDGET_INVALID = "BUDGET_INVALID"
REASON_LEVERAGE_DISABLED = "LEVERAGE_DISABLED"
REASON_SHORTS_DISABLED = "SHORTS_DISABLED"
REASON_STRESS_LOSS_INFORMATIONAL = "STRESS_LOSS_INFORMATIONAL"


@dataclass
class LimitEvaluation:
    name: str
    severity: LimitSeverity
    value: Decimal
    limit: Decimal
    breached: bool
    warning: bool
    reason_code: str
    detail: str = ""

    def to_public(self) -> dict:
        return {
            "name": self.name,
            "severity": self.severity.value,
            "value": str(q_money(self.value) if abs(self.value) >= Decimal("0.0001") else self.value),
            "limit": str(self.limit),
            "breached": self.breached,
            "warning": self.warning,
            "reason_code": self.reason_code,
            "detail": self.detail,
        }


@dataclass
class TradeProposal:
    """Proposed PAPER trade for impact evaluation (not an order)."""

    symbol: str
    side: str  # BUY / SELL
    quantity: Decimal
    price: Decimal
    stop_price: Decimal | None = None
    security_id: str = ""

    def to_public(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side.upper(),
            "quantity": str(q_qty(self.quantity)),
            "price": str(q_price(self.price)),
            "stop_price": str(q_price(self.stop_price)) if self.stop_price is not None else None,
            "security_id": self.security_id or f"sec_{self.symbol.upper()}_PAPER",
        }


@dataclass
class RiskDecision:
    decision_id: str
    result: RiskResult
    risk_state: RiskState
    timestamp: float
    budget_version: str
    fund_id: str
    metrics: dict[str, Any]
    limits_evaluated: list[LimitEvaluation]
    breaches: list[dict]
    warnings: list[dict]
    reason_codes: list[str]
    proposal: dict | None = None
    projected: dict | None = None
    mode: str = "PAPER"
    live_execution: str = "UNAVAILABLE"
    authorizes_execution: bool = False

    def to_public(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "result": self.result.value,
            "risk_state": self.risk_state.value,
            "timestamp": self.timestamp,
            "budget_version": self.budget_version,
            "fund_id": self.fund_id,
            "metrics": self.metrics,
            "limits_evaluated": [x.to_public() for x in self.limits_evaluated],
            "breaches": self.breaches,
            "warnings": self.warnings,
            "reason_codes": list(self.reason_codes),
            "proposal": self.proposal,
            "projected": self.projected,
            "mode": self.mode,
            "live_execution": self.live_execution,
            "authorizes_execution": False,
            "label": "PAPER RISK",
        }


def new_decision_id() -> str:
    return f"rsk_{uuid.uuid4().hex[:16]}"


def now_ts() -> float:
    return _time.time()
