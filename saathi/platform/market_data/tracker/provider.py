"""Governed read-only HTTP provider for NEPSE Portfolio Tracker's PUBLIC REST API.

No credentials, no MCP key, no cookies, no browser. Host-allowlisted, bounded timeout /
response size / retries / concurrency, cross-host redirects rejected. Never writes
md_bars/md_quotes. Data is THIRD_PARTY_STRUCTURED_MARKET_DATA.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

import requests

from saathi.browser.policy import check_domain
from saathi.platform.market_data.tracker.models import (
    DATA_CLASS, RANGE_GRANULARITY, SUPPORTED_RANGES,
    DividendRecord, FundamentalSnapshot, MarketPoint, MarketSeries, TrackerStatus,
    business_date_epoch, dec,
)

# api.<host> is the documented backend; the apex mirror is used where DNS for the
# subdomain is unavailable. Both are official NEPSE Portfolio Tracker hosts.
ALLOWED_HOSTS = ("api.nepseportfoliotracker.app", "nepseportfoliotracker.app")
_BASES = ("https://api.nepseportfoliotracker.app/api", "https://nepseportfoliotracker.app/api")
_UA = "SaathiOS/1.0 (+read-only market analytics; contact owner)"
_TIMEOUT = 12.0
_MAX_BYTES = 8 * 1024 * 1024
_MAX_RETRIES = 2
_CACHE_TTL = {"history": 300.0, "fundamentals": 300.0, "dividends": 900.0,
              "quote": 60.0, "market_status": 60.0}
_CACHE_MAX = 256


def _host_ok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        return False
    # SSRF defense: reject private/loopback/metadata even for an allowlisted name.
    return check_domain(url, allowed_hosts=list(ALLOWED_HOSTS)).allowed


class NepsePortfolioTrackerProvider:
    """One bounded HTTP client with a small TTL cache. Read-only."""

    def __init__(self, *, timeout: float = _TIMEOUT, session: requests.Session | None = None):
        self._timeout = timeout
        self._sess = session or requests.Session()
        self._sess.headers.update({"User-Agent": _UA, "Accept": "application/json"})
        self._cache: dict = {}
        self._lock = threading.Lock()
        self._sema = threading.Semaphore(2)   # bound concurrent outbound requests

    # ── governed transport ────────────────────────────────────────────────────
    def _get(self, path: str) -> tuple[dict | list | None, TrackerStatus]:
        last = TrackerStatus.TRACKER_UNAVAILABLE
        for base in _BASES:
            url = f"{base}{path}"
            if not _host_ok(url):
                last = TrackerStatus.TRACKER_UNAVAILABLE
                continue
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    with self._sema:
                        r = self._sess.get(url, timeout=self._timeout, allow_redirects=False,
                                           stream=True)
                    if r.status_code in (301, 302, 303, 307, 308):
                        loc = r.headers.get("location", "")
                        r.close()
                        if loc and not _host_ok(loc if "://" in loc else base + loc):
                            return None, TrackerStatus.TRACKER_UNAVAILABLE
                        return None, TrackerStatus.TRACKER_SCHEMA_CHANGED
                    if r.status_code == 429:
                        r.close()
                        return None, TrackerStatus.TRACKER_RATE_LIMITED
                    if r.status_code == 404:
                        r.close()
                        return None, TrackerStatus.HISTORICAL_RANGE_UNAVAILABLE
                    if r.status_code >= 400:
                        r.close()
                        last = TrackerStatus.TRACKER_UNAVAILABLE
                        continue
                    body = r.raw.read(_MAX_BYTES + 1, decode_content=True)
                    r.close()
                    if len(body) > _MAX_BYTES:
                        return None, TrackerStatus.INVALID_SERIES
                    import json
                    payload = json.loads(body.decode("utf-8", "replace"))
                    if not isinstance(payload, dict) or not payload.get("success"):
                        return None, TrackerStatus.TRACKER_SCHEMA_CHANGED
                    return payload.get("data"), TrackerStatus.TRACKER_AVAILABLE
                except requests.exceptions.RequestException:
                    last = TrackerStatus.TRACKER_UNAVAILABLE
                    time.sleep(0.2 * (attempt + 1))
                except (ValueError, UnicodeDecodeError):
                    return None, TrackerStatus.TRACKER_SCHEMA_CHANGED
        return None, last

    def _cache_get(self, key):
        with self._lock:
            hit = self._cache.get(key)
        if not hit:
            return None
        ts, kind, val = hit
        if (time.time() - ts) > _CACHE_TTL.get(kind, 300.0):
            return None
        return val

    def _cache_put(self, key, kind, val):
        with self._lock:
            if len(self._cache) >= _CACHE_MAX:
                oldest = min(self._cache, key=lambda k: self._cache[k][0])
                self._cache.pop(oldest, None)
            self._cache[key] = (time.time(), kind, val)

    # ── symbol resolution (reuses the instrument master; never guesses) ─────────
    @staticmethod
    def _resolve(symbol: str) -> tuple[str, str] | None:
        from saathi.platform.nepse.instruments import instrument_id_for, normalize_symbol
        try:
            return normalize_symbol(symbol), instrument_id_for(symbol)
        except Exception:
            return None

    # ── history ────────────────────────────────────────────────────────────────
    def market_history(self, symbol: str, range_: str = "1Y"
                       ) -> tuple[MarketSeries | None, TrackerStatus]:
        if range_ not in SUPPORTED_RANGES:
            return None, TrackerStatus.HISTORICAL_RANGE_UNAVAILABLE
        res = self._resolve(symbol)
        if res is None:
            return None, TrackerStatus.SYMBOL_UNRESOLVED
        sym, inst = res
        ckey = ("history", sym, range_)
        cached = self._cache_get(ckey)
        if cached is not None:
            return cached, TrackerStatus.TRACKER_AVAILABLE
        data, st = self._get(f"/history/{sym}?range={range_}")
        if st != TrackerStatus.TRACKER_AVAILABLE:
            return None, st
        rows = data if isinstance(data, list) else (data or {}).get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return None, TrackerStatus.TRACKER_SCHEMA_CHANGED
        series = self._parse_history(sym, inst, range_, rows)
        if series is None:
            return None, TrackerStatus.INVALID_SERIES
        self._cache_put(ckey, "history", series)
        return series, TrackerStatus.TRACKER_AVAILABLE

    def _parse_history(self, sym, inst, range_, rows) -> MarketSeries | None:
        pts: list[MarketPoint] = []
        limitations: list[str] = []
        rejected = 0
        seen_ts: set = set()
        last_ts = None
        for r in rows:
            bd = r.get("business_date") or r.get("date") or r.get("time")
            ts = business_date_epoch(bd) if bd else None
            o, h, l, c = dec(r.get("open_price")), dec(r.get("high_price")), dec(r.get("low_price")), dec(r.get("close_price"))
            v = dec(r.get("total_traded_quantity")) or dec(r.get("volume"))
            if None in (ts, o, h, l, c) or v is None:
                rejected += 1
                continue
            if h < max(o, c, l) or l > min(o, c, h) or v < 0:   # never silently repair
                rejected += 1
                continue
            if ts in seen_ts:
                limitations.append(f"duplicate timestamp {bd} dropped")
                continue
            seen_ts.add(ts)
            pts.append(MarketPoint(timestamp=ts, business_date=str(bd)[:10], open=o, high=h,
                                   low=l, close=c, volume=v, turnover=dec(r.get("total_traded_value"))))
        pts.sort(key=lambda p: p.timestamp)
        # ordering / gap reporting
        for p in pts:
            if last_ts is not None and p.timestamp <= last_ts:
                limitations.append("non-monotonic timestamps detected")
                break
            last_ts = p.timestamp
        if rejected:
            limitations.append(f"{rejected} invalid row(s) rejected (not repaired)")
        if not pts:
            return None
        return MarketSeries(symbol=sym, instrument_id=inst, range=range_,
                            timeframe=RANGE_GRANULARITY[range_], retrieved_at=time.time(),
                            points=tuple(pts), limitations=tuple(limitations))

    # ── fundamentals ─────────────────────────────────────────────────────────
    def fundamentals(self, symbol: str) -> tuple[FundamentalSnapshot | None, TrackerStatus]:
        res = self._resolve(symbol)
        if res is None:
            return None, TrackerStatus.SYMBOL_UNRESOLVED
        sym, inst = res
        ckey = ("fundamentals", sym, "")
        cached = self._cache_get(ckey)
        if cached is not None:
            return cached, TrackerStatus.TRACKER_AVAILABLE
        data, st = self._get(f"/scripts/{sym}")
        if st != TrackerStatus.TRACKER_AVAILABLE or not isinstance(data, dict):
            return None, (st if st != TrackerStatus.TRACKER_AVAILABLE else TrackerStatus.TRACKER_SCHEMA_CHANGED)
        snap = FundamentalSnapshot(
            symbol=sym, instrument_id=inst, retrieved_at=time.time(),
            company_name=str(data.get("company_name") or ""), sector=data.get("sector_name"),
            eps=dec(data.get("eps")), pe_ratio=dec(data.get("pe_ratio")),
            pb_ratio=dec(data.get("pb_ratio")), dividend_yield=dec(data.get("dividend_yield")),
            market_cap=dec(data.get("market_capitalization")),
            week52_high=dec(data.get("fifty_two_week_high")),
            week52_low=dec(data.get("fifty_two_week_low")),
            last_traded_price=dec(data.get("last_traded_price") or data.get("ltp")))
        self._cache_put(ckey, "fundamentals", snap)
        return snap, TrackerStatus.TRACKER_AVAILABLE

    def tracker_ltp(self, symbol: str):
        snap, st = self.fundamentals(symbol)
        return (snap.last_traded_price if snap else None), st

    # ── dividends ────────────────────────────────────────────────────────────
    def dividends(self, symbol: str | None = None
                  ) -> tuple[list[DividendRecord], TrackerStatus]:
        sym = None
        if symbol:
            res = self._resolve(symbol)
            if res is None:
                return [], TrackerStatus.SYMBOL_UNRESOLVED
            sym = res[0]
        ckey = ("dividends", sym or "*", "")
        cached = self._cache_get(ckey)
        if cached is not None:
            return cached, TrackerStatus.TRACKER_AVAILABLE
        data, st = self._get("/announced-dividends")
        if st != TrackerStatus.TRACKER_AVAILABLE or not isinstance(data, list):
            return [], (st if st != TrackerStatus.TRACKER_AVAILABLE else TrackerStatus.TRACKER_SCHEMA_CHANGED)
        recs = []
        for r in data:
            if sym and str(r.get("symbol", "")).upper() != sym:
                continue
            recs.append(DividendRecord(
                symbol=str(r.get("symbol", "")), fiscal_year=str(r.get("fiscal_year") or ""),
                bonus_share=dec(r.get("bonus_share")), cash_dividend=dec(r.get("cash_dividend")),
                total_dividend=dec(r.get("total_dividend")),
                book_close_date=r.get("book_close_date"), published_date=r.get("published_date")))
        self._cache_put(ckey, "dividends", recs)
        return recs, TrackerStatus.TRACKER_AVAILABLE

    def market_status(self) -> tuple[dict | None, TrackerStatus]:
        data, st = self._get("/market/status")
        return (data if isinstance(data, dict) else None), st


_DEFAULT: NepsePortfolioTrackerProvider | None = None


def get_provider() -> NepsePortfolioTrackerProvider:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = NepsePortfolioTrackerProvider()
    return _DEFAULT
