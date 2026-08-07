"""Momentum and sector-relative-strength strategy."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.tg.domain import MarketSnapshot, TradeSignal
from saathi.platform.tg.strategies.base import StrategyEvaluatorBase, StrategySpec

ASSUMPTIONS = [
    "Relative strength vs sector/benchmark can identify leaders.",
    "Momentum continues in liquid markets with healthy breadth.",
    "Long-only paper simulation; no leverage.",
    "Requires liquidity filter and positive instrument + sector momentum.",
]

INVALIDATION = [
    "Instrument momentum turns negative.",
    "Sector momentum collapses.",
    "Breadth deteriorates below threshold.",
    "Liquidity filter fails.",
]


class MomentumRelativeStrength(StrategyEvaluatorBase):
    def spec(self) -> StrategySpec:
        return StrategySpec(
            slug="momentum_rs",
            name="Momentum & Sector Relative Strength",
            family="momentum",
            version="1.0.0",
            description=(
                "Instrument and sector momentum with relative-strength ranking signals, "
                "breadth filter, and liquidity gate."
            ),
            assumptions=ASSUMPTIONS,
            regime_compatibility=["BULL_TREND", "SIDEWAYS"],
            invalidation_conditions=INVALIDATION,
            stop_logic="Percentage stop under entry; optional trailing after +1R.",
            holding_horizon="3-20 sessions",
            confidence_components=[
                "instrument_momentum",
                "sector_momentum",
                "relative_strength",
                "breadth_ok",
                "liquidity_ok",
            ],
            supported_instruments=["*"],
            supported_timeframes=["1d"],
            required_data_fields=["close", "volume"],
            parameter_schema={
                "momentum_lookback": {"type": "integer", "min": 2, "max": 60},
                "min_instrument_momentum": {"type": "decimal"},
                "min_sector_momentum": {"type": "decimal"},
                "min_breadth": {"type": "decimal", "min": "0", "max": "1"},
                "min_liquidity": {"type": "decimal"},
                "stop_pct": {"type": "decimal", "min": "0.01", "max": "0.20"},
            },
            default_parameters={
                "momentum_lookback": 10,
                "min_instrument_momentum": "0.02",
                "min_sector_momentum": "0.0",
                "min_breadth": "0.45",
                "min_liquidity": "10000",
                "stop_pct": "0.05",
            },
        )

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        *,
        params: dict[str, Any],
        correlation_id: str = "",
        org_id: str = "",
        workspace_id: str = "",
    ) -> list[TradeSignal]:
        p = self._merged_params(params)
        closes = self._closes(snapshot)
        lookback = int(p["momentum_lookback"])
        min_im = Decimal(str(p["min_instrument_momentum"]))
        min_sm = Decimal(str(p["min_sector_momentum"]))
        min_breadth = Decimal(str(p["min_breadth"]))
        min_liq = Decimal(str(p["min_liquidity"]))
        stop_pct = Decimal(str(p["stop_pct"]))

        if len(closes) < lookback + 1:
            return []

        price = closes[-1]
        base = closes[-(lookback + 1)]
        if base <= 0:
            return []
        instrument_mom = (price - base) / base
        # Sector momentum proxied by benchmark_return on snapshot (explicit input)
        sector_mom = snapshot.benchmark_return
        # Relative strength: instrument vs benchmark over window
        rel_strength = instrument_mom - sector_mom
        breadth_ok = snapshot.breadth >= min_breadth
        liquidity_ok = (
            snapshot.avg_traded_value >= min_liq
            or snapshot.volume * price >= min_liq
        )

        # Leader classification: positive instrument + sector + RS
        is_leader = instrument_mom >= min_im and sector_mom >= min_sm and rel_strength > 0
        if not (is_leader and breadth_ok and liquidity_ok):
            return []

        stop_distance = price * stop_pct
        stop_price = price - stop_distance
        take_profit = price + stop_distance * Decimal("2")

        conf = Decimal("0")
        conf += Decimal("0.30") if instrument_mom >= min_im else Decimal("0")
        conf += Decimal("0.20") if sector_mom >= min_sm else Decimal("0")
        conf += Decimal("0.25") if rel_strength > 0 else Decimal("0")
        conf += Decimal("0.15") if breadth_ok else Decimal("0")
        conf += Decimal("0.10") if liquidity_ok else Decimal("0")

        sp = self.spec()
        return [TradeSignal(
            strategy_id=sp.slug,
            strategy_version=sp.version,
            strategy_fingerprint=sp.fingerprint(),
            symbol=snapshot.symbol,
            side="BUY",
            action="ENTER_LONG",
            confidence=conf,
            confidence_components={
                "instrument_momentum": str(instrument_mom),
                "sector_momentum": str(sector_mom),
                "relative_strength": str(rel_strength),
                "classification": "leader",
                "breadth": str(snapshot.breadth),
                "breadth_ok": breadth_ok,
                "liquidity_ok": liquidity_ok,
            },
            inputs={
                "price": str(price),
                "stop_price": str(stop_price),
                "take_profit_price": str(take_profit),
                "stop_distance": str(stop_distance),
            },
            explanation=(
                f"Momentum RS leader: instrument mom {instrument_mom:.2%}, sector {sector_mom:.2%}, "
                f"RS {rel_strength:.2%}, breadth {snapshot.breadth}."
            ),
            assumptions=list(ASSUMPTIONS),
            invalidation=list(INVALIDATION),
            stop_logic=sp.stop_logic,
            holding_horizon=sp.holding_horizon,
            regime_labels=list(sp.regime_compatibility),
            source_identity="momentum_rs",
            correlation_id=correlation_id,
            org_id=org_id,
            workspace_id=workspace_id,
        )]
