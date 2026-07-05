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
            "script": {"hook": f"Struggling with {topic} in your IELTS speaking test?",
                       "teaching": ["The present perfect links a past action to the present moment "
                                    "using has or have plus the past participle of the verb.",
                                    "Use it for life experiences and changes that still matter now."],
                       "examples": "I have visited London twice this year already.",
                       "cta": "Practice free on pielts.web.app today"}}


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


# ── operating modes + instrumentation ────────────────────────────────────────
def test_autonomous_mode_auto_publishes_above_threshold():
    from saathi.ai_studio import AIStudio, Mode
    eps, events, published = [], [], []
    studio = AIStudio(pipeline=_pipeline(eps, events), metadata_gen=_meta,
                      publisher=lambda **k: published.append(k) or {"video_url": "https://youtu.be/x"})
    run = studio.run(topic="modal verbs", video_path="/x.mp4", mode=Mode.AUTONOMOUS,
                     approver=None, confidence_threshold=0.4, thumbnail="t.png")
    assert run.status == "published"                 # no human approver needed — confidence gated
    assert run.overall_confidence >= 0.4 and run.cost_total > 0
    assert run.video_url == "https://youtu.be/x"
    assert {s.stage for s in run.stages} >= {"research", "script", "gate", "publish"}
    assert all(isinstance(s.duration_ms, int) for s in run.stages)   # time tracking


def test_autonomous_low_confidence_pauses():
    from saathi.ai_studio import AIStudio, Mode
    studio = AIStudio(pipeline=_pipeline([], []), metadata_gen=_meta,
                      publisher=lambda **k: {"video_url": "u"})
    run = studio.run(topic="x", video_path="/x.mp4", mode=Mode.AUTONOMOUS,
                     approver=None, confidence_threshold=0.99, thumbnail="t.png")
    assert run.status == "awaiting_approval"         # confidence below threshold → pause


def test_structured_failure_on_gate_block():
    from saathi.ai_studio import AIStudio
    studio = AIStudio(pipeline=_pipeline([], []),
                      metadata_gen=lambda t: {"title": "Mr Yeti short", "description": "too short",
                                              "seo_tags": ["ielts"],
                                              "script": _meta(t)["script"]},
                      publisher=lambda **k: {})
    run = studio.run(topic="x", video_path="/x.mp4", approver="Ajay", thumbnail="t.png")
    assert run.status == "gate_blocked"
    assert run.failure and run.failure["stage"] == "gate" and run.failure["recommendation"]


def test_studio_store_queue_counts(tmp_path):
    from saathi.ai_studio import AIStudio, Mode
    from saathi.studio_store import StudioStore
    store = StudioStore(db_path=str(tmp_path / "s.db"))
    studio = AIStudio(pipeline=_pipeline([], []), metadata_gen=_meta,
                      publisher=lambda **k: {"video_url": "u"}, store=store)
    studio.run(topic="a", video_path="/x", mode=Mode.AUTONOMOUS, confidence_threshold=0.4, thumbnail="t")
    studio.run(topic="b", video_path="/x", mode=Mode.ASSISTED, approver=None, thumbnail="t")
    counts = store.queue_counts()
    assert counts["published"] >= 1 and counts["awaiting_approval"] >= 1
    assert len(store.recent()) == 2


def test_factory_kpis_today(tmp_path):
    from saathi.ai_studio import AIStudio, Mode
    from saathi.studio_store import StudioStore
    store = StudioStore(db_path=str(tmp_path / "s.db"))
    studio = AIStudio(pipeline=_pipeline([], []), metadata_gen=_meta,
                      publisher=lambda **k: {"video_url": "u"}, store=store)
    studio.run(topic="a", video_path="/x", mode=Mode.AUTONOMOUS, confidence_threshold=0.4, thumbnail="t")
    studio.run(topic="b", video_path="/x", mode=Mode.ASSISTED, approver=None, thumbnail="t")
    k = store.factory_kpis()
    assert k["runs"] == 2 and k["published"] >= 1 and k["waiting_approval"] >= 1
    assert 0 <= k["avg_confidence"] <= 1 and k["avg_cost"] >= 0 and k["avg_runtime_ms"] >= 0


# ── Run Manager + full generation chain ──────────────────────────────────────
def test_workspace_run_writes_artifacts_and_stage_flags(tmp_path):
    from saathi.ai_studio import AIStudio
    from saathi.run_manager import RunManager
    rm = RunManager(root=tmp_path / "runs")
    # force the honest no-provider path so the test is host-independent
    studio = AIStudio(pipeline=_pipeline([], []), metadata_gen=_meta,
                      publisher=lambda **k: {"video_url": "https://youtu.be/x"},
                      run_manager=rm, store=None,
                      voice_gen=lambda **k: None, image_gen=lambda **k: None)
    # fallback clip lets render's hard gate pass while voice/assets are unwired
    clip = tmp_path / "clip.mp4"; clip.write_bytes(b"\x00" * 32)
    run = studio.run(topic="past perfect", video_path=str(clip), approver="Ajay",
                     thumbnail=str(clip), generate=True, run_prefix="PAT")
    assert run.status == "published" and run.run_id.startswith("PAT-")
    # artifacts landed in the owned workspace
    wr = rm.get(run.run_id)
    for art in ("research.md", "script.md", "metadata.json", "video.mp4", "publish.json", "run.json"):
        assert wr.verify(art) or art == "run.json", f"missing {art}"
    flags = run.stage_flags
    assert flags["research"] and flags["script"] and flags["render"] and flags["publish"]
    assert flags["voice"] is False and flags["assets"] is False   # honest: no provider yet


def test_generate_render_fails_without_clip_or_renderer(tmp_path):
    from saathi.ai_studio import AIStudio
    from saathi.run_manager import RunManager
    rm = RunManager(root=tmp_path / "runs")
    # null renderer + no clip → render's hard gate must fail honestly
    studio = AIStudio(pipeline=_pipeline([], []), metadata_gen=_meta,
                      publisher=lambda **k: {"video_url": "u"}, run_manager=rm, store=None,
                      voice_gen=lambda **k: None, image_gen=lambda **k: None,
                      renderer=lambda **k: None)
    run = studio.run(topic="x", video_path=None, approver="Ajay", generate=True, run_prefix="PAT")
    assert run.status == "render_failed"
    assert run.failure["stage"] == "render" and run.failure["recommendation"]
