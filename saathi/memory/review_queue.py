"""Knowledge Governance Engine — the Review Queue (M2 Phase 2).

Not just a queue: the governance system for learning. Candidates routed to
review by the Promotion Engine land here, get prioritized, and are resolved
either automatically (high-confidence, low-risk, by policy) or by a human via
Telegram / Mission Control.

    Promotion Engine → Review Queue → {auto-approve | human review} → Knowledge Store

Principles applied: AP-14 (autonomy earned — strategic knowledge needs a human),
AP-16 (contradictions reviewed, never silently replaced), AP-17 (deterministic
prioritization and policy, no LLM in the governance path).

Rejected knowledge is never deleted — it keeps a resolution history so new
evidence can reopen it later.

Testable in isolation (AP-12): plain SQLite + injected clock + injected event
publisher; no network, no Telegram.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from saathi.memory.platform import PlatformMemory, Knowledge, PromotionState, MemoryScope


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


_PRIORITY_ORDER = {  # for surfacing highest-first
    ReviewPriority.CRITICAL: 0, ReviewPriority.HIGH: 1,
    ReviewPriority.MEDIUM: 2, ReviewPriority.LOW: 3,
}

# knowledge_type → review priority (deterministic prioritizer)
_TYPE_PRIORITY: dict[str, ReviewPriority] = {
    "security": ReviewPriority.CRITICAL,
    "safety": ReviewPriority.CRITICAL,
    "business": ReviewPriority.HIGH,
    "finance": ReviewPriority.HIGH,
    "strategy": ReviewPriority.HIGH,
    "architecture": ReviewPriority.MEDIUM,
    "performance": ReviewPriority.MEDIUM,
    "writing_style": ReviewPriority.LOW,
    "style": ReviewPriority.LOW,
}


def prioritize(knowledge_type: str, has_contradiction: bool) -> ReviewPriority:
    base = _TYPE_PRIORITY.get(knowledge_type, ReviewPriority.MEDIUM)
    # A contradiction never lowers priority, and bumps an otherwise-low item up.
    if has_contradiction and _PRIORITY_ORDER[base] > _PRIORITY_ORDER[ReviewPriority.HIGH]:
        return ReviewPriority.HIGH
    return base


@dataclass
class AutoApprovalPolicy:
    """Configurable — never hardcode confidence > 0.95 into logic."""
    min_confidence: float = 0.95
    allow_contradiction: bool = False
    allowed_scopes: frozenset[MemoryScope] = field(
        default_factory=lambda: frozenset({MemoryScope.PLATFORM, MemoryScope.PRODUCT}))
    allowed_types: frozenset[str] = field(
        default_factory=lambda: frozenset({"behavior", "performance", "preference", "domain", "error"}))

    def approves(self, *, confidence: float, has_contradiction: bool,
                 scope: MemoryScope, knowledge_type: str) -> bool:
        return (
            confidence >= self.min_confidence
            and (self.allow_contradiction or not has_contradiction)
            and scope in self.allowed_scopes
            and knowledge_type in self.allowed_types
        )


@dataclass
class Review:
    review_id: int
    knowledge_id: int
    status: ReviewStatus
    priority: ReviewPriority
    reason: str
    confidence: float
    risk_level: str
    scope: str
    reviewer: str | None
    created_at: float
    resolved_at: float | None
    resolution: str | None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority TEXT NOT NULL DEFAULT 'medium',
    reason TEXT DEFAULT '',
    confidence REAL DEFAULT 0.0,
    risk_level TEXT DEFAULT 'medium',
    scope TEXT DEFAULT 'product',
    reviewer TEXT,
    created_at REAL NOT NULL,
    resolved_at REAL,
    resolution TEXT
);
CREATE INDEX IF NOT EXISTS idx_rev_status ON knowledge_reviews(status);
CREATE INDEX IF NOT EXISTS idx_rev_knowledge ON knowledge_reviews(knowledge_id);
"""


class ReviewQueue:
    def __init__(self, mem: PlatformMemory,
                 policy: AutoApprovalPolicy | None = None,
                 publish: "Callable[[str, dict], None] | None" = None,
                 now: Callable[[], float] = time.time):
        self.mem = mem
        self.policy = policy or AutoApprovalPolicy()
        self._publish_fn = publish
        self._now = now
        self.mem.db.executescript(_SCHEMA)
        self.mem.db.commit()

    def _publish(self, name: str, payload: dict) -> None:
        if self._publish_fn is not None:
            self._publish_fn(name, payload)

    # ── enqueue (from the Promotion Engine) ───────────────────────────────
    def enqueue(self, knowledge_id: int, reason: str = "",
                has_contradiction: bool = False, risk_level: str = "medium") -> Review:
        """Create a review for an UNDER_REVIEW knowledge item. Auto-resolves if
        the policy approves; otherwise leaves it pending for a human."""
        k = self.mem.get_knowledge(knowledge_id)
        if k is None:
            raise KeyError(knowledge_id)
        priority = prioritize(k.knowledge_type, has_contradiction)
        now = self._now()
        cur = self.mem.db.execute(
            "INSERT INTO knowledge_reviews (knowledge_id, status, priority, reason,"
            " confidence, risk_level, scope, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (knowledge_id, ReviewStatus.PENDING.value, priority.value, reason,
             k.confidence, risk_level, k.scope.value, now),
        )
        self.mem.db.commit()
        review_id = cur.lastrowid
        self._publish("knowledge.review_enqueued",
                      {"review_id": review_id, "knowledge_id": knowledge_id,
                       "priority": priority.value})

        # Auto-approval policy (configurable, deterministic).
        if self.policy.approves(confidence=k.confidence, has_contradiction=has_contradiction,
                                scope=k.scope, knowledge_type=k.knowledge_type):
            return self._resolve(review_id, ReviewStatus.APPROVED, reviewer="auto",
                                 resolution="auto-approved by policy")
        return self._review(review_id)

    def sync_from_memory(self, reason: str = "routed by promotion engine") -> list[Review]:
        """Enqueue any UNDER_REVIEW knowledge that has no review yet (event-light
        integration path — the queue picks up what the engine routed)."""
        rows = self.mem.db.execute(
            "SELECT id FROM knowledge WHERE promotion_state=? AND id NOT IN"
            " (SELECT knowledge_id FROM knowledge_reviews)",
            (PromotionState.UNDER_REVIEW.value,),
        ).fetchall()
        return [self.enqueue(r["id"], reason=reason) for r in rows]

    # ── human resolution ──────────────────────────────────────────────────
    def approve(self, review_id: int, reviewer: str) -> Review:
        return self._resolve(review_id, ReviewStatus.APPROVED, reviewer,
                             resolution="approved")

    def reject(self, review_id: int, reviewer: str, reason: str = "") -> Review:
        return self._resolve(review_id, ReviewStatus.REJECTED, reviewer,
                             resolution=reason or "rejected")

    def _resolve(self, review_id: int, status: ReviewStatus, reviewer: str,
                 resolution: str) -> Review:
        rev = self._review(review_id)
        if rev.status is not ReviewStatus.PENDING:
            raise ValueError(f"review {review_id} already {rev.status.value}")
        # Move the underlying knowledge through the state machine.
        if status is ReviewStatus.APPROVED:
            self.mem.transition_knowledge(rev.knowledge_id, PromotionState.PROMOTED,
                                          reason=f"review approved by {reviewer}")
            self._publish("knowledge.promoted",
                          {"knowledge_id": rev.knowledge_id, "via": "review"})
            self._publish("brain.update_candidate", {"knowledge_id": rev.knowledge_id})
        else:  # REJECTED — archived, NEVER deleted (history preserved)
            self.mem.transition_knowledge(rev.knowledge_id, PromotionState.ARCHIVED,
                                          reason=f"review rejected by {reviewer}: {resolution}")
            self.mem.db.execute("UPDATE knowledge SET status='rejected' WHERE id=?",
                                (rev.knowledge_id,))
            self._publish("knowledge.rejected",
                          {"knowledge_id": rev.knowledge_id, "reason": resolution})
        self.mem.db.execute(
            "UPDATE knowledge_reviews SET status=?, reviewer=?, resolved_at=?,"
            " resolution=? WHERE id=?",
            (status.value, reviewer, self._now(), resolution, review_id),
        )
        self.mem.db.commit()
        return self._review(review_id)

    # ── queries ───────────────────────────────────────────────────────────
    def pending(self, limit: int = 50) -> list[Review]:
        rows = self.mem.db.execute(
            "SELECT * FROM knowledge_reviews WHERE status='pending' ORDER BY"
            " CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1"
            " WHEN 'medium' THEN 2 ELSE 3 END, created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row(r) for r in rows]

    def history(self, limit: int = 100) -> list[Review]:
        rows = self.mem.db.execute(
            "SELECT * FROM knowledge_reviews WHERE status!='pending'"
            " ORDER BY resolved_at DESC LIMIT ?", (limit,),
        ).fetchall()
        return [self._row(r) for r in rows]

    def evidence_for(self, review_id: int) -> dict:
        """Evidence Explorer — Knowledge → Pattern → Episodes → raw. Every
        conclusion is explainable."""
        rev = self._review(review_id)
        k = self.mem.get_knowledge(rev.knowledge_id)
        episodes = [self.mem.get_episode(eid) for eid in (k.source_episode_ids if k else [])]
        return {
            "review": rev,
            "knowledge": k,
            "episodes": [
                {"episode_id": e.episode_id, "intent": e.intent, "outcome": e.outcome,
                 "product": e.product, "quality_score": e.quality_score,
                 "created_at": e.created_at, "metadata": e.metadata}
                for e in episodes if e is not None
            ],
        }

    def counts(self) -> dict:
        pend = self.mem.db.execute(
            "SELECT COUNT(*) n FROM knowledge_reviews WHERE status='pending'").fetchone()["n"]
        appr = self.mem.db.execute(
            "SELECT COUNT(*) n FROM knowledge_reviews WHERE status='approved'").fetchone()["n"]
        rej = self.mem.db.execute(
            "SELECT COUNT(*) n FROM knowledge_reviews WHERE status='rejected'").fetchone()["n"]
        return {"pending": pend, "approved": appr, "rejected": rej}

    # ── row mappers ───────────────────────────────────────────────────────
    def _review(self, review_id: int) -> Review:
        r = self.mem.db.execute("SELECT * FROM knowledge_reviews WHERE id=?",
                                (review_id,)).fetchone()
        if r is None:
            raise KeyError(review_id)
        return self._row(r)

    @staticmethod
    def _row(r) -> Review:
        return Review(
            review_id=r["id"], knowledge_id=r["knowledge_id"],
            status=ReviewStatus(r["status"]), priority=ReviewPriority(r["priority"]),
            reason=r["reason"], confidence=r["confidence"], risk_level=r["risk_level"],
            scope=r["scope"], reviewer=r["reviewer"], created_at=r["created_at"],
            resolved_at=r["resolved_at"], resolution=r["resolution"],
        )


def format_review_for_telegram(evidence: dict) -> str:
    """Human review interface message (the /approve, /reject, /inspect commands
    are handled by the bot; this is the formatted card). Lightweight governance
    without a web UI."""
    rev: Review = evidence["review"]
    k = evidence["knowledge"]
    episodes = evidence["episodes"]
    products = {e["product"] for e in episodes if e["product"]}
    lines = [
        "🧠 Knowledge Review",
        "",
        f"Title: {k.value if k else '?'}",
        f"Priority: {rev.priority.value.upper()}",
        f"Confidence: {rev.confidence:.0%}",
        f"Evidence: {len(episodes)} episodes",
        f"Cross-product: {'YES' if len(products) > 1 else 'no'}",
        f"Reason: {rev.reason or '—'}",
        "",
        f"/approve_{rev.review_id}   /reject_{rev.review_id}   /inspect_{rev.review_id}",
    ]
    return "\n".join(lines)
