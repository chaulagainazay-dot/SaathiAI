"""STRATEGY-MONITORING-1 — continuous strategy health against a frozen envelope.

WHAT ALREADY EXISTED, AND WHY THIS IS NOT THAT:

  OperationalMonitor._component_strategy counts how many activations are running.
  That is OPERATIONAL health — "are the workers up?" — not "is the strategy
  behaving the way it was qualified to behave?".

  GraduationEngine decides a campaign's terminal classification once it is
  COMPLETED or ARCHIVED. That is an end-of-run verdict and the promotion
  authority; it says nothing while a run is in flight.

Neither answers "is this strategy still inside its operating envelope, right
now?". That is the gap, and this module fills only that gap. It reuses the
canonical HealthClass taxonomy rather than inventing a second one, and it maps
its own states onto it so OperationalMonitor can keep aggregating with `_worst`.

AUTHORITY: none. This module classifies and explains. It cannot size, retune,
promote, demote, suspend, submit, approve or reserve. Every threshold is read
from a VERSIONED policy fixed before evaluation — a monitor that can move its own
goalposts after seeing the result is not measuring anything.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.trading_models import D

MONITOR_POLICY_VERSION = "strategy-monitor/v1.0.0"
CALCULATION_VERSION = "strategy-monitor-calc/v1.0.0"


class StrategyHealth(str, Enum):
    """Strategy-behaviour health. Distinct from operational HealthClass.

    INSUFFICIENT_EVIDENCE and DATA_QUALITY_BLOCKED are deliberately NOT failures:
    the first says we have not watched long enough to have an opinion, the second
    says the observation itself is untrustworthy. Collapsing either into DEGRADED
    would blame the strategy for our own blindness.
    """

    NORMAL = "NORMAL"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DATA_QUALITY_BLOCKED = "DATA_QUALITY_BLOCKED"


#: Bridge to the canonical operational taxonomy, so this never becomes a second
#: health vocabulary that OperationalMonitor has to learn.
HEALTH_CLASS_OF = {
    StrategyHealth.NORMAL: HealthClass.HEALTHY,
    StrategyHealth.WATCH: HealthClass.WARNING,
    StrategyHealth.DEGRADED: HealthClass.DEGRADED,
    # Not knowing is a warning about our evidence, never a claim about the strategy.
    StrategyHealth.INSUFFICIENT_EVIDENCE: HealthClass.WARNING,
    StrategyHealth.DATA_QUALITY_BLOCKED: HealthClass.WARNING,
}


class Dimension(str, Enum):
    OBSERVATION = "OBSERVATION_SUFFICIENCY"
    DRAWDOWN = "DRAWDOWN"
    BENCHMARK = "BENCHMARK_RELATIVE"
    COST = "COST_DRAG"
    TURNOVER = "TURNOVER"
    SIGNAL = "SIGNAL_BEHAVIOUR"
    REGIME = "REGIME_COMPATIBILITY"
    DATA_QUALITY = "DATA_QUALITY"
    RECONCILIATION = "RECONCILIATION"


class Reason(str, Enum):
    OBSERVATION_INSUFFICIENT = "OBSERVATION_INSUFFICIENT"
    DRAWDOWN_WATCH = "DRAWDOWN_WATCH"
    DRAWDOWN_DEGRADED = "DRAWDOWN_DEGRADED"
    BENCHMARK_UNDERPERFORMANCE = "BENCHMARK_UNDERPERFORMANCE"
    BENCHMARK_UNAVAILABLE = "BENCHMARK_UNAVAILABLE"
    COST_ASSUMPTION_BREACH = "COST_ASSUMPTION_BREACH"
    COST_DETAIL_UNAVAILABLE = "COST_DETAIL_UNAVAILABLE"
    TURNOVER_INFLATION = "TURNOVER_INFLATION"
    TURNOVER_UNAVAILABLE = "TURNOVER_UNAVAILABLE"
    SIGNAL_SPARSE = "SIGNAL_SPARSE"
    REGIME_MISMATCH = "REGIME_MISMATCH"
    REGIME_UNKNOWN = "REGIME_UNKNOWN"
    DATA_STALE = "DATA_STALE"
    DATA_GAP = "DATA_GAP"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    ATTRIBUTION_UNAVAILABLE = "ATTRIBUTION_UNAVAILABLE"
    RECOVERY_OBSERVED = "RECOVERY_OBSERVED"


@dataclass(frozen=True)
class MonitorPolicy:
    """Thresholds fixed BEFORE evaluation and versioned.

    Derived from qualification evidence and paper-activation policy, never chosen
    after seeing a result. `version` travels with every verdict so a number can
    always be traced to the rule that produced it.
    """

    version: str = MONITOR_POLICY_VERSION
    # Observation sufficiency — dominates every performance conclusion.
    min_closed_trades: int = 20
    min_observation_seconds: int = 7 * 24 * 3600
    min_regimes_seen: int = 1
    # Drawdown bands, as positive fractions of peak equity.
    drawdown_watch: Decimal = Decimal("0.10")
    drawdown_degraded: Decimal = Decimal("0.20")
    # Benchmark: how far below, over how many closed trades, before it counts.
    benchmark_underperformance: Decimal = Decimal("0.05")
    benchmark_min_trades: int = 20
    # Realized cost drag versus the assumption used at qualification.
    cost_overrun_ratio: Decimal = Decimal("1.50")
    # Turnover envelope, as a multiple of the qualified turnover.
    turnover_inflation_ratio: Decimal = Decimal("2.00")
    # Hysteresis: a recovering strategy must clear the band by this margin before
    # it is allowed to improve, so a value sitting on a threshold cannot flap.
    hysteresis: Decimal = Decimal("0.02")

    def fingerprint(self) -> str:
        blob = json.dumps(
            {k: str(v) for k, v in sorted(self.__dict__.items())}, sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class QualificationEnvelope:
    """What the strategy was qualified to do. Frozen at qualification time.

    Monitoring compares observation against THIS, never against a number derived
    from the observation itself — that would be marking your own homework.
    """

    strategy_id: str
    strategy_version: str
    qualification_sha: str
    benchmark_version: str
    qualified_max_drawdown: Decimal | None = None
    assumed_cost_drag: Decimal | None = None
    qualified_turnover: Decimal | None = None
    qualified_regimes: tuple = ()
    expected_trades_per_week: Decimal | None = None


@dataclass(frozen=True)
class Observation:
    """What actually happened, from canonical records only.

    Every field is optional because the honest answer to "what was the cost drag?"
    is sometimes "we do not know", and that must be representable.
    """

    mode: str = "SHADOW"
    window_start: str | None = None
    window_end: str | None = None
    observed_seconds: int = 0
    closed_trades: int = 0
    signals: int = 0
    max_drawdown: Decimal | None = None
    net_return: Decimal | None = None
    benchmark_return: Decimal | None = None
    cost_drag: Decimal | None = None
    cost_detail_available: bool = False
    turnover_ratio: Decimal | None = None
    regimes_seen: tuple = ()
    current_regime: str | None = None
    data_stale: bool = False
    data_gap: bool = False
    reconciliation_ok: bool = True
    attribution_report_id: str | None = None


@dataclass(frozen=True)
class DimensionVerdict:
    dimension: str
    health: str
    reasons: tuple = ()
    observed: Decimal | None = None
    threshold: Decimal | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MonitorVerdict:
    strategy_id: str
    strategy_version: str
    health: str
    health_class: str
    reasons: tuple
    dimensions: tuple
    policy_version: str
    policy_fingerprint: str
    calculation_version: str
    mode: str
    window_start: str | None
    window_end: str | None
    previous_health: str | None
    transitioned: bool
    verdict_id: str
    #: Permanent, asserted by tests: monitoring observes, it never acts.
    authorizes_execution: bool = field(default=False, init=False)
    mutates_parameters: bool = field(default=False, init=False)

    def to_public(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "health": self.health,
            "health_class": self.health_class,
            "reasons": list(self.reasons),
            "dimensions": [d.__dict__ for d in self.dimensions],
            "policy_version": self.policy_version,
            "policy_fingerprint": self.policy_fingerprint,
            "calculation_version": self.calculation_version,
            "mode": self.mode,
            "window": {"start": self.window_start, "end": self.window_end},
            "previous_health": self.previous_health,
            "transitioned": self.transitioned,
            "verdict_id": self.verdict_id,
            "authorizes_execution": False,
            "mutates_parameters": False,
        }


_SEVERITY = {
    StrategyHealth.NORMAL.value: 0,
    StrategyHealth.INSUFFICIENT_EVIDENCE.value: 1,
    StrategyHealth.DATA_QUALITY_BLOCKED.value: 1,
    StrategyHealth.WATCH.value: 2,
    StrategyHealth.DEGRADED.value: 3,
}


def _worst(*healths: str) -> str:
    return max(healths, key=lambda h: _SEVERITY.get(h, 0))


# ── dimension evaluators ────────────────────────────────────────────────────

def evaluate_observation(obs: Observation, policy: MonitorPolicy) -> DimensionVerdict:
    """Have we watched long enough to have an opinion at all?

    This dominates every performance dimension. A strategy is not NORMAL because
    it made two trades and neither lost money.
    """
    reasons = []
    if obs.closed_trades < policy.min_closed_trades:
        reasons.append(Reason.OBSERVATION_INSUFFICIENT.value)
    if obs.observed_seconds < policy.min_observation_seconds:
        reasons.append(Reason.OBSERVATION_INSUFFICIENT.value)
    if len(obs.regimes_seen) < policy.min_regimes_seen:
        reasons.append(Reason.OBSERVATION_INSUFFICIENT.value)
    health = StrategyHealth.INSUFFICIENT_EVIDENCE.value if reasons else StrategyHealth.NORMAL.value
    return DimensionVerdict(
        Dimension.OBSERVATION.value, health, tuple(dict.fromkeys(reasons)),
        observed=Decimal(obs.closed_trades), threshold=Decimal(policy.min_closed_trades),
        detail=f"{obs.closed_trades} closed trades over {obs.observed_seconds}s",
    )


def evaluate_drawdown(obs: Observation, policy: MonitorPolicy, previous: str | None = None) -> DimensionVerdict:
    """Drawdown against pre-declared bands, with hysteresis on the way back.

    A value parked on a threshold would otherwise flap NORMAL/WATCH forever, so
    improving requires clearing the band by an explicit margin.
    """
    if obs.max_drawdown is None:
        return DimensionVerdict(Dimension.DRAWDOWN.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.ATTRIBUTION_UNAVAILABLE.value,),
                                detail="no drawdown observed")
    dd = D(obs.max_drawdown)
    watch, degraded = policy.drawdown_watch, policy.drawdown_degraded
    h = policy.hysteresis

    if dd >= degraded:
        return DimensionVerdict(Dimension.DRAWDOWN.value, StrategyHealth.DEGRADED.value,
                                (Reason.DRAWDOWN_DEGRADED.value,), dd, degraded)
    if dd >= watch:
        return DimensionVerdict(Dimension.DRAWDOWN.value, StrategyHealth.WATCH.value,
                                (Reason.DRAWDOWN_WATCH.value,), dd, watch)

    # Below watch. If we were worse before, require clearing by the hysteresis
    # margin before improving.
    if previous in (StrategyHealth.WATCH.value, StrategyHealth.DEGRADED.value) and dd > watch - h:
        return DimensionVerdict(Dimension.DRAWDOWN.value, StrategyHealth.WATCH.value,
                                (Reason.DRAWDOWN_WATCH.value,), dd, watch,
                                detail="within hysteresis band of the watch threshold")
    reasons = (Reason.RECOVERY_OBSERVED.value,) if previous in (
        StrategyHealth.WATCH.value, StrategyHealth.DEGRADED.value) else ()
    return DimensionVerdict(Dimension.DRAWDOWN.value, StrategyHealth.NORMAL.value, reasons, dd, watch)


def evaluate_benchmark(obs: Observation, policy: MonitorPolicy) -> DimensionVerdict:
    """Relative performance, but only once there is enough of it to mean anything."""
    if obs.benchmark_return is None or obs.net_return is None:
        return DimensionVerdict(Dimension.BENCHMARK.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.BENCHMARK_UNAVAILABLE.value,))
    if obs.closed_trades < policy.benchmark_min_trades:
        return DimensionVerdict(Dimension.BENCHMARK.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.OBSERVATION_INSUFFICIENT.value,),
                                detail="too few closed trades to judge relative performance")
    excess = D(obs.net_return) - D(obs.benchmark_return)
    if -excess >= policy.benchmark_underperformance:
        return DimensionVerdict(Dimension.BENCHMARK.value, StrategyHealth.WATCH.value,
                                (Reason.BENCHMARK_UNDERPERFORMANCE.value,),
                                excess, -policy.benchmark_underperformance)
    return DimensionVerdict(Dimension.BENCHMARK.value, StrategyHealth.NORMAL.value, (), excess,
                            -policy.benchmark_underperformance)


def evaluate_cost(obs: Observation, envelope: QualificationEnvelope, policy: MonitorPolicy) -> DimensionVerdict:
    """Realized cost drag against the assumption used at qualification."""
    if obs.cost_drag is None or envelope.assumed_cost_drag is None:
        return DimensionVerdict(Dimension.COST.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.COST_DETAIL_UNAVAILABLE.value,))
    assumed = D(envelope.assumed_cost_drag)
    if assumed <= 0:
        return DimensionVerdict(Dimension.COST.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.COST_DETAIL_UNAVAILABLE.value,),
                                detail="qualified cost assumption is not positive")
    actual = D(obs.cost_drag)
    ratio = actual / assumed
    if ratio >= policy.cost_overrun_ratio:
        return DimensionVerdict(Dimension.COST.value, StrategyHealth.WATCH.value,
                                (Reason.COST_ASSUMPTION_BREACH.value,), ratio, policy.cost_overrun_ratio)
    reasons = () if obs.cost_detail_available else (Reason.COST_DETAIL_UNAVAILABLE.value,)
    return DimensionVerdict(Dimension.COST.value, StrategyHealth.NORMAL.value, reasons,
                            ratio, policy.cost_overrun_ratio)


def evaluate_turnover(obs: Observation, envelope: QualificationEnvelope, policy: MonitorPolicy) -> DimensionVerdict:
    if obs.turnover_ratio is None or envelope.qualified_turnover is None:
        return DimensionVerdict(Dimension.TURNOVER.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.TURNOVER_UNAVAILABLE.value,))
    qualified = D(envelope.qualified_turnover)
    if qualified <= 0:
        return DimensionVerdict(Dimension.TURNOVER.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.TURNOVER_UNAVAILABLE.value,))
    ratio = D(obs.turnover_ratio) / qualified
    if ratio >= policy.turnover_inflation_ratio:
        return DimensionVerdict(Dimension.TURNOVER.value, StrategyHealth.WATCH.value,
                                (Reason.TURNOVER_INFLATION.value,), ratio, policy.turnover_inflation_ratio)
    return DimensionVerdict(Dimension.TURNOVER.value, StrategyHealth.NORMAL.value, (), ratio,
                            policy.turnover_inflation_ratio)


def evaluate_signals(obs: Observation, envelope: QualificationEnvelope, policy: MonitorPolicy) -> DimensionVerdict:
    """Sparse signals are a reason to keep watching, never a verdict on skill."""
    if envelope.expected_trades_per_week is None or obs.observed_seconds <= 0:
        return DimensionVerdict(Dimension.SIGNAL.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.OBSERVATION_INSUFFICIENT.value,))
    weeks = D(obs.observed_seconds) / D(7 * 24 * 3600)
    if weeks <= 0:
        return DimensionVerdict(Dimension.SIGNAL.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.OBSERVATION_INSUFFICIENT.value,))
    expected = D(envelope.expected_trades_per_week) * weeks
    actual = D(obs.signals)
    if expected > 0 and actual < expected / 2:
        return DimensionVerdict(Dimension.SIGNAL.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.SIGNAL_SPARSE.value,), actual, expected)
    return DimensionVerdict(Dimension.SIGNAL.value, StrategyHealth.NORMAL.value, (), actual, expected)


def evaluate_regime(obs: Observation, envelope: QualificationEnvelope) -> DimensionVerdict:
    """Regime compatibility — an OBSERVATION, never switching authority.

    An unknown regime is unknown, not a mismatch: the existing regime engine
    fails closed to UNKNOWN, and treating that as incompatibility would
    manufacture a verdict out of our own missing data.
    """
    if not envelope.qualified_regimes:
        return DimensionVerdict(Dimension.REGIME.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.REGIME_UNKNOWN.value,),
                                detail="strategy declares no qualified regime")
    if obs.current_regime is None or obs.current_regime == "UNKNOWN":
        return DimensionVerdict(Dimension.REGIME.value, StrategyHealth.INSUFFICIENT_EVIDENCE.value,
                                (Reason.REGIME_UNKNOWN.value,),
                                detail="regime classifier returned no usable label")
    if obs.current_regime not in envelope.qualified_regimes:
        return DimensionVerdict(Dimension.REGIME.value, StrategyHealth.WATCH.value,
                                (Reason.REGIME_MISMATCH.value,),
                                detail=f"observing {obs.current_regime}, qualified for "
                                       f"{sorted(envelope.qualified_regimes)}")
    return DimensionVerdict(Dimension.REGIME.value, StrategyHealth.NORMAL.value, ())


def evaluate_data_quality(obs: Observation) -> DimensionVerdict:
    """Bad data blocks interpretation. It is never the strategy's fault.

    NO_DATA_FAILURE_CLASSIFIED_AS_STRATEGY_FAILURE: this returns
    DATA_QUALITY_BLOCKED, which the roll-up treats as "cannot judge", not as
    evidence against the strategy.
    """
    reasons = []
    if obs.data_stale:
        reasons.append(Reason.DATA_STALE.value)
    if obs.data_gap:
        reasons.append(Reason.DATA_GAP.value)
    health = StrategyHealth.DATA_QUALITY_BLOCKED.value if reasons else StrategyHealth.NORMAL.value
    return DimensionVerdict(Dimension.DATA_QUALITY.value, health, tuple(reasons))


def evaluate_reconciliation(obs: Observation) -> DimensionVerdict:
    if obs.reconciliation_ok:
        return DimensionVerdict(Dimension.RECONCILIATION.value, StrategyHealth.NORMAL.value, ())
    return DimensionVerdict(Dimension.RECONCILIATION.value, StrategyHealth.DATA_QUALITY_BLOCKED.value,
                            (Reason.RECONCILIATION_REQUIRED.value,),
                            detail="books do not reconcile; health cannot be claimed")


# ── roll-up ─────────────────────────────────────────────────────────────────

def _verdict_id(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def evaluate_strategy_health(
    envelope: QualificationEnvelope,
    observation: Observation,
    *,
    policy: MonitorPolicy | None = None,
    previous_health: str | None = None,
) -> MonitorVerdict:
    """Classify one strategy over one window. Deterministic and read-only.

    Ordering matters and is deliberate:
      1. Untrustworthy observation blocks interpretation outright.
      2. Insufficient observation dominates every performance conclusion.
      3. Only then do the performance dimensions get to speak.
    """
    policy = policy or MonitorPolicy()

    data = evaluate_data_quality(observation)
    recon = evaluate_reconciliation(observation)
    sufficiency = evaluate_observation(observation, policy)
    dims = [
        data, recon, sufficiency,
        evaluate_drawdown(observation, policy, previous_health),
        evaluate_benchmark(observation, policy),
        evaluate_cost(observation, envelope, policy),
        evaluate_turnover(observation, envelope, policy),
        evaluate_signals(observation, envelope, policy),
        evaluate_regime(observation, envelope),
    ]

    blocked = StrategyHealth.DATA_QUALITY_BLOCKED.value
    if data.health == blocked or recon.health == blocked:
        # The observation itself is untrustworthy, so no performance claim is made.
        health = blocked
        reasons = tuple(dict.fromkeys(data.reasons + recon.reasons))
    else:
        perf = _worst(*[d.health for d in dims if d.dimension != Dimension.OBSERVATION.value])
        if sufficiency.health == StrategyHealth.INSUFFICIENT_EVIDENCE.value:
            # A real DEGRADED signal still surfaces; anything milder is drowned out
            # by not having watched long enough to say it.
            health = perf if perf == StrategyHealth.DEGRADED.value \
                else StrategyHealth.INSUFFICIENT_EVIDENCE.value
        else:
            health = perf
        reasons = tuple(dict.fromkeys(r for d in dims for r in d.reasons))

    body = {
        "strategy_id": envelope.strategy_id,
        "strategy_version": envelope.strategy_version,
        "qualification_sha": envelope.qualification_sha,
        "health": health,
        "reasons": list(reasons),
        "dimensions": [d.__dict__ for d in dims],
        "policy_fingerprint": policy.fingerprint(),
        "calculation_version": CALCULATION_VERSION,
        "mode": observation.mode,
        "window_start": observation.window_start,
        "window_end": observation.window_end,
        "attribution_report_id": observation.attribution_report_id,
    }
    return MonitorVerdict(
        strategy_id=envelope.strategy_id,
        strategy_version=envelope.strategy_version,
        health=health,
        health_class=HEALTH_CLASS_OF[StrategyHealth(health)].value,
        reasons=reasons,
        dimensions=tuple(dims),
        policy_version=policy.version,
        policy_fingerprint=policy.fingerprint(),
        calculation_version=CALCULATION_VERSION,
        mode=observation.mode,
        window_start=observation.window_start,
        window_end=observation.window_end,
        previous_health=previous_health,
        transitioned=previous_health is not None and previous_health != health,
        verdict_id=_verdict_id(body),
    )


def monitoring_events(verdict: MonitorVerdict) -> list[dict]:
    """Alerts for this verdict. Idempotent by construction.

    The event key is derived from the verdict content, so re-evaluating an
    unchanged window produces the same keys and a consumer can drop duplicates
    without a clock or a sequence number. Events are emitted only on a TRANSITION,
    so a strategy sitting in WATCH does not alert on every cycle.
    """
    if verdict.previous_health is not None and not verdict.transitioned:
        return []
    events = []
    for reason in verdict.reasons or ("STATE_" + verdict.health,):
        events.append({
            "event": f"STRATEGY_{verdict.health}",
            "reason": reason,
            "strategy_id": verdict.strategy_id,
            "strategy_version": verdict.strategy_version,
            "health": verdict.health,
            "previous_health": verdict.previous_health,
            "policy_version": verdict.policy_version,
            "key": hashlib.sha256(
                f"{verdict.verdict_id}:{reason}".encode()).hexdigest()[:24],
            "authorizes_execution": False,
        })
    return events
