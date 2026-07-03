"""Knowledge Publication Engine tests (M2 Phase 5) — AP-12 + AP-20.

The cardinal rule under test: NO automatic edits — markdown renders only after
approval. Covers destination routing, deduplication (no proposal spam),
lifecycle, evidence linking, document impact analysis, and events.
"""
import pytest

from saathi.publication import (
    PublicationEngine, TargetDocument, ChangeType, ProposalState,
    route_destination, analyze_impact,
)


@pytest.fixture
def eng(tmp_path):
    return PublicationEngine(str(tmp_path / "pub.db"), now=lambda: 5_000_000.0)


# ── destination routing ───────────────────────────────────────────────────
def test_destination_router():
    assert route_destination("architecture") is TargetDocument.BRAIN
    assert route_destination("business") is TargetDocument.BUSINESS
    assert route_destination("finance") is TargetDocument.BUSINESS
    assert route_destination("principle") is TargetDocument.WISDOM
    assert route_destination("style") is TargetDocument.WRITING_STYLE
    assert route_destination("decision") is TargetDocument.ADR
    assert route_destination("maturity") is TargetDocument.BUILD_STATUS
    assert route_destination("unknown") is TargetDocument.BRAIN   # default


def test_proposal_routed_to_correct_document(eng):
    p = eng.propose(knowledge_type="business", summary="Focus pielts premium tier",
                    confidence=0.8)
    assert p.target_document is TargetDocument.BUSINESS


# ── deduplication ─────────────────────────────────────────────────────────
def test_duplicate_proposals_merge_not_spam(eng):
    a = eng.propose(knowledge_type="architecture",
                    summary="Storage Intelligence should own cleanup",
                    evidence_knowledge_ids=[1], confidence=0.7)
    # near-identical summary (word order / casing) → merges into the same proposal
    b = eng.propose(knowledge_type="architecture",
                    summary="cleanup should own Storage Intelligence",
                    evidence_knowledge_ids=[2, 3], confidence=0.75)
    assert a.proposal_id == b.proposal_id                      # one proposal, not two
    assert b.evidence_knowledge_ids == [1, 2, 3]               # evidence merged
    assert b.confidence > a.confidence                        # confidence bumped
    assert len(eng.pending()) == 1                            # no spam


# ── lifecycle + no-edit-before-approval ───────────────────────────────────
def test_markdown_only_renders_after_approval(eng):
    p = eng.propose(knowledge_type="architecture", summary="A new principle",
                    evidence_knowledge_ids=[9], confidence=0.9)
    with pytest.raises(ValueError, match="before approval"):
        eng.render_markdown(p.proposal_id)                    # NO automatic edits
    eng.approve(p.proposal_id)
    md = eng.render_markdown(p.proposal_id)                    # now allowed
    assert "A new principle" in md
    assert "#9" in md                                        # evidence linked into the view


def test_lifecycle_rejects_illegal_transition(eng):
    p = eng.propose(knowledge_type="architecture", summary="X", confidence=0.5)
    with pytest.raises(ValueError, match="illegal transition"):
        eng.transition(p.proposal_id, ProposalState.PUBLISHED)  # draft can't jump to published


def test_full_lifecycle_to_published(eng):
    p = eng.propose(knowledge_type="architecture", summary="Y", confidence=0.9)
    eng.approve(p.proposal_id)
    eng.render_markdown(p.proposal_id)
    pub = eng.mark_published(p.proposal_id)
    assert pub.state is ProposalState.PUBLISHED


# ── document impact analyzer ──────────────────────────────────────────────
def test_impact_analyzer_flags_affected_specs():
    assert "SES-003" in analyze_impact("Change how episodic memory promotion works")
    assert "SES-019A" in analyze_impact("Storage cleanup should pause rendering")
    impacts = analyze_impact("A new agent safety governance rule")
    assert "SES-002" in impacts


def test_proposal_records_impacts(eng):
    p = eng.propose(knowledge_type="architecture",
                    summary="Memory promotion should require 3 episodes", confidence=0.9)
    assert "SES-003" in p.impacts


# ── events ────────────────────────────────────────────────────────────────
def test_events_published(tmp_path):
    events = []
    eng = PublicationEngine(str(tmp_path / "p.db"), publish=lambda n, p: events.append(n),
                            now=lambda: 5_000_000.0)
    p = eng.propose(knowledge_type="architecture", summary="Z", confidence=0.9)
    eng.approve(p.proposal_id)
    eng.mark_published(p.proposal_id)
    assert "doc.proposal_created" in events
    assert "doc.proposal_approved" in events
    assert "doc.proposal_published" in events


def test_counts_by_target(eng):
    eng.propose(knowledge_type="architecture", summary="a rule", confidence=0.5)
    eng.propose(knowledge_type="business", summary="a strategy", confidence=0.5)
    counts = eng.counts_by_target()
    assert counts.get("Brain.md") == 1
    assert counts.get("Business.md") == 1
