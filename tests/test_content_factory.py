"""Content Factory tests (M3 Phase B) — production line + Discovery gate, AP-12."""
from saathi.content_factory import ContentFactory, default_poster


def _content(ok=True):
    c = {"title": "5 IELTS Writing Mistakes", "description": "Mr Yeti explains the errors",
         "seo_tags": ["ielts"], "thumbnail": "t.png", "geo": {"@type": "VideoObject"}}
    if not ok:
        del c["thumbnail"]
    return c


def _factory(poster):
    episodes = []
    events = []
    f = ContentFactory(poster=poster,
                       record_episode=lambda **kw: episodes.append(kw) or len(episodes),
                       publish_event=lambda n, p: events.append(n))
    return f, episodes, events


def test_publishes_to_multiple_platforms_when_complete():
    posted = []
    f, episodes, _ = _factory(lambda c, p: posted.append(p) or {"id": f"post-{p}"})
    results = f.publish(_content(), platforms=["facebook", "twitter", "instagram"])
    assert all(r.published for r in results.values())
    assert set(posted) == {"facebook", "twitter", "instagram"}
    assert len([e for e in episodes if e["outcome"] == "success"]) == 3


def test_incomplete_content_blocked_on_every_platform():
    posted = []
    f, episodes, events = _factory(lambda c, p: posted.append(p) or {"id": "x"})
    results = f.publish(_content(ok=False), platforms=["facebook", "twitter"])
    assert not any(r.published for r in results.values())
    assert posted == []                       # Discovery gate blocked all
    assert "publish.blocked" in events


def test_default_poster_guards_unknown_platform():
    res = default_poster({"title": "x"}, "myspace")
    assert "error" in res and "no connector" in res["error"]


def test_analytics_feedback_recorded():
    f, episodes, _ = _factory(lambda c, p: {"id": "x"})
    f.record_analytics(product="mr_yeti", platform="youtube",
                       content_id="vid1", views=2000, likes=300)
    perf = [e for e in episodes if e["intent"] == "content_performance"]
    assert perf and perf[0]["metadata"]["views"] == 2000
