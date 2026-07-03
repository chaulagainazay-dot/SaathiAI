"""Executive Intelligence tests (M4) — the daily CEO, deterministic, AP-12/17."""
import pytest

from saathi.executive import (
    Recommendation, DecisionEngine, Priority, align_to_goal, DREAM_TARGET,
    forecast_linear, compute_execution_score, ExecutionScoreEngine, build_briefing,
)


# ── Decision Engine ────────────────────────────────────────────────────────
def test_recommendation_priority_is_explainable():
    r = Recommendation(
        title="Make another IELTS whiteboard video",
        why="Last 4 videos: CTR +23%, watch time +18%, revenue +14%",
        expected_impact_usd=430, confidence=0.89, risk=0.1)
    # 430 * 0.89 * 0.9 = 344.43
    assert r.priority_score == 344.43
    assert r.priority is Priority.HIGH


def test_decision_engine_ranks_top_actions():
    d = DecisionEngine()
    d.add(Recommendation("low", "meh", expected_impact_usd=20, confidence=0.5, risk=0.5))
    d.add(Recommendation("high", "great evidence", expected_impact_usd=1000, confidence=0.9, risk=0.1))
    d.add(Recommendation("mid", "ok", expected_impact_usd=200, confidence=0.7, risk=0.3))
    top = d.top(2)
    assert [r.title for r in top] == ["high", "mid"]


def test_risk_and_cost_lower_priority():
    safe = Recommendation("safe", "", expected_impact_usd=500, confidence=0.9, risk=0.1)
    risky = Recommendation("risky", "", expected_impact_usd=500, confidence=0.9, risk=0.8)
    assert safe.priority_score > risky.priority_score


# ── Goal Alignment ─────────────────────────────────────────────────────────
def test_goal_alignment_scores_contribution():
    a = align_to_goal(500)
    assert a.priority is Priority.HIGH
    assert a.contribution_pct == round(500 / DREAM_TARGET * 100, 4)
    assert align_to_goal(10).priority is Priority.LOW


# ── Forecast ───────────────────────────────────────────────────────────────
def test_forecast_projects_from_trend():
    # +100/day for 5 days → +100*30 in 30 days
    f = forecast_linear([100, 200, 300, 400, 500], horizon_days=30)
    assert f.current == 500
    assert f.projected == 500 + 100 * 30
    assert f.probability == 0.7


def test_forecast_handles_sparse_history():
    assert forecast_linear([], 30).projected == 0.0
    assert forecast_linear([42], 30).projected == 42


# ── Execution Score ────────────────────────────────────────────────────────
def test_execution_score_rewards_throughput_and_automation():
    good = compute_execution_score(completed=14, delayed=1, blocked=0, revenue_usd=184,
                                   knowledge_learned=4, automation_pct=0.73, goal_progress_pct=0.018)
    bad = compute_execution_score(completed=2, delayed=5, blocked=5, revenue_usd=0,
                                  knowledge_learned=0, automation_pct=0.1, goal_progress_pct=0.0)
    assert good.score > bad.score
    assert 0 <= good.score <= 100


def test_execution_score_trend(tmp_path):
    eng = ExecutionScoreEngine(str(tmp_path / "ex.db"), now=lambda: 9_000_000.0)
    for sc in (60, 70, 80):
        eng.record(compute_execution_score(
            completed=sc // 10, delayed=0, blocked=0, revenue_usd=sc, knowledge_learned=1,
            automation_pct=sc / 100, goal_progress_pct=0.01))
    assert eng.trend() == "improving"
    assert len(eng.recent_scores()) == 3


# ── Executive Briefing (ties it together) ──────────────────────────────────
def test_briefing_assembles_prioritized_actions():
    d = DecisionEngine()
    d.add(Recommendation("Reduce cafeteria rice", "waste +4%", expected_impact_usd=200,
                         confidence=0.8, risk=0.1))
    d.add(Recommendation("Contact travel lead", "waiting 2 days", expected_impact_usd=640,
                         confidence=0.7, risk=0.2))
    es = compute_execution_score(completed=14, delayed=3, blocked=2, revenue_usd=184,
                                 knowledge_learned=4, automation_pct=0.73, goal_progress_pct=0.018)
    brief = build_briefing(decisions=d, dream_progress_pct=0.0011, execution=es,
                           execution_trend="improving")
    text = brief.render("Ajay")
    assert text.startswith("Good morning Ajay.")
    assert "Priority Score:" in text
    assert "Top actions:" in text
    assert "travel lead" in text.lower()          # higher impact ranked first
    assert "Execution yesterday: " in text
    # top action should be the higher-priority one
    assert brief.top_actions[0].title == "Contact travel lead"
