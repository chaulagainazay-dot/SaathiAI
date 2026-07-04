"""Content Intelligence (M6) — the Analytics → Learning loop for AI Studio.

Turns the Content Factory from a pipeline into a self-improving business unit.
Every published video's real analytics flow in, get normalized to one schema,
and are mined into *verified knowledge* about what actually works — which hook,
length, thumbnail, publish time, and CTA move CTR / retention / RPM. That
knowledge feeds the same M2 learning architecture (Episodes → proposals →
promotion) and answers, for the CEO: "why did this succeed, and what do we repeat?"

n8n stays thin: it POSTs raw platform analytics; SaathiAI does all the math.
Every ingestion records an Episode. Deterministic (AP-17); db/clock/recorder
injected (AP-12).
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable

DREAM_TARGET = 7_938_838.98


# ── one normalized schema every platform maps into ─────────────────────────
@dataclass
class ContentAnalytics:
    video_id: str
    platform: str
    topic: str = ""
    hook_style: str = "unknown"        # curiosity / question / bold / story
    thumbnail_style: str = "unknown"   # blue / orange / face / text
    cta_style: str = "unknown"         # subscribe / follow / comment / link
    length_s: float = 0.0
    publish_hour: int = 12             # 0..23 local
    views: int = 0
    impressions: int = 0
    ctr: float = 0.0                   # 0..1
    watch_time_s: float = 0.0
    avg_view_duration_s: float = 0.0
    retention: float = 0.0             # 0..1
    likes: int = 0
    comments: int = 0
    shares: int = 0
    subscribers: int = 0
    rpm: float = 0.0
    revenue_usd: float = 0.0
    publish_ts: float = 0.0

    @property
    def performance(self) -> float:
        """Composite quality: CTR × retention, lifted by monetization."""
        return round(self.ctr * self.retention * (1 + self.rpm / 20.0), 4)


# platform → normalizer. n8n posts the raw platform payload; we map it here.
def _y(raw, *keys, d=0):
    for k in keys:
        if k in raw and raw[k] is not None:
            return raw[k]
    return d


def normalize(platform: str, raw: dict) -> ContentAnalytics:
    p = platform.lower()
    views = _y(raw, "views", "video_views", "plays", "impressions_unique")
    impressions = _y(raw, "impressions", "reach", d=views)
    ctr = _y(raw, "ctr", "click_through_rate")
    if not ctr and impressions:
        ctr = round(views / impressions, 4) if p == "youtube" else ctr
    return ContentAnalytics(
        video_id=str(_y(raw, "video_id", "id", "media_id", d="")),
        platform=p, topic=_y(raw, "topic", d=""),
        hook_style=_y(raw, "hook_style", "hook", d="unknown"),
        thumbnail_style=_y(raw, "thumbnail_style", "thumbnail", d="unknown"),
        cta_style=_y(raw, "cta_style", "cta", d="unknown"),
        length_s=float(_y(raw, "length_s", "duration", "video_length")),
        publish_hour=int(_y(raw, "publish_hour", d=12)),
        views=int(views), impressions=int(impressions), ctr=float(ctr),
        watch_time_s=float(_y(raw, "watch_time_s", "total_watch_time", "minutes_viewed")),
        avg_view_duration_s=float(_y(raw, "avg_view_duration_s", "average_view_duration")),
        retention=float(_y(raw, "retention", "average_percentage_viewed", "avg_watch_pct")),
        likes=int(_y(raw, "likes", "reactions")), comments=int(_y(raw, "comments")),
        shares=int(_y(raw, "shares")), subscribers=int(_y(raw, "subscribers", "subscribers_gained", "follows")),
        rpm=float(_y(raw, "rpm")), revenue_usd=float(_y(raw, "revenue_usd", "estimated_revenue", "revenue")),
        publish_ts=float(_y(raw, "publish_ts", d=time.time())))


def length_bucket(s: float) -> str:
    m = s / 60.0
    return "<4m" if m < 4 else "4-6m" if m < 6 else "6-8m" if m < 8 else "8m+"


def hour_bucket(h: int) -> str:
    return "morning" if 6 <= h < 12 else "afternoon" if 12 <= h < 17 else "evening" if 17 <= h < 22 else "night"


# dimension → (value extractor, metric attribute)
DIMENSIONS = [
    ("hook", lambda a: a.hook_style, "ctr"),
    ("length", lambda a: length_bucket(a.length_s), "retention"),
    ("thumbnail", lambda a: a.thumbnail_style, "ctr"),
    ("publishing", lambda a: hour_bucket(a.publish_hour), "watch_time_s"),
    ("cta", lambda a: a.cta_style, "subscribers"),
]


@dataclass
class Knowledge:
    dimension: str
    value: str
    metric: str
    lift: float           # vs channel average, e.g. +0.14 = +14%
    sample_count: int
    verified: bool

    def render(self) -> str:
        sign = "+" if self.lift >= 0 else ""
        return (f"{self.dimension}: {self.value} → {sign}{self.lift:.0%} {self.metric} "
                f"({'verified' if self.verified else 'candidate'}, {self.sample_count} videos)")


class ContentIntelligence:
    def __init__(self, db_path: "str | Path", *, improvement_registry=None,
                 verify_threshold: int = 10, min_lift: float = 0.05,
                 now: Callable[[], float] = time.time,
                 publish: Callable[[str, dict], object] | None = None,
                 record_episode: Callable[..., int] | None = None):
        self.path = str(db_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS content_analytics (
                video_id TEXT PRIMARY KEY, platform TEXT, performance REAL,
                ctr REAL, retention REAL, rpm REAL, revenue_usd REAL, publish_ts REAL,
                payload TEXT);
            CREATE TABLE IF NOT EXISTS content_knowledge (
                key TEXT PRIMARY KEY, dimension TEXT, value TEXT, metric TEXT,
                lift REAL, sample_count INTEGER, verified INTEGER, updated_at REAL);
        """)
        self.db.commit()
        self.improvements = improvement_registry
        self.verify_threshold = verify_threshold
        self.min_lift = min_lift
        self.now = now
        if publish is None:
            from saathi.events import bus
            publish = bus.publish_sync
        if record_episode is None:
            from saathi.integration import ingest_episode as record_episode
        self._publish = publish
        self._episode = record_episode

    # ── ingest one video's analytics → store, learn, dream ─────────────────
    def ingest(self, a: ContentAnalytics) -> dict:
        self.db.execute(
            "INSERT INTO content_analytics (video_id,platform,performance,ctr,retention,rpm,"
            "revenue_usd,publish_ts,payload) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(video_id) DO UPDATE SET platform=excluded.platform,performance=excluded.performance,"
            "ctr=excluded.ctr,retention=excluded.retention,rpm=excluded.rpm,revenue_usd=excluded.revenue_usd,"
            "publish_ts=excluded.publish_ts,payload=excluded.payload",
            (a.video_id, a.platform, a.performance, a.ctr, a.retention, a.rpm,
             a.revenue_usd, a.publish_ts, json.dumps(asdict(a))))
        self.db.commit()
        self._relearn()
        dream_pct = round(a.revenue_usd / DREAM_TARGET * 100, 6)
        self._episode(
            agent="content_intelligence", department="ai_studio", product="mr_yeti",
            intent="content_analytics",
            action=f"analytics for {a.video_id} ({a.platform})",
            result=f"CTR {a.ctr:.1%} · retention {a.retention:.0%} · ${a.revenue_usd:.0f}",
            outcome="success", quality_score=round(min(1.0, a.performance), 3),
            metadata={"video_id": a.video_id, "dream_pct": dream_pct})
        self._publish("content.analytics", {"video_id": a.video_id, "performance": a.performance,
                                             "revenue_usd": a.revenue_usd})
        return {"performance": a.performance, "dream_contribution_pct": dream_pct}

    # ── recompute cohort knowledge from all rows (small-data, exact) ───────
    def _rows(self):
        return [json.loads(r["payload"]) for r in
                self.db.execute("SELECT payload FROM content_analytics").fetchall()]

    def _relearn(self):
        rows = self._rows()
        if not rows:
            return
        for dim, extract, metric in DIMENSIONS:
            overall = _mean([r[metric] for r in rows])
            if overall <= 1e-6:        # no signal for this metric yet — don't invent lift
                continue
            cohorts: dict[str, list[float]] = {}
            for r in rows:
                a = _as_obj(r)
                cohorts.setdefault(extract(a), []).append(r[metric])
            for value, vals in cohorts.items():
                if value in ("", "unknown"):
                    continue
                lift = round(_mean(vals) / overall - 1.0, 4)
                n = len(vals)
                verified = n >= self.verify_threshold and abs(lift) >= self.min_lift
                self.db.execute(
                    "INSERT INTO content_knowledge (key,dimension,value,metric,lift,sample_count,verified,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET lift=excluded.lift,"
                    "sample_count=excluded.sample_count,verified=excluded.verified,updated_at=excluded.updated_at",
                    (f"{dim}|{value}", dim, value, metric, lift, n, int(verified), self.now()))
                # promote strong verified knowledge into the M2 improvement pipeline
                if verified and lift >= self.min_lift and self.improvements is not None:
                    self.improvements.propose(
                        capability="Autonomous Content Factory",
                        improvement=f"Prefer {dim}={value} (+{lift:.0%} {metric})",
                        evidence=f"{n} videos", expected_benefit=f"+{lift:.0%} {metric}",
                        confidence=round(min(0.99, 0.6 + n / (n + 20) * 0.4), 2))
        self.db.commit()

    def knowledge(self, verified_only: bool = False) -> list[Knowledge]:
        q = "SELECT * FROM content_knowledge"
        if verified_only:
            q += " WHERE verified=1"
        q += " ORDER BY ABS(lift) DESC"
        return [Knowledge(r["dimension"], r["value"], r["metric"], r["lift"],
                          r["sample_count"], bool(r["verified"]))
                for r in self.db.execute(q).fetchall()]

    def recommendations(self, top: int = 5) -> list[str]:
        return [k.render() for k in self.knowledge(verified_only=True)[:top]]

    def leaderboard(self, top: int = 5) -> list[dict]:
        rows = self.db.execute(
            "SELECT video_id,platform,performance,ctr,retention,revenue_usd "
            "FROM content_analytics ORDER BY performance DESC LIMIT ?", (top,)).fetchall()
        return [dict(r) for r in rows]

    def experiments(self) -> list[dict]:
        """Verified knowledge already decided; surface near-ties worth A/B testing."""
        out = []
        by_dim: dict[str, list[Knowledge]] = {}
        for k in self.knowledge():
            by_dim.setdefault(k.dimension, []).append(k)
        for dim, ks in by_dim.items():
            ks = sorted(ks, key=lambda k: k.lift, reverse=True)
            if len(ks) >= 2 and abs(ks[0].lift - ks[1].lift) < 0.05:
                out.append({"dimension": dim, "a": ks[0].value, "b": ks[1].value,
                            "note": "near-tie — worth an A/B test"})
        return out

    # ── comparative analysis: why did A beat B? ────────────────────────────
    def compare(self, id_a: str, id_b: str) -> dict:
        a, b = self._get(id_a), self._get(id_b)
        if not a or not b:
            raise KeyError("both videos must have analytics")
        diffs = {}
        for f in ("hook_style", "thumbnail_style", "cta_style", "length_s", "publish_hour", "topic"):
            if a[f] != b[f]:
                diffs[f] = {"a": a[f], "b": b[f]}
        winners = {m: (id_a if a[m] >= b[m] else id_b) for m in ("ctr", "retention", "rpm", "revenue_usd")}
        overall = id_a if a["performance"] >= b["performance"] else id_b
        self._episode(
            agent="content_intelligence", department="ai_studio", product="mr_yeti",
            intent="content_compare", action=f"compared {id_a} vs {id_b}",
            result=f"{overall} won on performance", outcome="success",
            quality_score=1.0, metadata={"diffs": diffs, "winners": winners})
        return {"winner": overall, "differences": diffs, "metric_winners": winners}

    # ── the Executive line: why + what to repeat ───────────────────────────
    def content_briefing(self) -> str:
        v = self.knowledge(verified_only=True)
        if not v:
            return "Not enough data yet to recommend a repeatable format."
        top = v[:3]
        parts = ", ".join(f"{k.value} ({'+' if k.lift>=0 else ''}{k.lift:.0%} {k.metric})" for k in top)
        return f"Repeat this format: {parts} — verified across recent videos. Recommend duplicating."

    # helpers
    def _get(self, vid):
        r = self.db.execute("SELECT payload,performance FROM content_analytics WHERE video_id=?", (vid,)).fetchone()
        if not r:
            return None
        d = json.loads(r["payload"]); d["performance"] = r["performance"]; return d


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def _as_obj(d: dict) -> ContentAnalytics:
    return ContentAnalytics(**{k: v for k, v in d.items() if k in ContentAnalytics.__dataclass_fields__})
