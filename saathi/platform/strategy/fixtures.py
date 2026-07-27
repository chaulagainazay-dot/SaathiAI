"""M62.4 — deterministic strategy fixtures + broken-strategy certification matrix.

Valid fixtures give the happy path a stable, hashable definition. The BROKEN matrix
encodes each unsafe/invalid strategy the certification suite must prove fails, with
the EXPECTED failure reason. Nothing here executes real orders.
"""
from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal
from typing import Any, Callable

from saathi.platform.market_data.models import Timeframe
from saathi.platform.strategy.models import (
    StrategyDefinition, StrategyType, FeatureSpec, FeatureKind, SignalRule, Comparator,
    SignalAction, SizingRule, SizingMethod, CostModel, REALISTIC_COST, ZERO_COST, strategy_hash,
)
from saathi.platform.strategy.features import BacktestContext

FIXTURE_VERSION = "m62_4.strat.v1"


def _defn(**kw) -> StrategyDefinition:
    base = dict(
        id="fixture", org_id="o", workspace_id="w", name=kw.get("name", "fx"),
        strategy_type=StrategyType.MOMENTUM, instrument_universe=["TRENDING"], timeframe=Timeframe.D1,
        features=[], signals=[], sizing=SizingRule(SizingMethod.EQUITY_FRACTION, Decimal("0.5"), Decimal("1")),
        cost_model=REALISTIC_COST, warmup_bars=2, created_by="system",
    )
    base.update(kw)
    return StrategyDefinition(**base)


# ── valid strategies ─────────────────────────────────────────────────────────
def valid_momentum(instrument: str = "TRENDING") -> StrategyDefinition:
    return _defn(
        name="sma_crossover", strategy_type=StrategyType.MOMENTUM, instrument_universe=[instrument],
        features=[FeatureSpec("sma_fast", FeatureKind.SMA, lookback=3),
                  FeatureSpec("sma_slow", FeatureKind.SMA, lookback=10)],
        signals=[SignalRule("sma_fast", Comparator.GT, "sma_slow", SignalAction.ENTER_LONG),
                 SignalRule("sma_fast", Comparator.LT, "sma_slow", SignalAction.EXIT)],
        sizing=SizingRule(SizingMethod.EQUITY_FRACTION, Decimal("0.5"), Decimal("1")),
        warmup_bars=10, benchmark=instrument,
    )


def valid_mean_reversion(instrument: str = "MEAN_REVERTING") -> StrategyDefinition:
    return _defn(
        name="deviation_reversion", strategy_type=StrategyType.MEAN_REVERSION, instrument_universe=[instrument],
        features=[FeatureSpec("dev", FeatureKind.PRICE_DEVIATION, lookback=5)],
        signals=[SignalRule("dev", Comparator.LT, "-0.01", SignalAction.ENTER_LONG),
                 SignalRule("dev", Comparator.GT, "0.01", SignalAction.EXIT)],
        sizing=SizingRule(SizingMethod.EQUITY_FRACTION, Decimal("0.4"), Decimal("1")),
        warmup_bars=6, benchmark=instrument,
    )


def valid_buy_and_hold(instrument: str = "TRENDING") -> StrategyDefinition:
    return _defn(
        name="buy_and_hold", strategy_type=StrategyType.BUY_AND_HOLD, instrument_universe=[instrument],
        features=[FeatureSpec("ret", FeatureKind.RETURN, lookback=1)],
        signals=[SignalRule("ret", Comparator.GTE, "-9999", SignalAction.ENTER_LONG)],
        sizing=SizingRule(SizingMethod.EQUITY_FRACTION, Decimal("0.9"), Decimal("1")),
        warmup_bars=1, benchmark=instrument,
    )


VALID_FIXTURES: dict[str, Callable[[], StrategyDefinition]] = {
    "VALID_MOMENTUM": valid_momentum,
    "VALID_MEAN_REVERSION": valid_mean_reversion,
    "VALID_BUY_AND_HOLD": valid_buy_and_hold,
}


# ── broken strategy matrix ────────────────────────────────────────────────────
# Each entry: builder -> StrategyDefinition, optional probe (adversarial hook),
# expected failure channel + code, and the dataset to run on.
def _future_return_feature() -> StrategyDefinition:
    d = valid_momentum()
    d.features = [FeatureSpec("future_ret", FeatureKind.RETURN, lookback=1, forward_offset=1)]
    d.signals = [SignalRule("future_ret", Comparator.GT, "0", SignalAction.ENTER_LONG)]
    return d


def _unbounded_position() -> StrategyDefinition:
    d = valid_momentum()
    d.sizing = SizingRule(SizingMethod.EQUITY_FRACTION, Decimal("3"), Decimal("1"))
    return d


def _excessive_leverage() -> StrategyDefinition:
    d = valid_momentum()
    d.sizing = SizingRule(SizingMethod.EQUITY_FRACTION, Decimal("0.5"), Decimal("5"))
    d.risk_max_position_fraction = Decimal("5")
    return d


def _duplicate_order() -> StrategyDefinition:
    # tries to ENTER_LONG on every bar; the engine's held==0 guard must dedup
    d = valid_momentum()
    d.features = [FeatureSpec("ret", FeatureKind.RETURN, lookback=1)]
    d.signals = [SignalRule("ret", Comparator.GTE, "-9999", SignalAction.ENTER_LONG)]
    return d


def _zero_cost_dependent() -> StrategyDefinition:
    # high-turnover reversion churn whose edge is smaller than stressed costs
    d = valid_mean_reversion("MEAN_REVERTING")
    d.name = "cost_fragile_churn"
    d.features = [FeatureSpec("dev", FeatureKind.PRICE_DEVIATION, lookback=3)]
    d.signals = [SignalRule("dev", Comparator.LT, "0", SignalAction.ENTER_LONG),
                 SignalRule("dev", Comparator.GT, "0", SignalAction.EXIT)]
    d.sizing = SizingRule(SizingMethod.EQUITY_FRACTION, Decimal("0.95"), Decimal("1"))
    d.warmup_bars = 4
    return d


def _look_ahead_probe(ctx: BacktestContext) -> None:
    # deliberately read one bar into the future; recorded by instrumentation
    ctx.future_peek(1)


LOOK_AHEAD_STRATEGY = valid_momentum


BROKEN_MATRIX: dict[str, dict[str, Any]] = {
    "LOOK_AHEAD_STRATEGY": {
        "builder": valid_momentum, "probe": _look_ahead_probe, "dataset": "TRENDING",
        "expected_channel": "engine", "expected_status": "REJECTED", "expected_code": "look-ahead",
    },
    "FUTURE_RETURN_FEATURE": {
        "builder": _future_return_feature, "dataset": "TRENDING",
        "expected_channel": "structural", "expected_status": "REJECTED", "expected_code": "FUTURE_RETURN_FEATURE",
    },
    "UNBOUNDED_POSITION_SIZE": {
        "builder": _unbounded_position, "dataset": "TRENDING",
        "expected_channel": "structural", "expected_status": "REJECTED", "expected_code": "UNBOUNDED_POSITION_SIZE",
    },
    "EXCESSIVE_LEVERAGE_REQUEST": {
        "builder": _excessive_leverage, "dataset": "TRENDING",
        "expected_channel": "structural", "expected_status": "REJECTED", "expected_code": "EXCESSIVE_LEVERAGE_REQUEST",
    },
    "DUPLICATE_ORDER_STRATEGY": {
        "builder": _duplicate_order, "dataset": "TRENDING",
        "expected_channel": "engine_guard", "expected_status": "COMPLETE", "expected_code": "single_entry",
    },
    "ZERO_COST_DEPENDENT": {
        "builder": _zero_cost_dependent, "dataset": "MEAN_REVERTING",
        "expected_channel": "cost", "expected_status": "COMPLETE", "expected_code": "cost_sensitive",
    },
    "SINGLE_TRADE_OVERFIT": {
        "builder": valid_buy_and_hold, "dataset": "TRENDING",
        "expected_channel": "validation", "expected_status": "COMPLETE", "expected_code": "SINGLE_TRADE_DOMINANCE",
    },
    "TEST_SET_TUNED": {
        "builder": valid_momentum, "dataset": "TRENDING",
        "expected_channel": "walk_forward", "expected_status": "COMPLETE", "expected_code": "selected_before_test",
    },
    "MISSING_DATA_IGNORER": {
        "builder": valid_momentum, "dataset": "MISSING_BARS",
        "expected_channel": "quality", "expected_status": "COMPLETE", "expected_code": "gap_surfaced",
    },
    "INVALID_PRICE_ACCEPTOR": {
        "builder": valid_momentum, "dataset": "INVALID_OHLC",
        "expected_channel": "quality", "expected_status": "REJECTED", "expected_code": "data quality blocking",
    },
}


def strategy_fixture_manifest() -> dict[str, Any]:
    valid = {name: strategy_hash(fn()) for name, fn in VALID_FIXTURES.items()}
    broken = {name: strategy_hash(spec["builder"]()) for name, spec in BROKEN_MATRIX.items()}
    return {"version": FIXTURE_VERSION, "valid": valid, "broken": broken}
