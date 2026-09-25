"""Canonical fund ledger domain models."""
from __future__ import annotations

import time as _time
import uuid
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from enum import Enum
from typing import Any

from saathi.platform.fund_ledger.money import D, q_money, q_price, q_qty


def new_event_id(prefix: str = "lev_") -> str:
    return f"{prefix}{uuid.uuid4().hex[:16]}"


class EventType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL_SIM = "WITHDRAWAL_SIM"  # paper-only simulated withdrawal
    BUY_FILL = "BUY_FILL"
    SELL_FILL = "SELL_FILL"
    FEE = "FEE"
    DIVIDEND = "DIVIDEND"
    ADJUSTMENT = "ADJUSTMENT"
    CORRECTION = "CORRECTION"  # reverse/correct prior event (links via reverses_event_id)
    MARK = "MARK"  # valuation price update (does not mutate lots/cash)
    # deferred: SPLIT, FX — interfaces only


@dataclass
class Security:
    security_id: str
    symbol: str
    venue: str = "PAPER"
    asset_class: str = "EQUITY"
    currency: str = "USD"
    price_precision: int = 6
    quantity_precision: int = 6

    def to_public(self) -> dict:
        return {
            "security_id": self.security_id,
            "symbol": self.symbol,
            "venue": self.venue,
            "asset_class": self.asset_class,
            "currency": self.currency,
        }


@dataclass
class Fund:
    fund_id: str
    name: str = "SaathiOS Paper Fund"
    base_currency: str = "USD"
    environment: str = "PAPER"
    created_at: float = field(default_factory=_time.time)

    def to_public(self) -> dict:
        return {
            "fund_id": self.fund_id,
            "name": self.name,
            "base_currency": self.base_currency,
            "environment": self.environment,
            "mode": "PAPER",
        }


@dataclass
class LedgerEvent:
    """Append-only ledger event. Never mutate after append."""

    event_id: str
    fund_id: str
    event_type: EventType
    ts: float
    actor: str = "system"
    source: str = "paper"
    # monetary / trade fields (as Decimal-safe strings in payload)
    security_id: str = ""
    symbol: str = ""
    side: str = ""  # BUY/SELL for fills
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    price: Decimal = field(default_factory=lambda: Decimal("0"))
    fee: Decimal = field(default_factory=lambda: Decimal("0"))
    cash_delta: Decimal = field(default_factory=lambda: Decimal("0"))
    currency: str = "USD"
    fill_ref: str = ""
    order_ref: str = ""
    reason: str = ""
    reverses_event_id: str = ""
    payload: dict = field(default_factory=dict)
    # idempotency key — unique per fund
    idempotency_key: str = ""

    def to_record(self) -> dict:
        return {
            "event_id": self.event_id,
            "fund_id": self.fund_id,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else str(self.event_type),
            "ts": self.ts,
            "actor": self.actor,
            "source": self.source,
            "security_id": self.security_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": str(q_qty(self.quantity)),
            "price": str(q_price(self.price)),
            "fee": str(q_money(self.fee)),
            "cash_delta": str(q_money(self.cash_delta)),
            "currency": self.currency,
            "fill_ref": self.fill_ref,
            "order_ref": self.order_ref,
            "reason": self.reason,
            "reverses_event_id": self.reverses_event_id,
            "payload": self.payload,
            "idempotency_key": self.idempotency_key or self.event_id,
        }

    @classmethod
    def from_record(cls, r: dict) -> "LedgerEvent":
        et = r["event_type"]
        if isinstance(et, str):
            et = EventType(et)
        return cls(
            event_id=r["event_id"],
            fund_id=r["fund_id"],
            event_type=et,
            ts=float(r["ts"]),
            actor=r.get("actor") or "system",
            source=r.get("source") or "paper",
            security_id=r.get("security_id") or "",
            symbol=r.get("symbol") or "",
            side=r.get("side") or "",
            quantity=D(r.get("quantity") or "0"),
            price=D(r.get("price") or "0"),
            fee=D(r.get("fee") or "0"),
            cash_delta=D(r.get("cash_delta") or "0"),
            currency=r.get("currency") or "USD",
            fill_ref=r.get("fill_ref") or "",
            order_ref=r.get("order_ref") or "",
            reason=r.get("reason") or "",
            reverses_event_id=r.get("reverses_event_id") or "",
            payload=dict(r.get("payload") or {}),
            idempotency_key=r.get("idempotency_key") or r["event_id"],
        )


@dataclass
class PositionLot:
    lot_id: str
    security_id: str
    symbol: str
    quantity_open: Decimal
    quantity_original: Decimal
    cost_price: Decimal
    opened_ts: float
    fill_ref: str = ""
    fees_allocated: Decimal = field(default_factory=lambda: Decimal("0"))
    currency: str = "USD"

    def cost_basis(self) -> Decimal:
        return q_money(self.quantity_open * self.cost_price)

    def to_public(self) -> dict:
        return {
            "lot_id": self.lot_id,
            "security_id": self.security_id,
            "symbol": self.symbol,
            "quantity_open": str(q_qty(self.quantity_open)),
            "quantity_original": str(q_qty(self.quantity_original)),
            "cost_price": str(q_price(self.cost_price)),
            "cost_basis": str(self.cost_basis()),
            "opened_ts": self.opened_ts,
            "fill_ref": self.fill_ref,
            "currency": self.currency,
        }


@dataclass
class Mark:
    security_id: str
    price: Decimal
    ts: float
    source: str = "fixture"
    max_age_seconds: float = 86400.0

    def is_stale(self, now: float | None = None) -> bool:
        now = _time.time() if now is None else now
        return (now - self.ts) > self.max_age_seconds

    def to_public(self, now: float | None = None) -> dict:
        return {
            "security_id": self.security_id,
            "price": str(q_price(self.price)),
            "ts": self.ts,
            "source": self.source,
            "stale": self.is_stale(now),
            "max_age_seconds": self.max_age_seconds,
        }


@dataclass
class PositionView:
    security_id: str
    symbol: str
    quantity: Decimal
    avg_cost: Decimal  # derived from open lots (cost-weighted)
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    weight: Decimal = field(default_factory=lambda: Decimal("0"))
    mark: Mark | None = None
    mark_stale: bool = False

    def to_public(self) -> dict:
        return {
            "security_id": self.security_id,
            "symbol": self.symbol,
            "quantity": str(q_qty(self.quantity)),
            "avg_cost": str(q_price(self.avg_cost)),
            "cost_basis": str(q_money(self.cost_basis)),
            "market_value": str(q_money(self.market_value)),
            "unrealized_pnl": str(q_money(self.unrealized_pnl)),
            "realized_pnl": str(q_money(self.realized_pnl)),
            "weight": str(q_money(self.weight)),
            "mark_stale": self.mark_stale,
            "mark": self.mark.to_public() if self.mark else None,
        }


@dataclass
class Exposure:
    gross: Decimal
    net: Decimal
    long: Decimal
    short: Decimal  # always 0 while shorts disabled
    cash_weight: Decimal
    currency: str = "USD"

    def to_public(self) -> dict:
        return {
            "gross": str(q_money(self.gross)),
            "net": str(q_money(self.net)),
            "long": str(q_money(self.long)),
            "short": str(q_money(self.short)),
            "cash_weight": str(q_money(self.cash_weight)),
            "currency": self.currency,
            "shorts_enabled": False,
            "leverage_enabled": False,
        }


@dataclass
class PortfolioState:
    fund_id: str
    currency: str
    cash: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_fees: Decimal
    positions_value: Decimal
    nav: Decimal
    positions: list[PositionView]
    open_lots: list[PositionLot]
    exposure: Exposure
    event_count: int
    last_event_id: str = ""
    marks: dict[str, Mark] = field(default_factory=dict)
    invariants: list[str] = field(default_factory=list)
    mode: str = "PAPER"

    def to_public(self) -> dict:
        return {
            "fund_id": self.fund_id,
            "mode": self.mode,
            "currency": self.currency,
            "cash": str(q_money(self.cash)),
            "realized_pnl": str(q_money(self.realized_pnl)),
            "unrealized_pnl": str(q_money(self.unrealized_pnl)),
            "total_pnl": str(q_money(self.realized_pnl + self.unrealized_pnl)),
            "total_fees": str(q_money(self.total_fees)),
            "positions_value": str(q_money(self.positions_value)),
            "nav": str(q_money(self.nav)),
            "paper_nav": str(q_money(self.nav)),
            "exposure": self.exposure.to_public(),
            "positions": [p.to_public() for p in self.positions if p.quantity != 0],
            "open_lots": [l.to_public() for l in self.open_lots if l.quantity_open != 0],
            "event_count": self.event_count,
            "last_event_id": self.last_event_id,
            "invariants_ok": len(self.invariants) == 0,
            "invariants": list(self.invariants),
        }


@dataclass
class ValuationSnapshot:
    snapshot_id: str
    fund_id: str
    ts: float
    nav: Decimal
    cash: Decimal
    positions_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    event_count: int
    state_hash: str

    def to_public(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "fund_id": self.fund_id,
            "ts": self.ts,
            "nav": str(q_money(self.nav)),
            "cash": str(q_money(self.cash)),
            "positions_value": str(q_money(self.positions_value)),
            "realized_pnl": str(q_money(self.realized_pnl)),
            "unrealized_pnl": str(q_money(self.unrealized_pnl)),
            "event_count": self.event_count,
            "state_hash": self.state_hash,
            "mode": "PAPER",
        }
