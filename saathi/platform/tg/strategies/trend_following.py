"""Trend-following strategy — MA alignment, breakout, volume confirmation."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.tg.domain import MarketSnapshot, TradeSignal
from saathi.platform.tg.strategies.base import StrategyEvaluatorBase, StrategySpec

ASSUMPTIONS = [
    "Trends persist over intermediate horizons more often than they reverse abruptly.",
    "Long-only; requires MA alignment and breakout confirmation.",
    "Volume confirmation reduces false breakouts but does not eliminate them.",
    "Paper/simulation only; no leverage.",
]

INVALIDATION = [
    "Fast MA crosses below slow MA.",
    "Close below volatility-adjusted trailing stop.",
    "Break of recent swing low after entry.",
    "Liquidity collapse or event-risk flag.",
]


class TrendFollowing(StrategyEvaluatorBase):
    def spec(self) -> StrategySpec:
        return StrategySpec(
            slug="trend_following",
            name="Trend Following",
            family="trend",
            version="1.0.0",
            description=(
                "Moving-average alignment with breakout confirmation, volume support, "
                "and volatility-adjusted stop."
            ),
            assumptions=ASSUMPTIONS,
            regime_compatibility=["BULL_TREND"],
            invalidation_conditions=INVALIDATION,
            stop_logic="Volatility-adjusted stop under entry (ATR/std multiple); trail on new highs.",
            holding_horizon="5-40 sessions",
            confidence_components=[
                "ma_alignment",
                "breakout_confirmation",
                "volume_confirmation",
                "trend_persistence",
            ],
            supported_instruments=["*"],
            supported_timeframes=["1d"],
            required_data_fields=["close", "high", "volume"],
            parameter_schema={
                "fast_ma": {"type": "integer", "min": 2, "max": 50},
                "slow_ma": {"type": "integer", "min": 5, "max": 200},
                "breakout_lookback": {"type": "integer", "min": 3, "max": 60},
                "volume_confirm_ratio": {"type": "decimal", "min": "1.0", "max": "3.0"},
                "stop_vol_mult": {"type": "decimal", "min": "0.5", "max": "5.0"},
            },
            default_parameters={
                "fast_ma": 5,
                "slow_ma": 20,
                "breakout_lookback": 10,
                "volume_confirm_ratio": "1.2",
                "stop_vol_mult": "2.5",
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
        volumes = self._volumes(snapshot)
        fast_n = int(p["fast_ma"])
        slow_n = int(p["slow_ma"])
        br_n = int(p["breakout_lookback"])
        vol_thr = Decimal(str(p["volume_confirm_ratio"]))
        stop_mult = Decimal(str(p["stop_vol_mult"]))

        if slow_n <= fast_n or len(closes) < max(slow_n, br_n) + 1:
            return []

        fast = self._sma(closes, fast_n)
        slow = self._sma(closes, slow_n)
        if fast is None or slow is None:
            return []

        price = closes[-1]
        prior_high = max(closes[-(br_n + 1):-1]) if len(closes) > br_n else closes[0]
        ma_aligned = fast > slow and price > fast
        breakout = price > prior_high

        vol_sma = self._sma(volumes, min(slow_n, len(volumes))) if volumes else None
        vol_ratio = (volumes[-1] / vol_sma) if vol_sma and vol_sma > 0 else Decimal("0")
        volume_ok = vol_ratio >= vol_thr

        # Persistence: fraction of last N bars with price > slow MA
        persist_window = closes[-slow_n:]
        above = sum(1 for c in persist_window if c > slow)
        persistence = Decimal(above) / Decimal(len(persist_window))

        if not (ma_aligned and breakout and volume_ok):
            return []

        rets = []
        for i in range(1, min(len(closes), slow_n + 1)):
            if closes[-i - 1] > 0:
                rets.append((closes[-i] - closes[-i - 1]) / closes[-i - 1])
        vol = self._std(rets) or Decimal("0.02")
        stop_distance = price * vol * stop_mult
        stop_price = price - stop_distance
        take_profit = price + stop_distance * Decimal("2.5")

        conf = Decimal("0")
        conf += Decimal("0.35") if ma_aligned else Decimal("0")
        conf += Decimal("0.30") if breakout else Decimal("0")
        conf += Decimal("0.20") if volume_ok else Decimal("0")
        conf += Decimal("0.15") if persistence >= Decimal("0.6") else Decimal("0")

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
                "ma_alignment": ma_aligned,
                "fast_ma": str(fast),
                "slow_ma": str(slow),
                "breakout_confirmation": breakout,
                "prior_high": str(prior_high),
                "volume_confirmation": volume_ok,
                "volume_ratio": str(vol_ratio),
                "trend_persistence": str(persistence),
            },
            inputs={
                "price": str(price),
                "stop_price": str(stop_price),
                "take_profit_price": str(take_profit),
                "stop_distance": str(stop_distance),
            },
            explanation=(
                f"Trend entry: fast MA {fast} > slow MA {slow}, breakout above {prior_high}, "
                f"volume ratio {vol_ratio:.2f}x, persistence {persistence:.0%}."
            ),
            assumptions=list(ASSUMPTIONS),
            invalidation=list(INVALIDATION),
            stop_logic=sp.stop_logic,
            holding_horizon=sp.holding_horizon,
            regime_labels=list(sp.regime_compatibility),
            source_identity="trend_following",
            correlation_id=correlation_id,
            org_id=org_id,
            workspace_id=workspace_id,
        )]
