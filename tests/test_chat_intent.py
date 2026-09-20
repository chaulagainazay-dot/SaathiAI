"""Finance chat-intent routing guards (hermetic — detection only, engines monkeypatched)."""
from __future__ import annotations

from saathi.platform.finance import chat_intent as ci


def test_symbol_extraction():
    assert ci._symbol("fundamentals of NABIL") == "NABIL"
    assert ci._symbol("setup for BTC") == "BTC"
    # low-level extractor may pick a stray token; the handle_* guard is what prevents hijack
    assert ci.handle_finance_chat("what is your name") is None


def test_non_market_falls_through():
    assert ci.handle_finance_chat("what is your name") is None
    assert ci.handle_finance_chat("write me a poem") is None


def test_nepse_symbol_without_keyword_ignored():
    # a bare uppercase token that isn't crypto and no finance keyword → don't hijack
    assert ci.handle_finance_chat("CALL ME") is None


def test_crypto_symbol_routes(monkeypatch):
    monkeypatch.setattr(ci, "_technical", lambda m, s: {"handled": True, "kind": "technical", "text": f"{m} {s} ok"})
    r = ci.handle_finance_chat("BTC")
    assert r and r["kind"] == "technical" and "CRYPTO BTC" in r["text"]


def test_keyword_routes_to_strategy(monkeypatch):
    monkeypatch.setattr(ci, "_strategy", lambda m, s: {"handled": True, "kind": "strategy", "text": "plan"})
    r = ci.handle_finance_chat("give me an ICT strategy for NABIL")
    assert r and r["kind"] == "strategy"


def test_movers_no_symbol(monkeypatch):
    monkeypatch.setattr(ci, "_movers", lambda: {"handled": True, "kind": "movers", "text": "movers"})
    r = ci.handle_finance_chat("top gainers today")
    assert r and r["kind"] == "movers"
