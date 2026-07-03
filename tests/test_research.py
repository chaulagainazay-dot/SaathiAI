"""Research Department tests (M5 Phase 1) — evidence source + Confidence Framework.

Deterministic (AP-17), injected collectors/clock/publisher/recorder (AP-12) —
no network, no real clock, no LLM.
"""
from saathi.research import (
    ResearchCategory, Evidence, score_confidence,
    fundamental_intelligence, onchain_intelligence, technical_intelligence,
    project_intelligence, sentiment_intelligence, news_intelligence,
    market_intelligence, ResearchDepartment, CONFIDENCE_WEIGHTS,
)

T0 = 1_000_000.0                       # fixed "now"
def clock():
    return T0


def _ev(cat, metric, score, source, age_s=0.0):
    return Evidence(cat, metric, score, source, T0 - age_s)


# ── Confidence weights are a valid distribution ────────────────────────────
def test_confidence_weights_sum_to_one():
    assert abs(sum(CONFIDENCE_WEIGHTS.values()) - 1.0) < 1e-9


# ── Weighted overall + full coverage ───────────────────────────────────────
def test_overall_is_weighted_over_present_categories():
    ev = [
        _ev(ResearchCategory.FUNDAMENTALS, "revenue", 90, "sec"),
        _ev(ResearchCategory.ONCHAIN, "tvl", 80, "defillama"),
        _ev(ResearchCategory.TECHNICAL, "momentum", 60, "ta"),
        _ev(ResearchCategory.TEAM_GITHUB, "commits", 100, "github"),
        _ev(ResearchCategory.SENTIMENT, "reddit", 50, "reddit"),
        _ev(ResearchCategory.RISK, "drawdown", 70, "risk"),
    ]
    c = score_confidence("PEPE", ev, now=T0)
    # 0.30*90 + 0.20*80 + 0.15*60 + 0.15*100 + 0.10*50 + 0.10*70 = 79.0
    assert c.overall == 79.0
    assert c.coverage == 1.0
    assert c.missing_evidence == []
    assert c.source_count == 6
    assert c.actionable is True


# ── Missing evidence surfaced; overall renormalizes over present ───────────
def test_missing_categories_are_reported_and_renormalized():
    ev = [
        _ev(ResearchCategory.FUNDAMENTALS, "revenue", 80, "sec"),
        _ev(ResearchCategory.ONCHAIN, "tvl", 60, "defillama"),
    ]
    c = score_confidence("X", ev, now=T0)
    # present weight = 0.50; overall = (0.30*80 + 0.20*60)/0.50 = 72.0
    assert c.overall == 72.0
    assert c.coverage == 0.5
    assert set(c.missing_evidence) == {
        ResearchCategory.TECHNICAL, ResearchCategory.TEAM_GITHUB,
        ResearchCategory.SENTIMENT, ResearchCategory.RISK,
    }
    assert c.actionable is True          # 50% coverage + hard evidence present


# ── Guardrail: sentiment is NEVER a sole basis ─────────────────────────────
def test_sentiment_only_is_not_actionable():
    ev = [
        _ev(ResearchCategory.SENTIMENT, "reddit", 95, "reddit"),
        _ev(ResearchCategory.SENTIMENT, "x", 90, "twitter"),
        _ev(ResearchCategory.NEWS, "hype", 88, "cryptopanic"),
    ]
    c = score_confidence("MOONcoin", ev, now=T0)
    assert c.actionable is False         # no fundamentals/on-chain → not actionable


# ── Contradiction detection lowers trust ───────────────────────────────────
def test_conflicting_sources_flag_contradiction():
    ev = [
        _ev(ResearchCategory.FUNDAMENTALS, "revenue", 90, "sourceA"),
        _ev(ResearchCategory.FUNDAMENTALS, "revenue", 30, "sourceB"),   # disagree
        _ev(ResearchCategory.ONCHAIN, "tvl", 70, "defillama"),
    ]
    c = score_confidence("Y", ev, now=T0)
    assert any("revenue" in s for s in c.contradictions)


# ── Freshness horizon flags stale evidence ─────────────────────────────────
def test_stale_evidence_flagged():
    ev = [
        _ev(ResearchCategory.FUNDAMENTALS, "revenue", 80, "sec", age_s=0),
        _ev(ResearchCategory.ONCHAIN, "tvl", 70, "defillama", age_s=200_000),  # >24h
    ]
    c = score_confidence("Z", ev, now=T0)
    assert "tvl" in c.stale_metrics
    assert "revenue" not in c.stale_metrics


# ── Agents normalize collector output into categorized Evidence ────────────
def test_agent_tags_evidence_with_its_category():
    agent = fundamental_intelligence(
        collect=lambda subject: [("revenue", 88.0, "sec"), ("cashflow", 76.0, "10k")],
        now=clock)
    ev = agent.research("SolidCo")
    assert all(e.category is ResearchCategory.FUNDAMENTALS for e in ev)
    assert {e.metric for e in ev} == {"revenue", "cashflow"}
    assert all(e.collected_at == T0 for e in ev)


# ── Department orchestrates agents, publishes, records an episode ───────────
def test_department_gathers_publishes_and_records_episode():
    events = []
    episodes = []
    agents = [
        fundamental_intelligence(lambda s: [("revenue", 90, "sec")], now=clock),
        onchain_intelligence(lambda s: [("tvl", 85, "defillama")], now=clock),
        technical_intelligence(lambda s: [("momentum", 70, "ta")], now=clock),
        project_intelligence(lambda s: [("commits", 95, "github")], now=clock),
        sentiment_intelligence(lambda s: [("reddit", 60, "reddit")], now=clock),
    ]
    dept = ResearchDepartment(
        agents, now=clock,
        publish=lambda name, payload: events.append((name, payload)),
        record_episode=lambda **kw: episodes.append(kw) or len(episodes))

    report = dept.research("Bittensor")

    assert len(report.evidence) == 5
    assert events[0][0] == "research.completed"
    assert events[0][1]["subject"] == "Bittensor"
    assert episodes[0]["intent"] == "research_pass"
    assert episodes[0]["department"] == "investment"
    assert episodes[0]["outcome"] == "success"       # hard evidence + coverage
    assert 0.0 <= episodes[0]["quality_score"] <= 1.0


def test_department_records_insufficient_when_sentiment_only():
    episodes = []
    agents = [
        sentiment_intelligence(lambda s: [("reddit", 95, "reddit")], now=clock),
        news_intelligence(lambda s: [("hype", 90, "news")], now=clock),
        market_intelligence(lambda s: [("btc_trend", 70, "cmc")], now=clock),
    ]
    dept = ResearchDepartment(
        agents, now=clock,
        publish=lambda n, p: None,
        record_episode=lambda **kw: episodes.append(kw) or 1)
    report = dept.research("HypeCoin")
    assert report.confidence.actionable is False
    assert episodes[0]["outcome"] == "insufficient_evidence"
