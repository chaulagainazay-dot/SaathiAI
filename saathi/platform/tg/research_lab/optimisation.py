"""Thin portfolio optimisation facade re-exporting PortfolioBuilder methods."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.research_lab.portfolio_builder import PortfolioBuilder
from saathi.platform.tg.research_lab.storage import ResearchLabStore


class PortfolioOptimiser:
    def __init__(self, store: ResearchLabStore):
        self.builder = PortfolioBuilder(store)

    def optimise(self, **kwargs: Any) -> dict[str, Any]:
        return self.builder.build(**kwargs)
