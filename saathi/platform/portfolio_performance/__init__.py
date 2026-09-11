"""T-NEXT-4 — Deterministic portfolio performance history & position contribution.

Read/derived truth only. Never mutates ledger, risk budgets, proposals, or orders.
"""
from __future__ import annotations

from saathi.platform.portfolio_performance.engine import PortfolioPerformanceEngine

__all__ = ["PortfolioPerformanceEngine"]

ENGINE_VERSION = "portfolio-performance/1.0.0"
AUTHORITY = "PORTFOLIO_PERFORMANCE_READ_ONLY"
