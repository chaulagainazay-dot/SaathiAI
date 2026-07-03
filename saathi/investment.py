"""Investment Intelligence Department (M5) — decision support, never autonomy.

Mission: find, evaluate, simulate, prioritize, monitor, and improve every capital
allocation opportunity across all asset classes AND across your own businesses.

The non-negotiable spine (AP-14, certified by the M4.5 Security audit — financial
actions are L4, human-approved): SaathiAI prepares explainable analysis; **you**
confirm capital allocation. No path reaches an exchange without approval.

    Research → Opportunity → Due Diligence → Simulation → Risk → Recommendation
             → HUMAN APPROVAL → Execution connector → Episode → Learning

Engines here (deterministic, testable — AP-17): Opportunity scoring, Due
Diligence, Risk sizing, Scenario simulation, Recommendation (approval-gated),
and the Capital Allocation Engine (every dollar competes — crypto vs stock vs
marketing vs AI Studio vs cafeteria vs GPU).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    STOCK = "stock"
    ETF = "etf"
    IPO = "ipo"
    ICO = "ico"
    REAL_ESTATE = "real_estate"
    BUSINESS = "business"
    SAAS = "saas"
    AI_STARTUP = "ai_startup"
    MARKETING = "marketing"
    EQUIPMENT = "equipment"
    HIRING = "hiring"
    OWN_BUSINESS = "own_business"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── Opportunity scoring ────────────────────────────────────────────────────
@dataclass
class Opportunity:
    name: str
    asset_class: AssetClass
    roi_estimate: float           # expected return multiple (e.g. 0.5 = +50%)
    risk: float                   # 0..1
    capital_required_usd: float
    time_to_revenue_months: float
    strategic_fit: float          # 0..1 — alignment with long-term goals
    evidence_sources: int = 0

    @property
    def score(self) -> float:
        """Deterministic: reward ROI, strategic fit, low risk; penalize long time
        to revenue. Explainable, no black box."""
        time_factor = 1.0 / math.sqrt(max(1.0, self.time_to_revenue_months))
        return round(self.roi_estimate * self.strategic_fit * (1.0 - self.risk) * time_factor, 4)


def rank_opportunities(opps: list[Opportunity], top: int = 5) -> list[Opportunity]:
    return sorted(opps, key=lambda o: o.score, reverse=True)[:top]


# ── Due Diligence ──────────────────────────────────────────────────────────
@dataclass
class DueDiligenceItem:
    name: str
    passed: bool
    weight: float = 1.0
    note: str = ""


@dataclass
class DueDiligenceResult:
    items: list[DueDiligenceItem]
    score: float
    passed: bool

    @property
    def failures(self) -> list[str]:
        return [i.name for i in self.items if not i.passed]


def score_due_diligence(items: list[DueDiligenceItem], threshold: float = 0.7) -> DueDiligenceResult:
    """Nothing reaches a recommendation without passing due diligence."""
    total_w = sum(i.weight for i in items) or 1.0
    score = round(sum(i.weight for i in items if i.passed) / total_w, 3)
    return DueDiligenceResult(items, score, score >= threshold)


# Standard crypto DD checklist keys (the caller supplies pass/fail per key).
CRYPTO_DD_KEYS = ["team", "audit", "treasury", "tokenomics", "unlock_schedule",
                  "github_commits", "community", "partnerships", "roadmap",
                  "liquidity", "security_history"]


# ── Risk Engine ────────────────────────────────────────────────────────────
@dataclass
class RiskProfile:
    position_size_usd: float
    max_allocation_pct: float
    max_drawdown_pct: float
    risk_level: RiskLevel


def size_position(*, portfolio_usd: float, conviction: float, risk: float,
                  hard_cap_pct: float = 0.05) -> RiskProfile:
    """Position sizing: scale with conviction, shrink with risk, never exceed the
    hard cap. Deterministic and conservative."""
    alloc_pct = min(hard_cap_pct, hard_cap_pct * conviction * (1.0 - risk))
    size = round(portfolio_usd * alloc_pct, 2)
    level = RiskLevel.HIGH if risk >= 0.66 else RiskLevel.MEDIUM if risk >= 0.33 else RiskLevel.LOW
    max_dd = round(0.2 + 0.6 * risk, 3)     # higher risk → larger expected drawdown
    return RiskProfile(size, round(alloc_pct, 4), max_dd, level)


# ── Simulation Engine ──────────────────────────────────────────────────────
@dataclass
class Scenario:
    name: str
    price_change_pct: float      # e.g. -0.35 = BTC falls 35%
    probability: float


@dataclass
class SimulationResult:
    expected_value_usd: float
    best_case_usd: float
    worst_case_usd: float
    scenarios: list[Scenario]


def simulate(position_usd: float, scenarios: list[Scenario]) -> SimulationResult:
    """Never 'should I buy?' — always 'what happens if...'. Scenario analysis."""
    outcomes = [(s, position_usd * s.price_change_pct) for s in scenarios]
    ev = round(sum(o[1] * o[0].probability for o in outcomes), 2)
    best = round(max(o[1] for o in outcomes), 2) if outcomes else 0.0
    worst = round(min(o[1] for o in outcomes), 2) if outcomes else 0.0
    return SimulationResult(ev, best, worst, scenarios)


# ── Recommendation Engine (approval-gated) ─────────────────────────────────
class Verdict(str, Enum):
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    REJECT = "reject"


@dataclass
class Recommendation:
    opportunity: str
    verdict: Verdict
    confidence: float
    risk_level: RiskLevel
    investment_usd: float
    max_allocation_pct: float
    horizon_months: float
    evidence_count: int
    dd_passed: bool
    simulation_ev_usd: float
    contradictions: list[str] = field(default_factory=list)
    requires_approval: bool = True       # ALWAYS — financial actions are L4 (AP-14)
    approved: bool = False
    approver: str | None = None
    why: str = ""

    def approve(self, approver: str) -> "Recommendation":
        """The human confirms. Only after this may an execution connector run."""
        if self.verdict is Verdict.REJECT:
            raise ValueError("cannot approve a REJECT recommendation")
        self.approved = True
        self.approver = approver
        return self

    @property
    def executable(self) -> bool:
        """An execution connector may run ONLY if approved. Never auto-true."""
        return self.approved and self.verdict in (Verdict.BUY, Verdict.SELL)


class RecommendationEngine:
    def recommend(self, *, opp: Opportunity, dd: DueDiligenceResult,
                  risk: RiskProfile, sim: SimulationResult,
                  contradictions: list[str] | None = None) -> Recommendation:
        contradictions = contradictions or []
        if not dd.passed:
            return Recommendation(
                opp.name, Verdict.REJECT, confidence=0.0, risk_level=risk.risk_level,
                investment_usd=0.0, max_allocation_pct=0.0, horizon_months=0,
                evidence_count=opp.evidence_sources, dd_passed=False,
                simulation_ev_usd=sim.expected_value_usd, contradictions=contradictions,
                why=f"Due diligence failed: {', '.join(dd.failures)}")
        # Verdict from expected value + strategic fit; conservative when EV negative.
        if sim.expected_value_usd <= 0 or contradictions:
            verdict = Verdict.HOLD
        else:
            verdict = Verdict.BUY
        confidence = round(dd.score * opp.strategic_fit * (1.0 - opp.risk), 3)
        return Recommendation(
            opp.name, verdict, confidence=confidence, risk_level=risk.risk_level,
            investment_usd=risk.position_size_usd, max_allocation_pct=risk.max_allocation_pct,
            horizon_months=opp.time_to_revenue_months, evidence_count=opp.evidence_sources,
            dd_passed=True, simulation_ev_usd=sim.expected_value_usd,
            contradictions=contradictions,
            why=(f"DD {dd.score:.0%}, strategic fit {opp.strategic_fit:.0%}, "
                 f"sim EV ${sim.expected_value_usd:.0f}, {opp.evidence_sources} sources"))


# ── Capital Allocation Engine (every dollar competes) ──────────────────────
@dataclass
class AllocationOption:
    name: str
    category: AssetClass
    roi: float                    # expected return multiple
    risk: float                   # 0..1
    time_to_payoff_months: float
    strategic_value: float        # 0..1
    confidence: float             # 0..1

    @property
    def expected_value_score(self) -> float:
        """Where does the next dollar create the greatest expected value? Financial
        assets compete directly with business investments (marketing, AI Studio,
        cafeteria, GPU) — sometimes the best return isn't a token."""
        time_factor = 1.0 / math.sqrt(max(1.0, self.time_to_payoff_months))
        return round(self.roi * (1.0 - self.risk) * self.strategic_value
                     * self.confidence * time_factor, 4)


@dataclass
class AllocationDecision:
    amount_usd: float
    ranked: list[AllocationOption]
    recommended: AllocationOption
    rationale: str


class CapitalAllocationEngine:
    def allocate(self, amount_usd: float, options: list[AllocationOption]) -> AllocationDecision:
        if not options:
            raise ValueError("no allocation options provided")
        ranked = sorted(options, key=lambda o: o.expected_value_score, reverse=True)
        best = ranked[0]
        rationale = (f"${amount_usd:,.0f} → {best.name} ({best.category.value}): "
                     f"highest expected value ({best.expected_value_score}) among "
                     f"{len(options)} options — ROI {best.roi:.0%}, risk {best.risk:.0%}, "
                     f"strategic {best.strategic_value:.0%}")
        return AllocationDecision(amount_usd, ranked, best, rationale)
