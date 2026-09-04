"""Deterministic performance policy defaults (PAPER)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PerformancePolicy:
    # observation
    min_observations_for_volatility: int = 20
    min_observations_for_sharpe: int = 30
    annualization_factor: int = 252  # trading-day convention when daily
    # returns
    weight_sum_tolerance: Decimal = Decimal("0.01")  # money units for P&L reconcile
    contribution_tolerance: Decimal = Decimal("0.05")
    # cash flows
    external_flow_types: tuple = ("DEPOSIT", "WITHDRAWAL_SIM")
    # win/loss unit
    win_loss_unit: str = "closed_lot"  # canonical
    # risk-free for Sharpe (explicit PAPER assumption)
    risk_free_rate_annual: Decimal = Decimal("0")  # documented zero for PAPER research
    risk_free_assumption: str = "ZERO_RATE_PAPER_EXPLICIT"
    # benchmark
    benchmark_enabled: bool = False
    # currency
    multi_currency: bool = False
    currency_boundary: str = "SINGLE_BASE_CURRENCY_ONLY"
    # drawdown
    # never report positive drawdown (drawdown is loss from peak as non-negative fraction)

    def to_public(self) -> dict:
        return {
            "min_observations_for_volatility": self.min_observations_for_volatility,
            "min_observations_for_sharpe": self.min_observations_for_sharpe,
            "annualization_factor": self.annualization_factor,
            "win_loss_unit": self.win_loss_unit,
            "risk_free_assumption": self.risk_free_assumption,
            "risk_free_rate_annual": str(self.risk_free_rate_annual),
            "benchmark_enabled": self.benchmark_enabled,
            "currency_boundary": self.currency_boundary,
            "return_methodology": "TWR_when_external_flows_else_SIMPLE",
        }


DEFAULT_POLICY = PerformancePolicy()
