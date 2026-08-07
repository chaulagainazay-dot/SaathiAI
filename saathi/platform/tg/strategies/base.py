"""Base contract for governed catalog strategies."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from saathi.platform.tg.domain import MarketSnapshot, TradeSignal, strategy_fingerprint


@dataclass
class StrategySpec:
    slug: str
    name: str
    family: str
    version: str = "1.0.0"
    description: str = ""
    assumptions: list[str] = field(default_factory=list)
    regime_compatibility: list[str] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)
    stop_logic: str = ""
    holding_horizon: str = ""
    confidence_components: list[str] = field(default_factory=list)
    supported_instruments: list[str] = field(default_factory=list)
    supported_timeframes: list[str] = field(default_factory=lambda: ["1d"])
    required_data_fields: list[str] = field(default_factory=lambda: ["close", "volume"])
    parameter_schema: dict[str, Any] = field(default_factory=dict)
    default_parameters: dict[str, Any] = field(default_factory=dict)
    paper_only: bool = True

    def fingerprint(self) -> str:
        return strategy_fingerprint({
            "slug": self.slug,
            "version": self.version,
            "family": self.family,
            "parameters": self.default_parameters,
            "parameter_schema": self.parameter_schema,
            "supported_instruments": self.supported_instruments,
            "supported_timeframes": self.supported_timeframes,
            "required_data_fields": self.required_data_fields,
            "regime_compatibility": self.regime_compatibility,
            "stop_logic": self.stop_logic,
            "holding_horizon": self.holding_horizon,
        })

    def to_public(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "family": self.family,
            "version": self.version,
            "description": self.description,
            "assumptions": list(self.assumptions),
            "regime_compatibility": list(self.regime_compatibility),
            "invalidation_conditions": list(self.invalidation_conditions),
            "stop_logic": self.stop_logic,
            "holding_horizon": self.holding_horizon,
            "confidence_components": list(self.confidence_components),
            "supported_instruments": list(self.supported_instruments),
            "supported_timeframes": list(self.supported_timeframes),
            "required_data_fields": list(self.required_data_fields),
            "parameter_schema": dict(self.parameter_schema),
            "default_parameters": dict(self.default_parameters),
            "fingerprint": self.fingerprint(),
            "paper_only": True,
            "live_authorized": False,
            "llm_signals": False,
        }


class StrategyEvaluatorBase(ABC):
    """Deterministic strategy evaluator. Produces TradeSignal list only."""

    @abstractmethod
    def spec(self) -> StrategySpec:
        ...

    @abstractmethod
    def evaluate(
        self,
        snapshot: MarketSnapshot,
        *,
        params: dict[str, Any],
        correlation_id: str = "",
        org_id: str = "",
        workspace_id: str = "",
    ) -> list[TradeSignal]:
        ...

    def _merged_params(self, params: dict[str, Any]) -> dict[str, Any]:
        out = dict(self.spec().default_parameters)
        out.update(params or {})
        return out

    def _sma(self, closes: list[Decimal], period: int) -> Decimal | None:
        if period < 1 or len(closes) < period:
            return None
        window = closes[-period:]
        return sum(window, Decimal("0")) / Decimal(period)

    def _std(self, values: list[Decimal]) -> Decimal | None:
        n = len(values)
        if n < 2:
            return None
        mean = sum(values, Decimal("0")) / Decimal(n)
        var = sum((v - mean) ** 2 for v in values) / Decimal(n - 1)
        # Decimal sqrt via float is avoided; use Newton for stability on small sets
        x = var
        if x <= 0:
            return Decimal("0")
        guess = x / 2 if x > 1 else x
        for _ in range(20):
            if guess == 0:
                break
            guess = (guess + x / guess) / 2
        return guess

    def _closes(self, snapshot: MarketSnapshot) -> list[Decimal]:
        if snapshot.bars:
            return [b.close for b in snapshot.bars]
        return [snapshot.last_price] if snapshot.last_price > 0 else []

    def _volumes(self, snapshot: MarketSnapshot) -> list[Decimal]:
        if snapshot.bars:
            return [b.volume for b in snapshot.bars]
        return [snapshot.volume]
