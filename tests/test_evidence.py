"""Evidence Scoring + Contradiction Detector tests (M2 Phase 1b Stage 4) — AP-12.

Episode/Knowledge dataclasses built directly with literals; no DB needed.
"""
from saathi.memory.platform import (
    Episode, Knowledge, PromotionState, MemoryScope, RetentionPolicy,
)
from saathi.memory.evidence import score_evidence, find_contradictions, EvidenceScore

_DAY = 86400.0


def _ep(product="pielts", department="IELTS Tutor", agent="a", created_at=1_000_000.0):
    return Episode(
        episode_id=1, agent=agent, department=department, product=product,
        user=None, intent="x", action="", result="", outcome="success",
        quality_score=0.9, confidence=1.0, cost=0.0, duration_ms=0,
        scope=MemoryScope.PRODUCT, retention=RetentionPolicy.STANDARD,
        created_at=created_at, expires_at=None,
        promotion_state=PromotionState.NEW, promotion_reason="", summary="", metadata={},
    )


def _k(value, state=PromotionState.PROMOTED, status="active"):
    return Knowledge(
        knowledge_id=1, key="k", knowledge_type="performance", value=value,
        scope=MemoryScope.PLATFORM, confidence=0.9, quality_score=0.9,
        source_episode_ids=[], source_episode_count=0, verification_count=1,
        cross_product_score=0.0, promotion_state=state, promotion_reason="",
        last_verified=None, status=status, created_at=1_000_000.0,
    )


# ── evidence scoring ──────────────────────────────────────────────────────
def test_verification_scales_and_caps():
    assert score_evidence([_ep()] * 5, 1.0).verification == 0.5
    assert score_evidence([_ep()] * 20, 1.0).verification == 1.0


def test_source_diversity():
    same = [_ep(product="p", department="d", agent="a") for _ in range(3)]
    assert score_evidence(same, 1.0).source_diversity < 0.5
    diverse = [_ep(product=f"prod{i}", department=f"dep{i}", agent=f"ag{i}") for i in range(3)]
    assert score_evidence(diverse, 1.0).source_diversity == 1.0


def test_time_consistency_burst_vs_spread():
    burst = [_ep(created_at=1_000_000.0) for _ in range(3)]
    assert score_evidence(burst, 1.0).time_consistency == 0.0
    spread = [_ep(created_at=1_000_000.0), _ep(created_at=1_000_000.0 + 8 * _DAY)]
    assert score_evidence(spread, 1.0).time_consistency == 1.0


def test_cross_product():
    one = [_ep(product="pielts") for _ in range(3)]
    multi = [_ep(product=f"p{i}") for i in range(3)]
    assert score_evidence(one, 1.0).cross_product < score_evidence(multi, 1.0).cross_product
    assert score_evidence(multi, 1.0).cross_product == 1.0


def test_contradiction_risk_and_overall_drop():
    base = score_evidence([_ep()] * 3, 1.0, n_contradictions=0)
    one = score_evidence([_ep()] * 3, 1.0, n_contradictions=1)
    many = score_evidence([_ep()] * 3, 1.0, n_contradictions=3)
    assert base.contradiction_risk == 0.0
    assert one.contradiction_risk == 0.4
    assert many.contradiction_risk == 1.0
    assert base.overall > one.overall > many.overall


def test_overall_weights_hand_computed():
    # 3 same-source episodes, burst timing, single product, llm=0.8, 0 contradictions.
    # verification=3/10=0.3, diversity=1/3≈0.333, time=0.0, cross=1/3≈0.333, llm=0.8, non_contra=1.0
    # overall = .20*.3 + .15*(1/3) + .10*0 + .10*(1/3) + .20*.8 + .25*1.0
    #         = .06 + .05 + 0 + .033333 + .16 + .25 = .553333 → 0.553
    s = score_evidence([_ep(product="pielts", department="d", agent="a")] * 3, 0.8, 0)
    assert s.overall == 0.553


# ── contradiction detection ───────────────────────────────────────────────
def test_flags_classic_renderer_conflict():
    existing = [_k("Use Renderer X for educational videos")]
    conflicts = find_contradictions(
        "Renderer Y consistently outperforms Renderer X", existing)
    assert len(conflicts) == 1


def test_unrelated_knowledge_not_flagged():
    existing = [_k("Post shorts at 8pm Nepal time")]
    conflicts = find_contradictions(
        "Renderer Y consistently outperforms Renderer X", existing)
    assert conflicts == []


def test_non_promoted_or_rejected_ignored():
    existing = [
        _k("Use Renderer X for educational videos", state=PromotionState.CANDIDATE),
        _k("Use Renderer X for educational videos", status="rejected"),
    ]
    conflicts = find_contradictions(
        "Renderer Y consistently outperforms Renderer X", existing)
    assert conflicts == []


def test_same_topic_restatement_not_flagged():
    # Same topic, no opposing markers, no distinct competing entity → not a conflict.
    existing = [_k("Use Renderer X for educational videos")]
    conflicts = find_contradictions("Renderer X for education content", existing)
    assert conflicts == []
