"""T-NEXT-3 — Deterministic portfolio construction & rebalancing proposals.

ZERO execution / approval / TG override / ledger mutation authority.
"""
from __future__ import annotations

from saathi.platform.portfolio_construction.engine import PortfolioConstructionEngine
from saathi.platform.portfolio_construction.models import (
    CandidatePortfolio,
    CandidatePortfolioStatus,
    ProposalStatus,
    RebalanceAction,
    ConstructionMethod,
    ConstructionReasonCode,
    InstrumentMetadata,
    PortfolioConstructionRequest,
    PortfolioPosition,
    PortfolioSnapshotInput,
    StrategyQualificationEvidence,
    StrategyQualificationStatus,
)

__all__ = [
    "PortfolioConstructionEngine",
    "CandidatePortfolio",
    "CandidatePortfolioStatus",
    "ProposalStatus",
    "RebalanceAction",
    "ConstructionMethod",
    "ConstructionReasonCode",
    "InstrumentMetadata",
    "PortfolioConstructionRequest",
    "PortfolioPosition",
    "PortfolioSnapshotInput",
    "StrategyQualificationEvidence",
    "StrategyQualificationStatus",
]

ENGINE_VERSION = "portfolio-construction/2.0.0"
AUTHORITY = "PORTFOLIO_CONSTRUCTION_PROPOSAL_ONLY"
