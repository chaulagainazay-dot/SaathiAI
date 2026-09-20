"""Technical Analysis engine — deterministic signal math + crypto pair normalization.

Pure/hermetic: no network, no agent. Proves the evidence layer is correct and honest
(research-only envelope) independent of any LLM provider or market feed.
"""
from __future__ import annotations

from saathi.platform.market_data.technical_analysis import (
    _crypto_pair, compute_signals, DISCLAIMER,
)


def _series(closes):
    # minimal OHLC rows (high/low tracked around close)
    return [{"open": c, "high": c + 1, "low": c - 1, "close": c} for c in closes]


def test_uptrend_classified():
    closes = list(range(100, 160))  # strictly rising
    sig = compute_signals(_series(closes))
    assert sig is not None
    assert sig["trend"] == "UPTREND"
    assert sig["last"] == 159
    assert sig["sma20"] is not None and sig["sma50"] is not None
    assert 0 <= sig["rsi14"] <= 100


def test_downtrend_classified():
    closes = list(range(160, 100, -1))  # strictly falling
    sig = compute_signals(_series(closes))
    assert sig["trend"] == "DOWNTREND"


def test_insufficient_history_returns_none():
    assert compute_signals(_series([1, 2, 3])) is None


def test_rsi_all_gains_is_100():
    sig = compute_signals(_series(list(range(1, 40))))
    assert sig["rsi14"] == 100.0


def test_levels_bracket_last():
    closes = [10, 12, 8, 15, 9, 14, 11, 13, 7, 16, 10, 12, 9, 15, 11]
    sig = compute_signals(_series(closes))
    last = sig["last"]
    if sig["support"] is not None:
        assert sig["support"] <= last
    if sig["resistance"] is not None:
        assert sig["resistance"] >= last


def test_crypto_pair_normalization():
    assert _crypto_pair("BTC") == "BTCUSDT"
    assert _crypto_pair("btc") == "BTCUSDT"
    assert _crypto_pair("BTC/USDT") == "BTCUSDT"
    assert _crypto_pair("ETH-USD") == "ETHUSDT"
    assert _crypto_pair("SOLUSDT") == "SOLUSDT"
    assert _crypto_pair("USDC") == "USDC"  # already a quote-like suffix, left as-is


def test_disclaimer_is_research_only():
    assert "not financial advice" in DISCLAIMER.lower()
