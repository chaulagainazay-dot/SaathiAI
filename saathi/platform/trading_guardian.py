"""M62.1 — Trading Guardian: the independent risk-veto engine.

The Guardian is INDEPENDENT of strategy/research agents and holds FINAL VETO power
before any order intent may proceed toward ExecutionGateway. It is fail-closed:
anything unknown, ambiguous, or unsafe is DENIED. It never places orders — it only
permits or vetoes.

Default posture (M62): every advanced capability is DISABLED, and LIVE execution is
DISABLED. Only non-live (paper/simulation/sandbox) intents may pass, and only when
every order- and account-level check holds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from saathi.platform.trading_models import (
    D, Environment, NON_LIVE_ENVIRONMENTS, OrderIntent, OrderSide, OrderType,
    DataQuality, MarketState, Account,
)


# Capabilities that stay DISABLED unless a later, separately-authorized milestone
# enables them. The Guardian refuses to construct with any of these enabled.
DEFAULT_DISABLED_CAPABILITIES = (
    "LEVERAGE", "MARGIN", "SHORT_SELLING", "OPTIONS", "FUTURES",
    "PERPETUALS", "DERIVATIVES", "BORROWING", "AUTONOMOUS_LIVE_EXECUTION",
)


class CircuitState(str, Enum):
    ARMED = "ARMED"        # trading permitted (subject to checks)
    TRIPPED = "TRIPPED"    # halted, fail-closed


@dataclass
class RiskLimits:
    max_order_notional: Decimal = field(default_factory=lambda: Decimal("10000"))
    max_position_notional: Decimal = field(default_factory=lambda: Decimal("25000"))
    max_gross_exposure: Decimal = field(default_factory=lambda: Decimal("100000"))
    max_open_positions: int = 20
    min_cash_reserve: Decimal = field(default_factory=lambda: Decimal("0"))
    max_symbol_concentration_pct: Decimal = field(default_factory=lambda: Decimal("25"))  # of equity
    max_price_deviation_pct: Decimal = field(default_factory=lambda: Decimal("5"))
    restricted_symbols: frozenset = field(default_factory=frozenset)


@dataclass
class GuardianDecision:
    allowed: bool
    reasons: list[str]
    checks: list[dict[str, Any]]

    def to_public(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reasons": self.reasons, "checks": self.checks}


class TradingGuardian:
    def __init__(self, *, limits: RiskLimits | None = None, capabilities: dict[str, bool] | None = None):
        caps = capabilities or {}
        # Fail closed: refuse to even construct with a prohibited capability enabled.
        for c in DEFAULT_DISABLED_CAPABILITIES:
            if caps.get(c) is True:
                raise ValueError(f"capability {c} is disabled in M62 and cannot be enabled")
        self.capabilities = {c: False for c in DEFAULT_DISABLED_CAPABILITIES}
        self.limits = limits or RiskLimits()
        self.circuit = CircuitState.ARMED

    # ── circuit breaker ──────────────────────────────────────────────────
    def trip(self, reason: str = "manual") -> None:
        self.circuit = CircuitState.TRIPPED
        self._trip_reason = reason

    def reset(self) -> None:
        self.circuit = CircuitState.ARMED

    # ── the veto gate ────────────────────────────────────────────────────
    def evaluate(
        self,
        intent: OrderIntent,
        *,
        account: Account,
        ref_price: Decimal,
        price_quality: DataQuality,
        market_state: MarketState,
        marks: dict[str, Decimal] | None = None,
    ) -> GuardianDecision:
        marks = marks or {}
        reasons: list[str] = []
        checks: list[dict[str, Any]] = []

        def check(name: str, ok: bool, detail: str = "") -> None:
            checks.append({"check": name, "ok": bool(ok), "detail": detail})
            if not ok:
                reasons.append(detail or name)

        # 0. circuit breaker — fail closed
        check("circuit_armed", self.circuit == CircuitState.ARMED, "trading halted (circuit tripped)")

        # 1. environment identity — LIVE is always vetoed; unknown is vetoed
        env_ok = isinstance(intent.environment, Environment) and intent.environment in NON_LIVE_ENVIRONMENTS
        check("environment_non_live", env_ok, f"environment {getattr(intent.environment, 'value', intent.environment)} not permitted (live disabled)")

        # 2. prohibited capabilities — short-selling proxy: SELL with no long inventory
        pos = account.positions.get(intent.symbol)
        held = pos.quantity if pos else Decimal("0")
        if intent.side == OrderSide.SELL:
            check("no_short_selling", D(intent.quantity) <= held, "short-selling disabled: sell exceeds held quantity")
        for c in DEFAULT_DISABLED_CAPABILITIES:
            if self.capabilities.get(c) is True:
                check(f"capability_{c}_disabled", False, f"{c} must be disabled")

        # 3. data quality — only VALID prices may back an order
        check("price_quality_valid", price_quality == DataQuality.VALID, f"price quality {getattr(price_quality,'value',price_quality)} not tradeable")

        # 4. market open
        check("market_open", market_state == MarketState.OPEN, f"market state {getattr(market_state,'value',market_state)} not open")

        # 5. order sanity
        check("quantity_positive", D(intent.quantity) > 0, "quantity must be positive")
        check("idempotency_present", bool(intent.idempotency_key), "idempotency key required")
        check("approval_present", bool(intent.approval_id), "approval reference required")
        if intent.order_type == OrderType.LIMIT:
            check("limit_price_present", intent.limit_price is not None and D(intent.limit_price) > 0, "limit order requires positive limit price")

        # 6. price deviation (limit vs ref)
        if intent.order_type == OrderType.LIMIT and intent.limit_price is not None and ref_price > 0:
            dev = abs(D(intent.limit_price) - ref_price) / ref_price * Decimal("100")
            check("price_deviation", dev <= self.limits.max_price_deviation_pct, f"limit deviates {dev:.2f}% > {self.limits.max_price_deviation_pct}%")

        # 7. notional limits
        est = intent.estimated_notional(ref_price)
        check("order_notional", est <= self.limits.max_order_notional, f"order notional {est} > max {self.limits.max_order_notional}")

        # 8. buying power (BUY needs cash incl. reserve)
        if intent.side == OrderSide.BUY:
            available = account.cash - self.limits.min_cash_reserve
            check("buying_power", est <= available, f"insufficient buying power: need {est}, available {available}")

        # 9. position notional + concentration after fill
        projected_qty = held + (D(intent.quantity) if intent.side == OrderSide.BUY else -D(intent.quantity))
        projected_notional = abs(projected_qty * ref_price).quantize(Decimal("0.01"))
        check("position_notional", projected_notional <= self.limits.max_position_notional, f"position notional {projected_notional} > max {self.limits.max_position_notional}")
        equity = account.equity({**marks, intent.symbol: ref_price})
        if equity > 0:
            conc = projected_notional / equity * Decimal("100")
            check("concentration", conc <= self.limits.max_symbol_concentration_pct, f"concentration {conc:.2f}% > {self.limits.max_symbol_concentration_pct}%")

        # 10. gross exposure + open positions + restricted symbols
        gross_after = account.gross_exposure({**marks, intent.symbol: ref_price}) + (est if intent.side == OrderSide.BUY else Decimal("0"))
        check("gross_exposure", gross_after <= self.limits.max_gross_exposure, f"gross exposure {gross_after} > max {self.limits.max_gross_exposure}")
        open_after = len(account.positions) + (0 if intent.symbol in account.positions else 1)
        check("max_open_positions", open_after <= self.limits.max_open_positions, f"open positions {open_after} > max {self.limits.max_open_positions}")
        check("not_restricted", intent.symbol not in self.limits.restricted_symbols, f"{intent.symbol} is restricted")

        return GuardianDecision(allowed=len(reasons) == 0, reasons=reasons, checks=checks)


def safety_posture() -> dict[str, str]:
    """Machine-readable snapshot of the disabled trading capabilities."""
    posture = {c: "DISABLED" for c in DEFAULT_DISABLED_CAPABILITIES}
    posture["LIVE_EXECUTION"] = "DISABLED"
    posture["HIGHEST_PERMITTED_TARGET"] = "PAPER_TRADING"
    return posture
