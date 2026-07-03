"""Business OS — real-world operations on the platform (M3 Business OS).

Every business activity becomes measurable, learnable, and improvable by flowing
through one interface — no business reimplements memory, learning, or revenue:

    business activity → Episode → Learning Runtime → Knowledge → Recommendations
                      → Revenue → CEO Dashboard

`record_activity` is the universal entry point (cafeteria, travel, subscriptions,
AI Studio, personal finance). The cafeteria helper shows the pattern: a day's
production → an Episode carrying a deterministic recommendation the Learning
Runtime can promote into standing knowledge.

The Enterprise KPI Engine lets every department declare its North Star + KPIs and
compare actuals against targets — the backbone of Executive Intelligence.

Testable in isolation (AP-12): episode recorder + revenue recorder injected.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from saathi.revenue import RevenueSource


def _noop_episode(**kw) -> int:
    return 0


def _noop_revenue(**kw) -> int:
    return 0


class BusinessOS:
    def __init__(self,
                 record_episode: Callable[..., int] | None = None,
                 record_revenue: Callable[..., int] | None = None):
        if record_episode is None:
            from saathi.integration import ingest_episode as record_episode
        if record_revenue is None:
            from saathi.revenue import record_revenue as record_revenue
        self._episode = record_episode
        self._revenue = record_revenue

    # ── universal entry point ─────────────────────────────────────────────
    def record_activity(self, *, department: str, product: str, activity: str,
                        metrics: dict, outcome: str = "success",
                        quality_score: float = 0.0, result: str = "",
                        revenue_usd: float = 0.0,
                        revenue_source: RevenueSource | None = None,
                        currency: str = "USD") -> int:
        """Any business activity → a platform Episode (and revenue if any)."""
        eid = self._episode(
            agent=f"{department}_ops", department=department, product=product,
            intent=activity, action=activity, result=result or str(metrics)[:200],
            outcome=outcome, quality_score=quality_score, metadata=metrics)
        if revenue_usd and revenue_source is not None:
            self._revenue(source=revenue_source, amount=revenue_usd,
                          currency=currency, product=product,
                          note=f"{department}:{activity}")
        return eid

    # ── HCG cafeteria (the daily business) ────────────────────────────────
    def record_cafeteria_day(self, *, item: str, produced: int, sold: int,
                             revenue_usd: float = 0.0, currency: str = "NPR") -> dict:
        """A day's production of one dish → Episode + a deterministic
        recommendation. Example: Dal Bhat produced 180, sold 171, waste 9 (5%)
        → 'reduce tomorrow by 6 portions'."""
        waste = max(0, produced - sold)
        waste_pct = round(waste / produced, 4) if produced else 0.0
        # Keep a safety buffer so we don't under-produce: cut ~2/3 of the waste.
        recommended_reduction = round(waste * 2 / 3)
        recommendation = (f"Reduce {item} tomorrow by {recommended_reduction} portions"
                          if recommended_reduction > 0 else f"Keep {item} production steady")
        metrics = {"item": item, "produced": produced, "sold": sold, "waste": waste,
                   "waste_pct": waste_pct, "recommended_reduction": recommended_reduction,
                   "recommendation": recommendation}
        eid = self.record_activity(
            department="HCG Cafeteria", product="hcg_pos",
            activity="daily_production", metrics=metrics,
            outcome="success" if waste_pct <= 0.1 else "partial",
            quality_score=round(sold / produced, 3) if produced else 0.0,
            result=recommendation, revenue_usd=revenue_usd,
            revenue_source=RevenueSource.POS, currency=currency)
        return {"episode_id": eid, **metrics}


# ── Enterprise KPI Engine ─────────────────────────────────────────────────
@dataclass
class KPI:
    name: str
    department: str
    target: float
    higher_is_better: bool
    cadence: str          # daily | weekly | monthly
    is_north_star: bool


@dataclass
class KPIComparison:
    name: str
    latest: float | None
    target: float
    on_track: bool
    vs_target_pct: float | None    # latest / target (or inverse for lower-is-better)


_KPI_SCHEMA = """
CREATE TABLE IF NOT EXISTS kpis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    department TEXT NOT NULL,
    target REAL NOT NULL,
    higher_is_better INTEGER DEFAULT 1,
    cadence TEXT DEFAULT 'daily',
    is_north_star INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS kpi_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    recorded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kpi_name ON kpi_values(name);
"""


class KPIEngine:
    def __init__(self, db_path: "str | Path", now: Callable[[], float] = time.time):
        Path(str(db_path)).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_KPI_SCHEMA)
        self.db.commit()
        self._now = now

    def define_kpi(self, *, name: str, department: str, target: float,
                   higher_is_better: bool = True, cadence: str = "daily",
                   is_north_star: bool = False) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO kpis (name, department, target, higher_is_better,"
            " cadence, is_north_star) VALUES (?,?,?,?,?,?)",
            (name, department, target, int(higher_is_better), cadence, int(is_north_star)))
        self.db.commit()

    def record_value(self, name: str, value: float) -> None:
        self.db.execute("INSERT INTO kpi_values (name, value, recorded_at) VALUES (?,?,?)",
                        (name, value, self._now()))
        self.db.commit()

    def latest(self, name: str) -> float | None:
        r = self.db.execute("SELECT value FROM kpi_values WHERE name=? ORDER BY id DESC LIMIT 1",
                            (name,)).fetchone()
        return r["value"] if r else None

    def compare(self, name: str) -> KPIComparison:
        k = self.db.execute("SELECT * FROM kpis WHERE name=?", (name,)).fetchone()
        if k is None:
            raise KeyError(name)
        latest = self.latest(name)
        hib = bool(k["higher_is_better"])
        if latest is None:
            return KPIComparison(name, None, k["target"], False, None)
        on_track = latest >= k["target"] if hib else latest <= k["target"]
        vs = round((latest / k["target"]) if hib else (k["target"] / latest), 3) if k["target"] else None
        return KPIComparison(name, latest, k["target"], on_track, vs)

    def north_stars(self) -> list[KPIComparison]:
        rows = self.db.execute("SELECT name FROM kpis WHERE is_north_star=1").fetchall()
        return [self.compare(r["name"]) for r in rows]
