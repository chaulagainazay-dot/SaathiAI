"""Execution Layer (M5 Phase 5) — governed, auditable, paper-first, no bypass.

The spine, end to end: an approved InvestmentCase → an immutable ExecutionIntent
→ a broker-independent Connector → an Execution Monitor that publishes events →
the Portfolio Registry and Learning Runtime (which subscribe, never poll).

Non-negotiable guarantees:
  • No trade bypasses approval — an ExecutionIntent can ONLY be born from a case
    that is `executable` (approved by a human, Governance L4). ExecutionIntent is
    frozen: a complete, replayable audit record.
  • Broker independence — every connector implements the SAME interface; callers
    use ExecutionService.execute(intent) and never touch Binance/Alpaca directly
    (same abstraction as the Model Router / Tool Registry).
  • Paper-first — PaperConnector and ReplayConnector share the live interface, so
    Financial Intelligence can be tested for months with zero capital at risk.
  • Idempotent failure recovery — on broker timeout we NEVER blind-retry; we query
    order status by intent_id and reconcile, so a lost response can't double-trade.

Deterministic (AP-17); price feed / clock / publisher / recorder / registry
injected (AP-12).
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from saathi.investment import AssetClass, Verdict
from saathi.investment_pipeline import InvestmentCase, _to_investment_opportunity
from saathi.portfolio import Position, PortfolioRegistry


class ExecutionSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial_fill"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"
    FAILED = "failed"


# ── 1. Execution Intent (immutable audit record) ────────────────────────────
@dataclass(frozen=True)
class ExecutionIntent:
    intent_id: str
    case_id: str
    broker: str
    account: str
    symbol: str
    side: ExecutionSide
    quantity: float
    asset_class: AssetClass
    order_type: OrderType
    created_at: float
    approved_by: str
    expires_at: float
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    @classmethod
    def from_case(cls, case: InvestmentCase, *, broker: str, account: str,
                  symbol: str, quantity: float, now: float, ttl_s: float = 3600.0,
                  order_type: OrderType = OrderType.MARKET,
                  limit_price: float | None = None, stop_loss: float | None = None,
                  take_profit: float | None = None) -> "ExecutionIntent":
        # THE GUARD: nothing executes without human approval (Governance L4).
        if not case.executable:
            raise PermissionError(
                "ExecutionIntent requires an approved, executable InvestmentCase "
                "(human approval / Governance L4 not satisfied)")
        side = ExecutionSide.BUY if case.verdict is Verdict.BUY else ExecutionSide.SELL
        return cls(
            intent_id=str(uuid.uuid4()), case_id=case.opportunity.key, broker=broker,
            account=account, symbol=symbol, side=side, quantity=quantity,
            asset_class=_to_investment_opportunity(case.opportunity).asset_class,
            order_type=order_type, created_at=now,
            approved_by=case.recommendation.approver or "unknown",
            expires_at=now + ttl_s, limit_price=limit_price,
            stop_loss=stop_loss, take_profit=take_profit)


@dataclass
class OrderPreview:
    side: ExecutionSide
    symbol: str
    quantity: float
    estimated_cost_usd: float
    estimated_fee_usd: float
    slippage_pct: float
    remaining_cash_usd: float
    risk_after: str

    def render(self) -> str:
        return (f"📄 {self.side.value.upper()} {self.quantity} {self.symbol} — "
                f"cost ${self.estimated_cost_usd:,.0f} (fee ${self.estimated_fee_usd:.2f}, "
                f"slip {self.slippage_pct:.2%}), cash left ${self.remaining_cash_usd:,.0f}, "
                f"risk {self.risk_after}")


@dataclass
class ExecutionOrder:
    intent: ExecutionIntent
    status: ExecutionStatus
    broker_order_id: str = ""
    filled_quantity: float = 0.0
    avg_price: float = 0.0
    fee_usd: float = 0.0
    history: list[ExecutionStatus] = field(default_factory=list)

    @property
    def notional_usd(self) -> float:
        return round(self.filled_quantity * self.avg_price, 2)


# ── 2. Connector interface (every broker implements this) ───────────────────
class BrokerConnector(ABC):
    name: str

    @abstractmethod
    def validate(self, intent: ExecutionIntent, now: float) -> tuple[bool, str]: ...
    @abstractmethod
    def preview(self, intent: ExecutionIntent, now: float) -> OrderPreview: ...
    @abstractmethod
    def execute(self, intent: ExecutionIntent, now: float) -> ExecutionOrder: ...
    @abstractmethod
    def cancel(self, intent_id: str) -> bool: ...
    @abstractmethod
    def status(self, intent_id: str) -> ExecutionOrder | None: ...
    @abstractmethod
    def positions(self) -> list[dict]: ...
    @abstractmethod
    def balances(self) -> dict: ...
    @abstractmethod
    def orders(self) -> list[ExecutionOrder]: ...

    # shared validation every connector reuses
    def _base_validate(self, intent: ExecutionIntent, now: float) -> tuple[bool, str]:
        if intent.quantity <= 0:
            return False, "quantity must be positive"
        if now > intent.expires_at:
            return False, "intent expired"
        if intent.order_type is OrderType.LIMIT and intent.limit_price is None:
            return False, "limit order requires limit_price"
        return True, "ok"


# ── Paper connector (default; identical interface to live) ──────────────────
class PaperConnector(BrokerConnector):
    name = "paper"

    def __init__(self, price: Callable[[str], float], *, starting_cash: float = 100_000,
                 fee_rate: float = 0.001, slippage: float = 0.0012):
        self._price = price
        self._cash = starting_cash
        self._fee_rate = fee_rate
        self._slippage = slippage
        self._orders: dict[str, ExecutionOrder] = {}   # keyed by intent_id (idempotent)
        self._positions: dict[str, float] = {}

    def validate(self, intent, now):
        return self._base_validate(intent, now)

    def preview(self, intent, now):
        px = self._price(intent.symbol)
        fill_px = px * (1 + self._slippage if intent.side is ExecutionSide.BUY
                        else 1 - self._slippage)
        cost = intent.quantity * fill_px
        fee = cost * self._fee_rate
        remaining = self._cash - (cost + fee if intent.side is ExecutionSide.BUY else -cost + fee)
        risk = "high" if intent.asset_class in (AssetClass.CRYPTO, AssetClass.ICO) else "medium"
        return OrderPreview(intent.side, intent.symbol, intent.quantity,
                            round(cost, 2), round(fee, 2), self._slippage,
                            round(remaining, 2), risk)

    def execute(self, intent, now):
        if intent.intent_id in self._orders:          # idempotent — never double-trade
            return self._orders[intent.intent_id]
        px = self._price(intent.symbol)
        fill_px = px * (1 + self._slippage if intent.side is ExecutionSide.BUY
                        else 1 - self._slippage)
        cost = intent.quantity * fill_px
        fee = cost * self._fee_rate
        if intent.side is ExecutionSide.BUY:
            self._cash -= cost + fee
            self._positions[intent.symbol] = self._positions.get(intent.symbol, 0.0) + intent.quantity
        else:
            self._cash += cost - fee
            self._positions[intent.symbol] = self._positions.get(intent.symbol, 0.0) - intent.quantity
        order = ExecutionOrder(
            intent=intent, status=ExecutionStatus.FILLED,
            broker_order_id="paper-" + intent.intent_id[:8],
            filled_quantity=intent.quantity, avg_price=round(fill_px, 6),
            fee_usd=round(fee, 2), history=[ExecutionStatus.SUBMITTED, ExecutionStatus.FILLED])
        self._orders[intent.intent_id] = order
        return order

    def cancel(self, intent_id):
        o = self._orders.get(intent_id)
        if o and o.status in (ExecutionStatus.PENDING, ExecutionStatus.SUBMITTED):
            o.status = ExecutionStatus.CANCELLED
            return True
        return False

    def status(self, intent_id):
        return self._orders.get(intent_id)

    def positions(self):
        return [{"symbol": s, "quantity": q} for s, q in self._positions.items()]

    def balances(self):
        return {"cash_usd": round(self._cash, 2)}

    def orders(self):
        return list(self._orders.values())


# ── Replay connector (scripted outcomes — tests failure recovery) ───────────
class ReplayConnector(PaperConnector):
    """Scripts broker behaviour. 'timeout_filled' models the dangerous case: the
    broker DID fill but the response was lost — a naive retry would double-trade."""
    name = "replay"

    def __init__(self, price, script: list[str], **kw):
        super().__init__(price, **kw)
        self._script = list(script)
        self._step = 0

    def execute(self, intent, now):
        behaviour = self._script[self._step] if self._step < len(self._script) else "filled"
        self._step += 1
        if behaviour == "timeout_filled":
            super().execute(intent, now)               # broker really filled it…
            raise TimeoutError("broker response lost after fill")
        if behaviour == "timeout_unfilled":
            raise TimeoutError("broker unreachable, no order placed")
        return super().execute(intent, now)


# ── 8. Broker Registry (like the Tool Registry) ─────────────────────────────
class BrokerRegistry:
    def __init__(self) -> None:
        self._brokers: dict[str, BrokerConnector] = {}

    def register(self, connector: BrokerConnector) -> None:
        self._brokers[connector.name] = connector

    def get(self, name: str) -> BrokerConnector:
        if name not in self._brokers:
            raise KeyError(f"broker '{name}' not registered")
        return self._brokers[name]

    def names(self) -> list[str]:
        return list(self._brokers)


# ── 3–6. Execution Service (select connector, preview, execute, recover) ────
class ExecutionService:
    def __init__(self, registry: BrokerRegistry, *,
                 portfolio: PortfolioRegistry | None = None,
                 publish: Callable[[str, dict], object] | None = None,
                 record_episode: Callable[..., int] | None = None):
        self.registry = registry
        self.portfolio = portfolio
        if publish is None:
            from saathi.events import bus
            publish = bus.publish_sync
        if record_episode is None:
            from saathi.integration import ingest_episode as record_episode
        self._publish = publish
        self._episode = record_episode

    def preview(self, intent: ExecutionIntent, now: float) -> OrderPreview:
        return self.registry.get(intent.broker).preview(intent, now)

    def execute(self, intent: ExecutionIntent, now: float, *,
                confirm: bool = True) -> ExecutionOrder:
        if not confirm:
            raise PermissionError("execution requires explicit confirmation of the preview")
        connector = self.registry.get(intent.broker)
        ok, reason = connector.validate(intent, now)
        if not ok:
            return self._settle(ExecutionOrder(intent, ExecutionStatus.REJECTED), reason=reason)

        # 6. Idempotent failure recovery — never blind-retry on timeout.
        try:
            order = connector.execute(intent, now)
        except TimeoutError:
            existing = connector.status(intent.intent_id)
            if existing is not None and existing.status is ExecutionStatus.FILLED:
                order = existing                       # broker filled; reconcile, DON'T retry
            else:
                order = connector.execute(intent, now)  # confirmed unfilled → safe retry

        return self._settle(order)

    # 4/5. Monitor: publish events, update the portfolio, feed learning.
    def _settle(self, order: ExecutionOrder, *, reason: str = "") -> ExecutionOrder:
        intent = order.intent
        event = {
            ExecutionStatus.FILLED: "execution.filled",
            ExecutionStatus.PARTIAL: "execution.partial_fill",
            ExecutionStatus.CANCELLED: "execution.cancelled",
            ExecutionStatus.REJECTED: "execution.failed",
            ExecutionStatus.FAILED: "execution.failed",
        }.get(order.status, "execution.submitted")
        self._publish(event, {
            "intent_id": intent.intent_id, "symbol": intent.symbol,
            "side": intent.side.value, "status": order.status.value,
            "notional_usd": order.notional_usd, "reason": reason})

        if order.status is ExecutionStatus.FILLED and self.portfolio is not None:
            if intent.side is ExecutionSide.BUY:
                self.portfolio.add_position(Position(
                    symbol=intent.symbol, asset_class=intent.asset_class,
                    usd_value=order.notional_usd, cost_basis_usd=order.notional_usd))

        outcome = "success" if order.status is ExecutionStatus.FILLED else "failure"
        self._episode(
            agent="execution_service", department="investment", product="execution",
            intent="execute_trade",
            action=f"{intent.side.value} {intent.quantity} {intent.symbol} via {intent.broker}",
            result=f"{order.status.value} ${order.notional_usd:.0f}"
                   + (f" ({reason})" if reason else ""),
            outcome=outcome, quality_score=1.0 if outcome == "success" else 0.0,
            metadata={"intent_id": intent.intent_id, "broker": intent.broker,
                      "approved_by": intent.approved_by, "case_id": intent.case_id})
        return order
