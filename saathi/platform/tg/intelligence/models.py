"""M248–M255 Institutional Investment Intelligence — models and authority locks.

PAPER ONLY. NO BROKER CONNECTIVITY. NO API KEYS. NO LIVE MARKET ACCESS.
NO ORDER EXECUTION. NO LIVE TRADING.
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m248.institutional_intelligence.v1"
ENGINE_VERSION = "m248.institutional_intelligence.engine.v1"

TERMINAL_VERDICT = "INSTITUTIONAL_INVESTMENT_INTELLIGENCE_CERTIFIED_WITH_LIMITATIONS"
MAX_STATE = "PAPER_INTELLIGENCE_ENGINE_READY"

# Hard authority locks — never true in this milestone.
LIVE_TRADING_AUTHORIZED = False
BROKER_CONNECTIVITY_AUTHORIZED = False
API_KEYS_ACCEPTED = False
OAUTH_AUTHORIZED = False
ORDER_SUBMISSION_AUTHORIZED = False
LIVE_MARKET_DATA_AUTHORIZED = False
LIVE_DATA_DEPENDENCY = False
REAL_BROKER_CONNECTION_CAPABLE = False
ORDER_EXECUTION_CAPABLE = False

AUTHORITY_VALUES = {
    "LIVE_TRADING_AUTHORIZED": False,
    "BROKER_CONNECTIVITY_AUTHORIZED": False,
    "API_KEYS_ACCEPTED": False,
    "OAUTH_AUTHORIZED": False,
    "ORDER_SUBMISSION_AUTHORIZED": False,
    "LIVE_MARKET_DATA_AUTHORIZED": False,
    "LIVE_DATA_DEPENDENCY": False,
    "paper_only": True,
    "sandbox_only": True,
    "offline_capable": True,
    "no_broker_connection": True,
    "no_api_keys": True,
    "no_oauth": True,
    "no_order_submission": True,
    "no_live_data_dependency": True,
    "no_live_trading": True,
}

TERMINAL_STATEMENTS = (
    "PAPER ONLY",
    "NO BROKER CONNECTIVITY",
    "NO API KEYS",
    "NO LIVE MARKET ACCESS",
    "NO ORDER EXECUTION",
    "NO LIVE TRADING",
)

II_POSTURE = {
    "mode": "PAPER_INTELLIGENCE_ONLY",
    "broker_connected": False,
    "credentials_loaded": False,
    "live_data": False,
    "orders_enabled": False,
}

LLM_BOUNDARY = {
    "may_advise": True,
    "may_explain": True,
    "may_simulate": True,
    "may_submit_orders": False,
    "may_connect_broker": False,
    "may_load_api_keys": False,
    "may_authorize_live": False,
}

STRATEGY_CATEGORIES = (
    "momentum",
    "mean_reversion",
    "trend_following",
    "breakout",
    "volatility",
    "dca",
    "value_investing",
    "growth_investing",
    "swing_trading",
    "scalping",
    "long_term_investing",
)


class RiskProfile(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    SPECULATIVE = "speculative"


class SizingModel(str, Enum):
    FIXED_FRACTIONAL = "fixed_fractional"
    FIXED_NOTIONAL = "fixed_notional"
    VOLATILITY_TARGET = "volatility_target"
    EQUAL_WEIGHT = "equal_weight"
    KELLY_FRACTION = "kelly_fraction_capped"
    DCA_SCHEDULE = "dca_schedule"


class CommitteeRole(str, Enum):
    MACRO = "macro_analyst"
    TECHNICAL = "technical_analyst"
    FUNDAMENTAL = "fundamental_analyst"
    QUANT = "quant_analyst"
    RISK = "risk_manager"
    PORTFOLIO = "portfolio_manager"


class RecommendationAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    INCREASE = "INCREASE"
    AVOID = "AVOID"
    WATCH = "WATCH"


class ConfidenceBand(str, Enum):
    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"
