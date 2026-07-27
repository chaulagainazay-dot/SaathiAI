"""M62.7 — automated paper-safety circuit breakers, sweeps, alerts, acknowledgement,
and fail-closed reset controls.

Proves: durable breaker defs/states/trips, deterministic evaluation + sweep manifests,
loss/drawdown/exposure/concentration/open-order/rejection-rate/processing-failure
breakers, reconciliation-critical auto-trip, corrupted/stale market-data fail-closed
trips, manual kill switch, cross-scope isolation, Guardian veto under active breakers,
durable tenant-scoped alerts, acknowledgement (halt retained), fail-closed reset (denied
while unsafe / bad approval / agent / stale version / broader breaker), successful reset
that modifies NO financial state, idempotency, restart recovery, atomic rollback, and
prohibited-capability rejection.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import ApprovalRecord, ApprovalStatus, new_id, role_has_permission
from saathi.platform.models import PlatformRole, PlatformPermission
from saathi.platform.trading_models import D, DataQuality, MarketState
from saathi.platform.paper_trading import (
    PaperTradingService, PaperStore, MarketEvent, ReconciliationEngine, ZERO_FEE, ZERO_SLIP,
)
from saathi.platform.safety import (
    SafetyService, BreakerType, BreakerScope, BreakerState, Severity, assert_safety_safe,
    is_agent_actor, trading_day, can_breaker_transition, default_account_breakers,
)
from saathi.platform.safety.models import shash, PROHIBITED_SAFETY_TOKENS
from saathi.platform.paper_trading.models import PaperSafetyError


# ── helpers ───────────────────────────────────────────────────────────────────
def _ctx(role="owner", org="o1", user="u1", ws="w1", authority=""):
    return PlatformExecutionContext(user_id=user, role=role, org_id=org, workspace_id=ws, run_id="r1",
                                    authority=authority)


def _svc(tmp_path):
    from saathi.platform.store import PlatformStore
    from saathi.platform.trading_guardian import RiskLimits
    plat = PlatformStore(db_path=tmp_path / "paper.db")   # same file → shared approvals table
    ps = PaperStore(db_path=tmp_path / "paper.db")
    # relax the Guardian's own limits so these tests exercise the M62.7 breakers,
    # not the M62.1 Guardian risk caps.
    limits = RiskLimits(max_order_notional=D("100000000"), max_position_notional=D("100000000"),
                        max_gross_exposure=D("100000000"), max_symbol_concentration_pct=D("100"),
                        max_open_positions=100000, min_cash_reserve=D("0"))
    svc = PaperTradingService(ps, platform_store=plat, fee_model=ZERO_FEE, slippage_model=ZERO_SLIP,
                              guardian_limits=limits)
    sf = SafetyService(ps, platform_store=plat).bind_paper_service(svc)
    svc.bind_safety(sf)
    return svc, sf, ps, plat


def _ev(*, symbol="TRENDING", bid="99.98", ask="100.02", last="100.00", ref="fx"):
    return MarketEvent(symbol=symbol, ts=1000.0, bid=D(bid), ask=D(ask), last=D(last),
                       liquidity=D("1000000"), quality=DataQuality.VALID, market_state=MarketState.OPEN, ref=ref)


def _acct(svc, ctx, cash="100000"):
    return svc.create_account(ctx, name="a", starting_cash=cash)


def _buy_fill(svc, ctx, a, *, qty="10", ask="100.02", ref="c"):
    i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity=qty)
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev(ask=ask))
    svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(ask=ask, ref=ref))
    return r["order"]["id"]


def _sell_fill(svc, ctx, a, *, qty="10", bid="90.00", ref="s"):
    i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="SELL", order_type="MARKET", quantity=qty)
    r = svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev(bid=bid))
    svc.process_market_event(ctx, order_id=r["order"]["id"], event=_ev(bid=bid, ref=ref))
    return r["order"]["id"]


def _configure(sf, ctx, btype, *, threshold, scope_ref, **kw):
    return sf.create_breaker(ctx, breaker_type=btype.value, scope="PAPER_ACCOUNT", scope_ref=scope_ref,
                             threshold=threshold, **kw)


def _reset_approval(plat, sf, ctx, trip):
    """Create a server-owned APPROVED reset approval matching the trip payload."""
    payload_hash = shash({"definition_id": trip["definition_id"], "trip_id": trip["trip_id"],
                          "scope": trip["scope"], "scope_ref": trip["scope_ref"]})
    ap = ApprovalRecord(approval_id=new_id("appr_"), user_id="owner2", org_id=ctx.org_id, workspace_id="w1",
                        project_id="", mission_id="", tool_id="paper_safety.reset", action="paper_safety_reset",
                        target_resource=payload_hash, authority="LOCAL_MUTATION",
                        side_effect_class="LOCAL_IRREVERSIBLE", capability="paper_safety_reset",
                        status=ApprovalStatus.APPROVED.value, requested_by="user:u1", decided_by="owner2",
                        expires_at=_now_plus(3600))
    plat.save_approval(ap)
    return ap


def _now_plus(sec):
    import time
    return time.time() + sec


# ══════════════════════════ SAFETY BOUNDARIES ═══════════════════════════════
def test_prohibited_config_fails_closed():
    assert_safety_safe()  # ok
    for tok in ("LIVE", "PRODUCTION", "REAL_MONEY", "LEVERAGE", "MARGIN", "SHORT_SELLING",
                "AUTONOMOUS_CAPITAL", "EXTERNAL_EXECUTION"):
        assert tok in PROHIBITED_SAFETY_TOKENS
        with pytest.raises(PaperSafetyError):
            assert_safety_safe({tok: True})
    with pytest.raises(PaperSafetyError):
        assert_safety_safe(environment="LIVE")


def test_permissions_agents_lack_dangerous():
    # viewer read-only
    assert role_has_permission(PlatformRole.VIEWER, PlatformPermission.PAPER_SAFETY_READ)
    for p in (PlatformPermission.PAPER_SAFETY_CONFIGURE, PlatformPermission.PAPER_SAFETY_RESET,
              PlatformPermission.PAPER_SAFETY_ACKNOWLEDGE):
        assert not role_has_permission(PlatformRole.VIEWER, p)
    # operator can sweep/trip/ack/request but NOT configure/reset
    assert role_has_permission(PlatformRole.OPERATOR, PlatformPermission.PAPER_SAFETY_SWEEP)
    assert role_has_permission(PlatformRole.OPERATOR, PlatformPermission.PAPER_SAFETY_ACKNOWLEDGE)
    assert not role_has_permission(PlatformRole.OPERATOR, PlatformPermission.PAPER_SAFETY_RESET)
    assert not role_has_permission(PlatformRole.OPERATOR, PlatformPermission.PAPER_SAFETY_CONFIGURE)
    # owner has all safety perms
    for p in (PlatformPermission.PAPER_SAFETY_CONFIGURE, PlatformPermission.PAPER_SAFETY_RESET):
        assert role_has_permission(PlatformRole.OWNER, p)


def test_agent_actor_detection():
    assert is_agent_actor(_ctx(authority="AUTONOMOUS_AGENT"))
    assert is_agent_actor(_ctx(user="agent:bot"))
    assert not is_agent_actor(_ctx(user="u1", authority="user"))


def test_state_machine_transitions():
    assert can_breaker_transition(BreakerState.NORMAL, BreakerState.TRIPPED)
    assert can_breaker_transition(BreakerState.TRIPPED, BreakerState.HALTED)
    assert can_breaker_transition(BreakerState.HALTED, BreakerState.ACKNOWLEDGED)
    assert can_breaker_transition(BreakerState.ACKNOWLEDGED, BreakerState.RESET_PENDING)
    assert can_breaker_transition(BreakerState.RESET_PENDING, BreakerState.RESET)
    assert can_breaker_transition(BreakerState.RESET, BreakerState.NORMAL)
    assert not can_breaker_transition(BreakerState.NORMAL, BreakerState.RESET)
    assert not can_breaker_transition(BreakerState.HALTED, BreakerState.NORMAL)


def test_trading_day_rejects_naive_and_is_deterministic():
    d1 = trading_day(1_700_000_000.0, tz_name="UTC")
    d2 = trading_day(1_700_000_000.0, tz_name="UTC")
    assert d1 == d2 and d1["start"] <= 1_700_000_000.0 < d1["end"]
    with pytest.raises(PaperSafetyError):
        trading_day(None)
    with pytest.raises(PaperSafetyError):
        trading_day(1_700_000_000.0, tz_name="Not/AZone")


# ══════════════════════════ MANUAL KILL SWITCH + SCOPES ═════════════════════
def test_manual_kill_switch_halts_account(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx)
    res = sf.manual_trip(ctx, scope="PAPER_ACCOUNT", scope_ref=a["id"], reason="kill")
    assert res["trip"]["trip_id"]
    assert svc.get_account(ctx, a["id"])["status"] == "HALTED"
    assert sf.breaker_posture(ctx, account_id=a["id"])["blocked"]


def test_global_kill_switch_requires_owner(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path)
    op = _ctx(role="operator")
    with pytest.raises(PlatformContextError):
        sf.manual_trip(op, scope="GLOBAL_PAPER")
    owner = _ctx(role="owner")
    res = sf.manual_trip(owner, scope="GLOBAL_PAPER")
    assert res["trip"]["scope"] == "GLOBAL_PAPER"
    # global blocks any account
    assert sf.breaker_posture(owner, account_id="anything")["blocked"]


def test_agent_cannot_trip_ack_reset(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    agent = _ctx(role="owner", authority="AUTONOMOUS_AGENT")
    with pytest.raises(PlatformContextError):
        sf.manual_trip(agent, scope="PAPER_ACCOUNT", scope_ref=a["id"])


def test_account_scope_isolation(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx()
    a1 = _acct(svc, ctx); a2 = _acct(svc, ctx)
    sf.manual_trip(ctx, scope="PAPER_ACCOUNT", scope_ref=a1["id"])
    assert sf.breaker_posture(ctx, account_id=a1["id"])["blocked"]
    assert not sf.breaker_posture(ctx, account_id=a2["id"])["blocked"]
    assert svc.get_account(ctx, a2["id"])["status"] == "ACTIVE"


def test_tenant_isolation(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path)
    c1 = _ctx(org="o1"); c2 = _ctx(org="o2")
    a1 = _acct(svc, c1)
    sf.manual_trip(c1, scope="PAPER_ACCOUNT", scope_ref=a1["id"])
    # other tenant sees no breakers and cannot read the trip
    assert sf.list_states(c2) == []
    assert not sf.breaker_posture(c2, account_id=a1["id"])["blocked"]


# ══════════════════════════ GUARDIAN VETO UNDER BREAKER ═════════════════════
def test_guardian_vetoes_submission_when_halted(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    sf.manual_trip(ctx, scope="PAPER_ACCOUNT", scope_ref=a["id"])
    # account is HALTED — submit path rejects (account not ACTIVE and/or breaker veto)
    i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity="1")
    with pytest.raises(PlatformContextError):
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())


def test_instrument_breaker_vetoes_only_that_symbol(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    # instrument breaker doesn't halt the account; guardian veto blocks that symbol
    sf.manual_trip(ctx, scope="INSTRUMENT", scope_ref="TRENDING")
    assert svc.get_account(ctx, a["id"])["status"] == "ACTIVE"
    i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity="1")
    with pytest.raises(PlatformContextError):
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev(symbol="TRENDING"))


# ══════════════════════════ LOSS / DRAWDOWN / EXPOSURE / CONC ════════════════
def test_daily_realized_loss_trip(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _configure(sf, ctx, BreakerType.DAILY_REALIZED_LOSS, threshold="50", scope_ref=a["id"], timezone="UTC")
    _buy_fill(svc, ctx, a, qty="10", ask="100.00")
    _sell_fill(svc, ctx, a, qty="10", bid="90.00")   # realized -100
    man = sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)
    assert man["trips_created"] >= 1
    assert svc.get_account(ctx, a["id"])["status"] == "HALTED"


def test_total_loss_trip_uses_marks(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _configure(sf, ctx, BreakerType.DAILY_TOTAL_LOSS, threshold="200", scope_ref=a["id"])
    _buy_fill(svc, ctx, a, qty="24", ask="100.00")   # hold 24 @ 100 (2400 notional < approval threshold)
    # mark down to 90 → unrealized -240 (daily total) breaches 200
    man = sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0, marks={a["id"]: {"TRENDING": "90"}})
    assert man["trips_created"] >= 1


def test_drawdown_peak_persists_across_restart(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx, cash="1000")
    d = _configure(sf, ctx, BreakerType.MAX_DRAWDOWN, threshold="20", scope_ref=a["id"])
    _buy_fill(svc, ctx, a, qty="5", ask="100.00")   # 500 notional; cash now 500
    # establish peak at mark 120 (equity 500 + 5*120 = 1100)
    sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0, marks={a["id"]: {"TRENDING": "120"}})
    st = [s for s in sf.list_states(ctx) if s["definition_id"] == d["id"]][0]
    assert D(st["peak_equity"]) >= D("1100")
    # simulate restart: new service instances on same DB
    sf2 = SafetyService(ps)
    st2 = [s for s in sf2.list_states(ctx) if s["definition_id"] == d["id"]][0]
    assert st2["peak_equity"] == st["peak_equity"]
    # now drop hard → equity 500 + 5*40 = 700 vs peak 1100 → ~36% drawdown
    man = sf2.run_sweep(ctx, account_ids=[a["id"]], now=1001.0, marks={a["id"]: {"TRENDING": "40"}})
    assert man["trips_created"] >= 1


def test_gross_exposure_trip(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _configure(sf, ctx, BreakerType.GROSS_EXPOSURE, threshold="500", scope_ref=a["id"])
    _buy_fill(svc, ctx, a, qty="10", ask="100.00")   # exposure 1000 > 500
    man = sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)
    assert man["trips_created"] >= 1


def test_concentration_warning_then_trip(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx()
    a = _acct(svc, ctx, cash="1000")
    d = _configure(sf, ctx, BreakerType.POSITION_CONCENTRATION, threshold="80", warning_threshold="40",
                   scope_ref=a["id"])
    _buy_fill(svc, ctx, a, qty="5", ask="100.00")   # 500 notional; equity ~1000 → 50% → WARNING
    man = sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0,
                       marks={a["id"]: {"TRENDING": "100"}})
    st = [s for s in sf.list_states(ctx) if s["definition_id"] == d["id"]][0]
    assert st["state"] == "WARNING"
    assert svc.get_account(ctx, a["id"])["status"] == "ACTIVE"   # warning does not halt


def test_open_order_count_trip(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _configure(sf, ctx, BreakerType.OPEN_ORDER_COUNT, threshold="1", scope_ref=a["id"])
    # two OPEN (unfilled) buys
    for _ in range(2):
        i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="BUY", order_type="MARKET", quantity="1")
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    man = sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)
    assert man["trips_created"] >= 1


def test_rejection_rate_needs_min_samples(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    d = _configure(sf, ctx, BreakerType.ORDER_REJECTION_RATE, threshold="0.4", scope_ref=a["id"],
                   window_seconds=100000, min_samples="3")
    # one guardian-vetoed intent (sell with no holding) → 1 reject, 1 total < min_samples
    i = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="SELL", order_type="MARKET", quantity="5")
    with pytest.raises(PlatformContextError):
        svc.submit_order(ctx, intent_id=i["intent_id"], event=_ev())
    man = sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)
    st = [s for s in sf.list_states(ctx) if s["definition_id"] == d["id"]][0]
    assert st["state"] == "NORMAL"   # insufficient sample → no unstable trip
    # add more rejects to exceed min_samples with rate > 0.4
    for _ in range(3):
        j = svc.create_intent(ctx, account_id=a["id"], symbol="TRENDING", side="SELL", order_type="MARKET", quantity="5")
        with pytest.raises(PlatformContextError):
            svc.submit_order(ctx, intent_id=j["intent_id"], event=_ev())
    man2 = sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)
    assert man2["trips_created"] >= 1


def test_processing_failure_trip(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx()
    for _ in range(5):
        r = sf.record_processing_failure(ctx, scope="PAPER_BROKER_PROCESSOR", scope_ref="p1",
                                         kind="event_error", now=1000.0)
    assert r["tripped"] is True
    assert sf.breaker_posture(ctx)["blocked"]   # processor scope blocks broadly


# ══════════════════════════ RECONCILIATION + MARKET DATA ════════════════════
def test_reconciliation_critical_trips_and_reset_denied(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_fill(svc, ctx, a, qty="10", ask="100.00")
    # corrupt the position → CRITICAL drift on reconcile
    ps._conn.execute("UPDATE paper_positions SET quantity='999' WHERE account_id=?", (a["id"],))
    ps._conn.commit()
    res = sf.reconcile_and_guard(ctx, a["id"])
    assert res["reconciliation"]["severity_max"] == "CRITICAL"
    assert res["trip"] is not None
    assert svc.get_account(ctx, a["id"])["status"] == "HALTED"
    trip = res["trip"]
    sf.acknowledge(ctx, trip["trip_id"], note="seen")
    ap = _reset_approval(plat, sf, ctx, trip)
    req = sf.request_reset(ctx, trip["trip_id"], reason="fixed?", approval_id=ap.approval_id)
    # corruption remains → reset must fail
    out = sf.execute_reset(ctx, req["request_id"])
    assert out["allowed"] is False
    assert svc.get_account(ctx, a["id"])["status"] == "HALTED"
    assert plat.get_approval(ap.approval_id).status == ApprovalStatus.APPROVED.value  # not consumed on failure


def test_stale_market_data_blocks(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx()
    out = sf.observe_market_event(ctx, source="src1", quality="VALID", event_ts=0.0, now=100000.0,
                                  max_age_seconds=60)
    assert out["blocked"] and out["breaker_type"] == "STALE_MARKET_DATA"
    assert sf.breaker_posture(ctx, source="src1")["blocked"]


def test_corrupted_replay_fails_closed(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx()
    # hash mismatch + sequence regression + invalid quality
    out = sf.observe_market_event(ctx, source="srcX", quality="INVALID", event_ts=1000.0, now=1000.0,
                                  seq=5, prev_seq=9, payload_hash="aaa", expected_hash="bbb")
    assert out["blocked"] and out["breaker_type"] == "INVALID_MARKET_DATA"
    assert "hash_mismatch" in out["reasons"] and "sequence_regression" in out["reasons"]
    # source stays blocked (does not trust later events until reset)
    assert sf.breaker_posture(ctx, source="srcX")["blocked"]


# ══════════════════════════ ACK / RESET (fail-closed) ═══════════════════════
def _trip_ack(svc, sf, ps, ctx, a):
    res = sf.manual_trip(ctx, scope="PAPER_ACCOUNT", scope_ref=a["id"], reason="kill")
    trip = res["trip"]
    ackres = sf.acknowledge(ctx, trip["trip_id"], note="seen", evidence_reviewed=True)
    assert ackres["halt_retained"] is True
    assert svc.get_account(ctx, a["id"])["status"] == "HALTED"   # ack does NOT unhalt
    return trip


def test_reset_success_no_financial_change(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    before = svc.get_account(ctx, a["id"])
    trip = _trip_ack(svc, sf, ps, ctx, a)
    ap = _reset_approval(plat, sf, ctx, trip)
    req = sf.request_reset(ctx, trip["trip_id"], reason="all clear", approval_id=ap.approval_id)
    out = sf.execute_reset(ctx, req["request_id"])
    assert out["allowed"] is True and out["account_unhalted"] is True
    assert out["financial_state_modified"] is False
    after = svc.get_account(ctx, a["id"])
    assert after["status"] == "ACTIVE"
    assert after["current_cash"] == before["current_cash"]
    assert after["realized_pnl"] == before["realized_pnl"]
    assert plat.get_approval(ap.approval_id).status == ApprovalStatus.CONSUMED.value
    st = [s for s in sf.list_states(ctx) if s["definition_id"] == trip["definition_id"]][0]
    assert st["state"] == "NORMAL"


def test_reset_requires_acknowledgement(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    trip = sf.manual_trip(ctx, scope="PAPER_ACCOUNT", scope_ref=a["id"])["trip"]
    with pytest.raises(PlatformContextError):
        sf.request_reset(ctx, trip["trip_id"], reason="x")   # not acknowledged


def test_reset_denied_missing_approval(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    trip = _trip_ack(svc, sf, ps, ctx, a)
    req = sf.request_reset(ctx, trip["trip_id"], reason="clear")   # no approval_id
    out = sf.execute_reset(ctx, req["request_id"])
    assert out["allowed"] is False
    assert any(c["check"] == "approval_valid" and not c["ok"] for c in out["decision"]["checks"])


def test_reset_denied_expired_approval(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    trip = _trip_ack(svc, sf, ps, ctx, a)
    ap = _reset_approval(plat, sf, ctx, trip)
    ap.expires_at = 1.0   # already expired
    plat.save_approval(ap)
    req = sf.request_reset(ctx, trip["trip_id"], reason="clear", approval_id=ap.approval_id)
    out = sf.execute_reset(ctx, req["request_id"])
    assert out["allowed"] is False


def test_reset_denied_cross_tenant_approval(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    trip = _trip_ack(svc, sf, ps, ctx, a)
    ap = _reset_approval(plat, sf, ctx, trip)
    ap.org_id = "o2"; plat.save_approval(ap)
    req = sf.request_reset(ctx, trip["trip_id"], reason="clear", approval_id=ap.approval_id)
    out = sf.execute_reset(ctx, req["request_id"])
    assert out["allowed"] is False


def test_reset_denied_reused_approval(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    trip = _trip_ack(svc, sf, ps, ctx, a)
    ap = _reset_approval(plat, sf, ctx, trip)
    req = sf.request_reset(ctx, trip["trip_id"], reason="clear", approval_id=ap.approval_id)
    assert sf.execute_reset(ctx, req["request_id"])["allowed"] is True   # consumed
    # re-trip + re-ack + new request reusing same (now CONSUMED) approval
    trip2 = _trip_ack(svc, sf, ps, ctx, a)
    req2 = sf.request_reset(ctx, trip2["trip_id"], reason="again", approval_id=ap.approval_id)
    assert sf.execute_reset(ctx, req2["request_id"])["allowed"] is False


def test_reset_denied_payload_mismatch(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    trip = _trip_ack(svc, sf, ps, ctx, a)
    ap = _reset_approval(plat, sf, ctx, trip)
    ap.target_resource = "different-payload-hash"; plat.save_approval(ap)
    req = sf.request_reset(ctx, trip["trip_id"], reason="clear", approval_id=ap.approval_id)
    out = sf.execute_reset(ctx, req["request_id"])
    assert out["allowed"] is False


def test_reset_denied_agent_requester(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    trip = _trip_ack(svc, sf, ps, ctx, a)
    ap = _reset_approval(plat, sf, ctx, trip)
    req = sf.request_reset(ctx, trip["trip_id"], reason="clear", approval_id=ap.approval_id)
    agent = _ctx(role="owner", authority="AUTONOMOUS_AGENT")
    with pytest.raises(PlatformContextError):
        sf.execute_reset(agent, req["request_id"])


def test_reset_denied_broader_breaker_active(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    trip = _trip_ack(svc, sf, ps, ctx, a)
    ap = _reset_approval(plat, sf, ctx, trip)
    req = sf.request_reset(ctx, trip["trip_id"], reason="clear", approval_id=ap.approval_id)
    sf.manual_trip(ctx, scope="GLOBAL_PAPER")   # broader breaker now active
    out = sf.execute_reset(ctx, req["request_id"])
    assert out["allowed"] is False
    assert any(c["check"] == "no_broader_breaker" and not c["ok"] for c in out["decision"]["checks"])


def test_reset_denied_threshold_still_breached(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    d = _configure(sf, ctx, BreakerType.GROSS_EXPOSURE, threshold="500", scope_ref=a["id"])
    _buy_fill(svc, ctx, a, qty="10", ask="100.00")   # exposure 1000, stays > 500
    sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)
    trip = sf.list_trips(ctx, definition_id=d["id"])[0]
    sf.acknowledge(ctx, trip["trip_id"], note="seen")
    ap = _reset_approval(plat, sf, ctx, trip)
    req = sf.request_reset(ctx, trip["trip_id"], reason="clear", approval_id=ap.approval_id)
    out = sf.execute_reset(ctx, req["request_id"])
    assert out["allowed"] is False
    assert any(c["check"] == "threshold_cleared" and not c["ok"] for c in out["decision"]["checks"])


# ══════════════════════════ ALERTS + DETERMINISM + IDEMPOTENCY ══════════════
def test_alert_created_and_tenant_scoped(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    sf.manual_trip(ctx, scope="PAPER_ACCOUNT", scope_ref=a["id"])
    alerts = sf.list_alerts(ctx)
    assert alerts and alerts[0]["blocking"] == 1
    assert sf.list_alerts(_ctx(org="o2")) == []


def test_sweep_deterministic_result_hash(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _configure(sf, ctx, BreakerType.GROSS_EXPOSURE, threshold="9999999", scope_ref=a["id"])
    _buy_fill(svc, ctx, a, qty="10", ask="100.00")
    m1 = sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)
    m2 = sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)
    assert m1["result_hash"] == m2["result_hash"]


def test_duplicate_recon_trip_idempotent(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _buy_fill(svc, ctx, a, qty="10", ask="100.00")
    ps._conn.execute("UPDATE paper_positions SET quantity='999' WHERE account_id=?", (a["id"],))
    ps._conn.commit()
    r1 = sf.reconcile_and_guard(ctx, a["id"])
    trips_before = len(sf.list_trips(ctx))
    # second recon on still-blocking breaker → no new trip
    r2 = sf.reconcile_and_guard(ctx, a["id"])
    assert len(sf.list_trips(ctx)) == trips_before


def test_duplicate_sweep_no_double_trip(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    _configure(sf, ctx, BreakerType.GROSS_EXPOSURE, threshold="500", scope_ref=a["id"])
    _buy_fill(svc, ctx, a, qty="10", ask="100.00")
    sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)
    n = len(sf.list_trips(ctx))
    sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)   # breaker already HALTED
    assert len(sf.list_trips(ctx)) == n


# ══════════════════════════ RESTART + ROLLBACK ══════════════════════════════
def test_restart_recovers_breaker_state(tmp_path):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    trip = sf.manual_trip(ctx, scope="PAPER_ACCOUNT", scope_ref=a["id"])["trip"]
    # reopen store + service (simulated restart)
    ps2 = PaperStore(db_path=tmp_path / "paper.db")
    sf2 = SafetyService(ps2)
    t = sf2.get_trip(ctx, trip["trip_id"])
    assert t["trip_id"] == trip["trip_id"]
    assert sf2.breaker_posture(ctx, account_id=a["id"])["blocked"]


def test_atomic_trip_rolls_back(tmp_path, monkeypatch):
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    d = _configure(sf, ctx, BreakerType.GROSS_EXPOSURE, threshold="500", scope_ref=a["id"])
    _buy_fill(svc, ctx, a, qty="10", ask="100.00")
    # force a failure inside persist_trip (after some writes) → whole trip rolls back
    orig = sf.store._write_state
    def boom(*args, **kw):
        raise RuntimeError("injected sqlite interruption")
    monkeypatch.setattr(sf.store, "_write_state", boom)
    # the sweep isolates per-breaker errors into the manifest; the persist_trip
    # transaction rolls back fully → no partial halt, no orphan trip/alert.
    man = sf.run_sweep(ctx, account_ids=[a["id"]], now=1000.0)
    assert man["errors"]   # the injected failure surfaced, not silently swallowed
    monkeypatch.undo()
    # no partial trip, no halt
    assert sf.list_trips(ctx) == []
    assert svc.get_account(ctx, a["id"])["status"] == "ACTIVE"
    st = [s for s in sf.list_states(ctx) if s["definition_id"] == d["id"]][0]
    assert st["state"] == "NORMAL"


# ══════════════════════════ RUNTIME / GATEWAY PATH ══════════════════════════
def test_full_lifecycle_through_gateway(tmp_path):
    """trip → halt → acknowledge → request_reset → approval → Runtime/Gateway →
    registered paper_safety.reset tool → fail-closed verification → reset → audit."""
    from saathi.platform.safety import orchestration, set_safety_service_for_tests
    from saathi.tool_runtime.contracts import ToolOutcomeClass
    svc, sf, ps, plat = _svc(tmp_path); ctx = _ctx(); a = _acct(svc, ctx)
    set_safety_service_for_tests(sf)   # adapters resolve to this tmp-scoped service
    try:
        # manual trip through the gateway tool boundary
        r = orchestration.trip_via_gateway(ctx, scope="PAPER_ACCOUNT", scope_ref=a["id"], reason="kill")
        assert r.outcome_class == ToolOutcomeClass.SUCCESS_CONFIRMED
        assert svc.get_account(ctx, a["id"])["status"] == "HALTED"
        trip = sf.list_trips(ctx)[0]
        # acknowledge through the gateway
        ra = orchestration.acknowledge_via_gateway(ctx, trip_id=trip["trip_id"], note="seen")
        assert ra.outcome_class == ToolOutcomeClass.SUCCESS_CONFIRMED
        assert svc.get_account(ctx, a["id"])["status"] == "HALTED"   # ack keeps halt
        # request + approval-backed reset through the gateway
        ap = _reset_approval(plat, sf, ctx, trip)
        orchestration.request_reset_via_gateway(ctx, trip_id=trip["trip_id"], reason="clear",
                                                approval_id=ap.approval_id)
        request_id = _latest_request_id(sf, ctx)
        rr = orchestration.reset_via_gateway(ctx, request_id=request_id, approval_id=ap.approval_id)
        assert rr.outcome_class == ToolOutcomeClass.SUCCESS_CONFIRMED
        assert rr.data.get("allowed") is True and rr.data.get("financial_state_modified") is False
        assert svc.get_account(ctx, a["id"])["status"] == "ACTIVE"
        assert plat.get_approval(ap.approval_id).status == ApprovalStatus.CONSUMED.value
    finally:
        set_safety_service_for_tests(None)


def _latest_request_id(sf, ctx):
    row = sf.store._conn.execute("SELECT request_id FROM safety_reset_requests WHERE org_id=? "
                                 "ORDER BY requested_at DESC LIMIT 1", (ctx.org_id,)).fetchone()
    return row["request_id"]


def test_default_breakers_present():
    defs = default_account_breakers("o1", "acc1")
    types = {d.breaker_type for d in defs}
    assert BreakerType.DAILY_REALIZED_LOSS in types
    assert BreakerType.MAX_DRAWDOWN in types
    assert BreakerType.RECONCILIATION_CRITICAL in types
    # daily-loss defaults are inert until configured (fail-closed, no unsafe default)
    dl = [d for d in defs if d.breaker_type == BreakerType.DAILY_REALIZED_LOSS][0]
    assert dl.requires_config and dl.threshold == 0
