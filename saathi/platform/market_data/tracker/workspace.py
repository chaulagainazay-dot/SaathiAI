"""Native NEPSE Market Intelligence workspace — read-only projections that COMBINE
sources without merging authority.

CURRENT market  → official governed browser (OFFICIAL_PAGE_OBSERVED, authority)
HISTORY/analytics → NEPSE Portfolio Tracker (THIRD_PARTY_STRUCTURED_MARKET_DATA)
RESEARCH/CATALYST → frozen Research Surface + Fusion (unchanged)
PORTFOLIO → not connected (MCP deferred)

Each section is failure-isolated: one source down never collapses the workspace. No
trading semantics, no execution authority, no md_bars/md_quotes writes.
"""
from __future__ import annotations

import time
from decimal import Decimal

from saathi.platform.market_data.tracker import chart as _chart
from saathi.platform.market_data.tracker.compare import build_comparison
from saathi.platform.market_data.tracker.provider import get_provider

# typed UI states
AVAILABLE = "AVAILABLE"
STALE = "STALE"
PARTIAL_DATA = "PARTIAL_DATA"
LIVE_SOURCE_UNAVAILABLE = "LIVE_SOURCE_UNAVAILABLE"
HISTORY_SOURCE_UNAVAILABLE = "HISTORY_SOURCE_UNAVAILABLE"

_SORTS = {
    "volume": ("volume", True), "turnover": ("turnover", True),
    "gain": ("percent_change", True), "decline": ("percent_change", False),
    "pe": ("pe_ratio", False), "market_cap": ("market_cap", True),
}


def _official_snapshot():
    try:
        from saathi.platform.market_data.nepse_live_service import get_default_service
        return get_default_service().snapshot()
    except Exception:
        return None


def overview() -> dict:
    """Official current market (authority) + tracker descriptive context. Badged."""
    out = {"generated_at": time.time(), "current_market_authority": "OFFICIAL_PAGE_OBSERVED"}
    snap = _official_snapshot()
    if snap is not None:
        out["official"] = {"source": "Official NEPSE", "source_badge": "Official NEPSE · live observed",
                           **snap.summary()}
        out["official_state"] = AVAILABLE
    else:
        out["official"] = None
        out["official_state"] = LIVE_SOURCE_UNAVAILABLE
    try:
        ms, st = get_provider().market_status()
        out["tracker"] = {"source_badge": "NEPSE Portfolio Tracker · third-party", **(ms or {})} if ms else None
        out["tracker_state"] = AVAILABLE if ms else HISTORY_SOURCE_UNAVAILABLE
    except Exception:
        out["tracker"] = None
        out["tracker_state"] = HISTORY_SOURCE_UNAVAILABLE
    if out["official_state"] != AVAILABLE and out["tracker_state"] != AVAILABLE:
        out["state"] = PARTIAL_DATA
    else:
        out["state"] = AVAILABLE
    return out


def stock_table(*, sort: str = "turnover", sector: str | None = None, limit: int = 50,
                provider=None) -> dict:
    """Full-universe stock rows (tracker), with official LTP preferred where observed."""
    provider = provider or get_provider()
    rows, st = provider.stock_universe()
    if not rows:
        return {"state": HISTORY_SOURCE_UNAVAILABLE, "status": st.value, "rows": []}
    snap = _official_snapshot()
    official = {o.symbol.upper(): o for o in (snap.securities if snap else ())}
    pub = []
    for r in rows:
        if sector and (r.sector or "").lower() != sector.lower():
            continue
        d = r.to_public()
        o = official.get(r.symbol)
        if o is not None and o.ltp is not None:                 # official wins current LTP
            d["ltp"] = str(o.ltp)
            d["ltp_source"] = "OFFICIAL_PAGE_OBSERVED"
        pub.append(d)
    key, desc = _SORTS.get(sort, ("turnover", True))

    def sk(d):
        v = d.get(key)
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("-inf") if desc else float("inf")
    pub.sort(key=sk, reverse=desc)
    return {"state": AVAILABLE if snap else PARTIAL_DATA, "sort": sort, "sector": sector,
            "count": len(pub), "ltp_authority": "OFFICIAL_PAGE_OBSERVED where observed, else tracker",
            "rows": pub[:limit]}


def sectors(*, sort: str = "turnover", provider=None) -> dict:
    provider = provider or get_provider()
    secs, st = provider.sectors()
    if not secs:
        return {"state": HISTORY_SOURCE_UNAVAILABLE, "status": st.value, "sectors": []}
    keymap = {"turnover": "aggregate_turnover", "volume": "aggregate_volume",
              "change": "sector_percentage_change", "breadth": "advancers"}
    key = keymap.get(sort, "aggregate_turnover")

    def sk(s):
        v = getattr(s, key)
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("-inf")
    ranked = sorted(secs, key=sk, reverse=True)
    return {"state": AVAILABLE, "sort": sort, "count": len(ranked),
            "source_authority": "DERIVED_SECTOR_ANALYTICS",
            "sectors": [s.to_public() for s in ranked]}


def compare(symbols, range_: str = "1Y", *, mode: str = "NORMALIZED_PERCENT",
            provider=None) -> dict:
    cmp = build_comparison(symbols, range_, mode=mode, provider=provider)
    d = cmp.to_public()
    d["state"] = AVAILABLE if cmp.series else HISTORY_SOURCE_UNAVAILABLE
    return d


def symbol_panel(symbol: str, range_: str = "1Y", *, provider=None) -> dict:
    """Everything for one symbol: chart (tracker) + reconciliation (official authority)
    + fundamentals + dividends + research + catalyst context. Failure-isolated."""
    provider = provider or get_provider()
    panel = {"symbol": symbol.upper(), "range": range_}
    try:
        panel["chart"] = _chart.build_chart_model(symbol, range_, which_indicators=None,
                                                  provider=provider)
    except Exception as e:
        panel["chart"] = {"available": False, "error": str(e)[:120]}
    try:
        panel["reconciliation"] = _chart.reconcile_current(symbol, provider=provider).to_public()
    except Exception:
        panel["reconciliation"] = None
    try:
        panel["catalyst_history"] = _chart.catalyst_historical_context(symbol, "3M", provider=provider)
    except Exception:
        panel["catalyst_history"] = None
    panel["research"], panel["catalysts"] = _research_catalyst(symbol)
    panel["portfolio"] = {"connected": False, "message": "Portfolio connection not configured"}
    return panel


def _research_catalyst(symbol: str):
    """Read-only projection over the frozen Research Surface / Fusion (no edits)."""
    try:
        from saathi.market_intelligence.fusion import build_from_store, central_command_projection
        from saathi.platform.market_data.store import MarketDataStore
        snap = build_from_store(MarketDataStore())
        proj = central_command_projection(snap)
        sym = symbol.upper()
        events = [e for e in proj.get("latest_events", []) if str(e.get("symbol", "")).upper() == sym]
        catalysts = [c for c in proj.get("catalysts", []) if str(c.get("symbol", "")).upper() == sym]
        return ({"state": AVAILABLE, "events": events, "note": "frozen Research Surface projection"},
                {"state": AVAILABLE, "catalysts": catalysts,
                 "note": "Fusion; is_historical_reaction stays canonical/MD-1 only"})
    except Exception as e:
        return ({"state": PARTIAL_DATA, "events": [], "error": str(e)[:120]},
                {"state": PARTIAL_DATA, "catalysts": []})


# ── chat / voice (source-aware routing; reuses tracker + official) ─────────────
def workspace_chat(query: str, *, provider=None) -> dict:
    provider = provider or get_provider()
    ql = (query or "").lower()
    # sector strength
    if "sector" in ql or "hydropower" in ql or "commercial bank" in ql:
        d = sectors(sort="change", provider=provider)
        if d["state"] != AVAILABLE:
            return {"answer": "Sector data unavailable.", "source": "NEPSE Portfolio Tracker"}
        top = d["sectors"][0]
        return {"answer": f"Strongest sector by change: {top['sector']} "
                          f"({top['sector_percentage_change']}%), turnover Rs {top['aggregate_turnover']}, "
                          f"{top['advancers']} up / {top['decliners']} down. "
                          f"Source: NEPSE Portfolio Tracker (derived sector analytics).",
                "source": "NEPSE Portfolio Tracker · derived", "sectors": d["sectors"][:5]}
    # highest turnover/volume across market
    if ("highest turnover" in ql or "highest volume" in ql or "most active" in ql
            or "top turnover" in ql):
        sort = "volume" if "volume" in ql else "turnover"
        t = stock_table(sort=sort, limit=5, provider=provider)
        names = ", ".join(f"{r['symbol']} ({r.get(sort)})" for r in t["rows"])
        return {"answer": f"Top by {sort}: {names}.", "source": "combined (official LTP + tracker)"}
    # comparison
    if "compare" in ql or (" and " in ql and any(w in ql for w in ("month", "year", "week", "1m", "3m", "1y"))):
        import re
        syms = [s for s in re.findall(r"\b([A-Z]{2,10}\d{0,4})\b", (query or "").upper())
                if s not in _chart._STOPWORDS][:4]
        rng = _chart._pick_range(ql)
        if len(syms) >= 2:
            c = compare(syms, rng, provider=provider)
            if c.get("series"):
                parts = ", ".join(f"{s['symbol']} {s['change_pct']}%" for s in c["series"])
                return {"answer": f"{rng} normalized performance ({c['common_start']}→{c['common_end']}): "
                                  f"{parts}. Source: NEPSE Portfolio Tracker (third-party, descriptive).",
                        "source": "NEPSE Portfolio Tracker · third-party", "comparison": c}
        return {"answer": "Name 2–4 NEPSE symbols to compare (e.g. NABIL and API over 1 year).",
                "source": None}
    # consistency check
    if "consistent" in ql or "reconcil" in ql or "official and tracker" in ql:
        sym = _chart._pick_symbol(query or "") or "NABIL"
        r = _chart.reconcile_current(sym, provider=provider).to_public()
        return {"answer": f"{sym}: official {r['official_ltp']} vs tracker {r['tracker_ltp']} → {r['verdict']}.",
                "source": "reconciliation", "reconciliation": r}
    # delegate everything else (symbol trend/rsi/pe/dividends/current) to tracker chat
    return _chart.chat_answer_tracker(query, provider=provider)


def workspace_voice(query: str, *, provider=None) -> str:
    return workspace_chat(query, provider=provider).get("answer", "")
