"""M192–M199 — Paper activation governance domain.

PAPER ONLY. No live broker, no credentials, no real money.
LIVE_APPROVED is intentionally absent.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


SCHEMA_VERSION = "m192.tg.paper_activation.v1"
ENGINE_VERSION = "m192.paper_activation.engine.v1"
FUNDS_LABEL = "SIMULATED"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _now() -> float:
    return time.time()


def fingerprint(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def D(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


class PaperActivationState(str, Enum):
    """Strategy paper-activation lifecycle. No LIVE states."""

    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_ELIGIBLE = "PAPER_ELIGIBLE"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    PAPER_APPROVED = "PAPER_APPROVED"
    PAPER_ACTIVE = "PAPER_ACTIVE"
    PAPER_HALTED = "PAPER_HALTED"
    PAPER_SUSPENDED = "PAPER_SUSPENDED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class ActivationApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    CONSUMED = "CONSUMED"  # single-use consumed on activation


class PortfolioStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    HALTED = "HALTED"
    LOCKED = "LOCKED"
    CLOSED = "CLOSED"


class SimOrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class SimTimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class SimOrderStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class RiskHaltReason(str, Enum):
    NONE = "NONE"
    DAILY_LOSS = "DAILY_LOSS"
    WEEKLY_LOSS = "WEEKLY_LOSS"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    KILL_SWITCH = "KILL_SWITCH"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    UNRECONCILED = "UNRECONCILED"
    EXPOSURE_LIMIT = "EXPOSURE_LIMIT"
    OPERATOR = "OPERATOR"
    STRATEGY_NOT_ACTIVE = "STRATEGY_NOT_ACTIVE"


@dataclass
class RiskLimits:
    max_position_notional: Decimal = field(default_factory=lambda: Decimal("25000"))
    max_portfolio_exposure_pct: Decimal = field(default_factory=lambda: Decimal("100"))
    daily_loss_limit_pct: Decimal = field(default_factory=lambda: Decimal("3"))
    weekly_loss_limit_pct: Decimal = field(default_factory=lambda: Decimal("8"))
    max_concurrent_positions: int = 10
    # Simulation-only labels — orders never use real leverage/margin
    max_leverage_sim: Decimal = field(default_factory=lambda: Decimal("1"))
    margin_simulation_enabled: bool = False  # display-only when True; never funds real margin
    max_drawdown_pct: Decimal = field(default_factory=lambda: Decimal("20"))
    fee_bps: Decimal = field(default_factory=lambda: Decimal("5"))
    slippage_bps: Decimal = field(default_factory=lambda: Decimal("5"))
    spread_bps: Decimal = field(default_factory=lambda: Decimal("2"))

    def to_public(self) -> dict[str, Any]:
        return {
            "max_position_notional": str(self.max_position_notional),
            "max_portfolio_exposure_pct": str(self.max_portfolio_exposure_pct),
            "daily_loss_limit_pct": str(self.daily_loss_limit_pct),
            "weekly_loss_limit_pct": str(self.weekly_loss_limit_pct),
            "max_concurrent_positions": self.max_concurrent_positions,
            "max_leverage_sim": str(self.max_leverage_sim),
            "margin_simulation_enabled": self.margin_simulation_enabled,
            "max_drawdown_pct": str(self.max_drawdown_pct),
            "fee_bps": str(self.fee_bps),
            "slippage_bps": str(self.slippage_bps),
            "spread_bps": str(self.spread_bps),
            "leverage_executable": False,
            "margin_executable": False,
            "paper_only": True,
            "note": "Leverage/margin fields are simulation labels only; orders remain cash long-only.",
        }


@dataclass
class ActivationApproval:
    id: str = field(default_factory=lambda: _id("paap"))
    strategy_slug: str = ""
    strategy_version: str = "1.0.0"
    dataset_id: str = ""
    dataset_fingerprint: str = ""
    qualification_fingerprint: str = ""
    status: ActivationApprovalStatus = ActivationApprovalStatus.PENDING
    reason: str = ""
    operator_id: str = ""
    operator_identity: str = ""  # must not be llm: or strategy:
    created_at: float = field(default_factory=_now)
    decided_at: float | None = None
    expires_at: float | None = None
    single_use: bool = True
    consumed_at: float | None = None
    notes: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    org_id: str = ""
    workspace_id: str = ""
    immutable: bool = False
    rejection_reason: str = ""

    def freeze(self) -> None:
        self.immutable = True

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "strategy_slug": self.strategy_slug,
            "strategy_version": self.strategy_version,
            "dataset_id": self.dataset_id,
            "dataset_fingerprint": self.dataset_fingerprint,
            "qualification_fingerprint": self.qualification_fingerprint,
            "status": self.status.value,
            "reason": self.reason,
            "operator_id": self.operator_id,
            "operator_identity": self.operator_identity,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "expires_at": self.expires_at,
            "single_use": self.single_use,
            "consumed_at": self.consumed_at,
            "notes": self.notes,
            "evidence": dict(self.evidence),
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "immutable": self.immutable,
            "rejection_reason": self.rejection_reason,
            "paper_only": True,
            "live_authorized": False,
            "llm_may_approve": False,
        }


@dataclass
class StrategyActivationRecord:
    id: str = field(default_factory=lambda: _id("pact"))
    strategy_slug: str = ""
    strategy_version: str = "1.0.0"
    state: PaperActivationState = PaperActivationState.RESEARCH_ONLY
    qualification_verdict: str = ""
    qualification_fingerprint: str = ""
    dataset_id: str = ""
    dataset_fingerprint: str = ""
    approval_id: str = ""
    portfolio_id: str = ""
    activated_at: float | None = None
    halted_at: float | None = None
    halt_reason: str = ""
    org_id: str = ""
    workspace_id: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)
    paper_only: bool = True

    def record(self, event: str, **detail: Any) -> None:
        self.history.append({"ts": _now(), "event": event, **detail})

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "strategy_slug": self.strategy_slug,
            "strategy_version": self.strategy_version,
            "state": self.state.value,
            "qualification_verdict": self.qualification_verdict,
            "qualification_fingerprint": self.qualification_fingerprint,
            "dataset_id": self.dataset_id,
            "dataset_fingerprint": self.dataset_fingerprint,
            "approval_id": self.approval_id,
            "portfolio_id": self.portfolio_id,
            "activated_at": self.activated_at,
            "halted_at": self.halted_at,
            "halt_reason": self.halt_reason,
            "history": list(self.history[-50:]),
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "paper_only": True,
            "live_authorized": False,
            "live_state_exists": False,
        }


@dataclass
class PositionLot:
    lot_id: str = field(default_factory=lambda: _id("lot"))
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_price: Decimal = field(default_factory=lambda: Decimal("0"))
    opened_at: float = field(default_factory=_now)
    fees: Decimal = field(default_factory=lambda: Decimal("0"))

    def to_public(self) -> dict[str, Any]:
        return {
            "lot_id": self.lot_id,
            "quantity": str(self.quantity),
            "avg_price": str(self.avg_price),
            "opened_at": self.opened_at,
            "fees": str(self.fees),
        }


@dataclass
class PaperPosition:
    symbol: str
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_price: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    fees: Decimal = field(default_factory=lambda: Decimal("0"))
    strategy_slug: str = ""
    lots: list[PositionLot] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    def unrealized(self, mark: Decimal) -> Decimal:
        return (D(mark) - self.avg_price) * self.quantity

    def market_value(self, mark: Decimal) -> Decimal:
        return D(mark) * self.quantity

    def to_public(self, mark: Decimal | None = None) -> dict[str, Any]:
        m = mark if mark is not None else self.avg_price
        return {
            "symbol": self.symbol,
            "quantity": str(self.quantity),
            "avg_price": str(self.avg_price),
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized(m)),
            "market_value": str(self.market_value(m)),
            "fees": str(self.fees),
            "strategy_slug": self.strategy_slug,
            "lots": [l.to_public() for l in self.lots],
            "history_len": len(self.history),
            "paper_only": True,
        }


@dataclass
class SimOrder:
    id: str = field(default_factory=lambda: _id("pord"))
    portfolio_id: str = ""
    strategy_slug: str = ""
    symbol: str = ""
    side: str = "BUY"  # BUY | SELL
    order_type: SimOrderType = SimOrderType.MARKET
    tif: SimTimeInForce = SimTimeInForce.DAY
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    filled_qty: Decimal = field(default_factory=lambda: Decimal("0"))
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    status: SimOrderStatus = SimOrderStatus.PENDING
    reject_reason: str = ""
    avg_fill_price: Decimal = field(default_factory=lambda: Decimal("0"))
    fees: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage: Decimal = field(default_factory=lambda: Decimal("0"))
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    fills: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    correlation_id: str = ""
    paper_only: bool = True

    @property
    def remaining(self) -> Decimal:
        return self.quantity - self.filled_qty

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "portfolio_id": self.portfolio_id,
            "strategy_slug": self.strategy_slug,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type.value,
            "tif": self.tif.value,
            "quantity": str(self.quantity),
            "filled_qty": str(self.filled_qty),
            "remaining": str(self.remaining),
            "limit_price": str(self.limit_price) if self.limit_price is not None else None,
            "stop_price": str(self.stop_price) if self.stop_price is not None else None,
            "status": self.status.value,
            "reject_reason": self.reject_reason,
            "avg_fill_price": str(self.avg_fill_price),
            "fees": str(self.fees),
            "slippage": str(self.slippage),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "fills": list(self.fills),
            "notes": self.notes,
            "correlation_id": self.correlation_id,
            "paper_only": True,
            "live_order": False,
            "exchange_connected": False,
        }


@dataclass
class JournalEntry:
    id: str = field(default_factory=lambda: _id("pjnl"))
    portfolio_id: str = ""
    strategy_slug: str = ""
    order_id: str = ""
    symbol: str = ""
    side: str = ""
    reason: str = ""
    signal: dict[str, Any] = field(default_factory=dict)
    confidence: str = ""
    market_regime: str = ""
    risk: dict[str, Any] = field(default_factory=dict)
    stop: str = ""
    target: str = ""
    entry: str = ""
    exit: str = ""
    notes: str = ""
    owner_notes: str = ""
    llm_explanation: str = ""  # advisory only; never authoritative
    screenshot_refs: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=_now)
    immutable: bool = True
    org_id: str = ""
    workspace_id: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "portfolio_id": self.portfolio_id,
            "strategy_slug": self.strategy_slug,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "reason": self.reason,
            "signal": dict(self.signal),
            "confidence": self.confidence,
            "market_regime": self.market_regime,
            "risk": dict(self.risk),
            "stop": self.stop,
            "target": self.target,
            "entry": self.entry,
            "exit": self.exit,
            "notes": self.notes,
            "owner_notes": self.owner_notes,
            "llm_explanation": self.llm_explanation,
            "llm_authoritative": False,
            "screenshot_refs": list(self.screenshot_refs),
            "created_at": self.created_at,
            "immutable": True,
            "paper_only": True,
            "funds_label": FUNDS_LABEL,
        }


@dataclass
class PortfolioSnapshot:
    ts: float
    cash: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    drawdown_pct: Decimal
    positions_count: int
    note: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "cash": str(self.cash),
            "equity": str(self.equity),
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "drawdown_pct": str(self.drawdown_pct),
            "positions_count": self.positions_count,
            "note": self.note,
        }


@dataclass
class PaperPortfolio:
    id: str = field(default_factory=lambda: _id("pport"))
    name: str = "Paper Fund"
    status: PortfolioStatus = PortfolioStatus.ACTIVE
    base_currency: str = "USD"
    starting_cash: Decimal = field(default_factory=lambda: Decimal("100000"))
    cash: Decimal = field(default_factory=lambda: Decimal("100000"))
    reserved_cash: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    fees_paid: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage_paid: Decimal = field(default_factory=lambda: Decimal("0"))
    peak_equity: Decimal = field(default_factory=lambda: Decimal("100000"))
    day_start_equity: Decimal = field(default_factory=lambda: Decimal("100000"))
    week_start_equity: Decimal = field(default_factory=lambda: Decimal("100000"))
    month_start_equity: Decimal = field(default_factory=lambda: Decimal("100000"))
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    risk_limits: RiskLimits = field(default_factory=RiskLimits)
    halt_reason: RiskHaltReason = RiskHaltReason.NONE
    halt_detail: str = ""
    marks: dict[str, Decimal] = field(default_factory=dict)
    equity_curve: list[PortfolioSnapshot] = field(default_factory=list)
    trade_ledger: list[dict[str, Any]] = field(default_factory=list)
    audit_trail: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    org_id: str = ""
    workspace_id: str = ""
    linked_m62_account_id: str = ""  # optional compose ref
    paper_only: bool = True

    def equity(self) -> Decimal:
        upnl = Decimal("0")
        for sym, pos in self.positions.items():
            mark = self.marks.get(sym, pos.avg_price)
            upnl += pos.unrealized(mark)
        return self.cash + upnl + sum(
            (pos.market_value(self.marks.get(sym, pos.avg_price)) for sym, pos in self.positions.items()),
            Decimal("0"),
        ) - sum(
            (pos.market_value(self.marks.get(sym, pos.avg_price)) for sym, pos in self.positions.items()),
            Decimal("0"),
        ) + sum(
            (pos.quantity * self.marks.get(sym, pos.avg_price) for sym, pos in self.positions.items()),
            Decimal("0"),
        )

    def compute_equity(self) -> Decimal:
        pos_value = Decimal("0")
        for sym, pos in self.positions.items():
            mark = self.marks.get(sym, pos.avg_price)
            pos_value += pos.quantity * mark
        return self.cash + pos_value

    def buying_power(self) -> Decimal:
        """Cash long-only buying power. Margin sim is display-only."""
        if self.risk_limits.margin_simulation_enabled:
            # Display-only simulated buying power label — still cannot exceed cash for orders
            return self.cash * self.risk_limits.max_leverage_sim
        return self.cash - self.reserved_cash

    def unrealized_pnl(self) -> Decimal:
        total = Decimal("0")
        for sym, pos in self.positions.items():
            total += pos.unrealized(self.marks.get(sym, pos.avg_price))
        return total

    def drawdown_pct(self) -> Decimal:
        eq = self.compute_equity()
        if self.peak_equity <= 0:
            return Decimal("0")
        if eq > self.peak_equity:
            self.peak_equity = eq
        return ((self.peak_equity - eq) / self.peak_equity) * Decimal("100")

    def audit(self, event: str, **detail: Any) -> None:
        self.audit_trail.append({
            "ts": _now(),
            "event": event,
            **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in detail.items()},
            "paper_only": True,
        })
        self.updated_at = _now()

    def snapshot(self, note: str = "") -> PortfolioSnapshot:
        eq = self.compute_equity()
        if eq > self.peak_equity:
            self.peak_equity = eq
        snap = PortfolioSnapshot(
            ts=_now(),
            cash=self.cash,
            equity=eq,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=self.unrealized_pnl(),
            drawdown_pct=self.drawdown_pct(),
            positions_count=sum(1 for p in self.positions.values() if p.quantity > 0),
            note=note,
        )
        self.equity_curve.append(snap)
        return snap

    def to_public(self) -> dict[str, Any]:
        eq = self.compute_equity()
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "base_currency": self.base_currency,
            "starting_cash": str(self.starting_cash),
            "cash": str(self.cash),
            "reserved_cash": str(self.reserved_cash),
            "buying_power": str(self.buying_power()),
            "buying_power_note": "Cash long-only; margin_sim is display-only",
            "equity": str(eq),
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized_pnl()),
            "fees_paid": str(self.fees_paid),
            "slippage_paid": str(self.slippage_paid),
            "peak_equity": str(self.peak_equity),
            "drawdown_pct": str(self.drawdown_pct()),
            "daily_pnl": str(eq - self.day_start_equity),
            "weekly_pnl": str(eq - self.week_start_equity),
            "monthly_pnl": str(eq - self.month_start_equity),
            "positions": {
                s: p.to_public(self.marks.get(s, p.avg_price))
                for s, p in self.positions.items() if p.quantity != 0
            },
            "risk_limits": self.risk_limits.to_public(),
            "halt_reason": self.halt_reason.value,
            "halt_detail": self.halt_detail,
            "equity_curve_len": len(self.equity_curve),
            "trade_ledger_len": len(self.trade_ledger),
            "audit_trail_len": len(self.audit_trail),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "linked_m62_account_id": self.linked_m62_account_id,
            "funds_label": FUNDS_LABEL,
            "paper_only": True,
            "live_money": False,
            "live_authorized": False,
            "exchange_connected": False,
            "disclaimer": "SIMULATED FUNDS — PAPER ONLY — NO LIVE ORDERS",
        }
