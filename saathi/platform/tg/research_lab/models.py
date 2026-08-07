"""M272–M279 Multi-Strategy Research Lab — models and authority locks.

RESEARCH ONLY. OFFLINE-FIRST. PAPER/SANDBOX ONLY.
NO BROKER CONNECTIVITY. NO API KEYS. NO ORDER EXECUTION. NO LIVE TRADING.
Maximum authority: RESEARCH_PORTFOLIO_AND_PAPER_CANDIDATE_EVALUATION_ONLY
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m272.research_lab.v1"
ENGINE_VERSION = "m272.research_lab.engine.v1"
EXPERIMENT_REGISTRY_VERSION = "m272.experiment_registry.v1"
REGIME_ENGINE_VERSION = "m275.regime.v1"
PORTFOLIO_ENGINE_VERSION = "m276.portfolio.v1"
ENSEMBLE_ENGINE_VERSION = "m277.ensemble.v1"
PROMOTION_POLICY_VERSION = "m278.promotion.v1"

TERMINAL_VERDICT = "MULTI_STRATEGY_RESEARCH_LAB_AND_ADAPTIVE_PORTFOLIO_INTELLIGENCE_CERTIFIED_WITH_LIMITATIONS"
MAX_STATE = "RESEARCH_PORTFOLIO_AND_PAPER_CANDIDATE_EVALUATION_ONLY"
BROWSER_CERT_VERDICT = "MULTI_STRATEGY_RESEARCH_LAB_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
MAX_AUTHORITY = "RESEARCH_PORTFOLIO_AND_PAPER_CANDIDATE_EVALUATION_ONLY"

# Hard authority locks — never true in this milestone.
LIVE_TRADING_AUTHORIZED = False
BROKER_CONNECTIVITY_AUTHORIZED = False
REAL_CONNECTIVITY_AUTHORIZED = False
CREDENTIAL_PROVISIONING_AUTHORIZED = False
CANARY_ACTIVATION_AUTHORIZED = False
ORDER_EXECUTION_AUTHORIZED = False
ORDER_SUBMISSION_AUTHORIZED = False
ORDER_MODIFICATION_AUTHORIZED = False
ORDER_CANCELLATION_AUTHORIZED = False
API_KEYS_ACCEPTED = False
OAUTH_AUTHORIZED = False
LIVE_MARKET_DATA_AUTHORIZED = False
LIVE_DATA_DEPENDENCY = False
PAPER_EXECUTION_AUTHORIZED = False
AUTOMATED_INVESTMENT_AUTHORITY = False
REGULATORY_GRADE_PORTFOLIO_OPTIMISATION = False
STRATEGY_PROFITABILITY_GUARANTEED = False
LIVE_MARKET_READINESS = False
INVESTMENT_ADVICE_CERTIFIED = False
PRODUCTION_AUTHORIZED = False
REAL_BROKER_CONNECTION_CAPABLE = False

# Invariants
CERTIFIED_EXPERIMENT_REQUIRES_PRE_REGISTRATION = True
DEFAULT_LEVERAGE_MAX = 1.0
HUMAN_REVIEW_REQUIRED_FOR_PAPER_CANDIDATE = True

AUTHORITY_VALUES = {
    "LIVE_TRADING_AUTHORIZED": False,
    "BROKER_CONNECTIVITY_AUTHORIZED": False,
    "REAL_CONNECTIVITY_AUTHORIZED": False,
    "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
    "CANARY_ACTIVATION_AUTHORIZED": False,
    "ORDER_EXECUTION_AUTHORIZED": False,
    "ORDER_SUBMISSION_AUTHORIZED": False,
    "ORDER_MODIFICATION_AUTHORIZED": False,
    "ORDER_CANCELLATION_AUTHORIZED": False,
    "API_KEYS_ACCEPTED": False,
    "OAUTH_AUTHORIZED": False,
    "LIVE_MARKET_DATA_AUTHORIZED": False,
    "LIVE_DATA_DEPENDENCY": False,
    "PAPER_EXECUTION_AUTHORIZED": False,
    "AUTOMATED_INVESTMENT_AUTHORITY": False,
    "REGULATORY_GRADE_PORTFOLIO_OPTIMISATION": False,
    "STRATEGY_PROFITABILITY_GUARANTEED": False,
    "LIVE_MARKET_READINESS": False,
    "INVESTMENT_ADVICE_CERTIFIED": False,
    "PRODUCTION_AUTHORIZED": False,
    "REAL_BROKER_CONNECTION_CAPABLE": False,
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
    "certified_experiment_requires_pre_registration": True,
    "human_review_required_for_paper_candidate": True,
    "paper_candidate_does_not_authorise_execution": True,
    "max_authority": MAX_AUTHORITY,
    "default_leverage_max": DEFAULT_LEVERAGE_MAX,
}

TERMINAL_STATEMENTS = (
    "RESEARCH ONLY",
    "OFFLINE-FIRST",
    "PAPER ONLY",
    "SANDBOX ONLY",
    "NO BROKER CONNECTIVITY",
    "NO ACCOUNT ACCESS",
    "NO CREDENTIALS",
    "NO ORDER EXECUTION",
    "NO LIVE TRADING",
    "PAPER CANDIDATE DOES NOT AUTHORISE ORDER EXECUTION",
    "NO GUARANTEED PROFITABILITY",
    "RESEARCH RESULTS DO NOT CONSTITUTE INVESTMENT ADVICE",
    "HUMAN REVIEW REQUIRED FOR PAPER CANDIDATE",
)

RL_POSTURE = {
    "mode": "RESEARCH_LAB_ONLY",
    "broker_connected": False,
    "credentials_loaded": False,
    "live_data": False,
    "orders_enabled": False,
    "canary_active": False,
    "paper_execution_enabled": False,
    "max_authority": MAX_AUTHORITY,
}

LLM_BOUNDARY = {
    "may_formulate_research_questions": True,
    "may_explain_experiment_configuration": True,
    "may_propose_bounded_experiments": True,
    "may_summarise_results": True,
    "may_compare_strategies": True,
    "may_explain_regime_classifications": True,
    "may_explain_portfolio_weights": True,
    "may_explain_stress_failures": True,
    "may_identify_robustness_concerns": True,
    "may_prepare_committee_review_material": True,
    "may_generate_evidence_summaries": True,
    "may_alter_frozen_test_results": False,
    "may_remove_failed_strategies": False,
    "may_waive_robustness_gates": False,
    "may_approve_hidden_trials": False,
    "may_fabricate_dataset_history": False,
    "may_fabricate_regimes": False,
    "may_change_licences": False,
    "may_bypass_candidate_gates": False,
    "may_approve_own_promotion": False,
    "may_authorize_paper_execution": False,
    "may_request_credentials": False,
    "may_connect_broker": False,
    "may_access_account": False,
    "may_place_orders": False,
    "may_enable_live_trading": False,
    "may_claim_guaranteed_performance": False,
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

# Preserved M270 failures — never mutate.
PRESERVED_OOS_FAILURES = (
    {"instrument": "AAPL", "strategy_id": "tf_dual_ma", "state": "OUT_OF_SAMPLE_FAILED"},
    {"instrument": "BTCUSDT", "strategy_id": "tf_dual_ma", "state": "OUT_OF_SAMPLE_FAILED"},
)

HISTORICAL_DATA_STATUS = "BOUNDED_REAL_HISTORICAL_DATA_VALIDATED_WITH_LIMITATIONS"
SYNTHETIC_TEST_DATA_LABEL = "SYNTHETIC_TEST_DATA"
RESEARCH_ROBUSTNESS_SCORE_NAME = "RESEARCH_ROBUSTNESS_SCORE"

PAPER_CANDIDATE_MEANING = "ELIGIBLE_FOR_FUTURE_PAPER_SIMULATION_REVIEW"

SCORECARD_DIMENSIONS = (
    "out_of_sample_performance",
    "downside_risk",
    "maximum_drawdown",
    "expected_shortfall",
    "parameter_stability",
    "temporal_stability",
    "cross_asset_stability",
    "regime_stability",
    "transaction_cost_resilience",
    "slippage_resilience",
    "turnover_efficiency",
    "diversification_contribution",
    "benchmark_improvement",
    "data_quality",
    "evidence_completeness",
    "overfitting_risk",
    "multiple_testing_burden",
)

PROMOTION_HARD_GATES = {
    "governed_historical_data": True,
    "pre_registered_experiment": True,
    "out_of_sample_evaluated": True,
    "walk_forward_completed": True,
    "transaction_costs_included": True,
    "slippage_included": True,
    "robustness_completed": True,
    "multiple_testing_disclosed": True,
    "regime_analysis_completed": True,
    "stress_testing_completed": True,
    "evidence_complete": True,
    "authority_violation": False,
    "human_review_required": True,
}


class ExperimentState(str, Enum):
    DRAFT = "DRAFT"
    PRE_REGISTERED = "PRE_REGISTERED"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    INVALIDATED = "INVALIDATED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class ComparisonState(str, Enum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    FAILED = "FAILED"
    UNSTABLE = "UNSTABLE"
    COST_SENSITIVE = "COST_SENSITIVE"
    REGIME_DEPENDENT = "REGIME_DEPENDENT"
    ROBUST_WITH_LIMITATIONS = "ROBUST_WITH_LIMITATIONS"
    RESEARCH_PROMISING = "RESEARCH_PROMISING"
    REJECTED = "REJECTED"


class RobustnessClass(str, Enum):
    ROBUSTNESS_NOT_TESTED = "ROBUSTNESS_NOT_TESTED"
    ROBUSTNESS_FAILED = "ROBUSTNESS_FAILED"
    PARAMETER_FRAGILE = "PARAMETER_FRAGILE"
    TEMPORALLY_UNSTABLE = "TEMPORALLY_UNSTABLE"
    CROSS_ASSET_UNSTABLE = "CROSS_ASSET_UNSTABLE"
    COST_FRAGILE = "COST_FRAGILE"
    DATA_FRAGILE = "DATA_FRAGILE"
    OVERFITTING_RISK_HIGH = "OVERFITTING_RISK_HIGH"
    ROBUST_WITH_LIMITATIONS = "ROBUST_WITH_LIMITATIONS"


class RegimeState(str, Enum):
    REGIME_UNKNOWN = "REGIME_UNKNOWN"
    REGIME_INSUFFICIENT_DATA = "REGIME_INSUFFICIENT_DATA"
    REGIME_LOW_CONFIDENCE = "REGIME_LOW_CONFIDENCE"
    REGIME_CLASSIFIED = "REGIME_CLASSIFIED"
    REGIME_TRANSITION = "REGIME_TRANSITION"
    REGIME_DRIFT_DETECTED = "REGIME_DRIFT_DETECTED"


class PortfolioState(str, Enum):
    PORTFOLIO_NOT_BUILT = "PORTFOLIO_NOT_BUILT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INFEASIBLE = "INFEASIBLE"
    UNSTABLE = "UNSTABLE"
    CONCENTRATED = "CONCENTRATED"
    COST_INEFFICIENT = "COST_INEFFICIENT"
    RESEARCH_PORTFOLIO_READY_WITH_LIMITATIONS = "RESEARCH_PORTFOLIO_READY_WITH_LIMITATIONS"
    REJECTED = "REJECTED"


class EnsembleState(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    LEAKAGE_BLOCKED = "LEAKAGE_BLOCKED"
    OVERFIT = "OVERFIT"
    UNSTABLE = "UNSTABLE"
    TURNOVER_EXCESSIVE = "TURNOVER_EXCESSIVE"
    NO_BENEFIT_OVER_BASELINE = "NO_BENEFIT_OVER_BASELINE"
    RESEARCH_PROMISING = "RESEARCH_PROMISING"
    RESEARCH_VALIDATED_WITH_LIMITATIONS = "RESEARCH_VALIDATED_WITH_LIMITATIONS"
    REJECTED = "REJECTED"


class CandidateState(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    DATA_BLOCKED = "DATA_BLOCKED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    ROBUSTNESS_FAILED = "ROBUSTNESS_FAILED"
    STRESS_FAILED = "STRESS_FAILED"
    COMMITTEE_REVIEW_REQUIRED = "COMMITTEE_REVIEW_REQUIRED"
    PAPER_CANDIDATE = "PAPER_CANDIDATE"
    PAPER_CANDIDATE_WITH_LIMITATIONS = "PAPER_CANDIDATE_WITH_LIMITATIONS"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class PortfolioMethod(str, Enum):
    EQUAL_WEIGHT = "equal_weight"
    INVERSE_VOLATILITY = "inverse_volatility"
    VOLATILITY_TARGETING = "volatility_targeting"
    RISK_PARITY = "risk_parity"
    MINIMUM_VARIANCE = "minimum_variance"
    MAXIMUM_DIVERSIFICATION = "maximum_diversification"
    CONSTRAINED_MEAN_VARIANCE = "constrained_mean_variance"
    DRAWDOWN_AWARE = "drawdown_aware"
    RISK_BUDGET = "risk_budget"


class EnsembleMethod(str, Enum):
    EQUAL_WEIGHT = "equal_weight"
    RISK_WEIGHTED = "risk_weighted"
    CONFIDENCE_WEIGHTED = "confidence_weighted"
    REGIME_CONDITIONED = "regime_conditioned"
    DRAWDOWN_CONTROLLED = "drawdown_controlled"
    VOLATILITY_TARGETED = "volatility_targeted"
    CAPPED_RANKING = "capped_ranking"
