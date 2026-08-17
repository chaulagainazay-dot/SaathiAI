"""Versioned, auditable PAPER risk budgets (deterministic)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from saathi.platform.fund_ledger.money import D, q_money


@dataclass(frozen=True)
class RiskBudget:
    """Conservative PAPER defaults. Mutations require governance (not agents)."""

    version: str = "paper-risk-budget/v1"
    environment: str = "PAPER"
    # Exposure (fraction of NAV unless noted)
    max_gross_exposure: Decimal = field(default_factory=lambda: Decimal("1.00"))  # 100% NAV
    max_net_exposure: Decimal = field(default_factory=lambda: Decimal("1.00"))
    max_position_weight: Decimal = field(default_factory=lambda: Decimal("0.15"))  # 15%
    max_top3_concentration: Decimal = field(default_factory=lambda: Decimal("0.40"))
    max_top5_concentration: Decimal = field(default_factory=lambda: Decimal("0.60"))
    # Cash
    min_cash_buffer: Decimal = field(default_factory=lambda: Decimal("0.05"))  # 5% NAV
    # Loss / drawdown (fractions of NAV or absolute loss vs period start NAV)
    max_daily_loss: Decimal = field(default_factory=lambda: Decimal("0.03"))  # 3%
    max_weekly_loss: Decimal = field(default_factory=lambda: Decimal("0.07"))  # 7%
    max_drawdown: Decimal = field(default_factory=lambda: Decimal("0.15"))  # 15%
    # Trade
    max_trade_notional: Decimal = field(default_factory=lambda: Decimal("10000"))
    max_trade_risk_fraction: Decimal = field(default_factory=lambda: Decimal("0.01"))  # 1% NAV risk
    # Data freshness
    max_mark_age_seconds: float = 86400.0
    # Soft warning thresholds (fraction of hard limit, 0-1)
    soft_warning_ratio: Decimal = field(default_factory=lambda: Decimal("0.85"))
    # Feature flags
    leverage_enabled: bool = False
    shorts_enabled: bool = False
    sector_concentration_enabled: bool = False  # deferred without metadata
    # Period timezone
    period_timezone: str = "UTC"

    def to_public(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, Decimal):
                d[k] = str(v)
        return d

    def soft_threshold(self, hard: Decimal) -> Decimal:
        return q_money(D(hard) * D(self.soft_warning_ratio))


PAPER_BUDGET_V1 = RiskBudget()
