"""AI Studio orchestrator — existing pipeline wired to the proven publisher."""
from saathi.content_pipeline import ContentFactoryPipeline
from saathi.ai_studio import AIStudio


def _pipeline(eps, events):
    return ContentFactoryPipeline(
        record_episode=lambda **kw: eps.append(kw) or len(eps),
        publish_event=lambda n, p: events.append((n, p)))


def _meta(topic):
    return {"title": f"Mr. Yeti: {topic}",
            "description": f"A friendly Mr. Yeti IELTS lesson about {topic} with examples.",
            "seo_tags": ["ielts", "mr yeti", topic],
            "script": {"hook": "Struggling?", "teaching": ["idea one", "idea two"],
                       "examples": "an example sentence here", "cta": "pielts.web.app"}}


def test_full_run_publishes_via_injected_publisher():
    eps, events, published = [], [], []
    studio = AIStudio(pipeline=_pipeline(eps, events), metadata_gen=_meta,
                      publisher=lambda **k: published.append((k["platform"], k["metadata"]["title"]))
                      or {"video_url": "https://youtu.be/x"})
    run = studio.run(topic="past perfect tense", video_path="/tmp/clip.mp4",
                     platforms=["youtube"], approver="Ajay", thumbnail="thumb.png")
    assert run.status == "published" and run.published[0]["ok"] is True
    assert published[0][0] == "youtube" and "past perfect" in published[0][1]
    intents = [e["intent"] for e in eps]
    assert "content_research" in intents and "content_script" in intents
    assert "content_gate" in intents and "content_publish" in intents


def test_without_approval_stops_at_gate():
    eps, events, published = [], [], []
    studio = AIStudio(pipeline=_pipeline(eps, events), metadata_gen=_meta,
                      publisher=lambda **k: published.append(k) or {})
    run = studio.run(topic="linking words", video_path="/x.mp4",
                     platforms=["youtube"], approver=None, thumbnail="t.png")
    assert run.status == "awaiting_approval" and run.published == []
    assert published == []                       # nothing published without approval


def test_bad_script_blocks_before_publish():
    eps, events, published = [], [], []
    studio = AIStudio(pipeline=_pipeline(eps, events),
                      metadata_gen=lambda t: {"title": "x", "description": "", "seo_tags": [],
                                              "script": {"hook": "", "teaching": [], "examples": "", "cta": ""}},
                      publisher=lambda **k: published.append(k) or {})
    run = studio.run(topic="x", video_path="/x.mp4", approver="Ajay")
    assert run.status in ("script_blocked", "gate_blocked") and published == []


def test_default_metadata_never_raises():
    from saathi.ai_studio import default_metadata
    m = default_metadata("conditionals")
    assert m["title"] and "script" in m and isinstance(m["seo_tags"], list)
