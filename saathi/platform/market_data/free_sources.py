"""Free market-data agent — pulls the whole NEPSE market from public web sources with NO API
key and NO paid vendor. Personal-use, observation-only.

Primary source: ShareSansar's public "Today's Share Price" page (a full-market HTML table).
Fallback: Merolagani's live market page. Both are public web pages, scraped read-only and
cached so we never hammer them. On failure the agent returns available=False honestly — it
never fabricates prices.

This replaces the tiny built-in reference universe with the live, full listed market for the
screener, S-R screener, movers and quotes.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any

_UA = {"User-Agent": "Mozilla/5.0 (personal-use SaathiOS market reader)"}
_SHARESANSAR = "https://www.sharesansar.com/today-share-price"
_TTL_SEC = 120.0

_lock = threading.Lock()
_cache: dict[str, Any] = {"at": 0.0, "data": None}


def _num(s: str):
    s = re.sub(r"<[^>]+>", "", s or "").strip().replace(",", "")
    if s in ("", "-", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_sharesansar(html: str) -> list[dict]:
    m = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not m:
        return []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S)
    out = []
    for r in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(cells) < 13:
            continue
        symbol = re.sub(r"<[^>]+>", "", cells[1]).strip().upper()
        if not re.match(r"^[A-Z0-9/]{2,16}$", symbol):
            continue
        o, h, l, c = _num(cells[3]), _num(cells[4]), _num(cells[5]), _num(cells[6])
        ltp = _num(cells[7])
        vwap = _num(cells[10]) if len(cells) > 10 else None
        vol = _num(cells[11]) if len(cells) > 11 else None
        prev = _num(cells[12]) if len(cells) > 12 else None
        turnover = _num(cells[13]) if len(cells) > 13 else None
        price = ltp if ltp is not None else c
        chg = (price - prev) if (price is not None and prev) else None
        pct = (chg / prev * 100) if (chg is not None and prev) else None
        out.append({
            "symbol": symbol, "open": o, "high": h, "low": l, "close": c, "ltp": price,
            "prev_close": prev, "change": None if chg is None else round(chg, 2),
            "percent_change": None if pct is None else round(pct, 2),
            "vwap": vwap, "volume": vol, "turnover": turnover,
        })
    return out


_MEROLAGANI = "https://merolagani.com/StockQuote.aspx"


def _parse_merolagani(html: str) -> list[dict]:
    """Fallback market table (Merolagani StockQuote): #,Symbol,LTP,%Chg,High,Low,Open,Qty,Turnover."""
    m = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not m:
        return []
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(cells) < 9:
            continue
        symbol = re.sub(r"<[^>]+>", "", cells[1]).strip().upper()
        if not re.match(r"^[A-Z0-9/]{2,16}$", symbol):
            continue
        ltp, pct = _num(cells[2]), _num(cells[3])
        prev = (ltp / (1 + pct / 100)) if (ltp is not None and pct not in (None, -100)) else None
        chg = (ltp - prev) if (ltp is not None and prev is not None) else None
        out.append({"symbol": symbol, "ltp": ltp, "open": _num(cells[6]), "high": _num(cells[4]),
                    "low": _num(cells[5]), "close": ltp, "prev_close": None if prev is None else round(prev, 2),
                    "change": None if chg is None else round(chg, 2),
                    "percent_change": pct, "vwap": None, "volume": _num(cells[7]), "turnover": _num(cells[8])})
    return out


def _fetch() -> dict:
    import httpx
    try:
        r = httpx.get(_SHARESANSAR, timeout=25, headers=_UA, follow_redirects=True)
        r.raise_for_status()
        rows = _parse_sharesansar(r.text)
        if rows:
            return {"available": True, "source": "ShareSansar · today-share-price (public web)",
                    "count": len(rows), "rows": rows}
    except Exception:
        pass
    # Fallback: Merolagani (partial — top ~100 by activity)
    try:
        r = httpx.get(_MEROLAGANI, timeout=25, headers=_UA, follow_redirects=True)
        r.raise_for_status()
        rows = _parse_merolagani(r.text)
        if rows:
            return {"available": True, "source": "Merolagani · StockQuote (fallback, partial)",
                    "count": len(rows), "rows": rows}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": f"ALL_SOURCES_FAILED:{str(e)[:60]}", "source": "none"}
    return {"available": False, "error": "PARSE_EMPTY", "source": "none"}


def nepse_market(force: bool = False) -> dict:
    """Full NEPSE market snapshot from the free public source, cached for _TTL_SEC."""
    now = time.time()
    with _lock:
        if not force and _cache["data"] and (now - _cache["at"] < _TTL_SEC):
            return {**_cache["data"], "cached": True, "age_sec": round(now - _cache["at"], 1)}
    data = _fetch()
    if data.get("available"):
        with _lock:
            _cache["data"] = data
            _cache["at"] = now
    elif _cache["data"]:
        # serve last-good on failure, flagged honestly
        return {**_cache["data"], "stale": True, "last_error": data.get("error")}
    return {**data, "cached": False}


def nepse_quote(symbol: str) -> dict:
    sym = (symbol or "").strip().upper()
    snap = nepse_market()
    if not snap.get("available"):
        return {"available": False, "symbol": sym, "error": snap.get("error")}
    row = next((r for r in snap["rows"] if r["symbol"] == sym), None)
    if not row:
        return {"available": False, "symbol": sym, "error": "SYMBOL_NOT_LISTED"}
    return {"available": True, "symbol": sym, "quote": row, "source": snap.get("source")}


_company_cache: dict[str, Any] = {}
_COMPANY_TTL = 3600.0


def _parse_company(html: str) -> dict:
    out = {}
    m = re.search(r"52\s*Week\s*High-?Low\s*:?\s*(?:<[^>]*>\s*)*([\d,]+\.?\d*)\s*-\s*([\d,]+\.?\d*)", html, re.I)
    if m:
        out["week52_high"] = _num(m.group(1))
        out["week52_low"] = _num(m.group(2))
    m = re.search(r"(?:Last\s*Traded\s*Price|LTP)\s*:?\s*(?:<[^>]*>\s*)*([\d,]+\.?\d*)", html, re.I)
    if m:
        out["ltp"] = _num(m.group(1))
    m = re.search(r"Sector\s*:?\s*(?:<[^>]*>\s*)*([A-Za-z &/]{3,40})", html)
    if m:
        sec = m.group(1).strip()
        if sec.lower() not in ("wise share price",):
            out["sector"] = sec
    return out


def nepse_company(symbol: str) -> dict:
    """Per-company details scraped from the public company page (52-week high/low, LTP,
    sector where present). Cached ~1h. No API key."""
    sym = (symbol or "").strip().upper()
    if not re.match(r"^[A-Z0-9/]{2,16}$", sym):
        return {"available": False, "symbol": sym, "error": "BAD_SYMBOL"}
    now = time.time()
    hit = _company_cache.get(sym)
    if hit and (now - hit["at"] < _COMPANY_TTL):
        return {**hit["data"], "cached": True}
    import httpx
    try:
        r = httpx.get(f"https://www.sharesansar.com/company/{sym}", timeout=20, headers=_UA, follow_redirects=True)
        r.raise_for_status()
        parsed = _parse_company(r.text)
        if not parsed:
            return {"available": False, "symbol": sym, "error": "PARSE_EMPTY"}
        data = {"available": True, "symbol": sym, "source": "ShareSansar company page (public web)", **parsed}
        _company_cache[sym] = {"at": now, "data": data}
        return data
    except Exception as e:  # noqa: BLE001
        return {"available": False, "symbol": sym, "error": f"FETCH_FAILED:{str(e)[:80]}"}


# ── Full fundamentals (#1) — Merolagani company detail, static HTML, no API key ──
_fund_cache: dict[str, Any] = {}
_FUND_TTL = 6 * 3600.0
_MEROLAGANI_DETAIL = "https://merolagani.com/CompanyDetail.aspx?symbol="


def _grab(html: str, label: str):
    for pat in (re.escape(label) + r"\s*</[^>]+>\s*<[^>]*>\s*([0-9][0-9,\.]*)",
                re.escape(label) + r"[^<]{0,6}</t[dh]>\s*<td[^>]*>\s*([0-9][0-9,\.]*)"):
        m = re.search(pat, html, re.I)
        if m:
            return _num(m.group(1))
    return None


def nepse_fundamentals(symbol: str) -> dict:
    """Full fundamentals (EPS, P/E, P/B, book value, market cap) scraped from the public
    company detail page. Static HTML, no API key, cached ~6h."""
    sym = (symbol or "").strip().upper()
    if not re.match(r"^[A-Z0-9/]{2,16}$", sym):
        return {"available": False, "symbol": sym, "error": "BAD_SYMBOL"}
    now = time.time()
    hit = _fund_cache.get(sym)
    if hit and (now - hit["at"] < _FUND_TTL):
        return {**hit["data"], "cached": True}
    import httpx
    try:
        r = httpx.get(_MEROLAGANI_DETAIL + sym, timeout=20, headers=_UA, follow_redirects=True)
        r.raise_for_status()
        h = r.text
        data = {"available": True, "symbol": sym, "source": "Merolagani company detail (public web)",
                "eps": _grab(h, "EPS"), "pe": _grab(h, "P/E Ratio"),
                "pb": _grab(h, "PBV"), "book_value": _grab(h, "Book Value"),
                "market_cap": _grab(h, "Market Capitalization")}
        if not any(data[k] is not None for k in ("eps", "pe", "pb", "book_value", "market_cap")):
            return {"available": False, "symbol": sym, "error": "PARSE_EMPTY"}
        _fund_cache[sym] = {"at": now, "data": data}
        return data
    except Exception as e:  # noqa: BLE001
        return {"available": False, "symbol": sym, "error": f"FETCH_FAILED:{str(e)[:80]}"}


# ── Background 52-week range enrichment (#2) — fills all symbols slowly into a cache ──
_ranges: dict[str, dict] = {}          # symbol -> {high, low}
_range_state = {"running": False, "done": 0, "total": 0, "started_at": 0.0, "finished_at": 0.0}
_range_lock = threading.Lock()
_RANGE_GAP_SEC = 1.2                    # polite pacing between per-symbol page hits


def _enrich_ranges_worker():
    snap = nepse_market()
    symbols = [r["symbol"] for r in snap.get("rows", [])] if snap.get("available") else []
    with _range_lock:
        _range_state.update(total=len(symbols), done=0, started_at=time.time(), finished_at=0.0)
    for sym in symbols:
        if sym not in _ranges:
            c = nepse_company(sym)
            if c.get("available") and c.get("week52_high") is not None:
                _ranges[sym] = {"high": c["week52_high"], "low": c.get("week52_low")}
        with _range_lock:
            _range_state["done"] += 1
        time.sleep(_RANGE_GAP_SEC)
    with _range_lock:
        _range_state.update(running=False, finished_at=time.time())


def start_range_enrichment() -> dict:
    with _range_lock:
        if _range_state["running"]:
            return {"started": False, "already_running": True, **_range_state}
        _range_state["running"] = True
    threading.Thread(target=_enrich_ranges_worker, daemon=True).start()
    return {"started": True}


def ranges(start: bool = False) -> dict:
    if start and not _range_state["running"] and _range_state["done"] == 0:
        start_range_enrichment()
    with _range_lock:
        st = dict(_range_state)
    return {"available": True, "count": len(_ranges), "ranges": _ranges,
            "status": st, "source": "ShareSansar company pages (background, public web)"}


def movers(top: int = 5) -> dict:
    snap = nepse_market()
    if not snap.get("available"):
        return {"available": False, "error": snap.get("error")}
    rows = [r for r in snap["rows"] if r.get("percent_change") is not None]
    gainers = sorted(rows, key=lambda r: r["percent_change"], reverse=True)[:top]
    losers = sorted(rows, key=lambda r: r["percent_change"])[:top]
    return {"available": True, "source": snap.get("source"),
            "gainers": gainers, "losers": losers, "count": len(rows)}
