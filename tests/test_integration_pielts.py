"""PIELTS × Learning Runtime integration (M3 Sprint) — AP-12.

Proves the loop the design describes: student interactions become platform
Episodes → Promotion Engine clusters them → a knowledge candidate emerges → the
Learning Engine can analyze outcomes. PIELTS becomes a continuously-improving
tutor by *using the platform*, not reimplementing it (Dev Rule #2, AP-01).
"""
import pytest

from saathi.memory.platform import PlatformMemory, PromotionState
from saathi.memory.promotion import PromotionEngine
from saathi.learning import LearningEngine, CapabilityImprovementRegistry
from saathi import integration


NOW = 6_000_000.0
OLD = NOW - 5 * 86400   # older than promotion's 3-day min age


@pytest.fixture
def platform(tmp_path):
    mem = PlatformMemory(str(tmp_path / "platform.db"), now=lambda: OLD)
    integration.set_platform_memory(mem)
    events = []
    integration.set_publisher(lambda n, p: events.append((n, p)))
    yield mem, events
    integration.set_platform_memory(None)   # reset global


def test_pielts_interaction_becomes_platform_episode(platform):
    mem, events = platform
    eid = integration.ingest_pielts_interaction(
        student_id="s1", skill="writing", input_text="My essay on climate",
        response="Band 6.5 — good structure", band_est=6.5)
    ep = mem.get_episode(eid)
    assert ep.product == "pielts"
    assert ep.metadata["student_id"] == "s1"
    assert ep.metadata["skill"] == "writing"
    assert ep.intent == "ielts_writing_practice"
    # event-first: the platform is notified
    assert any(n == "execution.recorded" for n, _ in events)


def test_pielts_interactions_promote_to_knowledge_candidate(platform):
    mem, _ = platform
    # Several similar writing-practice interactions accumulate...
    for i in range(4):
        integration.ingest_pielts_interaction(
            student_id=f"s{i}", skill="writing",
            input_text="essay", response="feedback", band_est=6.0)
    # ...and the shared Promotion Engine turns them into a knowledge candidate.
    engine = PromotionEngine(mem, now=lambda: NOW, auto_approve_threshold=0.99)
    report = engine.run()
    assert report.candidates_created >= 1
    k = mem.get_knowledge(1)
    assert k is not None
    assert k.promotion_state in (PromotionState.CANDIDATE, PromotionState.UNDER_REVIEW)
    assert "ielts_writing_practice" in k.value.lower() or k.source_episode_count == 4


def test_learning_engine_evaluates_pielts_outcomes(platform, tmp_path):
    mem, _ = platform
    integration.ingest_pielts_interaction(student_id="s1", skill="speaking",
                                          input_text="hi", response="ok", band_est=6.0,
                                          outcome="success")
    integration.ingest_pielts_interaction(student_id="s2", skill="speaking",
                                          input_text="hi", response="err", band_est=None,
                                          outcome="failure")
    reg = CapabilityImprovementRegistry(str(tmp_path / "imp.db"), now=lambda: NOW)
    scores = LearningEngine(mem, reg, now=lambda: NOW).evaluate_outcomes(product="pielts")
    s = scores["ielts_speaking_practice"]
    assert s.n == 2 and s.success_rate == 0.5     # the tutor can see its own success rate
