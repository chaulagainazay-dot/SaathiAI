"""HEALTH-COLLECTOR-1 — safe reads from live subsystems into the ops snapshot.

TRADING-HEALTH-PRODUCERS-1 built typed producers and certified one limitation
above all others: they classify supplied state and nothing polls the subsystems.
This closes that, and the reason it needed its own milestone is the reason that
limitation existed in the first place.

  live subsystems -> NON-MUTATING read adapters -> health producers
                  -> trading_ops snapshot

THE CONSTRAINT THAT SHAPES EVERYTHING HERE. Two authorities have no side-effect-free
public read:

  * `ActivationApprovalCenter.get`/`.list` lazily expire a lapsed approval,
    stamping `decided_at` and freezing it.
  * `ProviderHealthTracker.get` inserts a record for a provider it has not seen.

Both behaviours are right in their own modules — expiry should bite the moment
anyone acts on an approval, and an observation path should default a record into
existence. Both are wrong for monitoring. A health pass that expired approvals
would write transitions into the audit trail caused by nothing but looking, and
one that inserted providers would grow the registry with every provider it merely
asked about. So this module drives the `peek` reads added alongside it and never
the mutating accessors, and tests prove the distinction rather than assert it.

COLLECTION IS NOT AUTHORITY. This reads, copies, normalises and aggregates. It
does not expire, create, reconcile, recover, retry, submit, reserve, consume or
engage anything.

TIME IS EXPLICIT. Freshness genuinely depends on the clock, so the collector takes
an `evaluation_time` rather than reading one. The producers stay clock-free, and
tests inject a deterministic time instead of tolerating whatever `now` happens to
be.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from saathi.platform.tg.health_producers import (
    HealthMode,
    ProducedHealth,
    approval_health,
    execution_gateway_health,
    guardian_health,
    market_data_health,
    provider_health,
)
from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.tg.trading_ops import OperatorAction, Subsystem

# One implementation of civil-date arithmetic, imported rather than copied. It is
# deliberately clock-free there, which is exactly what a deterministic freshness
# calculation needs; a second copy could drift from it silently.
from saathi.platform.tg.strategy_observation import _epoch as iso_epoch

COLLECTOR_VERSION = "trading-health-collector/v1.0.0"

#: How old a market-data observation may be before it stops counting as fresh.
#: A default, not a policy: callers with a real freshness policy pass their own.
DEFAULT_MAX_OBSERVATION_AGE_SECONDS = 120


class CollectionStatus(str, Enum):
    """Why a subsystem reading looks the way it does.

    Kept distinct rather than collapsed into one UNKNOWN, because "nobody asked",
    "the source is not wired up" and "the read raised" call for different operator
    responses.
    """

    OK = "OK"
    NOT_COLLECTED = "NOT_COLLECTED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    COLLECTION_FAILED = "COLLECTION_FAILED"


@dataclass(frozen=True)
class SubsystemReading:
    """One safe read: the raw state, plus how the reading itself went."""

    subsystem: str
    status: str
    #: STRICTLY the producer's keyword arguments. Anything else belongs in
    #: `diagnostics` — a stray key here becomes a TypeError at produce time,
    #: which fault isolation would turn into a silent INSUFFICIENT_EVIDENCE.
    state: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)
    error: str | None = None
    source_ref: str | None = None

    @property
    def usable(self) -> bool:
        return self.status == CollectionStatus.OK.value


@dataclass(frozen=True)
class CollectionResult:
    """Everything one pass produced. Derived; persisted nowhere."""

    evaluation_time: str | None
    readings: tuple = ()
    healths: tuple = ()
    failures: tuple = ()
    collector_version: str = COLLECTOR_VERSION
    authorizes_execution: bool = False

    def health_for(self, subsystem: str) -> ProducedHealth | None:
        return next((h for h in self.healths if h.subsystem == subsystem), None)


def _failed(subsystem: str, exc: BaseException, *, source_ref=None) -> SubsystemReading:
    return SubsystemReading(
        subsystem=subsystem,
        status=CollectionStatus.COLLECTION_FAILED.value,
        error=f"{type(exc).__name__}: {exc}"[:200],
        source_ref=source_ref,
    )


def _not_collected(subsystem: str, why: str) -> SubsystemReading:
    return SubsystemReading(
        subsystem=subsystem, status=CollectionStatus.NOT_COLLECTED.value, error=why,
    )


# ── safe read adapters ──────────────────────────────────────────────────────
def read_provider(tracker, provider_id: str) -> SubsystemReading:
    """Read one provider's health record WITHOUT creating it.

    Uses `peek`, never `get`. An unseen provider reads as NOT_COLLECTED — which is
    true, and importantly leaves the registry exactly as it was.
    """
    if tracker is None:
        return _not_collected(Subsystem.PROVIDER.value, "no provider tracker supplied")
    try:
        rec = tracker.peek(provider_id)
    except Exception as exc:  # a broken source must not take the pass down
        return _failed(Subsystem.PROVIDER.value, exc, source_ref=provider_id)
    if rec is None:
        return SubsystemReading(
            subsystem=Subsystem.PROVIDER.value,
            status=CollectionStatus.NOT_COLLECTED.value,
            error=f"provider {provider_id} has no recorded health",
            source_ref=provider_id,
        )
    return SubsystemReading(
        subsystem=Subsystem.PROVIDER.value,
        status=CollectionStatus.OK.value,
        state={"state": rec.state, "last_error": rec.last_reason or None},
        source_ref=provider_id,
    )


def read_approval(center, *, evaluation_time: str | None = None) -> SubsystemReading:
    """Read approval-store state WITHOUT expiring anything.

    Uses `peek`, never `get`/`list`. Approvals whose deadline has passed but which
    the authority has not yet transitioned are counted here as lapsed, from
    `expires_at` against the supplied evaluation time — an observation, not a
    transition. The authority still owns the actual expiry.
    """
    if center is None:
        return _not_collected(Subsystem.APPROVAL.value, "no approval centre supplied")
    try:
        rows = center.peek()
    except Exception as exc:
        return _failed(Subsystem.APPROVAL.value, exc)

    now = iso_epoch(evaluation_time) if evaluation_time else None
    pending = expired = 0
    for r in rows:
        status = str(r.get("status", "")).upper()
        if status == "EXPIRED":
            expired += 1
        elif status == "PENDING":
            deadline = r.get("expires_at")
            # Lapsed but untransitioned: counted as expired, left untouched.
            if now is not None and deadline is not None and float(deadline) < now:
                expired += 1
            else:
                pending += 1
    return SubsystemReading(
        subsystem=Subsystem.APPROVAL.value,
        status=CollectionStatus.OK.value,
        state={"service_available": True, "pending": pending, "expired": expired},
    )


def read_guardian(service) -> SubsystemReading:
    """Read Guardian posture. `posture()` is a pure read of policy and switches."""
    if service is None:
        return _not_collected(Subsystem.GUARDIAN.value, "no guardian service supplied")
    try:
        p = service.posture()
    except Exception as exc:
        return _failed(Subsystem.GUARDIAN.value, exc)
    version = p.get("policy_version")
    return SubsystemReading(
        subsystem=Subsystem.GUARDIAN.value,
        status=CollectionStatus.OK.value,
        state={
            "policy_loaded": bool(version),
            "policy_version": version,
            "authority_mode": p.get("authority_mode"),
        },
        # Read-only context. Kept OUT of `state` because Guardian health does not
        # take the kill switch as an input — the switch is the gateway's concern,
        # and a Guardian holding a valid policy is healthy whether or not trading
        # is halted.
        diagnostics={"kill_switch_engaged": bool(p.get("kill_switch"))},
    )


def read_kill_switch(store) -> SubsystemReading:
    """Kill-switch state, read-only. `status()` iterates; it never toggles."""
    if store is None:
        return _not_collected(Subsystem.KILL_SWITCH.value, "no kill switch store supplied")
    try:
        rows = list(store.status())
    except Exception as exc:
        return _failed(Subsystem.KILL_SWITCH.value, exc)
    active = [r for r in rows if r.get("active")]
    return SubsystemReading(
        subsystem=Subsystem.KILL_SWITCH.value,
        status=CollectionStatus.OK.value,
        state={
            "engaged": bool(active),
            "reason": active[0].get("reason") if active else None,
            "scope": active[0].get("scope") if active else None,
        },
    )


def read_execution_gateway(
    *, gateway_available=None, live_execution_enabled=False, paper_ready=True,
    shadow_only=False, unknown_execution_state=False, reconciliation_required=False,
    kill_switch_engaged=False,
) -> SubsystemReading:
    """Gateway posture from CONFIGURATION, never by exercising it.

    Deliberately takes flags rather than a gateway object: every interesting method
    on `ExecutionGateway` (`submit`, `approve_execution`, `retry_execution`,
    `recover_after_restart`) advances execution state. There is no method to ask
    it how it is without asking it to do something, so the collector reads the
    posture around it instead of poking it.

    `reconciliation_required` is likewise supplied. Calling a reconciler to find
    out whether reconciliation is needed is precisely the mutating read this
    milestone exists to avoid.
    """
    if gateway_available is None:
        return _not_collected(
            Subsystem.EXECUTION_GATEWAY.value, "gateway availability not supplied")
    return SubsystemReading(
        subsystem=Subsystem.EXECUTION_GATEWAY.value,
        status=CollectionStatus.OK.value,
        state={
            "gateway_available": bool(gateway_available),
            "live_execution_enabled": bool(live_execution_enabled),
            "paper_ready": bool(paper_ready),
            "shadow_only": bool(shadow_only),
            "unknown_execution_state": bool(unknown_execution_state),
            "reconciliation_required": bool(reconciliation_required),
            "kill_switch_engaged": bool(kill_switch_engaged),
        },
    )


def read_market_data(source, *, evaluation_time: str | None = None,
                     max_age_seconds: int = DEFAULT_MAX_OBSERVATION_AGE_SECONDS
                     ) -> SubsystemReading:
    """Read feed state, deriving freshness from OBSERVATION AGE and nothing else.

    NO_CONNECTIVITY_AS_FRESHNESS is enforced here as well as in the producer: a
    source that reports a live transport but no last-observation time yields no
    freshness at all, because a socket that is up while nothing arrives is the
    failure this rule exists for. Connectivity and freshness are collected as two
    separate facts and stay separate.
    """
    if source is None:
        return _not_collected(Subsystem.MARKET_DATA.value, "no market data source supplied")
    try:
        raw = dict(source) if isinstance(source, dict) else dict(source.snapshot())
    except Exception as exc:
        return _failed(Subsystem.MARKET_DATA.value, exc)

    state = {
        "connected": raw.get("connected"),
        "source": raw.get("source"),
        "sequence_gap": bool(raw.get("sequence_gap")),
        "resync_pending": bool(raw.get("resync_pending")),
        "reconnecting": bool(raw.get("reconnecting")),
        "reconnect_exhausted": bool(raw.get("reconnect_exhausted")),
        "last_valid_observation": raw.get("last_valid_observation"),
        "contained": bool(raw.get("contained", True)),
    }

    # Freshness: only ever from a real observation time against an explicit
    # evaluation time. If either is absent, freshness stays unknown.
    freshness = raw.get("freshness")
    age = None
    last = state["last_valid_observation"]
    if freshness is None and last and evaluation_time:
        a, b = iso_epoch(str(last)), iso_epoch(evaluation_time)
        if a is not None and b is not None:
            freshness = "FRESH" if (b - a) <= max_age_seconds else "STALE"
            age = max(0, b - a)
    state["freshness"] = freshness
    return SubsystemReading(
        subsystem=Subsystem.MARKET_DATA.value,
        status=CollectionStatus.OK.value,
        state=state,
        diagnostics={"observation_age_seconds": age, "max_age_seconds": max_age_seconds},
        source_ref=raw.get("source"),
    )


# ── collection ──────────────────────────────────────────────────────────────
#
# A reading that did not succeed must never become a HEALTHY producer result, so
# every unusable reading routes to the producer with NO state — which the
# producers already turn into INSUFFICIENT_EVIDENCE. This is the whole of
# NO_FALSE_HEALTHY_ON_COLLECTOR_FAILURE: it is enforced by passing nothing rather
# than by remembering to check a flag.
def collect_trading_health(
    *,
    evaluation_time: str | None,
    market_data_source=None,
    provider_tracker=None,
    provider_ids=(),
    guardian_service=None,
    kill_switch_store=None,
    approval_center=None,
    gateway=None,
    max_age_seconds: int = DEFAULT_MAX_OBSERVATION_AGE_SECONDS,
) -> CollectionResult:
    """One safe pass over the trading subsystems. Pure with respect to the clock.

    FAULT ISOLATION IS THE POINT. Each subsystem is read and produced
    independently, so a provider whose read raises cannot erase Guardian's health.
    The failure is carried per-subsystem and that subsystem falls to insufficient
    evidence; everything else still reports.
    """
    readings: list[SubsystemReading] = []
    healths: list[ProducedHealth] = []
    failures: list[dict] = []

    def _produce(reading: SubsystemReading, producer, **kwargs):
        readings.append(reading)
        if not reading.usable:
            failures.append({
                "subsystem": reading.subsystem,
                "status": reading.status,
                "error": reading.error,
            })
        try:
            # An unusable reading contributes no state, so the producer reaches
            # its own insufficient-evidence path rather than a fabricated one.
            state = dict(reading.state) if reading.usable else {}
            healths.append(producer(observed_at=evaluation_time, **state, **kwargs))
        except Exception as exc:
            failures.append({
                "subsystem": reading.subsystem,
                "status": CollectionStatus.COLLECTION_FAILED.value,
                "error": f"{type(exc).__name__}: {exc}"[:200],
            })
            healths.append(_producer_failed(reading.subsystem, exc, evaluation_time))

    # Kill switch first: the gateway reading depends on it, and it is a pure read.
    ks_reading = read_kill_switch(kill_switch_store)
    ks_engaged = bool(ks_reading.state.get("engaged")) if ks_reading.usable else False

    _produce(
        read_market_data(market_data_source, evaluation_time=evaluation_time,
                         max_age_seconds=max_age_seconds),
        market_data_health,
    )

    # A provider list is explicit: the collector never enumerates providers by
    # asking for ones it has not been told about, which is how `get` would have
    # created them.
    ids = list(provider_ids)
    if not ids and provider_tracker is not None:
        try:
            ids = list(provider_tracker.known_provider_ids())
        except Exception:
            ids = []
    if not ids:
        _produce(_not_collected(Subsystem.PROVIDER.value, "no providers named"),
                 provider_health)
    else:
        for pid in ids:
            _produce(read_provider(provider_tracker, pid), provider_health,
                     provider_id=pid)

    _produce(read_guardian(guardian_service), guardian_health)

    gw = gateway if gateway is not None else {}
    _produce(
        read_execution_gateway(
            gateway_available=gw.get("gateway_available"),
            live_execution_enabled=gw.get("live_execution_enabled", False),
            paper_ready=gw.get("paper_ready", True),
            shadow_only=gw.get("shadow_only", False),
            unknown_execution_state=gw.get("unknown_execution_state", False),
            reconciliation_required=gw.get("reconciliation_required", False),
            kill_switch_engaged=gw.get("kill_switch_engaged", ks_engaged),
        ),
        execution_gateway_health,
    )

    _produce(read_approval(approval_center, evaluation_time=evaluation_time),
             approval_health)

    readings.append(ks_reading)
    return CollectionResult(
        evaluation_time=evaluation_time,
        readings=tuple(readings),
        healths=tuple(healths),
        failures=tuple(failures),
    )


def _producer_failed(subsystem: str, exc: BaseException, at: str | None) -> ProducedHealth:
    """A producer that raised yields an explicit failure, never a gap.

    Dropping the subsystem would be worse than reporting the fault: an absent row
    reads as "nothing to say", and a subsystem nobody can classify is exactly the
    thing an operator must be told about.
    """
    from saathi.platform.tg.health_producers import StateCode

    return ProducedHealth(
        subsystem=subsystem,
        health_class=HealthClass.WARNING.value,
        state_code=StateCode.INSUFFICIENT_EVIDENCE.value,
        reason_codes=("COLLECTION_FAILED",),
        observed_at=at,
        mode=HealthMode.UNKNOWN.value,
        evidence_sufficient=False,
        operator_action_required=OperatorAction.MANUAL_OPERATOR_VALIDATION.value,
        detail=f"health collection failed: {type(exc).__name__}",
    )


def snapshot_from_collection(result: CollectionResult, *, mode: str, **snapshot_kwargs):
    """Feed one collection into the EXISTING TRADING-OPS-1 snapshot, unchanged."""
    from saathi.platform.tg.health_producers import snapshot_from_producers

    return snapshot_from_producers(
        result.healths, observed_at=result.evaluation_time, mode=mode, **snapshot_kwargs,
    )


# ── bounded runner ──────────────────────────────────────────────────────────
class TradingHealthCollector:
    """Caller-driven runner with overlap coalescing. No thread, no daemon.

    Scheduling is kept OUT of the collection logic so the aggregation stays pure
    and testable. This adds no dependency and starts nothing: the host loop, or
    the existing `pg_scheduler` job table, decides when `tick` is called. That is
    deliberately the smallest thing that satisfies "do not pile up overlapping
    collections" without introducing a process manager the milestone forbids.
    """

    def __init__(self, *, min_interval_seconds: int = 30):
        self.min_interval_seconds = int(min_interval_seconds)
        self._running = False
        self._last_evaluation_time: str | None = None
        self._last: CollectionResult | None = None
        self.skipped = 0
        self.runs = 0

    @property
    def last_result(self) -> CollectionResult | None:
        return self._last

    def tick(self, *, evaluation_time: str, **kwargs) -> CollectionResult | None:
        """Collect if due. Returns None when coalesced.

        Two guards, both deterministic. A re-entrant call while a pass is already
        in flight is DROPPED rather than queued — an unbounded queue of health
        passes is how a slow subsystem turns a monitor into an outage. And a call
        that arrives sooner than the minimum interval is coalesced, because health
        does not need millisecond polling.
        """
        if self._running:
            self.skipped += 1
            return None
        if self._last_evaluation_time is not None:
            a = iso_epoch(self._last_evaluation_time)
            b = iso_epoch(evaluation_time)
            if a is not None and b is not None and (b - a) < self.min_interval_seconds:
                self.skipped += 1
                return None
        self._running = True
        try:
            result = collect_trading_health(evaluation_time=evaluation_time, **kwargs)
        finally:
            # Released even if collection raised, or one bad pass would wedge the
            # collector shut for the life of the process.
            self._running = False
        self._last_evaluation_time = evaluation_time
        self._last = result
        self.runs += 1
        return result
