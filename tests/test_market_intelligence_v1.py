"""M — MARKET_INTELLIGENCE_FUSION_AND_CATALYST_ENGINE tests (Phase 19).

Deterministic, no model, no network. Proves fusion, point-in-time / look-ahead
safety, degraded states, evidence traceability, and — critically — that no
trade-authority semantics or imports exist.
"""
from __future__ import annotations

import datetime as dt

from saathi.browser_research.intelligence import (
    ContradictionState, ResearchEvent, ResearchEventType, ResearchIntelligenceSnapshot,
)
from saathi.browser_research.freshness import Freshness
from saathi.browser_research.tiers import SourceTier
from saathi.market_intelligence import (
    CatalystPriority, FORBIDDEN_TRADE_TOKENS, MarketContextStatus, PortfolioContextStatus,
    RiskContextStatus, build_snapshot, central_command_projection, chat_answer, compute_market_reaction,
    fuse, voice_answer,
)

DAY = 86_400.0
PUB = dt.datetime(2024, 9, 12, tzinfo=dt.timezone.utc).timestamp()
NOW = dt.datetime(2024, 9, 13, tzinfo=dt.timezone.utc).timestamp()


def _event(**kw):
    d = dict(event_id="e1", event_type=ResearchEventType.DIVIDEND, market="NEPSE",
             headline="Dividend 20% [NABIL]", symbol="NABIL", event_date_raw="2024-09-12",
             event_date_normalized=PUB, source_tier=SourceTier.TIER_1_OFFICIAL,
             freshness=Freshness.RECENT, confidence=0.9, contradiction_state=ContradictionState.NONE,
             evidence_refs=["ev-1"], document_refs=[])
    d.update(kw)
    return ResearchEvent(**d)


def _bars(symbol):
    # sessions around PUB; available_at drives point-in-time selection
    return [
        {"available_at": PUB - 2 * DAY, "close": "100", "volume": "1000", "session_date": "2024-09-10"},
        {"available_at": PUB - 1 * DAY, "close": "102", "volume": "1100", "session_date": "2024-09-11"},
        {"available_at": PUB + 1 * DAY, "close": "108", "volume": "2200", "session_date": "2024-09-13"},
        {"available_at": PUB + 2 * DAY, "close": "110", "volume": "1500", "session_date": "2024-09-14"},
    ]


# 1 + 2 — mapping ResearchEvent → CatalystEvent
def test_fuse_mapping():
    c = fuse(_event())
    assert c.research_event_id == "e1" and c.event_type == ResearchEventType.DIVIDEND
    assert c.symbol == "NABIL" and c.evidence_refs == ["ev-1"]
    assert c.source_tier == SourceTier.TIER_1_OFFICIAL


# 5 + 6 — market reaction from canonical reader (point-in-time)
def test_market_reaction_point_in_time():
    c = fuse(_event(), reader=_bars)
    mc = c.market_context
    assert mc.status == MarketContextStatus.OK
    assert mc.price_before == "102" and mc.price_after == "108"   # last-before / first-after PUB
    assert mc.percentage_change == "5.88%"


# 7 — look-ahead prevention: a bar available at/before publication is NEVER "after"
def test_look_ahead_prevention():
    mc = compute_market_reaction("NABIL", PUB, reader=_bars)
    assert float(mc.price_before) <= 102 and float(mc.price_after) >= 108
    # if we move publication AFTER all bars → no 'after' → INSUFFICIENT_HISTORY (never a past bar)
    mc2 = compute_market_reaction("NABIL", PUB + 10 * DAY, reader=_bars)
    assert mc2.status == MarketContextStatus.INSUFFICIENT_HISTORY


# 8 — after-close publication uses the next available session as 'after'
def test_after_close_publication():
    # publication exactly at a before-session availability still treats strictly-after as after
    mc = compute_market_reaction("NABIL", PUB - 1 * DAY, reader=_bars)
    assert mc.status == MarketContextStatus.OK and mc.price_before == "102" and mc.price_after == "108"


# 9 — missing history
def test_missing_history():
    mc = compute_market_reaction("NABIL", PUB - 100 * DAY, reader=_bars)
    assert mc.status == MarketContextStatus.INSUFFICIENT_HISTORY


# 18 — degraded: no reader / no data / unresolved symbol / ts
def test_degraded_states():
    assert compute_market_reaction("NABIL", PUB, reader=None).status == MarketContextStatus.MARKET_DATA_UNAVAILABLE
    assert compute_market_reaction("NABIL", PUB, reader=lambda s: []).status == MarketContextStatus.MARKET_DATA_UNAVAILABLE
    assert compute_market_reaction("", PUB, reader=_bars).status == MarketContextStatus.SYMBOL_UNRESOLVED
    assert compute_market_reaction("NABIL", None, reader=_bars).status == MarketContextStatus.TIMESTAMP_UNRESOLVED


# 11 + 12 — portfolio relevance / unavailable
def test_portfolio_context():
    c = fuse(_event(), holdings={"NABIL": {"quantity": "100", "weight": "25%", "value": "250000"}})
    assert c.portfolio_context.status == PortfolioContextStatus.OK and c.portfolio_context.portfolio_relevant
    c2 = fuse(_event())  # no holdings supplied
    assert c2.portfolio_context.status == PortfolioContextStatus.PORTFOLIO_CONTEXT_UNAVAILABLE
    c3 = fuse(_event(symbol="SCB"), holdings={"NABIL": {}})
    assert c3.portfolio_context.status == PortfolioContextStatus.NOT_HELD


# 13 — read-only risk projection (concentration), no TG execution path
def test_risk_context():
    c = fuse(_event(), holdings={"NABIL": {"weight": "25%"}})
    assert c.risk_context.status == RiskContextStatus.OK and "concentration" in c.risk_context.concentration_note
    c2 = fuse(_event())
    assert c2.risk_context.status == RiskContextStatus.RISK_CONTEXT_UNAVAILABLE


# 14 + 15 — priority + reasons
def test_priority_and_reasons():
    c = fuse(_event(), reader=_bars, holdings={"NABIL": {"weight": "25%"}})
    assert c.catalyst_priority == CatalystPriority.HIGH and c.priority_reasons
    low = fuse(_event(source_tier=SourceTier.TIER_6_UNKNOWN, freshness=Freshness.STALE,
                      event_type=ResearchEventType.OTHER, document_refs=[]))
    assert low.catalyst_priority in (CatalystPriority.LOW, CatalystPriority.MEDIUM)


# 16 — contradiction preserved
def test_contradiction_preserved():
    c = fuse(_event(contradiction_state=ContradictionState.UNCONFIRMED_MULTI_SOURCE))
    assert c.contradiction_state == ContradictionState.UNCONFIRMED_MULTI_SOURCE


# 17 — evidence traceability
def test_evidence_traceability():
    c = fuse(_event(evidence_refs=["a", "b"]))
    assert c.evidence_refs == ["a", "b"] and c.research_event_id == "e1"


# 20 — NEGATIVE: no trade-authority tokens anywhere in output
def test_no_trade_authority_language():
    snap = build_snapshot(ResearchIntelligenceSnapshot(
        snapshot_id="s", generated_at=NOW, market="NEPSE",
        events=[_event(), _event(event_id="e2", symbol="SCB", event_type=ResearchEventType.RIGHTS_ISSUE)]),
        reader=_bars, holdings={"NABIL": {"weight": "25%"}}, now=NOW)
    blob = (str(snap.as_dict()) + str(central_command_projection(snap))
            + str(chat_answer(snap, "what changed")) + voice_answer(snap)
            + str([c.priority_reasons for c in snap.catalysts])).lower()
    for tok in FORBIDDEN_TRADE_TOKENS:
        # allow the disclaimer phrase 'not investment advice' but no actionable directives
        assert tok not in blob, f"forbidden trade token present: {tok}"


# 21 — authority imports audit (zero execution/trade/broker/portfolio-write/market_data-write)
def test_no_authority_imports():
    import saathi.market_intelligence.catalyst as m1
    import saathi.market_intelligence.market_reaction as m2
    import saathi.market_intelligence.fusion as m3
    for mod in (m1, m2, m3):
        imports = [l for l in open(mod.__file__).read().splitlines()
                   if l.strip().startswith(("import ", "from "))]
        blob = "\n".join(imports)
        for banned in ("execution.gateway", "trading_guardian", "broker",
                       "portfolio_construction", "portfolio_risk", "market_data.store",
                       "market_data.ingest"):
            assert banned not in blob, f"{banned} imported by {mod.__name__}"


# 22 — snapshot + projections
def test_snapshot_and_projections():
    snap = build_snapshot(ResearchIntelligenceSnapshot(
        snapshot_id="s", generated_at=NOW, market="NEPSE",
        events=[_event(), _event(event_id="e2", symbol="SCB")]), reader=_bars, now=NOW)
    d = snap.as_dict()
    assert d["schema"] == "market_intelligence.snapshot.v1" and len(d["catalysts"]) == 2
    cc = central_command_projection(snap)
    assert cc["read_only"] and "high_priority_catalysts" in cc
    ans = chat_answer(snap, "what important market events today")
    assert ans["supported"]
    assert isinstance(voice_answer(snap), str)


# 23 — MARKET_DATA_UNAVAILABLE snapshot (real NEPSE state: no feed)
def test_market_data_unavailable_snapshot():
    snap = build_snapshot(ResearchIntelligenceSnapshot(
        snapshot_id="s", generated_at=NOW, market="NEPSE", events=[_event()]), reader=None, now=NOW)
    assert snap.market_data_health["status"] == "MARKET_DATA_UNAVAILABLE"
    assert any("MARKET_DATA_UNAVAILABLE" in l for l in snap.limitations)
    assert snap.catalysts[0].market_context.status == MarketContextStatus.MARKET_DATA_UNAVAILABLE
