"""T-NEXT-2 — Independent portfolio risk engine (PAPER).

Ledger owns books. This package owns risk measurement, budgets, and breach detection.
Trading Guardian owns allow/deny. Agents cannot override BLOCK.
"""
from __future__ import annotations

from saathi.platform.portfolio_risk_engine.budget import PAPER_BUDGET_V1, PAPER_BUDGET_V2, RiskBudget
from saathi.platform.portfolio_risk_engine.engine import PortfolioRiskEngine
from saathi.platform.portfolio_risk_engine.models import (
    LimitSeverity,
    RiskDecision,
    RiskState,
    TradeProposal,
)
from saathi.platform.portfolio_risk_engine.tg_compose import compose_guardian_with_risk

__all__ = [
    "PAPER_BUDGET_V1",
    "PAPER_BUDGET_V2",
    "RiskBudget",
    "PortfolioRiskEngine",
    "LimitSeverity",
    "RiskDecision",
    "RiskState",
    "TradeProposal",
    "compose_guardian_with_risk",
]

ENGINE_VERSION = "portfolio-risk-engine/2.0.0"
AUTHORITY = "INDEPENDENT_PORTFOLIO_RISK_ENGINE"
ENVIRONMENT = "PAPER"
