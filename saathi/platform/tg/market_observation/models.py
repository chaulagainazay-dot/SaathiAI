"""M304–M311 Read-Only Market Observation — models and authority locks.

READ-ONLY OBSERVATION ONLY. VALIDATION — NOT TRADING.
NO BROKER LOGIN. NO OAUTH. NO CREDENTIALS. NO ORDERS. NO ACCOUNT ACCESS.
Maximum authority: READ_ONLY_MARKET_OBSERVATION_ONLY
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m304.market_observation.v1"
ENGINE_VERSION = "m304.market_observation.engine.v1"

TERMINAL_VERDICT = "READ_ONLY_MARKET_OBSERVATION_CERTIFIED_WITH_LIMITATIONS"
MAX_STATE = "READ_ONLY_MARKET_OBSERVATION_ONLY"
BROWSER_CERT_VERDICT = "READ_ONLY_MARKET_OBSERVATION_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
MAX_AUTHORITY = "READ_ONLY_MARKET_OBSERVATION_ONLY"

LIVE_TRADING_AUTHORIZED = False
BROKER_CONNECTIVITY_AUTHORIZED = False
REAL_CONNECTIVITY_AUTHORIZED = False
CREDENTIAL_PROVISIONING_AUTHORIZED = False
CREDENTIAL_STORAGE_AUTHORIZED = False
CANARY_ACTIVATION_AUTHORIZED = False
ORDER_EXECUTION_AUTHORIZED = False
ORDER_SUBMISSION_AUTHORIZED = False
ACCOUNT_ACCESS_AUTHORIZED = False
PORTFOLIO_ACCESS_AUTHORIZED = False
BALANCE_ACCESS_AUTHORIZED = False
API_KEYS_ACCEPTED = False
OAUTH_AUTHORIZED = False
PRODUCTION_AUTHORIZED = False
LIVE_MARKET_READINESS = False
STRATEGY_PROFITABILITY_GUARANTEED = False
INVESTMENT_ADVICE_CERTIFIED = False

# Observation may use offline fixtures / frozen local data only by default
OFFLINE_OBSERVATION_DEFAULT = True
AUTHENTICATED_PROVIDER_TRAFFIC = False

AUTHORITY_VALUES = {
    "LIVE_TRADING_AUTHORIZED": False,
    "BROKER_CONNECTIVITY_AUTHORIZED": False,
    "REAL_CONNECTIVITY_AUTHORIZED": False,
    "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
    "CREDENTIAL_STORAGE_AUTHORIZED": False,
    "CANARY_ACTIVATION_AUTHORIZED": False,
    "ORDER_EXECUTION_AUTHORIZED": False,
    "ORDER_SUBMISSION_AUTHORIZED": False,
    "ACCOUNT_ACCESS_AUTHORIZED": False,
    "PORTFOLIO_ACCESS_AUTHORIZED": False,
    "BALANCE_ACCESS_AUTHORIZED": False,
    "API_KEYS_ACCEPTED": False,
    "OAUTH_AUTHORIZED": False,
    "PRODUCTION_AUTHORIZED": False,
    "LIVE_MARKET_READINESS": False,
    "STRATEGY_PROFITABILITY_GUARANTEED": False,
    "INVESTMENT_ADVICE_CERTIFIED": False,
    "AUTHENTICATED_PROVIDER_TRAFFIC": False,
    "paper_only": True,
    "sandbox_only": True,
    "research_only": True,
    "offline_first": True,
    "read_only_observation": True,
    "validation_not_trading": True,
    "no_broker_login": True,
    "no_oauth": True,
    "no_credential_storage": True,
    "no_orders": True,
    "no_account_access": True,
    "no_portfolio_access": True,
    "no_balance_access": True,
    "no_live_trading": True,
    "max_authority": MAX_AUTHORITY,
}

TERMINAL_STATEMENTS = (
    "READ-ONLY MARKET OBSERVATION",
    "VALIDATION — NOT TRADING",
    "OFFLINE-FIRST",
    "NO BROKER LOGIN",
    "NO OAUTH",
    "NO API KEYS",
    "NO CREDENTIAL STORAGE",
    "NO ORDERS",
    "NO ACCOUNT ACCESS",
    "NO PORTFOLIO ACCESS",
    "NO BALANCE ACCESS",
    "NO LIVE TRADING",
)

MO_POSTURE = {
    "mode": "READ_ONLY_MARKET_OBSERVATION_ONLY",
    "broker_connected": False,
    "broker_login_available": False,
    "credentials_loaded": False,
    "oauth_available": False,
    "orders_enabled": False,
    "account_access": False,
    "portfolio_access": False,
    "balance_access": False,
    "observation_only": True,
    "max_authority": MAX_AUTHORITY,
}

LLM_BOUNDARY = {
    "may_summarise_snapshots": True,
    "may_explain_quotes": True,
    "may_map_symbol_metadata": True,
    "may_flag_stale_data": True,
    "may_request_credentials": False,
    "may_initiate_oauth": False,
    "may_connect_broker": False,
    "may_place_orders": False,
    "may_access_accounts": False,
    "may_access_balances": False,
    "may_access_live_portfolios": False,
    "may_store_api_keys": False,
    "may_enable_trading": False,
}

# Deterministic offline observation universe
DEFAULT_SYMBOLS = (
    "SPY", "QQQ", "AAPL", "MSFT", "TLT", "GLD", "BTCUSDT", "ETHUSDT",
)

DEFAULT_BENCHMARKS = ("SPY", "QQQ", "AGG")


class ObservationSource(str, Enum):
    OFFLINE_FIXTURE = "OFFLINE_FIXTURE"
    FROZEN_LOCAL_CACHE = "FROZEN_LOCAL_CACHE"
    GOVERNED_DATASET = "GOVERNED_DATASET"
    # Explicitly not implemented for authenticated live feeds
    AUTHENTICATED_LIVE_FORBIDDEN = "AUTHENTICATED_LIVE_FORBIDDEN"


class ExchangeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PRE_OPEN = "PRE_OPEN"
    HALTED = "HALTED"
    UNKNOWN = "UNKNOWN"


class DataFreshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    FROZEN = "FROZEN"
    UNKNOWN = "UNKNOWN"
