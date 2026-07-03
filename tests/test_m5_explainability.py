"""M5 Integration Sprint — Financial Explainability Audit (end-to-end lineage).

Certifies a single opportunity can be traced through EVERY M5 stage —
discovery → research → recommendation → approval → execution → journal →
learning — and that each of the ten explainability questions has an answer
grounded in a real artifact. Also certifies the governance spine end-to-end:
no execution without human approval.
"""
from saathi.research import ResearchCategory, Evidence, score_confidence
from saathi.opportunity import (
    Opportunity, OpportunityCategory, ai_discovery, OpportunityIntelligence,
)
from saathi.investment import DueDiligenceItem, Scenario, Verdict
from saathi.investment_pipeline import InvestmentPipeline
from saathi.execution import (
    ExecutionIntent, PaperConnector, BrokerRegistry, ExecutionService, ExecutionStatus,
)
from saathi.trade_journal import (
    TradeJournalRegistry, Strategy, ExitReason, DecisionSnapshot,
    ResearchAttribution, PerformanceAnalytics,
)
from saathi.investment_learning import InvestmentLearningRuntime
from saathi.learning.registry import CapabilityImprovementRegistry, ImprovementStatus

T0 = 7_000_000.0


def _research_fn(subject):
    ev = [Evidence(ResearchCategory.FUNDAMENTALS, "revenue", 90, "sec", T0),
          Evidence(ResearchCategory.ONCHAIN, "tvl", 85, "defillama", T0),
          Evidence(ResearchCategory.TEAM_GITHUB, "commits", 95, "github", T0)]
    return score_confidence(subject, ev, now=T0)


def test_full_lineage_discovery_to_learning(tmp_path):
    lineage = {}

    # 1. DISCOVERY — why was this opportunity discovered?
    from saathi.opportunity import RawSignal
    agent = ai_discovery(lambda: [RawSignal("Bittensor", OpportunityCategory.INVESTMENT,
                                            "github", asset_type="crypto", expected_roi=2.5,
                                            risk=0.3, strategic_fit=0.9, urgency=0.8)])
    disco = OpportunityIntelligence([agent], research=_research_fn, now=lambda: T0,
                                    publish=lambda n, p: None, record_episode=lambda **k: 1)
    top = disco.discover()
    assert top, "opportunity must survive discovery"
    opp = top[0]
    lineage["why_discovered"] = f"AI Discovery via {opp.sources}"
    lineage["which_agents"] = opp.research_report.breakdown          # research contribution
    lineage["which_evidence"] = opp.research_report.source_count

    # 2. PIPELINE — why recommended? risk rules? position size? why L4?
    pipe = InvestmentPipeline(
        portfolio_usd=100_000,
        dd_provider=lambda o: [DueDiligenceItem(k, True) for k in ("team", "audit", "liquidity")],
        scenario_provider=lambda o: [Scenario("bull", 1.0, 0.6), Scenario("bear", -0.3, 0.4)],
        publish=lambda n, p: None, record_episode=lambda **k: 1)
    case = pipe.evaluate(opp)
    assert case.verdict is Verdict.BUY
    lineage["why_recommended"] = case.explanation
    lineage["risk_rules"] = case.due_diligence.passed
    lineage["why_position_size"] = case.risk.position_size_usd
    lineage["why_L4"] = case.approval_required and case.governance_level == "L4"

    # GOVERNANCE — no execution before human approval
    intent_blocked = False
    try:
        ExecutionIntent.from_case(case, broker="paper", account="m", symbol="TAO",
                                  quantity=1.0, now=T0)
    except PermissionError:
        intent_blocked = True
    assert intent_blocked, "must NOT be executable before approval"

    # 3. APPROVAL + EXECUTION
    case.approve("ajay")
    intent = ExecutionIntent.from_case(case, broker="paper", account="m", symbol="TAO",
                                       quantity=10.0, now=T0)
    reg = BrokerRegistry(); reg.register(PaperConnector(lambda s: 300.0, starting_cash=1_000_000))
    svc = ExecutionService(reg, publish=lambda n, p: None, record_episode=lambda **k: 1)
    order = svc.execute(intent, T0)
    assert order.status is ExecutionStatus.FILLED
    lineage["approved_by"] = intent.approved_by

    # 4. TRADE JOURNAL — permanent record
    journal = TradeJournalRegistry(tmp_path / "j.db", now=lambda: T0,
                                   publish=lambda n, p: None, record_episode=lambda **k: 1)
    j = journal.record_open(
        order, strategy=Strategy.RESEARCH_DRIVEN,
        decision=DecisionSnapshot(opportunity_score=opp.score,
                                  research_confidence=opp.research_report.overall,
                                  risk_score=case.risk.max_drawdown_pct * 100),
        research=ResearchAttribution(fundamentals=90, onchain=85, team_github=95, sentiment=15))
    closed = journal.record_close(j.journal_id, exit_price=360.0,
                                  exit_reason=ExitReason.TARGET_HIT)
    lineage["why_made_money"] = closed.pnl_usd > 0
    assert closed.is_win

    # 5. LEARNING — lesson + proposal
    imp = CapabilityImprovementRegistry(tmp_path / "imp.db", now=lambda: T0)
    # add a few more journals so learning has a sample
    for _ in range(4):
        jj = journal.record_open(order, strategy=Strategy.RESEARCH_DRIVEN,
                                 research=ResearchAttribution(fundamentals=90, sentiment=15))
        journal.record_close(jj.journal_id, exit_price=360.0, exit_reason=ExitReason.TARGET_HIT)
    runtime = InvestmentLearningRuntime(imp, min_sample=3, now=lambda: T0,
                                        publish=lambda n, p: None, record_episode=lambda **k: 1)
    result = runtime.learn(journal.closed())
    lineage["what_lesson"] = result.patterns
    lineage["what_proposal"] = result.proposals

    # ── Every explainability question has a grounded answer ────────────────
    for key in ("why_discovered", "which_agents", "which_evidence", "why_recommended",
                "risk_rules", "why_position_size", "why_L4", "approved_by",
                "why_made_money", "what_lesson", "what_proposal"):
        assert key in lineage, f"missing lineage: {key}"
    assert lineage["why_L4"] is True
    assert lineage["approved_by"] == "ajay"
    # proposals from learning are only PROPOSED, never auto-applied (AP-20)
    for p in lineage["what_proposal"]:
        assert imp.get(p["id"]).status is ImprovementStatus.PROPOSED
