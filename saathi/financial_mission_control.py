"""Financial Mission Control (M5 Phase 8) — the consumer, not a producer.

The presentation & orchestration layer for everything M5 built. It performs NO
analysis of its own — it aggregates the outputs of Portfolio Intelligence, the
Investment Pipeline, the Research Department, the Trade Journal, the Investment
Learning Runtime, the Revenue Engine, and Executive Intelligence into one
morning briefing. Formatting only; the numbers come from the engines.

Sections: Investment Overview · Opportunity Pipeline · Research Intelligence ·
Strategy Performance · Portfolio Health · Learning & Knowledge · Dream
Contribution · CEO Action List. Plus a Capital Allocation Timeline — the
historical map of "where every dollar produced the greatest long-term value",
across financial markets AND businesses.

Deterministic (AP-17); all data passed in from the engines; publisher injected
(AP-12). No engine is called here — Mission Control cannot bypass governance
because it never executes anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from saathi.portfolio import HealthReport, AllocationBreakdown, PortfolioRiskReport, RebalanceAction
from saathi.trade_journal import PerformanceReport
from saathi.investment_learning import LearningResult

DREAM_TARGET = 7_938_838.98


# ── Input funnel (from the pipeline; Mission Control only displays it) ───────
@dataclass
class PipelineFunnel:
    scanned: int = 0
    qualified: int = 0
    researched: int = 0
    dd_passed: int = 0
    awaiting_approval: int = 0
    executed_today: int = 0


@dataclass
class KnowledgeStats:
    proposals_awaiting: int = 0
    knowledge_promoted: int = 0
    contradictions: int = 0
    experiments_running: int = 0


# ── Capital Allocation Timeline (historical map of capital decisions) ───────
@dataclass
class AllocationEvent:
    period: str                       # "Jan", "2026-Q1", …
    label: str                        # "YouTube Marketing", "Kitchen Upgrade"
    amount_usd: float                 # realized outcome, signed (+gain / −loss)


class CapitalAllocationTimeline:
    def __init__(self, events: list[AllocationEvent] | None = None):
        self.events = list(events or [])

    def add(self, event: AllocationEvent) -> None:
        self.events.append(event)

    def best(self) -> AllocationEvent | None:
        return max(self.events, key=lambda e: e.amount_usd) if self.events else None

    def worst(self) -> AllocationEvent | None:
        return min(self.events, key=lambda e: e.amount_usd) if self.events else None

    def net_usd(self) -> float:
        return round(sum(e.amount_usd for e in self.events), 2)

    def render(self) -> str:
        lines = ["🗺️  Capital Allocation Timeline"]
        for e in self.events:
            lines.append(f"  {e.period:<8} {e.label:<24} {e.amount_usd:+,.0f}")
        if self.events:
            b, w = self.best(), self.worst()
            lines.append(f"  → best: {b.label} ({b.amount_usd:+,.0f}); "
                         f"worst: {w.label} ({w.amount_usd:+,.0f}); net {self.net_usd():+,.0f}")
        return "\n".join(lines)


@dataclass
class FinancialDashboard:
    # 1. Investment overview
    portfolio_health: float
    portfolio_value_usd: float
    cash_usd: float
    todays_change_pct: float
    risk_level: str
    regime: str
    # 2. pipeline funnel
    funnel: PipelineFunnel
    # 3. research accuracy (agent → predictive accuracy)
    research_accuracy: dict[str, float]
    # 4. strategy performance (strategy → stars 0..5)
    strategy_stars: dict[str, int]
    # 5. portfolio health detail
    diversification: float
    concentration: float
    liquidity: float
    cash_runway_months: float
    rebalance: list[str]
    # 6. learning & knowledge
    knowledge: KnowledgeStats
    # 7. dream contribution (business → % of contributions)
    dream_target: float
    dream_progress_pct: float
    dream_contributions_pct: dict[str, float]
    # 8. CEO action list (from Executive Intelligence)
    actions: list[dict]
    timeline: CapitalAllocationTimeline | None = None

    def render(self) -> str:
        L = ["💰 FINANCIAL MISSION CONTROL", ""]
        L.append(f"📈 Overview — Health {self.portfolio_health:.0f}/100 · "
                 f"Value ${self.portfolio_value_usd:,.0f} · Cash ${self.cash_usd:,.0f} · "
                 f"Today {self.todays_change_pct:+.1f}% · Risk {self.risk_level} · "
                 f"Regime {self.regime}")
        f = self.funnel
        L.append(f"🔎 Pipeline — scanned {f.scanned} · qualified {f.qualified} · "
                 f"researched {f.researched} · DD passed {f.dd_passed} · "
                 f"awaiting approval {f.awaiting_approval} · executed today {f.executed_today}")
        if self.research_accuracy:
            ra = " · ".join(f"{k} {v:.0%}" for k, v in
                            sorted(self.research_accuracy.items(), key=lambda x: -x[1]))
            L.append("🧪 Research accuracy — " + ra)
        if self.strategy_stars:
            ss = " · ".join(f"{k} {'★' * v}{'☆' * (5 - v)}" for k, v in self.strategy_stars.items())
            L.append("⚖️  Strategies — " + ss)
        L.append(f"🩺 Portfolio — diversification {self.diversification:.0f} · "
                 f"concentration {self.concentration:.0%} · liquidity {self.liquidity:.0%} · "
                 f"cash runway {self.cash_runway_months:.0f}mo")
        if self.rebalance:
            L.append("   rebalance: " + "; ".join(self.rebalance))
        k = self.knowledge
        L.append(f"🧠 Learning — {k.proposals_awaiting} proposals awaiting · "
                 f"{k.knowledge_promoted} promoted · {k.contradictions} contradictions · "
                 f"{k.experiments_running} experiments")
        L.append(f"🎯 Dream ${self.dream_target:,.0f} — progress {self.dream_progress_pct:.2f}%")
        for biz, pct in sorted(self.dream_contributions_pct.items(), key=lambda x: -x[1]):
            L.append(f"     {biz:<20} {pct:.0%}")
        if self.actions:
            L.append("✅ CEO Action List:")
            for i, a in enumerate(self.actions, 1):
                extra = ""
                if "roi" in a:
                    extra = f" (ROI {a['roi']:.0%}, conf {a.get('confidence', 0):.0%})"
                L.append(f"   {i}. {a['title']}{extra}")
        if self.timeline is not None and self.timeline.events:
            L.append("")
            L.append(self.timeline.render())
        return "\n".join(L)

    def to_dict(self) -> dict:
        return {
            "overview": {"health": self.portfolio_health, "value_usd": self.portfolio_value_usd,
                         "cash_usd": self.cash_usd, "todays_change_pct": self.todays_change_pct,
                         "risk_level": self.risk_level, "regime": self.regime},
            "funnel": self.funnel.__dict__,
            "research_accuracy": self.research_accuracy,
            "strategy_stars": self.strategy_stars,
            "portfolio": {"diversification": self.diversification,
                          "concentration": self.concentration, "liquidity": self.liquidity,
                          "cash_runway_months": self.cash_runway_months,
                          "rebalance": self.rebalance},
            "knowledge": self.knowledge.__dict__,
            "dream": {"target": self.dream_target, "progress_pct": self.dream_progress_pct,
                      "contributions_pct": self.dream_contributions_pct},
            "actions": self.actions,
        }


class FinancialMissionControl:
    """Aggregates engine outputs into the dashboard. Formatting only."""

    def __init__(self, *, publish: Callable[[str, dict], object] | None = None,
                 send: Callable[[str], object] | None = None):
        if publish is None:
            from saathi.events import bus
            publish = bus.publish_sync
        self._publish = publish
        self._send = send

    def compose(self, *,
                health: HealthReport, allocation: AllocationBreakdown,
                risk: PortfolioRiskReport, rebalance: list[RebalanceAction],
                funnel: PipelineFunnel, learning: LearningResult,
                performance: PerformanceReport,
                portfolio_value_usd: float, cash_usd: float, todays_change_pct: float,
                regime: str, knowledge: KnowledgeStats,
                dream_contributions_usd: dict[str, float], revenue_to_date_usd: float,
                actions: list[dict], timeline: CapitalAllocationTimeline | None = None,
                dream_target: float = DREAM_TARGET) -> FinancialDashboard:

        research_accuracy = {ra.agent: ra.predictive_accuracy for ra in learning.research_accuracy}
        strategy_stars = {s: max(0, min(5, round(rep.win_rate * 5)))
                          for s, rep in learning.strategy_scores.items()}
        total_contrib = sum(dream_contributions_usd.values()) or 1.0
        contributions_pct = {k: round(v / total_contrib, 4) for k, v in dream_contributions_usd.items()}
        risk_level = "high" if risk.risk_score < 40 else "medium" if risk.risk_score < 70 else "low"

        dash = FinancialDashboard(
            portfolio_health=health.overall, portfolio_value_usd=portfolio_value_usd,
            cash_usd=cash_usd, todays_change_pct=todays_change_pct, risk_level=risk_level,
            regime=regime, funnel=funnel, research_accuracy=research_accuracy,
            strategy_stars=strategy_stars, diversification=health.diversification,
            concentration=risk.concentration, liquidity=risk.liquidity,
            cash_runway_months=risk.cash_runway_months,
            rebalance=[a.render() for a in rebalance], knowledge=knowledge,
            dream_target=dream_target,
            dream_progress_pct=round(revenue_to_date_usd / dream_target * 100, 4),
            dream_contributions_pct=contributions_pct, actions=actions, timeline=timeline)

        self._publish("financial_mission_control.rendered", {
            "health": health.overall, "awaiting_approval": funnel.awaiting_approval,
            "proposals": knowledge.proposals_awaiting, "actions": len(actions)})
        return dash

    def send_briefing(self, dashboard: FinancialDashboard) -> bool:
        """Deliver the briefing (e.g. Telegram) if a sender was injected."""
        if self._send is None:
            return False
        self._send(dashboard.render())
        return True
