"""Investment Memory & Trade Journal tests (M5 Phase 6) — financial Platform Memory.

Deterministic (AP-17); clock/publish/record/db injected (AP-12).
"""
import pytest

from saathi.investment import AssetClass, Verdict, Recommendation, RiskLevel
from saathi.opportunity import Opportunity, OpportunityCategory
from saathi.investment_pipeline import InvestmentCase
from saathi.execution import (
    ExecutionIntent, PaperConnector, BrokerRegistry, ExecutionService,
)
from saathi.trade_journal import (
    TradeJournalRegistry, TradeStatus, ExitReason, Strategy,
    DecisionSnapshot, MarketContext, ResearchAttribution, PortfolioAttribution,
    Lesson, PerformanceAnalytics,
)

NOW = [10_000_000.0]                      # mutable clock
def clock():
    return NOW[0]


def _fill(symbol="BTC", qty=0.1, price=60_000.0):
    """Produce a real FILLED ExecutionOrder through the paper connector."""
    rec = Recommendation("BTC", Verdict.BUY, 0.8, RiskLevel.MEDIUM, 6000, 0.05, 12, 6,
                         True, 1000)
    case = InvestmentCase(opportunity=Opportunity(symbol, OpportunityCategory.INVESTMENT,
                          "gh", "crypto", expected_roi=1.5, risk=0.3, strategic_fit=0.8,
                          urgency=0.7, time_horizon_months=12, capital_required_usd=1000,
                          sources=["gh"]), recommendation=rec)
    case.approve("ajay")
    intent = ExecutionIntent.from_case(case, broker="paper", account="m",
                                       symbol=symbol, quantity=qty, now=clock())
    conn = PaperConnector(lambda s: price, starting_cash=1_000_000)
    return conn.execute(intent, clock())


def _registry(tmp_path, events=None, episodes=None):
    return TradeJournalRegistry(
        tmp_path / "journal.db", now=clock,
        publish=lambda n, p: (events if events is not None else []).append((n, p)),
        record_episode=lambda **kw: (episodes if episodes is not None else []).append(kw) or 1)


# ── Open a journal from a fill; snapshots preserved ────────────────────────
def test_open_journal_captures_decision_and_market_snapshots(tmp_path):
    reg = _registry(tmp_path)
    j = reg.record_open(
        _fill(), strategy=Strategy.RESEARCH_DRIVEN,
        decision=DecisionSnapshot(opportunity_score=0.82, research_confidence=88,
                                  risk_score=71, portfolio_health_before=82),
        market=MarketContext(fear_greed=25, regime="bear", btc_dominance=54),
        research=ResearchAttribution(fundamentals=95, onchain=90, sentiment=18))
    assert j.status is TradeStatus.OPEN
    assert j.decision.research_confidence == 88
    assert j.market.regime == "bear"                 # market context frozen at decision
    assert j.research.fundamentals == 95


# ── Close computes PnL / return / duration; win recorded ───────────────────
def test_close_computes_pnl_and_records_episode(tmp_path):
    events, episodes = [], []
    reg = _registry(tmp_path, events, episodes)
    j = reg.record_open(_fill(qty=0.1, price=60_000), strategy=Strategy.MOMENTUM)
    NOW[0] += 3600                                    # an hour later
    closed = reg.record_close(j.journal_id, exit_price=66_000,
                              exit_reason=ExitReason.TARGET_HIT)
    # (66000-60000)*0.1 - fee(~6) = ~594
    assert closed.pnl_usd > 500
    assert closed.return_pct > 0
    assert closed.duration_s == 3600
    assert closed.is_win
    assert events[-1][0] == "trade.closed"
    assert episodes[-1]["intent"] == "trade_closed" and episodes[-1]["outcome"] == "success"


# ── A closed journal is immutable — cannot re-close ────────────────────────
def test_closed_journal_is_immutable(tmp_path):
    reg = _registry(tmp_path)
    j = reg.record_open(_fill(), strategy=Strategy.MOMENTUM)
    reg.record_close(j.journal_id, exit_price=61_000, exit_reason=ExitReason.MANUAL)
    with pytest.raises(ValueError):
        reg.record_close(j.journal_id, exit_price=99_000, exit_reason=ExitReason.MANUAL)


# ── Append-only persistence: reopen the db, journal survives ───────────────
def test_journal_persists_across_reopen(tmp_path):
    reg = _registry(tmp_path)
    j = reg.record_open(_fill(), strategy=Strategy.FUNDAMENTAL,
                        research=ResearchAttribution(fundamentals=91))
    again = TradeJournalRegistry(tmp_path / "journal.db", now=clock,
                                 publish=lambda n, p: None, record_episode=lambda **k: 1)
    loaded = again.get(j.journal_id)
    assert loaded is not None
    assert loaded.research.fundamentals == 91
    assert loaded.strategy is Strategy.FUNDAMENTAL


# ── Structured lessons stored at close ─────────────────────────────────────
def test_close_stores_structured_lessons(tmp_path):
    reg = _registry(tmp_path)
    j = reg.record_open(_fill(), strategy=Strategy.AI_DISCOVERY)
    lesson = Lesson(observation="entered too early", root_cause="sentiment overweighted",
                    recommendation="require on-chain confirmation",
                    confidence=0.8, capabilities_affected=["Research Confidence Framework"],
                    evidence=["trade_143"])
    closed = reg.record_close(j.journal_id, exit_price=55_000,
                              exit_reason=ExitReason.STOP_HIT, lessons=[lesson])
    assert closed.lessons[0].root_cause == "sentiment overweighted"
    assert not closed.is_win


# ── Performance analytics across many trades ───────────────────────────────
def test_performance_analytics(tmp_path):
    reg = _registry(tmp_path)
    # 3 winners (momentum), 2 losers (mean_reversion)
    specs = [(66_000, Strategy.MOMENTUM), (64_000, Strategy.MOMENTUM),
             (63_000, Strategy.MOMENTUM), (57_000, Strategy.MEAN_REVERSION),
             (58_000, Strategy.MEAN_REVERSION)]
    for exit_px, strat in specs:
        j = reg.record_open(_fill(qty=0.1, price=60_000), strategy=strat)
        NOW[0] += 100
        reg.record_close(j.journal_id, exit_price=exit_px, exit_reason=ExitReason.MANUAL)
    report = PerformanceAnalytics().analyze(reg.closed())
    assert report.trades == 5
    assert report.win_rate == 0.6                    # 3 of 5
    assert report.best_strategy == Strategy.MOMENTUM.value
    assert report.worst_strategy == Strategy.MEAN_REVERSION.value
    assert report.max_drawdown_usd >= 0
    assert "trades" in report.render()


# ── Research attribution: winners vs losers per agent (closes the loop) ─────
def test_research_attribution_separates_winners_and_losers(tmp_path):
    reg = _registry(tmp_path)
    # winners had strong fundamentals+onchain, weak sentiment
    win = reg.record_open(_fill(price=60_000), strategy=Strategy.RESEARCH_DRIVEN,
                          research=ResearchAttribution(fundamentals=90, onchain=85, sentiment=20))
    NOW[0] += 100
    reg.record_close(win.journal_id, exit_price=66_000, exit_reason=ExitReason.TARGET_HIT)
    # losers were driven by sentiment
    lose = reg.record_open(_fill(price=60_000), strategy=Strategy.RESEARCH_DRIVEN,
                           research=ResearchAttribution(fundamentals=40, onchain=35, sentiment=95))
    NOW[0] += 100
    reg.record_close(lose.journal_id, exit_price=54_000, exit_reason=ExitReason.STOP_HIT)

    attr = PerformanceAnalytics().research_attribution(reg.closed())
    assert attr["fundamentals"]["winners"] > attr["fundamentals"]["losers"]
    assert attr["sentiment"]["winners"] < attr["sentiment"]["losers"]


# ── Execution → Journal integration (a fill becomes a journal) ─────────────
def test_execution_fill_can_be_journaled(tmp_path):
    reg = BrokerRegistry()
    reg.register(PaperConnector(lambda s: 60_000, starting_cash=1_000_000))
    svc = ExecutionService(reg, publish=lambda n, p: None, record_episode=lambda **k: 1)
    rec = Recommendation("BTC", Verdict.BUY, 0.8, RiskLevel.MEDIUM, 6000, 0.05, 12, 6, True, 1000)
    case = InvestmentCase(opportunity=Opportunity("BTC", OpportunityCategory.INVESTMENT,
                          "gh", "crypto", expected_roi=1.5, risk=0.3, strategic_fit=0.8,
                          urgency=0.7, time_horizon_months=12, capital_required_usd=1000,
                          sources=["gh"]), recommendation=rec)
    case.approve("ajay")
    intent = ExecutionIntent.from_case(case, broker="paper", account="m",
                                       symbol="BTC", quantity=0.1, now=clock())
    order = svc.execute(intent, clock())

    journal = _registry(tmp_path)
    j = journal.record_open(order, strategy=Strategy.RESEARCH_DRIVEN)
    assert j.intent_id == intent.intent_id
    assert j.position_size_usd == order.notional_usd
