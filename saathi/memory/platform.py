"""Platform Memory — the generic, product-agnostic memory foundation (M2 Phase 1a).

Transforms the PIELTS application memory into SaathiAI platform memory without
breaking existing functionality (AP-01 Platform-First). The schema is generic —
``Episode``, not ``IELTSEpisode`` — and products attach their own data in
``metadata``:

    pielts     → {"student_id": ..., "skill": ..., "band_est": ...}
    hcg_pos    → {"table": 8, "menu": "Dal Bhat"}
    ai_studio  → {"video_id": ..., "renderer": "LTX-2"}

Beyond SES-003, two evidence fields (per M2 design review):
    source_episode_ids  — the Source Trace: every promoted knowledge item can
                          always answer "why do I believe this?"
    verification_count  — observed once → don't trust it; observed 200 times →
                          high confidence. Promotion becomes evidence-based.

The Promotion State Machine is defined here; the Promotion Engine (Phase 1b)
simply moves states:

    NEW → CANDIDATE → UNDER_REVIEW → PROMOTED → SUPERSEDED → ARCHIVED

Testable in isolation (AP-12): plain SQLite at any path, injected clock.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable


class PromotionState(str, Enum):
    NEW = "new"
    CANDIDATE = "candidate"
    UNDER_REVIEW = "under_review"
    PROMOTED = "promoted"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


# Legal transitions — the Promotion Engine may only move along these edges.
_TRANSITIONS: dict[PromotionState, set[PromotionState]] = {
    PromotionState.NEW: {PromotionState.CANDIDATE, PromotionState.ARCHIVED},
    PromotionState.CANDIDATE: {PromotionState.UNDER_REVIEW, PromotionState.ARCHIVED},
    PromotionState.UNDER_REVIEW: {PromotionState.PROMOTED, PromotionState.CANDIDATE,
                                  PromotionState.ARCHIVED},   # reject → back or archive
    PromotionState.PROMOTED: {PromotionState.SUPERSEDED},
    PromotionState.SUPERSEDED: {PromotionState.ARCHIVED},
    PromotionState.ARCHIVED: set(),                            # terminal
}


class MemoryScope(str, Enum):
    SESSION = "session"
    PRODUCT = "product"
    DEPARTMENT = "department"
    PLATFORM = "platform"
    GLOBAL = "global"


# Only these scopes may cross products (SES-003 cross-product firewall).
_CROSS_PRODUCT_SCOPES = {MemoryScope.PLATFORM, MemoryScope.GLOBAL}


class RetentionPolicy(str, Enum):
    SESSION = "session"                  # 7 days
    WORKFLOW = "workflow"                # 30 days
    STANDARD = "standard"                # 90 days
    SEMANTIC = "semantic"                # forever
    PLATFORM_WISDOM = "platform_wisdom"  # never delete (L6 — the constitution)


_RETENTION_SECONDS: dict[RetentionPolicy, float | None] = {
    RetentionPolicy.SESSION: 7 * 86400,
    RetentionPolicy.WORKFLOW: 30 * 86400,
    RetentionPolicy.STANDARD: 90 * 86400,
    RetentionPolicy.SEMANTIC: None,
    RetentionPolicy.PLATFORM_WISDOM: None,
}


def retention_expiry(policy: RetentionPolicy, now: float) -> float | None:
    ttl = _RETENTION_SECONDS[policy]
    return None if ttl is None else now + ttl


@dataclass
class Episode:
    episode_id: int
    agent: str
    department: str
    product: str | None
    user: str | None
    intent: str
    action: str
    result: str
    outcome: str                    # success | failure | partial
    quality_score: float
    confidence: float
    cost: float
    duration_ms: int
    scope: MemoryScope
    retention: RetentionPolicy
    created_at: float
    expires_at: float | None
    promotion_state: PromotionState
    promotion_reason: str
    summary: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Knowledge:
    knowledge_id: int
    key: str
    knowledge_type: str             # behavior | preference | performance | error | domain
    value: str
    scope: MemoryScope
    confidence: float
    quality_score: float
    source_episode_ids: list[int]   # Source Trace — "why do I believe this?"
    source_episode_count: int
    verification_count: int         # evidence-based trust
    cross_product_score: float
    promotion_state: PromotionState
    promotion_reason: str
    last_verified: float | None
    status: str                     # active | rejected | superseded
    created_at: float


_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    department TEXT NOT NULL,
    product TEXT,
    user TEXT,
    intent TEXT NOT NULL,
    action TEXT DEFAULT '',
    result TEXT DEFAULT '',
    outcome TEXT NOT NULL,
    quality_score REAL DEFAULT 0.0,
    confidence REAL DEFAULT 1.0,
    cost REAL DEFAULT 0.0,
    duration_ms INTEGER DEFAULT 0,
    scope TEXT NOT NULL DEFAULT 'product',
    retention TEXT NOT NULL DEFAULT 'standard',
    created_at REAL NOT NULL,
    expires_at REAL,
    promotion_state TEXT NOT NULL DEFAULT 'new',
    promotion_reason TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_ep_product ON episodes(product);
CREATE INDEX IF NOT EXISTS idx_ep_intent ON episodes(intent);
CREATE INDEX IF NOT EXISTS idx_ep_state ON episodes(promotion_state);
CREATE INDEX IF NOT EXISTS idx_ep_created ON episodes(created_at);

CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    knowledge_type TEXT NOT NULL,
    value TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'product',
    confidence REAL DEFAULT 0.5,
    quality_score REAL DEFAULT 0.0,
    source_episode_ids TEXT DEFAULT '[]',
    verification_count INTEGER DEFAULT 1,
    cross_product_score REAL DEFAULT 0.0,
    promotion_state TEXT NOT NULL DEFAULT 'new',
    promotion_reason TEXT DEFAULT '',
    last_verified REAL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_k_type ON knowledge(knowledge_type);
CREATE INDEX IF NOT EXISTS idx_k_state ON knowledge(promotion_state);
CREATE INDEX IF NOT EXISTS idx_k_confidence ON knowledge(confidence);
"""


class PlatformMemory:
    def __init__(self, db_path: "str | Path", now: Callable[[], float] = time.time):
        self.path = str(db_path)
        Path(str(db_path)).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()
        self._now = now

    # ── Episodes ──────────────────────────────────────────────────────────
    def record_episode(
        self, *, agent: str, department: str, product: str | None,
        intent: str, action: str = "", result: str = "", outcome: str = "success",
        quality_score: float = 0.0, user: str | None = None,
        confidence: float = 1.0, cost: float = 0.0, duration_ms: int = 0,
        scope: MemoryScope = MemoryScope.PRODUCT,
        retention: RetentionPolicy = RetentionPolicy.STANDARD,
        summary: str = "", metadata: dict | None = None,
    ) -> int:
        now = self._now()
        cur = self.db.execute(
            "INSERT INTO episodes (agent, department, product, user, intent, action,"
            " result, outcome, quality_score, confidence, cost, duration_ms, scope,"
            " retention, created_at, expires_at, summary, metadata)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (agent, department, product, user, intent, action, result, outcome,
             quality_score, confidence, cost, duration_ms, scope.value,
             retention.value, now, retention_expiry(retention, now), summary,
             json.dumps(metadata or {})),
        )
        self.db.commit()
        return cur.lastrowid

    def get_episode(self, episode_id: int) -> Episode | None:
        row = self.db.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()
        return self._episode(row) if row else None

    def episodes(self, product: str | None = None, intent: str | None = None,
                 promotion_state: PromotionState | None = None,
                 limit: int = 100) -> list[Episode]:
        q, params = "SELECT * FROM episodes WHERE 1=1", []
        if product is not None:
            q += " AND product=?"; params.append(product)
        if intent is not None:
            q += " AND intent=?"; params.append(intent)
        if promotion_state is not None:
            q += " AND promotion_state=?"; params.append(promotion_state.value)
        q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        return [self._episode(r) for r in self.db.execute(q, params).fetchall()]

    # ── PIELTS backward compatibility ─────────────────────────────────────
    def record_pielts_interaction(self, *, student_id: str, skill: str,
                                  input_text: str, response: str,
                                  band_est: float | None = None,
                                  **extra_metadata) -> int:
        """The old (student_id, skill, band_est) shape maps into metadata —
        PIELTS keeps working; the platform schema stays generic."""
        return self.record_episode(
            agent=f"{skill}_subagent", department="IELTS Tutor", product="pielts",
            user=student_id, intent=f"ielts_{skill}_practice",
            action=input_text[:500], result=response[:500], outcome="success",
            quality_score=(band_est / 9.0) if band_est is not None else 0.0,
            metadata={"student_id": student_id, "skill": skill,
                      "band_est": band_est, **extra_metadata},
        )

    # ── Knowledge (semantic) ──────────────────────────────────────────────
    def record_knowledge(
        self, *, key: str, knowledge_type: str, value: str, scope: MemoryScope,
        confidence: float = 0.5, quality_score: float = 0.0,
        source_episode_ids: list[int] | None = None,
        cross_product_score: float = 0.0,
    ) -> int:
        cur = self.db.execute(
            "INSERT INTO knowledge (key, knowledge_type, value, scope, confidence,"
            " quality_score, source_episode_ids, cross_product_score, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (key, knowledge_type, value, scope.value, confidence, quality_score,
             json.dumps(source_episode_ids or []), cross_product_score, self._now()),
        )
        self.db.commit()
        return cur.lastrowid

    def get_knowledge(self, knowledge_id: int) -> Knowledge | None:
        row = self.db.execute("SELECT * FROM knowledge WHERE id=?", (knowledge_id,)).fetchone()
        return self._knowledge(row) if row else None

    def verify_knowledge(self, knowledge_id: int, source_episode_id: int | None = None) -> None:
        """New evidence observed — evidence-based trust, not LLM vibes."""
        k = self.get_knowledge(knowledge_id)
        if k is None:
            raise KeyError(knowledge_id)
        ids = k.source_episode_ids
        if source_episode_id is not None and source_episode_id not in ids:
            ids = ids + [source_episode_id]
        self.db.execute(
            "UPDATE knowledge SET verification_count=verification_count+1,"
            " source_episode_ids=?, last_verified=? WHERE id=?",
            (json.dumps(ids), self._now(), knowledge_id),
        )
        self.db.commit()

    def transition_knowledge(self, knowledge_id: int, new_state: PromotionState,
                             reason: str = "") -> None:
        """The Promotion State Machine — the Promotion Engine only moves states."""
        k = self.get_knowledge(knowledge_id)
        if k is None:
            raise KeyError(knowledge_id)
        if new_state not in _TRANSITIONS[k.promotion_state]:
            raise ValueError(
                f"illegal transition {k.promotion_state.value} → {new_state.value}"
            )
        self.db.execute(
            "UPDATE knowledge SET promotion_state=?, promotion_reason=? WHERE id=?",
            (new_state.value, reason, knowledge_id),
        )
        self.db.commit()

    # ── Scope rules (deterministic promotion firewall) ────────────────────
    @staticmethod
    def may_cross_products(scope: MemoryScope) -> bool:
        return scope in _CROSS_PRODUCT_SCOPES

    # ── row mappers ───────────────────────────────────────────────────────
    @staticmethod
    def _episode(r: sqlite3.Row) -> Episode:
        return Episode(
            episode_id=r["id"], agent=r["agent"], department=r["department"],
            product=r["product"], user=r["user"], intent=r["intent"],
            action=r["action"], result=r["result"], outcome=r["outcome"],
            quality_score=r["quality_score"], confidence=r["confidence"],
            cost=r["cost"], duration_ms=r["duration_ms"],
            scope=MemoryScope(r["scope"]), retention=RetentionPolicy(r["retention"]),
            created_at=r["created_at"], expires_at=r["expires_at"],
            promotion_state=PromotionState(r["promotion_state"]),
            promotion_reason=r["promotion_reason"], summary=r["summary"],
            metadata=json.loads(r["metadata"] or "{}"),
        )

    @staticmethod
    def _knowledge(r: sqlite3.Row) -> Knowledge:
        ids = json.loads(r["source_episode_ids"] or "[]")
        return Knowledge(
            knowledge_id=r["id"], key=r["key"], knowledge_type=r["knowledge_type"],
            value=r["value"], scope=MemoryScope(r["scope"]),
            confidence=r["confidence"], quality_score=r["quality_score"],
            source_episode_ids=ids, source_episode_count=len(ids),
            verification_count=r["verification_count"],
            cross_product_score=r["cross_product_score"],
            promotion_state=PromotionState(r["promotion_state"]),
            promotion_reason=r["promotion_reason"],
            last_verified=r["last_verified"], status=r["status"],
            created_at=r["created_at"],
        )
