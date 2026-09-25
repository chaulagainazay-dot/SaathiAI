"""HEALTH-COLLECTOR-1 — safe reads from live subsystems into the ops snapshot.

The milestone exists because two authorities have no side-effect-free public
read. So the central tests here are not about health at all: they drive REAL
`ActivationApprovalCenter` and `ProviderHealthTracker` objects and prove that a
health pass changed nothing about them.
"""
from __future__ import annotations

import ast
import inspect
import time
from pathlib import Path

import pytest

from saathi.connectors.providers.health import ProviderHealthTracker
from saathi.platform.tg.health_collector import (
    DEFAULT_MAX_OBSERVATION_AGE_SECONDS,
    CollectionStatus,
    TradingHealthCollector,
    collect_trading_health,
    read_approval,
    read_execution_gateway,
    read_guardian,
    read_kill_switch,
    read_market_data,
    read_provider,
    snapshot_from_collection,
)
from saathi.platform.tg.health_producers import StateCode
from saathi.platform.tg.kill_switch import KillSwitchStore
from saathi.platform.tg.paper_activation.approvals import ActivationApprovalCenter
from saathi.platform.tg.paper_activation.models import ActivationApprovalStatus
from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.tg.service import TradingGuardianService
from saathi.platform.tg.trading_ops import OperatorAction, OpsMode, Subsystem

SRC = Path("saathi/platform/tg/health_collector.py")
AT = "2026-09-06T12:00:00Z"
#: Comfortably after any real-time deadline created during the test run.
LATER = "2030-01-01T00:00:00Z"
RECENT = "2026-09-06T11:59:30Z"
OLD = "2026-09-06T10:00:00Z"


def _approved(center):
    ap = center.request(strategy_slug="s", reason="collector test",
                        operator_id="op-1", operator_identity="human:operator")
    center.decide(ap.id, decision="approve", operator_id="op-1",
                  operator_identity="human:operator", notes="ok")
    return ap


def _healthy_sources():
    tracker = ProviderHealthTracker()
    tracker.observe_success("binance.public")
    return dict(
        market_data_source={"connected": True, "source": "GOVERNED_DATASET",
                            "last_valid_observation": RECENT},
        provider_tracker=tracker,
        guardian_service=TradingGuardianService(),
        kill_switch_store=KillSwitchStore(),
        approval_center=ActivationApprovalCenter(),
        gateway={"gateway_available": True},
    )


def _collect(**over):
    src = _healthy_sources()
    src.update(over)
    return collect_trading_health(evaluation_time=AT, **src)


# ══ the reason this milestone exists ════════════════════════════════════════
def test_a_health_pass_does_not_expire_a_lapsed_approval():
    """NO_APPROVAL_EXPIRY_FROM_HEALTH_READ, against the real approval centre.

    `get`/`list` transition a lapsed PENDING approval to EXPIRED, stamp
    `decided_at` and freeze it. If the collector used them, a monitoring pass
    would write that transition into the audit trail — an approval expired by
    nothing but being looked at.
    """
    center = ActivationApprovalCenter()
    lapsed = center.request(strategy_slug="s", reason="r", operator_id="o",
                            operator_identity="human:o", expires_in_sec=-1)
    assert lapsed.status is ActivationApprovalStatus.PENDING

    # Evaluated well after the approval's real-time deadline, so it is genuinely
    # lapsed at the moment of the read — otherwise this would pass vacuously.
    src = _healthy_sources()
    src["approval_center"] = center
    result = collect_trading_health(evaluation_time=LATER, **src)
    snapshot_from_collection(result, mode=OpsMode.SHADOW.value)

    assert lapsed.status is ActivationApprovalStatus.PENDING
    assert lapsed.decided_at is None
    assert lapsed.immutable is False
    # And the collector still REPORTED it as lapsed, without transitioning it.
    reading = next(r for r in result.readings if r.subsystem == Subsystem.APPROVAL.value)
    assert reading.state["expired"] == 1


def test_the_mutating_read_still_expires_so_the_contrast_is_real():
    """Guards the guard: if `get` stopped expiring, the test above would be vacuous."""
    center = ActivationApprovalCenter()
    lapsed = center.request(strategy_slug="s", reason="r", operator_id="o",
                            operator_identity="human:o", expires_in_sec=-1)
    assert center.get(lapsed.id).status is ActivationApprovalStatus.EXPIRED


def test_a_health_pass_does_not_consume_an_approval():
    center = ActivationApprovalCenter()
    ap = _approved(center)
    result = _collect(approval_center=center)
    snapshot_from_collection(result, mode=OpsMode.SHADOW.value)
    assert ap.status is ActivationApprovalStatus.APPROVED
    assert ap.consumed_at is None


def test_a_health_pass_does_not_create_an_unseen_provider():
    """NO_PROVIDER_CREATION_FROM_HEALTH_READ, against the real tracker.

    `tracker.get` defaults a missing provider into existence. Asking how a
    provider is doing must never be what makes it exist, or a monitoring pass
    would grow the registry with every id it was handed.
    """
    tracker = ProviderHealthTracker()
    tracker.observe_success("known.provider")
    before = tracker.known_provider_ids()

    result = collect_trading_health(
        evaluation_time=AT, provider_tracker=tracker,
        provider_ids=["known.provider", "never.seen.before", "also.unseen"],
    )
    snapshot_from_collection(result, mode=OpsMode.SHADOW.value)

    assert tracker.known_provider_ids() == before
    assert len(tracker.peek_all()) == 1
    assert tracker.peek("never.seen.before") is None


def test_the_mutating_provider_read_still_creates_so_the_contrast_is_real():
    tracker = ProviderHealthTracker()
    assert tracker.known_provider_ids() == ()
    tracker.get("brand.new")
    assert tracker.known_provider_ids() == ("brand.new",)


def test_an_unseen_provider_reports_not_collected_rather_than_healthy():
    r = read_provider(ProviderHealthTracker(), "unseen")
    assert r.status == CollectionStatus.NOT_COLLECTED.value
    assert r.usable is False


def test_a_health_pass_does_not_engage_or_release_the_kill_switch():
    store = KillSwitchStore()
    store.activate(scope="GLOBAL", reason="operator halt", activated_by="operator")
    before = [dict(x) for x in store.status()]
    _collect(kill_switch_store=store)
    assert [dict(x) for x in store.status()] == before
    assert store.is_blocked()["blocked"] is True


def test_the_collector_never_calls_a_mutating_read():
    """Structural: the accessors that transition state are absent by name."""
    tree = ast.parse(SRC.read_text())
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    # `get`/`list` on the approval centre and tracker are the exact hazards.
    assert "consume" not in called
    assert "decide" not in called
    assert "revoke" not in called
    assert "force_state" not in called
    assert "observe_error" not in called
    assert "observe_success" not in called
    assert "peek" in called  # the safe read is actually used


# ══ no false healthy ════════════════════════════════════════════════════════
def test_a_failing_read_never_yields_healthy_for_that_subsystem():
    class Exploding:
        def snapshot(self):
            raise RuntimeError("source exploded")

    result = _collect(market_data_source=Exploding())
    md = result.health_for(Subsystem.MARKET_DATA.value)
    assert md.health_class != HealthClass.HEALTHY.value
    assert md.evidence_sufficient is False
    assert any(f["subsystem"] == Subsystem.MARKET_DATA.value for f in result.failures)


def test_one_failing_read_does_not_erase_unrelated_health():
    """Fault isolation: a broken provider must not take Guardian down with it."""
    class Exploding:
        def peek(self, _pid):
            raise RuntimeError("tracker exploded")
        def known_provider_ids(self):
            return ("p",)

    result = _collect(provider_tracker=Exploding(), provider_ids=["p"])
    assert result.health_for(Subsystem.PROVIDER.value).evidence_sufficient is False
    for other in (Subsystem.GUARDIAN.value, Subsystem.APPROVAL.value,
                  Subsystem.EXECUTION_GATEWAY.value, Subsystem.MARKET_DATA.value):
        h = result.health_for(other)
        assert h is not None and h.evidence_sufficient is True, other


def test_an_uncollected_subsystem_is_insufficient_not_absent():
    """Dropping the row would read as 'nothing to say' about a real subsystem."""
    result = collect_trading_health(evaluation_time=AT)
    assert len(result.healths) == 5
    for h in result.healths:
        assert h.health_class != HealthClass.HEALTHY.value
        assert h.state_code == StateCode.INSUFFICIENT_EVIDENCE.value


# ══ connectivity is not freshness ═══════════════════════════════════════════
def test_a_connected_source_with_no_observation_time_yields_no_freshness():
    """NO_CONNECTIVITY_AS_FRESHNESS, enforced at the collector as well."""
    r = read_market_data({"connected": True, "source": "GOVERNED_DATASET"},
                         evaluation_time=AT)
    assert r.state["freshness"] is None
    result = _collect(market_data_source={"connected": True, "source": "GOVERNED_DATASET"})
    md = result.health_for(Subsystem.MARKET_DATA.value)
    assert md.state_code == StateCode.INSUFFICIENT_EVIDENCE.value


def test_freshness_comes_from_observation_age_against_explicit_time():
    fresh = read_market_data({"connected": True, "last_valid_observation": RECENT},
                             evaluation_time=AT)
    stale = read_market_data({"connected": True, "last_valid_observation": OLD},
                             evaluation_time=AT)
    assert fresh.state["freshness"] == "FRESH"
    assert stale.state["freshness"] == "STALE"
    assert fresh.diagnostics["observation_age_seconds"] == 30
    assert stale.diagnostics["observation_age_seconds"] == 7200


def test_the_freshness_threshold_is_the_supplied_policy_not_a_hidden_one():
    tight = read_market_data({"connected": True, "last_valid_observation": RECENT},
                             evaluation_time=AT, max_age_seconds=10)
    assert tight.state["freshness"] == "STALE"
    assert DEFAULT_MAX_OBSERVATION_AGE_SECONDS == 120


def test_without_an_evaluation_time_freshness_is_not_guessed():
    r = read_market_data({"connected": True, "last_valid_observation": RECENT})
    assert r.state["freshness"] is None


# ══ explicit time ═══════════════════════════════════════════════════════════
def test_the_collector_reads_no_hidden_clock():
    tree = ast.parse(SRC.read_text())
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            imported.add(n.module.split(".")[0])
    assert not ({"datetime", "time", "calendar"} & imported), imported
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not ({"now", "utcnow", "today", "monotonic"} & called), called


def test_the_same_state_and_time_reproduce_the_same_snapshot():
    src = _healthy_sources()
    a = snapshot_from_collection(
        collect_trading_health(evaluation_time=AT, **src), mode=OpsMode.SHADOW.value)
    b = snapshot_from_collection(
        collect_trading_health(evaluation_time=AT, **src), mode=OpsMode.SHADOW.value)
    assert a.snapshot_id == b.snapshot_id


# ══ UNKNOWN reduction from LIVE state ═══════════════════════════════════════
def test_live_sources_populate_all_five_subsystems_without_manual_shaping():
    """The milestone's headline claim, proven end to end.

    Nothing here hand-builds a producer argument: real objects go in, and five
    typed subsystem healths come out the far side of the ops snapshot.
    """
    snap = snapshot_from_collection(_collect(), mode=OpsMode.SHADOW.value)
    populated = {s.subsystem for s in snap.subsystems}
    assert populated == {
        Subsystem.MARKET_DATA.value, Subsystem.PROVIDER.value, Subsystem.GUARDIAN.value,
        Subsystem.EXECUTION_GATEWAY.value, Subsystem.APPROVAL.value,
    }
    for s in snap.subsystems:
        assert s.health in {h.value for h in HealthClass}
        assert s.authority != "UNKNOWN"


def test_a_real_guardian_service_reports_healthy_through_the_collector():
    r = read_guardian(TradingGuardianService())
    assert r.usable
    assert r.state["policy_loaded"] is True
    assert r.state["policy_version"]
    h = _collect().health_for(Subsystem.GUARDIAN.value)
    assert h.health_class == HealthClass.HEALTHY.value


def test_a_fully_healthy_collection_is_healthy_and_still_not_live_authorised():
    snap = snapshot_from_collection(_collect(), mode=OpsMode.SHADOW.value)
    assert snap.overall_health == HealthClass.HEALTHY.value
    assert snap.live_trading_authorized is False
    assert snap.authorizes_execution is False


@pytest.mark.parametrize("mode", [OpsMode.REPLAY, OpsMode.SHADOW, OpsMode.PAPER])
def test_mode_is_preserved_through_collection(mode):
    snap = snapshot_from_collection(_collect(), mode=mode.value)
    assert snap.mode == mode.value


def test_a_replay_feed_is_never_labelled_live():
    md = _collect().health_for(Subsystem.MARKET_DATA.value)
    assert md.mode == "REPLAY"
    assert "LIVE" not in md.mode


# ══ fault matrix ════════════════════════════════════════════════════════════
def test_stale_market_data_degrades_the_collected_snapshot():
    snap = snapshot_from_collection(
        _collect(market_data_source={"connected": True, "source": "GOVERNED_DATASET",
                                     "last_valid_observation": OLD}),
        mode=OpsMode.SHADOW.value)
    assert snap.overall_health == HealthClass.DEGRADED.value


def test_a_disconnected_feed_is_collected_as_a_fault():
    md = _collect(market_data_source={"connected": False, "source": "GOVERNED_DATASET"}
                  ).health_for(Subsystem.MARKET_DATA.value)
    assert md.state_code == StateCode.FEED_DISCONNECTED.value


def test_a_rate_limited_provider_survives_collection_as_itself():
    tracker = ProviderHealthTracker()
    tracker.observe_success("p")
    tracker.force_state("p", __import__(
        "saathi.connectors.providers.models", fromlist=["ProviderHealthState"]
    ).ProviderHealthState.RATE_LIMITED)
    h = collect_trading_health(evaluation_time=AT, provider_tracker=tracker,
                               provider_ids=["p"]).health_for(Subsystem.PROVIDER.value)
    assert h.state_code == StateCode.PROVIDER_RATE_LIMITED.value


def test_an_engaged_kill_switch_reaches_the_gateway_reading():
    store = KillSwitchStore()
    store.activate(scope="GLOBAL", reason="halt", activated_by="operator")
    result = _collect(kill_switch_store=store, gateway={"gateway_available": True})
    gw = result.health_for(Subsystem.EXECUTION_GATEWAY.value)
    assert gw.state_code == StateCode.KILL_SWITCH_ENGAGED.value
    assert gw.health_class == HealthClass.FAILED_SAFE.value


def test_an_unknown_execution_state_is_collected_as_critical():
    gw = _collect(gateway={"gateway_available": True, "unknown_execution_state": True}
                  ).health_for(Subsystem.EXECUTION_GATEWAY.value)
    assert gw.health_class == HealthClass.CRITICAL.value
    assert gw.operator_action_required == OperatorAction.REVIEW_RECONCILIATION.value


def test_pending_approvals_are_collected_without_becoming_a_fault():
    center = ActivationApprovalCenter()
    for _ in range(3):
        center.request(strategy_slug="s", reason="r", operator_id="o",
                       operator_identity="human:o")
    result = _collect(approval_center=center)
    reading = next(r for r in result.readings if r.subsystem == Subsystem.APPROVAL.value)
    assert reading.state["pending"] == 3
    assert result.health_for(Subsystem.APPROVAL.value).health_class == \
        HealthClass.HEALTHY.value


def test_root_cause_convergence_survives_real_collection():
    """A provider outage staling the feed must still be ONE incident."""
    from saathi.connectors.providers.models import ProviderHealthState

    tracker = ProviderHealthTracker()
    tracker.observe_success("binance.public")
    tracker.force_state("binance.public", ProviderHealthState.UNAVAILABLE)

    result = _collect(
        provider_tracker=tracker, provider_ids=["binance.public"],
        market_data_source={"connected": True, "source": "GOVERNED_DATASET",
                            "last_valid_observation": OLD},
    )
    snap = snapshot_from_collection(
        result, mode=OpsMode.SHADOW.value,
        extra_findings=[{
            "subsystem": Subsystem.STRATEGY.value, "health": HealthClass.DEGRADED.value,
            "cause": "STRATEGY_DATA_QUALITY_BLOCKED", "state": "DATA_QUALITY_BLOCKED",
        }],
    )
    assert len(snap.incidents) == 1
    assert snap.incidents[0].subsystem == Subsystem.PROVIDER.value
    assert {s["subsystem"] for s in snap.incidents[0].symptoms} == {
        Subsystem.MARKET_DATA.value, Subsystem.STRATEGY.value}


# ══ runner ══════════════════════════════════════════════════════════════════
def test_the_runner_coalesces_calls_inside_the_minimum_interval():
    c = TradingHealthCollector(min_interval_seconds=60)
    assert c.tick(evaluation_time="2026-09-06T12:00:00Z") is not None
    assert c.tick(evaluation_time="2026-09-06T12:00:30Z") is None   # too soon
    assert c.tick(evaluation_time="2026-09-06T12:01:00Z") is not None
    assert c.runs == 2 and c.skipped == 1


def test_a_reentrant_tick_is_dropped_not_queued():
    """An unbounded queue of health passes is how a monitor becomes an outage."""
    c = TradingHealthCollector(min_interval_seconds=0)
    seen = {}

    class Reentrant:
        def snapshot(self):
            seen["inner"] = c.tick(evaluation_time="2026-09-06T12:00:01Z")
            return {"connected": True, "last_valid_observation": RECENT}

    c.tick(evaluation_time=AT, market_data_source=Reentrant())
    assert seen["inner"] is None
    assert c.skipped == 1


def test_a_raising_collection_does_not_wedge_the_runner_shut():
    c = TradingHealthCollector(min_interval_seconds=0)
    with pytest.raises(TypeError):
        c.tick(evaluation_time=AT, not_a_real_argument=1)
    # The in-flight guard must be released even on failure.
    assert c.tick(evaluation_time="2026-09-06T12:00:05Z") is not None


def test_a_restart_reproduces_equivalent_health_from_the_same_state():
    """No fabricated healthy state on startup, no lost unresolved condition."""
    src = _healthy_sources()
    first = TradingHealthCollector(min_interval_seconds=0)
    before = snapshot_from_collection(
        first.tick(evaluation_time=AT, **src), mode=OpsMode.SHADOW.value)

    fresh = TradingHealthCollector(min_interval_seconds=0)   # new process
    after = snapshot_from_collection(
        fresh.tick(evaluation_time=AT, **src), mode=OpsMode.SHADOW.value)

    assert before.snapshot_id == after.snapshot_id
    assert before.overall_health == after.overall_health
    assert [s.health for s in before.subsystems] == [s.health for s in after.subsystems]


def test_the_runner_starts_nothing_on_construction():
    """Bounded by design: no thread, no daemon, no process manager."""
    c = TradingHealthCollector()
    assert c.runs == 0 and c.last_result is None
    tree = ast.parse(SRC.read_text())
    names = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not ({"Thread", "start", "spawn", "Process", "create_task"} & names), names


# ══ authority containment ═══════════════════════════════════════════════════
def test_the_collector_holds_no_execution_or_recovery_authority():
    tree = ast.parse(SRC.read_text())
    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                called.add(n.func.id)
    forbidden = {
        "submit", "place", "send_order", "create_order", "cancel", "execute",
        "reserve", "reserve_cash", "consume", "approve", "decide", "revoke",
        "activate", "deactivate", "reconcile", "recover", "recover_after_restart",
        "retry", "retry_execution", "run_recovery_suite", "set_policy", "set_limit",
        "commit", "with_tx", "freeze", "force_state",
    }
    assert not (forbidden & called), forbidden & called


def test_the_collector_triggers_no_reconciliation_or_recovery():
    """NO_RECONCILIATION_FROM_HEALTH_READ — reconciliation need is READ, not run."""
    sig = inspect.signature(read_execution_gateway)
    assert "reconciliation_required" in sig.parameters
    src = SRC.read_text()
    assert "reconcile(" not in src
    assert "run_recovery_suite" not in src


def test_no_private_account_or_broker_access():
    tree = ast.parse(SRC.read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    banned = ("broker", "binance", "venue", "fund_ledger", "credentials", "secret")
    assert not [m for m in mods if any(b in m.lower() for b in banned)], mods


def test_no_credential_material_reaches_a_collected_snapshot():
    import json

    blob = json.dumps(
        snapshot_from_collection(_collect(), mode=OpsMode.SHADOW.value).to_public(),
        default=str,
    ).lower()
    for marker in ("api_key", "secret", "password", "bearer", "token=", "authorization"):
        assert marker not in blob, marker


def test_a_full_pass_is_cheap_enough_to_run_continuously():
    """Resource budget: this is meant to run on an 8 GB laptop, repeatedly."""
    src = _healthy_sources()
    start = time.perf_counter()
    for _ in range(200):
        collect_trading_health(evaluation_time=AT, **src)
    elapsed = time.perf_counter() - start
    # Generous bound: the point is to catch an accidental I/O path, not to
    # benchmark. A per-pass cost anywhere near a millisecond is still fine.
    assert elapsed < 5.0, elapsed


def test_every_reading_state_key_is_a_real_producer_argument():
    """Guards a whole class of silent failure.

    A reading whose `state` carries a key the producer does not accept raises a
    TypeError, which fault isolation dutifully converts into INSUFFICIENT_EVIDENCE
    — so the subsystem quietly stops reporting while every test about health still
    passes. Two such keys (`observation_age_seconds`, `kill_switch_engaged`) were
    caught this way. Diagnostics exist for exactly that context.
    """
    from saathi.platform.tg import health_producers as hp

    src = _healthy_sources()
    result = collect_trading_health(evaluation_time=AT, **src)
    producer_for = {
        Subsystem.MARKET_DATA.value: hp.market_data_health,
        Subsystem.PROVIDER.value: hp.provider_health,
        Subsystem.GUARDIAN.value: hp.guardian_health,
        Subsystem.EXECUTION_GATEWAY.value: hp.execution_gateway_health,
        Subsystem.APPROVAL.value: hp.approval_health,
    }
    for reading in result.readings:
        producer = producer_for.get(reading.subsystem)
        if producer is None or not reading.usable:
            continue
        accepted = set(inspect.signature(producer).parameters)
        assert set(reading.state) <= accepted, (
            reading.subsystem, set(reading.state) - accepted)


def test_no_collected_subsystem_silently_falls_to_insufficient_evidence():
    """The symptom the test above prevents, asserted directly on a healthy pass."""
    result = _collect()
    for h in result.healths:
        assert h.evidence_sufficient is True, (h.subsystem, h.detail)
    assert result.failures == ()
