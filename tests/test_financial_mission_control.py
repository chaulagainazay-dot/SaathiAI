"""Financial Mission Control tests (M5 Phase 8) — pure consumer/presentation.

Deterministic (AP-17); all data passed in from engines; publisher/sender injected
(AP-12). Mission Control performs no analysis and executes nothing.
"""
from saathi.portfolio import (
    HealthReport, AllocationBreakdown, PortfolioRiskReport, RebalanceAction,
)
from saathi.trade_journal import PerformanceReport
from saathi.investment_learning import LearningResult, ResearchAccuracy
from saathi.financial_mission_control import (
    FinancialMissionControl, PipelineFunnel, KnowledgeStats,
    CapitalAllocationTimeline, AllocationEvent, DREAM_TARGET,
)


def _health():
    return HealthReport(overall=91, allocation=88, risk=75, diversification=80,
                        liquidity=90, goal_alignment=85, performance=60)


def _risk():
    return PortfolioRiskReport(weighted_volatility=0.3, max_drawdown_est=0.4,
                               concentration=0.35, correlation=0.2, liquidity=0.82,
                               leverage=0.0, cash_runway_months=6.0, risk_score=72)


def _learning():
    return LearningResult(
        performance=PerformanceReport(10, 0.6, 200, -80, 88, 2.1, 1.4, 300, 3600, 1200,
                                      "momentum", "mean_reversion", "crypto", "meme"),
        strategy_scores={
            "momentum": PerformanceReport(5, 0.8, 200, -50, 130, 3.0, 1.6, 100, 3600, 900,
                                          "momentum", "momentum", "crypto", "crypto"),
            "mean_reversion": PerformanceReport(5, 0.4, 100, -120, -20, 0.6, 0.4, 300, 3600, 300,
                                                "mean_reversion", "mean_reversion", "etf", "etf")},
        research_accuracy=[ResearchAccuracy("fundamentals", 0.91, 10),
                           ResearchAccuracy("onchain", 0.86, 10),
                           ResearchAccuracy("sentiment", 0.41, 10)],
        regime_insights=[], portfolio_insights=[], patterns=[], proposals=[{"id": 1}])


def _compose(mc=None, timeline=None, send=None, events=None):
    mc = mc or FinancialMissionControl(
        publish=lambda n, p: (events if events is not None else []).append((n, p)), send=send)
    return mc.compose(
        health=_health(),
        allocation=AllocationBreakdown(100_000, 0.1, 0.05, {"crypto": 0.3, "etf": 0.4}),
        risk=_risk(),
        rebalance=[RebalanceAction("reduce", "crypto", 0.08, "over-concentrated")],
        funnel=PipelineFunnel(scanned=154, qualified=18, researched=9, dd_passed=4,
                              awaiting_approval=2, executed_today=1),
        learning=_learning(),
        performance=_learning().performance,
        portfolio_value_usd=42_350, cash_usd=8_200, todays_change_pct=1.8,
        regime="bull", knowledge=KnowledgeStats(3, 2, 1, 4),
        dream_contributions_usd={"AI Studio": 18_000, "Cafeteria": 22_000,
                                 "Travel": 15_000, "Crypto": 9_000},
        revenue_to_date_usd=100_000,
        actions=[{"title": "Approve AI Studio marketing ($2,000)", "roi": 0.31,
                  "confidence": 0.91},
                 {"title": "Review Opportunity #218"}],
        timeline=timeline)


# ── Composition maps engine outputs into sections (no recomputation) ───────
def test_compose_builds_all_sections():
    dash = _compose()
    assert dash.portfolio_health == 91
    assert dash.funnel.awaiting_approval == 2
    assert dash.research_accuracy["fundamentals"] == 0.91
    assert dash.strategy_stars["momentum"] == 4        # round(0.8*5)
    assert dash.strategy_stars["mean_reversion"] == 2  # round(0.4*5)
    assert dash.risk_level == "low"                    # risk_score 72 ≥ 70
    assert dash.dream_target == DREAM_TARGET


# ── Dream contributions normalized to % ────────────────────────────────────
def test_dream_contributions_normalized():
    dash = _compose()
    total = sum(dash.dream_contributions_pct.values())
    assert abs(total - 1.0) < 1e-6
    assert dash.dream_contributions_pct["Cafeteria"] == round(22_000 / 64_000, 4)


# ── Render includes the headline sections ──────────────────────────────────
def test_render_contains_key_sections():
    text = _compose().render()
    for marker in ("MISSION CONTROL", "Overview", "Pipeline", "Research accuracy",
                   "Strategies", "Dream", "CEO Action List"):
        assert marker in text
    assert "★★★★☆" in text                             # momentum 4 stars


# ── Research accuracy ordering (best first) ────────────────────────────────
def test_research_accuracy_rendered_best_first():
    text = _compose().render()
    assert text.index("fundamentals") < text.index("sentiment")


# ── Publishes an event; sends briefing only when a sender is injected ──────
def test_publishes_and_optionally_sends():
    events, sent = [], []
    mc = FinancialMissionControl(publish=lambda n, p: events.append((n, p)),
                                 send=lambda msg: sent.append(msg))
    dash = _compose(mc=mc)
    assert events[0][0] == "financial_mission_control.rendered"
    assert mc.send_briefing(dash) is True
    assert "MISSION CONTROL" in sent[0]
    # no sender → returns False, no crash
    assert FinancialMissionControl(publish=lambda n, p: None).send_briefing(dash) is False


# ── Capital Allocation Timeline: best/worst/net historical map ─────────────
def test_capital_allocation_timeline():
    tl = CapitalAllocationTimeline([
        AllocationEvent("Jan", "YouTube Marketing", 18_000),
        AllocationEvent("Feb", "Kitchen Upgrade", 6_200),
        AllocationEvent("Mar", "AI Coin", -1_300),
        AllocationEvent("Apr", "Travel Business", 12_800),
    ])
    assert tl.best().label == "YouTube Marketing"
    assert tl.worst().label == "AI Coin"
    assert tl.net_usd() == 35_700
    dash = _compose(timeline=tl)
    assert "Capital Allocation Timeline" in dash.render()


def test_to_dict_is_api_ready():
    d = _compose().to_dict()
    assert d["overview"]["health"] == 91
    assert d["funnel"]["scanned"] == 154
    assert d["dream"]["target"] == DREAM_TARGET
    assert "fundamentals" in d["research_accuracy"]
