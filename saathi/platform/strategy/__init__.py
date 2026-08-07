"""M62.4 — deterministic strategy versioning + bias-resistant backtesting.

Simulation ONLY. No order submission, broker access, live provider, credential
access, network, or execution authority. A backtest evaluates a versioned strategy
against versioned market data; a passing result is NOT trading approval, investment
advice, or proof of profitability. See docs/trading/STRATEGY_AND_BACKTESTING.md.
"""
from saathi.platform.strategy.models import (
    StrategyType, StrategyStatus, STRATEGY_TRANSITIONS, can_strategy_transition,
    BacktestStatus, BACKTEST_TRANSITIONS, can_backtest_transition, BACKTEST_TERMINAL,
    FeatureKind, Comparator, SignalAction, SizingMethod, LotMethod,
    FeatureSpec, SignalRule, SizingRule, CostModel, ZERO_COST, REALISTIC_COST, STRESSED_COST,
    ThesisReference, StrategyDefinition, StrategyVersion, DatasetReference,
    SimulatedOrder, SimOrderStatus, SimPosition, EquityPoint,
    strategy_hash, ENGINE_VERSION, FEATURE_VERSION, D, q2,
)
from saathi.platform.strategy.features import BacktestContext, compute_feature, compute_all, LookAheadViolation
from saathi.platform.strategy.signals import evaluate_signals
from saathi.platform.strategy.sizing import target_quantity, SizingError
from saathi.platform.strategy.execution_model import simulate_fill, compute_fees, apply_slippage
from saathi.platform.strategy.accounting import PortfolioAccountant
from saathi.platform.strategy import metrics as metrics_mod
from saathi.platform.strategy.metrics import compute_metrics, Metric, MetricStatus
from saathi.platform.strategy.validation import (
    validate_strategy, is_runnable, evaluate_backtest, ValidationOutcome, ValidationResult,
    Finding, SufficiencyPolicy,
)
from saathi.platform.strategy.walk_forward import (
    Split, SplitKind, make_chronological_splits, check_splits, build_folds, Fold, aggregate_folds,
)
from saathi.platform.strategy import stress as stress_mod
from saathi.platform.strategy.engine import run_backtest, BacktestResult, quality_summary
from saathi.platform.strategy.store import StrategyStore
from saathi.platform.strategy.service import StrategyService
from saathi.platform.strategy.guardian_sim import simulate_guardian_review
from saathi.platform.strategy import fixtures as fixtures_mod
from saathi.platform.strategy.fixtures import (
    VALID_FIXTURES, BROKEN_MATRIX, strategy_fixture_manifest, valid_momentum,
    valid_mean_reversion, valid_buy_and_hold, FIXTURE_VERSION,
)

__all__ = [
    "StrategyType", "StrategyStatus", "STRATEGY_TRANSITIONS", "can_strategy_transition",
    "BacktestStatus", "BACKTEST_TRANSITIONS", "can_backtest_transition", "BACKTEST_TERMINAL",
    "FeatureKind", "Comparator", "SignalAction", "SizingMethod", "LotMethod",
    "FeatureSpec", "SignalRule", "SizingRule", "CostModel", "ZERO_COST", "REALISTIC_COST", "STRESSED_COST",
    "ThesisReference", "StrategyDefinition", "StrategyVersion", "DatasetReference",
    "SimulatedOrder", "SimOrderStatus", "SimPosition", "EquityPoint",
    "strategy_hash", "ENGINE_VERSION", "FEATURE_VERSION", "D", "q2",
    "BacktestContext", "compute_feature", "compute_all", "LookAheadViolation",
    "evaluate_signals", "target_quantity", "SizingError",
    "simulate_fill", "compute_fees", "apply_slippage", "PortfolioAccountant",
    "metrics_mod", "compute_metrics", "Metric", "MetricStatus",
    "validate_strategy", "is_runnable", "evaluate_backtest", "ValidationOutcome", "ValidationResult",
    "Finding", "SufficiencyPolicy",
    "Split", "SplitKind", "make_chronological_splits", "check_splits", "build_folds", "Fold", "aggregate_folds",
    "stress_mod", "run_backtest", "BacktestResult", "quality_summary",
    "StrategyStore", "StrategyService", "simulate_guardian_review",
    "fixtures_mod", "VALID_FIXTURES", "BROKEN_MATRIX", "strategy_fixture_manifest",
    "valid_momentum", "valid_mean_reversion", "valid_buy_and_hold", "FIXTURE_VERSION",
]
