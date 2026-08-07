"""M62.5 — paper-trading domain models (durable, decimal-precise, PAPER-only).

Reuses the M62.1 canonical trading domain (`saathi.platform.trading_models`):
``OrderIntent`` remains the platform-level proposed action and stays Trading
Guardian-compatible. This module adds the *broker-level* durable objects that come
into existence ONLY after every authorization gate passes: ``PaperAccount``,
``PaperOrder``, ``PaperFill``, plus the reservation, fee, and slippage primitives.

Hard boundaries (fail-closed, enforced by :func:`assert_paper_safe`):
  * environment is always ``Environment.PAPER`` — never LIVE/PRODUCTION/REAL_MONEY;
  * long-only — no shorting, margin, leverage, borrowing, or derivatives;
  * no broker credentials, no provider keys, no network — simulation only.

Nothing here opens a socket, holds a secret, or reaches a real broker. A fill is a
simulation event, not a live trade.
"""
from __future__ import annotations

import hashlib
import json
import time as _time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from saathi.platform.trading_models import (
    D, Environment, OrderSide, OrderType, TimeInForce,
)

ENGINE_VERSION = "paper-broker/1.0.0"
CALENDAR = "DEFAULT_24_5"


def q2(v: Any) -> Decimal:
    return D(v).quantize(Decimal("0.01"))


def q6(v: Any) -> Decimal:
    return D(v).quantize(Decimal("0.000001"))


# ── prohibited configuration tokens (executable fail-closed guard) ───────────
PROHIBITED_CONFIG_TOKENS = frozenset({
    "LIVE", "PRODUCTION", "REAL_MONEY", "LIVE_BROKER", "LEVERAGE", "MARGIN",
    "SHORT_SELLING", "SHORT", "OPTIONS", "FUTURES", "PERPETUALS", "DERIVATIVES",
    "BORROWING",
})


class PaperSafetyError(Exception):
    """Raised when a configuration attempts to enable a prohibited capability."""


def assert_paper_safe(config: dict | None = None, *, environment: Environment | str | None = None) -> None:
    """Fail closed: refuse any prohibited capability or non-PAPER environment."""
    if environment is not None:
        env = environment if isinstance(environment, Environment) else Environment(str(environment))
        if env != Environment.PAPER:
            raise PaperSafetyError(f"paper broker operates only in PAPER (got {env.value})")
    cfg = config or {}
    for key, value in cfg.items():
        token = str(key).upper()
        if token in PROHIBITED_CONFIG_TOKENS and bool(value):
            raise PaperSafetyError(f"prohibited capability enabled: {token}")
        if isinstance(value, str) and value.upper() in PROHIBITED_CONFIG_TOKENS:
            raise PaperSafetyError(f"prohibited capability referenced: {value.upper()}")


# ── enums ─────────────────────────────────────────────────────────────────────
class AccountStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    HALTED = "HALTED"
    CLOSED = "CLOSED"


ACCOUNT_TRANSITIONS: dict[AccountStatus, frozenset[AccountStatus]] = {
    AccountStatus.DRAFT: frozenset({AccountStatus.ACTIVE, AccountStatus.CLOSED}),
    AccountStatus.ACTIVE: frozenset({AccountStatus.HALTED, AccountStatus.CLOSED}),
    AccountStatus.HALTED: frozenset({AccountStatus.ACTIVE, AccountStatus.CLOSED}),
    AccountStatus.CLOSED: frozenset(),
}


def can_account_transition(cur: AccountStatus, tgt: AccountStatus) -> bool:
    return tgt in ACCOUNT_TRANSITIONS.get(cur, frozenset())


class BrokerOrderState(str, Enum):
    PENDING_VALIDATION = "PENDING_VALIDATION"
    ACCEPTED = "ACCEPTED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


BROKER_TERMINAL_STATES = frozenset({
    BrokerOrderState.FILLED, BrokerOrderState.CANCELLED,
    BrokerOrderState.REJECTED, BrokerOrderState.EXPIRED, BrokerOrderState.FAILED,
})

BROKER_TRANSITIONS: dict[BrokerOrderState, frozenset[BrokerOrderState]] = {
    BrokerOrderState.PENDING_VALIDATION: frozenset({
        BrokerOrderState.ACCEPTED, BrokerOrderState.REJECTED, BrokerOrderState.FAILED}),
    BrokerOrderState.ACCEPTED: frozenset({
        BrokerOrderState.OPEN, BrokerOrderState.PARTIALLY_FILLED, BrokerOrderState.FILLED,
        BrokerOrderState.CANCEL_PENDING, BrokerOrderState.REJECTED, BrokerOrderState.EXPIRED,
        BrokerOrderState.FAILED}),
    BrokerOrderState.OPEN: frozenset({
        BrokerOrderState.PARTIALLY_FILLED, BrokerOrderState.FILLED, BrokerOrderState.CANCEL_PENDING,
        BrokerOrderState.CANCELLED, BrokerOrderState.EXPIRED, BrokerOrderState.FAILED}),
    BrokerOrderState.PARTIALLY_FILLED: frozenset({
        BrokerOrderState.PARTIALLY_FILLED, BrokerOrderState.FILLED, BrokerOrderState.CANCEL_PENDING,
        BrokerOrderState.CANCELLED, BrokerOrderState.EXPIRED, BrokerOrderState.FAILED}),
    BrokerOrderState.CANCEL_PENDING: frozenset({
        BrokerOrderState.CANCELLED, BrokerOrderState.FILLED, BrokerOrderState.PARTIALLY_FILLED,
        BrokerOrderState.FAILED}),
    # terminal
    BrokerOrderState.FILLED: frozenset(),
    BrokerOrderState.CANCELLED: frozenset(),
    BrokerOrderState.REJECTED: frozenset(),
    BrokerOrderState.EXPIRED: frozenset(),
    BrokerOrderState.FAILED: frozenset(),
}


def can_broker_transition(cur: BrokerOrderState | str, tgt: BrokerOrderState | str) -> bool:
    c = cur if isinstance(cur, BrokerOrderState) else BrokerOrderState(cur)
    t = tgt if isinstance(tgt, BrokerOrderState) else BrokerOrderState(tgt)
    return t in BROKER_TRANSITIONS.get(c, frozenset())


# ── fee & slippage models (versioned, deterministic) ────────────────────────
@dataclass(frozen=True)
class FeeModel:
    version: str = "fee/1.0.0"
    fixed: Decimal = field(default_factory=lambda: Decimal("0"))
    pct: Decimal = field(default_factory=lambda: Decimal("0"))          # fraction of notional
    per_unit: Decimal = field(default_factory=lambda: Decimal("0"))
    minimum: Decimal = field(default_factory=lambda: Decimal("0"))

    def fee(self, *, quantity: Decimal, price: Decimal) -> Decimal:
        notional = D(quantity) * D(price)
        raw = self.fixed + (self.pct * notional) + (self.per_unit * D(quantity))
        return q2(max(raw, self.minimum) if (D(quantity) > 0) else Decimal("0"))

    def to_public(self) -> dict[str, Any]:
        return {"version": self.version, "fixed": str(self.fixed), "pct": str(self.pct),
                "per_unit": str(self.per_unit), "minimum": str(self.minimum)}


@dataclass(frozen=True)
class SlippageModel:
    version: str = "slip/1.0.0"
    bps: Decimal = field(default_factory=lambda: Decimal("0"))          # basis points on reference price
    spread_aware: bool = True
    max_volume_participation: Decimal = field(default_factory=lambda: Decimal("0.25"))

    def adjust(self, *, side: OrderSide, reference: Decimal, spread: Decimal | None) -> Decimal:
        """Deterministic adverse price adjustment. BUY pays up, SELL receives less."""
        ref = D(reference)
        move = ref * (self.bps / Decimal("10000"))
        if self.spread_aware and spread is not None and spread > 0:
            move += D(spread) / Decimal("2")
        return q6(ref + move) if side == OrderSide.BUY else q6(ref - move)

    def to_public(self) -> dict[str, Any]:
        return {"version": self.version, "bps": str(self.bps), "spread_aware": self.spread_aware,
                "max_volume_participation": str(self.max_volume_participation)}


# Named, versioned tiers (analogous to strategy cost tiers, but broker-durable).
ZERO_FEE = FeeModel(version="fee/zero", fixed=Decimal("0"), pct=Decimal("0"))
REALISTIC_FEE = FeeModel(version="fee/realistic", fixed=Decimal("0"), pct=Decimal("0.0005"), minimum=Decimal("1"))
ZERO_SLIP = SlippageModel(version="slip/zero", bps=Decimal("0"), spread_aware=False)
REALISTIC_SLIP = SlippageModel(version="slip/realistic", bps=Decimal("5"), spread_aware=True)


# ── durable account ──────────────────────────────────────────────────────────
@dataclass
class PaperAccount:
    id: str
    org_id: str
    workspace_id: str
    project_id: str
    name: str
    base_currency: str
    starting_cash: Decimal
    current_cash: Decimal
    reserved_cash: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    status: AccountStatus = AccountStatus.DRAFT
    environment: Environment = Environment.PAPER
    created_by: str = ""
    created_at: float = field(default_factory=_time.time)
    updated_at: float = field(default_factory=_time.time)
    version: int = 1

    @property
    def available_cash(self) -> Decimal:
        return q2(self.current_cash - self.reserved_cash)

    def to_public(self, *, unrealized_pnl: Decimal | None = None, positions_value: Decimal | None = None) -> dict[str, Any]:
        pv = q2(positions_value) if positions_value is not None else Decimal("0.00")
        equity = q2(self.current_cash + pv)
        out = {
            "id": self.id, "org_id": self.org_id, "workspace_id": self.workspace_id,
            "project_id": self.project_id, "name": self.name, "base_currency": self.base_currency,
            "starting_cash": str(q2(self.starting_cash)), "current_cash": str(q2(self.current_cash)),
            "reserved_cash": str(q2(self.reserved_cash)), "available_cash": str(self.available_cash),
            "realized_pnl": str(q2(self.realized_pnl)), "positions_value": str(pv),
            "total_equity": str(equity), "status": self.status.value, "environment": self.environment.value,
            "created_by": self.created_by, "created_at": self.created_at, "updated_at": self.updated_at,
            "version": self.version,
        }
        if unrealized_pnl is not None:
            out["unrealized_pnl"] = str(q2(unrealized_pnl))
        return out

    def state_hash(self) -> str:
        return _hash({"id": self.id, "cash": str(self.current_cash), "reserved": str(self.reserved_cash),
                      "realized": str(self.realized_pnl), "status": self.status.value, "version": self.version})


@dataclass
class PaperPosition:
    account_id: str
    symbol: str
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    reserved_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_cost: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def available_quantity(self) -> Decimal:
        return self.quantity - self.reserved_quantity

    def market_value(self, mark: Decimal) -> Decimal:
        return q2(self.quantity * D(mark))

    def unrealized_pnl(self, mark: Decimal) -> Decimal:
        return q2((D(mark) - self.avg_cost) * self.quantity)

    def to_public(self, mark: Decimal | None = None) -> dict[str, Any]:
        out = {"symbol": self.symbol, "quantity": str(self.quantity),
               "reserved_quantity": str(self.reserved_quantity), "available_quantity": str(self.available_quantity),
               "avg_cost": str(q2(self.avg_cost)), "realized_pnl": str(q2(self.realized_pnl))}
        if mark is not None:
            out["mark"] = str(q2(mark)); out["market_value"] = str(self.market_value(mark))
            out["unrealized_pnl"] = str(self.unrealized_pnl(mark))
        return out


# ── durable broker order ─────────────────────────────────────────────────────
@dataclass
class PaperOrder:
    id: str
    order_intent_id: str
    paper_account_id: str
    org_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    original_quantity: Decimal
    filled_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    limit_price: Decimal | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    broker_state: BrokerOrderState = BrokerOrderState.PENDING_VALIDATION
    rejection_reason: str = ""
    idempotency_key: str = ""
    reserved_cash: Decimal = field(default_factory=lambda: Decimal("0"))
    reserved_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    market_data_ref: str = ""
    correlation_id: str = ""
    submitted_at: float = field(default_factory=_time.time)
    accepted_at: float = 0.0
    cancelled_at: float = 0.0
    completed_at: float = 0.0
    version: int = 1

    @property
    def remaining_quantity(self) -> Decimal:
        return self.original_quantity - self.filled_quantity

    @property
    def is_terminal(self) -> bool:
        return self.broker_state in BROKER_TERMINAL_STATES

    def order_state_hash(self) -> str:
        return _hash({"id": self.id, "state": self.broker_state.value, "filled": str(self.filled_quantity),
                      "remaining": str(self.remaining_quantity), "version": self.version})

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id, "order_intent_id": self.order_intent_id, "paper_account_id": self.paper_account_id,
            "symbol": self.symbol, "side": self.side.value, "order_type": self.order_type.value,
            "original_quantity": str(self.original_quantity), "filled_quantity": str(self.filled_quantity),
            "remaining_quantity": str(self.remaining_quantity),
            "limit_price": str(self.limit_price) if self.limit_price is not None else None,
            "time_in_force": self.time_in_force.value, "broker_state": self.broker_state.value,
            "rejection_reason": self.rejection_reason, "idempotency_key": self.idempotency_key,
            "reserved_cash": str(q2(self.reserved_cash)), "reserved_quantity": str(self.reserved_quantity),
            "market_data_ref": self.market_data_ref, "correlation_id": self.correlation_id,
            "submitted_at": self.submitted_at, "accepted_at": self.accepted_at,
            "cancelled_at": self.cancelled_at, "completed_at": self.completed_at, "version": self.version,
        }


@dataclass
class PaperFill:
    id: str
    paper_order_id: str
    org_id: str
    event_ts: float
    quantity: Decimal
    price: Decimal
    gross_amount: Decimal
    fee: Decimal
    slippage: Decimal
    side: OrderSide
    liquidity_ref: str = ""
    market_data_ref: str = ""
    fee_model_version: str = ""
    slippage_model_version: str = ""
    result_hash: str = ""
    seq: int = 0
    created_at: float = field(default_factory=_time.time)

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id, "paper_order_id": self.paper_order_id, "event_ts": self.event_ts,
            "quantity": str(self.quantity), "price": str(q2(self.price)), "gross_amount": str(q2(self.gross_amount)),
            "fee": str(q2(self.fee)), "slippage": str(self.slippage), "side": self.side.value,
            "liquidity_ref": self.liquidity_ref, "market_data_ref": self.market_data_ref,
            "fee_model_version": self.fee_model_version, "slippage_model_version": self.slippage_model_version,
            "result_hash": self.result_hash, "seq": self.seq, "created_at": self.created_at,
        }


# ── deterministic hashing ────────────────────────────────────────────────────
def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def market_event_hash(event: dict) -> str:
    return _hash(event)


def fill_result_hash(*, engine_version: str, account_state_hash: str, order_state_hash: str,
                     market_event_hash: str, fee_model_version: str, slippage_model_version: str,
                     seed: int, calendar: str, quantity: Decimal, price: Decimal, fee: Decimal) -> str:
    return _hash({
        "engine": engine_version, "account": account_state_hash, "order": order_state_hash,
        "event": market_event_hash, "fee_model": fee_model_version, "slippage_model": slippage_model_version,
        "seed": seed, "calendar": calendar, "quantity": str(quantity), "price": str(price), "fee": str(fee),
    })
