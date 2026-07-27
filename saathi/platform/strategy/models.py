"""M62.4 — canonical strategy + backtesting domain models.

Deterministic, decimal-precise, simulation-only. Reuses the M62.1 trading domain
(`saathi.platform.trading_models`: ``D``, ``AssetClass``) and the M62.2 market-data
layer (``Timeframe``). Grants NO execution authority: nothing here submits an
order, opens a broker connection, consumes an approval, or reaches ExecutionGateway.
A ``SimulatedOrder`` / ``SimulatedPortfolio`` lives entirely inside an isolated
backtest domain and never becomes a platform ``OrderIntent``.

Strategies are DECLARATIVE (feature specs + signal rules + a sizing rule). There
is no arbitrary-code path: a strategy cannot import, eval, fetch, or read the
filesystem. This is a structural safety property, not a runtime check.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from enum import Enum
from typing import Any

from saathi.platform.trading_models import D, AssetClass
from saathi.platform.market_data.models import Timeframe


ENGINE_VERSION = "m62_4.engine.v1"
FEATURE_VERSION = "m62_4.features.v1"


# ── enums ─────────────────────────────────────────────────────────────────────
class StrategyType(str, Enum):
    MOMENTUM = "MOMENTUM"
    MEAN_REVERSION = "MEAN_REVERSION"
    BREAKOUT = "BREAKOUT"
    THRESHOLD = "THRESHOLD"
    BUY_AND_HOLD = "BUY_AND_HOLD"


class StrategyStatus(str, Enum):
    DRAFT = "DRAFT"
    RESEARCH_LINKED = "RESEARCH_LINKED"
    DATA_VALIDATED = "DATA_VALIDATED"
    BACKTESTING = "BACKTESTING"
    BACKTEST_COMPLETE = "BACKTEST_COMPLETE"
    VALIDATION_REQUIRED = "VALIDATION_REQUIRED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


# Explicit lifecycle transitions. No jump DRAFT -> VALIDATED. "Validated" is a
# technical/statistical verdict, NOT a claim of profitability.
STRATEGY_TRANSITIONS: dict[StrategyStatus, frozenset[StrategyStatus]] = {
    StrategyStatus.DRAFT: frozenset({StrategyStatus.RESEARCH_LINKED, StrategyStatus.DATA_VALIDATED, StrategyStatus.REJECTED}),
    StrategyStatus.RESEARCH_LINKED: frozenset({StrategyStatus.DATA_VALIDATED, StrategyStatus.REJECTED}),
    StrategyStatus.DATA_VALIDATED: frozenset({StrategyStatus.BACKTESTING, StrategyStatus.REJECTED}),
    StrategyStatus.BACKTESTING: frozenset({StrategyStatus.BACKTEST_COMPLETE, StrategyStatus.REJECTED}),
    StrategyStatus.BACKTEST_COMPLETE: frozenset({StrategyStatus.VALIDATION_REQUIRED, StrategyStatus.REJECTED}),
    StrategyStatus.VALIDATION_REQUIRED: frozenset({StrategyStatus.VALIDATED, StrategyStatus.REJECTED}),
    StrategyStatus.VALIDATED: frozenset({StrategyStatus.SUPERSEDED, StrategyStatus.EXPIRED}),
    StrategyStatus.REJECTED: frozenset(),
    StrategyStatus.SUPERSEDED: frozenset(),
    StrategyStatus.EXPIRED: frozenset(),
}


def can_strategy_transition(cur: StrategyStatus | str, target: StrategyStatus | str) -> bool:
    c = StrategyStatus(cur) if not isinstance(cur, StrategyStatus) else cur
    t = StrategyStatus(target) if not isinstance(target, StrategyStatus) else target
    return t in STRATEGY_TRANSITIONS.get(c, frozenset())


class BacktestStatus(str, Enum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    VALIDATING_DATA = "VALIDATING_DATA"
    GENERATING_FEATURES = "GENERATING_FEATURES"
    RUNNING = "RUNNING"
    CALCULATING_METRICS = "CALCULATING_METRICS"
    RUNNING_STRESS_TESTS = "RUNNING_STRESS_TESTS"
    RUNNING_SENSITIVITY = "RUNNING_SENSITIVITY"
    VALIDATION_REQUIRED = "VALIDATION_REQUIRED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


BACKTEST_TERMINAL = frozenset({BacktestStatus.COMPLETE, BacktestStatus.FAILED,
                               BacktestStatus.CANCELLED, BacktestStatus.REJECTED})

BACKTEST_TRANSITIONS: dict[BacktestStatus, frozenset[BacktestStatus]] = {
    BacktestStatus.DRAFT: frozenset({BacktestStatus.QUEUED, BacktestStatus.CANCELLED}),
    BacktestStatus.QUEUED: frozenset({BacktestStatus.VALIDATING_DATA, BacktestStatus.CANCELLED, BacktestStatus.FAILED}),
    BacktestStatus.VALIDATING_DATA: frozenset({BacktestStatus.GENERATING_FEATURES, BacktestStatus.FAILED, BacktestStatus.REJECTED, BacktestStatus.CANCELLED}),
    BacktestStatus.GENERATING_FEATURES: frozenset({BacktestStatus.RUNNING, BacktestStatus.FAILED, BacktestStatus.REJECTED, BacktestStatus.CANCELLED}),
    BacktestStatus.RUNNING: frozenset({BacktestStatus.CALCULATING_METRICS, BacktestStatus.FAILED, BacktestStatus.CANCELLED}),
    BacktestStatus.CALCULATING_METRICS: frozenset({BacktestStatus.RUNNING_STRESS_TESTS, BacktestStatus.FAILED, BacktestStatus.CANCELLED}),
    BacktestStatus.RUNNING_STRESS_TESTS: frozenset({BacktestStatus.RUNNING_SENSITIVITY, BacktestStatus.FAILED, BacktestStatus.CANCELLED}),
    BacktestStatus.RUNNING_SENSITIVITY: frozenset({BacktestStatus.VALIDATION_REQUIRED, BacktestStatus.FAILED, BacktestStatus.CANCELLED}),
    BacktestStatus.VALIDATION_REQUIRED: frozenset({BacktestStatus.COMPLETE, BacktestStatus.FAILED, BacktestStatus.CANCELLED}),
    BacktestStatus.COMPLETE: frozenset(),
    BacktestStatus.FAILED: frozenset(),
    BacktestStatus.CANCELLED: frozenset(),
    BacktestStatus.REJECTED: frozenset(),
}


def can_backtest_transition(cur: BacktestStatus | str, target: BacktestStatus | str) -> bool:
    c = BacktestStatus(cur) if not isinstance(cur, BacktestStatus) else cur
    t = BacktestStatus(target) if not isinstance(target, BacktestStatus) else target
    return t in BACKTEST_TRANSITIONS.get(c, frozenset())


class FeatureKind(str, Enum):
    RETURN = "RETURN"                 # simple return over lookback
    SMA = "SMA"                       # simple moving average of close
    VOLATILITY = "VOLATILITY"         # rolling stddev of returns
    ROLLING_HIGH = "ROLLING_HIGH"
    ROLLING_LOW = "ROLLING_LOW"
    VOLUME_AVG = "VOLUME_AVG"
    PRICE_DEVIATION = "PRICE_DEVIATION"   # (close - sma) / sma
    MOMENTUM = "MOMENTUM"             # close - close[lookback]


class Comparator(str, Enum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    CROSS_ABOVE = "CROSS_ABOVE"       # feature crosses above ref this bar
    CROSS_BELOW = "CROSS_BELOW"


class SignalAction(str, Enum):
    ENTER_LONG = "ENTER_LONG"
    EXIT = "EXIT"


class SizingMethod(str, Enum):
    FIXED_QUANTITY = "FIXED_QUANTITY"
    EQUITY_FRACTION = "EQUITY_FRACTION"   # fraction of current equity, in [0,1]


class SplitKind(str, Enum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


class LotMethod(str, Enum):
    AVERAGE_COST = "AVERAGE_COST"


# ── declarative specs ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FeatureSpec:
    """A time-aware feature. ``lookback`` is the number of PAST bars used, ending
    at (and including) the decision bar. ``forward_offset`` MUST be 0 — any positive
    value denotes future-data access and is rejected by validation (look-ahead).
    """
    name: str
    kind: FeatureKind
    lookback: int = 1
    forward_offset: int = 0           # >0 == look-ahead == illegal
    source: str = "close"             # close|open|high|low|volume

    def to_public(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind.value, "lookback": self.lookback,
                "forward_offset": self.forward_offset, "source": self.source}


@dataclass(frozen=True)
class SignalRule:
    """When ``left`` (feature name) compares against ``right`` (a feature name or a
    numeric constant), emit ``action``. Purely declarative."""
    left: str
    comparator: Comparator
    right: str                        # feature name OR numeric literal (as str)
    action: SignalAction

    def right_is_feature(self, feature_names: frozenset[str]) -> bool:
        return self.right in feature_names

    def to_public(self) -> dict[str, Any]:
        return {"left": self.left, "comparator": self.comparator.value,
                "right": self.right, "action": self.action.value}


@dataclass(frozen=True)
class SizingRule:
    method: SizingMethod
    value: Decimal = field(default_factory=lambda: Decimal("1"))
    max_position_fraction: Decimal = field(default_factory=lambda: Decimal("1"))  # <=1: no leverage

    def to_public(self) -> dict[str, Any]:
        return {"method": self.method.value, "value": str(self.value),
                "max_position_fraction": str(self.max_position_fraction)}


@dataclass(frozen=True)
class CostModel:
    """All fields Decimal. bps = basis points (1bp = 0.01%)."""
    fixed_fee: Decimal = field(default_factory=lambda: Decimal("0"))
    pct_fee: Decimal = field(default_factory=lambda: Decimal("0"))        # fraction, e.g. 0.001 = 10bp
    per_unit_fee: Decimal = field(default_factory=lambda: Decimal("0"))
    min_fee: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage_bps: Decimal = field(default_factory=lambda: Decimal("0"))   # fixed slippage
    spread_slippage: bool = False                                          # add half-spread proxy
    max_volume_participation: Decimal = field(default_factory=lambda: Decimal("1"))  # cap qty vs bar volume

    def to_public(self) -> dict[str, Any]:
        return {"fixed_fee": str(self.fixed_fee), "pct_fee": str(self.pct_fee),
                "per_unit_fee": str(self.per_unit_fee), "min_fee": str(self.min_fee),
                "slippage_bps": str(self.slippage_bps), "spread_slippage": self.spread_slippage,
                "max_volume_participation": str(self.max_volume_participation)}


ZERO_COST = CostModel()
REALISTIC_COST = CostModel(pct_fee=Decimal("0.0005"), min_fee=Decimal("1"), slippage_bps=Decimal("5"),
                           max_volume_participation=Decimal("0.1"))
STRESSED_COST = CostModel(pct_fee=Decimal("0.003"), min_fee=Decimal("2"), slippage_bps=Decimal("50"),
                          max_volume_participation=Decimal("0.05"))


@dataclass
class ThesisReference:
    """Read-only reference to an M62.3 research thesis. Records the version + its
    publication/expiry so a strategy can NEVER treat unpublished/expired research
    as authoritative. Research is never market data."""
    project_id: str
    thesis_version: int
    published: bool = False
    expired: bool = False
    authoritative: bool = False       # only published & not-expired counts
    relevant_claims: list[str] = field(default_factory=list)
    confidence_score: float = 0.0
    note: str = ""

    def to_public(self) -> dict[str, Any]:
        return {"project_id": self.project_id, "thesis_version": self.thesis_version,
                "published": self.published, "expired": self.expired,
                "authoritative": self.authoritative, "relevant_claims": list(self.relevant_claims),
                "confidence_score": self.confidence_score, "note": self.note}


# ── strategy definition + immutable version ──────────────────────────────────
@dataclass
class StrategyDefinition:
    id: str
    org_id: str
    workspace_id: str
    name: str
    strategy_type: StrategyType
    instrument_universe: list[str]
    timeframe: Timeframe
    features: list[FeatureSpec]
    signals: list[SignalRule]
    sizing: SizingRule
    description: str = ""
    benchmark: str = ""               # instrument symbol used as benchmark
    cost_model: CostModel = field(default_factory=lambda: REALISTIC_COST)
    warmup_bars: int = 0              # bars skipped before signals allowed
    risk_max_position_fraction: Decimal = field(default_factory=lambda: Decimal("1"))
    thesis_refs: list[ThesisReference] = field(default_factory=list)
    status: StrategyStatus = StrategyStatus.DRAFT
    created_by: str = ""
    version: int = 1                  # optimistic-concurrency counter on the mutable def

    @property
    def feature_names(self) -> frozenset[str]:
        return frozenset(f.name for f in self.features)

    def required_warmup(self) -> int:
        return max([self.warmup_bars] + [f.lookback for f in self.features] + [1])

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id, "org_id": self.org_id, "workspace_id": self.workspace_id,
            "name": self.name, "description": self.description, "strategy_type": self.strategy_type.value,
            "instrument_universe": list(self.instrument_universe), "timeframe": self.timeframe.value,
            "features": [f.to_public() for f in self.features], "signals": [s.to_public() for s in self.signals],
            "sizing": self.sizing.to_public(), "benchmark": self.benchmark,
            "cost_model": self.cost_model.to_public(), "warmup_bars": self.warmup_bars,
            "risk_max_position_fraction": str(self.risk_max_position_fraction),
            "thesis_refs": [t.to_public() for t in self.thesis_refs], "status": self.status.value,
            "created_by": self.created_by, "version": self.version,
        }

    def config_snapshot(self) -> dict[str, Any]:
        """Deterministic, hashable snapshot of the STRATEGY LOGIC (not identity)."""
        return {
            "strategy_type": self.strategy_type.value, "timeframe": self.timeframe.value,
            "features": sorted([f.to_public() for f in self.features], key=lambda d: d["name"]),
            "signals": [s.to_public() for s in self.signals], "sizing": self.sizing.to_public(),
            "cost_model": self.cost_model.to_public(), "warmup_bars": self.warmup_bars,
            "risk_max_position_fraction": str(self.risk_max_position_fraction),
            "instrument_universe": sorted(self.instrument_universe), "benchmark": self.benchmark,
        }


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def strategy_hash(defn: StrategyDefinition, parameters: dict[str, Any] | None = None) -> str:
    payload = {"config": defn.config_snapshot(), "parameters": parameters or {}}
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()


@dataclass
class StrategyVersion:
    """Immutable snapshot of a strategy definition + parameter set. Once created it
    is never mutated; a change is a NEW version with a parent link + rationale."""
    strategy_id: str
    version: int
    org_id: str
    config_snapshot: dict[str, Any]
    parameters: dict[str, Any]
    code_hash: str
    dataset_requirements: dict[str, Any]
    parent_version: int | None = None
    change_rationale: str = ""
    created_by: str = ""
    created_at: float = 0.0
    validation_state: str = "UNVALIDATED"

    def to_public(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id, "version": self.version, "code_hash": self.code_hash,
            "config_snapshot": self.config_snapshot, "parameters": self.parameters,
            "dataset_requirements": self.dataset_requirements, "parent_version": self.parent_version,
            "change_rationale": self.change_rationale, "created_by": self.created_by,
            "created_at": self.created_at, "validation_state": self.validation_state,
        }


# ── dataset reference ─────────────────────────────────────────────────────────
@dataclass
class DatasetReference:
    provider: str
    dataset_version: str
    instrument: str
    timeframe: Timeframe
    start_epoch: float
    end_epoch: float
    content_hash: str
    source: str = "fixture"           # fixture|stored
    calendar: str = "DEFAULT_24_5"
    quality_summary: dict[str, Any] = field(default_factory=dict)
    bar_count: int = 0

    def to_public(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "dataset_version": self.dataset_version, "instrument": self.instrument,
            "timeframe": self.timeframe.value, "start_epoch": self.start_epoch, "end_epoch": self.end_epoch,
            "content_hash": self.content_hash, "source": self.source, "calendar": self.calendar,
            "quality_summary": self.quality_summary, "bar_count": self.bar_count,
        }


# ── simulated execution artifacts (isolated backtest domain) ─────────────────
class SimOrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


@dataclass
class SimulatedOrder:
    seq: int
    decision_epoch: float             # bar ts that generated the intent
    fill_epoch: float                 # bar ts where it filled (>= decision, conservative)
    instrument: str
    side: str                         # BUY | SELL
    order_type: str                   # MARKET | LIMIT
    quantity: Decimal
    reference_price: Decimal
    fill_price: Decimal
    fees: Decimal
    slippage: Decimal
    status: SimOrderStatus
    signal_ref: str = ""
    reject_reason: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "seq": self.seq, "decision_epoch": self.decision_epoch, "fill_epoch": self.fill_epoch,
            "instrument": self.instrument, "side": self.side, "order_type": self.order_type,
            "quantity": str(self.quantity), "reference_price": str(self.reference_price),
            "fill_price": str(self.fill_price), "fees": str(self.fees), "slippage": str(self.slippage),
            "status": self.status.value, "signal_ref": self.signal_ref, "reject_reason": self.reject_reason,
        }


@dataclass
class SimPosition:
    instrument: str
    quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    avg_cost: Decimal = field(default_factory=lambda: Decimal("0"))
    realized_pnl: Decimal = field(default_factory=lambda: Decimal("0"))

    def market_value(self, mark: Decimal) -> Decimal:
        return (self.quantity * mark)

    def unrealized_pnl(self, mark: Decimal) -> Decimal:
        return ((mark - self.avg_cost) * self.quantity)


@dataclass
class EquityPoint:
    epoch: float
    equity: Decimal
    cash: Decimal
    positions_value: Decimal
    drawdown: Decimal

    def to_public(self) -> dict[str, Any]:
        return {"epoch": self.epoch, "equity": str(self.equity), "cash": str(self.cash),
                "positions_value": str(self.positions_value), "drawdown": str(self.drawdown)}


Q2 = Decimal("0.01")


def q2(x: Decimal) -> Decimal:
    return D(x).quantize(Q2)
