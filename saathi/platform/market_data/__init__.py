"""M62.2 — deterministic market-data quality, storage, and replay foundation.

Provider-neutral, decimal-precise, timezone-aware, fail-closed. Data only — no
order submission, no broker access, no execution authority. See
docs/trading/MARKET_DATA.md.
"""
from saathi.platform.market_data.models import (
    Timeframe, TIMEFRAME_SECONDS, MarketDataQuality, QualityFinding,
    MDInstrument, MDQuote, MDBar, FreshnessPolicy, DEFAULT_FRESHNESS,
    to_data_quality, require_aware, is_aware,
)
from saathi.platform.market_data.quality import classify_quote, classify_bar, classify_series, is_bar_fresh
from saathi.platform.market_data.calendar import MarketCalendar, get_calendar, SUPPORTED_CALENDARS, DEFAULT_24_5, RTH_UTC
from saathi.platform.market_data.provider import MarketDataProvider, ProviderResult, ProviderStatus, MarketClock
from saathi.platform.market_data.fixtures import FixtureProvider, DATASETS, fixture_manifest, dataset_hash, build_bars, build_quote
from saathi.platform.market_data.store import MarketDataStore
from saathi.platform.market_data.ingest import IngestionService, IngestionReport
from saathi.platform.market_data.replay import ReplayEngine, ReplayStatus, ReplayEvent
from saathi.platform.market_data.identity import IdentityValidationError, MarketIdentity, resolve_market_identity

__all__ = [
    "Timeframe", "TIMEFRAME_SECONDS", "MarketDataQuality", "QualityFinding",
    "MDInstrument", "MDQuote", "MDBar", "FreshnessPolicy", "DEFAULT_FRESHNESS",
    "to_data_quality", "require_aware", "is_aware",
    "classify_quote", "classify_bar", "classify_series", "is_bar_fresh",
    "MarketCalendar", "get_calendar", "SUPPORTED_CALENDARS", "DEFAULT_24_5", "RTH_UTC",
    "MarketDataProvider", "ProviderResult", "ProviderStatus", "MarketClock",
    "FixtureProvider", "DATASETS", "fixture_manifest", "dataset_hash", "build_bars", "build_quote",
    "MarketDataStore", "IngestionService", "IngestionReport",
    "ReplayEngine", "ReplayStatus", "ReplayEvent",
    "IdentityValidationError", "MarketIdentity", "resolve_market_identity",
]
