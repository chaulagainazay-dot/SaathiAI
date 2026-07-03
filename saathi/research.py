"""Research Department (M5 Phase 1) — the evidence source for all investment work.

Every downstream capability (Opportunity Discovery, Due Diligence, Simulation,
Risk, Recommendation, Portfolio, Learning, Mission Control) consumes the SAME
high-quality research produced here — build once, reuse everywhere (AP-01).

Seven specialized research agents each emit structured `Evidence` tagged with a
`ResearchCategory`. The flagship is the **Research Confidence Framework**: a
transparent weighted breakdown per category, plus missing-evidence,
contradiction, freshness, and independent-source metrics — so every
recommendation is explainable and auditable (AP-15 → AP-20).

Deterministic core (AP-17): the scoring, aggregation, and confidence math are
pure and testable. The *collectors* (what an agent talks to — an exchange API,
an on-chain indexer, an LLM summarizer) are injected callables; in tests they
are fakes, in production they are the AI-assisted / networked implementations.
No network, no clock, no LLM inside this module (AP-12).

Guardrails encoded here, per Ajay's direction:
  • Sentiment is NEVER a sole basis — a sentiment-only report is not actionable.
  • Technical COMPLEMENTS, never replaces, fundamentals.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


# ── Categories & weights (the Research Confidence Framework) ────────────────
class ResearchCategory(str, Enum):
    FUNDAMENTALS = "fundamentals"
    TECHNICAL = "technical"
    ONCHAIN = "onchain"
    SENTIMENT = "sentiment"
    TEAM_GITHUB = "team_github"
    RISK = "risk"
    # Cross-cutting context categories (informative, not weighted in confidence):
    MARKET = "market"
    NEWS = "news"


# The confidence weights. MUST sum to 1.0 over the weighted categories.
CONFIDENCE_WEIGHTS: dict[ResearchCategory, float] = {
    ResearchCategory.FUNDAMENTALS: 0.30,
    ResearchCategory.ONCHAIN: 0.20,
    ResearchCategory.TECHNICAL: 0.15,
    ResearchCategory.TEAM_GITHUB: 0.15,
    ResearchCategory.SENTIMENT: 0.10,
    ResearchCategory.RISK: 0.10,
}
assert abs(sum(CONFIDENCE_WEIGHTS.values()) - 1.0) < 1e-9, "confidence weights must sum to 1.0"


@dataclass
class Evidence:
    """One researched signal. `score` is 0..100 where higher = more favourable
    (for RISK, higher = safer). Direction is uniform so aggregation is honest."""
    category: ResearchCategory
    metric: str
    score: float                 # 0..100
    source: str                  # independent source id (exchange, indexer, repo…)
    collected_at: float          # unix seconds (injected clock upstream)
    note: str = ""

    def __post_init__(self) -> None:
        self.score = max(0.0, min(100.0, float(self.score)))


# ── Research agents ─────────────────────────────────────────────────────────
# Each agent normalizes a thin collector's raw signals into Evidence for its
# category. The collector is injected: (subject) -> list[(metric, score, source)].
Collector = Callable[[str], list[tuple[str, float, str]]]


@dataclass
class ResearchAgent:
    name: str
    category: ResearchCategory
    collect: Collector
    now: Callable[[], float] = time.time

    def research(self, subject: str) -> list[Evidence]:
        out: list[Evidence] = []
        for metric, score, source in self.collect(subject):
            out.append(Evidence(self.category, metric, score, source, self.now()))
        return out


# Factory helpers for the seven specialized agents. Each is just a category +
# an injected collector — the "intelligence" lives in the collector.
def market_intelligence(collect: Collector, now=time.time) -> ResearchAgent:
    return ResearchAgent("Market Intelligence", ResearchCategory.MARKET, collect, now)


def onchain_intelligence(collect: Collector, now=time.time) -> ResearchAgent:
    return ResearchAgent("On-Chain Intelligence", ResearchCategory.ONCHAIN, collect, now)


def project_intelligence(collect: Collector, now=time.time) -> ResearchAgent:
    return ResearchAgent("Project Intelligence", ResearchCategory.TEAM_GITHUB, collect, now)


def news_intelligence(collect: Collector, now=time.time) -> ResearchAgent:
    return ResearchAgent("News Intelligence", ResearchCategory.NEWS, collect, now)


def sentiment_intelligence(collect: Collector, now=time.time) -> ResearchAgent:
    return ResearchAgent("Sentiment Intelligence", ResearchCategory.SENTIMENT, collect, now)


def fundamental_intelligence(collect: Collector, now=time.time) -> ResearchAgent:
    return ResearchAgent("Fundamental Intelligence", ResearchCategory.FUNDAMENTALS, collect, now)


def technical_intelligence(collect: Collector, now=time.time) -> ResearchAgent:
    return ResearchAgent("Technical Intelligence", ResearchCategory.TECHNICAL, collect, now)


# ── Research Confidence Framework ───────────────────────────────────────────
@dataclass
class CategoryScore:
    category: ResearchCategory
    weight: float
    score: float                 # 0..100 weighted mean of the category's evidence
    evidence_count: int


@dataclass
class ResearchConfidence:
    subject: str
    breakdown: list[CategoryScore]
    overall: float               # 0..100, renormalized over categories present
    coverage: float              # 0..1, share of confidence weight with evidence
    missing_evidence: list[ResearchCategory]
    contradictions: list[str]
    source_count: int            # distinct independent sources
    stale_metrics: list[str]     # metrics older than the freshness horizon
    actionable: bool             # guardrails: enough coverage, not sentiment-only

    def render(self) -> str:
        lines = [f"🔬 Research Confidence — {self.subject}: {self.overall:.0f}/100 "
                 f"(coverage {self.coverage:.0%}, {self.source_count} sources)"]
        for c in self.breakdown:
            lines.append(f"  {c.category.value:<12} w{c.weight:.0%}  {c.score:5.1f}  "
                         f"({c.evidence_count} signals)")
        if self.missing_evidence:
            lines.append("  ⚠ missing: " + ", ".join(m.value for m in self.missing_evidence))
        if self.contradictions:
            lines.append("  ⚠ contradictions: " + "; ".join(self.contradictions))
        if self.stale_metrics:
            lines.append("  ⚠ stale: " + ", ".join(self.stale_metrics))
        lines.append(f"  → {'ACTIONABLE' if self.actionable else 'NOT actionable (insufficient / one-sided evidence)'}")
        return "\n".join(lines)


def _find_contradictions(evidence: list[Evidence], divergence: float = 40.0) -> list[str]:
    """Two independent sources reporting the same metric with scores that diverge
    strongly = a genuine contradiction that should lower confidence."""
    by_metric: dict[str, list[Evidence]] = {}
    for e in evidence:
        by_metric.setdefault(e.metric, []).append(e)
    out: list[str] = []
    for metric, items in by_metric.items():
        sources = {i.source for i in items}
        if len(sources) < 2:
            continue
        lo, hi = min(i.score for i in items), max(i.score for i in items)
        if hi - lo >= divergence:
            out.append(f"{metric}: sources disagree ({lo:.0f}↔{hi:.0f})")
    return out


def score_confidence(subject: str, evidence: list[Evidence], *,
                     now: float, freshness_horizon_s: float = 86_400.0) -> ResearchConfidence:
    """The flagship. Produce a transparent, weighted, auditable confidence score."""
    by_cat: dict[ResearchCategory, list[Evidence]] = {}
    for e in evidence:
        by_cat.setdefault(e.category, []).append(e)

    breakdown: list[CategoryScore] = []
    weighted_sum = 0.0
    present_weight = 0.0
    for cat, weight in CONFIDENCE_WEIGHTS.items():
        items = by_cat.get(cat, [])
        if items:
            cat_score = sum(i.score for i in items) / len(items)
            weighted_sum += weight * cat_score
            present_weight += weight
            breakdown.append(CategoryScore(cat, weight, round(cat_score, 1), len(items)))

    overall = round(weighted_sum / present_weight, 1) if present_weight else 0.0
    coverage = round(present_weight, 4)   # weights sum to 1.0, so this is a 0..1 share
    missing = [c for c in CONFIDENCE_WEIGHTS if c not in by_cat]
    contradictions = _find_contradictions(evidence)
    sources = {e.source for e in evidence}
    stale = sorted({e.metric for e in evidence if now - e.collected_at > freshness_horizon_s})

    # Guardrails: sentiment is never a sole basis; require real coverage and
    # at least one hard-evidence category (fundamentals or on-chain).
    present = set(by_cat)
    sentiment_only = present and present.issubset(
        {ResearchCategory.SENTIMENT, ResearchCategory.NEWS, ResearchCategory.MARKET})
    has_hard = bool(present & {ResearchCategory.FUNDAMENTALS, ResearchCategory.ONCHAIN})
    actionable = (coverage >= 0.5) and has_hard and not sentiment_only

    return ResearchConfidence(subject, breakdown, overall, coverage, missing,
                              contradictions, len(sources), stale, actionable)


# ── Research Department (orchestrator) ──────────────────────────────────────
@dataclass
class ResearchReport:
    subject: str
    evidence: list[Evidence]
    confidence: ResearchConfidence

    def render(self) -> str:
        return self.confidence.render()


class ResearchDepartment:
    """Runs the specialized agents over a subject, gathers Evidence, computes the
    confidence framework, publishes an event, and records an episode for the
    Learning Runtime (AP integration). All side-effects are injected (AP-12)."""

    def __init__(self, agents: list[ResearchAgent], *,
                 now: Callable[[], float] = time.time,
                 publish: Callable[[str, dict], object] | None = None,
                 record_episode: Callable[..., int] | None = None):
        self.agents = agents
        self.now = now
        if publish is None:
            from saathi.events import bus
            publish = bus.publish_sync
        if record_episode is None:
            from saathi.integration import ingest_episode as record_episode
        self._publish = publish
        self._episode = record_episode

    def research(self, subject: str) -> ResearchReport:
        evidence: list[Evidence] = []
        for agent in self.agents:
            evidence.extend(agent.research(subject))
        conf = score_confidence(subject, evidence, now=self.now())
        self._publish("research.completed", {
            "subject": subject, "overall": conf.overall, "coverage": conf.coverage,
            "sources": conf.source_count, "actionable": conf.actionable,
            "contradictions": len(conf.contradictions),
        })
        # Feed the Learning Runtime: a research pass is an episode.
        self._episode(
            agent="research_department", department="investment", product="research",
            intent="research_pass", action=f"researched {subject}",
            result=f"confidence {conf.overall:.0f}/100, coverage {conf.coverage:.0%}",
            outcome="success" if conf.actionable else "insufficient_evidence",
            quality_score=round(conf.overall / 100.0, 3),
            metadata={"subject": subject, "coverage": conf.coverage,
                      "missing": [m.value for m in conf.missing_evidence]})
        return ResearchReport(subject, evidence, conf)
