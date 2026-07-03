"""Investment Learning Runtime tests (M5 Phase 7) — journals → M2 proposals.

Learning proposes, never mutates (AP-18/20): proposals land in the M2
CapabilityImprovementRegistry as PROPOSED, never auto-implemented.
Deterministic (AP-17); registry/clock/io injected (AP-12).
"""
import itertools

from saathi.learning.registry import CapabilityImprovementRegistry, ImprovementStatus
from saathi.trade_journal import (
    TradeJournal, TradeStatus, Strategy, ExitReason, MarketContext,
    ResearchAttribution, PortfolioAttribution,
)
from saathi.investment_learning import InvestmentLearningRuntime

_ids = itertools.count(1)


def _journal(*, pnl, strategy=Strategy.MOMENTUM, regime="bull",
             research=None, health_before=0.0, health_after=0.0):
    """A CLOSED journal with the fields learning cares about."""
    entry, qty = 100.0, 10.0
    exit_price = entry + pnl / qty
    return TradeJournal(
        journal_id=f"j{next(_ids)}", case_id="c", intent_id="i", broker="paper",
        asset="BTC", asset_class="crypto", strategy=strategy, quantity=qty,
        entry_price=entry, position_size_usd=entry * qty, fees_usd=0.0,
        opened_at=0.0, status=TradeStatus.CLOSED, exit_price=exit_price,
        exit_reason=ExitReason.MANUAL, closed_at=100.0, duration_s=100.0,
        pnl_usd=pnl, return_pct=round(pnl / (entry * qty), 4),
        market=MarketContext(regime=regime),
        research=research or ResearchAttribution(),
        portfolio=PortfolioAttribution(health_before=health_before, health_after=health_after))


def _runtime(tmp_path, events=None, episodes=None, min_sample=3):
    reg = CapabilityImprovementRegistry(tmp_path / "imp.db", now=lambda: 1.0)
    rt = InvestmentLearningRuntime(
        reg, min_sample=min_sample, now=lambda: 1.0,
        publish=lambda n, p: (events if events is not None else []).append((n, p)),
        record_episode=lambda **kw: (episodes if episodes is not None else []).append(kw) or 1)
    return rt, reg


# ── Performance + strategy scores ──────────────────────────────────────────
def test_learn_produces_performance_and_strategy_scores(tmp_path):
    rt, _ = _runtime(tmp_path)
    journals = [_journal(pnl=p, strategy=Strategy.MOMENTUM) for p in (100, 200, -50)] + \
               [_journal(pnl=p, strategy=Strategy.MEAN_REVERSION) for p in (-80, -40, 10)]
    result = rt.learn(journals)
    assert result.performance.trades == 6
    assert Strategy.MOMENTUM.value in result.strategy_scores
    assert Strategy.MEAN_REVERSION.value in result.strategy_scores


# ── Research accuracy: predictive agents score higher ──────────────────────
def test_research_accuracy_rewards_predictive_agents(tmp_path):
    rt, _ = _runtime(tmp_path)
    # winners have strong fundamentals + weak sentiment; losers the reverse
    winners = [_journal(pnl=150, research=ResearchAttribution(fundamentals=90, sentiment=20))
               for _ in range(4)]
    losers = [_journal(pnl=-150, research=ResearchAttribution(fundamentals=30, sentiment=90))
              for _ in range(4)]
    result = rt.learn(winners + losers)
    acc = {r.agent: r.predictive_accuracy for r in result.research_accuracy}
    assert acc["fundamentals"] == 1.0      # signalled positive iff it won
    assert acc["sentiment"] == 0.0         # signalled positive exactly when it lost


# ── Improvement proposals land in M2 registry as PROPOSED (never applied) ──
def test_proposals_are_submitted_but_not_implemented(tmp_path):
    rt, reg = _runtime(tmp_path)
    winners = [_journal(pnl=150, research=ResearchAttribution(fundamentals=90, sentiment=20))
               for _ in range(5)]
    losers = [_journal(pnl=-150, research=ResearchAttribution(fundamentals=30, sentiment=90))
              for _ in range(5)]
    result = rt.learn(winners + losers)
    assert result.proposals                              # at least one proposal
    # research reweighting proposal present
    assert any(p["capability"] == "Research Confidence Framework" for p in result.proposals)
    # every proposal exists in the M2 registry and is only PROPOSED (AP-20)
    for p in result.proposals:
        stored = reg.get(p["id"])
        assert stored is not None
        assert stored.status is ImprovementStatus.PROPOSED


# ── Negative-expectancy strategy → reduce-weight proposal ──────────────────
def test_losing_strategy_triggers_reduction_proposal(tmp_path):
    rt, _ = _runtime(tmp_path)
    losing = [_journal(pnl=p, strategy=Strategy.MEAN_REVERSION) for p in (-100, -80, -120, -50)]
    result = rt.learn(losing)
    assert any("Reduce confidence weighting for mean_reversion" in p["improvement"]
               for p in result.proposals)


# ── Sentiment-only losing pattern → avoidance proposal ─────────────────────
def test_sentiment_only_losses_trigger_avoidance_proposal(tmp_path):
    rt, _ = _runtime(tmp_path)
    sent_losers = [_journal(pnl=-100, research=ResearchAttribution(
        sentiment=85, fundamentals=20, onchain=15)) for _ in range(4)]
    result = rt.learn(sent_losers)
    assert any(p["improvement"] == "Avoid sentiment-only opportunities"
               for p in result.proposals)
    assert any("Sentiment-only" in pat for pat in result.patterns)


# ── Regime learning: per (strategy, regime) win rates ──────────────────────
def test_regime_insights_tag_strategy_by_regime(tmp_path):
    rt, _ = _runtime(tmp_path)
    bull = [_journal(pnl=100, strategy=Strategy.MOMENTUM, regime="bull") for _ in range(3)]
    sideways = [_journal(pnl=-50, strategy=Strategy.MOMENTUM, regime="sideways") for _ in range(3)]
    result = rt.learn(bull + sideways)
    table = {(r.strategy, r.regime): r.win_rate for r in result.regime_insights}
    assert table[("momentum", "bull")] == 1.0
    assert table[("momentum", "sideways")] == 0.0


# ── Portfolio evaluation: allocations that changed portfolio health ────────
def test_portfolio_insights_flag_health_changes(tmp_path):
    rt, _ = _runtime(tmp_path)
    result = rt.learn([
        _journal(pnl=100, health_before=82, health_after=90),   # +8 improved
        _journal(pnl=50, health_before=90, health_after=84),    # -6 worsened
    ])
    joined = " ".join(result.portfolio_insights)
    assert "improved portfolio health" in joined
    assert "worsened portfolio health" in joined


# ── Event + episode emitted; empty input is safe ───────────────────────────
def test_emits_event_and_episode_and_handles_empty(tmp_path):
    events, episodes = [], []
    rt, _ = _runtime(tmp_path, events, episodes)
    rt.learn([_journal(pnl=100) for _ in range(3)])
    assert events[-1][0] == "investment.learning_completed"
    assert episodes[-1]["intent"] == "investment_learning_pass"
    # empty → no crash, no proposals
    empty = InvestmentLearningRuntime(
        CapabilityImprovementRegistry(tmp_path / "e.db", now=lambda: 1.0),
        publish=lambda n, p: None, record_episode=lambda **k: 1)
    assert empty.learn([]).proposals == []
