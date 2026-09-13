"""M — LIVE_NEPSE_BROWSER_MARKET_DATA: bounded live service, storage, consumers.

`NepseLiveService` holds ONE browser worker's most-recent observation, refreshes on a
bounded schedule (rarely when the market is closed), and on failure PRESERVES the last
good observation marked STALE — it never fabricates data and never falls back to
unofficial sources. Observations persist to additive `live_market_*` tables (clearly
NOT `md_bars`, NOT a second store). Read-only consumers project the same snapshot to
Central Command, chat, voice, the catalyst engine (CURRENT context only), and Trading
Guardian (observational input, zero execution authority).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import replace

from saathi.platform.market_data.live_observation import (
    DATA_CLASS, Freshness, LiveAcquisitionStatus, MarketState, NepseLiveMarketSnapshot,
    SymbolResolution,
)
from saathi.platform.market_data.nepse_live import SOURCE_TODAY_PRICE, observe_nepse_live

_LIVE_SCHEMA = """
CREATE TABLE IF NOT EXISTS live_market_snapshot (
    snapshot_id TEXT PRIMARY KEY, observed_at REAL NOT NULL, source_url TEXT NOT NULL,
    market_status TEXT NOT NULL, freshness TEXT NOT NULL, source_health TEXT NOT NULL,
    nepse_index TEXT, index_change TEXT, index_change_percent TEXT,
    total_turnover TEXT, total_volume TEXT, advancers INTEGER, decliners INTEGER, unchanged INTEGER,
    source_as_of TEXT, source_as_of_epoch REAL, data_class TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS live_market_observation (
    id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id TEXT NOT NULL, observed_at REAL NOT NULL,
    symbol TEXT NOT NULL, instrument_id TEXT NOT NULL, ltp TEXT, open TEXT, high TEXT, low TEXT,
    close TEXT, volume TEXT, turnover TEXT, data_class TEXT NOT NULL, source_url TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lmo_series ON live_market_observation(instrument_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_lms_time ON live_market_snapshot(observed_at DESC);
"""

REFRESH_OPEN_SEC = 60.0        # conservative; measured for reliability, not speed
REFRESH_CLOSED_SEC = 1800.0    # market closed: 30 min


def ensure_live_tables(store) -> None:
    store._conn.executescript(_LIVE_SCHEMA)
    store._conn.commit()


def persist_snapshot(store, snap: NepseLiveMarketSnapshot, *, persist_series: bool = True) -> None:
    """Persist a live snapshot + (optionally) its per-security observation series.
    BROWSER_OBSERVATION_SERIES — NEVER canonical exchange ticks, NEVER md_bars."""
    ensure_live_tables(store)
    d = snap.summary()
    store._conn.execute(
        "INSERT OR REPLACE INTO live_market_snapshot (snapshot_id, observed_at, source_url,"
        " market_status, freshness, source_health, nepse_index, index_change, index_change_percent,"
        " total_turnover, total_volume, advancers, decliners, unchanged, source_as_of,"
        " source_as_of_epoch, data_class, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (snap.snapshot_id, snap.observed_at, snap.source_url, snap.market_status.value,
         snap.freshness.value, snap.source_health.value, d.get("nepse_index"), d.get("index_change"),
         d.get("index_change_percent"), d.get("total_turnover"), d.get("total_volume"),
         snap.advancers, snap.decliners, snap.unchanged, snap.source_as_of, snap.source_as_of_epoch,
         DATA_CLASS, json.dumps(d)))
    if persist_series and snap.securities:
        store._conn.executemany(
            "INSERT INTO live_market_observation (snapshot_id, observed_at, symbol, instrument_id,"
            " ltp, open, high, low, close, volume, turnover, data_class, source_url)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(snap.snapshot_id, o.observed_at, o.symbol, o.instrument_id,
              _s(o.ltp), _s(o.open), _s(o.high), _s(o.low), _s(o.close), _s(o.volume),
              _s(o.turnover), DATA_CLASS, o.source_url) for o in snap.securities])
    store._conn.commit()


def _s(v):
    return None if v is None else str(v)


def latest_snapshot_row(store) -> dict | None:
    ensure_live_tables(store)
    r = store._conn.execute(
        "SELECT * FROM live_market_snapshot ORDER BY observed_at DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def observation_series(store, instrument_id: str, *, limit: int = 50) -> list[dict]:
    """BROWSER_OBSERVATION_SERIES for one instrument (operational history, not ticks)."""
    ensure_live_tables(store)
    rows = store._conn.execute(
        "SELECT * FROM live_market_observation WHERE instrument_id=? ORDER BY observed_at DESC LIMIT ?",
        (instrument_id, limit)).fetchall()
    return [dict(r) for r in rows]


class NepseLiveService:
    """One bounded live-market browser worker with a cached last observation."""

    def __init__(self, *, store=None, reader=None, persist: bool = True,
                 refresh_open_sec: float = REFRESH_OPEN_SEC,
                 refresh_closed_sec: float = REFRESH_CLOSED_SEC):
        self._store = store
        self._reader = reader
        self._persist = persist and store is not None
        self._refresh_open = refresh_open_sec
        self._refresh_closed = refresh_closed_sec
        self._last: NepseLiveMarketSnapshot | None = None
        self._last_ok: NepseLiveMarketSnapshot | None = None
        self._last_refresh_at: float = 0.0
        self._last_metrics: dict = {}

    def _interval(self) -> float:
        st = self._last.market_status if self._last else MarketState.UNKNOWN
        return self._refresh_closed if st == MarketState.CLOSED else self._refresh_open

    def refresh(self, *, force: bool = False, now: float | None = None) -> NepseLiveMarketSnapshot:
        now = now if now is not None else time.time()
        if not force and self._last and (now - self._last_refresh_at) < self._interval():
            return self._last  # bounded: do not hammer the site
        snap, metrics = observe_nepse_live(reader=self._reader, now=now)
        self._last_refresh_at = now
        self._last_metrics = metrics
        good = snap.source_health in (
            LiveAcquisitionStatus.NEPSE_LIVE_AVAILABLE,
            LiveAcquisitionStatus.NEPSE_MARKET_CLOSED,
            LiveAcquisitionStatus.NEPSE_LIVE_STALE)
        if good:
            self._last_ok = snap
            if self._persist:
                try:
                    persist_snapshot(self._store, snap)
                except Exception:
                    pass
        elif self._last_ok is not None:
            # failure containment: preserve last good, mark STALE, never fabricate
            snap = replace(
                self._last_ok, freshness=Freshness.STALE,
                source_health=LiveAcquisitionStatus.NEPSE_LIVE_STALE,
                limitations=tuple(self._last_ok.limitations) +
                (f"live read failed ({metrics.get('source_health')}); showing last observation",))
        self._last = snap
        return snap

    def snapshot(self, *, max_age_sec: float | None = None,
                 now: float | None = None) -> NepseLiveMarketSnapshot | None:
        if self._last is None:
            return None
        if max_age_sec is not None:
            now = now if now is not None else time.time()
            if (now - self._last.observed_at) > max_age_sec:
                return replace(self._last, freshness=Freshness.STALE)
        return self._last

    @property
    def last_metrics(self) -> dict:
        return dict(self._last_metrics)

    def health(self) -> dict:
        s = self._last
        return {
            "service": "nepse_live_browser", "acquisition_method": "OFFICIAL_LIVE_BROWSER",
            "data_class": DATA_CLASS, "source_url": SOURCE_TODAY_PRICE,
            "source_kind": "OFFICIAL_PAGE_OBSERVED (rendered DOM; not a licensed tick feed)",
            "browser_workers": 1, "last_refresh_at": self._last_refresh_at,
            "refresh_interval_sec": self._interval(), "last_metrics": self._last_metrics,
            "market_status": s.market_status.value if s else None,
            "freshness": s.freshness.value if s else None,
            "source_health": s.source_health.value if s else "NO_OBSERVATION_YET",
            "securities": len(s.securities) if s else 0,
        }


# ── read-only consumers (zero trade authority) ──────────────────────────────────
# process singleton so server + scheduler share ONE bounded browser worker.
_DEFAULT_SVC: "NepseLiveService | None" = None


def get_default_service() -> NepseLiveService:
    global _DEFAULT_SVC
    if _DEFAULT_SVC is None:
        from saathi.platform.market_data.store import MarketDataStore
        _DEFAULT_SVC = NepseLiveService(store=MarketDataStore())
    return _DEFAULT_SVC


def central_command_live_projection(snap: NepseLiveMarketSnapshot, *, watchlist=None,
                                    top_n: int = 8) -> dict:
    """Phase 13 — read-only NEPSE live tile for Central Command. No Buy/Sell controls."""
    if watchlist:
        wl = [o for o in (snap.get(sym) for sym in watchlist) if o is not None]
    else:
        wl = snap.top_by("turnover", top_n)
    return {
        "exchange": snap.exchange, "data_class": snap.data_class,
        "market_status": snap.market_status.value, "freshness": snap.freshness.value,
        "source_health": snap.source_health.value,
        "nepse_index": _s(snap.nepse_index), "index_change": _s(snap.index_change),
        "index_change_percent": _s(snap.index_change_percent),
        "total_turnover": _s(snap.total_turnover), "total_volume": _s(snap.total_volume),
        "advancers": snap.advancers, "decliners": snap.decliners, "unchanged": snap.unchanged,
        "observed_at": snap.observed_at, "source_as_of": snap.source_as_of,
        "source": "Official NEPSE (nepalstock.com)", "source_url": snap.source_url,
        "watchlist": [{"symbol": o.symbol, "ltp": _s(o.ltp), "point_change": _s(o.point_change),
                       "percent_change": _s(o.percent_change), "volume": _s(o.volume),
                       "observed_at": o.observed_at} for o in wl],
        "controls": [],  # explicitly no trade controls
    }


def _freshness_phrase(snap: NepseLiveMarketSnapshot) -> str:
    if snap.market_status == MarketState.CLOSED:
        return f"market is CLOSED (as of {snap.source_as_of})" if snap.source_as_of else "market is CLOSED"
    return f"observed {snap.freshness.value.lower()}" + (f", as of {snap.source_as_of}" if snap.source_as_of else "")


def chat_answer_live(snap: NepseLiveMarketSnapshot, query: str) -> dict:
    """Phase 14 — deterministic live-market chat. Always exposes source + freshness."""
    q = (query or "").lower().strip()
    base = {"source": "Official NEPSE (nepalstock.com)", "source_url": snap.source_url,
            "observed_at": snap.observed_at, "source_as_of": snap.source_as_of,
            "market_status": snap.market_status.value, "freshness": snap.freshness.value,
            "data_class": snap.data_class}

    def ans(text):
        return {**base, "answer": text}

    if "market open" in q or "is the market" in q or ("open" in q and "market" in q):
        return ans(f"NEPSE {'is OPEN' if snap.market_open else 'is CLOSED'} "
                   f"({_freshness_phrase(snap)}).")
    if "fresh" in q or "how old" in q or "how recent" in q:
        return ans(f"This NEPSE observation freshness is {snap.freshness.value} "
                   f"(observed at {snap.source_as_of or 'read time'}).")
    if ("highest volume" in q or "most volume" in q or "top volume" in q or
            "most active" in q or "highest turnover" in q):
        key = "turnover" if "turnover" in q else "volume"
        top = snap.top_by(key, 5)
        if not top:
            return ans("No live per-security observations available right now.")
        parts = ", ".join(f"{o.symbol} ({_s(getattr(o, key))})" for o in top)
        return ans(f"Top by {key} (live observed): {parts}. ({_freshness_phrase(snap)})")
    if ("nepse" in q and ("doing" in q or "right now" in q or "today" in q)) or "index" in q:
        return ans(f"NEPSE index {_s(snap.nepse_index)} "
                   f"({_s(snap.index_change)} / {_s(snap.index_change_percent)}%), turnover Rs "
                   f"{_s(snap.total_turnover)}, {snap.advancers} advancing / {snap.decliners} declining. "
                   f"({_freshness_phrase(snap)})")
    # per-symbol lookup: find a token that resolves to an observed security
    for tok in re.findall(r"[A-Za-z0-9]+", query or ""):
        o = snap.get(tok)
        if o is not None:
            hi = "high" in q or "range" in q
            if hi:
                return ans(f"{o.symbol} today (live observed): high {_s(o.high)}, low {_s(o.low)}, "
                           f"LTP {_s(o.ltp)}. ({_freshness_phrase(snap)})")
            return ans(f"{o.symbol} was observed at NPR {_s(o.ltp)} on the official NEPSE page "
                       f"({_freshness_phrase(snap)}).")
    return ans("I can report live-observed NEPSE index, turnover, breadth, market status, or a "
               "specific symbol's LTP/high/low — all with source and freshness.")


def voice_answer_live(snap: NepseLiveMarketSnapshot, query: str | None = None) -> str:
    """Phase 15 — same snapshot, spoken (Nepali/English blend)."""
    if query:
        for tok in re.findall(r"[A-Za-z0-9]+", query):
            o = snap.get(tok)
            if o is not None:
                return (f"Latest NEPSE observation ma {o.symbol} NPR {_s(o.ltp)} cha. "
                        f"Market {snap.market_status.value} cha.")
    status = "khulla" if snap.market_open else "banda"
    return (f"NEPSE index {_s(snap.nepse_index)} cha, market {status} ({snap.market_status.value}). "
            f"Turnover Rs {_s(snap.total_turnover)}. Observation {snap.freshness.value}.")


def catalyst_current_context(snap: NepseLiveMarketSnapshot, symbol: str) -> dict:
    """Phase 16 — CURRENT_MARKET_CONTEXT for a catalyst. Explicitly NOT historical
    market-reaction evidence (that still requires canonical historical data)."""
    o = snap.get(symbol)
    ctx = {
        "context_kind": "CURRENT_MARKET_CONTEXT", "data_class": snap.data_class,
        "is_historical_reaction": False,
        "note": "Live browser observation = current context only; historical reaction "
                "requires canonical historical data (md_bars).",
        "market_status": snap.market_status.value, "freshness": snap.freshness.value,
        "observed_at": snap.observed_at, "source_as_of": snap.source_as_of, "symbol": symbol,
    }
    if o is None:
        ctx["available"] = False
        return ctx
    ctx.update({"available": True, "ltp": _s(o.ltp), "day_high": _s(o.high), "day_low": _s(o.low),
                "volume": _s(o.volume), "turnover": _s(o.turnover),
                "point_change": _s(o.point_change), "percent_change": _s(o.percent_change),
                "symbol_resolution": o.symbol_resolution.value})
    return ctx


def trading_guardian_live_context(snap: NepseLiveMarketSnapshot) -> dict:
    """Phase 18 — read-only observational input for Trading Guardian. NOT execution
    authority; a browser observation can never become an order."""
    return {
        "kind": "LIVE_MARKET_OBSERVATION", "authority": "READ_ONLY_CONTEXT",
        "execution_authority": False, "data_class": snap.data_class,
        "market_status": snap.market_status.value, "freshness": snap.freshness.value,
        "nepse_index": _s(snap.nepse_index), "observed_at": snap.observed_at,
        "source": "Official NEPSE (nepalstock.com)",
        "note": "Observation only. Path to any action still requires canonical data + research "
                "+ portfolio + deterministic risk -> proposal -> Trading Guardian -> approval "
                "-> ExecutionGateway.",
    }
