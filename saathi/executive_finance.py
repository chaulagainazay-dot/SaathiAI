"""Executive Intelligence — Financial Integration (M5 Phase 9, final M5 engineering).

Executive Intelligence stays the single synthesizing brain; Financial Mission
Control stays a finance department. This module lets the brain *consume* the
finance department's dashboard (no recomputation, no duplicated logic) and folds
it into the CEO morning briefing.

Adds two things:
  • CrossDepartmentPriorityEngine — normalizes recommendations from EVERY
    department (AI Studio, Discovery, Cafeteria, Travel, Investment, Learning,
    Storage) into ONE deterministic ranked queue, so a low-value *urgent* task
    can't displace a high-value strategic one.
  • CEO Question Framework — guarantees the briefing answers the eight questions
    that make it a true CEO cockpit, each sourced from an existing subsystem.

Deterministic (AP-17); dashboard + yesterday summary passed in (AP-12).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from saathi.financial_mission_control import FinancialDashboard, DREAM_TARGET


# ── Cross-Department Priority Engine ────────────────────────────────────────
@dataclass
class DepartmentRecommendation:
    title: str
    department: str
    why: str = ""
    estimated_value_usd: float = 0.0
    confidence: float = 0.5          # 0..1
    urgency: float = 0.5             # 0..1 (bounded influence — see priority_score)
    risk: float = 0.3                # 0..1
    goal_alignment: float = 0.5      # 0..1
    estimated_time_hours: float = 1.0
    requires_approval: bool = False

    @property
    def priority_score(self) -> float:
        """One deterministic score across departments. Value, confidence, and
        (1-risk) dominate; goal alignment swings 40%; urgency only 20% — so an
        urgent low-value task cannot outrank a strategic high-value one."""
        value = max(0.0, self.estimated_value_usd)
        return round(value * self.confidence * (1.0 - self.risk)
                     * (0.6 + 0.4 * self.goal_alignment)
                     * (0.8 + 0.2 * self.urgency), 2)


class CrossDepartmentPriorityEngine:
    def __init__(self) -> None:
        self._recs: list[DepartmentRecommendation] = []

    def add(self, rec: DepartmentRecommendation) -> None:
        self._recs.append(rec)

    def add_many(self, recs: list[DepartmentRecommendation]) -> None:
        self._recs.extend(recs)

    def ranked(self) -> list[DepartmentRecommendation]:
        return sorted(self._recs, key=lambda r: r.priority_score, reverse=True)

    def top(self, n: int = 5) -> list[DepartmentRecommendation]:
        return self.ranked()[:n]

    def by_department(self, department: str) -> list[DepartmentRecommendation]:
        return [r for r in self._recs if r.department == department]

    def pending_approvals(self) -> list[DepartmentRecommendation]:
        return [r for r in self._recs if r.requires_approval]


# ── Yesterday summary (from execution/revenue subsystems) ───────────────────
@dataclass
class YesterdaySummary:
    completed: int = 0
    delayed: int = 0
    blocked: int = 0
    made_money: list[str] = field(default_factory=list)   # "AI Studio +$420"
    lost_money: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


# ── CEO briefing (the cockpit) ──────────────────────────────────────────────
_CEO_QUESTIONS = [
    "What happened yesterday?",
    "What should I do today?",
    "What is blocking progress?",
    "What made money yesterday?",
    "What lost money yesterday?",
    "What did SaathiAI learn?",
    "Which approvals are waiting for me?",
    f"Am I getting closer to ${DREAM_TARGET:,.2f}?",
]


@dataclass
class CEOBriefing:
    priority_score: int
    dream_progress_pct: float
    dream_delta_pct: float
    financial_highlights: list[str]
    top_actions: list[DepartmentRecommendation]
    risks: list[str]
    learning: list[str]
    answers: dict[str, str]

    def render(self, name: str = "Ajay") -> str:
        L = [f"Good morning {name}.", "",
             f"Today's Priority Score: {self.priority_score}/100",
             f"🎯 Dream Progress: {self.dream_progress_pct:.2f}% ({self.dream_delta_pct:+.2f}% vs yesterday)",
             ""]
        if self.financial_highlights:
            L.append("💰 Financial Highlights")
            L += [f"• {h}" for h in self.financial_highlights]
            L.append("")
        L.append("🔥 Highest-Impact Actions")
        for i, r in enumerate(self.top_actions, 1):
            tag = " [approval]" if r.requires_approval else ""
            L.append(f"{i}. {r.title} — {r.department}{tag}")
        if self.risks:
            L += ["", "⚠ Risks"] + [f"• {r}" for r in self.risks]
        if self.learning:
            L += ["", "📈 Learning"] + [f"• {l}" for l in self.learning]
        return "\n".join(L)

    def render_cockpit(self, name: str = "Ajay") -> str:
        """The eight-question CEO cockpit — each answer from a real subsystem."""
        lines = [f"CEO Cockpit — {name}", ""]
        for q in _CEO_QUESTIONS:
            lines.append(f"❓ {q}")
            lines.append(f"   {self.answers[q]}")
        return "\n".join(lines)


class ExecutiveFinanceBriefer:
    """Synthesizes the CEO briefing by CONSUMING Financial Mission Control's
    dashboard and the cross-department queue. It computes no finance numbers."""

    def __init__(self, *, publish: Callable[[str, dict], object] | None = None):
        if publish is None:
            from saathi.events import bus
            publish = bus.publish_sync
        self._publish = publish

    def _financial_highlights(self, d: FinancialDashboard) -> list[str]:
        hl = [f"Portfolio Health: {d.portfolio_health:.0f}/100"]
        if d.dream_contributions_pct:
            biz, pct = max(d.dream_contributions_pct.items(), key=lambda x: x[1])
            hl.append(f"{biz} contributed {pct:.0%} of growth")
        if d.funnel.awaiting_approval:
            hl.append(f"{d.funnel.awaiting_approval} investment(s) awaiting approval")
        if d.strategy_stars:
            strat = max(d.strategy_stars.items(), key=lambda x: x[1])[0]
            hl.append(f"{strat.replace('_', ' ').title()} strategy remains strongest")
        if d.research_accuracy:
            agent, acc = max(d.research_accuracy.items(), key=lambda x: x[1])
            hl.append(f"{agent.title()} research accuracy: {acc:.0%}")
        return hl

    def build(self, *, priority: CrossDepartmentPriorityEngine,
              dashboard: FinancialDashboard, yesterday: YesterdaySummary,
              dream_progress_pct: float, dream_delta_pct: float,
              top_n: int = 5, name: str = "Ajay") -> CEOBriefing:
        top = priority.top(top_n)
        priority_score = round(sum(min(100, r.priority_score / 10) for r in top) / len(top)) if top else 0

        highlights = self._financial_highlights(dashboard)
        risks = list(dashboard.rebalance)
        if dashboard.knowledge.contradictions:
            risks.append(f"{dashboard.knowledge.contradictions} knowledge contradiction(s) awaiting review")
        risks += yesterday.blockers

        learning = []
        if dashboard.knowledge.proposals_awaiting:
            learning.append(f"{dashboard.knowledge.proposals_awaiting} finance improvement(s) proposed")
        if dashboard.knowledge.experiments_running:
            learning.append(f"{dashboard.knowledge.experiments_running} experiment(s) running")

        approvals = priority.pending_approvals()
        answers = {
            _CEO_QUESTIONS[0]: (f"{yesterday.completed} done, {yesterday.delayed} delayed, "
                                f"{yesterday.blocked} blocked"),
            _CEO_QUESTIONS[1]: "; ".join(f"{r.title}" for r in top) or "no ranked actions",
            _CEO_QUESTIONS[2]: "; ".join(yesterday.blockers) or "nothing blocking",
            _CEO_QUESTIONS[3]: "; ".join(yesterday.made_money) or "no gains recorded",
            _CEO_QUESTIONS[4]: "; ".join(yesterday.lost_money) or "no losses recorded",
            _CEO_QUESTIONS[5]: (f"{dashboard.knowledge.proposals_awaiting} proposals, "
                                f"{dashboard.knowledge.knowledge_promoted} promoted"),
            _CEO_QUESTIONS[6]: (f"{len(approvals)} action approval(s) + "
                                f"{dashboard.funnel.awaiting_approval} investment(s)"),
            _CEO_QUESTIONS[7]: (f"{dream_progress_pct:.2f}% of the dream "
                                f"({dream_delta_pct:+.2f}% vs yesterday)"),
        }

        self._publish("executive.financial_briefing", {
            "priority_score": priority_score, "actions": len(top),
            "pending_approvals": len(approvals) + dashboard.funnel.awaiting_approval,
            "dream_progress_pct": dream_progress_pct})
        return CEOBriefing(priority_score, dream_progress_pct, dream_delta_pct,
                           highlights, top, risks, learning, answers)
