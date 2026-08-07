"""M256–M263 Market Data Foundation — models and authority locks.

RESEARCH ONLY. OFFLINE-FIRST. PAPER/SANDBOX ONLY.
NO REAL BROKER CONNECTIVITY. NO API KEYS. NO ORDER EXECUTION. NO LIVE TRADING.
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m256.market_data.v1"
ENGINE_VERSION = "m256.market_data.engine.v1"
INGESTION_VERSION = "m258.ingestion.v1"
FEATURE_CREATOR_VERSION = "m261.feature_store.v1"
OHLCV_SCHEMA_VERSION = "canonical.ohlcv.v1"

TERMINAL_VERDICT = "RESEARCH_GRADE_MARKET_DATA_AND_SIGNAL_VALIDATION_CERTIFIED_WITH_LIMITATIONS"
MAX_STATE = "RESEARCH_DATA_AND_SIGNAL_VALIDATION_READY"
BROWSER_CERT_VERDICT = "RESEARCH_GRADE_MARKET_DATA_SIGNAL_VALIDATION_BROWSER_CERT_PASSED_WITH_LIMITATIONS"

# Hard authority locks — never true in this milestone.
LIVE_TRADING_AUTHORIZED = False
BROKER_CONNECTIVITY_AUTHORIZED = False
REAL_CONNECTIVITY_AUTHORIZED = False
CREDENTIAL_PROVISIONING_AUTHORIZED = False
CANARY_ACTIVATION_AUTHORIZED = False
ORDER_EXECUTION_AUTHORIZED = False
ORDER_SUBMISSION_AUTHORIZED = False
API_KEYS_ACCEPTED = False
OAUTH_AUTHORIZED = False
LIVE_MARKET_DATA_AUTHORIZED = False
LIVE_DATA_DEPENDENCY = False
REGULATORY_GRADE_MARKET_DATA = False
STRATEGY_PROFITABILITY_GUARANTEED = False
LIVE_MARKET_READINESS = False
INVESTMENT_ADVICE_CERTIFIED = False
REAL_BROKER_CONNECTION_CAPABLE = False

AUTHORITY_VALUES = {
    "LIVE_TRADING_AUTHORIZED": False,
    "BROKER_CONNECTIVITY_AUTHORIZED": False,
    "REAL_CONNECTIVITY_AUTHORIZED": False,
    "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
    "CANARY_ACTIVATION_AUTHORIZED": False,
    "ORDER_EXECUTION_AUTHORIZED": False,
    "ORDER_SUBMISSION_AUTHORIZED": False,
    "API_KEYS_ACCEPTED": False,
    "OAUTH_AUTHORIZED": False,
    "LIVE_MARKET_DATA_AUTHORIZED": False,
    "LIVE_DATA_DEPENDENCY": False,
    "REGULATORY_GRADE_MARKET_DATA": False,
    "STRATEGY_PROFITABILITY_GUARANTEED": False,
    "LIVE_MARKET_READINESS": False,
    "INVESTMENT_ADVICE_CERTIFIED": False,
    "paper_only": True,
    "sandbox_only": True,
    "research_only": True,
    "offline_first": True,
    "offline_capable": True,
    "no_broker_connection": True,
    "no_api_keys": True,
    "no_oauth": True,
    "no_order_submission": True,
    "no_live_data_dependency": True,
    "no_live_trading": True,
    "certified_research_requires_registered_dataset": True,
}

TERMINAL_STATEMENTS = (
    "RESEARCH ONLY",
    "OFFLINE-FIRST",
    "PAPER ONLY",
    "SANDBOX ONLY",
    "NO BROKER CONNECTIVITY",
    "NO ACCOUNT ACCESS",
    "NO ORDER EXECUTION",
    "NO LIVE TRADING",
    "NO GUARANTEED PROFITABILITY",
    "BIAS CONTROLS EXPLICIT OR DISCLOSED",
)

MD_POSTURE = {
    "mode": "RESEARCH_DATA_ONLY",
    "broker_connected": False,
    "credentials_loaded": False,
    "live_data": False,
    "orders_enabled": False,
    "canary_active": False,
}

LLM_BOUNDARY = {
    "may_explain_metadata": True,
    "may_map_schemas": True,
    "may_recommend_quality_checks": True,
    "may_identify_anomalies": True,
    "may_summarise_provenance": True,
    "may_classify_limitations": True,
    "may_propose_feature_definitions": True,
    "may_explain_validation_results": True,
    "may_compare_strategies": True,
    "may_identify_bias_risks": True,
    "may_generate_research_reports": True,
    "may_approve_unknown_licences": False,
    "may_provide_legal_approval": False,
    "may_fabricate_provenance": False,
    "may_remove_blocking_quality_findings": False,
    "may_reclassify_synthetic_as_historical": False,
    "may_waive_lookahead_controls": False,
    "may_waive_survivorship_controls": False,
    "may_access_broker_accounts": False,
    "may_receive_credentials": False,
    "may_activate_provider_connectivity": False,
    "may_execute_orders": False,
    "may_claim_guaranteed_profitability": False,
    "may_certify_live_readiness": False,
    "may_enable_live_trading": False,
}

FORBIDDEN_PROVIDER_DOMAINS = frozenset({
    "api.binance.com", "binance.com", "fapi.binance.com", "dapi.binance.com",
    "api.alpaca.markets", "paper-api.alpaca.markets", "alpaca.markets", "data.alpaca.markets",
    "api.ibkr.com", "interactivebrokers.com",
    "api.kite.trade", "kite.zerodha.com", "zerodha.com",
    "api.bybit.com", "bybit.com",
    "api.coinbase.com", "coinbase.com",
    "api.kraken.com", "kraken.com",
    "oauth.binance.com", "login.alpaca.markets",
})

FORBIDDEN_ENV_VARS = frozenset({
    "BINANCE_API_KEY", "BINANCE_API_SECRET",
    "ALPACA_API_KEY", "ALPACA_API_SECRET", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY",
    "IBKR_USERNAME", "IBKR_PASSWORD",
    "ZERODHA_API_KEY", "KITE_API_KEY",
    "BYBIT_API_KEY", "COINBASE_API_KEY", "KRAKEN_API_KEY",
    "BROKER_API_KEY", "BROKER_API_SECRET", "PROVIDER_API_KEY",
    "OAUTH_CLIENT_SECRET", "TRADING_PASSWORD",
})

MAX_INGEST_BYTES = 25 * 1024 * 1024  # 25 MiB bounded fixture/ingestion cap
MAX_INGEST_ROWS = 500_000


class DatasetState(str, Enum):
    DISCOVERED = "DISCOVERED"
    REGISTERED = "REGISTERED"
    LICENCE_REVIEW_REQUIRED = "LICENCE_REVIEW_REQUIRED"
    INGESTION_PENDING = "INGESTION_PENDING"
    INGESTED_UNVERIFIED = "INGESTED_UNVERIFIED"
    QUALITY_REVIEW_REQUIRED = "QUALITY_REVIEW_REQUIRED"
    RESEARCH_APPROVED = "RESEARCH_APPROVED"
    RESEARCH_RESTRICTED = "RESEARCH_RESTRICTED"
    QUARANTINED = "QUARANTINED"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


class GovernanceClass(str, Enum):
    OPEN_RESEARCH_USE = "OPEN_RESEARCH_USE"
    ATTRIBUTION_REQUIRED = "ATTRIBUTION_REQUIRED"
    NON_COMMERCIAL_ONLY = "NON_COMMERCIAL_ONLY"
    NO_REDISTRIBUTION = "NO_REDISTRIBUTION"
    INTERNAL_RESEARCH_ONLY = "INTERNAL_RESEARCH_ONLY"
    LICENCE_UNCLEAR = "LICENCE_UNCLEAR"
    LEGAL_REVIEW_REQUIRED = "LEGAL_REVIEW_REQUIRED"
    USE_FORBIDDEN = "USE_FORBIDDEN"


class RowStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    NORMALIZED = "NORMALIZED"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    DUPLICATE = "DUPLICATE"
    CONFLICTING = "CONFLICTING"


class QualityClass(str, Enum):
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    RESEARCH_USABLE_WITH_WARNINGS = "RESEARCH_USABLE_WITH_WARNINGS"
    LIMITED_USE = "LIMITED_USE"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


class ValidationState(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    DATA_GOVERNANCE_BLOCKED = "DATA_GOVERNANCE_BLOCKED"
    IN_SAMPLE_ONLY = "IN_SAMPLE_ONLY"
    OUT_OF_SAMPLE_FAILED = "OUT_OF_SAMPLE_FAILED"
    UNSTABLE = "UNSTABLE"
    REGIME_DEPENDENT = "REGIME_DEPENDENT"
    RESEARCH_PROMISING = "RESEARCH_PROMISING"
    RESEARCH_VALIDATED_WITH_LIMITATIONS = "RESEARCH_VALIDATED_WITH_LIMITATIONS"
    REJECTED = "REJECTED"


class SourceType(str, Enum):
    LOCAL_FILE = "LOCAL_FILE"
    REPOSITORY_FIXTURE = "REPOSITORY_FIXTURE"
    PUBLIC_HISTORICAL_SNAPSHOT = "PUBLIC_HISTORICAL_SNAPSHOT"
    SYNTHETIC_TEST_DATA = "SYNTHETIC_TEST_DATA"
    USER_PROVIDED = "USER_PROVIDED"
    DERIVED = "DERIVED"


class AssetClass(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    CRYPTO = "crypto"
    FX = "fx"
    FUTURES = "futures"
    MACRO = "macro"
    FUNDAMENTAL = "fundamental"
    MIXED = "mixed"


class DataFamily(str, Enum):
    OHLCV = "ohlcv"
    QUOTE = "quote"
    TRADE = "trade"
    BENCHMARK = "benchmark"
    INDEX_HISTORY = "index_history"
    CORPORATE_ACTION = "corporate_action"
    FUNDAMENTAL = "fundamental"
    MACRO = "macro"
    ECONOMIC_CALENDAR = "economic_calendar"
    ASSET_METADATA = "asset_metadata"
    EXCHANGE_CALENDAR = "exchange_calendar"


class SplitKind(str, Enum):
    CHRONOLOGICAL_HOLDOUT = "chronological_holdout"
    ROLLING_WALK_FORWARD = "rolling_walk_forward"
    EXPANDING_WINDOW = "expanding_window"
    EMBARGO_GAP = "embargo_gap"
    PURGE_WINDOW = "purge_window"
    OUT_OF_SAMPLE = "out_of_sample"


class CorporateActionType(str, Enum):
    STOCK_SPLIT = "stock_split"
    REVERSE_SPLIT = "reverse_split"
    CASH_DIVIDEND = "cash_dividend"
    STOCK_DIVIDEND = "stock_dividend"
    SYMBOL_CHANGE = "symbol_change"
    MERGER = "merger"
    SPIN_OFF = "spin_off"
    DELISTING = "delisting"


KNOWN_RESEARCH_LIMITATION = "KNOWN_RESEARCH_LIMITATION"
SYNTHETIC_TEST_DATA_LABEL = "SYNTHETIC_TEST_DATA"
REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE = "REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE"
REVISION_BIAS_POSSIBLE = "REVISION_BIAS_POSSIBLE"
LEGAL_REVIEW_REQUIRED = "LEGAL_REVIEW_REQUIRED"

# Forbidden certification states
FORBIDDEN_VALIDATION_STATES = frozenset({
    "PROFITABLE", "GUARANTEED", "SAFE", "LIVE_READY", "PRODUCTION_READY",
})

CANONICAL_OHLCV_FIELDS = (
    "instrument_id", "symbol", "exchange", "asset_class", "timestamp", "timezone",
    "interval", "open", "high", "low", "close", "adjusted_close", "volume",
    "trade_count", "vwap", "currency", "source_dataset_id", "source_row_ref",
    "ingestion_version",
)

COLUMN_ALIASES = {
    "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
    "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume",
    "Adj Close": "adjusted_close", "adj_close": "adjusted_close", "adjclose": "adjusted_close",
    "Date": "timestamp", "date": "timestamp", "Datetime": "timestamp", "datetime": "timestamp",
    "time": "timestamp", "ts": "timestamp", "Ticker": "symbol", "ticker": "symbol",
    "Symbol": "symbol", "exchange_code": "exchange", "Exch": "exchange",
}
