"""TRADING-OPS-1 — operator-facing supervision over the existing trading stack.

The question every test here serves: can one operator tell whether the trading
system is safe right now, and if not, what they must do and who owns it?

Nothing in this milestone decides health. The authorities decide; this layer
combines. So the tests assert COMBINATION behaviour — precedence, convergence,
deduplication, ownership — plus the structural guarantee that supervision never
acquires execution authority.
"""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from saathi.platform.research.store import ResearchStore
from saathi.platform.tg.kill_switch import KillSwitchStore
from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.tg.paper_activation.ops.monitoring import _worst as monitor_worst
from saathi.platform.tg.resilience import FailureMode, Response, degrade
from saathi.platform.tg.shadow_session import (
    ShadowEventKind,
    ShadowMode,
    ShadowSessionStore,
)
from saathi.platform.tg.strategy_monitor import (
    QualificationEnvelope,
    StrategyHealth,
    evaluate_strategy_health,
)
from saathi.platform.tg.strategy_observation import observation_from_shadow
from saathi.platform.tg.trading_ops import (
    AUTHORITY_OF,
    CAUSAL_PARENTS,
    SUBSYSTEM_FOR_FAILURE,
    authority_for,
    panel_status_for,
    OperatorAction,
    OpsMode,
    RecoveryState,
    ReconciliationState,
    Subsystem,
    build_snapshot,
    converge_incidents,
    dedup_key,
    health_for_failure,
    recovery_for_failures,
    worst_health,
)

OPS_SRC = Path("saathi/platform/tg/trading_ops.py")
AT = "2026-09-06T12:00:00Z"


def _sub(subsystem, health, **kw):
    return {"subsystem": subsystem, "health": health, **kw}


def _snap(subsystems, **kw):
    params = dict(observed_at=AT, mode=OpsMode.SHADOW.value, subsystems=subsystems)
    params.update(kw)
    return build_snapshot(**params)


HEALTHY = [
    _sub(Subsystem.MARKET_DATA.value, HealthClass.HEALTHY.value),
    _sub(Subsystem.GUARDIAN.value, HealthClass.HEALTHY.value),
    _sub(Subsystem.STRATEGY.value, HealthClass.HEALTHY.value),
]


# ── vocabulary convergence ──────────────────────────────────────────────────
def test_no_new_health_vocabulary_is_invented():
    """The brief's hard constraint: reuse HealthClass, never colours."""
    tree = ast.parse(OPS_SRC.read_text())
    # Whole enum-member names, not substrings — "RED" lives inside "REQUIRED",
    # and a scan that cannot tell those apart would fail on correct code.
    members = {
        t.id
        for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
        for stmt in n.body if isinstance(stmt, ast.Assign)
        for t in stmt.targets if isinstance(t, ast.Name)
    }
    assert not (members & {"GREEN", "YELLOW", "ORANGE", "RED", "AMBER"}), members
    enums = {
        n.name for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef)
        and any(getattr(b, "id", getattr(b, "attr", "")) == "Enum" for b in n.bases)
    }
    # Ops-specific enums are fine; a rival HEALTH enum is not.
    assert "HealthClass" not in enums
    from saathi.platform.tg import trading_ops
    assert trading_ops.HealthClass.__module__ == \
        "saathi.platform.tg.paper_activation.ops.models"


def test_aggregation_is_the_existing_certified_aggregator():
    """Not a reimplementation with the same shape — literally the same function."""
    cases = [
        ("HEALTHY", "WARNING"), ("HEALTHY", "CRITICAL"),
        ("WARNING", "DEGRADED", "CRITICAL"), ("CRITICAL", "FAILED_SAFE"),
        ("HEALTHY",), ("DEGRADED", "DEGRADED"),
    ]
    for c in cases:
        assert worst_health(*c) == monitor_worst(*c), c


def test_degradation_policy_is_the_existing_resilience_table():
    for f in FailureMode:
        expected = {
            Response.CONTINUE_DEGRADED: HealthClass.WARNING.value,
            Response.HALT_NEW_ORDERS: HealthClass.DEGRADED.value,
            Response.RECONCILE_FIRST: HealthClass.CRITICAL.value,
            Response.FAIL_CLOSED: HealthClass.FAILED_SAFE.value,
        }[degrade(f).response]
        assert health_for_failure(f) == expected, f


# ── overall health precedence ───────────────────────────────────────────────
def test_one_critical_subsystem_is_not_diluted_by_seven_healthy_ones():
    """The explicit anti-averaging requirement."""
    subs = [_sub(f"S{i}", HealthClass.HEALTHY.value) for i in range(7)]
    subs.append(_sub(Subsystem.RISK.value, HealthClass.CRITICAL.value, cause="LIMIT_BREACH"))
    assert _snap(subs).overall_health == HealthClass.CRITICAL.value


def test_kill_switch_engaged_with_everything_else_healthy_is_failed_safe():
    snap = _snap(HEALTHY, kill_switch_state={"engaged": True, "reason": "operator halt",
                                             "scope": "GLOBAL", "engaged_at": AT})
    # FAILED_SAFE is CONTAINED, not chaotic — the distinction the brief insists on.
    assert snap.overall_health == HealthClass.FAILED_SAFE.value
    assert snap.recovery_state == RecoveryState.FAILED_SAFE.value
    assert snap.kill_switch_state["reason"] == "operator halt"


def test_reconciliation_required_prevents_a_healthy_readiness_claim():
    snap = _snap(HEALTHY, reconciliation_state=ReconciliationState.REQUIRED.value)
    assert snap.overall_health != HealthClass.HEALTHY.value
    assert snap.recovery_state == RecoveryState.RECONCILIATION_REQUIRED.value
    assert any(a.action == OperatorAction.REVIEW_RECONCILIATION.value
               for a in snap.operator_actions_required)


def test_strategy_watch_on_an_otherwise_healthy_system_stays_mild():
    subs = list(HEALTHY) + [_sub(Subsystem.STRATEGY.value, HealthClass.WARNING.value,
                                 cause="BENCHMARK_DRIFT")]
    assert _snap(subs).overall_health == HealthClass.WARNING.value


def test_guardian_unavailable_with_strategy_normal_still_degrades_the_system():
    subs = [_sub(Subsystem.GUARDIAN.value, HealthClass.CRITICAL.value, cause="GUARDIAN_UNAVAILABLE"),
            _sub(Subsystem.STRATEGY.value, HealthClass.HEALTHY.value)]
    snap = _snap(subs)
    assert snap.overall_health == HealthClass.CRITICAL.value


def test_guardian_blocking_correctly_is_not_a_guardian_failure():
    """Guardian doing its job must never read as Guardian broken."""
    subs = [_sub(Subsystem.GUARDIAN.value, HealthClass.HEALTHY.value,
                 cause="POLICY_ENFORCED", summary="42 intents blocked by policy")]
    snap = _snap(subs)
    assert snap.overall_health == HealthClass.HEALTHY.value
    assert snap.incidents == ()


# ── incident convergence ────────────────────────────────────────────────────
def test_one_root_cause_produces_one_incident_with_symptoms():
    """A feed outage that blocks a strategy is ONE incident, not two alerts."""
    subs = [
        _sub(Subsystem.MARKET_DATA.value, HealthClass.DEGRADED.value,
             cause="WEBSOCKET_DISCONNECT", summary="stream down"),
        _sub(Subsystem.STRATEGY.value, HealthClass.DEGRADED.value,
             cause="STRATEGY_DATA_QUALITY_BLOCKED", state="DATA_QUALITY_BLOCKED"),
        _sub(Subsystem.PORTFOLIO.value, HealthClass.DEGRADED.value, cause="NO_MARKS"),
    ]
    snap = _snap(subs)
    assert len(snap.incidents) == 1
    inc = snap.incidents[0]
    assert inc.subsystem == Subsystem.MARKET_DATA.value
    assert {s["subsystem"] for s in inc.symptoms} == {
        Subsystem.STRATEGY.value, Subsystem.PORTFOLIO.value}


def test_a_data_blocked_strategy_is_not_blamed_for_the_feed():
    subs = [
        _sub(Subsystem.MARKET_DATA.value, HealthClass.DEGRADED.value, cause="STALE_MARKET_DATA"),
        _sub(Subsystem.STRATEGY.value, HealthClass.DEGRADED.value,
             cause="STRATEGY_DATA_QUALITY_BLOCKED", state="DATA_QUALITY_BLOCKED"),
    ]
    actions = {a.action for a in _snap(subs).operator_actions_required}
    # NO_DATA_FAILURE_CLASSIFIED_AS_STRATEGY_FAILURE, at the action layer.
    assert OperatorAction.REVIEW_STRATEGY_DEGRADATION.value not in actions
    assert OperatorAction.RESTART_PUBLIC_FEED.value in actions or \
        OperatorAction.ACKNOWLEDGE_INCIDENT.value in actions


def test_a_genuinely_degraded_strategy_with_healthy_data_is_surfaced_as_such():
    subs = [
        _sub(Subsystem.MARKET_DATA.value, HealthClass.HEALTHY.value),
        _sub(Subsystem.STRATEGY.value, HealthClass.DEGRADED.value,
             cause="DRAWDOWN_BREACH", summary="drawdown beyond qualified envelope"),
    ]
    snap = _snap(subs)
    assert any(a.action == OperatorAction.REVIEW_STRATEGY_DEGRADATION.value
               for a in snap.operator_actions_required)
    assert snap.incidents[0].subsystem == Subsystem.STRATEGY.value


def test_repeated_evaluation_of_an_unchanged_condition_does_not_spam():
    subs = [_sub(Subsystem.MARKET_DATA.value, HealthClass.DEGRADED.value,
                 cause="STALE_MARKET_DATA", scope="BTCUSDT")]
    a = _snap(subs)
    b = _snap(subs)
    assert [i.dedup_key for i in a.incidents] == [i.dedup_key for i in b.incidents]
    assert a.snapshot_id == b.snapshot_id

    # Same condition observed twice in one pass is still one incident.
    twice, _ = converge_incidents(subs + subs, observed_at=AT)
    assert len(twice) == 1


def test_a_different_cause_or_scope_is_a_different_incident():
    base = dedup_key(Subsystem.MARKET_DATA.value, "STALE_MARKET_DATA", "BTCUSDT")
    assert base != dedup_key(Subsystem.MARKET_DATA.value, "SEQUENCE_GAP", "BTCUSDT")
    assert base != dedup_key(Subsystem.MARKET_DATA.value, "STALE_MARKET_DATA", "ETHUSDT")
    assert base == dedup_key(Subsystem.MARKET_DATA.value, "STALE_MARKET_DATA", "BTCUSDT")


def test_an_acknowledged_incident_stops_asking_to_be_acknowledged():
    subs = [_sub(Subsystem.MARKET_DATA.value, HealthClass.DEGRADED.value, cause="STALE_MARKET_DATA")]
    key = _snap(subs).incidents[0].dedup_key
    after = _snap(subs, acknowledged=(key,))
    assert after.incidents[0].acknowledged is True
    assert after.incidents[0].state == "ACKNOWLEDGED"
    assert not any(a.action == OperatorAction.ACKNOWLEDGE_INCIDENT.value
                   for a in after.operator_actions_required)


# ── recovery and non-retry ──────────────────────────────────────────────────
def test_an_ambiguous_order_outcome_requires_reconciliation_and_never_retries():
    """NO_UNKNOWN_AUTO_RETRY, inherited structurally from resilience.py."""
    assert recovery_for_failures([FailureMode.OMS_AMBIGUITY]) == \
        RecoveryState.RECONCILIATION_REQUIRED.value
    assert degrade(FailureMode.OMS_AMBIGUITY).auto_retry is False
    snap = _snap(HEALTHY, failures=[FailureMode.OMS_AMBIGUITY])
    actions = {a.action for a in snap.operator_actions_required}
    assert OperatorAction.REVIEW_RECONCILIATION.value in actions
    assert not any("RETRY" in a for a in actions)


def test_no_mapped_failure_mode_permits_automatic_retry():
    for f in FailureMode:
        assert degrade(f).auto_retry is False, f


def test_an_external_blocker_is_not_offered_as_a_retry():
    subs = [_sub(Subsystem.PROVIDER.value, HealthClass.DEGRADED.value,
                 cause="NEPSE_FEED_UNLICENSED", external_reason="LICENSE_REQUIRED")]
    snap = _snap(subs)
    acts = [a for a in snap.operator_actions_required
            if a.action == OperatorAction.EXTERNAL_ACTION_REQUIRED.value]
    assert acts, snap.operator_actions_required
    assert "cannot resolve this itself" in acts[0].detail
    assert acts[0].automatable is False


def test_provider_conditions_are_not_collapsed_into_offline():
    subs = [_sub(Subsystem.PROVIDER.value, HealthClass.DEGRADED.value,
                 cause="AUTH_EXPIRED", auth_required=True)]
    assert any(a.action == OperatorAction.REAUTHENTICATE_PROVIDER.value
               for a in _snap(subs).operator_actions_required)


# ── operator action ownership ───────────────────────────────────────────────
def test_every_operator_action_names_the_authority_that_owns_it():
    subs = [
        _sub(Subsystem.MARKET_DATA.value, HealthClass.DEGRADED.value, cause="STALE_MARKET_DATA"),
        _sub(Subsystem.STRATEGY.value, HealthClass.DEGRADED.value, cause="DRAWDOWN_BREACH"),
    ]
    snap = _snap(subs, reconciliation_state=ReconciliationState.REQUIRED.value,
                 failures=[FailureMode.STALE_MARKET_DATA])
    assert snap.operator_actions_required
    for a in snap.operator_actions_required:
        # No generic "Fix" button: an action with no owner cannot be acted on.
        assert a.authority and a.authority != "UNKNOWN", a
        assert a.action in {e.value for e in OperatorAction}


def test_every_subsystem_has_a_declared_authority():
    for s in Subsystem:
        assert AUTHORITY_OF.get(s), s


# ── mode integrity and readiness ────────────────────────────────────────────
@pytest.mark.parametrize("mode", [OpsMode.REPLAY, OpsMode.SHADOW, OpsMode.PAPER])
def test_mode_is_carried_verbatim(mode):
    assert _snap(HEALTHY, mode=mode.value).mode == mode.value


def test_live_is_not_an_available_mode():
    assert "LIVE" not in {m.value for m in OpsMode}


def test_a_perfectly_healthy_shadow_stack_is_still_not_live_authorised():
    """READINESS != HEALTH — the conflation the brief singles out."""
    snap = _snap(HEALTHY, mode=OpsMode.SHADOW.value)
    assert snap.overall_health == HealthClass.HEALTHY.value
    assert snap.live_trading_authorized is False
    assert snap.authorizes_execution is False


# ── determinism / restart ───────────────────────────────────────────────────
def test_the_aggregation_reads_no_clock():
    tree = ast.parse(OPS_SRC.read_text())
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


def test_the_same_inputs_reproduce_the_same_snapshot_across_a_restart():
    """Restart recovery: state is reconstructed, not remembered.

    The snapshot is derived, so a fresh process holding the same authority
    readings must land on the identical snapshot_id and the identical incident
    keys — no duplicate incident, no lost reconciliation, no false healthy.
    """
    subs = [
        _sub(Subsystem.MARKET_DATA.value, HealthClass.DEGRADED.value, cause="SEQUENCE_GAP"),
        _sub(Subsystem.SHADOW.value, HealthClass.CRITICAL.value, cause="RECONCILE"),
    ]
    kw = dict(reconciliation_state=ReconciliationState.REQUIRED.value,
              failures=[FailureMode.PROCESS_RESTART])
    before = _snap(subs, **kw)
    after = _snap(subs, **kw)

    assert before.snapshot_id == after.snapshot_id
    assert [i.dedup_key for i in before.incidents] == [i.dedup_key for i in after.incidents]
    assert after.reconciliation_state == ReconciliationState.REQUIRED.value
    assert after.overall_health != HealthClass.HEALTHY.value
    assert len({i.dedup_key for i in after.incidents}) == len(after.incidents)


def test_a_process_restart_reconciles_rather_than_resuming():
    assert recovery_for_failures([FailureMode.PROCESS_RESTART]) == \
        RecoveryState.RECONCILIATION_REQUIRED.value


# ── real-authority integration ──────────────────────────────────────────────
def test_the_kill_switch_state_comes_from_the_real_kill_switch_authority():
    ks = KillSwitchStore()
    ks.activate(scope="GLOBAL", reason="ops test halt", activated_by="operator")
    status = ks.status()
    assert status
    snap = _snap(HEALTHY, kill_switch_state={
        "engaged": True, "reason": status[0].get("reason"), "scope": status[0].get("scope"),
    })
    assert snap.overall_health == HealthClass.FAILED_SAFE.value
    assert snap.kill_switch_state["reason"] == "ops test halt"


def test_a_real_degraded_strategy_verdict_flows_into_the_ops_snapshot(tmp_path):
    """End to end over real components: shadow -> observation -> monitor -> ops."""
    store = ShadowSessionStore(research_store=ResearchStore(db_path=tmp_path / "s.sqlite3"))
    sid = store.open_session(
        mode=ShadowMode.REPLAY, market="CRYPTO", strategy_version="s@1",
        policy_versions={"guardian": "v2"}, feed_ref="replay:x",
        opening_cash="250000", started_at="2026-09-01T00:00:00Z", benchmark="B",
    )
    seq = 1
    for i in range(25):
        for side, px in (("BUY", "100"), ("SELL", "101")):
            store.append_event(sid, seq, ShadowEventKind.HYPOTHETICAL_FILL, {"i": i},
                               observed_at=f"2026-09-{1 + i:02d}T00:00:00Z")
            store.record_fill(sid, seq, symbol="BTCUSDT", side=side, quantity="10",
                              reference_price=px, fill_price=px, fee="1",
                              spread_cost="0.5", slippage_cost="0.5")
            seq += 1

    result = observation_from_shadow(
        store, sid, average_portfolio_value="250000",
        equity_path=["250000", "260000", "190000"],  # a real, large drawdown
        current_regime="TREND", regimes_seen=("TREND",),
    )
    verdict = evaluate_strategy_health(
        QualificationEnvelope(strategy_id="s@1", strategy_version="1",
                              qualification_sha="a" * 16, benchmark_version="B",
                              qualified_max_drawdown=Decimal("0.15"),
                              qualified_regimes=("TREND",)),
        result.observation,
    )
    store.close()
    assert verdict.health == StrategyHealth.DEGRADED.value

    # The monitor's verdict maps into the ops vocabulary without restatement.
    snap = _snap([
        _sub(Subsystem.MARKET_DATA.value, HealthClass.HEALTHY.value),
        _sub(Subsystem.STRATEGY.value, HealthClass.DEGRADED.value,
             cause="STRATEGY_DEGRADED", state=verdict.health,
             summary="drawdown beyond qualified envelope"),
    ])
    assert snap.overall_health == HealthClass.DEGRADED.value
    assert any(a.action == OperatorAction.REVIEW_STRATEGY_DEGRADATION.value
               for a in snap.operator_actions_required)


def test_a_shadow_reconciliation_failure_reaches_the_operator(tmp_path):
    store = ShadowSessionStore(research_store=ResearchStore(db_path=tmp_path / "s.sqlite3"))
    sid = store.open_session(
        mode=ShadowMode.REPLAY, market="CRYPTO", strategy_version="s@1",
        policy_versions={}, feed_ref="replay:x", opening_cash="100000",
        started_at="2026-09-01T00:00:00Z",
    )
    # A fill with no event behind it — history that does not explain itself.
    store.record_fill(sid, 900, symbol="BTCUSDT", side="BUY", quantity="1",
                      reference_price="10", fill_price="10", fee="0")
    recon = store.reconcile(sid)
    store.close()
    assert recon["ok"] is False

    snap = _snap(
        [_sub(Subsystem.SHADOW.value, HealthClass.CRITICAL.value, cause="ORPHAN_FILL")],
        reconciliation_state=ReconciliationState.FAILED.value,
    )
    assert snap.overall_health == HealthClass.CRITICAL.value
    assert any(a.action == OperatorAction.REVIEW_RECONCILIATION.value
               for a in snap.operator_actions_required)


# ── authority containment ───────────────────────────────────────────────────
def test_trading_ops_holds_no_execution_authority():
    """Static proof. Supervision that can trade is not supervision."""
    tree = ast.parse(OPS_SRC.read_text())
    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                called.add(n.func.id)
    forbidden = {
        "submit", "place", "send_order", "create_order", "cancel", "reserve",
        "reserve_cash", "consume", "approve", "activate", "deactivate", "promote",
        "set_limit", "set_policy", "mutate", "commit", "execute", "record_fill",
        "append_event", "with_tx",
    }
    assert not (forbidden & called), forbidden & called


def test_trading_ops_imports_no_broker_ledger_or_policy_mutator():
    tree = ast.parse(OPS_SRC.read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    banned = ("broker", "fund_ledger", "execution", "oms", "venue", "binance")
    hits = [m for m in mods if any(b in m.lower() for b in banned)]
    assert not hits, hits


def test_the_snapshot_never_claims_execution_authority():
    snap = _snap(HEALTHY)
    pub = snap.to_public()
    assert pub["authorizes_execution"] is False
    assert pub["live_trading_authorized"] is False
    assert set(pub["health_classes"]) == {h.value for h in HealthClass}


def test_no_credential_material_can_enter_a_snapshot_payload():
    """Ops payloads are shown to operators and logged; secrets must not ride along."""
    import json
    subs = [_sub(Subsystem.PROVIDER.value, HealthClass.DEGRADED.value, cause="AUTH_EXPIRED",
                 auth_required=True, summary="provider authentication required")]
    blob = json.dumps(_snap(subs).to_public(), default=str).lower()
    for marker in ("api_key", "secret", "password", "bearer", "token=", "authorization"):
        assert marker not in blob, marker


def test_causal_parents_never_form_a_cycle():
    """A cycle would make convergence order-dependent, i.e. nondeterministic."""
    for child, parents in CAUSAL_PARENTS.items():
        for p in parents:
            assert child not in CAUSAL_PARENTS.get(p, ()), (child, p)


def test_every_failure_mode_is_owned_by_a_subsystem_that_can_act_on_it():
    """An action addressed to the wrong owner is worse than no action."""
    for f in FailureMode:
        owner = SUBSYSTEM_FOR_FAILURE.get(f)
        assert owner is not None, f
        assert AUTHORITY_OF.get(owner), (f, owner)
    # Spot-check the routing the first draft got wrong.
    assert SUBSYSTEM_FOR_FAILURE[FailureMode.DISK_PRESSURE] is Subsystem.PAPER
    assert SUBSYSTEM_FOR_FAILURE[FailureMode.KILL_SWITCH] is Subsystem.KILL_SWITCH


def test_a_provider_outage_does_not_also_raise_a_market_data_incident():
    subs = [
        _sub(Subsystem.PROVIDER.value, HealthClass.DEGRADED.value, cause="PROVIDER_OUTAGE"),
        _sub(Subsystem.MARKET_DATA.value, HealthClass.DEGRADED.value, cause="NO_TICKS"),
        _sub(Subsystem.STRATEGY.value, HealthClass.DEGRADED.value,
             cause="STRATEGY_DATA_QUALITY_BLOCKED", state="DATA_QUALITY_BLOCKED"),
    ]
    snap = _snap(subs)
    assert len(snap.incidents) == 1
    assert snap.incidents[0].subsystem == Subsystem.PROVIDER.value
    assert {s["subsystem"] for s in snap.incidents[0].symptoms} == {
        Subsystem.MARKET_DATA.value, Subsystem.STRATEGY.value}


def test_an_unrecognised_subsystem_is_reported_rather_than_dropped():
    snap = _snap([_sub("SOME_FUTURE_SUBSYSTEM", HealthClass.CRITICAL.value, cause="X")])
    assert snap.overall_health == HealthClass.CRITICAL.value
    assert authority_for("SOME_FUTURE_SUBSYSTEM") == "UNKNOWN"
    assert len(snap.subsystems) == 1


def test_no_failing_subsystem_is_ever_lost_from_the_incident_tree():
    """The invariant behind the symptom-of-a-symptom defect.

    Convergence reduces ALERTS, never CONDITIONS. Every failing subsystem must
    appear exactly once — as a primary incident or as a symptom of one — because
    a condition that is neither has silently vanished from the operator's view.
    """
    chains = [
        # provider -> market data -> strategy -> portfolio, a three-deep chain
        [(Subsystem.PROVIDER.value, "OUTAGE"), (Subsystem.MARKET_DATA.value, "NO_TICKS"),
         (Subsystem.STRATEGY.value, "BLOCKED"), (Subsystem.PORTFOLIO.value, "NO_MARKS")],
        # a mid-chain root: market data fails with the provider healthy
        [(Subsystem.MARKET_DATA.value, "STALE"), (Subsystem.SHADOW.value, "NO_PRICES")],
        # unrelated roots must stay separate incidents
        [(Subsystem.GUARDIAN.value, "UNAVAILABLE"), (Subsystem.RISK.value, "LIMIT")],
    ]
    for chain in chains:
        subs = [_sub(s, HealthClass.DEGRADED.value, cause=c) for s, c in chain]
        incidents, _ = converge_incidents(subs, observed_at=AT)
        seen = set()
        for inc in incidents:
            assert inc.subsystem not in seen
            seen.add(inc.subsystem)
            for sym in inc.symptoms:
                assert sym["subsystem"] not in seen
                seen.add(sym["subsystem"])
        assert seen == {s for s, _ in chain}, (chain, seen)


def test_the_render_edge_maps_onto_the_existing_panel_vocabulary():
    """Converge with CommandSurface instead of forking a third vocabulary."""
    from saathi.platform.tg.command_surface import PanelStatus

    valid = {p.value for p in PanelStatus}
    for h in HealthClass:
        assert panel_status_for(h.value) in valid, h
    assert panel_status_for(HealthClass.HEALTHY.value) == PanelStatus.OK.value
    assert panel_status_for(HealthClass.CRITICAL.value) == PanelStatus.BLOCKED.value
    assert panel_status_for(HealthClass.FAILED_SAFE.value) == PanelStatus.BLOCKED.value
    # An unknown health must never render as OK.
    assert panel_status_for("SOMETHING_NEW") == PanelStatus.UNKNOWN.value


def test_contained_and_ambiguous_failure_stay_distinct_in_the_record():
    """They render alike; they must not be recorded alike."""
    contained = _snap(HEALTHY, kill_switch_state={"engaged": True, "reason": "halt"})
    ambiguous = _snap([_sub(Subsystem.RECONCILIATION.value, HealthClass.CRITICAL.value,
                            cause="OMS_AMBIGUITY")])
    assert contained.overall_health == HealthClass.FAILED_SAFE.value
    assert ambiguous.overall_health == HealthClass.CRITICAL.value
    assert contained.overall_health != ambiguous.overall_health
    assert panel_status_for(contained.overall_health) == \
        panel_status_for(ambiguous.overall_health)
