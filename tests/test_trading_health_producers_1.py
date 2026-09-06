"""TRADING-HEALTH-PRODUCERS-1 — typed health for the five safety-critical domains.

These producers are what turn TRADING-OPS-1's correctly-typed UNKNOWN fields into
real evidence. The tests are organised around the three rules that decide every
mapping: health is not readiness, missing evidence is never healthy, and
containment is not collapse.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from saathi.platform.tg.health_producers import (
    ALL_PRODUCERS,
    InvalidHealthCount,
    HEALTH_FOR_PROVIDER_STATE,
    PRODUCED_SUBSYSTEMS,
    HealthMode,
    ProducedHealth,
    StateCode,
    approval_health,
    execution_gateway_health,
    guardian_health,
    market_data_health,
    provider_health,
    snapshot_from_producers,
)
from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.tg.trading_ops import (
    OperatorAction,
    OpsMode,
    ReconciliationState,
    Subsystem,
    build_snapshot,
)

SRC = Path("saathi/platform/tg/health_producers.py")
AT = "2026-09-06T12:00:00Z"

HEALTHY_FIVE = dict(
    market=dict(connected=True, freshness="FRESH", source="GOVERNED_DATASET"),
    provider=dict(provider_id="binance.public", state="HEALTHY"),
    guardian=dict(policy_loaded=True, policy_version="v2"),
    gateway=dict(gateway_available=True),
    approval=dict(service_available=True),
)


def _five(**over):
    cfg = {k: dict(v) for k, v in HEALTHY_FIVE.items()}
    for k, v in over.items():
        cfg[k].update(v)
    return [
        market_data_health(observed_at=AT, **cfg["market"]),
        provider_health(observed_at=AT, **cfg["provider"]),
        guardian_health(observed_at=AT, **cfg["guardian"]),
        execution_gateway_health(observed_at=AT, **cfg["gateway"]),
        approval_health(observed_at=AT, **cfg["approval"]),
    ]


def _snap(healths, **kw):
    return snapshot_from_producers(
        healths, observed_at=AT, mode=OpsMode.SHADOW.value, **kw)


# ── vocabulary and contract ─────────────────────────────────────────────────
def test_every_producer_emits_only_canonical_health_classes():
    valid = {h.value for h in HealthClass}
    for h in _five():
        assert h.health_class in valid, h
    for _, (health, _) in HEALTH_FOR_PROVIDER_STATE.items():
        assert health in valid


def test_no_parallel_health_vocabulary_is_introduced():
    tree = ast.parse(SRC.read_text())
    members = {
        t.id
        for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
        for stmt in n.body if isinstance(stmt, ast.Assign)
        for t in stmt.targets if isinstance(t, ast.Name)
    }
    assert not (members & {"GREEN", "AMBER", "RED", "YELLOW", "BROKEN"}), members
    from saathi.platform.tg import health_producers
    assert health_producers.HealthClass.__module__ == \
        "saathi.platform.tg.paper_activation.ops.models"


def test_no_producer_can_imply_live_trading():
    assert "LIVE_TRADING" not in {m.value for m in HealthMode}
    assert "LIVE" not in {m.value for m in HealthMode}
    for h in _five():
        assert h.authorizes_execution is False


def test_every_produced_subsystem_has_a_declared_authority():
    for h in _five():
        assert h.authority and h.authority != "UNKNOWN", h.subsystem


# ── rule: missing evidence is never healthy ─────────────────────────────────
@pytest.mark.parametrize("producer,kwargs", [
    (market_data_health, {}),
    (provider_health, {"provider_id": "p"}),
    (guardian_health, {}),
    (execution_gateway_health, {}),
    (approval_health, {}),
])
def test_no_producer_defaults_to_healthy_without_evidence(producer, kwargs):
    """NO_DEFAULT_HEALTHY_ON_MISSING_EVIDENCE, for all five."""
    h = producer(**kwargs)
    assert h.health_class != HealthClass.HEALTHY.value
    assert h.evidence_sufficient is False
    assert h.state_code == StateCode.INSUFFICIENT_EVIDENCE.value
    # Never silently absent: the operator is told to check by hand.
    assert h.operator_action_required == OperatorAction.MANUAL_OPERATOR_VALIDATION.value


def test_an_unknown_provider_state_is_insufficient_not_healthy():
    h = provider_health(provider_id="p", state="UNKNOWN")
    assert h.evidence_sufficient is False
    assert h.health_class != HealthClass.HEALTHY.value


def test_unknown_freshness_is_insufficient_not_fresh():
    h = market_data_health(connected=True, freshness="UNKNOWN")
    assert h.state_code == StateCode.INSUFFICIENT_EVIDENCE.value


# ── rule: health is not readiness ───────────────────────────────────────────
def test_live_execution_disabled_by_policy_is_healthy_not_critical():
    """The designed posture must not render as a permanent fault."""
    h = execution_gateway_health(gateway_available=True, live_execution_enabled=False,
                                 paper_ready=True)
    assert h.health_class == HealthClass.HEALTHY.value
    assert StateCode.LIVE_EXECUTION_DISABLED.value in h.capabilities
    assert h.state_code == StateCode.PAPER_ONLY_READY.value


def test_a_provider_disabled_by_policy_is_healthy():
    assert provider_health(provider_id="p", state="DISABLED").health_class == \
        HealthClass.HEALTHY.value


def test_public_market_data_never_implies_a_trading_account():
    h = provider_health(provider_id="binance.public", state="HEALTHY",
                        scope="PUBLIC_MARKET_DATA")
    assert h.capabilities == ("PUBLIC_MARKET_DATA",)
    assert "TRADING_ACCOUNT" not in h.capabilities
    assert h.mode in {HealthMode.PUBLIC_DATA_ONLY.value, HealthMode.LIVE_PUBLIC_DATA.value}


def test_a_replay_feed_is_healthy_and_labelled_replay():
    """NO_FALSE_LIVE_LABEL: healthy for what it is, never claiming to be live."""
    h = market_data_health(connected=True, freshness="FRESH", source="GOVERNED_DATASET")
    assert h.health_class == HealthClass.HEALTHY.value
    assert h.mode == HealthMode.REPLAY.value
    assert h.mode != HealthMode.LIVE_PUBLIC_DATA.value


def test_a_fixture_feed_is_not_labelled_live():
    assert market_data_health(connected=True, freshness="FRESH",
                              source="OFFLINE_FIXTURE").mode == HealthMode.FIXTURE.value


# ── rule: containment is not collapse ───────────────────────────────────────
def test_reconnect_exhaustion_under_containment_is_failed_safe_not_critical():
    contained = market_data_health(connected=False, freshness="STALE",
                                   reconnect_exhausted=True, contained=True)
    uncontained = market_data_health(connected=False, freshness="STALE",
                                     reconnect_exhausted=True, contained=False)
    assert contained.health_class == HealthClass.FAILED_SAFE.value
    assert contained.failed_safe is True
    # Still serving while unable to refresh is the dangerous case.
    assert uncontained.health_class == HealthClass.CRITICAL.value


def test_an_engaged_kill_switch_is_failed_safe_at_the_gateway():
    h = execution_gateway_health(gateway_available=True, kill_switch_engaged=True)
    assert h.health_class == HealthClass.FAILED_SAFE.value
    assert h.failed_safe is True


def test_an_unavailable_approval_store_that_fails_closed_is_failed_safe():
    assert approval_health(service_available=False, contained=True).health_class == \
        HealthClass.FAILED_SAFE.value
    assert approval_health(service_available=False, contained=False).health_class == \
        HealthClass.CRITICAL.value


# ── Guardian: blocking is not failing ───────────────────────────────────────
@pytest.mark.parametrize("blocked", [0, 1, 42, 100, 10_000])
def test_guardian_health_is_independent_of_how_much_it_blocks(blocked):
    """The single most important classification rule in this milestone."""
    h = guardian_health(policy_loaded=True, policy_version="v2", blocked_count=blocked)
    assert h.health_class == HealthClass.HEALTHY.value
    assert h.state_code == StateCode.POLICY_LOADED.value
    # Visible to the operator as context, provably not an input.
    assert h.data_quality["blocked_count"] == blocked


def test_the_block_count_is_not_read_by_the_classifier():
    """Structural: the classification branches never reference blocked_count."""
    tree = ast.parse(SRC.read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "guardian_health")
    for node in ast.walk(fn):
        if isinstance(node, (ast.If, ast.Compare, ast.BoolOp)):
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            assert "blocked_count" not in names, ast.dump(node)[:200]


def test_guardian_without_required_inputs_is_contained_not_broken():
    h = guardian_health(policy_loaded=True, required_inputs_available=False, fail_closed=True)
    assert h.health_class == HealthClass.FAILED_SAFE.value
    assert h.state_code == StateCode.REQUIRED_INPUT_UNAVAILABLE.value


def test_a_missing_or_invalid_policy_fails_closed():
    assert guardian_health(policy_loaded=False, fail_closed=True).health_class == \
        HealthClass.FAILED_SAFE.value
    assert guardian_health(policy_loaded=False, fail_closed=False).health_class == \
        HealthClass.CRITICAL.value
    assert guardian_health(policy_loaded=True, policy_valid=False).state_code == \
        StateCode.POLICY_INVALID.value


def test_a_guardian_bypass_is_critical_and_never_failed_safe():
    """Nothing is contained if the gate can be walked around."""
    h = guardian_health(policy_loaded=True, bypass_detected=True)
    assert h.health_class == HealthClass.CRITICAL.value
    assert h.failed_safe is False
    assert h.operator_action_required == OperatorAction.ENGAGE_EXISTING_KILL_SWITCH.value


# ── gateway: unknown execution state ────────────────────────────────────────
def test_unknown_execution_state_is_critical_and_demands_reconciliation():
    h = execution_gateway_health(gateway_available=True, unknown_execution_state=True)
    assert h.health_class == HealthClass.CRITICAL.value
    assert h.operator_action_required == OperatorAction.REVIEW_RECONCILIATION.value


def test_no_producer_can_retry_anything():
    """NO_UNKNOWN_AUTO_RETRY, structurally: these functions call nothing."""
    tree = ast.parse(SRC.read_text())
    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                called.add(n.func.id)
    assert not ({"retry", "resubmit", "resend", "reconnect", "recover"} & called), called


# ── approval: a queue is not a fault ────────────────────────────────────────
@pytest.mark.parametrize("pending,expired", [(0, 0), (5, 0), (0, 9), (50, 50)])
def test_pending_and_expired_approvals_do_not_move_health(pending, expired):
    h = approval_health(service_available=True, pending=pending, expired=expired)
    assert h.health_class == HealthClass.HEALTHY.value
    assert h.data_quality == {"pending": pending, "expired": expired}


def test_a_broken_duplicate_consumption_guard_is_critical():
    """An approval that can be spent twice is indistinguishable from none."""
    h = approval_health(service_available=True, duplicate_guard_ok=False)
    assert h.health_class == HealthClass.CRITICAL.value
    assert h.state_code == StateCode.DUPLICATE_CONSUMPTION_GUARD_BROKEN.value


def test_an_unknown_approval_state_degrades_rather_than_passes():
    assert approval_health(service_available=True, unknown_state_count=2).health_class == \
        HealthClass.DEGRADED.value


# ── provider: conditions stay distinct ──────────────────────────────────────
def test_provider_conditions_are_not_collapsed_into_offline():
    seen = {provider_health(provider_id="p", state=s).state_code
            for s in HEALTH_FOR_PROVIDER_STATE}
    # Nine source states must not funnel into one code.
    assert len(seen) >= 6, seen


def test_a_licence_requirement_is_external_and_never_a_retry():
    h = provider_health(provider_id="nepse.licensed", state="UNAVAILABLE",
                        external_blocker="LICENSE_REQUIRED")
    assert h.state_code == StateCode.EXTERNAL_LICENSE_REQUIRED.value
    assert h.operator_action_required == OperatorAction.EXTERNAL_ACTION_REQUIRED.value
    assert "not resolvable by retry" in h.detail


def test_auth_required_asks_for_reauthentication_not_a_feed_restart():
    assert provider_health(provider_id="p", state="AUTH_BLOCKED").operator_action_required == \
        OperatorAction.REAUTHENTICATE_PROVIDER.value


# ── UNKNOWN reduction ───────────────────────────────────────────────────────
def test_before_wiring_the_five_subsystems_are_absent_from_the_snapshot():
    """The 'before' half of the UNKNOWN-reduction proof."""
    bare = build_snapshot(observed_at=AT, mode=OpsMode.SHADOW.value, subsystems=[])
    assert {s.subsystem for s in bare.subsystems} == set()


def test_after_wiring_all_five_subsystems_are_populated():
    snap = _snap(_five())
    populated = {s.subsystem for s in snap.subsystems}
    assert set(PRODUCED_SUBSYSTEMS) <= populated
    assert len(populated) == 5
    for s in snap.subsystems:
        assert s.health in {h.value for h in HealthClass}
        assert s.authority != "UNKNOWN"


def test_a_fully_healthy_stack_reports_healthy_and_still_not_live_authorised():
    snap = _snap(_five())
    assert snap.overall_health == HealthClass.HEALTHY.value
    assert snap.live_trading_authorized is False
    assert snap.authorizes_execution is False
    assert snap.incidents == ()


# ── multi-fault precedence ──────────────────────────────────────────────────
def test_stale_data_with_everything_else_healthy_degrades_the_system():
    snap = _snap(_five(market={"freshness": "STALE"}))
    assert snap.overall_health == HealthClass.DEGRADED.value
    assert snap.incidents[0].subsystem == Subsystem.MARKET_DATA.value


def test_guardian_blocking_with_all_else_healthy_is_not_degraded():
    snap = _snap(_five(guardian={"blocked_count": 250}))
    assert snap.overall_health == HealthClass.HEALTHY.value
    assert snap.incidents == ()


def test_gateway_live_disabled_with_paper_healthy_is_healthy():
    snap = _snap(_five(gateway={"live_execution_enabled": False, "paper_ready": True}))
    assert snap.overall_health == HealthClass.HEALTHY.value


def test_a_failed_safe_approval_store_blocks_readiness_even_if_all_else_is_well():
    snap = _snap(_five(approval={"service_available": False}))
    assert snap.overall_health == HealthClass.FAILED_SAFE.value


def test_a_guardian_bypass_outranks_a_stale_feed():
    snap = _snap(_five(market={"freshness": "STALE"},
                       guardian={"bypass_detected": True}))
    assert snap.overall_health == HealthClass.CRITICAL.value


def test_reconciliation_required_at_the_gateway_reaches_the_operator():
    snap = _snap(_five(gateway={"reconciliation_required": True}),
                 reconciliation_state=ReconciliationState.REQUIRED.value)
    assert snap.overall_health == HealthClass.CRITICAL.value
    assert any(a.action == OperatorAction.REVIEW_RECONCILIATION.value
               for a in snap.operator_actions_required)


# ── root-cause correlation survives the wiring ──────────────────────────────
def test_a_provider_outage_still_converges_to_one_incident():
    """TRADING-OPS-1's convergence must not be defeated by real producers."""
    snap = _snap(
        _five(provider={"state": "UNAVAILABLE"}, market={"freshness": "STALE"}),
        extra_findings=[{
            "subsystem": Subsystem.STRATEGY.value, "health": HealthClass.DEGRADED.value,
            "cause": "STRATEGY_DATA_QUALITY_BLOCKED", "state": "DATA_QUALITY_BLOCKED",
        }],
    )
    assert len(snap.incidents) == 1
    assert snap.incidents[0].subsystem == Subsystem.PROVIDER.value
    assert {s["subsystem"] for s in snap.incidents[0].symptoms} == {
        Subsystem.MARKET_DATA.value, Subsystem.STRATEGY.value}
    # And the strategy is still not blamed for the feed.
    assert not any(a.action == OperatorAction.REVIEW_STRATEGY_DEGRADATION.value
                   for a in snap.operator_actions_required)


def test_repeated_production_of_the_same_state_is_one_incident():
    a = _snap(_five(market={"freshness": "STALE"}))
    b = _snap(_five(market={"freshness": "STALE"}))
    assert a.snapshot_id == b.snapshot_id
    assert [i.dedup_key for i in a.incidents] == [i.dedup_key for i in b.incidents]


# ── read-only / authority containment ───────────────────────────────────────
def test_producers_hold_no_execution_or_mutation_authority():
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
        "activate", "deactivate", "force_state", "observe_error", "observe_success",
        "set_limit", "set_policy", "commit", "with_tx", "freeze", "transition",
    }
    assert not (forbidden & called), forbidden & called


def test_producers_import_no_mutating_authority():
    tree = ast.parse(SRC.read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    banned = ("approvals", "broker", "fund_ledger", "execution", "oms", "venue",
              "binance", "kill_switch", "policy")
    hits = [m for m in mods if any(b in m.lower() for b in banned)]
    assert not hits, hits


def test_no_producer_consumes_an_approval():
    """APPROVAL_CONSUMPTIONS = 0, proven against the real approval centre.

    The centre is driven directly to create a real APPROVED approval, then every
    producer runs. If any of them touched the approval authority, the approval
    would come back CONSUMED.
    """
    from saathi.platform.tg.paper_activation.approvals import ActivationApprovalCenter
    from saathi.platform.tg.paper_activation.models import ActivationApprovalStatus

    center = ActivationApprovalCenter()
    ap = center.request(
        strategy_slug="s", reason="producer read-only proof",
        operator_id="op-1", operator_identity="human:operator",
    )
    center.decide(ap.id, decision="approve", operator_id="op-1",
                  operator_identity="human:operator", notes="approved for test")
    before = center.get(ap.id).status

    for h in _five():
        assert isinstance(h, ProducedHealth)
    _snap(_five())

    after = center.get(ap.id).status
    assert before == after == ActivationApprovalStatus.APPROVED
    assert after != ActivationApprovalStatus.CONSUMED


def test_producers_take_state_not_the_mutating_accessors():
    """The two mutating reads discovery found must not be inherited.

    `ActivationApprovalCenter.get/list` lazily expire approvals and
    `ProviderHealthTracker.get` inserts a record for an unseen provider. Both are
    legitimate in their own modules; neither may be triggered by a health read,
    so the producers accept plain state instead of those objects.
    """
    import inspect

    for producer in ALL_PRODUCERS:
        params = inspect.signature(producer).parameters
        for name, p in params.items():
            assert p.kind is inspect.Parameter.KEYWORD_ONLY, (producer.__name__, name)
            assert not name.endswith(("_center", "_tracker", "_store", "_service_obj"))


def test_producers_read_no_clock():
    tree = ast.parse(SRC.read_text())
    imported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            imported.add(n.module.split(".")[0])
    assert not ({"datetime", "time", "calendar"} & imported), imported


def test_no_credential_material_can_enter_a_produced_payload():
    import json

    healths = _five(provider={"state": "AUTH_BLOCKED", "last_error": "auth failed"})
    blob = json.dumps(_snap(healths).to_public(), default=str).lower()
    for marker in ("api_key", "secret", "password", "bearer", "token=", "authorization"):
        assert marker not in blob, marker


def test_a_connected_feed_that_reports_no_freshness_is_not_healthy():
    """Connectivity is not freshness.

    A socket that stays up while no rows arrive is the classic silent feed
    failure. An earlier draft let `connected=True` alone reach the HEALTHY branch
    and report FEED_FRESH, which would have told an operator the feed was fine on
    the strength of a TCP connection.
    """
    h = market_data_health(connected=True)
    assert h.health_class != HealthClass.HEALTHY.value
    assert h.state_code == StateCode.INSUFFICIENT_EVIDENCE.value
    assert h.evidence_sufficient is False
    assert "freshness not reported" in h.detail


def test_a_disconnect_is_still_reported_as_a_fault_not_as_missing_evidence():
    """Positive evidence of a problem must not be softened into 'unknown'."""
    h = market_data_health(connected=False)
    assert h.health_class == HealthClass.DEGRADED.value
    assert h.state_code == StateCode.FEED_DISCONNECTED.value
    assert h.evidence_sufficient is True


def test_a_sequence_gap_is_a_fault_even_with_no_freshness_reported():
    h = market_data_health(connected=True, sequence_gap=True)
    assert h.state_code == StateCode.SEQUENCE_GAP.value
    assert h.health_class == HealthClass.DEGRADED.value


# ── numeric safety on count metrics ─────────────────────────────────────────
@pytest.mark.parametrize("bad", [True, False, float("nan"), float("inf"),
                                 float("-inf"), -1, 1.5, "3", object()])
def test_a_count_that_cannot_be_trusted_is_refused_not_coerced(bad):
    """`unknown_state_count` GATES a branch, so a bad value invents a fact.

    `True` is an int in Python and NaN is truthy, so either would read as "there
    is at least one approval in an unknown state" — a claim nobody made.
    """
    with pytest.raises(InvalidHealthCount):
        approval_health(service_available=True, unknown_state_count=bad)


@pytest.mark.parametrize("bad", [True, float("nan"), -5, "10"])
def test_a_bad_block_count_is_refused_rather_than_recorded(bad):
    with pytest.raises(InvalidHealthCount):
        guardian_health(policy_loaded=True, blocked_count=bad)


def test_an_absent_count_stays_absent_and_never_becomes_zero():
    h = approval_health(service_available=True)
    assert h.data_quality["pending"] is None
    assert h.data_quality["expired"] is None
    assert guardian_health(policy_loaded=True).data_quality["blocked_count"] is None


def test_a_whole_float_count_is_accepted_as_the_integer_it_is():
    h = approval_health(service_available=True, pending=3.0)
    assert h.data_quality["pending"] == 3
    assert isinstance(h.data_quality["pending"], int)
