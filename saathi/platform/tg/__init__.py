"""M166–M175 — Trading Guardian Research & Paper-Trading Foundation.

Composition layer over the certified M62 paper-trading stack:

    Market Data → Strategy Registry → Strategy Evaluation → Trade Proposal
    → Policy Engine → Risk Engine → Approval Center → ExecutionGateway
    → Paper Broker → Portfolio Ledger → Evidence and Audit

Authority: ADVISORY by default. PAPER only. No live orders, no broker credentials,
no leverage/margin, no self-approval, no LLM risk override.

Verdict target: TRADING_GUARDIAN_RESEARCH_AND_PAPER_FOUNDATION_READY_WITH_LIMITATIONS

This package does NOT claim profitability, live readiness, or production trading
authorization. Historical/simulated performance is not future performance.
"""
from __future__ import annotations

from saathi.platform.tg.domain import (
    SCHEMA_VERSION,
    ENGINE_VERSION,
    AuthorityMode,
    DEFAULT_AUTHORITY_MODE,
    MarketRegime,
    StrategyActivation,
    StrategyEvaluationVerdict,
    GateStatus,
    ProposalStatus,
    TradingStrategy,
    StrategyVersion,
    StrategyParameterSet,
    MarketInstrument,
    MarketBar,
    MarketSnapshot,
    TradeSignal,
    TradeProposal,
    PolicyGateResult,
    PolicyDecision,
    RiskDecision,
    PaperOrderRef,
    PaperFillRef,
    PaperPositionView,
    PaperPortfolioView,
    TradeJournalEntry,
    BacktestRunRef,
    BacktestResultView,
    PerformanceMetrics,
    TradingGuardianPolicy,
    TradingGuardianKillSwitch,
    KillSwitchScope,
    strategy_fingerprint,
)
from saathi.platform.tg.registry import StrategyRegistry
from saathi.platform.tg.regime import MarketRegimeEngine, RegimeAssessment
from saathi.platform.tg.policy import PolicyEngine, DEFAULT_POLICY
from saathi.platform.tg.risk import RiskEngine, RiskLimitsConfig
from saathi.platform.tg.kill_switch import KillSwitchStore
from saathi.platform.tg.journal import TradeJournal
from saathi.platform.tg.evaluation import StrategyEvaluator, StrategyComparison
from saathi.platform.tg.service import TradingGuardianService
from saathi.platform.tg.strategies import CATALOG, get_catalog_strategy, list_catalog

__all__ = [
    "SCHEMA_VERSION",
    "ENGINE_VERSION",
    "AuthorityMode",
    "DEFAULT_AUTHORITY_MODE",
    "MarketRegime",
    "StrategyActivation",
    "StrategyEvaluationVerdict",
    "GateStatus",
    "ProposalStatus",
    "TradingStrategy",
    "StrategyVersion",
    "StrategyParameterSet",
    "MarketInstrument",
    "MarketBar",
    "MarketSnapshot",
    "TradeSignal",
    "TradeProposal",
    "PolicyGateResult",
    "PolicyDecision",
    "RiskDecision",
    "PaperOrderRef",
    "PaperFillRef",
    "PaperPositionView",
    "PaperPortfolioView",
    "TradeJournalEntry",
    "BacktestRunRef",
    "BacktestResultView",
    "PerformanceMetrics",
    "TradingGuardianPolicy",
    "TradingGuardianKillSwitch",
    "KillSwitchScope",
    "strategy_fingerprint",
    "StrategyRegistry",
    "MarketRegimeEngine",
    "RegimeAssessment",
    "PolicyEngine",
    "DEFAULT_POLICY",
    "RiskEngine",
    "RiskLimitsConfig",
    "KillSwitchStore",
    "TradeJournal",
    "StrategyEvaluator",
    "StrategyComparison",
    "TradingGuardianService",
    "CATALOG",
    "get_catalog_strategy",
    "list_catalog",
]

# Live trading is not an executable option in this foundation.
LIVE_TRADING_AUTHORIZED = False
LIVE_ORDER_CAPABLE = False
BROKER_CREDENTIAL_SUPPORT = False
