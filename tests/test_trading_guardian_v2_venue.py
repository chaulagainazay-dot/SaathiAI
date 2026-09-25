"""TRADING-GUARDIAN-V2 — per-venue policy convergence.

Core certification proof: a fully green candidate (active strategy, valid
construction inputs, passing risk portfolio) can STILL be blocked by the one
Guardian for an independent venue reason. No candidate-status bypass.
"""
from decimal import Decimal

import pytest

from saathi.platform.tg import (
    GateStatus,
    MarketRegimeEngine,
    PolicyEngine,
    KillSwitchStore,
    StrategyRegistry,
)
from saathi.platform.tg.domain import TradeProposal
from saathi.platform.tg.fixtures import trending_snapshot
from saathi.platform.tg.venue_policy import evaluate_venue, venue_for, session_required


# ── unit: deterministic venue gate ───────────────────────────────────────────────
def test_venue_routing():
    assert venue_for("BTCUSDT") == "CRYPTO"
    assert venue_for("NEPSE:NABIL") == "NEPSE"
    assert venue_for("AAPL") == "SIM"


def test_crypto_no_session_requirement():
    assert session_required("BTCUSDT") is False
    r = evaluate_venue("BTCUSDT")
    assert r["ok"] and r["reason"] == "OK"


def test_disabled_venue_blocks():
    r = evaluate_venue("BTCUSDT", disabled_venues=["CRYPTO"])
    assert not r["ok"]
    assert r["reason"] == "VENUE_DISABLED"


def test_session_unknown_fails_closed():
    r = evaluate_venue("NEPSE:NABIL", require_session=True, session_open=None)
    assert not r["ok"]
    assert r["reason"] == "VENUE_SESSION_UNKNOWN"


def test_session_closed_blocks():
    r = evaluate_venue("NEPSE:NABIL", require_session=True, session_open=False)
    assert not r["ok"]
    assert r["reason"] == "VENUE_SESSION_CLOSED"


def test_session_open_passes():
    r = evaluate_venue("NEPSE:NABIL", require_session=True, session_open=True)
    assert r["ok"]


# ── integration helpers (mirror the canonical guardian test green path) ───────────
def _base_proposal(**kw):
    p = TradeProposal(
        strategy_id="sid", strategy_version="1.0.0", symbol="TREND_TEST", side="BUY",
        quantity=Decimal("10"), entry_price=Decimal("100"), stop_price=Decimal("95"),
        take_profit_price=Decimal("110"), stop_distance=Decimal("5"),
        reward_to_risk=Decimal("2"), notional=Decimal("1000"), idempotency_key="idem-v2",
        org_id="o", workspace_id="w", sector="TECH",
    )
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _active_strategy():
    reg = StrategyRegistry()
    s = reg.register(
        name="T", slug="trend_following", org_id="o", workspace_id="w",
        regime_compatibility=["BULL_TREND", "SIDEWAYS", "HIGH_VOLATILITY"], activate=True,
    )
    return s, s.versions[0]


def _green_portfolio():
    return {
        "equity": "100000", "gross_exposure": "0", "open_positions": 0,
        "sector_exposure_pct": {}, "correlated_exposure_pct": 0,
        "portfolio_heat_pct": 0, "daily_realized_loss": 0, "weekly_realized_loss": 0,
        "drawdown_pct": 0, "consecutive_losses": 0, "reconciled": True,
    }


def test_venue_gate_present_and_passes_by_default():
    eng = PolicyEngine(kill_switches=KillSwitchStore())
    strat, ver = _active_strategy()
    snap = trending_snapshot()
    regime = MarketRegimeEngine().evaluate(snap)
    dec = eng.evaluate(
        _base_proposal(), snapshot=snap, strategy=strat, strategy_version=ver,
        regime=regime, portfolio=_green_portfolio(),
    )
    venue_gate = next(g for g in dec.gates if g.gate == "venue_enabled")
    assert venue_gate.status == GateStatus.PASS  # default: no venue disabled


def test_green_candidate_still_blocked_by_disabled_venue():
    """The independence proof: everything else green, venue disabled -> BLOCKED."""
    eng = PolicyEngine(kill_switches=KillSwitchStore())
    strat, ver = _active_strategy()
    snap = trending_snapshot()
    regime = MarketRegimeEngine().evaluate(snap)
    proposal = _base_proposal()
    venue = venue_for(proposal.symbol)  # "SIM" for TREND_TEST

    dec = eng.evaluate(
        proposal, snapshot=snap, strategy=strat, strategy_version=ver,
        regime=regime, portfolio=_green_portfolio(),
        extra={"disabled_venues": [venue]},
    )
    assert dec.allowed is False
    venue_gate = next(g for g in dec.gates if g.gate == "venue_enabled")
    assert venue_gate.status == GateStatus.FAIL
    assert venue_gate.reason_code == "VENUE_DISABLED"
