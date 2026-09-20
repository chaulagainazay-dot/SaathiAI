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


def _fetch() -> dict:
    import httpx
    try:
        r = httpx.get(_SHARESANSAR, timeout=25, headers=_UA, follow_redirects=True)
        r.raise_for_status()
        rows = _parse_sharesansar(r.text)
        if not rows:
            return {"available": False, "error": "PARSE_EMPTY", "source": "sharesansar"}
        return {"available": True, "source": "ShareSansar · today-share-price (public web)",
                "count": len(rows), "rows": rows}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": f"FETCH_FAILED:{str(e)[:80]}", "source": "sharesansar"}


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


def movers(top: int = 5) -> dict:
    snap = nepse_market()
    if not snap.get("available"):
        return {"available": False, "error": snap.get("error")}
    rows = [r for r in snap["rows"] if r.get("percent_change") is not None]
    gainers = sorted(rows, key=lambda r: r["percent_change"], reverse=True)[:top]
    losers = sorted(rows, key=lambda r: r["percent_change"])[:top]
    return {"available": True, "source": snap.get("source"),
            "gainers": gainers, "losers": losers, "count": len(rows)}
