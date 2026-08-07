"""M288–M295 Institutional Paper Trading Simulation — models and authority.

PAPER SIMULATION ONLY. NO BROKER. NO API KEYS. NO REAL EXCHANGE.
NO LIVE TRADING. NO REAL ORDER ROUTING.
Maximum authority: INSTITUTIONAL_PAPER_SIMULATION_ONLY
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m288.paper_simulation.v1"
ENGINE_VERSION = "m288.paper_simulation.engine.v1"

TERMINAL_VERDICT = "INSTITUTIONAL_PAPER_TRADING_SIMULATION_CERTIFIED_WITH_LIMITATIONS"
MAX_STATE = "INSTITUTIONAL_PAPER_SIMULATION_ONLY"
BROWSER_CERT_VERDICT = "INSTITUTIONAL_PAPER_SIMULATION_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
MAX_AUTHORITY = "INSTITUTIONAL_PAPER_SIMULATION_ONLY"

LIVE_TRADING_AUTHORIZED = False
BROKER_CONNECTIVITY_AUTHORIZED = False
REAL_CONNECTIVITY_AUTHORIZED = False
REAL_EXCHANGE_AUTHORIZED = False
CREDENTIAL_PROVISIONING_AUTHORIZED = False
CANARY_ACTIVATION_AUTHORIZED = False
ORDER_EXECUTION_AUTHORIZED = False  # real order execution
ORDER_SUBMISSION_AUTHORIZED = False  # real broker order submission
API_KEYS_ACCEPTED = False
OAUTH_AUTHORIZED = False
PRODUCTION_AUTHORIZED = False
STRATEGY_PROFITABILITY_GUARANTEED = False
INVESTMENT_ADVICE_CERTIFIED = False
LIVE_MARKET_READINESS = False
# Paper simulation may accept paper orders into the virtual exchange only
PAPER_SIMULATION_ORDERS_ALLOWED = True
MARGIN_RESEARCH_ONLY = True

DEFAULT_INITIAL_CASH = 100_000.0
DEFAULT_SLIPPAGE_BPS = 5.0
DEFAULT_FEE_BPS = 2.0
DEFAULT_LATENCY_MS = 10
DEFAULT_MAX_LEVERAGE = 1.0
MAX_OPEN_ORDERS = 500
MAX_POSITIONS = 100

AUTHORITY_VALUES = {
    "LIVE_TRADING_AUTHORIZED": False,
    "BROKER_CONNECTIVITY_AUTHORIZED": False,
    "REAL_CONNECTIVITY_AUTHORIZED": False,
    "REAL_EXCHANGE_AUTHORIZED": False,
    "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
    "CANARY_ACTIVATION_AUTHORIZED": False,
    "ORDER_EXECUTION_AUTHORIZED": False,
    "ORDER_SUBMISSION_AUTHORIZED": False,
    "API_KEYS_ACCEPTED": False,
    "OAUTH_AUTHORIZED": False,
    "PRODUCTION_AUTHORIZED": False,
    "STRATEGY_PROFITABILITY_GUARANTEED": False,
    "INVESTMENT_ADVICE_CERTIFIED": False,
    "LIVE_MARKET_READINESS": False,
    "paper_only": True,
    "sandbox_only": True,
    "research_only": True,
    "offline_first": True,
    "simulation_only": True,
    "virtual_exchange_only": True,
    "no_broker_connection": True,
    "no_api_keys": True,
    "no_oauth": True,
    "no_real_order_routing": True,
    "no_live_trading": True,
    "paper_simulation_orders_allowed": True,
    "margin_research_only": True,
    "max_authority": MAX_AUTHORITY,
    "default_max_leverage": DEFAULT_MAX_LEVERAGE,
}

TERMINAL_STATEMENTS = (
    "PAPER SIMULATION ONLY",
    "VIRTUAL EXCHANGE ONLY",
    "NO BROKER CONNECTIVITY",
    "NO API KEYS",
    "NO REAL EXCHANGE ACCOUNT",
    "NO LIVE TRADING",
    "NO REAL ORDER ROUTING",
    "OFFLINE-FIRST",
    "MARGIN RESEARCH ONLY",
    "NO GUARANTEED PROFITABILITY",
)

PS_POSTURE = {
    "mode": "INSTITUTIONAL_PAPER_SIMULATION_ONLY",
    "broker_connected": False,
    "credentials_loaded": False,
    "live_data": False,
    "real_orders_enabled": False,
    "virtual_exchange_active": True,
    "canary_active": False,
    "max_authority": MAX_AUTHORITY,
}

LLM_BOUNDARY = {
    "may_explain_fills": True,
    "may_summarise_portfolio": True,
    "may_propose_paper_orders": True,
    "may_explain_risk_breaches": True,
    "may_submit_real_orders": False,
    "may_connect_broker": False,
    "may_load_api_keys": False,
    "may_disable_kill_switch": False,
    "may_bypass_risk_limits": False,
    "may_claim_live_execution": False,
    "may_claim_guaranteed_performance": False,
}


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    NEW = "NEW"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    STOPPED = "STOPPED"  # kill switch


class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class SessionState(str, Enum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HALTED = "HALTED"


class KillSwitchState(str, Enum):
    INACTIVE = "INACTIVE"
    ACTIVE = "ACTIVE"


class PortfolioState(str, Enum):
    ACTIVE = "ACTIVE"
    HALTED = "HALTED"
    LIQUIDATING = "LIQUIDATING"
    CLOSED = "CLOSED"
