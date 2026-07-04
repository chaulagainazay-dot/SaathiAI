"""Autonomous Content Factory tests — SaathiAI owns the intelligence, every step
records an Episode, nothing publishes without the gate + human approval."""
import pytest
from saathi.content_pipeline import ContentFactoryPipeline, ContentRun, Topic, Stage


def _pipe(episodes=None, events=None):
    return ContentFactoryPipeline(
        record_episode=lambda **kw: (episodes if episodes is not None else []).append(kw)
                                     or len(episodes if episodes is not None else [1]),
        publish_event=lambda n, p: (events if events is not None else []).append((n, p)),
        now=lambda: 1000.0)


def _complete_meta(pipe, run):
    pipe.build_metadata(run, title="5 IELTS Speaking Mistakes",
                        description="Mr. Yeti explains the five most common IELTS speaking mistakes.",
                        seo_tags=["ielts", "speaking"], thumbnail="t.png")


# ── discovery ranks by momentum × relevance − saturation ───────────────────
def test_rank_topics_orders_by_score():
    eps = []; pipe = _pipe(eps); run = ContentRun()
    ranked = pipe.rank_topics(run, [
        {"title": "Weak", "trend": 0.3, "relevance": 0.4, "competition": 0.8},
        {"title": "Strong", "trend": 0.9, "relevance": 0.9, "competition": 0.2},
    ])
    assert ranked[0].title == "Strong"
    assert eps and eps[0]["intent"] == "content_discover"


# ── research: sparse evidence → insufficient ───────────────────────────────
def test_research_confidence_and_evidence_gate():
    eps = []; pipe = _pipe(eps); run = ContentRun()
    strong = pipe.research_topic(run, Topic("T", "reddit", relevance=0.9, evidence=10))
    weak = pipe.research_topic(run, Topic("T2", "reddit", relevance=0.3, evidence=0))
    assert strong > weak
    assert eps[-1]["outcome"] == "insufficient_evidence"


# ── script validation blocks a missing CTA / too-short ─────────────────────
def test_validate_script():
    pipe = _pipe(); run = ContentRun()
    good = {"hook": "Ever freeze in IELTS speaking?", "teaching": ["Use fillers", "Structure answers", "Practice daily"],
            "examples": ["Well, that's an interesting question about my hometown, let me think"], "cta": "Follow Mr. Yeti"}
    assert pipe.validate_script(run, good) is True
    bad = {"hook": "Hi", "teaching": [], "examples": [], "cta": ""}
    assert pipe.validate_script(run, bad) is False
    assert any("missing cta" in i for i in run.script_issues)


# ── scene prompts generated for Flux ───────────────────────────────────────
def test_plan_scenes_makes_prompts():
    pipe = _pipe(); run = ContentRun()
    scenes = pipe.plan_scenes(run, {"hook": "Freeze in speaking?", "teaching": ["A", "B"], "cta": "Follow"})
    assert len(scenes) == 4
    assert all("Mr. Yeti" in s.image_prompt for s in scenes)


# ── the gate blocks incomplete metadata ────────────────────────────────────
def test_gate_blocks_incomplete_then_passes():
    pipe = _pipe(); run = ContentRun()
    pipe.build_metadata(run, title="", description="", seo_tags=[], thumbnail=None)
    assert pipe.gate(run) is False
    assert run.gate_blockers
    _complete_meta(pipe, run)
    assert pipe.gate(run) is True
    assert run.status == "awaiting_approval"


# ── publish requires gate pass AND human approval ──────────────────────────
def test_publish_requires_gate_and_approval():
    pipe = _pipe(); run = ContentRun()
    _complete_meta(pipe, run); pipe.gate(run)
    with pytest.raises(PermissionError):        # not approved yet
        pipe.publish(run, ["youtube"], publisher=lambda c, p: {"id": "v1"})
    pipe.approve(run, "ajay")
    results = pipe.publish(run, ["youtube", "tiktok"], publisher=lambda c, p: {"id": "v1", "url": "u"})
    assert all(r["ok"] for r in results)
    assert run.status == "published"


def test_cannot_approve_before_gate():
    pipe = _pipe(); run = ContentRun()
    with pytest.raises(ValueError):
        pipe.approve(run, "ajay")


# ── every stage recorded an Episode (the SaathiAI difference) ──────────────
def test_every_stage_records_episode():
    eps = []; events = []; pipe = _pipe(eps, events)
    run = ContentRun()
    t = pipe.rank_topics(run, [{"title": "IELTS", "trend": 0.9, "relevance": 0.9}])[0]
    pipe.research_topic(run, t)
    pipe.validate_script(run, {"hook": "x " * 20, "teaching": ["a " * 20], "examples": ["e"], "cta": "follow"})
    pipe.plan_scenes(run, {"hook": "h", "teaching": ["a"], "cta": "c"})
    _complete_meta(pipe, run); pipe.gate(run); pipe.approve(run, "ajay")
    pipe.publish(run, ["youtube"], publisher=lambda c, p: {"id": "v"})
    pipe.record_analytics(run, views=1000, ctr=0.12, watch_time_s=45, revenue_usd=8)
    intents = {e["intent"] for e in eps}
    for stage in ("discover", "research", "script", "assets", "gate", "publish", "analytics"):
        assert f"content_{stage}" in intents
    assert len(run.episodes) >= 7               # nothing happened without an Episode


# ── failure recovery records a failure Episode + actionable notification ───
def test_record_failure_emits_notification():
    eps = []; events = []; pipe = _pipe(eps, events)
    out = pipe.record_failure(Stage.RENDER, "renderer timeout", topic="IELTS")
    assert eps[-1]["outcome"] == "failure"
    assert out["notification"]["action"] == "Retry"
    assert events[-1][0] == "content.failed"
