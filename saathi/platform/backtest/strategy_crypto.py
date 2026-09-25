"""Deterministic BTC/ETH spot strategy qualification.

This module is a research boundary. Strategies emit canonical ``TradingSignal``
objects only; the simulator owns hypothetical sizing and cannot send orders,
reserve cash, access accounts, or authorize execution.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from saathi.platform.backtest.convergence import (
    LockedStrategyConfiguration,
    StrategyEvaluationPlan,
    WalkForwardResult,
)
from saathi.platform.backtest.cost import CryptoCostModel
from saathi.platform.market_data.contract import (
    AssetClass,
    HistoricalBar,
    PointInTime,
    ProviderReference,
)
from saathi.platform.market_data.crypto_dataset import (
    DatasetCertification,
    DatasetQualityStatus,
    canonical_historical_hash,
)
from saathi.platform.market_data.identity import resolve_market_identity
from saathi.platform.signal import Direction, TradingSignal
from saathi.platform.trading_models import DataQuality


CANONICAL_CRYPTO_INSTRUMENTS = (
    "BINANCE:BTC/USDT",
    "BINANCE:ETH/USDT",
)
MINIMUM_QUALIFICATION_BARS = 240
MAX_FAMILIES = 3
MAX_PARAMETER_VARIANTS = 4
WALK_FORWARD_FOLDS = 2
INITIAL_CAPITAL = Decimal("10000")
POSITION_FRACTION = Decimal("0.95")
BASE_VOLUME_PARTICIPATION = Decimal("0.01")


class StrategyFamily(str, Enum):
    TREND_MOMENTUM = "TREND_MOMENTUM"
    BREAKOUT = "BREAKOUT"
    MEAN_REVERSION = "MEAN_REVERSION"


class QualificationStatus(str, Enum):
    REJECTED = "REJECTED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    OOS_VALIDATED_WITH_LIMITATIONS = "OOS_VALIDATED_WITH_LIMITATIONS"
    PAPER_CANDIDATE = "PAPER_CANDIDATE"


class SelectionBiasStatus(str, Enum):
    MULTIPLE_TESTING_LIMITED = "MULTIPLE_TESTING_LIMITED"


class RejectionReason(str, Enum):
    OOS_FAILED = "OOS_FAILED"
    COSTS_ERASE_EDGE = "COSTS_ERASE_EDGE"
    WALK_FORWARD_UNSTABLE = "WALK_FORWARD_UNSTABLE"
    EXCESS_DRAWDOWN = "EXCESS_DRAWDOWN"
    TOO_FEW_TRADES = "TOO_FEW_TRADES"
    HIGH_SELECTION_RISK = "HIGH_SELECTION_RISK"
    REGIME_DEPENDENT = "REGIME_DEPENDENT"
    BENCHMARK_UNDERPERFORMANCE = "BENCHMARK_UNDERPERFORMANCE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TestWindowSpentError(RuntimeError):
    """A spent final test cannot be relabelled unbiased after retuning."""

    __test__ = False


def _d(value: object, *, name: str = "value") -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}") from exc
    if not result.is_finite():
        raise ValueError(f"invalid {name}")
    return result


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0000000001"))


def _aware(value: datetime, *, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _public(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _public(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _public(item) for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
    if isinstance(value, (tuple, list)):
        return [_public(item) for item in value]
    return value


PROMOTABLE_DATA_QUALITY = {
    "REAL_PUBLIC_HISTORICAL_REVISION_SNAPSHOT",
    "REPLAY_OF_REAL_PUBLIC_HISTORICAL",
}


@dataclass(frozen=True)
class CryptoDatasetSnapshot:
    dataset_id: str
    dataset_version: str
    instrument_id: str
    data_mode: str
    source: str
    quality_classification: str
    revision_snapshot: str
    revision_cutoff: datetime
    content_hash: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.instrument_id not in CANONICAL_CRYPTO_INSTRUMENTS:
            raise ValueError("unsupported canonical spot instrument")
        identity = resolve_market_identity(instrument_id=self.instrument_id)
        if identity.market != "CRYPTO" or identity.asset_class != "CRYPTO":
            raise ValueError("unsupported canonical spot instrument")
        if self.data_mode not in {"HISTORICAL", "REPLAY", "SYNTHETIC"}:
            raise ValueError("invalid qualification data mode")
        _aware(self.revision_cutoff, name="revision_cutoff")
        if not all((self.dataset_id, self.dataset_version, self.source, self.revision_snapshot)):
            raise ValueError("dataset provenance is incomplete")
        if len(self.content_hash) != 64:
            raise ValueError("dataset content hash must be sha256")

    @property
    def paper_evidence_eligible(self) -> bool:
        return self.quality_classification in PROMOTABLE_DATA_QUALITY and self.data_mode != "SYNTHETIC"


@dataclass(frozen=True)
class StrategyHypothesis:
    strategy_id: str
    strategy_version: str
    family: StrategyFamily
    instrument_id: str
    economic_hypothesis: str
    feature_set: tuple[str, ...]
    parameter_search_space: tuple[Mapping[str, Any], ...]
    evaluation_plan: StrategyEvaluationPlan
    benchmark: str
    cost_model: str
    fill_model: str
    trial_budget: int
    selection_rule: str
    rejection_conditions: tuple[str, ...]


@dataclass(frozen=True)
class QualificationFill:
    instrument_id: str
    side: str
    decision_at: datetime
    fill_at: datetime
    reference_price: Decimal
    fill_price: Decimal
    quantity: Decimal
    explicit_fee: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal


@dataclass(frozen=True)
class SegmentResult:
    period_start: datetime
    period_end: datetime
    gross_return: Decimal
    net_return: Decimal
    benchmark_return: Decimal
    excess_return: Decimal
    max_drawdown: Decimal
    volatility: Decimal
    turnover: Decimal
    trade_count: int
    cost_drag: Decimal
    hit_rate: Decimal | None
    average_holding_period: Decimal | None
    fills: tuple[QualificationFill, ...] = ()
    period_returns: tuple[tuple[datetime, Decimal], ...] = ()

    def to_public(self) -> dict[str, Any]:
        return _public(self)


@dataclass(frozen=True)
class BenchmarkResult:
    benchmark: str
    instrument_id: str
    return_value: Decimal
    max_drawdown: Decimal


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    metrics: SegmentResult
    fragile: bool
    assumptions: tuple[str, ...]
    details: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class StrategyQualificationResult:
    strategy_id: str
    strategy_version: str
    instrument_id: str
    selected_config_ref: LockedStrategyConfiguration | None
    train_result: SegmentResult
    validation_result: SegmentResult
    test_result: SegmentResult
    walk_forward_result: WalkForwardResult
    benchmark_result: BenchmarkResult
    cost_sensitivity: tuple[ScenarioResult, ...]
    stress_results: tuple[ScenarioResult, ...]
    regime_analysis: Mapping[str, Any]
    trial_count: int
    strategy_family_count: int
    parameter_variant_count: int
    selection_bias_status: SelectionBiasStatus
    data_quality: str
    dataset_id: str
    dataset_version: str
    revision_snapshot: str
    cost_model_version: str
    fill_model_version: str
    seed: int
    walk_forward_policy: str
    limitations: tuple[str, ...]
    rejection_reasons: tuple[RejectionReason, ...]
    qualification_status: QualificationStatus

    def to_public(self) -> dict[str, Any]:
        return _public(self)


@dataclass(frozen=True)
class QualificationSetResult:
    results: tuple[StrategyQualificationResult, ...]
    certification_outcome: str
    survivor_count: int
    family_count: int
    instrument_count: int
    total_trial_count: int
    limitations: tuple[str, ...]

    def to_public(self) -> dict[str, Any]:
        return {
            "certification_outcome": self.certification_outcome,
            "survivor_count": self.survivor_count,
            "family_count": self.family_count,
            "instrument_count": self.instrument_count,
            "total_trial_count": self.total_trial_count,
            "limitations": list(self.limitations),
            "results": [item.to_public() for item in self.results],
            "authority": {
                "research_only": True,
                "live_trading": False,
                "real_broker": False,
                "private_account_access": False,
                "withdrawal": False,
                "leverage": False,
                "llm_execution_authority": False,
                "signal_execution_authority": False,
                "intent_execution_authority": False,
            },
        }


class FinalTestLedger:
    """In-memory scientific guard; durable persistence remains explicit debt."""

    def __init__(self) -> None:
        self._spent: dict[tuple[str, datetime, datetime], str] = {}

    def record(self, evaluation_key: str, window: tuple[datetime, datetime], config_hash: str) -> None:
        key = (evaluation_key, window[0], window[1])
        prior = self._spent.get(key)
        if prior is not None and prior != config_hash:
            raise TestWindowSpentError("final test window was already spent by another configuration")
        self._spent[key] = config_hash


class SpotStrategy:
    family: StrategyFamily
    strategy_id: str
    strategy_version = "1.0.0"

    def __init__(self, parameters: Mapping[str, Any]) -> None:
        self.parameters = dict(parameters)

    def _signal(
        self,
        history: Sequence[HistoricalBar],
        data_mode: str,
        direction: Direction,
        strength: Decimal,
        reason_codes: Iterable[str],
    ) -> TradingSignal:
        bar = history[-1]
        return TradingSignal.create(
            self.strategy_id,
            self.strategy_version,
            bar.instrument_id,
            direction,
            min(Decimal("1"), max(Decimal("0"), strength)),
            bar.as_of,
            bar.as_of + timedelta(days=2),
            data_mode,
            tuple(reason_codes),
            quality="VALID",
        )

    def _no_signal(self, history: Sequence[HistoricalBar], data_mode: str, reason: str) -> TradingSignal:
        return self._signal(history, data_mode, Direction.NO_SIGNAL, Decimal("0"), (reason,))

    def evaluate(self, history: Sequence[HistoricalBar], *, data_mode: str) -> TradingSignal:
        raise NotImplementedError


class TrendMomentumStrategy(SpotStrategy):
    family = StrategyFamily.TREND_MOMENTUM
    strategy_id = "crypto_spot_trend_momentum"

    def evaluate(self, history: Sequence[HistoricalBar], *, data_mode: str) -> TradingSignal:
        fast_n = int(self.parameters["fast_lookback"])
        slow_n = int(self.parameters["slow_lookback"])
        momentum_n = int(self.parameters["momentum_lookback"])
        threshold = _d(self.parameters["momentum_threshold"])
        needed = max(slow_n, momentum_n + 1)
        if len(history) < needed:
            return self._no_signal(history, data_mode, "WARMUP_INCOMPLETE")
        closes = [row.close for row in history]
        fast = sum(closes[-fast_n:], Decimal("0")) / Decimal(fast_n)
        slow = sum(closes[-slow_n:], Decimal("0")) / Decimal(slow_n)
        base = closes[-momentum_n - 1]
        momentum = (closes[-1] / base - 1) if base > 0 else Decimal("0")
        if fast > slow and momentum >= threshold:
            strength = min(Decimal("1"), abs(fast / slow - 1) * Decimal("20") + max(momentum, 0))
            return self._signal(
                history,
                data_mode,
                Direction.LONG_BIAS,
                strength,
                ("FAST_MA_ABOVE_SLOW_MA", "MOMENTUM_THRESHOLD_MET"),
            )
        if fast < slow and momentum <= -threshold:
            return self._signal(
                history,
                data_mode,
                Direction.REDUCE_BIAS,
                min(Decimal("1"), abs(momentum)),
                ("TREND_INVALIDATED",),
            )
        return self._signal(history, data_mode, Direction.NEUTRAL, Decimal("0"), ("NO_TREND_EDGE",))


class BreakoutStrategy(SpotStrategy):
    family = StrategyFamily.BREAKOUT
    strategy_id = "crypto_spot_breakout"

    def evaluate(self, history: Sequence[HistoricalBar], *, data_mode: str) -> TradingSignal:
        lookback = int(self.parameters["lookback"])
        exit_lookback = int(self.parameters["exit_lookback"])
        confirmation = _d(self.parameters["confirmation"])
        if len(history) < max(lookback, exit_lookback) + 1:
            return self._no_signal(history, data_mode, "WARMUP_INCOMPLETE")
        # The decision bar is deliberately excluded from both range boundaries.
        prior = history[-lookback - 1 : -1]
        prior_high = max(row.high for row in prior)
        prior_low = min(row.low for row in history[-exit_lookback - 1 : -1])
        close = history[-1].close
        if close > prior_high * (Decimal("1") + confirmation):
            distance = close / prior_high - 1
            return self._signal(
                history,
                data_mode,
                Direction.LONG_BIAS,
                min(Decimal("1"), distance * Decimal("20")),
                ("PRIOR_RANGE_BREAKOUT", "DECISION_BAR_CLOSE_CONFIRMED"),
            )
        if close < prior_low:
            return self._signal(
                history,
                data_mode,
                Direction.REDUCE_BIAS,
                min(Decimal("1"), prior_low / close - 1),
                ("PRIOR_RANGE_BREAKDOWN",),
            )
        return self._signal(history, data_mode, Direction.NEUTRAL, Decimal("0"), ("INSIDE_PRIOR_RANGE",))


class MeanReversionStrategy(SpotStrategy):
    family = StrategyFamily.MEAN_REVERSION
    strategy_id = "crypto_spot_mean_reversion"

    def evaluate(self, history: Sequence[HistoricalBar], *, data_mode: str) -> TradingSignal:
        lookback = int(self.parameters["lookback"])
        entry_deviation = _d(self.parameters["entry_deviation"])
        exit_deviation = _d(self.parameters["exit_deviation"])
        if len(history) < lookback + 1:
            return self._no_signal(history, data_mode, "WARMUP_INCOMPLETE")
        prior_closes = [row.close for row in history[-lookback - 1 : -1]]
        center = sum(prior_closes, Decimal("0")) / Decimal(lookback)
        bar = history[-1]
        deviation = (bar.close / center - 1) if center > 0 else Decimal("0")
        reversal_confirmed = bar.close > bar.open
        if deviation <= -entry_deviation and reversal_confirmed:
            return self._signal(
                history,
                data_mode,
                Direction.LONG_BIAS,
                min(Decimal("1"), abs(deviation)),
                ("BOUNDED_NEGATIVE_DEVIATION", "REVERSAL_CONFIRMED"),
            )
        if deviation >= -exit_deviation:
            return self._signal(
                history,
                data_mode,
                Direction.REDUCE_BIAS,
                min(Decimal("1"), abs(deviation)),
                ("CENTRAL_TENDENCY_REACHED",),
            )
        return self._signal(
            history,
            data_mode,
            Direction.NEUTRAL,
            Decimal("0"),
            ("DEVIATION_WITHOUT_REVERSAL",),
        )


STRATEGY_CLASSES = {
    TrendMomentumStrategy.strategy_id: TrendMomentumStrategy,
    BreakoutStrategy.strategy_id: BreakoutStrategy,
    MeanReversionStrategy.strategy_id: MeanReversionStrategy,
}


class RegisteredSpotStrategyRegistry:
    """Static registry: no eval, pickle, dynamic import, or filesystem config."""

    def create(self, strategy_id: str, parameters: Mapping[str, Any]) -> SpotStrategy:
        strategy_class = STRATEGY_CLASSES.get(strategy_id)
        if strategy_class is None:
            raise ValueError("strategy is not registered")
        normalized = self._validate(strategy_class.family, parameters)
        return strategy_class(normalized)

    def _validate(self, family: StrategyFamily, parameters: Mapping[str, Any]) -> dict[str, Any]:
        params = dict(parameters)
        if family is StrategyFamily.TREND_MOMENTUM:
            expected = {"fast_lookback", "slow_lookback", "momentum_lookback", "momentum_threshold"}
            if set(params) != expected:
                raise ValueError("invalid registered trend parameters")
            fast, slow, momentum = (int(params[key]) for key in ("fast_lookback", "slow_lookback", "momentum_lookback"))
            threshold = _d(params["momentum_threshold"])
            if not (2 <= fast < slow <= 60 and 2 <= momentum <= 40 and Decimal("0") <= threshold <= Decimal("0.05")):
                raise ValueError("trend parameters outside bounded policy")
        elif family is StrategyFamily.BREAKOUT:
            expected = {"lookback", "confirmation", "exit_lookback"}
            if set(params) != expected:
                raise ValueError("invalid registered breakout parameters")
            lookback, exit_lookback = int(params["lookback"]), int(params["exit_lookback"])
            confirmation = _d(params["confirmation"])
            if not (10 <= lookback <= 60 and 5 <= exit_lookback <= 30 and Decimal("0") <= confirmation <= Decimal("0.02")):
                raise ValueError("breakout parameters outside bounded policy")
        else:
            expected = {"lookback", "entry_deviation", "exit_deviation"}
            if set(params) != expected:
                raise ValueError("invalid registered mean-reversion parameters")
            lookback = int(params["lookback"])
            entry = _d(params["entry_deviation"])
            exit_value = _d(params["exit_deviation"])
            if not (5 <= lookback <= 40 and Decimal("0.01") <= entry <= Decimal("0.10") and Decimal("0") <= exit_value <= Decimal("0.02")):
                raise ValueError("mean-reversion parameters outside bounded policy")
        return params


PARAMETER_GRIDS: dict[StrategyFamily, tuple[dict[str, Any], ...]] = {
    StrategyFamily.TREND_MOMENTUM: (
        {"fast_lookback": 5, "slow_lookback": 20, "momentum_lookback": 10, "momentum_threshold": "0"},
        {"fast_lookback": 5, "slow_lookback": 20, "momentum_lookback": 10, "momentum_threshold": "0.01"},
        {"fast_lookback": 10, "slow_lookback": 40, "momentum_lookback": 20, "momentum_threshold": "0"},
        {"fast_lookback": 10, "slow_lookback": 40, "momentum_lookback": 20, "momentum_threshold": "0.01"},
    ),
    StrategyFamily.BREAKOUT: (
        {"lookback": 20, "confirmation": "0", "exit_lookback": 10},
        {"lookback": 20, "confirmation": "0.005", "exit_lookback": 10},
        {"lookback": 55, "confirmation": "0", "exit_lookback": 20},
        {"lookback": 55, "confirmation": "0.005", "exit_lookback": 20},
    ),
    StrategyFamily.MEAN_REVERSION: (
        {"lookback": 10, "entry_deviation": "0.03", "exit_deviation": "0"},
        {"lookback": 10, "entry_deviation": "0.05", "exit_deviation": "0"},
        {"lookback": 20, "entry_deviation": "0.03", "exit_deviation": "0"},
        {"lookback": 20, "entry_deviation": "0.05", "exit_deviation": "0"},
    ),
}


HYPOTHESES = {
    StrategyFamily.TREND_MOMENTUM: (
        "Persistent spot trends may continue after a fast/slow average alignment and bounded multi-period momentum confirmation.",
        ("close", "fast_sma", "slow_sma", "multi_period_return"),
    ),
    StrategyFamily.BREAKOUT: (
        "A close above a fully prior spot range may continue, provided execution occurs only at the next observation.",
        ("close", "prior_high", "prior_low"),
    ),
    StrategyFamily.MEAN_REVERSION: (
        "A bounded negative deviation from a prior close average may revert only after same-bar reversal confirmation.",
        ("open", "close", "prior_close_average", "deviation"),
    ),
}


class CryptoQualificationRunner:
    def __init__(
        self,
        dataset: CryptoDatasetSnapshot,
        bars: Iterable[HistoricalBar],
        *,
        cost_model: CryptoCostModel | None = None,
        final_test_ledger: FinalTestLedger | None = None,
    ) -> None:
        self.dataset = dataset
        self.cost_model = cost_model or CryptoCostModel()
        if self.cost_model.is_zero:
            raise ValueError("zero-cost qualification is forbidden")
        self.final_test_ledger = final_test_ledger or FinalTestLedger()
        all_rows = tuple(bars)
        if any(row.instrument_id != dataset.instrument_id for row in all_rows):
            raise ValueError("cross-asset data is forbidden in one qualification runner")
        self._validate_revision_lineage(all_rows)
        self._revision_rows = tuple(row for row in all_rows if row.available_at <= dataset.revision_cutoff)
        if dataset_content_hash(self._revision_rows) != dataset.content_hash:
            raise ValueError("dataset content hash does not match the revision snapshot")
        self.bars = self._decision_timeline()
        if len(self.bars) < 6:
            raise ValueError("insufficient bars to construct chronological evaluation windows")

    def _validate_revision_lineage(self, rows: Sequence[HistoricalBar]) -> None:
        by_id: dict[str, HistoricalBar] = {}
        for row in rows:
            if row.revision_id in by_id:
                raise ValueError("duplicate revision id")
            by_id[row.revision_id] = row
        for row in rows:
            seen: set[str] = set()
            current = row
            while current.supersedes_revision_id:
                if current.revision_id in seen:
                    raise ValueError("cyclic revision lineage")
                seen.add(current.revision_id)
                prior = by_id.get(current.supersedes_revision_id)
                if prior is None or prior.source_record_id != row.source_record_id:
                    raise ValueError("unknown or cross-record superseded revision")
                current = prior

    def _decision_timeline(self) -> tuple[HistoricalBar, ...]:
        grouped: dict[str, list[HistoricalBar]] = {}
        for row in self._revision_rows:
            grouped.setdefault(row.source_record_id, []).append(row)
        timeline = []
        for revisions in grouped.values():
            as_of = revisions[0].as_of
            if any(row.as_of != as_of for row in revisions):
                raise ValueError("revisions of one bar must preserve as_of")
            candidates = [row for row in revisions if row.available_at <= as_of and row.status != "RETRACTED"]
            if candidates:
                timeline.append(max(candidates, key=lambda row: (row.available_at, row.revision_id)))
        timeline.sort(key=lambda row: (row.as_of, row.source_record_id))
        if len({row.as_of for row in timeline}) != len(timeline):
            raise ValueError("duplicate observation time")
        return tuple(timeline)

    def visible_history_at(self, decision_time: datetime) -> tuple[HistoricalBar, ...]:
        _aware(decision_time, name="decision_time")
        grouped: dict[str, HistoricalBar] = {}
        for row in self._revision_rows:
            if row.as_of > decision_time or row.available_at > decision_time or row.status == "RETRACTED":
                continue
            prior = grouped.get(row.source_record_id)
            if prior is None or (row.available_at, row.revision_id) > (prior.available_at, prior.revision_id):
                grouped[row.source_record_id] = row
        return tuple(sorted(grouped.values(), key=lambda row: (row.as_of, row.source_record_id)))

    def _indices(self) -> tuple[int, int]:
        count = len(self.bars)
        return int(count * 0.6), int(count * 0.8)

    def preregistrations(self) -> tuple[StrategyHypothesis, ...]:
        train_end, validation_end = self._indices()
        plans = []
        for family in StrategyFamily:
            strategy_class = next(item for item in STRATEGY_CLASSES.values() if item.family is family)
            economic_hypothesis, feature_set = HYPOTHESES[family]
            grid = tuple(MappingProxyType(dict(item)) for item in PARAMETER_GRIDS[family])
            if len(grid) > MAX_PARAMETER_VARIANTS:
                raise ValueError("parameter budget exceeded")
            evaluation_id = f"strategy-crypto-1:{self.dataset.instrument_id}:{family.value}"
            plan = StrategyEvaluationPlan(
                evaluation_id=evaluation_id,
                strategy_id=strategy_class.strategy_id,
                strategy_version=strategy_class.strategy_version,
                dataset_id=self.dataset.dataset_id,
                dataset_version=self.dataset.dataset_version,
                market="CRYPTO",
                venue="BINANCE",
                train_start=self.bars[0].as_of,
                train_end=self.bars[train_end - 1].as_of,
                validation_start=self.bars[train_end].as_of,
                validation_end=self.bars[validation_end - 1].as_of,
                test_start=self.bars[validation_end].as_of,
                test_end=self.bars[-1].as_of + timedelta(microseconds=1),
                cost_model_version=self.cost_model.version,
                fill_model_version="next-observation-open-v1",
                trial_count=12,
                seed=0,
                walk_forward_policy="EXPANDING",
                engine_version="strategy-crypto-1-v1",
            )
            plans.append(
                StrategyHypothesis(
                    strategy_id=strategy_class.strategy_id,
                    strategy_version=strategy_class.strategy_version,
                    family=family,
                    instrument_id=self.dataset.instrument_id,
                    economic_hypothesis=economic_hypothesis,
                    feature_set=feature_set,
                    parameter_search_space=grid,
                    evaluation_plan=plan,
                    benchmark="SAME_INSTRUMENT_SPOT_BUY_AND_HOLD",
                    cost_model=self.cost_model.version,
                    fill_model="next-observation-open-v1",
                    trial_budget=12,
                    selection_rule="MAX_VALIDATION_NET_RETURN_THEN_EXCESS_THEN_LOWER_DRAWDOWN_THEN_CONFIG_HASH",
                    rejection_conditions=tuple(reason.value for reason in RejectionReason),
                )
            )
        return tuple(plans)

    def _validate_hypothesis(self, hypothesis: StrategyHypothesis) -> None:
        expected_class = STRATEGY_CLASSES.get(hypothesis.strategy_id)
        if expected_class is None or expected_class.family is not hypothesis.family:
            raise ValueError("strategy hypothesis is not registered")
        if hypothesis.instrument_id != self.dataset.instrument_id:
            raise ValueError("cross-asset hypothesis is forbidden")
        if len(hypothesis.parameter_search_space) > MAX_PARAMETER_VARIANTS or hypothesis.trial_budget != 12:
            raise ValueError("parameter budget exceeded after preregistration")
        expected_grid = tuple(dict(item) for item in PARAMETER_GRIDS[hypothesis.family])
        actual_grid = tuple(dict(item) for item in hypothesis.parameter_search_space)
        if actual_grid != expected_grid:
            raise ValueError("parameter budget or preregistered search space changed")
        plan = hypothesis.evaluation_plan
        if (plan.dataset_id, plan.dataset_version) != (self.dataset.dataset_id, self.dataset.dataset_version):
            raise ValueError("preregistered dataset changed")

    def _configuration_hash(self, parameters: Mapping[str, Any]) -> str:
        payload = json.dumps(dict(parameters), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def run_segment(
        self,
        strategy: SpotStrategy,
        *,
        start_index: int,
        end_index: int,
        cost_model: CryptoCostModel | None = None,
        fill_delay: int = 1,
        volume_participation: Decimal = BASE_VOLUME_PARTICIPATION,
    ) -> SegmentResult:
        return self._run_on_timeline(
            strategy,
            self.bars,
            start_index=start_index,
            end_index=end_index,
            cost_model=cost_model or self.cost_model,
            fill_delay=fill_delay,
            volume_participation=volume_participation,
            revision_aware=True,
        )

    def _run_on_timeline(
        self,
        strategy: SpotStrategy,
        timeline: Sequence[HistoricalBar],
        *,
        start_index: int,
        end_index: int,
        cost_model: CryptoCostModel,
        fill_delay: int,
        volume_participation: Decimal,
        revision_aware: bool,
    ) -> SegmentResult:
        if cost_model.is_zero:
            raise ValueError("zero-cost qualification is forbidden")
        if fill_delay < 1:
            raise ValueError("same-bar execution is forbidden")
        if not (0 <= start_index < end_index <= len(timeline)):
            raise ValueError("invalid segment bounds")
        participation = _d(volume_participation, name="volume participation")
        if not (Decimal("0") < participation <= Decimal("1")):
            raise ValueError("invalid volume participation")

        cash = INITIAL_CAPITAL
        quantity = Decimal("0")
        pending: tuple[int, TradingSignal] | None = None
        fills: list[QualificationFill] = []
        equity_points: list[tuple[datetime, Decimal]] = []
        direct_cost = Decimal("0")
        turnover_notional = Decimal("0")
        entry_cost = Decimal("0")
        entry_index: int | None = None
        completed_returns: list[Decimal] = []
        holding_periods: list[int] = []

        for index in range(start_index, end_index):
            bar = timeline[index]
            if pending is not None and pending[0] == index:
                signal = pending[1]
                side = "BUY" if signal.direction is Direction.LONG_BIAS else "SELL"
                ask, bid = cost_model.quote(bar.open)
                fill_price = cost_model.fill_price(side, ask, bid)
                if side == "BUY" and quantity == 0:
                    available_notional = min(
                        cash * POSITION_FRACTION,
                        bar.volume * bar.open * participation,
                    )
                    fee_rate = cost_model.fee_bps / Decimal("10000")
                    fill_quantity = available_notional / (fill_price * (Decimal("1") + fee_rate))
                    estimate = cost_model.estimate(bar.instrument_id, side, bar.open, ask, fill_quantity)
                    explicit_fee = fill_price * fill_quantity * fee_rate
                    cash -= fill_price * fill_quantity + explicit_fee
                    quantity = fill_quantity
                    direct_cost += estimate.total_cost
                    turnover_notional += fill_price * fill_quantity
                    entry_cost = fill_price * fill_quantity + explicit_fee
                    entry_index = index
                    fills.append(
                        QualificationFill(
                            instrument_id=bar.instrument_id,
                            side=side,
                            decision_at=signal.generated_at,
                            fill_at=bar.as_of,
                            reference_price=bar.open,
                            fill_price=fill_price,
                            quantity=fill_quantity,
                            explicit_fee=explicit_fee,
                            spread_cost=estimate.spread_cost,
                            slippage_cost=estimate.slippage_cost,
                        )
                    )
                elif side == "SELL" and quantity > 0:
                    fill_quantity = quantity
                    estimate = cost_model.estimate(bar.instrument_id, side, bar.open, bid, fill_quantity)
                    explicit_fee = fill_price * fill_quantity * cost_model.fee_bps / Decimal("10000")
                    proceeds = fill_price * fill_quantity - explicit_fee
                    cash += proceeds
                    direct_cost += estimate.total_cost
                    turnover_notional += fill_price * fill_quantity
                    completed_returns.append(proceeds / entry_cost - 1 if entry_cost > 0 else Decimal("0"))
                    if entry_index is not None:
                        holding_periods.append(index - entry_index)
                    quantity = Decimal("0")
                    entry_cost = Decimal("0")
                    entry_index = None
                    fills.append(
                        QualificationFill(
                            instrument_id=bar.instrument_id,
                            side=side,
                            decision_at=signal.generated_at,
                            fill_at=bar.as_of,
                            reference_price=bar.open,
                            fill_price=fill_price,
                            quantity=fill_quantity,
                            explicit_fee=explicit_fee,
                            spread_cost=estimate.spread_cost,
                            slippage_cost=estimate.slippage_cost,
                        )
                    )
                pending = None

            equity_points.append((bar.as_of, cash + quantity * bar.close))
            if pending is not None or index + fill_delay >= end_index:
                continue
            history = (
                self.visible_history_at(bar.as_of)
                if revision_aware
                else tuple(timeline[: index + 1])
            )
            signal = strategy.evaluate(history, data_mode=self.dataset.data_mode)
            if signal.direction is Direction.LONG_BIAS and quantity == 0:
                pending = (index + fill_delay, signal)
            elif signal.direction in {Direction.REDUCE_BIAS, Direction.EXIT_BIAS} and quantity > 0:
                pending = (index + fill_delay, signal)

        returns = []
        for (timestamp, current), (_, prior) in zip(equity_points[1:], equity_points[:-1]):
            returns.append((timestamp, current / prior - 1 if prior > 0 else Decimal("0")))
        final_equity = equity_points[-1][1]
        net_return = final_equity / INITIAL_CAPITAL - 1
        cost_drag = direct_cost / INITIAL_CAPITAL
        gross_return = net_return + cost_drag
        benchmark_return = timeline[end_index - 1].close / timeline[start_index].open - 1
        peak = INITIAL_CAPITAL
        max_drawdown = Decimal("0")
        for _, equity in equity_points:
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, Decimal("1") - equity / peak)
        if returns:
            values = [value for _, value in returns]
            mean = sum(values, Decimal("0")) / Decimal(len(values))
            variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values))
            volatility = variance.sqrt() * Decimal("365").sqrt()
        else:
            volatility = Decimal("0")
        hit_rate = None
        if completed_returns:
            hit_rate = Decimal(sum(value > 0 for value in completed_returns)) / Decimal(len(completed_returns))
        average_holding = None
        if holding_periods:
            average_holding = Decimal(sum(holding_periods)) / Decimal(len(holding_periods))
        return SegmentResult(
            period_start=timeline[start_index].as_of,
            period_end=timeline[end_index - 1].as_of,
            gross_return=_q(gross_return),
            net_return=_q(net_return),
            benchmark_return=_q(benchmark_return),
            excess_return=_q(net_return - benchmark_return),
            max_drawdown=_q(max_drawdown),
            volatility=_q(volatility),
            turnover=_q(turnover_notional / INITIAL_CAPITAL),
            trade_count=len(completed_returns),
            cost_drag=_q(cost_drag),
            hit_rate=_q(hit_rate) if hit_rate is not None else None,
            average_holding_period=_q(average_holding) if average_holding is not None else None,
            fills=tuple(fills),
            period_returns=tuple((timestamp, _q(value)) for timestamp, value in returns),
        )

    def _ranked_configuration(
        self,
        hypothesis: StrategyHypothesis,
        *,
        train_bounds: tuple[int, int],
        validation_bounds: tuple[int, int],
        timeline: Sequence[HistoricalBar] | None = None,
    ) -> tuple[dict[str, Any], SegmentResult, SegmentResult]:
        rows = timeline or self.bars
        evidence = []
        for parameters in hypothesis.parameter_search_space:
            strategy = RegisteredSpotStrategyRegistry().create(hypothesis.strategy_id, parameters)
            train = self._run_on_timeline(
                strategy,
                rows,
                start_index=train_bounds[0],
                end_index=train_bounds[1],
                cost_model=self.cost_model,
                fill_delay=1,
                volume_participation=BASE_VOLUME_PARTICIPATION,
                revision_aware=rows is self.bars,
            )
            validation = self._run_on_timeline(
                strategy,
                rows,
                start_index=validation_bounds[0],
                end_index=validation_bounds[1],
                cost_model=self.cost_model,
                fill_delay=1,
                volume_participation=BASE_VOLUME_PARTICIPATION,
                revision_aware=rows is self.bars,
            )
            evidence.append((dict(parameters), train, validation))
        return sorted(
            evidence,
            key=lambda row: (
                -row[2].net_return,
                -row[2].excess_return,
                row[2].max_drawdown,
                row[2].turnover,
                self._configuration_hash(row[0]),
            ),
        )[0]

    def select_and_lock(self, hypothesis: StrategyHypothesis) -> LockedStrategyConfiguration:
        self._validate_hypothesis(hypothesis)
        train_end, validation_end = self._indices()
        parameters, _, _ = self._ranked_configuration(
            hypothesis,
            train_bounds=(0, train_end),
            validation_bounds=(train_end, validation_end),
        )
        return LockedStrategyConfiguration.lock(
            hypothesis.strategy_id,
            hypothesis.strategy_version,
            parameters,
            hypothesis.evaluation_plan.validation_end,
            f"{self.dataset.dataset_id}@{self.dataset.dataset_version}:TRAIN",
            f"{self.dataset.dataset_id}@{self.dataset.dataset_version}:VALIDATION",
            len(hypothesis.parameter_search_space),
            hypothesis.selection_rule,
            self.cost_model.version,
            hypothesis.fill_model,
        )

    def _walk_forward(self, hypothesis: StrategyHypothesis) -> WalkForwardResult:
        count = len(self.bars)
        folds = (
            ((0, int(count * 0.4)), (int(count * 0.4), int(count * 0.5)), (int(count * 0.5), int(count * 0.6))),
            ((0, int(count * 0.6)), (int(count * 0.6), int(count * 0.7)), (int(count * 0.7), int(count * 0.8))),
        )
        segments = []
        for fold_index, (train_bounds, validation_bounds, oos_bounds) in enumerate(folds, start=1):
            parameters, _, validation = self._ranked_configuration(
                hypothesis,
                train_bounds=train_bounds,
                validation_bounds=validation_bounds,
            )
            strategy = RegisteredSpotStrategyRegistry().create(hypothesis.strategy_id, parameters)
            oos = self.run_segment(
                strategy,
                start_index=oos_bounds[0],
                end_index=oos_bounds[1],
                cost_model=self.cost_model,
            )
            segments.append(
                {
                    "fold": fold_index,
                    "train_start": self.bars[train_bounds[0]].as_of.isoformat(),
                    "train_end": self.bars[train_bounds[1] - 1].as_of.isoformat(),
                    "validation_start": self.bars[validation_bounds[0]].as_of.isoformat(),
                    "validation_end": self.bars[validation_bounds[1] - 1].as_of.isoformat(),
                    "test_start": self.bars[oos_bounds[0]].as_of.isoformat(),
                    "test_end": self.bars[oos_bounds[1] - 1].as_of.isoformat(),
                    "selected_config_hash": self._configuration_hash(parameters),
                    "validation_result": validation.to_public(),
                    "oos_result": oos.to_public(),
                }
            )
        return WalkForwardResult(
            run_id=f"wf:{hypothesis.evaluation_plan.evaluation_id}",
            strategy_id=hypothesis.strategy_id,
            strategy_version=hypothesis.strategy_version,
            dataset_id=self.dataset.dataset_id,
            dataset_version=self.dataset.dataset_version,
            segments=tuple(segments),
            trial_count=len(hypothesis.parameter_search_space) * WALK_FORWARD_FOLDS,
            cost_model_version=self.cost_model.version,
            fill_model_version=hypothesis.fill_model,
            status="OOS_VALIDATED_WITH_LIMITATIONS",
            limitations=("MULTIPLE_TESTING_LIMITED",),
        )

    def _cost_sensitivity(
        self,
        strategy: SpotStrategy,
        start_index: int,
        end_index: int,
    ) -> tuple[ScenarioResult, ...]:
        scenarios = (
            ("BASE_COSTS", self.cost_model),
            ("DOUBLE_FEES", self.cost_model.with_multipliers(fee=2, scenario="double-fees")),
            ("DOUBLE_SPREAD", self.cost_model.with_multipliers(spread=2, scenario="double-spread")),
            ("DOUBLE_SLIPPAGE", self.cost_model.with_multipliers(slippage=2, scenario="double-slippage")),
        )
        base_result: SegmentResult | None = None
        results = []
        for name, model in scenarios:
            metrics = self.run_segment(
                strategy,
                start_index=start_index,
                end_index=end_index,
                cost_model=model,
            )
            if base_result is None:
                base_result = metrics
            fragile = base_result.net_return > 0 and metrics.net_return <= 0
            results.append(
                ScenarioResult(
                    scenario=name,
                    metrics=metrics,
                    fragile=fragile,
                    assumptions=(model.status, model.version, "NO_ACCOUNT_SPECIFIC_FEE_CLAIM"),
                )
            )
        return tuple(results)

    def _regime_analysis(self, metrics: SegmentResult) -> dict[str, Any]:
        index_by_time = {bar.as_of: index for index, bar in enumerate(self.bars)}
        buckets: dict[str, list[Decimal]] = {
            "UPTREND": [],
            "DOWNTREND": [],
            "RANGE": [],
            "HIGH_VOLATILITY": [],
            "LOW_VOLATILITY": [],
        }
        for timestamp, strategy_return in metrics.period_returns:
            index = index_by_time[timestamp]
            if index < 60:
                continue
            history = self.bars[: index + 1]
            trailing_return = history[-1].close / history[-21].close - 1
            trend = "UPTREND" if trailing_return > Decimal("0.05") else "DOWNTREND" if trailing_return < Decimal("-0.05") else "RANGE"
            returns_20 = [history[i].close / history[i - 1].close - 1 for i in range(len(history) - 19, len(history))]
            returns_60 = [history[i].close / history[i - 1].close - 1 for i in range(len(history) - 59, len(history))]
            mean_20 = sum(returns_20, Decimal("0")) / Decimal(len(returns_20))
            mean_60 = sum(returns_60, Decimal("0")) / Decimal(len(returns_60))
            vol_20 = (sum((value - mean_20) ** 2 for value in returns_20) / Decimal(len(returns_20))).sqrt()
            vol_60 = (sum((value - mean_60) ** 2 for value in returns_60) / Decimal(len(returns_60))).sqrt()
            volatility = "HIGH_VOLATILITY" if vol_20 > vol_60 else "LOW_VOLATILITY"
            buckets[trend].append(strategy_return)
            buckets[volatility].append(strategy_return)
        return {
            key: {
                "observations": len(values),
                "mean_strategy_return": str(_q(sum(values, Decimal("0")) / Decimal(len(values)))) if values else None,
                "label_policy": "TRAILING_ONLY_V1",
            }
            for key, values in buckets.items()
        }

    def _stress(
        self,
        strategy: SpotStrategy,
        start_index: int,
        end_index: int,
        base: SegmentResult,
        regime_analysis: Mapping[str, Any],
    ) -> tuple[ScenarioResult, ...]:
        delayed = self.run_segment(
            strategy,
            start_index=start_index,
            end_index=end_index,
            cost_model=self.cost_model,
            fill_delay=2,
        )
        test_rows = list(self.bars[start_index:end_index])
        reduced_rows = [row for index, row in enumerate(test_rows) if (index + 1) % 17 != 0]
        missing = self._run_on_timeline(
            strategy,
            reduced_rows,
            start_index=0,
            end_index=len(reduced_rows),
            cost_model=self.cost_model,
            fill_delay=1,
            volume_participation=BASE_VOLUME_PARTICIPATION,
            revision_aware=False,
        )
        liquidity_model = self.cost_model.with_multipliers(spread=2, slippage=2, scenario="liquidity-degradation")
        liquidity = self.run_segment(
            strategy,
            start_index=start_index,
            end_index=end_index,
            cost_model=liquidity_model,
            volume_participation=BASE_VOLUME_PARTICIPATION / Decimal("10"),
        )
        high_vol = regime_analysis.get("HIGH_VOLATILITY", {})
        high_vol_mean = high_vol.get("mean_strategy_return")
        high_vol_fragile = high_vol_mean is not None and Decimal(high_vol_mean) < Decimal("-0.01")
        return (
            ScenarioResult(
                "DELAYED_FILL",
                delayed,
                base.net_return > 0 >= delayed.net_return,
                ("TWO_OBSERVATION_DELAY",),
            ),
            ScenarioResult(
                "MISSING_OBSERVATIONS",
                missing,
                base.net_return > 0 >= missing.net_return,
                ("DROP_EVERY_17TH_TEST_OBSERVATION", "NEXT_AVAILABLE_OBSERVATION_FILL"),
            ),
            ScenarioResult(
                "LIQUIDITY_DEGRADATION",
                liquidity,
                base.net_return > 0 >= liquidity.net_return,
                ("ONE_TENTH_VOLUME_PARTICIPATION", "DOUBLE_SPREAD", "DOUBLE_SLIPPAGE"),
            ),
            ScenarioResult(
                "OBSERVED_VOLATILITY_SPIKE_REGIME",
                base,
                high_vol_fragile,
                ("TRAILING_ONLY_REGIME_LABEL", "NO_SYNTHETIC_SHOCK_INVENTED"),
                details=high_vol,
            ),
        )

    def _empty_result(self) -> SegmentResult:
        return SegmentResult(
            self.bars[0].as_of,
            self.bars[-1].as_of,
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            0,
            Decimal("0"),
            None,
            None,
        )

    def _insufficient_result(self, hypothesis: StrategyHypothesis) -> StrategyQualificationResult:
        empty = self._empty_result()
        walk = WalkForwardResult(
            run_id=f"wf:{hypothesis.evaluation_plan.evaluation_id}",
            strategy_id=hypothesis.strategy_id,
            strategy_version=hypothesis.strategy_version,
            dataset_id=self.dataset.dataset_id,
            dataset_version=self.dataset.dataset_version,
            segments=(),
            trial_count=1,
            cost_model_version=self.cost_model.version,
            fill_model_version=hypothesis.fill_model,
            status="RESEARCH_ONLY",
            limitations=("INSUFFICIENT_DATA",),
        )
        return StrategyQualificationResult(
            strategy_id=hypothesis.strategy_id,
            strategy_version=hypothesis.strategy_version,
            instrument_id=self.dataset.instrument_id,
            selected_config_ref=None,
            train_result=empty,
            validation_result=empty,
            test_result=empty,
            walk_forward_result=walk,
            benchmark_result=BenchmarkResult(hypothesis.benchmark, self.dataset.instrument_id, Decimal("0"), Decimal("0")),
            cost_sensitivity=(),
            stress_results=(),
            regime_analysis={},
            trial_count=0,
            strategy_family_count=MAX_FAMILIES,
            parameter_variant_count=len(hypothesis.parameter_search_space),
            selection_bias_status=SelectionBiasStatus.MULTIPLE_TESTING_LIMITED,
            data_quality=self.dataset.quality_classification,
            dataset_id=self.dataset.dataset_id,
            dataset_version=self.dataset.dataset_version,
            revision_snapshot=self.dataset.revision_snapshot,
            cost_model_version=self.cost_model.version,
            fill_model_version=hypothesis.fill_model,
            seed=0,
            walk_forward_policy="EXPANDING",
            limitations=("INSUFFICIENT_DATA", "MULTIPLE_TESTING_LIMITED"),
            rejection_reasons=(RejectionReason.INSUFFICIENT_DATA,),
            qualification_status=QualificationStatus.RESEARCH_ONLY,
        )

    def qualify(self, hypothesis: StrategyHypothesis) -> StrategyQualificationResult:
        self._validate_hypothesis(hypothesis)
        if len(self.bars) < MINIMUM_QUALIFICATION_BARS:
            return self._insufficient_result(hypothesis)
        train_end, validation_end = self._indices()
        parameters, train, validation = self._ranked_configuration(
            hypothesis,
            train_bounds=(0, train_end),
            validation_bounds=(train_end, validation_end),
        )
        locked = LockedStrategyConfiguration.lock(
            hypothesis.strategy_id,
            hypothesis.strategy_version,
            parameters,
            hypothesis.evaluation_plan.validation_end,
            f"{self.dataset.dataset_id}@{self.dataset.dataset_version}:TRAIN",
            f"{self.dataset.dataset_id}@{self.dataset.dataset_version}:VALIDATION",
            len(hypothesis.parameter_search_space),
            hypothesis.selection_rule,
            self.cost_model.version,
            hypothesis.fill_model,
        )
        self.final_test_ledger.record(
            hypothesis.evaluation_plan.evaluation_id,
            (hypothesis.evaluation_plan.test_start, hypothesis.evaluation_plan.test_end),
            locked.config_hash,
        )
        strategy = RegisteredSpotStrategyRegistry().create(hypothesis.strategy_id, parameters)
        test = self.run_segment(
            strategy,
            start_index=validation_end,
            end_index=len(self.bars),
            cost_model=self.cost_model,
        )
        walk = self._walk_forward(hypothesis)
        sensitivity = self._cost_sensitivity(strategy, validation_end, len(self.bars))
        regime_analysis = self._regime_analysis(test)
        stress = self._stress(strategy, validation_end, len(self.bars), test, regime_analysis)

        reasons: list[RejectionReason] = []
        if test.net_return <= 0 and test.excess_return <= 0:
            reasons.append(RejectionReason.OOS_FAILED)
        if test.gross_return > 0 >= test.net_return or any(item.fragile for item in sensitivity):
            reasons.append(RejectionReason.COSTS_ERASE_EDGE)
        oos_returns = [Decimal(item["oos_result"]["net_return"]) for item in walk.segments]
        if sum(value > 0 for value in oos_returns) < len(oos_returns):
            reasons.append(RejectionReason.WALK_FORWARD_UNSTABLE)
        if test.max_drawdown > Decimal("0.35"):
            reasons.append(RejectionReason.EXCESS_DRAWDOWN)
        if test.trade_count < 3:
            reasons.append(RejectionReason.TOO_FEW_TRADES)
        if test.excess_return < 0:
            reasons.append(RejectionReason.BENCHMARK_UNDERPERFORMANCE)
        if any(item.fragile for item in stress):
            reasons.append(RejectionReason.REGIME_DEPENDENT)
        reasons = list(dict.fromkeys(reasons))

        limitations = [
            *self.dataset.limitations,
            "MULTIPLE_TESTING_LIMITED",
            "FORMAL_STATISTICAL_SIGNIFICANCE_NOT_ASSERTED",
            "NO_ACCOUNT_SPECIFIC_BINANCE_FEE_CLAIM",
        ]
        if not self.dataset.paper_evidence_eligible:
            limitations.append("SYNTHETIC_ONLY_EVIDENCE" if self.dataset.data_mode == "SYNTHETIC" else "DATA_QUALITY_NOT_PROMOTABLE")
            status = QualificationStatus.RESEARCH_ONLY
        else:
            critical = {
                RejectionReason.OOS_FAILED,
                RejectionReason.COSTS_ERASE_EDGE,
                RejectionReason.WALK_FORWARD_UNSTABLE,
                RejectionReason.EXCESS_DRAWDOWN,
                RejectionReason.TOO_FEW_TRADES,
                RejectionReason.REGIME_DEPENDENT,
            }
            failures = critical.intersection(reasons)
            if not failures:
                status = QualificationStatus.PAPER_CANDIDATE
            elif RejectionReason.OOS_FAILED in failures or RejectionReason.EXCESS_DRAWDOWN in failures:
                status = QualificationStatus.REJECTED
            else:
                status = QualificationStatus.OOS_VALIDATED_WITH_LIMITATIONS
        benchmark_drawdown = self._benchmark_drawdown(validation_end, len(self.bars))
        return StrategyQualificationResult(
            strategy_id=hypothesis.strategy_id,
            strategy_version=hypothesis.strategy_version,
            instrument_id=self.dataset.instrument_id,
            selected_config_ref=locked,
            train_result=train,
            validation_result=validation,
            test_result=test,
            walk_forward_result=walk,
            benchmark_result=BenchmarkResult(
                hypothesis.benchmark,
                self.dataset.instrument_id,
                test.benchmark_return,
                benchmark_drawdown,
            ),
            cost_sensitivity=sensitivity,
            stress_results=stress,
            regime_analysis=regime_analysis,
            trial_count=len(hypothesis.parameter_search_space) * (1 + WALK_FORWARD_FOLDS),
            strategy_family_count=MAX_FAMILIES,
            parameter_variant_count=len(hypothesis.parameter_search_space),
            selection_bias_status=SelectionBiasStatus.MULTIPLE_TESTING_LIMITED,
            data_quality=self.dataset.quality_classification,
            dataset_id=self.dataset.dataset_id,
            dataset_version=self.dataset.dataset_version,
            revision_snapshot=self.dataset.revision_snapshot,
            cost_model_version=self.cost_model.version,
            fill_model_version=hypothesis.fill_model,
            seed=0,
            walk_forward_policy="EXPANDING_PRE_FINAL_TEST",
            limitations=tuple(dict.fromkeys(limitations)),
            rejection_reasons=tuple(reasons),
            qualification_status=status,
        )

    def _benchmark_drawdown(self, start_index: int, end_index: int) -> Decimal:
        start = self.bars[start_index].open
        peak = start
        drawdown = Decimal("0")
        for bar in self.bars[start_index:end_index]:
            peak = max(peak, bar.close)
            drawdown = max(drawdown, Decimal("1") - bar.close / peak)
        return _q(drawdown)

    def qualify_all(self) -> QualificationSetResult:
        hypotheses = self.preregistrations()
        if len({item.family for item in hypotheses}) > MAX_FAMILIES:
            raise ValueError("strategy family budget exceeded")
        results = tuple(self.qualify(item) for item in hypotheses)
        return _set_result(results, (self.dataset,))


def _set_result(
    results: Sequence[StrategyQualificationResult],
    datasets: Sequence[CryptoDatasetSnapshot],
) -> QualificationSetResult:
    survivors = sum(item.qualification_status is QualificationStatus.PAPER_CANDIDATE for item in results)
    if survivors:
        outcome = "CRYPTO_STRATEGY_QUALIFICATION_CERTIFIED_WITH_LIMITATIONS"
    elif all(not dataset.paper_evidence_eligible for dataset in datasets):
        outcome = "STRATEGY_RESEARCH_BLOCKED_DATA_QUALITY"
    else:
        outcome = "CRYPTO_STRATEGY_SET_REJECTED_OR_INSUFFICIENT"
    limitations = tuple(
        dict.fromkeys(
            limitation
            for item in results
            for limitation in item.limitations
        )
    )
    return QualificationSetResult(
        results=tuple(results),
        certification_outcome=outcome,
        survivor_count=survivors,
        family_count=len({item.strategy_id for item in results}),
        instrument_count=len({item.instrument_id for item in results}),
        total_trial_count=sum(item.trial_count for item in results),
        limitations=limitations,
    )


def qualify_crypto_universe(
    inputs: Mapping[str, tuple[CryptoDatasetSnapshot, Iterable[HistoricalBar]]],
    *,
    cost_model: CryptoCostModel | None = None,
) -> QualificationSetResult:
    if set(inputs) - set(CANONICAL_CRYPTO_INSTRUMENTS):
        raise ValueError("unregistered crypto spot instrument")
    results = []
    datasets = []
    for instrument_id in CANONICAL_CRYPTO_INSTRUMENTS:
        if instrument_id not in inputs:
            continue
        dataset, bars = inputs[instrument_id]
        if dataset.instrument_id != instrument_id:
            raise ValueError("dataset key and instrument identity disagree")
        runner = CryptoQualificationRunner(dataset, bars, cost_model=cost_model)
        results.extend(runner.qualify_all().results)
        datasets.append(dataset)
    if not results:
        raise ValueError("at least one canonical BTC/ETH dataset is required")
    return _set_result(results, datasets)


def build_public_binance_snapshot(
    instrument_id: str,
    adjusted_bars: Iterable[Any],
    *,
    retrieved_at: datetime,
    timeframe: str = "1d",
) -> tuple[CryptoDatasetSnapshot, tuple[HistoricalBar, ...]]:
    """Adapt credential-free Binance public klines into the PIT boundary.

    The existing adapter timestamps rows at interval open. Only fully closed
    daily observations are admitted. Binance's latest-only endpoint does not
    provide correction history, so that limitation is permanent in the returned
    snapshot and must propagate into qualification evidence.
    """

    if instrument_id not in CANONICAL_CRYPTO_INSTRUMENTS:
        raise ValueError("unsupported canonical spot instrument")
    _aware(retrieved_at, name="retrieved_at")
    if timeframe != "1d":
        raise ValueError("initial qualification supports daily spot bars only")
    rows = []
    for source in adjusted_bars:
        opened_at = datetime.fromtimestamp(float(source.ts), tz=timezone.utc)
        as_of = opened_at + timedelta(days=1)
        if as_of > retrieved_at:
            continue
        values = (
            str(source.open),
            str(source.high),
            str(source.low),
            str(source.close),
            str(source.volume),
        )
        source_record_id = f"{instrument_id}:1d:{opened_at.isoformat()}"
        revision_id = hashlib.sha256("|".join((source_record_id, *values)).encode()).hexdigest()
        rows.append(
            HistoricalBar(
                instrument_id=instrument_id,
                venue="BINANCE",
                asset_class=AssetClass.CRYPTO,
                currency="USDT",
                point_in_time=PointInTime(
                    event_timestamp=opened_at,
                    as_of=as_of,
                    available_at=as_of,
                    received_at=retrieved_at,
                ),
                provider=ProviderReference(
                    provider="BINANCE_PUBLIC_API_V3_KLINES",
                    provider_event_id=source_record_id,
                    source_ref="/api/v3/klines",
                    is_delayed=True,
                    delay_seconds=int((retrieved_at - as_of).total_seconds()),
                ),
                quality=DataQuality.VALID,
                source_record_id=source_record_id,
                revision_id=revision_id,
                open=_d(source.open, name="open"),
                high=_d(source.high, name="high"),
                low=_d(source.low, name="low"),
                close=_d(source.close, name="close"),
                volume=_d(source.volume, name="volume"),
            )
        )
    rows.sort(key=lambda row: row.as_of)
    immutable_rows = tuple(rows)
    if not immutable_rows:
        raise ValueError("no fully closed public bars")
    content_hash = dataset_content_hash(immutable_rows)
    compact_symbol = instrument_id.split(":", 1)[1].replace("/", "")
    dataset = CryptoDatasetSnapshot(
        dataset_id=f"binance-public:{compact_symbol}:1d",
        dataset_version=f"sha256:{content_hash}",
        instrument_id=instrument_id,
        data_mode="HISTORICAL",
        source="BINANCE_PUBLIC_API_V3_KLINES",
        quality_classification="REAL_PUBLIC_HISTORICAL_REVISION_SNAPSHOT",
        revision_snapshot=f"retrieved:{retrieved_at.isoformat()}",
        revision_cutoff=retrieved_at,
        content_hash=content_hash,
        limitations=(
            "LEGACY_LATEST_ONLY_DATASET",
            "DATASET_CORRECTION_HISTORY_UNAVAILABLE",
            "PUBLIC_NOT_ACCOUNT_SPECIFIC",
        ),
    )
    return dataset, immutable_rows


def dataset_content_hash(bars: Iterable[HistoricalBar]) -> str:
    return canonical_historical_hash(bars)


def qualification_inputs_from_certification(
    certification: DatasetCertification,
) -> dict[str, tuple[CryptoDatasetSnapshot, tuple[HistoricalBar, ...]]]:
    """Bind a certified immutable dataset to the frozen strategy experiment.

    This bridge performs no selection or return calculation.  It only creates
    the per-instrument PIT snapshots required by the existing qualification
    runner, preserving the certified content and source revision hashes.
    """

    if certification.quality_status is not DatasetQualityStatus.CERTIFIED_REAL_HISTORICAL:
        raise ValueError("strategy qualification requires a certified real historical dataset")
    if certification.data_mode != "HISTORICAL":
        raise ValueError("strategy qualification requires HISTORICAL data mode")
    if certification.performance_evaluations or certification.test_periods_spent:
        raise ValueError("dataset acquisition must not spend strategy evaluation periods")
    inputs: dict[str, tuple[CryptoDatasetSnapshot, tuple[HistoricalBar, ...]]] = {}
    for instrument_id in CANONICAL_CRYPTO_INSTRUMENTS:
        rows = tuple(bar for bar in certification.bars if bar.instrument_id == instrument_id)
        if not rows:
            continue
        revision_cutoff = max(bar.received_at for bar in rows)
        snapshot = CryptoDatasetSnapshot(
            dataset_id=certification.dataset_id,
            dataset_version=certification.dataset_version,
            instrument_id=instrument_id,
            data_mode="HISTORICAL",
            source="BINANCE_OFFICIAL_PUBLIC_DATA_ARCHIVE",
            quality_classification="REAL_PUBLIC_HISTORICAL_REVISION_SNAPSHOT",
            revision_snapshot=certification.source_revision_checksum,
            revision_cutoff=revision_cutoff,
            content_hash=dataset_content_hash(rows),
            limitations=certification.limitations,
        )
        inputs[instrument_id] = (snapshot, rows)
    if not inputs:
        raise ValueError("certification contains no canonical BTC/ETH observations")
    return inputs
