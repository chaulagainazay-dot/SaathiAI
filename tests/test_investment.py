"""Investment Intelligence tests (M5) — decision support, human-approved, AP-12/14/17."""
import pytest

from saathi.investment import (
    Opportunity, AssetClass, rank_opportunities,
    DueDiligenceItem, score_due_diligence,
    size_position, RiskLevel, Scenario, simulate,
    RecommendationEngine, Verdict,
    AllocationOption, CapitalAllocationEngine,
)


# ── Opportunity scoring ────────────────────────────────────────────────────
def test_opportunity_ranking_rewards_roi_fit_penalizes_risk_and_time():
    fast_good = Opportunity("A", AssetClass.CRYPTO, roi_estimate=2.0, risk=0.2,
                            capital_required_usd=500, time_to_revenue_months=6, strategic_fit=0.9)
    slow_risky = Opportunity("B", AssetClass.CRYPTO, roi_estimate=2.0, risk=0.8,
                             capital_required_usd=500, time_to_revenue_months=36, strategic_fit=0.4)
    ranked = rank_opportunities([slow_risky, fast_good])
    assert ranked[0].name == "A"
    assert fast_good.score > slow_risky.score


# ── Due Diligence gate ─────────────────────────────────────────────────────
def test_due_diligence_pass_and_fail():
    passing = [DueDiligenceItem(k, True) for k in ("team", "audit", "tokenomics", "liquidity")]
    assert score_due_diligence(passing).passed is True
    mostly_failing = [DueDiligenceItem("team", True)] + \
                     [DueDiligenceItem(k, False) for k in ("audit", "tokenomics", "liquidity")]
    r = score_due_diligence(mostly_failing)
    assert r.passed is False
    assert "audit" in r.failures


# ── Risk sizing ────────────────────────────────────────────────────────────
def test_position_sizing_respects_hard_cap_and_risk():
    low = size_position(portfolio_usd=10000, conviction=1.0, risk=0.1)
    high = size_position(portfolio_usd=10000, conviction=1.0, risk=0.9)
    assert low.position_size_usd > high.position_size_usd    # more risk → smaller position
    assert low.max_allocation_pct <= 0.05                    # never exceeds hard cap
    assert high.risk_level is RiskLevel.HIGH


# ── Simulation ─────────────────────────────────────────────────────────────
def test_simulation_expected_and_extremes():
    sim = simulate(1000, [
        Scenario("bull", 1.0, 0.3),      # +100%
        Scenario("bear", -0.5, 0.3),     # -50%
        Scenario("sideways", 0.0, 0.4),
    ])
    # EV = 1000*(1.0*0.3 + -0.5*0.3 + 0*0.4) = 1000*0.15 = 150
    assert sim.expected_value_usd == 150.0
    assert sim.best_case_usd == 1000.0
    assert sim.worst_case_usd == -500.0


# ── Recommendation (approval-gated) ────────────────────────────────────────
def _good_opp():
    return Opportunity("SolidProject", AssetClass.CRYPTO, roi_estimate=1.5, risk=0.3,
                       capital_required_usd=500, time_to_revenue_months=18,
                       strategic_fit=0.8, evidence_sources=18)


def test_failed_dd_yields_reject():
    eng = RecommendationEngine()
    dd = score_due_diligence([DueDiligenceItem("audit", False), DueDiligenceItem("team", False)])
    rec = eng.recommend(opp=_good_opp(), dd=dd,
                        risk=size_position(portfolio_usd=10000, conviction=0.8, risk=0.3),
                        sim=simulate(500, [Scenario("bull", 1.0, 1.0)]))
    assert rec.verdict is Verdict.REJECT
    with pytest.raises(ValueError):
        rec.approve("ajay")                    # can't approve a reject


def test_positive_ev_yields_buy_but_requires_approval():
    eng = RecommendationEngine()
    dd = score_due_diligence([DueDiligenceItem(k, True) for k in
                              ("team", "audit", "tokenomics", "liquidity", "roadmap")])
    rec = eng.recommend(opp=_good_opp(), dd=dd,
                        risk=size_position(portfolio_usd=10000, conviction=0.8, risk=0.3),
                        sim=simulate(500, [Scenario("bull", 1.0, 0.6), Scenario("bear", -0.3, 0.4)]))
    assert rec.verdict is Verdict.BUY
    assert rec.requires_approval is True
    assert rec.executable is False             # NOT executable until a human approves
    rec.approve("ajay")
    assert rec.approved is True and rec.executable is True
    assert "18 sources" in rec.why             # explainable


def test_contradiction_downgrades_to_hold():
    eng = RecommendationEngine()
    dd = score_due_diligence([DueDiligenceItem(k, True) for k in ("team", "audit", "liquidity")])
    rec = eng.recommend(opp=_good_opp(), dd=dd,
                        risk=size_position(portfolio_usd=10000, conviction=0.8, risk=0.3),
                        sim=simulate(500, [Scenario("bull", 1.0, 1.0)]),
                        contradictions=["conflicting on-chain signal"])
    assert rec.verdict is Verdict.HOLD


# ── Capital Allocation (every dollar competes) ─────────────────────────────
def test_capital_allocation_can_prefer_business_over_crypto():
    engine = CapitalAllocationEngine()
    options = [
        AllocationOption("Buy meme coin", AssetClass.CRYPTO, roi=3.0, risk=0.85,
                         time_to_payoff_months=12, strategic_value=0.3, confidence=0.5),
        AllocationOption("AI Studio marketing", AssetClass.MARKETING, roi=1.2, risk=0.2,
                         time_to_payoff_months=2, strategic_value=0.9, confidence=0.85),
        AllocationOption("Cafeteria equipment", AssetClass.EQUIPMENT, roi=0.6, risk=0.15,
                         time_to_payoff_months=6, strategic_value=0.7, confidence=0.9),
    ]
    decision = engine.allocate(1000, options)
    # the high-risk meme coin should NOT win despite highest ROI — risk-adjusted EV rules
    assert decision.recommended.name == "AI Studio marketing"
    assert decision.ranked[0].expected_value_score >= decision.ranked[-1].expected_value_score
    assert "AI Studio marketing" in decision.rationale
