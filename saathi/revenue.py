"""Revenue Engine — revenue as a first-class platform capability (M3 Phase B/#3).

Every income stream reports through one interface so the Dream Meter becomes a
live business metric instead of a placeholder. Persistent, event-first, and
wired to the CEO Dashboard.

    YouTube / Telegram / Travel / POS / Subscriptions / Crypto / Affiliate /
    Courses / Ads / Sponsors / Consulting  →  record_revenue()  →  Dream Meter

Testable in isolation (AP-12): SQLite at any path, injected clock/publisher.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class RevenueSource(str, Enum):
    YOUTUBE = "youtube"
    TELEGRAM = "telegram"
    TRAVEL = "travel"
    POS = "pos"                     # hospital cafeteria
    SUBSCRIPTIONS = "subscriptions"
    CRYPTO = "crypto"
    AFFILIATE = "affiliate"
    COURSES = "courses"
    ADS = "ads"
    SPONSORS = "sponsors"
    CONSULTING = "consulting"
    OTHER = "other"


@dataclass
class RevenueEntry:
    entry_id: int
    source: RevenueSource
    amount: float                  # in the reporting currency
    currency: str
    product: str | None
    note: str
    recorded_at: float


_SCHEMA = """
CREATE TABLE IF NOT EXISTS revenue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    product TEXT,
    note TEXT DEFAULT '',
    recorded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rev_source ON revenue(source);
CREATE INDEX IF NOT EXISTS idx_rev_time ON revenue(recorded_at);
"""

# Simple FX to a common base (USD) so the Dream Meter can sum mixed currencies.
# Approximate, configurable; a real feed can replace this later.
_FX_TO_USD = {"USD": 1.0, "NPR": 0.0075, "INR": 0.012, "EUR": 1.08, "GBP": 1.27}


def to_usd(amount: float, currency: str) -> float:
    return amount * _FX_TO_USD.get(currency.upper(), 1.0)


class RevenueEngine:
    def __init__(self, db_path: "str | Path",
                 publish: "Callable[[str, dict], None] | None" = None,
                 now: Callable[[], float] = time.time):
        Path(str(db_path)).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()
        self._publish_fn = publish
        self._now = now

    def record_revenue(self, *, source: RevenueSource, amount: float,
                       currency: str = "USD", product: str | None = None,
                       note: str = "") -> int:
        cur = self.db.execute(
            "INSERT INTO revenue (source, amount, currency, product, note, recorded_at)"
            " VALUES (?,?,?,?,?,?)",
            (source.value, amount, currency, product, note, self._now()))
        self.db.commit()
        eid = cur.lastrowid
        usd = to_usd(amount, currency)
        if self._publish_fn is not None:
            self._publish_fn("revenue.recorded",
                             {"source": source.value, "amount": amount,
                              "currency": currency, "usd": usd})
        return eid

    def total_usd(self, since: float | None = None) -> float:
        q, params = "SELECT source, amount, currency FROM revenue", []
        if since is not None:
            q += " WHERE recorded_at >= ?"; params.append(since)
        return round(sum(to_usd(r["amount"], r["currency"])
                         for r in self.db.execute(q, params).fetchall()), 2)

    def by_source(self, since: float | None = None) -> dict[str, float]:
        q, params = "SELECT source, amount, currency FROM revenue", []
        if since is not None:
            q += " WHERE recorded_at >= ?"; params.append(since)
        out: dict[str, float] = {}
        for r in self.db.execute(q, params).fetchall():
            out[r["source"]] = round(out.get(r["source"], 0.0)
                                     + to_usd(r["amount"], r["currency"]), 2)
        return out

    def today_usd(self) -> float:
        start = self._now() - 86400
        return self.total_usd(since=start)


# ── process-wide engine + CEO-dashboard bridge ────────────────────────────
_engine: RevenueEngine | None = None


def get_revenue_engine() -> RevenueEngine:
    global _engine
    if _engine is None:
        from saathi import config
        from saathi.events import bus
        _engine = RevenueEngine(str(config.ROOT / "data" / "revenue.db"),
                                publish=bus.publish_sync)
    return _engine


def record_revenue(*, source: RevenueSource, amount: float, currency: str = "USD",
                   product: str | None = None, note: str = "") -> int:
    """The unified revenue interface every income stream calls. Lights up the
    Dream Meter on the CEO Dashboard."""
    eid = get_revenue_engine().record_revenue(
        source=source, amount=amount, currency=currency, product=product, note=note)
    try:
        from saathi.ceo_dashboard import get_dashboard
        get_dashboard().record_revenue(to_usd(amount, currency))
    except Exception:
        pass
    return eid
