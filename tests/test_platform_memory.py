"""M2 Phase 1a — Platform Memory Foundation tests (written BEFORE implementation).

The contract: transform PIELTS application memory into generic platform memory
without breaking existing functionality. Products attach metadata; the schema
is product-agnostic (`Episode`, not `IELTSEpisode`).

Covers: generic episode schema, generic knowledge schema, Promotion State
Machine (legal + illegal transitions), retention policies, knowledge scope,
source trace (episode ids), verification_count, and PIELTS compatibility.
"""
import time

import pytest

from saathi.memory.platform import (
    PlatformMemory, Episode, Knowledge,
    PromotionState, MemoryScope, RetentionPolicy, retention_expiry,
)


@pytest.fixture
def mem(tmp_path):
    return PlatformMemory(str(tmp_path / "platform_memory.db"))


# ── 1. Generic Episode schema ─────────────────────────────────────────────
def test_episode_is_product_agnostic(mem):
    """Same schema serves pielts, HCG POS, AI Studio, crypto — via metadata."""
    eids = []
    for product, metadata in [
        ("pielts",    {"student_id": "s1", "skill": "writing", "band_est": 6.5}),
        ("hcg_pos",   {"table": 8, "menu": "Dal Bhat"}),
        ("ai_studio", {"video_id": "v42", "renderer": "LTX-2"}),
        ("crypto",    {"coin": "PEPE", "signal": "BUY"}),
    ]:
        eids.append(mem.record_episode(
            agent=f"{product}_agent", department=product, product=product,
            intent="do_work", action="did work", result="ok", outcome="success",
            quality_score=0.9, metadata=metadata,
        ))
    assert len(set(eids)) == 4
    ep = mem.get_episode(eids[0])
    assert ep.product == "pielts"
    assert ep.metadata["student_id"] == "s1"       # product data lives in metadata
    assert mem.get_episode(eids[1]).metadata["menu"] == "Dal Bhat"


def test_episode_carries_platform_fields(mem):
    eid = mem.record_episode(
        agent="writing_subagent", department="IELTS Tutor", product="pielts",
        user="u1", intent="evaluate_essay", action="scored essay",
        result="band 6.5 feedback", outcome="success", quality_score=0.85,
        confidence=0.9, cost=0.002, duration_ms=1200,
        scope=MemoryScope.PRODUCT, retention=RetentionPolicy.WORKFLOW,
        summary="Essay evaluated at band 6.5",
        metadata={"student_id": "s1"},
    )
    ep = mem.get_episode(eid)
    assert ep.agent == "writing_subagent" and ep.department == "IELTS Tutor"
    assert ep.outcome == "success" and ep.quality_score == 0.85
    assert ep.scope is MemoryScope.PRODUCT
    assert ep.retention is RetentionPolicy.WORKFLOW
    assert ep.promotion_state is PromotionState.NEW
    assert ep.expires_at is not None                # WORKFLOW → 30 days


# ── 2. Generic Knowledge (semantic) schema ────────────────────────────────
def test_knowledge_schema_with_trace_and_verification(mem):
    e1 = mem.record_episode(agent="a", department="d", product="pielts",
                            intent="x", action="", result="", outcome="success", quality_score=0.9)
    e2 = mem.record_episode(agent="a", department="d", product="pielts",
                            intent="x", action="", result="", outcome="success", quality_score=0.8)
    kid = mem.record_knowledge(
        key="hooks_under_3s_outperform",
        knowledge_type="performance",
        value="Video hooks under 3 seconds retain more viewers",
        scope=MemoryScope.PLATFORM,
        confidence=0.7, quality_score=0.8,
        source_episode_ids=[e1, e2],                  # ← Source Trace
    )
    k = mem.get_knowledge(kid)
    assert k.knowledge_type == "performance"
    assert k.source_episode_ids == [e1, e2]           # "why do I believe this?"
    assert k.source_episode_count == 2
    assert k.verification_count == 1                  # observed once so far
    assert k.promotion_state is PromotionState.NEW
    assert k.status == "active"


def test_verification_count_grows_with_evidence(mem):
    kid = mem.record_knowledge(key="k1", knowledge_type="behavior", value="v",
                               scope=MemoryScope.PRODUCT)
    e = mem.record_episode(agent="a", department="d", product="p",
                           intent="x", action="", result="", outcome="success", quality_score=1.0)
    for _ in range(3):
        mem.verify_knowledge(kid, source_episode_id=e)
    k = mem.get_knowledge(kid)
    assert k.verification_count == 4                  # 1 initial + 3 verifications
    assert k.last_verified is not None


# ── 3. Promotion State Machine ────────────────────────────────────────────
def test_promotion_state_machine_legal_path(mem):
    kid = mem.record_knowledge(key="k2", knowledge_type="behavior", value="v",
                               scope=MemoryScope.PRODUCT)
    for state in (PromotionState.CANDIDATE, PromotionState.UNDER_REVIEW,
                  PromotionState.PROMOTED, PromotionState.SUPERSEDED,
                  PromotionState.ARCHIVED):
        mem.transition_knowledge(kid, state, reason="test step")
    assert mem.get_knowledge(kid).promotion_state is PromotionState.ARCHIVED


def test_promotion_state_machine_rejects_illegal_jump(mem):
    kid = mem.record_knowledge(key="k3", knowledge_type="behavior", value="v",
                               scope=MemoryScope.PRODUCT)
    with pytest.raises(ValueError, match="illegal transition"):
        mem.transition_knowledge(kid, PromotionState.PROMOTED)   # NEW → PROMOTED skips review
    # and a terminal state cannot move on
    for s in (PromotionState.CANDIDATE, PromotionState.UNDER_REVIEW, PromotionState.PROMOTED,
              PromotionState.SUPERSEDED, PromotionState.ARCHIVED):
        mem.transition_knowledge(kid, s)
    with pytest.raises(ValueError, match="illegal transition"):
        mem.transition_knowledge(kid, PromotionState.NEW)


def test_transition_records_reason(mem):
    kid = mem.record_knowledge(key="k4", knowledge_type="behavior", value="v",
                               scope=MemoryScope.PRODUCT)
    mem.transition_knowledge(kid, PromotionState.CANDIDATE, reason="≥2 similar episodes")
    assert mem.get_knowledge(kid).promotion_reason == "≥2 similar episodes"


# ── 4. Retention policies ─────────────────────────────────────────────────
def test_retention_policies_map_to_expiry():
    now = 1_000_000.0
    assert retention_expiry(RetentionPolicy.SESSION, now) == now + 7 * 86400
    assert retention_expiry(RetentionPolicy.WORKFLOW, now) == now + 30 * 86400
    assert retention_expiry(RetentionPolicy.SEMANTIC, now) is None       # forever
    assert retention_expiry(RetentionPolicy.PLATFORM_WISDOM, now) is None  # never delete


def test_platform_wisdom_is_never_expirable(mem):
    eid = mem.record_episode(agent="a", department="d", product=None,
                             intent="principle", action="", result="",
                             outcome="success", quality_score=1.0,
                             retention=RetentionPolicy.PLATFORM_WISDOM)
    assert mem.get_episode(eid).expires_at is None


# ── 5. Knowledge scope ────────────────────────────────────────────────────
def test_scope_promotion_rules_are_deterministic(mem):
    """Only PLATFORM/GLOBAL scope may cross products (SES-003 firewall)."""
    assert mem.may_cross_products(MemoryScope.PLATFORM) is True
    assert mem.may_cross_products(MemoryScope.GLOBAL) is True
    for s in (MemoryScope.SESSION, MemoryScope.PRODUCT, MemoryScope.DEPARTMENT):
        assert mem.may_cross_products(s) is False


# ── 6. PIELTS backward compatibility ──────────────────────────────────────
def test_pielts_adapter_maps_old_fields_into_metadata(mem):
    """The old (student_id, skill, band_est) interaction still records cleanly."""
    eid = mem.record_pielts_interaction(
        student_id="s9", skill="speaking", input_text="my hometown...",
        response="good fluency", band_est=6.0,
    )
    ep = mem.get_episode(eid)
    assert ep.product == "pielts"
    assert ep.metadata["student_id"] == "s9"
    assert ep.metadata["skill"] == "speaking"
    assert ep.metadata["band_est"] == 6.0
    assert ep.intent == "ielts_speaking_practice"


def test_query_episodes_by_product_and_intent(mem):
    for i in range(3):
        mem.record_episode(agent="a", department="d", product="pielts",
                           intent="evaluate_essay", action="", result="",
                           outcome="success", quality_score=0.8)
    mem.record_episode(agent="a", department="d", product="hcg_pos",
                       intent="record_sale", action="", result="",
                       outcome="success", quality_score=1.0)
    assert len(mem.episodes(product="pielts")) == 3
    assert len(mem.episodes(product="pielts", intent="evaluate_essay")) == 3
    assert len(mem.episodes(product="hcg_pos")) == 1
