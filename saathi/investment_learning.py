"""Investment Learning Runtime (M5 Phase 7) — "how do we become a better investor?"

Specializes the M2 learning platform rather than reinventing it: it consumes
completed Trade Journals, derives evidence, and emits *proposals* into the
existing CapabilityImprovementRegistry — which flow through the M2 Promotion
Engine → Knowledge Graph → Publication → Executive Intelligence. Learning
proposes, never mutates (AP-18/AP-20): nothing is auto-applied.

Six deterministic stages:
    Trade Journal → Performance Analysis → Pattern Discovery → Strategy Eval
                  → Research Eval → Portfolio Eval → Improvement Proposals

Plus Regime Learning: every closed trade is tagged with market regime, so the
platform can learn "momentum works in bull markets but fails sideways" rather
than the flat "momentum has a 63% win rate".

Deterministic (AP-17); registry / clock / publisher / recorder injected (AP-12).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from saathi.trade_journal import (
    TradeJournal, TradeStatus, PerformanceAnalytics, PerformanceReport,
)

_RESEARCH_CATS = ("fundamentals", "technical", "onchain", "sentiment",
                  "team_github", "risk")
_SIGNAL_THRESHOLD = 60.0        # a research agent "signals positive" at/above this


@dataclass
class ResearchAccuracy:
    agent: str
    predictive_accuracy: float   # 0..1: signal direction agreed with outcome
    sample: int


@dataclass
class RegimeInsight:
    strategy: str
    regime: str
    win_rate: float
    sample: int

    def render(self) -> str:
        return f"{self.strategy} in {self.regime}: {self.win_rate:.0%} win ({self.sample})"


@dataclass
class LearningResult:
    performance: PerformanceReport
    strategy_scores: dict[str, PerformanceReport]
    research_accuracy: list[ResearchAccuracy]
    regime_insights: list[RegimeInsight]
    portfolio_insights: list[str]
    patterns: list[str]
    proposals: list[dict]        # {id, capability, improvement, confidence}

    def render(self) -> str:
        lines = ["🧠 Investment Learning", "  " + self.performance.render()]
        for ra in sorted(self.research_accuracy, key=lambda r: -r.predictive_accuracy):
            lines.append(f"  research {ra.agent}: {ra.predictive_accuracy:.0%} predictive")
        for p in self.proposals:
            lines.append(f"  💡 [{p['capability']}] {p['improvement']} "
                         f"(conf {p['confidence']:.0%})")
        return "\n".join(lines)


class InvestmentLearningRuntime:
    def __init__(self, improvement_registry, *, min_sample: int = 3,
                 now: Callable[[], float] = time.time,
                 publish: Callable[[str, dict], object] | None = None,
                 record_episode: Callable[..., int] | None = None):
        self.registry = improvement_registry      # CapabilityImprovementRegistry (M2)
        self.min_sample = min_sample
        self.now = now
        if publish is None:
            from saathi.events import bus
            publish = bus.publish_sync
        if record_episode is None:
            from saathi.integration import ingest_episode as record_episode
        self._publish = publish
        self._episode = record_episode

    # ── 1. Performance + 4. Strategy evaluation ────────────────────────────
    def _strategy_scores(self, closed: list[TradeJournal]) -> dict[str, PerformanceReport]:
        pa = PerformanceAnalytics()
        strategies = {j.strategy.value for j in closed}
        return {s: pa.analyze([j for j in closed if j.strategy.value == s])
                for s in strategies}

    # ── 3. Research evaluation (per-agent predictive accuracy) ─────────────
    def _research_accuracy(self, closed: list[TradeJournal]) -> list[ResearchAccuracy]:
        out = []
        for cat in _RESEARCH_CATS:
            correct = sum(1 for j in closed
                          if (getattr(j.research, cat) >= _SIGNAL_THRESHOLD) == j.is_win)
            out.append(ResearchAccuracy(cat, round(correct / len(closed), 3), len(closed)))
        return out

    # ── Regime learning ────────────────────────────────────────────────────
    def _regime_insights(self, closed: list[TradeJournal]) -> list[RegimeInsight]:
        groups: dict[tuple[str, str], list[TradeJournal]] = {}
        for j in closed:
            groups.setdefault((j.strategy.value, j.market.regime), []).append(j)
        out = []
        for (strat, regime), items in groups.items():
            if len(items) >= self.min_sample:
                wr = round(sum(1 for j in items if j.is_win) / len(items), 3)
                out.append(RegimeInsight(strat, regime, wr, len(items)))
        return out

    # ── 5. Portfolio evaluation ────────────────────────────────────────────
    def _portfolio_insights(self, closed: list[TradeJournal]) -> list[str]:
        insights = []
        for j in closed:
            delta = j.portfolio.health_after - j.portfolio.health_before
            if j.portfolio.health_after and abs(delta) >= 3:
                verb = "improved" if delta > 0 else "worsened"
                insights.append(f"{j.asset} {verb} portfolio health {delta:+.0f}")
        return insights

    # ── 2. Pattern discovery ───────────────────────────────────────────────
    def _patterns(self, closed: list[TradeJournal]) -> list[str]:
        patterns = []
        strong = [j for j in closed if j.research.fundamentals >= 80 and j.research.onchain >= 75]
        if len(strong) >= self.min_sample:
            wr = sum(1 for j in strong if j.is_win) / len(strong)
            patterns.append(f"Fundamentals>80 & on-chain>75 → {wr:.0%} win over {len(strong)} trades")
        sent_only = self._sentiment_only(closed)
        if len(sent_only) >= self.min_sample:
            wr = sum(1 for j in sent_only if j.is_win) / len(sent_only)
            patterns.append(f"Sentiment-only signals → {wr:.0%} win over {len(sent_only)} trades")
        return patterns

    @staticmethod
    def _sentiment_only(closed):
        return [j for j in closed if j.research.sentiment >= 70
                and j.research.fundamentals < 50 and j.research.onchain < 50]

    # ── 6. Improvement Engine → M2 proposals (never auto-applied) ──────────
    def _propose(self, closed, research_acc, strategy_scores) -> list[dict]:
        proposals = []
        n = len(closed)

        def submit(capability, improvement, evidence, confidence):
            iid = self.registry.propose(
                capability=capability, improvement=improvement, evidence=evidence,
                expected_benefit="better risk-adjusted returns", confidence=confidence)
            proposals.append({"id": iid, "capability": capability,
                              "improvement": improvement, "confidence": confidence})

        # research reweighting: best vs worst agent
        if n >= self.min_sample:
            ranked = sorted(research_acc, key=lambda r: r.predictive_accuracy, reverse=True)
            best, worst = ranked[0], ranked[-1]
            sep = best.predictive_accuracy - worst.predictive_accuracy
            if sep >= 0.2:
                conf = round(min(0.99, 0.6 + sep / 2 + n / (n + 30) * 0.2), 2)
                submit("Research Confidence Framework",
                       f"Increase {best.agent} weighting; decrease {worst.agent} weighting",
                       f"{n} trades: {best.agent} {best.predictive_accuracy:.0%} predictive "
                       f"vs {worst.agent} {worst.predictive_accuracy:.0%}", conf)

        # strategy with negative expectancy → propose reducing its weight
        for strat, rep in strategy_scores.items():
            if rep.trades >= self.min_sample and rep.expectancy_usd < 0:
                conf = round(min(0.99, 0.6 + rep.trades / (rep.trades + 20) * 0.3), 2)
                submit("Investment Pipeline",
                       f"Reduce confidence weighting for {strat} strategy",
                       f"{rep.trades} trades, expectancy ${rep.expectancy_usd:.0f}, "
                       f"win {rep.win_rate:.0%}", conf)

        # sentiment-only losing → propose avoiding
        sent_only = self._sentiment_only(closed)
        if len(sent_only) >= self.min_sample:
            wr = sum(1 for j in sent_only if j.is_win) / len(sent_only)
            if wr < 0.4:
                conf = round(min(0.99, 0.7 + len(sent_only) / (len(sent_only) + 15) * 0.3), 2)
                submit("Opportunity Intelligence", "Avoid sentiment-only opportunities",
                       f"{len(sent_only)} sentiment-only trades, {wr:.0%} win rate", conf)
        return proposals

    def learn(self, journals: list[TradeJournal]) -> LearningResult:
        closed = [j for j in journals if j.status is TradeStatus.CLOSED]
        perf = PerformanceAnalytics().analyze(closed)
        if not closed:
            return LearningResult(perf, {}, [], [], [], [], [])

        strategy_scores = self._strategy_scores(closed)
        research_acc = self._research_accuracy(closed)
        regime = self._regime_insights(closed)
        portfolio = self._portfolio_insights(closed)
        patterns = self._patterns(closed)
        proposals = self._propose(closed, research_acc, strategy_scores)

        self._publish("investment.learning_completed", {
            "trades": len(closed), "proposals": len(proposals),
            "win_rate": perf.win_rate, "best_strategy": perf.best_strategy})
        self._episode(
            agent="investment_learning", department="investment", product="learning",
            intent="investment_learning_pass",
            action=f"analyzed {len(closed)} completed trades",
            result=f"{len(proposals)} improvement proposals (awaiting promotion)",
            outcome="success", quality_score=round(perf.win_rate, 3),
            metadata={"proposals": [p["improvement"] for p in proposals],
                      "best_strategy": perf.best_strategy,
                      "regime_insights": [r.render() for r in regime]})
        return LearningResult(perf, strategy_scores, research_acc, regime,
                              portfolio, patterns, proposals)
