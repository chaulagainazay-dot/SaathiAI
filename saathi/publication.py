"""Knowledge Publication Engine (M2 Phase 5) — the Brain Synchronizer, expanded.

Publishes promoted knowledge into the human-readable "constitutions" — Brain.md,
Business.md, Wisdom.md, Writing & Speaking Style, ADR candidates, CHANGELOG,
BUILD_STATUS — as **structured proposals**. The cardinal rule (your design
center):

    NO AUTOMATIC EDITS. ONLY PROPOSALS. Markdown renders only after approval.

AP-20 — Human documents are derived artifacts, not primary storage: the
authoritative source is Knowledge → Graph → Memory. Markdown is a published
view, never the database. This is what prevents document drift forever.

    Knowledge → Candidate Generator → Destination Router → Proposal (persisted)
              → Dedup → Human Approval → Markdown Renderer → Repository Update

Testable in isolation (AP-12): SQLite at any path, injected clock/publisher;
no filesystem writes (rendering returns a string — a human applies it).
"""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable


class TargetDocument(str, Enum):
    BRAIN = "Brain.md"                       # architecture knowledge
    BUSINESS = "Business.md"                 # strategy, KPIs, goals
    WISDOM = "Wisdom.md"                     # long-term principles
    WRITING_STYLE = "Writing and Speaking Style.md"  # communication behavior
    ADR = "ADR Candidate"                    # architecture decisions
    CHANGELOG = "CHANGELOG.md"               # capability milestones
    BUILD_STATUS = "BUILD_STATUS.md"         # capability maturity


class ChangeType(str, Enum):
    APPEND = "append"
    UPDATE = "update"
    SUPERSEDE = "supersede"


class ProposalState(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"


_TRANSITIONS: dict[ProposalState, set[ProposalState]] = {
    ProposalState.DRAFT: {ProposalState.READY, ProposalState.SUPERSEDED},
    ProposalState.READY: {ProposalState.UNDER_REVIEW, ProposalState.SUPERSEDED},
    ProposalState.UNDER_REVIEW: {ProposalState.APPROVED, ProposalState.READY, ProposalState.SUPERSEDED},
    ProposalState.APPROVED: {ProposalState.PUBLISHED, ProposalState.SUPERSEDED},
    ProposalState.PUBLISHED: {ProposalState.SUPERSEDED},
    ProposalState.SUPERSEDED: set(),
}


# knowledge_type → destination (Destination Router)
_ROUTING: dict[str, TargetDocument] = {
    "architecture": TargetDocument.BRAIN,
    "behavior": TargetDocument.BRAIN,
    "performance": TargetDocument.BRAIN,
    "domain": TargetDocument.BRAIN,
    "business": TargetDocument.BUSINESS,
    "finance": TargetDocument.BUSINESS,
    "strategy": TargetDocument.BUSINESS,
    "principle": TargetDocument.WISDOM,
    "wisdom": TargetDocument.WISDOM,
    "safety": TargetDocument.WISDOM,
    "style": TargetDocument.WRITING_STYLE,
    "writing_style": TargetDocument.WRITING_STYLE,
    "decision": TargetDocument.ADR,
    "capability_milestone": TargetDocument.CHANGELOG,
    "maturity": TargetDocument.BUILD_STATUS,
}


def route_destination(knowledge_type: str) -> TargetDocument:
    """Where should this knowledge go? Not every lesson belongs everywhere."""
    return _ROUTING.get(knowledge_type, TargetDocument.BRAIN)


# Deterministic Document Impact Analyzer — which docs a change touches.
_IMPACT_KEYWORDS: dict[str, list[str]] = {
    "SES-003": ["memory", "episode", "knowledge", "promotion", "semantic"],
    "SES-019A": ["storage", "disk", "cleanup", "render", "lifecycle"],
    "SES-002": ["agent", "safety", "governance", "tool", "router"],
    "SES-005": ["studio", "renderer", "video", "storyboard"],
    "SES-010": ["seo", "geo", "discovery", "publishing"],
}


def analyze_impact(summary: str) -> list[str]:
    """Which specification documents are affected by this change?"""
    text = summary.lower()
    return sorted(doc for doc, kws in _IMPACT_KEYWORDS.items()
                  if any(k in text for k in kws))


@dataclass
class Proposal:
    proposal_id: int
    target_document: TargetDocument
    section: str
    change_type: ChangeType
    summary: str
    evidence_knowledge_ids: list[int]
    confidence: float
    state: ProposalState
    generated_at: float
    approved: bool
    impacts: list[str] = field(default_factory=list)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS doc_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_document TEXT NOT NULL,
    section TEXT DEFAULT '',
    change_type TEXT NOT NULL DEFAULT 'append',
    summary TEXT NOT NULL,
    summary_key TEXT NOT NULL,
    evidence TEXT DEFAULT '[]',
    confidence REAL DEFAULT 0.0,
    state TEXT NOT NULL DEFAULT 'draft',
    impacts TEXT DEFAULT '[]',
    generated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prop_state ON doc_proposals(state);
CREATE INDEX IF NOT EXISTS idx_prop_dedup ON doc_proposals(target_document, summary_key);
"""


def _summary_key(target: TargetDocument, summary: str) -> str:
    """Normalized fingerprint for deduplication."""
    tokens = sorted(t for t in re.split(r"[^a-z0-9]+", summary.lower()) if len(t) >= 4)
    return f"{target.value}::{' '.join(tokens)}"


class PublicationEngine:
    def __init__(self, db_path: "str | Path",
                 publish: "Callable[[str, dict], None] | None" = None,
                 now: Callable[[], float] = time.time):
        Path(str(db_path)).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()
        self._publish_fn = publish
        self._now = now

    def _publish(self, name: str, payload: dict) -> None:
        if self._publish_fn is not None:
            self._publish_fn(name, payload)

    # ── propose (with deduplication) ──────────────────────────────────────
    def propose(self, *, knowledge_type: str, summary: str, section: str = "",
                evidence_knowledge_ids: list[int] | None = None, confidence: float = 0.0,
                change_type: ChangeType = ChangeType.APPEND,
                target: TargetDocument | None = None) -> Proposal:
        import json
        target = target or route_destination(knowledge_type)
        key = _summary_key(target, summary)
        evidence = evidence_knowledge_ids or []

        # Dedup: same target + normalized summary → merge evidence, bump confidence.
        existing = self.db.execute(
            "SELECT * FROM doc_proposals WHERE target_document=? AND summary_key=?"
            " AND state NOT IN ('superseded','published')",
            (target.value, key)).fetchone()
        if existing:
            merged = sorted(set(json.loads(existing["evidence"]) + evidence))
            new_conf = min(1.0, max(existing["confidence"], confidence) + 0.05 * len(evidence))
            self.db.execute(
                "UPDATE doc_proposals SET evidence=?, confidence=? WHERE id=?",
                (json.dumps(merged), new_conf, existing["id"]))
            self.db.commit()
            self._publish("doc.proposal_merged", {"proposal_id": existing["id"], "target": target.value})
            return self.get(existing["id"])

        impacts = analyze_impact(summary)
        cur = self.db.execute(
            "INSERT INTO doc_proposals (target_document, section, change_type, summary,"
            " summary_key, evidence, confidence, impacts, generated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (target.value, section, change_type.value, summary, key,
             json.dumps(evidence), confidence, json.dumps(impacts), self._now()))
        self.db.commit()
        pid = cur.lastrowid
        self._publish("doc.proposal_created",
                      {"proposal_id": pid, "target": target.value, "summary": summary})
        return self.get(pid)

    # ── lifecycle ─────────────────────────────────────────────────────────
    def transition(self, proposal_id: int, new_state: ProposalState) -> Proposal:
        p = self.get(proposal_id)
        if p is None:
            raise KeyError(proposal_id)
        if new_state not in _TRANSITIONS[p.state]:
            raise ValueError(f"illegal transition {p.state.value} -> {new_state.value}")
        self.db.execute("UPDATE doc_proposals SET state=? WHERE id=?",
                        (new_state.value, proposal_id))
        self.db.commit()
        return self.get(proposal_id)

    def approve(self, proposal_id: int) -> Proposal:
        p = self.get(proposal_id)
        # walk to APPROVED through legal states
        if p.state is ProposalState.DRAFT:
            self.transition(proposal_id, ProposalState.READY)
        if self.get(proposal_id).state is ProposalState.READY:
            self.transition(proposal_id, ProposalState.UNDER_REVIEW)
        p = self.transition(proposal_id, ProposalState.APPROVED)
        self._publish("doc.proposal_approved", {"proposal_id": proposal_id})
        return p

    def render_markdown(self, proposal_id: int) -> str:
        """Render the human-readable view — ONLY after approval. This returns a
        string; a human applies it to the file. The engine never edits docs."""
        p = self.get(proposal_id)
        if p.state not in (ProposalState.APPROVED, ProposalState.PUBLISHED):
            raise ValueError("cannot render markdown before approval — proposals only")
        evidence = ", ".join(f"#{i}" for i in p.evidence_knowledge_ids) or "—"
        md = (f"<!-- proposal {p.proposal_id} · confidence {p.confidence:.0%} · "
              f"evidence {evidence} -->\n"
              f"{p.summary}")
        return md

    def mark_published(self, proposal_id: int) -> Proposal:
        p = self.transition(proposal_id, ProposalState.PUBLISHED)
        self._publish("doc.proposal_published", {"proposal_id": proposal_id})
        return p

    # ── queries ───────────────────────────────────────────────────────────
    def pending(self, target: TargetDocument | None = None) -> list[Proposal]:
        q = "SELECT * FROM doc_proposals WHERE state NOT IN ('published','superseded')"
        params: list = []
        if target is not None:
            q += " AND target_document=?"; params.append(target.value)
        q += " ORDER BY confidence DESC"
        return [self._row(r) for r in self.db.execute(q, params).fetchall()]

    def get(self, proposal_id: int) -> Proposal | None:
        r = self.db.execute("SELECT * FROM doc_proposals WHERE id=?", (proposal_id,)).fetchone()
        return self._row(r) if r else None

    def counts_by_target(self) -> dict:
        rows = self.db.execute(
            "SELECT target_document, COUNT(*) c FROM doc_proposals"
            " WHERE state NOT IN ('published','superseded') GROUP BY target_document").fetchall()
        return {r["target_document"]: r["c"] for r in rows}

    @staticmethod
    def _row(r) -> Proposal:
        import json
        return Proposal(
            proposal_id=r["id"], target_document=TargetDocument(r["target_document"]),
            section=r["section"], change_type=ChangeType(r["change_type"]),
            summary=r["summary"], evidence_knowledge_ids=json.loads(r["evidence"]),
            confidence=r["confidence"], state=ProposalState(r["state"]),
            generated_at=r["generated_at"], approved=(r["state"] == "approved"),
            impacts=json.loads(r["impacts"] or "[]"))
