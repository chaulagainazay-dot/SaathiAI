"""M — TRACKER_MARKET_HISTORY_READMODEL tests (Phase 27).

Offline: real provider with a monkeypatched `_get` returning canned public-API shapes.
Proves host policy, history parsing/validation, ranges/granularity, symbol resolution,
descriptive indicators (+ semantic boundary), reconciliation, chart model, chat/voice,
catalyst context, cache, failure states, and zero canonical/authority writes.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from saathi.platform.market_data.tracker import chart, indicators as ind
from saathi.platform.market_data.tracker.models import (
    MarketPoint, ReconVerdict, TrackerStatus, business_date_epoch,
)
from saathi.platform.market_data.tracker.provider import (
    NepsePortfolioTrackerProvider, _host_ok,
)

DAILY_ROWS = [
    {"business_date": "2026-09-09", "open_price": "548", "high_price": "551", "low_price": "547", "close_price": "550", "total_traded_quantity": "1000", "total_traded_value": "550000"},
    {"business_date": "2026-09-10", "open_price": "550", "high_price": "553", "low_price": "549", "close_price": "551", "total_traded_quantity": "1200"},
    {"business_date": "2026-09-11", "open_price": "552", "high_price": "554.9", "low_price": "551", "close_price": "552", "total_traded_quantity": "37182"},
]
SCRIPT = {"company_name": "Nabil Bank Limited", "sector_name": "Commercial Banks",
          "eps": "28.36", "pe_ratio": "19.46", "pb_ratio": "2.23", "dividend_yield": "2.86",
          "market_capitalization": "149354631168", "fifty_two_week_high": "568",
          "fifty_two_week_low": "471", "last_traded_price": "552.00", "ltp": "552"}
DIVS = [{"symbol": "NABIL", "fiscal_year": "2081/82", "bonus_share": "11", "cash_dividend": "0.58",
         "total_dividend": "11.58", "book_close_date": "2026-01-01", "published_date": "2025-12-01"},
        {"symbol": "SCB", "fiscal_year": "2081/82", "cash_dividend": "5", "total_dividend": "5"}]


def _provider(rows=DAILY_ROWS, script=SCRIPT, divs=DIVS, counter=None):
    p = NepsePortfolioTrackerProvider()

    def fake_get(path):
        if counter is not None:
            counter["n"] = counter.get("n", 0) + 1
        if path.startswith("/history/"):
            return rows, TrackerStatus.TRACKER_AVAILABLE
        if path.startswith("/scripts/"):
            return script, TrackerStatus.TRACKER_AVAILABLE
        if path.startswith("/announced-dividends"):
            return divs, TrackerStatus.TRACKER_AVAILABLE
        if path.startswith("/market/status"):
            return {"is_open": False, "status": "CLOSED"}, TrackerStatus.TRACKER_AVAILABLE
        return None, TrackerStatus.TRACKER_UNAVAILABLE
    p._get = fake_get
    return p


# 1 — host allowlist / SSRF
def test_host_policy():
    assert _host_ok("https://api.nepseportfoliotracker.app/api/x")
    assert _host_ok("https://nepseportfoliotracker.app/api/x")
    assert not _host_ok("https://evil.example/api")
    assert not _host_ok("http://127.0.0.1/api")
    assert not _host_ok("http://169.254.169.254/latest/meta-data")


# 2 — history parse + typed contract
def test_history_parse():
    s, st = _provider().market_history("NABIL", "1M")
    assert st == TrackerStatus.TRACKER_AVAILABLE and s is not None
    assert s.symbol == "NABIL" and s.instrument_id == "NEPSE:NABIL"
    assert s.data_class == "THIRD_PARTY_HISTORICAL_SERIES"
    assert s.point_in_time_capability == "HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED"
    assert len(s.points) == 3 and str(s.latest_close) == "552"
    assert s.points[0].timestamp < s.points[-1].timestamp   # ordered


# 3 — OHLC validation: bad candle rejected, not repaired
def test_ohlc_validation_rejects():
    bad = DAILY_ROWS + [{"business_date": "2026-09-12", "open_price": "10", "high_price": "5",
                         "low_price": "9", "close_price": "8", "total_traded_quantity": "1"}]  # high<low
    s, st = _provider(rows=bad).market_history("NABIL", "1M")
    assert len(s.points) == 3   # bad row dropped
    assert any("invalid row" in l for l in s.limitations)


# 4 — duplicate timestamp dropped
def test_duplicate_timestamp():
    dup = DAILY_ROWS + [dict(DAILY_ROWS[-1])]
    s, _ = _provider(rows=dup).market_history("NABIL", "1M")
    assert len(s.points) == 3
    assert any("duplicate" in l for l in s.limitations)


# 5 — all-invalid → INVALID_SERIES
def test_invalid_series():
    s, st = _provider(rows=[{"business_date": "x", "open_price": "a"}]).market_history("NABIL", "1M")
    assert s is None and st == TrackerStatus.INVALID_SERIES


# 6 — unsupported range
def test_range_validation():
    s, st = _provider().market_history("NABIL", "10Y")
    assert s is None and st == TrackerStatus.HISTORICAL_RANGE_UNAVAILABLE


# 7 — symbol resolution failure
def test_symbol_unresolved():
    s, st = _provider().market_history("??", "1M")
    assert s is None and st == TrackerStatus.SYMBOL_UNRESOLVED


# 8 — intraday vs daily granularity
def test_granularity():
    assert _provider().market_history("NABIL", "1D")[0].timeframe == "INTRADAY"
    assert _provider().market_history("NABIL", "1Y")[0].timeframe == "DAILY"


# 9 — indicators numeric correctness + warmup None
def test_indicators_values():
    closes = [Decimal(x) for x in [1, 2, 3, 4, 5, 6]]
    sma = ind.sma(closes, 3).series["sma_3"]
    assert sma[0] is None and sma[1] is None and sma[2] == 2.0 and sma[5] == 5.0
    e = ind.ema(closes, 3).series["ema_3"]
    assert e[2] == 2.0 and e[-1] is not None
    up = [Decimal(x) for x in range(1, 20)]
    r = ind.rsi(up).series["rsi"]
    assert r[14] is not None and r[14] >= 99.0        # monotonic up → RSI ~100
    m = ind.macd(closes)
    assert set(m.series) == {"macd", "signal", "histogram"}
    b = ind.bollinger([Decimal(5)] * 25, 20)
    assert b.series["bb_upper"][-1] == b.series["bb_lower"][-1]  # zero variance
    pts = [MarketPoint(i, "d", Decimal(10), Decimal(12), Decimal(9), Decimal(11), Decimal(1)) for i in range(20)]
    assert ind.atr(pts, 14).series["atr"][-1] is not None


# 10 — indicator semantic boundary
def test_indicator_semantic_boundary():
    assert ind.KIND == "DESCRIPTIVE_ANALYTICS"
    src = open(ind.__file__).read().upper()
    for banned in ("BUY_SIGNAL", "SELL_SIGNAL", "TARGET_PRICE", "STOP_LOSS", "POSITION_SIZ"):
        assert banned not in src
    assert "from saathi.platform.signal" not in open(ind.__file__).read()


# 11 — params exposed
def test_indicator_params_exposed():
    assert ind.rsi([Decimal(1)] * 20).params == {"period": 14}
    assert ind.macd([Decimal(1)] * 40).params == {"fast": 12, "slow": 26, "signal": 9}


# 12 — reconciliation verdicts (official authority)
def test_reconciliation(monkeypatch):
    p = _provider()
    monkeypatch.setattr(chart, "_official_ltp", lambda s: (Decimal("552"), True))
    assert chart.reconcile_current("NABIL", provider=p).verdict == ReconVerdict.CONFIRMED
    monkeypatch.setattr(chart, "_official_ltp", lambda s: (Decimal("600"), True))
    r = chart.reconcile_current("NABIL", provider=p)
    assert r.verdict == ReconVerdict.SOURCE_DISAGREEMENT
    assert r.authority == "OFFICIAL_PAGE_OBSERVED" and r.official_ltp == Decimal("600")
    monkeypatch.setattr(chart, "_official_ltp", lambda s: (None, False))
    assert chart.reconcile_current("NABIL", provider=p).verdict == ReconVerdict.OFFICIAL_UNAVAILABLE


# 13 — chart model
def test_chart_model():
    m = chart.build_chart_model("NABIL", "1M", which_indicators=["sma", "rsi"], provider=_provider())
    assert m["available"] and m["ohlc"] and m["volume"]
    assert "sma_20" in m["indicators"] and m["indicators_kind"] == "DESCRIPTIVE_ANALYTICS"
    assert m["fundamentals"]["eps"] == "28.36"
    assert m["dividends"] and m["point_in_time_capability"] == "HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED"
    assert any("not canonical MD-1" in l for l in m["limitations"])


# 14 — chat
def test_chat(monkeypatch):
    p = _provider()
    a = chart.chat_answer_tracker("show NABIL 1M trend", provider=p)
    assert "NABIL" in a["answer"] and "third-party" in a["source"].lower()
    r = chart.chat_answer_tracker("what is NABIL RSI?", provider=p)
    assert "RSI" in r["answer"] and "signal" in r["answer"].lower()
    f = chart.chat_answer_tracker("NABIL P/E?", provider=p)
    assert "P/E" in f["answer"] and "19.46" in f["answer"]
    dv = chart.chat_answer_tracker("show NABIL dividends", provider=p)
    assert "dividend" in dv["answer"].lower()
    monkeypatch.setattr(chart, "_official_ltp", lambda s: (Decimal("552"), True))
    cur = chart.chat_answer_tracker("latest NABIL price now", provider=p)
    assert "OFFICIAL" in cur["answer"] and "authoritative" in cur["source"].lower()


# 15 — voice
def test_voice():
    v = chart.voice_answer_tracker("NABIL 1 year trend", provider=_provider())
    assert "NABIL" in v


# 16 — catalyst historical context (never canonical reaction)
def test_catalyst_context():
    c = chart.catalyst_historical_context("NABIL", "1M", provider=_provider())
    assert c["context_kind"] == "THIRD_PARTY_HISTORICAL_CONTEXT"
    assert c["is_canonical_reaction"] is False and c["available"] is True


# 17 — cache: second call does not re-fetch
def test_cache():
    counter = {"n": 0}
    p = _provider(counter=counter)
    p.market_history("NABIL", "1M")
    n1 = counter["n"]
    p.market_history("NABIL", "1M")
    assert counter["n"] == n1   # served from cache


# 18 — failure states propagate, don't raise
def test_failure_states():
    p = NepsePortfolioTrackerProvider()
    p._get = lambda path: (None, TrackerStatus.TRACKER_RATE_LIMITED)
    s, st = p.market_history("NABIL", "1M")
    assert s is None and st == TrackerStatus.TRACKER_RATE_LIMITED


# 19 — no canonical / authority writes in tracker modules
def test_no_canonical_or_authority():
    import saathi.platform.market_data.tracker.provider as pv
    import saathi.platform.market_data.tracker.chart as ch
    for m in (pv, ch, ind):
        src = open(m.__file__).read()
        assert "insert_bar" not in src and "INTO md_bars" not in src and "insert_quote" not in src
        for banned in ("ExecutionGateway", "place_order", "trading_guardian", "portfolio_construction"):
            assert banned not in src


# 20 — point-in-time limitation explicit
def test_point_in_time():
    s, _ = _provider().market_history("NABIL", "5Y")
    assert s.point_in_time_capability == "HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED"
    assert business_date_epoch("2026-09-11") is not None
    assert business_date_epoch("bad") is None
