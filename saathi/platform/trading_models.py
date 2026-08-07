"""M62.1 — Canonical trading domain models (server-side, decimal-precise).

One authoritative representation for instruments, market data, orders, positions,
and accounts across the platform. Money / prices / quantities / fees / P&L use
``decimal.Decimal`` — never binary float — because financial correctness matters.

This module is PURE DATA + a validated order-intent state machine. It grants NO
execution authority, opens NO broker connection, and reaches NO network. Order
submission remains gated by approvals, Trading Guardian, PlatformAgentRuntime, and
ExecutionGateway (see docs/trading/AUTHORITY_MODEL.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any


def D(value: Any, default: str = "0") -> Decimal:
    """Coerce to Decimal via str (avoids binary-float contamination)."""
    try:
        if isinstance(value, Decimal):
            return value
        if value is None or value == "":
            return Decimal(default)
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


# ── enums ───────────────────────────────────────────────────────────────────
class Environment(str, Enum):
    MOCK = "MOCK"
    REPLAY = "REPLAY"
    SIMULATION = "SIMULATION"
    PAPER = "PAPER"
    SANDBOX = "SANDBOX"
    LIVE = "LIVE"


# Environments where NO real capital is ever at risk.
NON_LIVE_ENVIRONMENTS = frozenset({Environment.MOCK, Environment.REPLAY, Environment.SIMULATION, Environment.PAPER, Environment.SANDBOX})


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    ETF = "ETF"
    CRYPTO = "CRYPTO"
    CASH = "CASH"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class MarketState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HALTED = "HALTED"
    PRE = "PRE"
    POST = "POST"
    UNKNOWN = "UNKNOWN"


class DataQuality(str, Enum):
    VALID = "VALID"
    STALE = "STALE"
    INCOMPLETE = "INCOMPLETE"
    OUTLIER = "OUTLIER"
    GAPPED = "GAPPED"
    UNVERIFIED = "UNVERIFIED"
    PROVIDER_ERROR = "PROVIDER_ERROR"


# Only VALID market data may back a live/paper order.
TRADEABLE_QUALITY = frozenset({DataQuality.VALID})


class OrderState(str, Enum):
    DRAFT = "DRAFT"
    RESEARCH_COMPLETE = "RESEARCH_COMPLETE"
    STRATEGY_VALIDATED = "STRATEGY_VALIDATED"
    RISK_REVIEWED = "RISK_REVIEWED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    QUEUED = "QUEUED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    HALTED = "HALTED"


TERMINAL_ORDER_STATES = frozenset({
    OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED,
    OrderState.EXPIRED, OrderState.FAILED,
})

# Explicit, validated transitions. No order may jump from a recommendation
# straight to provider submission: the pre-submit chain must be walked in order.
ORDER_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.DRAFT: frozenset({OrderState.RESEARCH_COMPLETE, OrderState.FAILED}),
    OrderState.RESEARCH_COMPLETE: frozenset({OrderState.STRATEGY_VALIDATED, OrderState.FAILED}),
    OrderState.STRATEGY_VALIDATED: frozenset({OrderState.RISK_REVIEWED, OrderState.REJECTED, OrderState.FAILED}),
    OrderState.RISK_REVIEWED: frozenset({OrderState.APPROVAL_REQUIRED, OrderState.REJECTED, OrderState.FAILED}),
    OrderState.APPROVAL_REQUIRED: frozenset({OrderState.APPROVED, OrderState.REJECTED, OrderState.EXPIRED}),
    OrderState.APPROVED: frozenset({OrderState.QUEUED, OrderState.CANCELLED, OrderState.EXPIRED, OrderState.HALTED}),
    OrderState.QUEUED: frozenset({OrderState.SUBMITTING, OrderState.CANCELLED, OrderState.HALTED, OrderState.EXPIRED}),
    OrderState.SUBMITTING: frozenset({OrderState.SUBMITTED, OrderState.REJECTED, OrderState.FAILED, OrderState.RECONCILIATION_REQUIRED}),
    OrderState.SUBMITTED: frozenset({OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_REQUESTED, OrderState.REJECTED, OrderState.EXPIRED, OrderState.RECONCILIATION_REQUIRED, OrderState.HALTED}),
    OrderState.PARTIALLY_FILLED: frozenset({OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_REQUESTED, OrderState.CANCELLED, OrderState.RECONCILIATION_REQUIRED, OrderState.HALTED}),
    OrderState.CANCEL_REQUESTED: frozenset({OrderState.CANCELLED, OrderState.FILLED, OrderState.PARTIALLY_FILLED, OrderState.RECONCILIATION_REQUIRED}),
    OrderState.RECONCILIATION_REQUIRED: frozenset({OrderState.SUBMITTED, OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.FAILED, OrderState.HALTED}),
    OrderState.HALTED: frozenset({OrderState.QUEUED, OrderState.CANCELLED, OrderState.FAILED, OrderState.RECONCILIATION_REQUIRED}),
    # terminal
    OrderState.FILLED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.EXPIRED: frozenset(),
    OrderState.FAILED: frozenset(),
}


def can_transition(current: OrderState | str, target: OrderState | str) -> bool:
    c = OrderState(current) if not isinstance(current, OrderState) else current
    t = OrderState(target) if not isinstance(target, OrderState) else target
    return t in ORDER_TRANSITIONS.get(c, frozenset())


class ApprovalPurpose(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    BACKTEST = "BACKTEST"
    SIMULATION = "SIMULATION"
    PAPER_ORDER = "PAPER_ORDER"
    LIVE_ORDER = "LIVE_ORDER"          # remains disabled this milestone
    CANCEL_ORDER = "CANCEL_ORDER"
    CLOSE_POSITION = "CLOSE_POSITION"
    EMERGENCY_HALT = "EMERGENCY_HALT"


# Purposes an operator may exercise in M62 (LIVE_ORDER intentionally excluded).
M62_ENABLED_PURPOSES = frozenset({
    ApprovalPurpose.RESEARCH_ONLY, ApprovalPurpose.BACKTEST, ApprovalPurpose.SIMULATION,
    ApprovalPurpose.PAPER_ORDER, ApprovalPurpose.CANCEL_ORDER, ApprovalPurpose.CLOSE_POSITION,
    ApprovalPurpose.EMERGENCY_HALT,
})


# ── dataclasses ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Instrument:
    provider: str
    venue: str
    symbol: str
    asset_class: AssetClass
    base_currency: str = "USD"
    quote_currency: str = "USD"
    price_precision: int = 2
    quantity_precision: int = 0
    min_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    min_notional: Decimal = field(default_factory=lambda: Decimal("0"))
    tradable: bool = True

    def to_public(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "venue": self.venue, "symbol": self.symbol,
            "asset_class": self.asset_class.value, "base_currency": self.base_currency,
            "quote_currency": self.quote_currency, "price_precision": self.price_precision,
            "quantity_precision": self.quantity_precision, "min_quantity": str(self.min_quantity),
            "min_notional": str(self.min_notional), "tradable": self.tradable,
        }


@dataclass
class Quote:
    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    source: str
    source_ts: float          # provider timestamp
    ingest_ts: float          # when WE received it
    quality: DataQuality = DataQuality.UNVERIFIED

    def is_tradeable(self) -> bool:
        return self.quality in TRADEABLE_QUALITY

    def to_public(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "bid": str(self.bid), "ask": str(self.ask), "last": str(self.last),
                "source": self.source, "source_ts": self.source_ts, "ingest_ts": self.ingest_ts, "quality": self.quality.value}


@dataclass
class Bar:
    symbol: str
    ts: float
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str = ""
    quality: DataQuality = DataQuality.UNVERIFIED


@dataclass
class Position:
    symbol: str
    quantity: Decimal
    avg_price: Decimal
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))

    def notional(self, mark: Decimal) -> Decimal:
        return (self.quantity * mark).quantize(Decimal("0.01"))

    def unrealized_pnl(self, mark: Decimal) -> Decimal:
        return ((mark - self.avg_price) * self.quantity).quantize(Decimal("0.01"))


@dataclass
class Account:
    account_id: str
    environment: Environment
    cash: Decimal
    currency: str = "USD"
    positions: dict[str, Position] = field(default_factory=dict)

    def gross_exposure(self, marks: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for sym, pos in self.positions.items():
            total += abs(pos.notional(marks.get(sym, pos.avg_price)))
        return total.quantize(Decimal("0.01"))

    def equity(self, marks: dict[str, Decimal]) -> Decimal:
        eq = self.cash
        for sym, pos in self.positions.items():
            eq += pos.notional(marks.get(sym, pos.avg_price))
        return eq.quantize(Decimal("0.01"))


@dataclass
class OrderIntent:
    """A proposed order. Immutable identity fields + a validated state. It is NOT
    an order at a broker until it walks the full approved → submitted chain."""
    intent_id: str
    org_id: str
    workspace_id: str
    account_id: str
    environment: Environment
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    idempotency_key: str = ""
    approval_id: str = ""
    strategy_id: str = ""
    strategy_version: int = 0
    state: OrderState = OrderState.DRAFT
    version: int = 1
    audit_correlation_id: str = ""

    def transition(self, target: OrderState | str) -> None:
        t = OrderState(target) if not isinstance(target, OrderState) else target
        if not can_transition(self.state, t):
            raise ValueError(f"illegal order transition {self.state.value} -> {t.value}")
        self.state = t
        self.version += 1

    def estimated_notional(self, ref_price: Decimal) -> Decimal:
        px = self.limit_price if (self.order_type == OrderType.LIMIT and self.limit_price) else ref_price
        return (self.quantity * D(px)).quantize(Decimal("0.01"))

    def to_public(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id, "org_id": self.org_id, "workspace_id": self.workspace_id,
            "account_id": self.account_id, "environment": self.environment.value, "symbol": self.symbol,
            "side": self.side.value, "order_type": self.order_type.value, "quantity": str(self.quantity),
            "limit_price": str(self.limit_price) if self.limit_price is not None else None,
            "stop_price": str(self.stop_price) if self.stop_price is not None else None,
            "time_in_force": self.time_in_force.value, "idempotency_key": self.idempotency_key,
            "approval_id": self.approval_id, "strategy_id": self.strategy_id, "strategy_version": self.strategy_version,
            "state": self.state.value, "version": self.version, "audit_correlation_id": self.audit_correlation_id,
        }
