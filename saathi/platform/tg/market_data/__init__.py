"""M256–M263 Market Data Foundation, Dataset Governance and Research-Grade Signal Validation.

RESEARCH ONLY. OFFLINE-FIRST. NO BROKER CONNECTIVITY. NO API KEYS. NO LIVE TRADING.
"""
from saathi.platform.tg.market_data.models import (
    AUTHORITY_VALUES,
    MAX_STATE,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.market_data.service import (
    MarketDataService,
    default_market_data,
    reset_market_data_for_tests,
)

__all__ = [
    "AUTHORITY_VALUES",
    "MAX_STATE",
    "TERMINAL_VERDICT",
    "MarketDataService",
    "default_market_data",
    "reset_market_data_for_tests",
]
