"""Learning Engine — how SaathiAI becomes better tomorrow (M2 Phase 3).

Memory remembers · the Promotion Engine generalizes · the Review Queue governs ·
the **Learning Engine changes future behavior**. Deterministic staged pipeline:

    Execution → Outcome Evaluation → Failure Analysis → Lesson Extraction
              → Capability Improvement → Learning Policy → explicit outputs

The single most important constraint (your design center): the Learning Engine
**never writes prompts directly. It proposes.** Every lesson produces explicit,
governed outputs (an improvement proposal, a knowledge candidate, a Brain.md
candidate, an ADR candidate, an engineering task) — never a silent mutation.

Stage 4 (Lesson Extraction) is the ONLY place an LLM belongs (AP-17); it is
injected, with an LLM-free deterministic default so the pipeline is fully
testable (AP-12). Executions are read from PlatformMemory episodes (the live
Execution Collector subscribes to Event Fabric; the persisted episodes are the
same data, deterministically queryable).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from saathi.memory.platform import PlatformMemory, Episode
from saathi.learning.failures import FailureCategory, classify_failure
from saathi.learning.registry import CapabilityImprovementRegistry


# ── Stage 2: Outcome Evaluation ───────────────────────────────────────────
@dataclass
class OutcomeScore:
    intent: str
    n: int
    success_rate: float
    avg_quality: float
    avg_cost: float
    avg_duration_ms: float


# ── Stage 4 output: STRUCTURED, never free-form ───────────────────────────
@dataclass
class Lesson:
    lesson: str
    cause: str
    recommendation: str
    affected_capabilities: list[str]
    confidence: float


LessonExtractor = Callable[[FailureCategory, list[Episode]], "Lesson | None"]


def deterministic_lesson_extractor(category: FailureCategory,
                                   episodes: list[Episode]) -> "Lesson | None":
    """LLM-free default: a structured lesson from a failure cluster's statistics."""
    if not episodes:
        return None
    n = len(episodes)
    caps = sorted({e.department for e in episodes} | {e.product for e in episodes if e.product})
    confidence = min(1.0, n / 5.0)   # more repeats → more confident it's systemic
    return Lesson(
        lesson=f"{n} failures categorized {category.value} in {caps}",
        cause=f"Recurring {category.value} failures",
        recommendation=f"Investigate and harden the {category.value} path for {caps}",
        affected_capabilities=caps,
        confidence=confidence,
    )


# ── Stage 6: Learning Policy — explicit outputs ───────────────────────────
class LearningOutput(str, Enum):
    IMPROVEMENT_PROPOSAL = "improvement_proposal"
    KNOWLEDGE_CANDIDATE = "knowledge_candidate"
    BRAIN_CANDIDATE = "brain_candidate"
    ADR_CANDIDATE = "adr_candidate"
    ENGINEERING_TASK = "engineering_task"


def route_lesson(category: FailureCategory, lesson: Lesson) -> list[LearningOutput]:
    """Deterministic policy: every lesson produces explicit outputs."""
    outputs = [LearningOutput.IMPROVEMENT_PROPOSAL]     # always propose an improvement
    # Infrastructure/network/external failures that recur → engineering task
    if category in (FailureCategory.INFRASTRUCTURE, FailureCategory.NETWORK,
                    FailureCategory.EXTERNAL_API) and lesson.confidence >= 0.6:
        outputs.append(LearningOutput.ENGINEERING_TASK)
    # Reasoning/prompt/model lessons → knowledge candidate (behavior change)
    if category in (FailureCategory.REASONING, FailureCategory.PROMPT, FailureCategory.MODEL):
        outputs.append(LearningOutput.KNOWLEDGE_CANDIDATE)
    # High-confidence systemic lessons → an architectural decision candidate
    if lesson.confidence >= 0.8:
        outputs.append(LearningOutput.ADR_CANDIDATE)
    return outputs


@dataclass
class LearningReport:
    executions_evaluated: int = 0
    failures_analyzed: int = 0
    lessons_extracted: int = 0
    improvements_proposed: int = 0
    outputs_routed: dict[str, int] = field(default_factory=dict)


class LearningEngine:
    def __init__(self, mem: PlatformMemory,
                 improvements: CapabilityImprovementRegistry,
                 extractor: LessonExtractor = deterministic_lesson_extractor,
                 publish: "Callable[[str, dict], None] | None" = None,
                 now: Callable[[], float] = time.time,
                 min_failures: int = 2):
        self.mem = mem
        self.improvements = improvements
        self.extractor = extractor
        self._publish_fn = publish
        self._now = now
        self.min_failures = min_failures

    def _publish(self, name: str, payload: dict) -> None:
        if self._publish_fn is not None:
            self._publish_fn(name, payload)

    # ── Stage 2: Outcome Evaluation ───────────────────────────────────────
    def evaluate_outcomes(self, product: str | None = None) -> dict[str, OutcomeScore]:
        episodes = self.mem.episodes(product=product, limit=5000)
        by_intent: dict[str, list[Episode]] = {}
        for e in episodes:
            by_intent.setdefault(e.intent, []).append(e)
        scores: dict[str, OutcomeScore] = {}
        for intent, eps in by_intent.items():
            n = len(eps)
            scores[intent] = OutcomeScore(
                intent=intent, n=n,
                success_rate=sum(1 for e in eps if e.outcome == "success") / n,
                avg_quality=sum(e.quality_score for e in eps) / n,
                avg_cost=sum(e.cost for e in eps) / n,
                avg_duration_ms=sum(e.duration_ms for e in eps) / n,
            )
        return scores

    # ── Stage 3: Failure Analysis ─────────────────────────────────────────
    def analyze_failures(self, product: str | None = None) -> dict[FailureCategory, list[Episode]]:
        failures = [e for e in self.mem.episodes(product=product, limit=5000)
                    if e.outcome in ("failure", "partial")]
        clusters: dict[FailureCategory, list[Episode]] = {}
        for e in failures:
            clusters.setdefault(classify_failure(e), []).append(e)
        return clusters

    # ── full loop ─────────────────────────────────────────────────────────
    def run(self, product: str | None = None) -> LearningReport:
        report = LearningReport()
        report.executions_evaluated = sum(
            s.n for s in self.evaluate_outcomes(product).values())

        for category, episodes in self.analyze_failures(product).items():
            report.failures_analyzed += len(episodes)
            if len(episodes) < self.min_failures:
                continue
            lesson = self.extractor(category, episodes)   # Stage 4 (injected)
            if lesson is None:
                continue
            report.lessons_extracted += 1
            self._publish("learning.lesson_extracted",
                          {"category": category.value, "lesson": lesson.lesson,
                           "confidence": lesson.confidence})

            outputs = route_lesson(category, lesson)      # Stage 6
            for cap in lesson.affected_capabilities:
                # Stage 5: Capability Improvement — PROPOSE, never mutate.
                self.improvements.propose(
                    capability=cap, improvement=lesson.recommendation,
                    evidence=f"{len(episodes)} {category.value} failures",
                    expected_benefit=f"Reduce {category.value} failures",
                    confidence=lesson.confidence)
                report.improvements_proposed += 1
            for out in outputs:
                report.outputs_routed[out.value] = report.outputs_routed.get(out.value, 0) + 1
                self._publish(f"learning.{out.value}",
                              {"category": category.value,
                               "capabilities": lesson.affected_capabilities,
                               "confidence": lesson.confidence})
        return report
