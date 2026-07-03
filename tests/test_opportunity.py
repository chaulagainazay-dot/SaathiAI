"""Opportunity Intelligence tests (M5 Phase 2) — universal discovery pipeline.

Deterministic (AP-17); scanners / research / clock / io injected (AP-12).
"""
from saathi.research import ResearchCategory, Evidence, score_confidence
from saathi.opportunity import (
    OpportunityCategory, OpportunityStatus, RawSignal, Opportunity, dedupe_key,
    crypto_discovery, ai_discovery, revenue_discovery,
    OpportunityMemory, OpportunityIntelligence,
)

T0 = 2_000_000.0
def clock():
    return T0


def _research(actionable=True, overall=80.0, sources=6):
    """Fake research: build a real ResearchConfidence with the desired shape."""
    def fn(subject):
        if actionable:                    # two hard categories → coverage 0.5, actionable
            ev = [Evidence(ResearchCategory.FUNDAMENTALS, "rev", overall, f"f{i}", T0)
                  for i in range(sources)]
            ev += [Evidence(ResearchCategory.ONCHAIN, "tvl", overall, f"o{i}", T0)
                   for i in range(sources)]
        else:                             # sentiment-only → not actionable
            ev = [Evidence(ResearchCategory.SENTIMENT, "hype", 95, f"s{i}", T0)
                  for i in range(sources)]
        return score_confidence(subject, ev, now=T0)
    return fn


# ── Dedupe key collapses release-phrasing variants ─────────────────────────
def test_dedupe_key_collapses_variants():
    assert dedupe_key("GPT-X released") == dedupe_key("GPT-X announced") == dedupe_key("GPT-X available")


# ── Opportunity score follows the formula ──────────────────────────────────
def test_score_formula_penalizes_risk_rewards_confidence():
    safe = Opportunity("A", OpportunityCategory.AI, "gh", "model", expected_roi=2.0,
                       risk=0.2, strategic_fit=0.9, urgency=0.8,
                       time_horizon_months=6, capital_required_usd=0,
                       confidence=0.9, evidence_quality=1.0)
    risky = Opportunity("B", OpportunityCategory.AI, "gh", "model", expected_roi=2.0,
                        risk=0.9, strategic_fit=0.9, urgency=0.8,
                        time_horizon_months=6, capital_required_usd=0,
                        confidence=0.4, evidence_quality=0.4)
    assert safe.score > risky.score


# ── Deduplication merges three agents' signals into one opportunity ────────
def test_pipeline_deduplicates_across_agents():
    gh = ai_discovery(lambda: [RawSignal("GPT-X released", OpportunityCategory.AI,
                                          "github", expected_roi=1.0, strategic_fit=0.6)])
    news = ai_discovery(lambda: [RawSignal("GPT-X announced", OpportunityCategory.AI,
                                           "news", expected_roi=1.2, strategic_fit=0.8)],
                        name="News")
    twitter = ai_discovery(lambda: [RawSignal("GPT-X available", OpportunityCategory.AI,
                                              "twitter", urgency=0.9)], name="Twitter")
    dept = OpportunityIntelligence([gh, news, twitter], research=_research(),
                                   now=clock, publish=lambda n, p: None,
                                   record_episode=lambda **kw: 1)
    top = dept.discover()
    assert len(top) == 1                                  # merged, not three
    merged = top[0]
    assert set(merged.sources) == {"github", "news", "twitter"}
    assert merged.expected_roi == 1.2                     # strongest estimate kept
    assert merged.strategic_fit == 0.8
    assert merged.urgency == 0.9


# ── Non-actionable (sentiment-only) research → REJECTED, ranked out ─────────
def test_sentiment_only_opportunity_is_rejected():
    agent = crypto_discovery(lambda: [RawSignal("HypeCoin", OpportunityCategory.INVESTMENT,
                                                "cmc", expected_roi=5.0, risk=0.9)])
    dept = OpportunityIntelligence([agent], research=_research(actionable=False),
                                   now=clock, publish=lambda n, p: None,
                                   record_episode=lambda **kw: 1)
    top = dept.discover()
    assert top == []                                      # rejected → not ranked


# ── Ranking + episode/event emission ───────────────────────────────────────
def test_ranks_and_emits_episode():
    events, episodes = [], []
    strong = crypto_discovery(lambda: [RawSignal("Bittensor", OpportunityCategory.INVESTMENT,
                                                 "gh", expected_roi=3.0, risk=0.3,
                                                 strategic_fit=0.9, urgency=0.8)])
    weak = revenue_discovery(lambda: [RawSignal("Affiliate deal", OpportunityCategory.REVENUE,
                                                "partner", expected_roi=0.3, risk=0.4,
                                                strategic_fit=0.5, urgency=0.4)])
    dept = OpportunityIntelligence([strong, weak], research=_research(),
                                   now=clock, publish=lambda n, p: events.append((n, p)),
                                   record_episode=lambda **kw: episodes.append(kw) or 1)
    top = dept.discover()
    assert [o.title for o in top] == ["Bittensor", "Affiliate deal"]
    assert events[0][0] == "opportunity.discovered"
    assert episodes[0]["intent"] == "daily_discovery"


# ── Opportunity Memory: never forget; resurrect on improvement ─────────────
def test_memory_resurrects_previously_rejected(tmp_path):
    mem = OpportunityMemory(tmp_path / "opps.db", now=clock)
    key = dedupe_key("Project X")

    # January: weak, rejected then monitored
    weak = Opportunity("Project X", OpportunityCategory.INVESTMENT, "gh", "token",
                       expected_roi=0.5, risk=0.8, strategic_fit=0.4, urgency=0.3,
                       time_horizon_months=12, capital_required_usd=0,
                       confidence=0.4, evidence_quality=0.4,
                       status=OpportunityStatus.REJECTED)
    mem.remember(weak)
    mem.monitor_rejected(mem.get(key))
    assert mem.get(key).status is OpportunityStatus.MONITORING

    # March: developer activity up, funding announced, TVL doubled → much stronger
    # (same entity re-observed → same dedupe key → resurrection, not a new record)
    strong = Opportunity("Project X", OpportunityCategory.INVESTMENT,
                         "news", "token", expected_roi=2.5, risk=0.3, strategic_fit=0.9,
                         urgency=0.9, time_horizon_months=12, capital_required_usd=0,
                         confidence=0.9, evidence_quality=1.0)
    stored = mem.remember(strong)
    assert stored.status is OpportunityStatus.RESURRECTED
    assert stored.first_seen == weak.first_seen           # same opportunity, kept alive


def test_memory_persists_and_keeps_first_seen(tmp_path):
    mem = OpportunityMemory(tmp_path / "o.db", now=clock)
    opp = Opportunity("Solid Repo", OpportunityCategory.AI, "gh", "repo",
                      expected_roi=1.0, risk=0.3, strategic_fit=0.7, urgency=0.6,
                      time_horizon_months=6, capital_required_usd=0,
                      confidence=0.8, evidence_quality=0.8)
    mem.remember(opp)
    again = OpportunityMemory(tmp_path / "o.db", now=clock)   # reopen
    loaded = again.get(dedupe_key("Solid Repo"))
    assert loaded is not None
    assert loaded.title == "Solid Repo"
    assert loaded.first_seen == T0
