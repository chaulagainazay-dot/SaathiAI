"""M167 — Governed strategy catalog.

Four high-quality strategies only. Each produces structured proposals/signals —
never direct orders. No opaque LLM entry/exit signals.
"""
from __future__ import annotations

from typing import Any, Callable

from saathi.platform.tg.domain import MarketSnapshot, TradeSignal
from saathi.platform.tg.strategies.base import StrategyEvaluatorBase, StrategySpec
from saathi.platform.tg.strategies.kotegawa_mean_reversion import KotegawaMeanReversion
from saathi.platform.tg.strategies.trend_following import TrendFollowing
from saathi.platform.tg.strategies.momentum_rs import MomentumRelativeStrength
from saathi.platform.tg.strategies.no_trade import NoTradeControl

CATALOG: dict[str, StrategyEvaluatorBase] = {
    "kotegawa_mean_reversion": KotegawaMeanReversion(),
    "trend_following": TrendFollowing(),
    "momentum_rs": MomentumRelativeStrength(),
    "no_trade": NoTradeControl(),
}


def get_catalog_strategy(slug: str) -> StrategyEvaluatorBase:
    if slug not in CATALOG:
        raise KeyError(f"unknown catalog strategy: {slug}")
    return CATALOG[slug]


def list_catalog() -> list[dict[str, Any]]:
    return [s.spec().to_public() for s in CATALOG.values()]


def evaluate_catalog(
    slug: str,
    snapshot: MarketSnapshot,
    *,
    params: dict[str, Any] | None = None,
    correlation_id: str = "",
    org_id: str = "",
    workspace_id: str = "",
) -> list[TradeSignal]:
    return get_catalog_strategy(slug).evaluate(
        snapshot,
        params=params or {},
        correlation_id=correlation_id,
        org_id=org_id,
        workspace_id=workspace_id,
    )


__all__ = [
    "CATALOG",
    "StrategyEvaluatorBase",
    "StrategySpec",
    "KotegawaMeanReversion",
    "TrendFollowing",
    "MomentumRelativeStrength",
    "NoTradeControl",
    "get_catalog_strategy",
    "list_catalog",
    "evaluate_catalog",
]
