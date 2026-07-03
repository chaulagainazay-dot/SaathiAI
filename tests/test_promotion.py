"""Memory Promotion Engine tests (M2 Phase 1b) — the staged pipeline, AP-12.

Uses a real tmp_path PlatformMemory with an injected clock so episodes can be
aged deterministically. No LLM, no network. Verifies discovery filtering,
intent clustering, structured extraction, state transitions (never illegal),
the auto-promote / contradiction / strategic routing paths, event publication,
and idempotency.
"""
import time

import pytest

from saathi.memory.platform import PlatformMemory, PromotionState, MemoryScope
from saathi.memory.promotion import (
    PromotionEngine, PatternExtraction, deterministic_extractor,
)

DAY = 86400.0
NOW = 2_000_000.0
OLD = NOW - 5 * DAY       # older than the 3-day min age
FRESH = NOW - 1 * DAY      # too fresh


@pytest.fixture
def mem(tmp_path):
    # clock fixed at an OLD time so records land aged; the engine's own clock is NOW
    return PlatformMemory(str(tmp_path / "m.db"), now=lambda: OLD)


def _engine(mem, **kw):
    return PromotionEngine(mem, now=lambda: NOW, **kw)


def _add(mem, intent, product="pielts", outcome="success", n=1):
    for _ in range(n):
        mem.record_episode(agent="a", department="d", product=product,
                           intent=intent, action="", result="", outcome=outcome,
                           quality_score=0.9)


# ── discovery + clustering ────────────────────────────────────────────────
def test_discovery_filters_age_state_and_cluster_size(mem):
    _add(mem, "evaluate_essay", n=3)                    # aged, ≥2 → cluster
    _add(mem, "singleton_intent", n=1)                  # too small
    # a fresh cluster (created "now")
    mem2now = PlatformMemory(mem.path, now=lambda: FRESH)
    for _ in range(3):
        mem2now.record_episode(agent="a", department="d", product="pielts",
                               intent="fresh_intent", action="", result="",
                               outcome="success", quality_score=0.9)
    clusters = _engine(mem).discover()
    assert "evaluate_essay" in clusters
    assert "singleton_intent" not in clusters           # below min_cluster_size
    assert "fresh_intent" not in clusters                # too fresh


def test_clusters_never_mix_intents(mem):
    _add(mem, "render_failed_gpu", n=2)
    _add(mem, "render_failed_network", n=2)
    clusters = _engine(mem).discover()
    assert set(clusters) == {"render_failed_gpu", "render_failed_network"}
    assert all(e.intent == "render_failed_gpu" for e in clusters["render_failed_gpu"])


# ── extraction ────────────────────────────────────────────────────────────
def test_deterministic_extractor_is_structured(mem):
    _add(mem, "evaluate_essay", n=4)
    eps = mem.episodes(intent="evaluate_essay")
    ext = deterministic_extractor("evaluate_essay", eps)
    assert isinstance(ext, PatternExtraction)
    assert ext.evidence == [e.episode_id for e in eps]
    assert 0.0 <= ext.confidence <= 1.0


# ── run(): knowledge creation + source trace ──────────────────────────────
def test_run_creates_candidate_with_source_trace(mem):
    _add(mem, "evaluate_essay", n=2)                    # score below auto-approve
    report = _engine(mem, auto_approve_threshold=0.99).run()
    assert report.clusters_found == 1
    assert report.candidates_created == 1
    k = mem.get_knowledge(1)
    assert k.promotion_state is PromotionState.CANDIDATE
    assert k.source_episode_count == 2                  # source trace preserved
    assert k.scope is MemoryScope.PRODUCT               # single product


def test_auto_promotion_path_emits_events(mem):
    _add(mem, "evaluate_essay", product="pielts", n=8)  # lots of evidence
    events = []
    report = _engine(mem, auto_approve_threshold=0.4,
                     publish=lambda n, p: events.append(n)).run()
    assert report.auto_promoted == 1
    assert mem.get_knowledge(1).promotion_state is PromotionState.PROMOTED
    assert "knowledge.promoted" in events
    assert "brain.update_candidate" in events


def test_contradiction_path_routes_to_review(mem):
    _add(mem, "choose_renderer", n=3)
    # inject a finder that always reports a conflict with an existing item
    from saathi.memory.platform import Knowledge
    fake_conflict = Knowledge(
        knowledge_id=99, key="old", knowledge_type="performance",
        value="Use Renderer X", scope=MemoryScope.PLATFORM, confidence=0.9,
        quality_score=0.9, source_episode_ids=[], source_episode_count=0,
        verification_count=1, cross_product_score=0.0,
        promotion_state=PromotionState.PROMOTED, promotion_reason="",
        last_verified=None, status="active", created_at=OLD)
    events = []
    report = _engine(mem, auto_approve_threshold=0.0,
                     contradiction_finder=lambda v, e: [fake_conflict],
                     publish=lambda n, p: events.append(n)).run()
    assert report.conflicts_flagged == 1
    assert mem.get_knowledge(1).promotion_state is PromotionState.UNDER_REVIEW
    assert "knowledge.conflict_detected" in events


def test_strategic_knowledge_requires_review(mem):
    _add(mem, "pricing_strategy", n=5)
    events = []
    report = _engine(mem, auto_approve_threshold=0.0,
                     knowledge_type_resolver=lambda intent, p: "business",
                     publish=lambda n, p: events.append(n)).run()
    assert report.sent_to_review == 1
    assert mem.get_knowledge(1).promotion_state is PromotionState.UNDER_REVIEW
    assert "knowledge.review_requested" in events


# ── idempotency + state-machine safety ────────────────────────────────────
def test_source_episodes_consumed_second_run_finds_nothing(mem):
    _add(mem, "evaluate_essay", n=3)
    eng = _engine(mem, auto_approve_threshold=0.99)
    assert eng.run().clusters_found == 1
    assert eng.run().clusters_found == 0                # episodes marked consumed


def test_final_states_are_all_legal(mem):
    _add(mem, "a_intent", n=8)
    _add(mem, "b_intent", n=2)
    _engine(mem, auto_approve_threshold=0.4).run()
    legal = {PromotionState.CANDIDATE, PromotionState.UNDER_REVIEW, PromotionState.PROMOTED}
    for kid in (1, 2):
        k = mem.get_knowledge(kid)
        if k:
            assert k.promotion_state in legal
