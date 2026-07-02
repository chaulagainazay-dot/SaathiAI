"""Predictive Storage Engine tests (SES-019A Part 4) — AP-12.

Verifies plan-based estimation, per-renderer profile differences, the
safe/blocked decision, and event emission. Free-space reader + publisher
injected; no real disk or bus.
"""
from saathi.events import EventBus, WILDCARD
from saathi.storage import PredictiveStorageEngine
from saathi.storage.predictive import estimate_plan, RenderPlan as RP


def _plan(renderer="ltx", scenes=60, dur=4.0, fps=24, w=1080, h=1920):
    return RP(scene_count=scenes, avg_scene_duration_s=dur, fps=fps, width=w, height=h, renderer=renderer)


def test_frame_count_from_plan():
    p = _plan(scenes=60, dur=4.0, fps=24)
    assert p.total_duration_s == 240.0
    assert p.frame_count == 5760          # 240s × 24fps


def test_comfyui_needs_more_than_ffmpeg():
    """Different renderers → different temp footprints (the whole point)."""
    comfy = estimate_plan(_plan(renderer="comfyui"))
    ffmpeg = estimate_plan(_plan(renderer="ffmpeg"))
    assert comfy.peak_bytes > ffmpeg.peak_bytes
    assert ffmpeg.frames_bytes == 0        # muxing keeps no frame sequences


def test_decision_safe_when_room():
    est = estimate_plan(_plan())
    free = est.peak_bytes * 2              # plenty
    eng = PredictiveStorageEngine(free_reader=lambda: free)
    d = eng.decide(_plan())
    assert d.safe is True
    assert d.shortfall_bytes == 0


def test_decision_blocked_when_tight():
    est = estimate_plan(_plan())
    free = est.peak_bytes // 2             # not enough
    eng = PredictiveStorageEngine(free_reader=lambda: free)
    d = eng.decide(_plan())
    assert d.safe is False
    assert d.shortfall_bytes == est.peak_bytes - free


def test_events_emitted():
    bus = EventBus()
    seen = []
    bus.subscribe(WILDCARD, lambda e: seen.append(e.name))
    est = estimate_plan(_plan())

    PredictiveStorageEngine(free_reader=lambda: est.peak_bytes * 2, publish=bus.publish_sync).decide(_plan())
    assert "storage.render.allowed" in seen

    PredictiveStorageEngine(free_reader=lambda: est.peak_bytes // 2, publish=bus.publish_sync).decide(_plan())
    assert "storage.render.blocked" in seen
