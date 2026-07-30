"""M296–M303 Institutional Portfolio & Risk Intelligence — models and authority.

PAPER / RESEARCH ONLY. NO BROKER. NO LIVE TRADING. NO ORDER EXECUTION.
Maximum authority: INSTITUTIONAL_PORTFOLIO_RISK_INTELLIGENCE_ONLY
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m296.portfolio_risk.v1"
ENGINE_VERSION = "m296.portfolio_risk.engine.v1"

TERMINAL_VERDICT = "INSTITUTIONAL_PORTFOLIO_RISK_INTELLIGENCE_CERTIFIED_WITH_LIMITATIONS"
MAX_STATE = "INSTITUTIONAL_PORTFOLIO_RISK_INTELLIGENCE_ONLY"
BROWSER_CERT_VERDICT = "INSTITUTIONAL_PORTFOLIO_RISK_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
MAX_AUTHORITY = "INSTITUTIONAL_PORTFOLIO_RISK_INTELLIGENCE_ONLY"

LIVE_TRADING_AUTHORIZED = False
BROKER_CONNECTIVITY_AUTHORIZED = False
REAL_CONNECTIVITY_AUTHORIZED = False
CREDENTIAL_PROVISIONING_AUTHORIZED = False
CANARY_ACTIVATION_AUTHORIZED = False
ORDER_EXECUTION_AUTHORIZED = False
ORDER_SUBMISSION_AUTHORIZED = False
API_KEYS_ACCEPTED = False
OAUTH_AUTHORIZED = False
PRODUCTION_AUTHORIZED = False
STRATEGY_PROFITABILITY_GUARANTEED = False
INVESTMENT_ADVICE_CERTIFIED = False
LIVE_MARKET_READINESS = False
REGULATORY_GRADE_RISK = False
DEFAULT_MAX_LEVERAGE = 1.0

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
    "PRODUCTION_AUTHORIZED": False,
    "STRATEGY_PROFITABILITY_GUARANTEED": False,
    "INVESTMENT_ADVICE_CERTIFIED": False,
    "LIVE_MARKET_READINESS": False,
    "REGULATORY_GRADE_RISK": False,
    "paper_only": True,
    "sandbox_only": True,
    "research_only": True,
    "offline_first": True,
    "no_broker_connection": True,
    "no_api_keys": True,
    "no_oauth": True,
    "no_order_submission": True,
    "no_live_trading": True,
    "not_investment_advice": True,
    "max_authority": MAX_AUTHORITY,
    "default_max_leverage": DEFAULT_MAX_LEVERAGE,
}

TERMINAL_STATEMENTS = (
    "PAPER / RESEARCH ONLY",
    "OFFLINE-FIRST",
    "NO BROKER CONNECTIVITY",
    "NO ORDER EXECUTION",
    "NO LIVE TRADING",
    "NOT INVESTMENT ADVICE",
    "NOT REGULATORY-GRADE RISK CAPITAL",
    "NO GUARANTEED PROFITABILITY",
)

PR_POSTURE = {
    "mode": "INSTITUTIONAL_PORTFOLIO_RISK_INTELLIGENCE_ONLY",
    "broker_connected": False,
    "credentials_loaded": False,
    "live_data": False,
    "orders_enabled": False,
    "canary_active": False,
    "max_authority": MAX_AUTHORITY,
}

LLM_BOUNDARY = {
    "may_explain_risk": True,
    "may_summarise_attribution": True,
    "may_propose_rebalance_research": True,
    "may_draft_committee_notes": True,
    "may_execute_orders": False,
    "may_connect_broker": False,
    "may_bypass_exposure_limits": False,
    "may_claim_regulatory_grade": False,
    "may_claim_guaranteed_performance": False,
    "may_authorize_live": False,
}

# Default demo portfolio for offline analytics (deterministic)
DEFAULT_DEMO_PORTFOLIO = {
    "id": "pr_demo_core",
    "name": "Institutional Paper Demo",
    "currency": "USD",
    "cash": 20000.0,
    "starting_equity": 100000.0,
    "positions": [
        {"symbol": "SPY", "quantity": 80, "avg_cost": 420.0, "mark": 450.0,
         "sector": "Broad Market", "geography": "US", "asset_class": "equity_etf", "beta": 1.0,
         "factor_loadings": {"market": 1.0, "size": 0.0, "value": 0.1, "momentum": 0.0}},
        {"symbol": "QQQ", "quantity": 40, "avg_cost": 360.0, "mark": 390.0,
         "sector": "Technology", "geography": "US", "asset_class": "equity_etf", "beta": 1.15,
         "factor_loadings": {"market": 1.1, "size": -0.2, "value": -0.3, "momentum": 0.4}},
        {"symbol": "EFA", "quantity": 60, "avg_cost": 70.0, "mark": 74.0,
         "sector": "International", "geography": "Developed ex-US", "asset_class": "equity_etf", "beta": 0.9,
         "factor_loadings": {"market": 0.85, "size": 0.1, "value": 0.2, "momentum": -0.1}},
        {"symbol": "TLT", "quantity": 50, "avg_cost": 95.0, "mark": 92.0,
         "sector": "Fixed Income", "geography": "US", "asset_class": "bond_etf", "beta": -0.2,
         "factor_loadings": {"market": -0.15, "size": 0.0, "value": 0.3, "momentum": -0.2}},
        {"symbol": "GLD", "quantity": 30, "avg_cost": 180.0, "mark": 195.0,
         "sector": "Commodities", "geography": "Global", "asset_class": "commodity_etf", "beta": 0.1,
         "factor_loadings": {"market": 0.05, "size": 0.0, "value": 0.0, "momentum": 0.1}},
    ],
    "realized_pnl": 1500.0,
}


class LimitState(str, Enum):
    WITHIN_LIMITS = "WITHIN_LIMITS"
    WARNING = "WARNING"
    BREACHED = "BREACHED"
    HALTED = "HALTED"


class OptimiserState(str, Enum):
    READY = "READY"
    INFEASIBLE = "INFEASIBLE"
    UNSTABLE = "UNSTABLE"
    REJECTED = "REJECTED"


class CommitteeConsensus(str, Enum):
    STRONG_CONSENSUS = "STRONG_CONSENSUS"
    MAJORITY = "MAJORITY"
    SPLIT = "SPLIT"
    NO_CONSENSUS = "NO_CONSENSUS"
