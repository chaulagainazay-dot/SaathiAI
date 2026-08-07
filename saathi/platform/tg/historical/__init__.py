"""M184–M191 — Historical market data, research orchestration, and qualification.

Composes over M62 market_data and M166–M183 Trading Guardian. Paper research only.
No live orders, no broker credentials, no LLM authority over metrics or eligibility.
"""
from __future__ import annotations

from saathi.platform.tg.historical.models import (
    SCHEMA_VERSION as HISTORICAL_SCHEMA_VERSION,
    DataQualityVerdict,
    DatasetClassification,
    HistoricalDataset,
    DatasetVersion,
    DatasetManifest,
    CorporateAction,
    DataQualityReport,
    AdjustedPriceBar,
)
from saathi.platform.tg.historical.store import HistoricalDatasetStore
from saathi.platform.tg.historical.quality import evaluate_dataset_quality
from saathi.platform.tg.historical.normalize import apply_corporate_actions, NormalizationAudit
from saathi.platform.tg.historical.monte_carlo import run_monte_carlo, MonteCarloVerdict
from saathi.platform.tg.historical.research import HistoricalResearchRunner, ResearchPeriod
from saathi.platform.tg.historical.qualification import qualify_strategy, QualificationGates
from saathi.platform.tg.historical.calendars import get_market_calendar, SUPPORTED_MARKET_CALENDARS

__all__ = [
    "HISTORICAL_SCHEMA_VERSION",
    "DataQualityVerdict",
    "DatasetClassification",
    "HistoricalDataset",
    "DatasetVersion",
    "DatasetManifest",
    "CorporateAction",
    "DataQualityReport",
    "AdjustedPriceBar",
    "HistoricalDatasetStore",
    "evaluate_dataset_quality",
    "apply_corporate_actions",
    "NormalizationAudit",
    "run_monte_carlo",
    "MonteCarloVerdict",
    "HistoricalResearchRunner",
    "ResearchPeriod",
    "qualify_strategy",
    "QualificationGates",
    "get_market_calendar",
    "SUPPORTED_MARKET_CALENDARS",
]
