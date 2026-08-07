"""Kotegawa-inspired mean-reversion strategy (public principles interpretation).

NOT an exact reproduction of Takashi Kotegawa's private method.
Requires confirmation beyond mere price decline. Paper/research only.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.tg.domain import MarketSnapshot, TradeSignal
from saathi.platform.tg.strategies.base import StrategyEvaluatorBase, StrategySpec

ASSUMPTIONS = [
    "Interpretation of publicly discussed mean-reversion principles only.",
    "Not an exact reproduction of any private trading method.",
    "Requires multi-factor confirmation; price decline alone is insufficient.",
    "Long-only, paper simulation, no leverage.",
    "Works best in liquid equities with mean-reverting short-term behavior.",
    "Event/earnings windows should be excluded by policy.",
    "Historical/simulated edge may decay; no profitability claim.",
]

INVALIDATION = [
    "Breakdown below volatility-normalized stop without reversal confirmation.",
    "Liquidity below threshold or spread above maximum.",
    "Event-risk or earnings-window flag active.",
    "Regime classified as BEAR_TREND without exhaustion confirmation.",
    "Volume spike without exhaustion signature (panic continuation).",
]


class KotegawaMeanReversion(StrategyEvaluatorBase):
    def spec(self) -> StrategySpec:
        return StrategySpec(
            slug="kotegawa_mean_reversion",
            name="Kotegawa-inspired Mean Reversion",
            family="mean_reversion",
            version="1.0.0",
            description=(
                "Governed mean-reversion inspired by publicly discussed principles: "
                "deviation from short-term MA, abnormal volume, volatility normalization, "
                "and reversal confirmation. Never buys solely because price fell."
            ),
            assumptions=ASSUMPTIONS,
            regime_compatibility=["SIDEWAYS", "HIGH_VOLATILITY", "BULL_TREND"],
            invalidation_conditions=INVALIDATION,
            stop_logic="Volatility-normalized stop below entry (k * rolling std); hard max stop distance from policy.",
            holding_horizon="1-10 sessions (short-term reversion)",
            confidence_components=[
                "ma_deviation",
                "volume_abnormality",
                "reversal_confirmation",
                "liquidity_ok",
                "spread_ok",
                "volatility_normalized",
            ],
            supported_instruments=["*"],
            supported_timeframes=["1d"],
            required_data_fields=["close", "volume", "high", "low"],
            parameter_schema={
                "ma_period": {"type": "integer", "min": 3, "max": 50},
                "deviation_threshold": {"type": "decimal", "min": "0.01", "max": "0.20"},
                "volume_spike_ratio": {"type": "decimal", "min": "1.2", "max": "5.0"},
                "reversal_require_green": {"type": "boolean"},
                "min_liquidity": {"type": "decimal", "min": "0"},
                "max_spread": {"type": "decimal", "min": "0"},
                "stop_vol_mult": {"type": "decimal", "min": "0.5", "max": "5.0"},
            },
            default_parameters={
                "ma_period": 10,
                "deviation_threshold": "0.03",
                "volume_spike_ratio": "1.8",
                "reversal_require_green": True,
                "min_liquidity": "10000",
                "max_spread": "0.02",
                "stop_vol_mult": "2.0",
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
        ma_period = int(p["ma_period"])
        dev_thr = Decimal(str(p["deviation_threshold"]))
        vol_ratio_thr = Decimal(str(p["volume_spike_ratio"]))
        min_liq = Decimal(str(p["min_liquidity"]))
        max_spread = Decimal(str(p["max_spread"]))
        stop_vol_mult = Decimal(str(p["stop_vol_mult"]))
        require_green = bool(p["reversal_require_green"])

        if len(closes) < ma_period + 1:
            return []  # insufficient data — no signal

        sma = self._sma(closes, ma_period)
        if sma is None or sma <= 0:
            return []

        price = closes[-1]
        prev = closes[-2]
        deviation = (price - sma) / sma  # negative when below MA

        # Liquidity / spread gates (strategy-level; policy re-checks)
        liquidity_ok = snapshot.avg_traded_value >= min_liq or snapshot.volume * price >= min_liq
        spread_ok = snapshot.spread <= max_spread if snapshot.spread > 0 else True

        # Volume abnormality
        vol_sma = self._sma(volumes, min(ma_period, len(volumes))) if volumes else None
        vol_ratio = (volumes[-1] / vol_sma) if vol_sma and vol_sma > 0 else Decimal("0")
        volume_abnormal = vol_ratio >= vol_ratio_thr

        # Reversal confirmation: not buy on pure decline
        # Require (a) deviation below threshold AND (b) current bar not continuing lower, OR green bar
        bar_up = price > prev
        not_free_fall = price >= prev  # halt of decline at minimum
        reversal_ok = bar_up if require_green else not_free_fall

        # Volatility normalization for stop
        rets = []
        for i in range(1, min(len(closes), ma_period + 1)):
            if closes[-i - 1] > 0:
                rets.append((closes[-i] - closes[-i - 1]) / closes[-i - 1])
        vol = self._std(rets) or Decimal("0.02")
        stop_distance = price * vol * stop_vol_mult
        if stop_distance <= 0:
            return []

        # NEVER buy solely because price fell
        price_fell = price < prev
        components = {
            "ma_deviation": str(deviation),
            "below_ma": deviation < -dev_thr,
            "volume_abnormal": volume_abnormal,
            "volume_ratio": str(vol_ratio),
            "reversal_confirmation": reversal_ok,
            "liquidity_ok": liquidity_ok,
            "spread_ok": spread_ok,
            "price_fell_alone_insufficient": True,
            "would_reject_pure_decline": price_fell and not reversal_ok,
        }

        if not (deviation < -dev_thr and volume_abnormal and reversal_ok and liquidity_ok and spread_ok):
            return []

        # Confidence from explicit components (0..1)
        conf = Decimal("0")
        conf += Decimal("0.30") if deviation < -dev_thr else Decimal("0")
        conf += Decimal("0.25") if volume_abnormal else Decimal("0")
        conf += Decimal("0.25") if reversal_ok else Decimal("0")
        conf += Decimal("0.10") if liquidity_ok else Decimal("0")
        conf += Decimal("0.10") if spread_ok else Decimal("0")

        stop_price = price - stop_distance
        take_profit = price + stop_distance * Decimal("2")  # target R:R 2 before policy clamp

        sp = self.spec()
        return [TradeSignal(
            strategy_id=sp.slug,
            strategy_version=sp.version,
            strategy_fingerprint=sp.fingerprint(),
            symbol=snapshot.symbol,
            side="BUY",
            action="ENTER_LONG",
            confidence=conf,
            confidence_components=components,
            inputs={
                "sma": str(sma),
                "price": str(price),
                "deviation": str(deviation),
                "volume_ratio": str(vol_ratio),
                "stop_price": str(stop_price),
                "take_profit_price": str(take_profit),
                "stop_distance": str(stop_distance),
            },
            explanation=(
                f"Mean-reversion candidate: price {price} is {deviation:.2%} below SMA({ma_period})={sma}, "
                f"volume ratio {vol_ratio:.2f}x, reversal confirmed={reversal_ok}. "
                f"Not a pure-decline entry."
            ),
            assumptions=list(ASSUMPTIONS),
            invalidation=list(INVALIDATION),
            stop_logic=sp.stop_logic,
            holding_horizon=sp.holding_horizon,
            regime_labels=list(sp.regime_compatibility),
            source_identity="kotegawa_mean_reversion",
            correlation_id=correlation_id,
            org_id=org_id,
            workspace_id=workspace_id,
        )]
