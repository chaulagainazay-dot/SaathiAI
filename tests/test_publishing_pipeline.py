"""Publishing Pipeline tests (M3 Sprint #2) — nothing publishes without Discovery, AP-12.

Injected publisher + episode recorder; no network, no real posting. Verifies the
Discovery gate blocks incomplete content, complete content publishes and is
recorded for learning, and analytics feedback closes the loop.
"""
from saathi.publishing_pipeline import (
    PublishingPipeline, default_discovery_checks, PrePublishReport,
)


def _complete_content():
    return {
        "title": "5 IELTS Writing Mistakes to Avoid",
        "description": "Mr. Yeti explains the five most common IELTS Task 2 errors.",
        "seo_tags": ["ielts", "writing", "task 2"],
        "thumbnail": "thumb.png",
        "geo": {"@type": "VideoObject"},
    }


# ── Discovery gate ─────────────────────────────────────────────────────────
def test_gate_passes_complete_content():
    report = default_discovery_checks(_complete_content())
    assert report.passed
    assert report.blocking_failures == []


def test_gate_blocks_missing_seo_and_thumbnail():
    content = _complete_content()
    del content["seo_tags"]
    del content["thumbnail"]
    report = default_discovery_checks(content)
    assert not report.passed
    names = {c.name for c in report.blocking_failures}
    assert "seo_tags" in names and "thumbnail" in names


def test_geo_is_recommended_not_blocking():
    content = _complete_content()
    del content["geo"]
    report = default_discovery_checks(content)
    assert report.passed                       # GEO missing → warn, don't block
    geo_check = next(c for c in report.checks if c.name == "geo_metadata")
    assert geo_check.passed is False and geo_check.blocking is False


# ── pipeline: nothing publishes without passing Discovery ─────────────────
def test_incomplete_content_is_blocked_and_recorded():
    published = []
    episodes = []
    events = []

    def publisher(content, platform):
        published.append(platform)          # should NOT be called
        return {"ok": True}

    def recorder(**kw):
        episodes.append(kw)
        return len(episodes)

    pipe = PublishingPipeline(publisher=publisher, record_episode=recorder,
                              publish_event=lambda n, p: events.append(n))
    content = _complete_content()
    del content["seo_tags"]
    res = pipe.publish(content, platform="youtube")

    assert res.published is False
    assert published == []                   # never reached the publisher
    assert episodes[0]["outcome"] == "failure"    # block recorded for learning
    assert "publish.blocked" in events


def test_complete_content_publishes_and_records_for_learning():
    episodes = []

    def publisher(content, platform):
        return {"id": "vid123", "url": "https://youtu.be/vid123"}

    def recorder(**kw):
        episodes.append(kw)
        return len(episodes)

    events = []
    pipe = PublishingPipeline(publisher=publisher, record_episode=recorder,
                              publish_event=lambda n, p: events.append(n))
    res = pipe.publish(_complete_content(), platform="youtube", product="mr_yeti")

    assert res.published is True
    assert res.raw["id"] == "vid123"
    assert episodes[0]["outcome"] == "success"
    assert episodes[0]["product"] == "mr_yeti"
    assert episodes[0]["metadata"]["seo_tags"]      # SEO captured on the episode
    assert "publish.completed" in events


def test_publisher_error_recorded_as_failure():
    def publisher(content, platform):
        return {"error": "rate_limited"}
    episodes = []
    pipe = PublishingPipeline(publisher=publisher,
                              record_episode=lambda **kw: episodes.append(kw) or 1)
    res = pipe.publish(_complete_content(), platform="tiktok")
    assert res.published is False
    assert episodes[0]["outcome"] == "failure"


# ── analytics feedback closes the loop ────────────────────────────────────
def test_performance_feedback_becomes_episode():
    episodes = []
    pipe = PublishingPipeline(publisher=lambda c, p: {},
                              record_episode=lambda **kw: episodes.append(kw) or 1)
    pipe.record_performance(product="mr_yeti", platform="youtube",
                            content_id="vid123", views=1000, likes=200)
    rec = episodes[0]
    assert rec["intent"] == "content_performance"
    assert rec["metadata"]["engagement_rate"] == 0.2
    assert rec["quality_score"] == 1.0          # 0.2 * 10 capped at 1.0
