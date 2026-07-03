"""Memory Promotion Engine — deterministic staged pipeline (M2 Phase 1b).

Turns raw experience into promoted knowledge through independently testable
stages:

    Episode → Candidate Discovery → Intent Clustering → Pattern Extraction
            → Evidence Scoring → State Transition → Routing → Events

Every dependency is injected (AP-12): the extractor (an LLM-backed one can be
added later), the evidence scorer and contradiction finder (built by a parallel
workstream), the event publisher, and the clock. The defaults are fully
LLM-free and network-free, so the pipeline runs deterministically in tests.

The engine never writes ``promotion_state`` on knowledge directly — all state
changes go through ``PlatformMemory.transition_knowledge`` (the Promotion State
Machine); illegal jumps raise ``ValueError``. Conflicting knowledge is NEVER
silently replaced: both items remain, linked via reason + event.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from saathi.memory.platform import (
    PlatformMemory, Episode, Knowledge, PromotionState, MemoryScope,
)


# ── Stage 3 output: STRUCTURED, never free-form prose ─────────────────────
@dataclass
class PatternExtraction:
    pattern: str                 # concise statement of the learned pattern
    evidence: list[int]          # episode ids supporting it
    recommendation: str
    confidence: float            # 0..1 — extractor's own confidence


# Injectable signatures
Extractor = Callable[[str, list[Episode]], "PatternExtraction | None"]
Scorer = Callable[[list[Episode], float, int], float]
ContradictionFinder = Callable[[str, list[Knowledge]], list[Knowledge]]
KnowledgeTypeResolver = Callable[[str, PatternExtraction], str]


def deterministic_extractor(intent: str, episodes: list[Episode]) -> PatternExtraction | None:
    """Default LLM-free extractor: pattern statement from outcome statistics."""
    if len(episodes) < 2:
        return None
    n = len(episodes)
    successes = sum(1 for e in episodes if e.outcome == "success")
    success_rate = successes / n
    pattern = f"Intent '{intent}': {n} episodes, {success_rate:.0%} success"
    if success_rate >= 0.5:
        recommendation = f"Continue current approach for '{intent}'"
        confidence = success_rate
    else:
        recommendation = f"Revise approach for '{intent}' — majority failing"
        confidence = 1.0 - success_rate
    return PatternExtraction(
        pattern=pattern,
        evidence=[e.episode_id for e in episodes],
        recommendation=recommendation,
        confidence=confidence,
    )


def default_scorer(episodes: list[Episode], llm_confidence: float,
                   n_contradictions: int) -> float:
    """The real Evidence Scorer (Stage 4): deterministic metrics blended with
    the extractor's confidence. Combines verification volume, source diversity,
    time consistency, cross-product reusability, and contradiction risk."""
    from saathi.memory.evidence import score_evidence
    return score_evidence(episodes, llm_confidence, n_contradictions).overall


def default_contradiction_finder(candidate_value: str,
                                 existing: list[Knowledge]) -> list[Knowledge]:
    """The real Contradiction Detector (Stage 4): flags conflicting promoted
    knowledge for review instead of silently overwriting it."""
    from saathi.memory.evidence import find_contradictions
    return find_contradictions(candidate_value, existing)


@dataclass
class PromotionReport:
    clusters_found: int = 0
    patterns_extracted: int = 0
    candidates_created: int = 0
    auto_promoted: int = 0
    sent_to_review: int = 0
    conflicts_flagged: int = 0
    skipped_low_confidence: int = 0


class PromotionEngine:
    def __init__(self, mem: PlatformMemory,
                 extractor: Extractor = deterministic_extractor,
                 scorer: Scorer = default_scorer,
                 contradiction_finder: ContradictionFinder = default_contradiction_finder,
                 publish: "Callable[[str, dict], None] | None" = None,
                 now: Callable[[], float] = time.time,
                 min_age_days: float = 3.0,
                 min_cluster_size: int = 2,
                 min_pattern_confidence: float = 0.5,
                 auto_approve_threshold: float = 0.85,
                 strategic_types: frozenset = frozenset(
                     {"business", "finance", "architecture", "strategy"}),
                 knowledge_type_resolver: KnowledgeTypeResolver = lambda intent, p: "behavior"):
        self.mem = mem
        self.extractor = extractor
        self.scorer = scorer
        self.contradiction_finder = contradiction_finder
        self._publish = publish
        self.now = now
        self.min_age_days = min_age_days
        self.min_cluster_size = min_cluster_size
        self.min_pattern_confidence = min_pattern_confidence
        self.auto_approve_threshold = auto_approve_threshold
        self.strategic_types = strategic_types
        self.knowledge_type_resolver = knowledge_type_resolver

    # ── events ────────────────────────────────────────────────────────────
    def publish(self, event: str, payload: dict) -> None:
        if self._publish is not None:
            self._publish(event, payload)

    # ── Stage 1+2: Candidate Discovery + Intent Clustering ────────────────
    def discover(self) -> dict[str, list[Episode]]:
        """Aged NEW episodes, grouped by normalized intent. Deterministic."""
        cutoff = self.now() - self.min_age_days * 86400
        episodes = self.mem.episodes(promotion_state=PromotionState.NEW, limit=1000)
        clusters: dict[str, list[Episode]] = {}
        for ep in episodes:
            if ep.created_at > cutoff:
                continue
            clusters.setdefault(ep.intent.lower().strip(), []).append(ep)
        return {intent: eps for intent, eps in clusters.items()
                if len(eps) >= self.min_cluster_size}

    # ── helpers ───────────────────────────────────────────────────────────
    def _promoted_knowledge(self) -> list[Knowledge]:
        rows = self.mem.db.execute(
            "SELECT id FROM knowledge WHERE promotion_state='promoted'"
        ).fetchall()
        return [self.mem.get_knowledge(r["id"]) for r in rows]

    def _unique_key(self, intent: str) -> str:
        base = f"pattern::{intent}"
        key, suffix = base, 2
        while self.mem.db.execute(
                "SELECT 1 FROM knowledge WHERE key=?", (key,)).fetchone():
            key = f"{base}::{suffix}"
            suffix += 1
        return key

    def _consume_episodes(self, episodes: list[Episode]) -> None:
        ids = [e.episode_id for e in episodes]
        marks = ",".join("?" * len(ids))
        self.mem.db.execute(
            f"UPDATE episodes SET promotion_state='candidate' WHERE id IN ({marks})", ids)
        self.mem.db.commit()

    # ── Stages 3–7 per cluster; full pipeline ─────────────────────────────
    def run(self) -> PromotionReport:
        report = PromotionReport()
        clusters = self.discover()
        report.clusters_found = len(clusters)

        for intent, episodes in clusters.items():
            # Stage 3 — Pattern Extraction
            pattern = self.extractor(intent, episodes)
            if pattern is None or pattern.confidence < self.min_pattern_confidence:
                report.skipped_low_confidence += 1
                continue
            report.patterns_extracted += 1

            # Stage 4 — Evidence Scoring
            contradictions = self.contradiction_finder(
                pattern.pattern, self._promoted_knowledge())
            overall = self.scorer(episodes, pattern.confidence, len(contradictions))

            # Stage 5 — Create knowledge + NEW→CANDIDATE via the state machine
            knowledge_type = self.knowledge_type_resolver(intent, pattern)
            products = {e.product for e in episodes}
            scope = (MemoryScope.PRODUCT if len(products) == 1
                     else MemoryScope.PLATFORM)
            key = self._unique_key(intent)
            kid = self.mem.record_knowledge(
                key=key, knowledge_type=knowledge_type, value=pattern.pattern,
                scope=scope, confidence=pattern.confidence, quality_score=overall,
                source_episode_ids=pattern.evidence,
            )
            self.mem.transition_knowledge(
                kid, PromotionState.CANDIDATE,
                reason=f"{len(episodes)} similar episodes, score={overall:.2f}")
            report.candidates_created += 1

            # Stage 6 — Routing
            if contradictions:
                conflict_ids = [k.knowledge_id for k in contradictions]
                self.mem.transition_knowledge(
                    kid, PromotionState.UNDER_REVIEW,
                    reason=f"conflict with knowledge ids {conflict_ids}")
                self.publish("knowledge.conflict_detected",
                             {"new_id": kid, "conflicts_with": conflict_ids})
                report.conflicts_flagged += 1
            elif knowledge_type in self.strategic_types:
                self.mem.transition_knowledge(
                    kid, PromotionState.UNDER_REVIEW,
                    reason="strategic — requires human approval")
                self.publish("knowledge.review_requested",
                             {"knowledge_id": kid, "key": key})
                report.sent_to_review += 1
            elif overall >= self.auto_approve_threshold:
                self.mem.transition_knowledge(
                    kid, PromotionState.UNDER_REVIEW,
                    reason=f"auto-approval, score={overall:.2f}")
                self.mem.transition_knowledge(
                    kid, PromotionState.PROMOTED,
                    reason=f"auto-promoted, score={overall:.2f} >= "
                           f"{self.auto_approve_threshold:.2f}")
                self.publish("knowledge.promoted",
                             {"knowledge_id": kid, "key": key,
                              "value": pattern.pattern, "score": overall})
                self.publish("brain.update_candidate",
                             {"knowledge_id": kid, "key": key})
                report.auto_promoted += 1
            else:
                self.publish("knowledge.candidate_created",
                             {"knowledge_id": kid, "key": key, "score": overall})

            # Stage 7 — mark source episodes consumed (idempotency)
            self._consume_episodes(episodes)

        return report
