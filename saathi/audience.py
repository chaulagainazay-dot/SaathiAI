"""Audience Intelligence (M3 Phase B/#2) — every video generates reusable knowledge.

Instead of "how many views?", it asks who watches, where they stop, which titles
and thumbnails work, which topics convert, which videos produce subscribers and
revenue — and stores it all as structured platform Episodes so the Learning
Runtime can promote patterns like:

    "Educational videos 6-8 minutes featuring Mr. Yeti with whiteboard scenes
     increase watch time by 23%."

That becomes platform knowledge every future video benefits from.

Testable in isolation (AP-12): the episode recorder is injected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class VideoInsight:
    video_id: str
    product: str = "mr_yeti"
    platform: str = "youtube"
    title: str = ""
    topic: str = ""
    duration_s: int = 0
    thumbnail_style: str = ""
    watch_time_pct: float = 0.0          # avg % of video watched (0..1)
    drop_off_point_pct: float | None = None   # where most viewers stop (0..1)
    ctr: float = 0.0                     # click-through rate on impressions
    views: int = 0
    subscribers_gained: int = 0
    revenue_usd: float = 0.0
    country_breakdown: dict = field(default_factory=dict)
    top_search_terms: list = field(default_factory=list)


def _duration_bucket(seconds: int) -> str:
    m = seconds / 60
    if m < 1: return "<1min"
    if m < 3: return "1-3min"
    if m < 6: return "3-6min"
    if m < 8: return "6-8min"
    if m < 12: return "8-12min"
    return "12min+"


def _noop(**kw) -> int:
    return 0


class AudienceIntelligence:
    """Turns raw performance into structured, learnable audience knowledge."""

    def __init__(self, record_episode: Callable[..., int] = _noop):
        self._record = record_episode

    def record_video_insight(self, insight: VideoInsight) -> int:
        """One video's audience data → a platform Episode. quality_score blends
        watch time + CTR so the Promotion Engine surfaces what actually works."""
        quality = round(0.6 * insight.watch_time_pct + 0.4 * min(1.0, insight.ctr * 10), 3)
        # The intent groups comparable content so the Promotion Engine can cluster
        # (e.g. all "6-8min whiteboard" videos) and extract a pattern.
        intent = f"video_{_duration_bucket(insight.duration_s)}_{insight.thumbnail_style or 'plain'}"
        return self._record(
            agent="audience_intelligence", department="Discovery",
            product=insight.product, intent=intent,
            action=insight.title[:200],
            result=(f"watch {insight.watch_time_pct:.0%}, CTR {insight.ctr:.1%}, "
                    f"+{insight.subscribers_gained} subs, ${insight.revenue_usd:.2f}"),
            outcome="success" if insight.watch_time_pct >= 0.4 else "partial",
            quality_score=quality,
            metadata={
                "video_id": insight.video_id, "platform": insight.platform,
                "topic": insight.topic, "duration_bucket": _duration_bucket(insight.duration_s),
                "duration_s": insight.duration_s, "thumbnail_style": insight.thumbnail_style,
                "watch_time_pct": insight.watch_time_pct,
                "drop_off_point_pct": insight.drop_off_point_pct, "ctr": insight.ctr,
                "views": insight.views, "subscribers_gained": insight.subscribers_gained,
                "revenue_usd": insight.revenue_usd,
                "country_breakdown": insight.country_breakdown,
                "top_search_terms": insight.top_search_terms,
            })


def get_audience_intelligence() -> AudienceIntelligence:
    """Production instance wired to the shared Learning Runtime."""
    from saathi.integration import ingest_episode
    return AudienceIntelligence(record_episode=ingest_episode)
