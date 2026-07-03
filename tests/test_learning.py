"""Learning Engine tests (M2 Phase 3) — AP-12.

Deterministic pipeline: outcome evaluation, failure classification, lesson
extraction (injected), improvement PROPOSALS (never mutations), policy routing,
Capability Improvement Registry, and the Experiment Registry (A/B). No LLM,
no network.
"""
import pytest

from saathi.memory.platform import PlatformMemory, MemoryScope, RetentionPolicy
from saathi.learning import (
    LearningEngine, FailureCategory, classify_failure,
    CapabilityImprovementRegistry, ImprovementStatus,
    route_lesson, Lesson, LearningOutput, deterministic_lesson_extractor,
)
from saathi.memory.platform import Episode, PromotionState

NOW = 4_000_000.0


@pytest.fixture
def mem(tmp_path):
    return PlatformMemory(str(tmp_path / "m.db"), now=lambda: NOW)


@pytest.fixture
def reg(tmp_path):
    return CapabilityImprovementRegistry(str(tmp_path / "imp.db"), now=lambda: NOW)


def _fail(mem, intent, result, product="ai_studio", n=1):
    for _ in range(n):
        mem.record_episode(agent="a", department="Studio", product=product,
                           intent=intent, action="", result=result,
                           outcome="failure", quality_score=0.0)


# ── Stage 3: failure classification ───────────────────────────────────────
def test_classify_failure_categories():
    def ep(result, meta=None):
        return Episode(1, "a", "d", "p", None, "x", "", result, "failure", 0.0, 1.0,
                       0.0, 0, MemoryScope.PRODUCT, RetentionPolicy.STANDARD, NOW, None,
                       PromotionState.NEW, "", "", meta or {})
    assert classify_failure(ep("connection timed out")) is FailureCategory.NETWORK
    assert classify_failure(ep("HTTP 429 rate limit")) is FailureCategory.EXTERNAL_API
    assert classify_failure(ep("out of memory on GPU")) is FailureCategory.INFRASTRUCTURE
    assert classify_failure(ep("governance_denied")) is FailureCategory.HUMAN_APPROVAL
    assert classify_failure(ep("all providers failed")) is FailureCategory.MODEL
    assert classify_failure(ep("something odd")) is FailureCategory.UNKNOWN
    assert classify_failure(ep("", {"error": "connection timeout"})) is FailureCategory.NETWORK


# ── Stage 2: outcome evaluation ───────────────────────────────────────────
def test_outcome_evaluation(mem, reg):
    mem.record_episode(agent="a", department="d", product="pielts", intent="score",
                       action="", result="", outcome="success", quality_score=0.9, cost=0.01)
    mem.record_episode(agent="a", department="d", product="pielts", intent="score",
                       action="", result="", outcome="failure", quality_score=0.0, cost=0.02)
    eng = LearningEngine(mem, reg, now=lambda: NOW)
    scores = eng.evaluate_outcomes(product="pielts")
    s = scores["score"]
    assert s.n == 2 and s.success_rate == 0.5
    assert round(s.avg_cost, 3) == 0.015


# ── Stage 5+6: proposals + routing ────────────────────────────────────────
def test_run_proposes_improvements_never_mutates(mem, reg):
    _fail(mem, "render_scene", "GPU out of memory", n=3)
    events = []
    eng = LearningEngine(mem, reg, publish=lambda n, p: events.append(n), now=lambda: NOW)
    report = eng.run()
    assert report.lessons_extracted == 1
    assert report.improvements_proposed >= 1
    # improvement is a PROPOSAL, not an applied change
    props = reg.by_capability("Studio")
    assert props and props[0].status is ImprovementStatus.PROPOSED
    assert "learning.lesson_extracted" in events
    assert "learning.improvement_proposal" in events


def test_route_lesson_produces_explicit_outputs():
    lesson = Lesson("l", "c", "r", ["Studio"], confidence=0.9)
    outs = route_lesson(FailureCategory.INFRASTRUCTURE, lesson)
    assert LearningOutput.IMPROVEMENT_PROPOSAL in outs
    assert LearningOutput.ENGINEERING_TASK in outs      # infra + high confidence
    assert LearningOutput.ADR_CANDIDATE in outs         # confidence >= 0.8

    reasoning = route_lesson(FailureCategory.REASONING, Lesson("l", "c", "r", ["x"], 0.5))
    assert LearningOutput.KNOWLEDGE_CANDIDATE in reasoning
    assert LearningOutput.ADR_CANDIDATE not in reasoning  # low confidence


def test_low_failure_count_no_lesson(mem, reg):
    _fail(mem, "rare_fail", "network timeout", n=1)      # below min_failures
    report = LearningEngine(mem, reg, now=lambda: NOW).run()
    assert report.lessons_extracted == 0


def test_deterministic_extractor_is_structured(mem, reg):
    _fail(mem, "x", "network timeout", product="pielts", n=4)
    fails = [e for e in mem.episodes(product="pielts")]
    lesson = deterministic_lesson_extractor(FailureCategory.NETWORK, fails)
    assert isinstance(lesson, Lesson)
    assert lesson.affected_capabilities                  # captures department/product
    assert 0.0 <= lesson.confidence <= 1.0


# ── Capability Improvement Registry ───────────────────────────────────────
def test_improvement_lifecycle(reg):
    iid = reg.propose(capability="SEO Engine", improvement="Use llms.txt validation",
                      evidence="28 audits", expected_benefit="+cite rate", confidence=0.9)
    assert reg.get(iid).status is ImprovementStatus.PROPOSED
    reg.approve(iid)
    reg.implement(iid)
    assert reg.get(iid).status is ImprovementStatus.IMPLEMENTED
    assert reg.implemented_for("SEO Engine")             # organizational-learning query


# ── Experiment Registry (A/B) ─────────────────────────────────────────────
def test_experiment_picks_winner(reg):
    eid = reg.start_experiment(capability="Studio", control="LTX-2", variant="Wan",
                               higher_is_better=True)
    exp = reg.conclude_experiment(eid, control_metric=0.70, variant_metric=0.82)
    assert exp.winner == "variant"                        # higher retention wins

    eid2 = reg.start_experiment(capability="Router", control="A", variant="B",
                                higher_is_better=False)   # lower latency is better
    exp2 = reg.conclude_experiment(eid2, control_metric=120, variant_metric=90)
    assert exp2.winner == "variant"
