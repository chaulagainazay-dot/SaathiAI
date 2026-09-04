"""M62.5 — deterministic paper broker: order validation + conservative fill engine.

The broker is a PURE, STATELESS decision engine. It computes acceptance/rejection
and fills from an order plus a single market event; it never mutates durable state,
never opens a socket, never reads wall-clock time, and never sees a future event.
Durability and transactions belong to :mod:`saathi.platform.paper_trading.service`,
which applies the broker's decisions atomically.

Determinism: identical (engine version, account-state hash, order-state hash,
market-event hash, fee model, slippage model, seed, calendar) inputs produce an
identical acceptance decision, rejection reason, fill quantity, fill price, fee,
and result hash.

Fill policy (conservative, documented, tested):
  * Market orders fill at the *next* eligible event, at the adverse touch (ask for
    BUY, bid for SELL) plus deterministic slippage.
  * Limit BUY fills only when ask <= limit, and never above the limit.
  * Limit SELL fills only when bid >= limit, and never below the limit.
  * A partial fill is taken when available liquidity (participation cap) is below
    remaining quantity; the remainder stays open.
  * Invalid / stale price quality, or a non-open market, blocks the fill (no fill).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any

from saathi.platform.trading_models import (
    D, OrderSide, OrderType, DataQuality, MarketState,
)
from saathi.platform.paper_trading.models import (
    ENGINE_VERSION, CALENDAR, FeeModel, SlippageModel, PaperOrder, PaperAccount,
    PaperPosition, q2, q6, market_event_hash, fill_result_hash, assert_paper_safe,
)


@dataclass
class MarketEvent:
    """A single, self-describing market observation the broker may fill against.

    Built from an M62.2 ``MDQuote`` or ``MDBar`` (see :func:`from_quote` /
    :func:`from_bar`). Carries its own coarse ``DataQuality`` and ``MarketState`` so
    the broker fails closed on anything not fully VALID and OPEN.
    """
    symbol: str
    ts: float
    bid: Decimal
    ask: Decimal
    last: Decimal
    liquidity: Decimal            # available size at the touch (shares)
    quality: DataQuality
    market_state: MarketState
    ref: str = ""                 # market-data reference id (for audit/idempotency)

    @property
    def spread(self) -> Decimal:
        s = D(self.ask) - D(self.bid)
        return s if s > 0 else Decimal("0")

    def to_hashable(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "ts": self.ts, "bid": str(self.bid), "ask": str(self.ask),
                "last": str(self.last), "liquidity": str(self.liquidity), "quality": self.quality.value,
                "market_state": self.market_state.value}

    def event_hash(self) -> str:
        return market_event_hash(self.to_hashable())


def from_quote(quote, *, ref: str = "") -> MarketEvent:
    """Adapt an M62.2 ``MDQuote`` into a broker MarketEvent (uses its own quality)."""
    liq = min(D(quote.bid_size), D(quote.ask_size)) if (D(quote.bid_size) > 0 and D(quote.ask_size) > 0) \
        else max(D(quote.bid_size), D(quote.ask_size))
    ms = MarketState.OPEN
    if quote.data_quality() == DataQuality.STALE:
        ms = MarketState.OPEN  # staleness handled by quality gate, not market state
    return MarketEvent(symbol=quote.instrument, ts=quote.source_time.timestamp(), bid=D(quote.bid),
                       ask=D(quote.ask), last=D(quote.last), liquidity=liq, quality=quote.data_quality(),
                       market_state=ms, ref=ref or f"quote:{quote.instrument}:{quote.source_time.timestamp()}")


def from_bar(bar, *, market_state: MarketState = MarketState.OPEN, ref: str = "") -> MarketEvent:
    """Adapt an M62.2 ``MDBar`` into a broker MarketEvent.

    Conservative: uses the bar CLOSE as both touches (no favorable intrabar OHLC
    sequencing is ever assumed) with a synthetic 1-bps spread band.
    """
    close = D(bar.close)
    band = q6(close * (Decimal("1") / Decimal("10000")))
    return MarketEvent(symbol=bar.instrument, ts=bar.start_time.timestamp(), bid=q6(close - band),
                       ask=q6(close + band), last=close, liquidity=D(bar.volume), quality=bar.data_quality(),
                       market_state=market_state, ref=ref or f"bar:{bar.instrument}:{bar.start_time.timestamp()}")


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""


@dataclass
class FillPlan:
    eligible: bool
    quantity: Decimal
    price: Decimal
    fee: Decimal
    slippage_per_unit: Decimal
    gross_amount: Decimal
    reason: str = ""
    result_hash: str = ""


class PaperBroker:
    """Deterministic, stateless simulation broker (PAPER only)."""

    def __init__(self, *, fee_model: FeeModel, slippage_model: SlippageModel,
                 seed: int = 0, engine_version: str = ENGINE_VERSION, calendar: str = CALENDAR):
        assert_paper_safe()  # fail closed at construction
        self.fee_model = fee_model
        self.slippage_model = slippage_model
        self.seed = int(seed)
        self.engine_version = engine_version
        self.calendar = calendar

    # ── new-order validation ────────────────────────────────────────────────
    def validate_new_order(self, *, account: PaperAccount, side: OrderSide, order_type: OrderType,
                           quantity: Decimal, limit_price: Decimal | None,
                           position: PaperPosition | None, reserve_cost: Decimal,
                           ref_price: Decimal) -> ValidationResult:
        qty = D(quantity)
        if account.environment.value != "PAPER":
            return ValidationResult(False, "environment not PAPER")
        if account.status.value != "ACTIVE":
            return ValidationResult(False, f"account not ACTIVE ({account.status.value})")
        if qty <= 0:
            return ValidationResult(False, "quantity must be positive")
        # T-NEXT-4: an order must never be admitted against a non-positive or
        # non-finite reference price. The fill path already refuses a zero touch
        # price, but without this an order is still created and cash reserved
        # against a meaningless price.
        if ref_price is None or D(ref_price) <= 0:
            return ValidationResult(False, "reference price must be positive")
        if order_type not in (OrderType.MARKET, OrderType.LIMIT):
            return ValidationResult(False, f"unsupported order type {order_type.value}")
        if order_type == OrderType.LIMIT and (limit_price is None or D(limit_price) <= 0):
            return ValidationResult(False, "limit order requires positive limit price")
        if side == OrderSide.BUY:
            if reserve_cost > account.available_cash:
                return ValidationResult(False, f"insufficient cash: need {reserve_cost}, available {account.available_cash}")
        else:  # SELL — long-only: never exceed available (unreserved) long quantity
            held = position.available_quantity if position else Decimal("0")
            if qty > held:
                return ValidationResult(False, f"oversell: sell {qty} exceeds available long {held}")
        return ValidationResult(True, "")

    def reserve_for_buy(self, *, quantity: Decimal, ref_price: Decimal, limit_price: Decimal | None,
                        order_type: OrderType) -> Decimal:
        """Cash to reserve for a BUY: notional + estimated fee + bounded slippage reserve."""
        px = D(limit_price) if (order_type == OrderType.LIMIT and limit_price is not None) else D(ref_price)
        notional = D(quantity) * px
        fee = self.fee_model.fee(quantity=quantity, price=px)
        slip_reserve = notional * (self.slippage_model.bps / Decimal("10000"))
        return q2(notional + fee + slip_reserve)

    # ── conservative fill computation ───────────────────────────────────────
    def compute_fill(self, *, order: PaperOrder, account: PaperAccount, event: MarketEvent) -> FillPlan:
        remaining = order.remaining_quantity
        if remaining <= 0:
            return FillPlan(False, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "no remaining quantity")
        # fail closed on data quality / market state
        if event.quality != DataQuality.VALID:
            return FillPlan(False, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
                            f"price quality {event.quality.value} not tradeable")
        if event.market_state != MarketState.OPEN:
            return FillPlan(False, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
                            f"market state {event.market_state.value} not open")

        side = order.side
        touch = D(event.ask) if side == OrderSide.BUY else D(event.bid)
        if touch <= 0:
            return FillPlan(False, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "invalid touch price")

        # limit crossing (conservative)
        if order.order_type == OrderType.LIMIT:
            limit = D(order.limit_price)
            if side == OrderSide.BUY and touch > limit:
                return FillPlan(False, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "limit not crossed (ask>limit)")
            if side == OrderSide.SELL and touch < limit:
                return FillPlan(False, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "limit not crossed (bid<limit)")

        # deterministic slippage-adjusted price, clamped to never violate the limit
        price = self.slippage_model.adjust(side=side, reference=touch, spread=event.spread)
        if order.order_type == OrderType.LIMIT:
            limit = D(order.limit_price)
            if side == OrderSide.BUY and price > limit:
                price = limit
            if side == OrderSide.SELL and price < limit:
                price = limit
        price = q6(price)
        slippage_per_unit = q6(price - touch) if side == OrderSide.BUY else q6(touch - price)

        # participation-limited quantity (partial fills), floored to whole units
        cap = (D(event.liquidity) * self.slippage_model.max_volume_participation) if event.liquidity > 0 else remaining
        fill_qty = min(remaining, cap).quantize(Decimal("1"), rounding=ROUND_DOWN)
        if fill_qty <= 0:
            return FillPlan(False, Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "insufficient liquidity this event")

        gross = q2(fill_qty * price)
        fee = self.fee_model.fee(quantity=fill_qty, price=price)
        rh = fill_result_hash(engine_version=self.engine_version, account_state_hash=account.state_hash(),
                              order_state_hash=order.order_state_hash(), market_event_hash=event.event_hash(),
                              fee_model_version=self.fee_model.version, slippage_model_version=self.slippage_model.version,
                              seed=self.seed, calendar=self.calendar, quantity=fill_qty, price=price, fee=fee)
        return FillPlan(True, fill_qty, price, fee, slippage_per_unit, gross, "", rh)
