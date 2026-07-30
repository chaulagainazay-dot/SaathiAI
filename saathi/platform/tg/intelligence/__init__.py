"""M248–M255 Institutional Investment Intelligence & Portfolio Brain.

PAPER ONLY. NO BROKER CONNECTIVITY. NO API KEYS. NO LIVE MARKET ACCESS.
NO ORDER EXECUTION. NO LIVE TRADING.
"""
from saathi.platform.tg.intelligence.models import (
    SCHEMA_VERSION,
    ENGINE_VERSION,
    TERMINAL_VERDICT,
    LIVE_TRADING_AUTHORIZED,
    BROKER_CONNECTIVITY_AUTHORIZED,
    API_KEYS_ACCEPTED,
    ORDER_SUBMISSION_AUTHORIZED,
    AUTHORITY_VALUES,
)
from saathi.platform.tg.intelligence.service import (
    InstitutionalIntelligenceService,
    IntelligenceError,
    default_intelligence,
    reset_intelligence_for_tests,
)

__all__ = [
    "SCHEMA_VERSION",
    "ENGINE_VERSION",
    "TERMINAL_VERDICT",
    "LIVE_TRADING_AUTHORIZED",
    "BROKER_CONNECTIVITY_AUTHORIZED",
    "API_KEYS_ACCEPTED",
    "ORDER_SUBMISSION_AUTHORIZED",
    "AUTHORITY_VALUES",
    "InstitutionalIntelligenceService",
    "IntelligenceError",
    "default_intelligence",
    "reset_intelligence_for_tests",
]
