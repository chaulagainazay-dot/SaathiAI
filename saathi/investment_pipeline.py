"""Discovery → Recommendation Bridge (M5 Phase 3) — one autonomous pipeline.

Turns the eight independent M5 engines into a single traceable decision-support
flow. The orchestration lives HERE, not inside any engine — no stage knows how
the next one works (clean boundaries, AP-01):

    discover → research → validate → simulate → size → recommend
             → capital-allocate → [Governance L4 human approval] → learn

Every opportunity accumulates into ONE `InvestmentCase` that each stage appends
to, so downstream departments (Portfolio Intelligence, Mission Control) receive
a single object instead of ten. Every recommendation carries a complete,
explainable evidence package traceable from discovery all the way to learning.

The human-approval spine is preserved end-to-end: recommendations are L4, always
`requires_approval`, and `.executable` only after a human `.approve()` (AP-14).

Deterministic core (AP-17); discovery / research / DD & scenario providers /
clock / publisher / recorder all injected (AP-12).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from saathi.investment import (
    Opportunity as InvOpportunity, AssetClass,
    DueDiligenceItem, DueDiligenceResult, score_due_diligence,
    RiskProfile, size_position,
    Scenario, SimulationResult, simulate,
    Recommendation, RecommendationEngine, Verdict,
    AllocationOption, AllocationDecision, CapitalAllocationEngine,
)
from saathi.opportunity import Opportunity, OpportunityCategory


# category → asset class (asset_type string can refine INVESTMENT)
_ASSET_MAP = {
    OpportunityCategory.BUSINESS: AssetClass.OWN_BUSINESS,
    OpportunityCategory.AI: AssetClass.AI_STARTUP,
    OpportunityCategory.REVENUE: AssetClass.MARKETING,
    OpportunityCategory.EDUCATION: AssetClass.BUSINESS,
}
_INVESTMENT_ASSET = {
    "stock": AssetClass.STOCK, "etf": AssetClass.ETF, "ipo": AssetClass.IPO,
    "ico": AssetClass.ICO, "crypto": AssetClass.CRYPTO,
}


def _to_investment_opportunity(opp: Opportunity) -> InvOpportunity:
    if opp.category is OpportunityCategory.INVESTMENT:
        asset = _INVESTMENT_ASSET.get(opp.asset_type.lower(), AssetClass.CRYPTO)
    else:
        asset = _ASSET_MAP[opp.category]
    return InvOpportunity(
        name=opp.title, asset_class=asset, roi_estimate=opp.expected_roi,
        risk=opp.risk, capital_required_usd=opp.capital_required_usd,
        time_to_revenue_months=opp.time_horizon_months,
        strategic_fit=opp.strategic_fit, evidence_sources=len(opp.sources))


@dataclass
class InvestmentCase:
    """One object, appended to by each stage. The complete evidence package."""
    opportunity: Opportunity
    research: object | None = None            # ResearchConfidence
    due_diligence: DueDiligenceResult | None = None
    simulation: SimulationResult | None = None
    risk: RiskProfile | None = None
    recommendation: Recommendation | None = None
    allocation: AllocationDecision | None = None
    governance_level: str = "L4"              # financial actions are L4 (certified)
    approval_required: bool = True
    evidence_ids: list[str] = field(default_factory=list)
    explanation: str = ""

    @property
    def verdict(self) -> Verdict | None:
        return self.recommendation.verdict if self.recommendation else None

    def approve(self, approver: str) -> "InvestmentCase":
        """Human approval — the only path to executability (Governance L4)."""
        if self.recommendation is None:
            raise ValueError("no recommendation to approve")
        self.recommendation.approve(approver)   # raises on REJECT
        return self

    @property
    def executable(self) -> bool:
        return bool(self.recommendation and self.recommendation.executable)

    def render(self) -> str:
        r, opp = self.recommendation, self.opportunity
        lines = [f"📋 {opp.title} [{opp.category.value}] — "
                 f"{r.verdict.value.upper() if r else '—'} "
                 f"(governance {self.governance_level}, "
                 f"{'APPROVAL REQUIRED' if self.approval_required else 'approved'})"]
        if self.research is not None:
            lines.append(f"  research: {self.research.overall:.0f}/100, "
                         f"coverage {self.research.coverage:.0%}, "
                         f"{self.research.source_count} sources")
        if self.due_diligence is not None:
            lines.append(f"  due diligence: {self.due_diligence.score:.0%} "
                         f"({'PASS' if self.due_diligence.passed else 'FAIL: ' + ', '.join(self.due_diligence.failures)})")
        if self.simulation is not None:
            lines.append(f"  simulation: EV ${self.simulation.expected_value_usd:.0f} "
                         f"(worst ${self.simulation.worst_case_usd:.0f})")
        if self.risk is not None:
            lines.append(f"  risk: {self.risk.risk_level.value}, "
                         f"size ${self.risk.position_size_usd:.0f} "
                         f"({self.risk.max_allocation_pct:.1%})")
        if self.explanation:
            lines.append(f"  → {self.explanation}")
        return "\n".join(lines)


@dataclass
class PipelineResult:
    cases: list[InvestmentCase]                       # ranked, all evaluated
    recommendations: list[InvestmentCase]             # BUY, awaiting approval
    allocation: AllocationDecision | None             # capital competition winner

    def render(self) -> str:
        out = [c.render() for c in self.cases]
        if self.allocation is not None:
            out.append("💰 " + self.allocation.rationale)
        return "\n\n".join(out)


# providers derive DD checklist and scenarios per opportunity (from research in
# prod; injected fakes in tests). Signatures the caller supplies:
DDProvider = Callable[[Opportunity], list[DueDiligenceItem]]
ScenarioProvider = Callable[[Opportunity], list[Scenario]]


class InvestmentPipeline:
    def __init__(self, *,
                 portfolio_usd: float,
                 dd_provider: DDProvider,
                 scenario_provider: ScenarioProvider,
                 research: Callable[[str], object] | None = None,
                 rec_engine: RecommendationEngine | None = None,
                 alloc_engine: CapitalAllocationEngine | None = None,
                 publish: Callable[[str, dict], object] | None = None,
                 record_episode: Callable[..., int] | None = None):
        self.portfolio_usd = portfolio_usd
        self.dd_provider = dd_provider
        self.scenario_provider = scenario_provider
        self.research = research
        self.rec_engine = rec_engine or RecommendationEngine()
        self.alloc_engine = alloc_engine or CapitalAllocationEngine()
        if publish is None:
            from saathi.events import bus
            publish = bus.publish_sync
        if record_episode is None:
            from saathi.integration import ingest_episode as record_episode
        self._publish = publish
        self._episode = record_episode

    def evaluate(self, opp: Opportunity) -> InvestmentCase:
        """Run one opportunity through every stage into a complete case."""
        case = InvestmentCase(opportunity=opp, evidence_ids=list(opp.sources))

        # research (reuse what discovery already attached, else fetch)
        conf = opp.research_report
        if conf is None and self.research is not None:
            conf = self.research(opp.title)
        case.research = conf
        contradictions = list(getattr(conf, "contradictions", []) or [])
        conviction = round((conf.overall / 100.0) if conf else 0.5, 3)

        # validate (due diligence)
        dd = score_due_diligence(self.dd_provider(opp))
        case.due_diligence = dd

        # size position (risk engine)
        risk = size_position(portfolio_usd=self.portfolio_usd,
                             conviction=conviction, risk=opp.risk)
        case.risk = risk

        # simulate (scenario analysis on the sized position)
        sim = simulate(risk.position_size_usd, self.scenario_provider(opp))
        case.simulation = sim

        # recommend (approval-gated; contradictions from research downgrade)
        rec = self.rec_engine.recommend(
            opp=_to_investment_opportunity(opp), dd=dd, risk=risk, sim=sim,
            contradictions=contradictions)
        case.recommendation = rec
        case.approval_required = rec.requires_approval        # always True
        case.explanation = rec.why
        return case

    def run(self, opportunities: list[Opportunity], *,
            total_capital_usd: float | None = None) -> PipelineResult:
        cases = [self.evaluate(o) for o in opportunities]

        # capital allocation: every BUY dollar competes
        buys = [c for c in cases if c.verdict is Verdict.BUY]
        allocation = None
        if buys:
            options = [AllocationOption(
                name=c.opportunity.title, category=_to_investment_opportunity(c.opportunity).asset_class,
                roi=c.opportunity.expected_roi, risk=c.opportunity.risk,
                time_to_payoff_months=c.opportunity.time_horizon_months,
                strategic_value=c.opportunity.strategic_fit,
                confidence=(c.research.overall / 100.0) if c.research else 0.5)
                for c in buys]
            allocation = self.alloc_engine.allocate(
                total_capital_usd or self.portfolio_usd, options)
            for c in buys:
                if c.opportunity.title == allocation.recommended.name:
                    c.allocation = allocation

        # rank: BUY first (by confidence), then HOLD, REJECT last
        order = {Verdict.BUY: 0, Verdict.HOLD: 1, Verdict.SELL: 2, Verdict.REJECT: 3}
        cases.sort(key=lambda c: (order.get(c.verdict, 9),
                                  -(c.recommendation.confidence if c.recommendation else 0)))

        self._publish("investment.pipeline_run", {
            "evaluated": len(cases), "buys": len(buys),
            "awaiting_approval": len(buys),
            "allocated_to": allocation.recommended.name if allocation else None})
        self._episode(
            agent="investment_pipeline", department="investment", product="pipeline",
            intent="decision_pipeline",
            action=f"evaluated {len(cases)} opportunities end-to-end",
            result=f"{len(buys)} BUY recommendations awaiting human approval",
            outcome="success", quality_score=round(len(buys) / max(len(cases), 1), 3),
            metadata={"buys": [c.opportunity.title for c in buys],
                      "allocation": allocation.recommended.name if allocation else None})
        return PipelineResult(cases=cases, recommendations=buys, allocation=allocation)
