"""T-NEXT-3 — Deterministic portfolio construction & rebalancing proposals.

ZERO execution / approval / TG override / ledger mutation authority.
"""
from __future__ import annotations

from saathi.platform.portfolio_construction.engine import PortfolioConstructionEngine
from saathi.platform.portfolio_construction.models import (
    ProposalStatus,
    RebalanceAction,
    ConstructionMethod,
)

__all__ = [
    "PortfolioConstructionEngine",
    "ProposalStatus",
    "RebalanceAction",
    "ConstructionMethod",
]

ENGINE_VERSION = "portfolio-construction/1.0.0"
AUTHORITY = "PORTFOLIO_CONSTRUCTION_PROPOSAL_ONLY"
