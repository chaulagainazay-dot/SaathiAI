"""No-trade control strategy — deterministic baseline that never trades."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.domain import MarketSnapshot, TradeSignal
from saathi.platform.tg.strategies.base import StrategyEvaluatorBase, StrategySpec

ASSUMPTIONS = [
    "Control baseline for regression, validation, and performance comparison.",
    "Always produces zero trade signals by design.",
]

INVALIDATION = [
    "N/A — never enters positions.",
]


class NoTradeControl(StrategyEvaluatorBase):
    def spec(self) -> StrategySpec:
        return StrategySpec(
            slug="no_trade",
            name="No-Trade Control",
            family="control",
            version="1.0.0",
            description="Deterministic baseline that produces no trades. Used for validation and comparison.",
            assumptions=ASSUMPTIONS,
            regime_compatibility=[
                "BULL_TREND", "BEAR_TREND", "SIDEWAYS",
                "HIGH_VOLATILITY", "LOW_LIQUIDITY", "EVENT_RISK", "UNKNOWN",
            ],
            invalidation_conditions=INVALIDATION,
            stop_logic="N/A",
            holding_horizon="N/A",
            confidence_components=["always_zero"],
            supported_instruments=["*"],
            supported_timeframes=["1d", "1h", "15m"],
            required_data_fields=[],
            parameter_schema={},
            default_parameters={},
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
        # Deterministic: always empty. Inputs intentionally unused.
        _ = (snapshot, params, correlation_id, org_id, workspace_id)
        return []
