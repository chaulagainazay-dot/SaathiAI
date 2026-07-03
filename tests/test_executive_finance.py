"""Executive Intelligence financial integration tests (M5 Phase 9).

Executive Intelligence consumes Financial Mission Control — no recomputation.
Deterministic (AP-17); dashboard + yesterday passed in, publisher injected (AP-12).
"""
from saathi.financial_mission_control import (
    FinancialDashboard, PipelineFunnel, KnowledgeStats,
)
from saathi.executive_finance import (
    DepartmentRecommendation, CrossDepartmentPriorityEngine,
    YesterdaySummary, ExecutiveFinanceBriefer, _CEO_QUESTIONS,
)


def _dashboard():
    return FinancialDashboard(
        portfolio_health=91, portfolio_value_usd=42_350, cash_usd=8_200,
        todays_change_pct=1.8, risk_level="low", regime="bull",
        funnel=PipelineFunnel(scanned=154, qualified=18, researched=9, dd_passed=4,
                              awaiting_approval=1, executed_today=1),
        research_accuracy={"fundamentals": 0.91, "sentiment": 0.41},
        strategy_stars={"momentum": 4, "mean_reversion": 2},
        diversification=80, concentration=0.35, liquidity=0.82, cash_runway_months=6,
        rebalance=["Reduce crypto by 8% — over-concentrated"],
        knowledge=KnowledgeStats(proposals_awaiting=2, knowledge_promoted=1,
                                 contradictions=1, experiments_running=4),
        dream_target=7_938_838.98, dream_progress_pct=0.23,
        dream_contributions_pct={"AI Studio": 0.38, "Cafeteria": 0.22},
        actions=[])


# ── Cross-department priority: strategic high-value beats urgent low-value ──
def test_priority_engine_does_not_let_urgent_lowvalue_win():
    eng = CrossDepartmentPriorityEngine()
    strategic = DepartmentRecommendation(
        "Approve AI Studio marketing", "investment", estimated_value_usd=2000,
        confidence=0.91, urgency=0.3, risk=0.2, goal_alignment=0.9)
    urgent_small = DepartmentRecommendation(
        "Reply to a comment", "discovery", estimated_value_usd=20,
        confidence=0.9, urgency=1.0, risk=0.1, goal_alignment=0.3)
    eng.add_many([urgent_small, strategic])
    assert eng.top(1)[0].title == "Approve AI Studio marketing"
    assert eng.ranked()[0].priority_score > eng.ranked()[-1].priority_score


def test_priority_engine_pending_approvals_and_by_department():
    eng = CrossDepartmentPriorityEngine()
    eng.add(DepartmentRecommendation("Approve alloc", "investment",
                                     estimated_value_usd=1000, requires_approval=True))
    eng.add(DepartmentRecommendation("Publish video", "ai_studio", estimated_value_usd=500))
    assert len(eng.pending_approvals()) == 1
    assert len(eng.by_department("ai_studio")) == 1


# ── Briefer consumes the dashboard for finance highlights (no recompute) ───
def test_financial_highlights_sourced_from_dashboard():
    eng = CrossDepartmentPriorityEngine()
    eng.add(DepartmentRecommendation("Review Opportunity #218", "investment",
                                     estimated_value_usd=1500, confidence=0.8,
                                     goal_alignment=0.8))
    briefer = ExecutiveFinanceBriefer(publish=lambda n, p: None)
    b = briefer.build(priority=eng, dashboard=_dashboard(),
                      yesterday=YesterdaySummary(completed=5, delayed=1),
                      dream_progress_pct=0.23, dream_delta_pct=0.02)
    joined = " ".join(b.financial_highlights)
    assert "Portfolio Health: 91/100" in joined
    assert "AI Studio contributed 38%" in joined            # top dream contributor
    assert "awaiting approval" in joined
    assert "Momentum strategy remains strongest" in joined  # top strategy stars
    assert "Fundamentals research accuracy: 91%" in joined   # top research agent


# ── The eight-question CEO cockpit is always answered ──────────────────────
def test_ceo_cockpit_answers_all_eight_questions():
    eng = CrossDepartmentPriorityEngine()
    eng.add(DepartmentRecommendation("Publish Mr. Yeti Lesson #43", "ai_studio",
                                     estimated_value_usd=300, goal_alignment=0.6))
    briefer = ExecutiveFinanceBriefer(publish=lambda n, p: None)
    b = briefer.build(
        priority=eng, dashboard=_dashboard(),
        yesterday=YesterdaySummary(completed=6, delayed=1, blocked=1,
                                   made_money=["AI Studio +$420"],
                                   lost_money=["AI Coin -$130"],
                                   blockers=["Travel API key expired"]),
        dream_progress_pct=0.23, dream_delta_pct=0.02)
    assert set(b.answers.keys()) == set(_CEO_QUESTIONS)
    assert len(b.answers) == 8
    assert "AI Studio +$420" in b.answers[_CEO_QUESTIONS[3]]   # what made money
    assert "AI Coin -$130" in b.answers[_CEO_QUESTIONS[4]]     # what lost money
    assert "Travel API key expired" in b.answers[_CEO_QUESTIONS[2]]  # blockers
    cockpit = b.render_cockpit()
    for q in _CEO_QUESTIONS:
        assert q in cockpit


# ── Risks & learning folded in from dashboard; event published ─────────────
def test_risks_learning_and_event():
    events = []
    eng = CrossDepartmentPriorityEngine()
    eng.add(DepartmentRecommendation("Approve alloc", "investment",
                                     estimated_value_usd=2000, requires_approval=True,
                                     goal_alignment=0.9, confidence=0.9))
    briefer = ExecutiveFinanceBriefer(publish=lambda n, p: events.append((n, p)))
    b = briefer.build(priority=eng, dashboard=_dashboard(),
                      yesterday=YesterdaySummary(blockers=["supplier late"]),
                      dream_progress_pct=0.23, dream_delta_pct=0.02)
    assert any("Reduce crypto" in r for r in b.risks)               # from rebalance
    assert any("contradiction" in r for r in b.risks)               # from knowledge
    assert any("supplier late" == r for r in b.risks)               # from blockers
    assert any("finance improvement" in l for l in b.learning)
    assert events[0][0] == "executive.financial_briefing"
    assert "MISSION CONTROL" not in b.render()                      # briefing, not the dashboard
    assert "Highest-Impact Actions" in b.render()
