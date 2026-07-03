"""Knowledge Governance / Review Queue tests (M2 Phase 2) — AP-12.

Covers: prioritization, configurable auto-approval policy, human approve/reject,
resolution history (rejected knowledge kept, not deleted), evidence explorer,
priority ordering, event publication, and the promotion-engine → queue sync.
Real tmp_path PlatformMemory + injected clock/publisher; no network/Telegram.
"""
import pytest

from saathi.memory.platform import PlatformMemory, PromotionState, MemoryScope
from saathi.memory.review_queue import (
    ReviewQueue, ReviewStatus, ReviewPriority, AutoApprovalPolicy, prioritize,
)

NOW = 3_000_000.0


@pytest.fixture
def mem(tmp_path):
    return PlatformMemory(str(tmp_path / "m.db"), now=lambda: NOW)


def _under_review(mem, *, ktype="behavior", confidence=0.6, scope=MemoryScope.PRODUCT):
    """Create a knowledge item already routed to UNDER_REVIEW."""
    kid = mem.record_knowledge(key=f"k{confidence}{ktype}", knowledge_type=ktype,
                               value="v", scope=scope, confidence=confidence)
    mem.transition_knowledge(kid, PromotionState.CANDIDATE)
    mem.transition_knowledge(kid, PromotionState.UNDER_REVIEW)
    return kid


def _q(mem, **kw):
    return ReviewQueue(mem, now=lambda: NOW, **kw)


# ── prioritization ────────────────────────────────────────────────────────
def test_prioritizer_maps_types():
    assert prioritize("security", False) is ReviewPriority.CRITICAL
    assert prioritize("business", False) is ReviewPriority.HIGH
    assert prioritize("finance", False) is ReviewPriority.HIGH
    assert prioritize("architecture", False) is ReviewPriority.MEDIUM
    assert prioritize("writing_style", False) is ReviewPriority.LOW
    assert prioritize("unknown", False) is ReviewPriority.MEDIUM
    # contradiction bumps a low item up, never down
    assert prioritize("writing_style", True) is ReviewPriority.HIGH


# ── auto-approval policy ──────────────────────────────────────────────────
def test_high_confidence_low_risk_auto_approves():
    policy = AutoApprovalPolicy(min_confidence=0.9)
    m = None
    # build inline mem
    import tempfile, os
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    mem = PlatformMemory(p, now=lambda: NOW)
    kid = _under_review(mem, confidence=0.97)
    q = _q(mem, policy=policy)
    rev = q.enqueue(kid, reason="high conf")
    assert rev.status is ReviewStatus.APPROVED
    assert rev.reviewer == "auto"
    assert mem.get_knowledge(kid).promotion_state is PromotionState.PROMOTED


def test_strategic_knowledge_stays_pending_for_human(mem):
    kid = _under_review(mem, ktype="business", confidence=0.99)
    # default policy only auto-approves allowed_types (behavior/performance/…), not business
    q = _q(mem)
    rev = q.enqueue(kid, reason="strategic")
    assert rev.status is ReviewStatus.PENDING
    assert rev.priority is ReviewPriority.HIGH


def test_contradiction_blocks_auto_approval(mem):
    kid = _under_review(mem, confidence=0.99)
    q = _q(mem, policy=AutoApprovalPolicy(min_confidence=0.9, allow_contradiction=False))
    rev = q.enqueue(kid, has_contradiction=True)
    assert rev.status is ReviewStatus.PENDING     # conflict → human decides


def test_low_confidence_stays_pending(mem):
    kid = _under_review(mem, confidence=0.6)
    rev = _q(mem).enqueue(kid)
    assert rev.status is ReviewStatus.PENDING


# ── human resolution + history ────────────────────────────────────────────
def test_approve_promotes_and_records(mem):
    kid = _under_review(mem, confidence=0.6)
    q = _q(mem)
    rev = q.enqueue(kid)
    resolved = q.approve(rev.review_id, reviewer="ajay")
    assert resolved.status is ReviewStatus.APPROVED
    assert resolved.reviewer == "ajay"
    assert mem.get_knowledge(kid).promotion_state is PromotionState.PROMOTED


def test_reject_archives_but_keeps_history(mem):
    kid = _under_review(mem, confidence=0.6)
    q = _q(mem)
    rev = q.enqueue(kid)
    q.reject(rev.review_id, reviewer="ajay", reason="not general enough")
    k = mem.get_knowledge(kid)
    assert k.promotion_state is PromotionState.ARCHIVED   # not deleted
    assert k.status == "rejected"
    hist = q.history()
    assert len(hist) == 1
    assert hist[0].resolution == "not general enough"     # reason preserved for reconsideration


def test_cannot_resolve_twice(mem):
    kid = _under_review(mem, confidence=0.6)
    q = _q(mem)
    rev = q.enqueue(kid)
    q.approve(rev.review_id, "ajay")
    with pytest.raises(ValueError, match="already"):
        q.reject(rev.review_id, "ajay")


# ── priority ordering + events + evidence explorer ────────────────────────
def test_pending_sorted_by_priority(mem):
    q = _q(mem)
    q.enqueue(_under_review(mem, ktype="writing_style", confidence=0.5))   # LOW
    q.enqueue(_under_review(mem, ktype="security", confidence=0.5))         # CRITICAL
    q.enqueue(_under_review(mem, ktype="business", confidence=0.5))         # HIGH
    order = [r.priority for r in q.pending()]
    assert order == [ReviewPriority.CRITICAL, ReviewPriority.HIGH, ReviewPriority.LOW]


def test_events_published(mem):
    events = []
    q = _q(mem, publish=lambda n, p: events.append(n))
    kid = _under_review(mem, confidence=0.6)
    rev = q.enqueue(kid)
    assert "knowledge.review_enqueued" in events
    q.approve(rev.review_id, "ajay")
    assert "knowledge.promoted" in events and "brain.update_candidate" in events


def test_evidence_explorer_traces_to_episodes(mem):
    e1 = mem.record_episode(agent="a", department="d", product="pielts",
                            intent="x", action="", result="", outcome="success", quality_score=0.9)
    e2 = mem.record_episode(agent="a", department="d", product="pielts",
                            intent="x", action="", result="", outcome="success", quality_score=0.8)
    kid = mem.record_knowledge(key="traced", knowledge_type="behavior", value="v",
                               scope=MemoryScope.PRODUCT, confidence=0.6,
                               source_episode_ids=[e1, e2])
    mem.transition_knowledge(kid, PromotionState.CANDIDATE)
    mem.transition_knowledge(kid, PromotionState.UNDER_REVIEW)
    q = _q(mem)
    rev = q.enqueue(kid)
    ev = q.evidence_for(rev.review_id)
    assert len(ev["episodes"]) == 2                       # explainable to raw episodes
    assert {e["episode_id"] for e in ev["episodes"]} == {e1, e2}


# ── integration: promotion engine → queue ─────────────────────────────────
def test_sync_from_memory_picks_up_routed_candidates(mem):
    _under_review(mem, ktype="business", confidence=0.7)
    _under_review(mem, ktype="finance", confidence=0.8)
    q = _q(mem)
    picked = q.sync_from_memory()
    assert len(picked) == 2
    assert q.counts()["pending"] == 2


def test_telegram_review_card(mem):
    from saathi.memory.review_queue import format_review_for_telegram
    e1 = mem.record_episode(agent="a", department="d", product="pielts",
                            intent="x", action="", result="", outcome="success", quality_score=0.9)
    e2 = mem.record_episode(agent="a", department="d", product="ai_studio",
                            intent="x", action="", result="", outcome="success", quality_score=0.9)
    kid = mem.record_knowledge(key="tg", knowledge_type="performance",
                               value="Pause rendering above 90% disk usage",
                               scope=MemoryScope.PLATFORM, confidence=0.97,
                               source_episode_ids=[e1, e2])
    mem.transition_knowledge(kid, PromotionState.CANDIDATE)
    mem.transition_knowledge(kid, PromotionState.UNDER_REVIEW)
    q = _q(mem, policy=AutoApprovalPolicy(min_confidence=1.1))  # force pending
    rev = q.enqueue(kid, reason="cross-product performance rule")
    card = format_review_for_telegram(q.evidence_for(rev.review_id))
    assert "🧠 Knowledge Review" in card
    assert "Pause rendering above 90%" in card
    assert "97%" in card
    assert "Cross-product: YES" in card
    assert f"/approve_{rev.review_id}" in card
