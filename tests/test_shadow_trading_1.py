"""SHADOW-TRADING-1 — end-to-end durable shadow operation over the REAL chain.

Drives the certified authorities — construction, risk, Guardian venue policy —
through PaperCryptoPipeline, records every decision into a durable shadow session,
kills the store, restarts it, and proves the accounting survived without a single
order, private API call, or real-ledger mutation.

Bounded and deterministic: this certifies the MACHINERY. It says nothing about
whether the strategy makes money, and no test here pretends otherwise.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from saathi.platform.market_data.contract import (
    AssetClass, HistoricalBar, MarketStatus, PointInTime, ProviderReference,
)
from saathi.platform.portfolio_construction.models import (
    InstrumentMetadata, PortfolioConstructionRequest, PortfolioSnapshotInput,
    StrategyQualificationEvidence, StrategyQualificationStatus,
)
from saathi.platform.portfolio_risk_engine.budget import PAPER_BUDGET_V2
from saathi.platform.research.store import ResearchStore
from saathi.platform.signal import Direction, TradingIntentProposal, TradingSignal
from saathi.platform.trading_models import DataQuality
from saathi.platform.tg.paper_crypto_pipeline import PaperCryptoPipeline, PaperCycleOutcome
from saathi.platform.tg.shadow_engine import CryptoShadowEngine
from saathi.platform.tg.shadow_session import (
    ShadowEventKind, ShadowMode, ShadowSessionStore, ShadowSessionStatus,
)

NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)
BTC = "BINANCE:BTC/USDT"


def _signal(strength="0.50"):
    return TradingSignal.create(
        strategy_id="crypto_spot_mean_reversion", strategy_version="1.0.0",
        instrument_id=BTC, direction=Direction.LONG_BIAS, strength=strength,
        generated_at=NOW - timedelta(hours=1), valid_until=NOW + timedelta(days=1),
        data_mode="HISTORICAL", reason_codes=("FROZEN_STRATEGY_OUTPUT",), quality="VALID",
    )


def _qualification(signal):
    return StrategyQualificationEvidence(
        intent_id="intent:" + signal.signal_id, signal_ref=signal.signal_id,
        strategy_id=signal.strategy_id, strategy_version=signal.strategy_version,
        instrument_id=signal.instrument_id,
        status=StrategyQualificationStatus.PAPER_CANDIDATE,
        qualification_artifact_sha256="45a115c978047e228c769d05cbef48e5d1a59070c94f4706dc2903f561bccd40",
        dataset_version="sha256-0f1290db14ab0037e6a69e25bcd1d7928087629cf11630f0ac2c52dbb27768e8",
        selected_config_hash="8ba2c7a6cf2d5423263493ed992996541122350d5a6f7245e56322429b2f6e72",
        quality="CERTIFIED_WITH_LIMITATIONS",
    )


def _meta(instrument_id=BTC):
    return InstrumentMetadata(
        instrument_id=instrument_id, symbol="BTCUSDT", venue="BINANCE",
        asset_class=AssetClass.CRYPTO, quote_currency="USDT", enabled=True,
        venue_enabled=True, liquidity_limit_weight=Decimal("0.15"),
        estimated_round_trip_cost_bps=Decimal("40"),
    )


def _bars(count=100):
    rows = []
    close = Decimal("100")
    pattern = (Decimal("0.01"), Decimal("-0.01"))
    for i in range(count):
        close = close * (Decimal("1") + pattern[i % len(pattern)])
        t = NOW - timedelta(days=count + 1 - i)
        rows.append(HistoricalBar(
            instrument_id=BTC, venue="BINANCE", asset_class=AssetClass.CRYPTO, currency="USDT",
            point_in_time=PointInTime(t, t, t, t),
            provider=ProviderReference("BINANCE_PUBLIC_DATA", provider_event_id=str(i)),
            quality=DataQuality.VALID, market_status=MarketStatus.CLOSED,
            open=close, high=close, low=close, close=close, volume=Decimal("1000"),
            timeframe="1d", source_record_id=f"{BTC}:{i}", revision_id="dataset-revision-1",
        ))
    return tuple(rows)


def _snapshot(cash="100000"):
    return PortfolioSnapshotInput(
        fund_id="fund-v2", snapshot_ref="ledger-snapshot:1", reporting_currency="USDT",
        nav=Decimal("100000"), cash=Decimal(cash), available_cash=Decimal(cash),
        reserved_cash=Decimal("0"), unsettled_cash=Decimal("0"), positions=(),
        current_drawdown=Decimal("0"), source_authority="CANONICAL_FUND_LEDGER",
        reconciliation_status="HEALTHY",
    )


def _request(snapshot):
    sig = _signal()
    return PortfolioConstructionRequest.create(
        portfolio_snapshot=snapshot,
        intents=(TradingIntentProposal.from_signal(sig),),
        qualifications=(_qualification(sig),),
        instrument_metadata=(_meta(),), market_history={BTC: _bars()},
        market_data_snapshot_ref="market-data:certified:1", market_data_mode="HISTORICAL",
        market_data_quality="VALID", decision_time=NOW,
        construction_policy_version="portfolio-construction/v2.0.0-configured-conservative",
        risk_budget_version=PAPER_BUDGET_V2.version,
    ), sig


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "shadow-e2e.sqlite3"


def _store(db):
    return ShadowSessionStore(research_store=ResearchStore(db_path=db))


def _open(store):
    return store.open_session(
        mode=ShadowMode.REPLAY, market="CRYPTO",
        strategy_version="crypto_spot_mean_reversion@1.0.0",
        policy_versions={
            "construction": "portfolio-construction/v2.0.0-configured-conservative",
            "risk": PAPER_BUDGET_V2.version, "guardian": "venue-policy/v2",
        },
        feed_ref="replay:BINANCE_PUBLIC_DATA:deterministic-100-bar",
        opening_cash="100000", started_at=NOW.isoformat(), benchmark="BTC_BUY_AND_HOLD",
    )


def _run_cycle(store, sid, *, approval_granted, disabled_venues=(), price="60000"):
    """One full chain cycle, recorded durably. Returns the decision."""
    snap = _snapshot()
    request, sig = _request(snap)
    decision = PaperCryptoPipeline().run(
        request, portfolio_snapshot=snap, approval_granted=approval_granted,
        disabled_venues=disabled_venues, price_map={BTC: Decimal(price)},
    )
    seq = store.next_seq(sid)
    store.append_event(sid, seq, ShadowEventKind.SIGNAL,
                       {"signal_id": sig.signal_id, "strategy": sig.strategy_id})
    store.append_event(sid, seq + 1, ShadowEventKind.GUARDIAN, decision.to_public())

    if decision.ready:
        engine = CryptoShadowEngine()
        obs = engine.observe(decision, {BTC: Decimal(price)})
        for i, order in enumerate(obs.orders):
            s = store.next_seq(sid)
            store.append_event(sid, s, ShadowEventKind.HYPOTHETICAL_FILL, {
                "symbol": order.symbol, "side": order.side,
                "qty": str(order.quantity), "px": str(order.estimated_fill_price),
            })
            store.record_fill(
                sid, s, symbol=order.symbol, side=order.side, quantity=order.quantity,
                reference_price=order.reference_price, fill_price=order.estimated_fill_price,
                fee=order.fee, spread_cost=order.spread_cost, slippage_cost=order.slippage_cost,
            )
    else:
        # A refused cycle is recorded as a counterfactual so Guardian's value can
        # be measured later, without ever unblocking it.
        s = store.next_seq(sid)
        store.record_blocked(
            sid, s, symbol=BTC, side="BUY", quantity="1", reference_price=price,
            blocked_by=decision.outcome.value, reason_codes=list(decision.reason_codes),
        )
    return decision


# ── the target flow, end to end ─────────────────────────────────────────────

def test_the_full_chain_runs_and_persists_without_sending_an_order(db):
    s = _store(db)
    sid = _open(s)
    decision = _run_cycle(s, sid, approval_granted=True)

    assert decision.authorizes_execution is False, "the chain never authorizes execution"
    events = s.events(sid)
    kinds = {e["kind"] for e in events}
    assert ShadowEventKind.SIGNAL.value in kinds
    assert ShadowEventKind.GUARDIAN.value in kinds

    rec = s.reconcile(sid)
    assert rec["ok"] is True, rec["problems"]

    m = s.metrics(sid)
    assert m["real_order_attempts"] == 0
    assert m["private_api_calls"] == 0
    assert m["real_ledger_mutations"] == 0
    assert m["mode"] == "REPLAY", "a replay run must never be labelled live"


def test_a_refused_cycle_moves_no_money_and_is_kept_as_a_counterfactual(db):
    s = _store(db)
    sid = _open(s)
    # No approval: the chain must refuse before any hypothetical order exists.
    decision = _run_cycle(s, sid, approval_granted=False)
    assert decision.ready is False

    state = s.derive_portfolio(sid)
    assert state.fills == 0
    assert state.cash == Decimal("100000")
    assert state.positions == {}

    cfs = s.counterfactuals(sid)
    assert len(cfs) == 1
    assert cfs[0]["forward_pnl"] is None, "not yet observed"

    measured = s.observe_counterfactual(sid, cfs[0]["seq"], "62000")
    assert measured["forward_pnl"] == Decimal("2000")
    # Measuring it changed nothing about the book.
    assert s.derive_portfolio(sid).fills == 0


def test_a_disabled_venue_blocks_and_still_moves_no_money(db):
    s = _store(db)
    sid = _open(s)
    decision = _run_cycle(s, sid, approval_granted=True, disabled_venues=["CRYPTO"])
    assert decision.ready is False
    assert s.derive_portfolio(sid).fills == 0
    assert len(s.counterfactuals(sid)) == 1


# ── restart, over the real chain ────────────────────────────────────────────

def test_restart_mid_session_resumes_without_double_counting(db):
    s1 = _store(db)
    sid = _open(s1)
    _run_cycle(s1, sid, approval_granted=True)
    before = s1.derive_portfolio(sid)
    seq_before = s1.next_seq(sid)
    s1.close()

    s2 = _store(db)
    resumed = s2.resume(sid)
    assert resumed["next_seq"] == seq_before
    after = resumed["state"]
    assert after.fills == before.fills
    assert after.cash == before.cash
    assert after.fees_paid == before.fees_paid
    assert after.positions == before.positions

    # Continuing after the restart appends, never replaces.
    _run_cycle(s2, sid, approval_granted=False)
    assert s2.next_seq(sid) > seq_before
    assert s2.derive_portfolio(sid).fills == before.fills, "a blocked cycle adds no fill"


def test_the_session_contract_survives_a_restart(db):
    s1 = _store(db)
    sid = _open(s1)
    s1.close()
    s2 = _store(db)
    got = s2.get_session(sid)
    assert got["strategy_version"] == "crypto_spot_mean_reversion@1.0.0"
    assert got["policy_versions"]["risk"] == PAPER_BUDGET_V2.version
    assert got["feed_ref"].startswith("replay:")
    assert got["benchmark"] == "BTC_BUY_AND_HOLD"


# ── authority audit ─────────────────────────────────────────────────────────

def test_no_shadow_object_can_reach_a_broker_adapter(db):
    """A ShadowOrder must be structurally unusable as a broker order.

    An earlier version of this test scanned the broker MODULE for names starting
    "submit"/"place"/"execute", found none, and passed without asserting anything.
    It now drives PaperBroker's real entry points with a ShadowOrder and requires
    each to reject it.
    """
    import inspect

    from saathi.platform.paper_trading.broker import FeeModel, PaperBroker, SlippageModel
    from saathi.platform.tg.shadow_engine import ShadowOrder

    order = ShadowOrder(
        symbol=BTC, side="BUY", quantity=Decimal("1"), reference_price=Decimal("60000"),
        estimated_fill_price=Decimal("60030"), fee=Decimal("60"), spread_cost=Decimal("20"),
        slippage_cost=Decimal("10"), total_cost=Decimal("90"), notional=Decimal("60030"),
    )

    # 1. It carries no execution surface of its own.
    for attr in ("submit", "execute", "send", "client", "venue_client", "broker",
                 "api_key", "account_id", "credentials"):
        assert not hasattr(order, attr), f"ShadowOrder must not expose {attr}"

    # 2. The broker's real entry points exist and refuse it.
    entry = [m for m in ("validate_new_order", "compute_fill", "reserve_for_buy")
             if callable(getattr(PaperBroker, m, None))]
    assert entry, "the broker adapter exposes no entry point — this test would be vacuous"

    broker = PaperBroker(fee_model=FeeModel(), slippage_model=SlippageModel())
    refused, accepted = [], []
    for name in entry:
        fn = getattr(broker, name)
        sig = inspect.signature(fn)
        kwargs = {p: order for p in sig.parameters if p != "self"}
        try:
            fn(**kwargs)
            accepted.append(name)
        except Exception:
            refused.append(name)

    # The order-creating paths refuse a ShadowOrder outright.
    assert "validate_new_order" in refused
    assert "compute_fill" in refused

    # reserve_for_buy is a pure arithmetic helper: it returns a number and cannot
    # create an order, a position or a ledger row. It does NOT refuse a
    # ShadowOrder — it silently reads it as zero (see the D() finding below) — so
    # the property proven here is the one that matters: no path turns a shadow
    # object into something the broker will act on.
    if accepted:
        assert accepted == ["reserve_for_buy"], accepted
        assert not hasattr(broker, "orders"), "the adapter holds no order book to have been mutated"


def test_the_broker_numeric_helper_silently_zeroes_non_numbers(db):
    """Documents a latent weakness found while proving the shadow boundary.

    PaperBroker.D() turns None, "abc", True and arbitrary objects into Decimal 0
    rather than refusing, which is why reserve_for_buy accepts a ShadowOrder and
    answers 0.00. Nothing in SHADOW depends on that behaviour, and shadow cannot
    reach a live path through it — but a cash RESERVATION that silently becomes
    zero is the same silent-zero class this codebase is otherwise built against.
    Pinned here so a fix is a visible change, not a surprise.
    """
    from saathi.platform.paper_trading.broker import D

    for junk in (None, "abc", object(), True):
        assert D(junk) == Decimal("0"), "current (undesirable) behaviour"
    assert D("12.5") == Decimal("12.5")


def test_shadow_never_writes_a_paper_or_real_ledger_row(db):
    s = _store(db)
    sid = _open(s)
    _run_cycle(s, sid, approval_granted=True)
    tables = {r[0] for r in s.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in tables:
        low = t.lower()
        if ("paper" in low or "ledger" in low or "broker" in low) and "shadow" not in low:
            n = s.connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            assert n == 0, f"shadow mutated {t} ({n} rows)"


def test_replay_mode_is_never_reported_as_live(db):
    s = _store(db)
    sid = _open(s)
    _run_cycle(s, sid, approval_granted=True)
    m = s.metrics(sid)
    assert m["mode"] == ShadowMode.REPLAY.value
    assert "LIVE" not in m["mode"] or m["mode"] == "LIVE_PUBLIC"
    assert s.get_session(sid)["mode"] != "LIVE_PUBLIC"


# ── fault injection over the real chain ─────────────────────────────────────

def test_a_reconciliation_failure_stops_the_session_resuming(db):
    s = _store(db)
    sid = _open(s)
    _run_cycle(s, sid, approval_granted=True)
    # Inject an impossible sell.
    seq = s.next_seq(sid)
    s.append_event(sid, seq, ShadowEventKind.HYPOTHETICAL_FILL, {"injected": "bad"})
    s.record_fill(sid, seq, symbol=BTC, side="SELL", quantity="9999",
                  reference_price="60000", fill_price="60000", fee="1")
    rec = s.reconcile(sid)
    assert rec["ok"] is False
    assert s.get_session(sid)["status"] == ShadowSessionStatus.RECONCILIATION_REQUIRED.value
    with pytest.raises(Exception):
        s.resume(sid)


def test_a_duplicate_market_event_does_not_duplicate_the_decision(db):
    s = _store(db)
    sid = _open(s)
    _run_cycle(s, sid, approval_granted=True)
    fills_once = s.derive_portfolio(sid).fills
    # The same cycle arrives again with the same sequence numbers.
    evs = s.events(sid, ShadowEventKind.HYPOTHETICAL_FILL)
    for e in evs:
        assert s.append_event(sid, e["seq"], ShadowEventKind.HYPOTHETICAL_FILL, e["payload"]) is False
    assert s.derive_portfolio(sid).fills == fills_once


def test_metrics_separate_system_certification_from_strategy_evidence(db):
    s = _store(db)
    sid = _open(s)
    _run_cycle(s, sid, approval_granted=True)
    m = s.metrics(sid)
    # Machinery counts are present; profitability is NOT claimed from a bounded run.
    assert m["fills"] >= 0 and m["guardian_blocks"] >= 0
    assert m["nav"] is None, "NAV needs an explicit price map — never assumed"
