"""Audience Intelligence tests (M3 Phase B/#2) — AP-12.

Proves a video's audience data becomes a structured, learnable Episode, and
that comparable videos share an intent so the Promotion Engine can cluster them
into knowledge like "6-8min whiteboard videos retain better".
"""
from saathi.audience import AudienceIntelligence, VideoInsight


def _ai():
    episodes = []
    ai = AudienceIntelligence(record_episode=lambda **kw: episodes.append(kw) or len(episodes))
    return ai, episodes


def test_insight_becomes_rich_episode():
    ai, episodes = _ai()
    ai.record_video_insight(VideoInsight(
        video_id="vid1", title="5 IELTS Writing Mistakes", topic="ielts writing",
        duration_s=420, thumbnail_style="whiteboard", watch_time_pct=0.63, ctr=0.08,
        views=5000, subscribers_gained=42, revenue_usd=12.5,
        country_breakdown={"NP": 0.4, "IN": 0.3}, top_search_terms=["ielts writing tips"]))
    e = episodes[0]
    assert e["product"] == "mr_yeti"
    assert e["metadata"]["duration_bucket"] == "6-8min"
    assert e["metadata"]["thumbnail_style"] == "whiteboard"
    assert e["metadata"]["watch_time_pct"] == 0.63
    assert e["metadata"]["subscribers_gained"] == 42
    assert e["outcome"] == "success"          # watch time >= 40%


def test_low_watch_time_is_partial():
    ai, episodes = _ai()
    ai.record_video_insight(VideoInsight(video_id="v2", duration_s=600,
                                         watch_time_pct=0.2, ctr=0.02))
    assert episodes[0]["outcome"] == "partial"


def test_comparable_videos_share_intent_for_clustering():
    ai, episodes = _ai()
    for i in range(3):
        ai.record_video_insight(VideoInsight(
            video_id=f"v{i}", duration_s=420, thumbnail_style="whiteboard",
            watch_time_pct=0.6, ctr=0.07))
    intents = {e["intent"] for e in episodes}
    assert intents == {"video_6-8min_whiteboard"}   # cluster-ready for the Promotion Engine


def test_quality_blends_watch_time_and_ctr():
    ai, episodes = _ai()
    ai.record_video_insight(VideoInsight(video_id="v", duration_s=300,
                                         watch_time_pct=1.0, ctr=0.1))
    # 0.6*1.0 + 0.4*min(1.0, 0.1*10)=0.4*1.0 => 1.0
    assert episodes[0]["quality_score"] == 1.0
