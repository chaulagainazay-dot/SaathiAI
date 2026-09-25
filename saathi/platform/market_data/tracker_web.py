"""NEPSE Portfolio Tracker web-data agent — pulls every live dataset the
nepseportfoliotracker.app site exposes as JSON, from its public `/api` origin.

Discovered live from the site's own network calls. All responses use a
{success, status, message, data} envelope. Observation-only, no account/auth
(forex & gold-silver are server-rendered behind auth and are not covered here).

Datasets: market news, full today-prices, gainers/losers, sectors, sub-indices,
IPO/right calendar, announced dividends/bonus/right, promoter share lock-in/unlock,
mergers & acquisitions, brokers, holidays, market pulse/status/summary.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import httpx

_BASE = "https://nepseportfoliotracker.app/api"
_UA = {"user-agent": "Mozilla/5.0 (SaathiOS NEPSE observer; research-only)"}
_TIMEOUT = 25.0
_TTL = 120.0  # seconds

_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}

AUTHORITY = {"authority": "observation_only", "source": "nepseportfoliotracker.app"}


def _get(path: str, params: dict | None = None, cache_key: str | None = None) -> tuple[Any, str | None]:
    """GET {BASE}{path}; unwrap the data envelope. Returns (data, error)."""
    key = cache_key or (path + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items())))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1], None
    try:
        r = httpx.get(_BASE + path, params=params, headers=_UA, timeout=_TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        body = r.json()
        data = body.get("data") if isinstance(body, dict) else body
        with _lock:
            _cache[key] = (now, data)
        return data, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:120]


def _rows(data: Any) -> list[dict]:
    """Normalize the envelope's data to a list of rows (handles {total,data:[...]})."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    return []


def _wrap(data, error, extra: dict | None = None) -> dict[str, Any]:
    if error:
        return {"available": False, "error": error, **AUTHORITY}
    return {"available": True, **(extra or {}), **AUTHORITY}


# ── individual datasets ───────────────────────────────────────────────────────

def news(limit: int = 20) -> dict[str, Any]:
    d, err = _get("/news", {"limit": limit})
    rows = _rows(d)
    return {**_wrap(d, err), "count": len(rows), "news": rows}


def today_prices(limit: int = 3000) -> dict[str, Any]:
    d, err = _get("/today-prices", {"limit": limit})
    rows = _rows(d)
    return {**_wrap(d, err), "count": len(rows), "stocks": rows}


def gainers(limit: int = 20) -> dict[str, Any]:
    d, err = _get("/market/gainers", {"limit": limit})
    return {**_wrap(d, err), "gainers": _rows(d)}


def losers(limit: int = 20) -> dict[str, Any]:
    d, err = _get("/market/losers", {"limit": limit})
    return {**_wrap(d, err), "losers": _rows(d)}


def sectors() -> dict[str, Any]:
    d, err = _get("/market/sectors")
    return {**_wrap(d, err), "sectors": d}


def subindices() -> dict[str, Any]:
    d, err = _get("/market/indices/performance")
    return {**_wrap(d, err), "indices": _rows(d)}


def ipos(limit: int = 50) -> dict[str, Any]:
    d, err = _get("/ipos", {"limit": limit})
    return {**_wrap(d, err), "ipos": _rows(d)}


def dividends(limit: int = 100) -> dict[str, Any]:
    d, err = _get("/announced-dividends", {"limit": limit})
    return {**_wrap(d, err), "dividends": _rows(d)}


def mergers(limit: int = 50) -> dict[str, Any]:
    d, err = _get("/mergers", {"limit": limit})
    return {**_wrap(d, err), "mergers": _rows(d)}


def brokers() -> dict[str, Any]:
    d, err = _get("/brokers")
    return {**_wrap(d, err), "brokers": d}


def holidays() -> dict[str, Any]:
    d, err = _get("/holidays")
    return {**_wrap(d, err), "holidays": _rows(d)}


def market_pulse() -> dict[str, Any]:
    d, err = _get("/market/pulse")
    return {**_wrap(d, err), "pulse": d}


def market_status() -> dict[str, Any]:
    d, err = _get("/market/status")
    return {**_wrap(d, err), "status": d}


def market_summary() -> dict[str, Any]:
    d, err = _get("/market/summary")
    return {**_wrap(d, err), "summary": d}


_INDEX_IDS = {
    "NEPSE": 58, "SENSITIVE": 57, "FLOAT": 62, "SENSITIVE_FLOAT": 63, "BANKING": 51,
    "HOTELS": 52, "OTHERS": 53, "HYDROPOWER": 54, "DEVELOPMENT_BANK": 55, "MANUFACTURING": 56,
    "NON_LIFE_INSURANCE": 59, "FINANCE": 60, "TRADING": 61, "MICROFINANCE": 64,
    "LIFE_INSURANCE": 65, "MUTUAL_FUND": 66, "INVESTMENT": 67,
}


def index_list() -> dict[str, Any]:
    return {"available": True, "indices": sorted(_INDEX_IDS), **AUTHORITY}


def index_history(index: str = "NEPSE", range_: str = "1Y") -> dict[str, Any]:
    """Index / sub-index daily OHLC, shaped like the stock chart (business_date + OHLC)."""
    key = (index or "NEPSE").upper().replace(" ", "_").replace("&", "AND")
    idx_id = _INDEX_IDS.get(key)
    if idx_id is None:
        return {"available": False, "error": f"unknown index '{index}'", "indices": sorted(_INDEX_IDS), **AUTHORITY}
    d, err = _get("/market/indices/history", {"index_id": idx_id, "range": range_}, cache_key=f"idxhist:{key}:{range_}")
    if err:
        return {"available": False, "error": err, **AUTHORITY}
    rows = _rows(d)
    ohlc = [{"business_date": x.get("business_date"), "open": x.get("open_index"),
             "high": x.get("high_index"), "low": x.get("low_index"),
             "close": x.get("closing_index"), "volume": x.get("turnover_volume")}
            for x in rows if x.get("closing_index") is not None]
    return {"available": True, "index": key, "range": range_, "count": len(ohlc), "ohlc": ohlc, **AUTHORITY}


def promoter_lockins(status: str = "all", max_rows: int = 400) -> dict[str, Any]:
    """Paginated promoter share lock-in / unlock schedule (site caps 100/page)."""
    all_rows: list[dict] = []
    total = None
    err = None
    for page in range(1, 20):
        d, e = _get("/promoter-lockins",
                    {"page": page, "limit": 100, "status": status, "sortBy": "lockin_date", "sortOrder": "DESC"},
                    cache_key=f"promoter:{status}:{page}")
        if e:
            err = e
            break
        if isinstance(d, dict):
            total = d.get("total", total)
        rows = _rows(d)
        if not rows:
            break
        all_rows += rows
        if (total and len(all_rows) >= total) or len(all_rows) >= max_rows:
            break
    if err and not all_rows:
        return {"available": False, "error": err, **AUTHORITY}
    return {"available": True, "total": total, "count": len(all_rows), "lockins": all_rows, **AUTHORITY}


# ── per-symbol aggregation ────────────────────────────────────────────────────

def _sym(x: Any) -> str:
    return str(x or "").upper()


def symbol_corporate(symbol: str) -> dict[str, Any]:
    """Everything corporate for one symbol: promoter lock-in/unlock, dividends, news, IPO/right."""
    sym = _sym(symbol)
    lk = promoter_lockins()
    lock = next((r for r in lk.get("lockins", []) if _sym(r.get("symbol")) == sym), None)
    dv = dividends(200)
    divs = [r for r in dv.get("dividends", []) if _sym(r.get("symbol")) == sym]
    nw = news(60)
    sym_news = [r for r in nw.get("news", []) if sym and sym in (str(r.get("headline") or "") + str(r.get("symbol") or "")).upper()]
    ip = ipos(80)
    sym_ipos = [r for r in ip.get("ipos", []) if _sym(r.get("symbol")) == sym]
    return {
        "available": True, "symbol": sym,
        "promoter_lockin": lock, "dividends": divs, "news": sym_news, "ipos": sym_ipos,
        **AUTHORITY,
    }
