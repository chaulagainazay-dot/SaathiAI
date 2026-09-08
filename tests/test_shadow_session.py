"""SHADOW-TRADING-1 — durable shadow session, restart safety, no-order proof.

The scenario every test here is written against: a shadow session runs, the
process dies, a new one starts, and the accounting must be exactly as it was —
no double fill, no double fee, no double cash movement — while never claiming to
be live and never having sent an order.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from saathi.platform.research.store import ResearchStore
from saathi.platform.tg.shadow_session import (
    SHADOW_SESSION_SCHEMA_VERSION,
    ShadowAuthorityError,
    ShadowError,
    ShadowEventKind,
    ShadowMode,
    ShadowReconciliationError,
    ShadowSessionStatus,
    ShadowSessionStore,
    assert_no_execution_authority,
)


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "shadow.sqlite3"


def _store(db):
    return ShadowSessionStore(research_store=ResearchStore(db_path=db))


def _open(store, **kw):
    params = dict(
        mode=ShadowMode.REPLAY, market="CRYPTO", strategy_version="btc-mean-reversion@frozen-1",
        policy_versions={"guardian": "v2", "construction": "v2", "risk": "v2"},
        feed_ref="replay:btc-2026-08", opening_cash="250000", started_at="2026-09-01T00:00:00Z",
        benchmark="BTC_BUY_AND_HOLD",
    )
    params.update(kw)
    return store.open_session(**params)


def _fill(store, sid, seq, side="BUY", qty="1", ref="60000", px="60030", fee="60"):
    store.append_event(sid, seq, ShadowEventKind.HYPOTHETICAL_FILL,
                       {"symbol": "BTCUSDT", "side": side, "qty": qty, "px": px})
    store.record_fill(sid, seq, symbol="BTCUSDT", side=side, quantity=qty,
                      reference_price=ref, fill_price=px, fee=fee,
                      spread_cost="20", slippage_cost="10")


# ── session basics ──────────────────────────────────────────────────────────

def test_schema_is_versioned_and_records_the_session_contract(db):
    s = _store(db)
    assert s.schema_version == SHADOW_SESSION_SCHEMA_VERSION
    sid = _open(s)
    got = s.get_session(sid)
    assert got["mode"] == "REPLAY"
    assert got["strategy_version"] == "btc-mean-reversion@frozen-1"
    assert got["policy_versions"]["guardian"] == "v2"
    assert got["feed_ref"] == "replay:btc-2026-08"
    assert got["benchmark"] == "BTC_BUY_AND_HOLD"
    assert got["status"] == ShadowSessionStatus.OPEN.value


def test_replay_and_live_public_are_the_only_modes(db):
    assert {m.value for m in ShadowMode} == {"REPLAY", "LIVE_PUBLIC"}
    s = _store(db)
    with pytest.raises(ValueError):
        _open(s, mode="LIVE_VENUE")


# ── PHASE: restart recovery ─────────────────────────────────────────────────

def test_restart_recovers_the_book_without_double_counting(db):
    s1 = _store(db)
    sid = _open(s1)
    _fill(s1, sid, 1)
    _fill(s1, sid, 2, ref="61000", px="61030", fee="61")
    before = s1.derive_portfolio(sid)
    s1.close()

    # A brand new process opens the same durable store.
    s2 = _store(db)
    resumed = s2.resume(sid)
    after = resumed["state"]

    assert resumed["next_seq"] == 3
    assert after.fills == before.fills == 2
    assert after.cash == before.cash
    assert after.fees_paid == before.fees_paid == Decimal("121")
    assert after.positions == before.positions == {"BTCUSDT": Decimal("2")}


def test_replaying_a_recorded_event_after_restart_is_a_no_op(db):
    s1 = _store(db)
    sid = _open(s1)
    _fill(s1, sid, 1)
    cash_once = s1.derive_portfolio(sid).cash
    s1.close()

    # The crashed process had already written seq 1; the new one replays it.
    s2 = _store(db)
    appended = s2.append_event(sid, 1, ShadowEventKind.HYPOTHETICAL_FILL,
                               {"symbol": "BTCUSDT", "side": "BUY", "qty": "1", "px": "60030"})
    recorded = s2.record_fill(sid, 1, symbol="BTCUSDT", side="BUY", quantity="1",
                              reference_price="60000", fill_price="60030", fee="60",
                              spread_cost="20", slippage_cost="10")
    assert appended is False, "a replayed event must not be appended twice"
    assert recorded is False, "a replayed fill must not be recorded twice"

    after = s2.derive_portfolio(sid)
    assert after.fills == 1
    assert after.cash == cash_once, "no double cash movement"
    assert after.fees_paid == Decimal("60"), "no double fee"
    assert after.positions == {"BTCUSDT": Decimal("1")}


def test_rewriting_history_at_an_existing_seq_is_refused(db):
    s = _store(db)
    sid = _open(s)
    s.append_event(sid, 1, ShadowEventKind.SIGNAL, {"signal": "MEAN_REVERT", "z": "-2.1"})
    with pytest.raises(ShadowError):
        s.append_event(sid, 1, ShadowEventKind.SIGNAL, {"signal": "MEAN_REVERT", "z": "-9.9"})


def test_a_session_needing_reconciliation_cannot_silently_resume(db):
    s = _store(db)
    sid = _open(s)
    s.set_status(sid, ShadowSessionStatus.RECONCILIATION_REQUIRED)
    with pytest.raises(ShadowReconciliationError):
        s.resume(sid)


# ── PHASE: reconciliation fails closed ──────────────────────────────────────

def test_a_clean_session_reconciles(db):
    s = _store(db)
    sid = _open(s)
    _fill(s, sid, 1)
    rec = s.reconcile(sid)
    assert rec["ok"] is True and rec["problems"] == []


def test_selling_more_than_held_fails_closed_and_flags_the_session(db):
    s = _store(db)
    sid = _open(s)
    _fill(s, sid, 1, side="BUY", qty="1")
    _fill(s, sid, 2, side="SELL", qty="5", ref="61000", px="60900", fee="61")
    rec = s.reconcile(sid)
    assert rec["ok"] is False
    assert any("exceeds held" in p for p in rec["problems"])
    assert s.get_session(sid)["status"] == ShadowSessionStatus.RECONCILIATION_REQUIRED.value


def test_history_is_never_silently_repaired(db):
    s = _store(db)
    sid = _open(s)
    _fill(s, sid, 1, side="BUY", qty="1")
    _fill(s, sid, 2, side="SELL", qty="5", ref="61000", px="60900", fee="61")
    s.reconcile(sid)
    # The bad fill is still there afterwards — nothing deleted it to make the
    # books balance.
    assert len(s.fills(sid)) == 2


def test_overspending_cash_is_caught(db):
    s = _store(db)
    sid = _open(s, opening_cash="100")
    _fill(s, sid, 1, side="BUY", qty="1", ref="60000", px="60030", fee="60")
    rec = s.reconcile(sid)
    assert rec["ok"] is False
    assert any("negative shadow cash" in p for p in rec["problems"])


def test_a_fill_with_no_recorded_event_is_an_orphan(db):
    s = _store(db)
    sid = _open(s)
    s.record_fill(sid, 7, symbol="BTCUSDT", side="BUY", quantity="1",
                  reference_price="60000", fill_price="60030", fee="60")
    rec = s.reconcile(sid)
    assert rec["ok"] is False
    assert any("without a recorded fill event" in p for p in rec["problems"])


# ── accounting ──────────────────────────────────────────────────────────────

def test_costs_are_charged_and_realized_pnl_is_net_of_them(db):
    s = _store(db)
    sid = _open(s)
    _fill(s, sid, 1, side="BUY", qty="2", ref="60000", px="60000", fee="120")
    _fill(s, sid, 2, side="SELL", qty="2", ref="61000", px="61000", fee="122")
    st = s.derive_portfolio(sid)
    # gross 2 * 1000 = 2000, less the sell fee charged at realization
    assert st.realized_pnl == Decimal("1878")
    assert st.fees_paid == Decimal("242")
    assert st.positions == {}
    assert st.cash == Decimal("250000") - Decimal("120000") - Decimal("120") + Decimal("122000") - Decimal("122")


def test_nav_refuses_rather_than_understating_an_unpriced_position(db):
    s = _store(db)
    sid = _open(s)
    _fill(s, sid, 1)
    st = s.derive_portfolio(sid)
    with pytest.raises(ShadowError):
        st.nav({})           # no price for BTCUSDT
    assert st.nav({"BTCUSDT": "61000"}) == st.cash + Decimal("61000")


def test_metrics_report_unknown_as_none_never_zero(db):
    s = _store(db)
    sid = _open(s)
    _fill(s, sid, 1)
    m = s.metrics(sid)                     # no price map supplied
    assert m["nav"] is None
    assert m["net_return"] is None
    assert m["blocked_forward_pnl"] is None
    assert m["fills"] == 1
    priced = s.metrics(sid, {"BTCUSDT": "61000"})
    assert priced["nav"] is not None and priced["net_return"] is not None


# ── PHASE: counterfactual Guardian tracking ─────────────────────────────────

def test_a_guardian_block_is_recorded_and_stays_blocked(db):
    s = _store(db)
    sid = _open(s)
    s.append_event(sid, 1, ShadowEventKind.GUARDIAN, {"outcome": "BLOCKED"})
    s.record_blocked(sid, 1, symbol="BTCUSDT", side="BUY", quantity="1",
                     reference_price="60000", blocked_by="GUARDIAN",
                     reason_codes=["DRAWDOWN_LIMIT"])
    # A blocked proposal creates no fill and moves no cash — ever.
    st = s.derive_portfolio(sid)
    assert st.fills == 0
    assert st.cash == Decimal("250000")
    assert st.positions == {}
    assert len(s.counterfactuals(sid)) == 1


def test_the_counterfactual_measures_both_directions_honestly(db):
    s = _store(db)
    sid = _open(s)
    for seq, ref in ((1, "60000"), (2, "60000")):
        s.append_event(sid, seq, ShadowEventKind.GUARDIAN, {"outcome": "BLOCKED"})
        s.record_blocked(sid, seq, symbol="BTCUSDT", side="BUY", quantity="1",
                         reference_price=ref, blocked_by="GUARDIAN", reason_codes=["VOL"])
    up = s.observe_counterfactual(sid, 1, "62000")     # Guardian cost us
    down = s.observe_counterfactual(sid, 2, "58000")   # Guardian protected us
    assert up["forward_pnl"] == Decimal("2000")
    assert down["forward_pnl"] == Decimal("-2000")
    m = s.metrics(sid)
    assert m["guardian_blocks"] == 2
    assert m["blocked_measured"] == 2
    assert m["blocked_forward_pnl"] == Decimal("0")


def test_counterfactual_records_carry_no_execution_authority(db):
    s = _store(db)
    sid = _open(s)
    s.append_event(sid, 1, ShadowEventKind.GUARDIAN, {"outcome": "BLOCKED"})
    s.record_blocked(sid, 1, symbol="BTCUSDT", side="BUY", quantity="1",
                     reference_price="60000", blocked_by="GUARDIAN", reason_codes=["VOL"])
    s.observe_counterfactual(sid, 1, "62000")
    # Even after showing the block was costly, nothing became a position.
    assert s.derive_portfolio(sid).positions == {}
    assert s.derive_portfolio(sid).fills == 0


# ── PHASE: the no-order proof ───────────────────────────────────────────────

def test_the_module_has_no_execution_entrypoint():
    import saathi.platform.tg.shadow_session as mod
    src = open(mod.__file__).read()
    for banned in ("import ccxt", "binance", "requests.post", "httpx.post", "urllib.request"):
        assert banned not in src, f"shadow session must not reach a venue: {banned}"
    for name in dir(mod.ShadowSessionStore):
        assert not name.startswith(("submit", "execute", "send", "place")), name


def test_metrics_assert_the_structural_zeroes(db):
    s = _store(db)
    sid = _open(s)
    _fill(s, sid, 1)
    m = s.metrics(sid)
    assert m["real_order_attempts"] == 0
    assert m["private_api_calls"] == 0
    assert m["real_ledger_mutations"] == 0


def test_an_execution_capable_object_is_refused_at_the_boundary():
    class LooksLikeShadow:
        symbol = "BTCUSDT"

        def submit(self):  # the thing that must never be here
            raise AssertionError("never")

    with pytest.raises(ShadowAuthorityError):
        assert_no_execution_authority(LooksLikeShadow())

    class RealShadow:
        symbol = "BTCUSDT"
        quantity = Decimal("1")

    assert_no_execution_authority(RealShadow())  # does not raise


def test_shadow_tables_are_separate_from_paper_and_real_ledgers(db):
    s = _store(db)
    sid = _open(s)
    _fill(s, sid, 1)
    names = {r[0] for r in s.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"shadow_sessions", "shadow_events", "shadow_fills", "shadow_counterfactuals"} <= names
    # Shadow writes nothing into a paper or real ledger table.
    for t in names:
        if "paper" in t.lower() or "ledger" in t.lower():
            n = s.connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            assert n == 0, f"shadow mutated {t}"


# ── PHASE: fault injection ──────────────────────────────────────────────────

def test_out_of_order_and_gapped_sequences_stay_consistent(db):
    s = _store(db)
    sid = _open(s)
    _fill(s, sid, 5, ref="60000", px="60000", fee="10")
    _fill(s, sid, 2, ref="59000", px="59000", fee="10")
    st = s.derive_portfolio(sid)
    assert st.fills == 2
    # Derivation is by seq order, so the gap and the arrival order do not matter.
    assert [f["seq"] for f in s.fills(sid)] == [2, 5]
    assert s.next_seq(sid) == 6


def test_a_corrupt_row_is_refused_rather_than_parsed_loosely(db):
    s = _store(db)
    sid = _open(s)
    _fill(s, sid, 1)
    s.connection.execute(
        "UPDATE shadow_fills SET quantity='not-a-number' WHERE session_id=? AND seq=1", (sid,))
    s.connection.commit()
    with pytest.raises(Exception):
        s.derive_portfolio(sid)


def test_a_newer_schema_is_refused_not_guessed(db):
    s = _store(db)
    s.connection.execute("UPDATE shadow_session_meta SET schema_version=99 WHERE singleton=1")
    s.connection.commit()
    s.close()
    with pytest.raises(ShadowError):
        _store(db)


def test_an_unknown_session_is_an_error_not_an_empty_book(db):
    s = _store(db)
    with pytest.raises(ShadowError):
        s.derive_portfolio("shadow-does-not-exist")
    assert s.get_session("shadow-does-not-exist") is None


def test_quantities_are_never_parsed_loosely(db):
    s = _store(db)
    sid = _open(s)
    for bad in (None, True, "abc"):
        with pytest.raises(Exception):
            s.record_fill(sid, 99, symbol="BTCUSDT", side="BUY", quantity=bad,
                          reference_price="1", fill_price="1", fee="0")


def test_two_sessions_do_not_bleed_into_each_other(db):
    s = _store(db)
    a = _open(s)
    b = _open(s)
    _fill(s, a, 1)
    assert s.derive_portfolio(b).fills == 0
    assert s.derive_portfolio(a).fills == 1
