"""Paper trading agent — deterministic setup gate + win/loss journaling (SIMULATION ONLY).

Hermetic: the market feed (signals_only / current_price) is monkeypatched, so no network
and no LLM. Proves the success-rate math is computed from real closed outcomes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.finance import paper_trading as pt
from saathi.platform.market_data import technical_analysis as ta


@pytest.fixture(autouse=True)
def _tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(pt, "DB_PATH", Path(tmp_path) / "paper.db")
    monkeypatch.setattr(pt, "_conn", None)
    yield


def _sig(trend, last, atr, rsi=55.0, market="CRYPTO", symbol="BTC"):
    return {"available": True, "market": market, "symbol": symbol, "source": "test",
            "evidence": {"last": last, "atr14": atr, "rsi14": rsi, "trend": trend,
                         "sma20": last, "sma50": last, "support": last - atr,
                         "resistance": last + atr, "swing_low": last - atr, "swing_high": last + atr,
                         "range_low": last - 2 * atr, "range_high": last + 2 * atr, "change_pct": 1.0,
                         "n_points": 60}}


def test_long_setup_fires_on_uptrend(monkeypatch):
    monkeypatch.setattr(ta, "signals_only", lambda m, s: _sig("UPTREND", 100.0, 4.0))
    p = pt.propose("CRYPTO", "BTC")
    assert p["setup"] is True and p["side"] == "LONG"
    assert p["entry"] == 100.0 and p["stop"] == 94.0 and p["target"] == 108.0  # 1.5/2.0 * ATR
    assert p["planned_r"] == 1.33


def test_sideways_is_honest_no_setup(monkeypatch):
    monkeypatch.setattr(ta, "signals_only", lambda m, s: _sig("SIDEWAYS", 100.0, 4.0))
    assert pt.propose("CRYPTO", "BTC")["setup"] is False


def test_no_data_no_setup(monkeypatch):
    monkeypatch.setattr(ta, "signals_only", lambda m, s: {"available": False, "error": "NO_DATA",
                                                          "market": "NEPSE", "symbol": "X"})
    assert pt.propose("NEPSE", "X")["setup"] is False


def test_win_when_target_hit(monkeypatch):
    monkeypatch.setattr(ta, "signals_only", lambda m, s: _sig("UPTREND", 100.0, 4.0))
    o = pt.open_trade("CRYPTO", "BTC")
    assert o["status"] == "OPEN"
    monkeypatch.setattr(ta, "current_price", lambda m, s: 108.0)  # >= target
    ev = pt.evaluate()
    assert ev["closed"] and ev["closed"][0]["status"] == "WON"
    st = pt.stats()
    assert st["won"] == 1 and st["lost"] == 0 and st["win_rate"] == 100.0
    assert st["total_r"] == pytest.approx(2.0 / 1.5, abs=0.01)  # target = 2*ATR, risk = 1.5*ATR


def test_loss_when_stop_hit(monkeypatch):
    monkeypatch.setattr(ta, "signals_only", lambda m, s: _sig("UPTREND", 100.0, 4.0))
    pt.open_trade("CRYPTO", "BTC")
    monkeypatch.setattr(ta, "current_price", lambda m, s: 94.0)  # <= stop
    pt.evaluate()
    st = pt.stats()
    assert st["lost"] == 1 and st["won"] == 0 and st["win_rate"] == 0.0
    assert st["total_r"] == pytest.approx(-1.0, abs=0.01)


def test_open_stays_open_between_levels(monkeypatch):
    monkeypatch.setattr(ta, "signals_only", lambda m, s: _sig("UPTREND", 100.0, 4.0))
    pt.open_trade("CRYPTO", "BTC")
    monkeypatch.setattr(ta, "current_price", lambda m, s: 101.0)  # between stop and target
    ev = pt.evaluate()
    assert ev["closed"] == []
    assert pt.stats()["open"] == 1
