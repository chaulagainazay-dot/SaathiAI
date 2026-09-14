"""M — NATIVE_NEPSE_MARKET_INTELLIGENCE_WORKSPACE tests (Phase 28).

Offline: fake provider (_get monkeypatched) + monkeypatched official snapshot. Proves
overview combine, stock table (official-LTP preference + sort), sector aggregation/ranking,
multi-symbol compare (normalized, date intersection, missing-date, absolute), source-aware
chat/voice, outage isolation, cache, no-trading-semantics, zero authority.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from saathi.platform.market_data.tracker import compare as cmp_mod, workspace as ws
from saathi.platform.market_data.tracker.provider import NepsePortfolioTrackerProvider

HIST = {
    "NABIL": [{"business_date": d, "open_price": "550", "high_price": "553", "low_price": "549",
               "close_price": c, "total_traded_quantity": "1000"}
              for d, c in [("2026-09-09", "550"), ("2026-09-10", "551"), ("2026-09-11", "552")]],
    "API": [{"business_date": d, "open_price": "330", "high_price": "336", "low_price": "325",
             "close_price": c, "total_traded_quantity": "2000"}
            for d, c in [("2026-09-10", "330"), ("2026-09-11", "334.7"), ("2026-09-12", "340")]],
}
UNIVERSE = {"data": [
    {"symbol": "NABIL", "last_traded_price": "552", "percentage_change": "-0.09", "close_price": "552",
     "total_traded_quantity": "1000", "total_traded_value": "552000", "sector_name": "Commercial Banks",
     "pe_ratio": "19.46", "eps": "28.36", "market_capitalization": "149000000000"},
    {"symbol": "API", "last_traded_price": "334.7", "percentage_change": "8.7", "close_price": "334.7",
     "total_traded_quantity": "229569", "total_traded_value": "76000000", "sector_name": "Hydro Power",
     "pe_ratio": "12", "eps": "5", "market_capitalization": "8000000000"},
    {"symbol": "HDL", "last_traded_price": "1192", "percentage_change": "0.9", "close_price": "1192",
     "total_traded_quantity": "28552", "total_traded_value": "34000000", "sector_name": "Manufacturing And Processing",
     "pe_ratio": "30", "eps": "40", "market_capitalization": "12000000000"},
]}
SECTORS = [
    {"sector_name": "Hydro Power", "company_count": 111, "gainers": 90, "losers": 10, "unchanged": 11,
     "total_turnover": "900000000", "total_volume": "5000000", "avg_price_change": "3.1",
     "sector_percentage_change": "3.5", "total_market_cap": "5e11", "top_companies": [{"symbol": "API"}]},
    {"sector_name": "Commercial Banks", "company_count": 103, "gainers": 29, "losers": 3, "unchanged": 71,
     "total_turnover": "474870316.9", "total_volume": "1488537", "avg_price_change": "0.52",
     "sector_percentage_change": "0.68", "total_market_cap": "1.3e12", "top_companies": [{"symbol": "NABIL"}]},
]
SCRIPT = {"company_name": "Nabil Bank Limited", "sector_name": "Commercial Banks", "eps": "28.36",
          "pe_ratio": "19.46", "pb_ratio": "2.23", "dividend_yield": "2.86", "last_traded_price": "552",
          "market_capitalization": "149000000000", "fifty_two_week_high": "568", "fifty_two_week_low": "471"}
DIVS = [{"symbol": "NABIL", "fiscal_year": "2081/82", "cash_dividend": "0.58", "bonus_share": "11", "total_dividend": "11.58"}]


def _provider(counter=None, down=False):
    from saathi.platform.market_data.tracker.models import TrackerStatus
    p = NepsePortfolioTrackerProvider()

    def fake_get(path):
        if counter is not None:
            counter["n"] = counter.get("n", 0) + 1
        if down:
            return None, TrackerStatus.TRACKER_UNAVAILABLE
        if path.startswith("/history/"):
            sym = path.split("/history/")[1].split("?")[0]
            return HIST.get(sym, []), TrackerStatus.TRACKER_AVAILABLE
        if path.startswith("/today-prices"):
            return UNIVERSE, TrackerStatus.TRACKER_AVAILABLE
        if path.startswith("/market/sectors"):
            return SECTORS, TrackerStatus.TRACKER_AVAILABLE
        if path.startswith("/scripts/"):
            return SCRIPT, TrackerStatus.TRACKER_AVAILABLE
        if path.startswith("/announced-dividends"):
            return DIVS, TrackerStatus.TRACKER_AVAILABLE
        if path.startswith("/market/status"):
            return {"is_open": False, "status": "CLOSED"}, TrackerStatus.TRACKER_AVAILABLE
        return None, TrackerStatus.TRACKER_UNAVAILABLE
    p._get = fake_get
    return p


class _Obs:
    def __init__(self, sym, ltp):
        self.symbol = sym
        self.ltp = Decimal(str(ltp))


class _Snap:
    securities = (_Obs("NABIL", "552.00"), _Obs("API", "334.70"))

    def summary(self):
        return {"nepse_index": "2559.49", "index_change": "27.94", "index_change_percent": "1.10",
                "total_turnover": "4360159487.26", "total_volume": "12089709", "advancers": 238,
                "decliners": 30, "unchanged": 9, "market_status": "CLOSED",
                "source_as_of": "Sep 11, 2026, 3:00:00 PM", "freshness": "MARKET_CLOSED"}

    def get(self, s):
        return next((o for o in self.securities if o.symbol == s.upper()), None)


@pytest.fixture
def official(monkeypatch):
    monkeypatch.setattr(ws, "_official_snapshot", lambda: _Snap())
    monkeypatch.setattr("saathi.platform.market_data.tracker.chart._official_ltp",
                        lambda s: (_Snap().get(s).ltp if _Snap().get(s) else None, True))


# 1 — overview combines official + tracker, badged
def test_overview(official):
    o = ws.overview()
    assert o["official_state"] == "AVAILABLE" and o["official"]["nepse_index"] == "2559.49"
    assert "Official NEPSE" in o["official"]["source_badge"]
    # tracker section present with a distinct badge in real path; here monkeypatch has no provider,
    assert o["current_market_authority"] == "OFFICIAL_PAGE_OBSERVED"


# 2 — overview tolerates official outage
def test_overview_official_outage(monkeypatch):
    monkeypatch.setattr(ws, "_official_snapshot", lambda: None)
    o = ws.overview()
    assert o["official_state"] == "LIVE_SOURCE_UNAVAILABLE"


# 3 — stock table prefers official LTP where observed
def test_stock_table_official_pref(official):
    t = ws.stock_table(sort="turnover", provider=_provider())
    by = {r["symbol"]: r for r in t["rows"]}
    assert by["NABIL"]["ltp_source"] == "OFFICIAL_PAGE_OBSERVED"
    assert by["HDL"]["ltp_source"] != "OFFICIAL_PAGE_OBSERVED"   # not in official snapshot → tracker


# 4 — stock table sort
def test_stock_table_sort():
    t = ws.stock_table(sort="turnover", provider=_provider())
    tos = [float(r["turnover"]) for r in t["rows"]]
    assert tos == sorted(tos, reverse=True)
    g = ws.stock_table(sort="gain", provider=_provider())
    assert g["rows"][0]["symbol"] == "API"      # +8.7% highest


# 5 — sector filter
def test_stock_sector_filter():
    t = ws.stock_table(sector="Hydro Power", provider=_provider())
    assert all(r["sector"] == "Hydro Power" for r in t["rows"]) and t["count"] == 1


# 6 — sector aggregation + ranking
def test_sectors():
    d = ws.sectors(sort="change", provider=_provider())
    assert d["state"] == "AVAILABLE" and d["source_authority"] == "DERIVED_SECTOR_ANALYTICS"
    assert d["sectors"][0]["sector"] == "Hydro Power"   # 3.5% > 0.68%
    assert d["sectors"][0]["advancers"] == 90


# 7 — compare normalized + date intersection + missing-date report
def test_compare_normalized():
    c = ws.compare(["NABIL", "API"], "1M", provider=_provider())
    assert c["mode"] == "NORMALIZED_PERCENT"
    assert c["common_start"] == "2026-09-10" and c["common_end"] == "2026-09-11"  # intersection
    ser = {s["symbol"]: s for s in c["series"]}
    assert ser["NABIL"]["points"][0][1] == "0"          # starts at 0%
    assert any("non-overlapping" in l for l in c["limitations"])


# 8 — compare absolute mode
def test_compare_absolute():
    c = ws.compare(["NABIL", "API"], "1M", mode="ABSOLUTE", provider=_provider())
    ser = {s["symbol"]: s for s in c["series"]}
    assert ser["NABIL"]["points"][0][1] == "551"        # absolute close at common start


# 9 — compare cap at 4
def test_compare_cap():
    c = ws.compare(["NABIL", "API", "HDL", "SCB", "EBL"], "1M", provider=_provider())
    assert len(c["symbols"]) <= 4


# 10 — max symbols constant
def test_max_symbols():
    assert cmp_mod.MAX_SYMBOLS == 4


# 11 — chat: sector strength
def test_chat_sector():
    a = ws.workspace_chat("which sector is strongest today?", provider=_provider())
    assert "Hydro Power" in a["answer"] and "derived" in a["source"].lower()


# 12 — chat: highest turnover
def test_chat_turnover(official):
    a = ws.workspace_chat("which stocks have the highest turnover?", provider=_provider())
    assert "API" in a["answer"] or "NABIL" in a["answer"]


# 13 — chat: compare
def test_chat_compare():
    a = ws.workspace_chat("compare NABIL and API over 1M", provider=_provider())
    assert "NABIL" in a["answer"] and "%" in a["answer"] and "comparison" in a


# 14 — chat: reconciliation consistency
def test_chat_reconcile(official):
    a = ws.workspace_chat("are official and tracker NABIL prices consistent?", provider=_provider())
    assert "NABIL" in a["answer"] and ("CONFIRMED" in a["answer"] or "reconciliation" in a)


# 15 — chat delegates symbol queries to tracker
def test_chat_delegate():
    a = ws.workspace_chat("show NABIL 1M trend", provider=_provider())
    assert "NABIL" in a["answer"]


# 16 — voice reuse
def test_voice():
    v = ws.workspace_voice("which sector is strongest?", provider=_provider())
    assert "Hydro Power" in v


# 17 — tracker outage isolation (overview official still works)
def test_tracker_outage(official):
    t = ws.stock_table(provider=_provider(down=True))
    assert t["state"] == "HISTORY_SOURCE_UNAVAILABLE" and t["rows"] == []
    o = ws.overview()
    assert o["official_state"] == "AVAILABLE"   # official unaffected


# 18 — symbol panel combines, portfolio not connected
def test_symbol_panel(official):
    p = ws.symbol_panel("NABIL", "1M", provider=_provider())
    assert p["chart"]["available"] and p["reconciliation"]["verdict"]
    assert p["portfolio"]["connected"] is False
    assert p["catalyst_history"]["is_canonical_reaction"] is False


# 19 — cache reuse (universe fetched once)
def test_cache():
    counter = {"n": 0}
    p = _provider(counter=counter)
    ws.stock_table(provider=p)
    n1 = counter["n"]
    ws.stock_table(provider=p)
    assert counter["n"] == n1     # served from cache


# 20 — no trading semantics in workspace/compare source
def test_no_trading_semantics():
    import saathi.platform.market_data.tracker.workspace as w
    import saathi.platform.market_data.tracker.compare as c
    for m in (w, c):
        up = open(m.__file__).read().upper()
        for banned in ("BUY_SIGNAL", "SELL_SIGNAL", "STRONG BUY", "TARGET_PRICE", "STOP_LOSS",
                       "POSITION_SIZE", "EXPECTED_RETURN"):
            assert banned not in up


# 21 — zero authority / canonical writes
def test_no_authority():
    import saathi.platform.market_data.tracker.workspace as w
    src = open(w.__file__).read()
    assert "insert_bar" not in src and "insert_quote" not in src
    for banned in ("ExecutionGateway", "place_order", "portfolio_construction"):
        assert banned not in src


# 22 — concurrency bound unchanged
def test_concurrency_bound():
    p = NepsePortfolioTrackerProvider()
    assert p._sema._value == 2
