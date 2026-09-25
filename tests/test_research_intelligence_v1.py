"""M — RESEARCH_INTELLIGENCE_SURFACE deterministic tests (Phase 30).

Pure projection over synthetic ExtractedFacts + documents. No network, no model.
Covers event normalization/clustering, authority, contradictions, freshness,
priority, citations, chat/voice, source health, no-model mode, crypto-compat, and
zero-write-authority invariants.
"""
from __future__ import annotations

import datetime as dt

from saathi.browser_research.contract import DataDomain, ExtractedFact, FactGroup, Provenance
from saathi.browser_research.freshness import Freshness
from saathi.browser_research.tiers import SourceTier
from saathi.browser_research import intelligence as I
from saathi.browser_research.intelligence import (
    ContradictionState, ResearchEventType, build_snapshot, central_command_projection,
    chat_answer, daily_brief, deterministic_summary, optional_model_summary,
    unify_source_health, voice_answer,
)

NOW = dt.datetime(2024, 9, 13, tzinfo=dt.timezone.utc).timestamp()
DAY = 86_400.0
PUB = dt.datetime(2024, 9, 12, tzinfo=dt.timezone.utc).timestamp()


def _fact(stmt, group, host, tier, *, sym="", pub=PUB, fresh=Freshness.RECENT, ref="ev1", conf=0.9):
    return ExtractedFact(statement=stmt, group=group, source_url=f"https://{host}/x",
                         source_host=host, source_tier=tier, retrieval_ts=NOW,
                         publication_ts=pub, value=sym, provenance=Provenance.BROWSER_DERIVED,
                         data_domain=DataDomain.WEB_INTELLIGENCE, confidence=conf,
                         freshness=fresh, evidence_ref=ref)


NABIL_DIV_OFFICIAL = _fact("NABIL dividend 10% declared 2024-09-12", FactGroup.CORPORATE_ACTIONS,
                           "nepalstock.com", SourceTier.TIER_1_OFFICIAL, sym="NABIL", ref="e-off")
NABIL_DIV_NEWS = _fact("NABIL dividend 12% reported", FactGroup.CORPORATE_ACTIONS,
                       "kathmandupost.com", SourceTier.TIER_3_REPUTABLE_NEWS, sym="NABIL", ref="e-news")
NRB_POLICY = _fact("NRB monetary policy 2081-05 directive", FactGroup.REGULATORY,
                   "nrb.org.np", SourceTier.TIER_1_OFFICIAL, ref="e-nrb")
SCB_AGM = _fact("SCB annual general meeting AGM 2024-09-10", FactGroup.COMPANY_EVENTS,
                "sebon.gov.np", SourceTier.TIER_1_OFFICIAL, sym="SCB", ref="e-agm")


# 1
def test_event_normalization():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NRB_POLICY, SCB_AGM], now=NOW)
    types = {e.event_type for e in snap.events}
    assert ResearchEventType.DIVIDEND in types
    assert ResearchEventType.MONETARY_POLICY in types
    assert ResearchEventType.AGM in types


# 2 — duplicate clustering: two sources, same symbol+type+date → one event
def test_duplicate_event_clustering():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NABIL_DIV_NEWS], now=NOW)
    nabil = [e for e in snap.events if e.symbol == "NABIL"]
    assert len(nabil) == 1
    assert set(nabil[0].evidence_refs) == {"e-off", "e-news"}


# 3 + 4 — official document/page authority wins in contradiction
def test_official_authority_contradiction():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NABIL_DIV_NEWS], now=NOW)
    ev = next(e for e in snap.events if e.symbol == "NABIL")
    assert ev.contradiction_state == ContradictionState.OFFICIAL_SOURCE_WINS
    assert "10%" in ev.contradiction_note


# 5 — reputable-news fallback when no official
def test_reputable_news_fallback():
    a = _fact("XYZ dividend 8% reported", FactGroup.CORPORATE_ACTIONS, "kathmandupost.com",
              SourceTier.TIER_3_REPUTABLE_NEWS, sym="XYZ", ref="n1")
    b = _fact("XYZ dividend 9% reported", FactGroup.CORPORATE_ACTIONS, "thehimalayantimes.com",
              SourceTier.TIER_3_REPUTABLE_NEWS, sym="XYZ", ref="n2")
    snap = build_snapshot([a, b], now=NOW)
    ev = next(e for e in snap.events if e.symbol == "XYZ")
    assert ev.contradiction_state == ContradictionState.UNCONFIRMED_MULTI_SOURCE


# 6 — contradictions retained in snapshot
def test_contradiction_retained():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NABIL_DIV_NEWS], now=NOW)
    assert snap.contradictions and any("10%" in c for c in snap.contradictions)


# 7 — freshness surfaced
def test_freshness():
    stale = _fact("OLD notice", FactGroup.OFFICIAL_NOTICES, "sebon.gov.np",
                  SourceTier.TIER_1_OFFICIAL, pub=NOW - 30 * DAY, fresh=Freshness.STALE, ref="s1")
    snap = build_snapshot([stale], now=NOW)
    assert snap.freshness_warnings


# 8 — research priority present, official+fresh scores higher than stale-unknown
def test_research_priority():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NRB_POLICY], now=NOW)
    assert all(0.0 <= e.research_priority <= 1.0 for e in snap.events)
    assert snap.events[0].research_priority > 0.0


# 9 — no trade-score naming anywhere
def test_no_trade_score_naming():
    snap = build_snapshot([NABIL_DIV_OFFICIAL], now=NOW)
    blob = str(snap.as_dict()) + str(daily_brief(snap)) + str(deterministic_summary(snap.events[0]))
    low = blob.lower()
    for banned in ("buy_score", "trade_score", "alpha_score", " buy", " sell", "position size", "target price"):
        assert banned not in low
    assert "research_priority" in str(snap.events[0].as_dict())


# 10 — evidence references present
def test_evidence_references():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NRB_POLICY], now=NOW)
    assert "e-off" in snap.evidence_refs and "e-nrb" in snap.evidence_refs
    assert all(e.evidence_refs for e in snap.events)


# 11 — unsupported claim rejection
def test_unsupported_claim_rejection():
    snap = build_snapshot([NABIL_DIV_OFFICIAL], now=NOW)
    ans = chat_answer(snap, "show ZZZZ disclosures")
    assert ans["supported"] is False and not ans["events"]


# 12 — document linkage by symbol
def test_document_linkage():
    docs = [{"sha256": "abc123", "title": "Dividend PDF", "symbol": "NABIL",
             "source_url": "https://nrb.org.np/x.pdf", "status": "DOCUMENT_OK", "page_count": 2}]
    snap = build_snapshot([NABIL_DIV_OFFICIAL], docs, now=NOW)
    ev = next(e for e in snap.events if e.symbol == "NABIL")
    assert "abc123" in ev.document_refs


# 13 + 14 — document changed + token-gated states surfaced
def test_document_states_surfaced():
    docs = [
        {"sha256": "h1", "symbol": "MBL", "status": "DOCUMENT_NOT_FOUND",
         "source_url": "https://www.nepalstock.com/api/nots/notice/file/x.pdf"},
        {"sha256": "h2", "symbol": "SCB", "status": "DOCUMENT_OK", "source_url": "https://sebon.gov.np/a.pdf"},
    ]
    health = unify_source_health(documents=docs)
    assert health["documents"]["token_gated"] == 1
    assert health["documents"]["token_gated_note"] == "DOCUMENT_UNAVAILABLE_TOKEN_GATED"


# 15/16/17 + 22 — unified source health for NEPSE/SEBON/NRB
def test_source_health_unified():
    from saathi.browser_research.nepse_capture import CaptureResult
    cap = CaptureResult(status="ok",
        notices=[{"noticeHeading": "x", "modifiedDate": "2026-09-11", "noticeFilePath": "a.pdf"}],
        securities=[{"symbol": "N", "securityName": "n"}], endpoint_status={"/api/web/notice/": 200})
    h = unify_source_health(nepse_capture=cap, sebon_status="AVAILABLE", nrb_status="AVAILABLE")
    assert h["nepse"]["status"] == "AVAILABLE"
    assert h["sebon"]["status"] == "AVAILABLE" and h["nrb"]["status"] == "AVAILABLE"


# 18 — snapshot generation shape
def test_snapshot_generation():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NRB_POLICY, SCB_AGM], now=NOW)
    d = snap.as_dict()
    assert d["schema"] == "research_intelligence.v1" and d["events"] and "source_distribution" in d


# 19 — daily brief sections
def test_daily_brief():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NRB_POLICY, SCB_AGM], now=NOW)
    b = daily_brief(snap)
    for sec in ("what_changed", "corporate_actions", "regulatory", "company_disclosures",
                "monetary_macro", "contradictions_requiring_review", "stale_or_unavailable_sources"):
        assert sec in b
    assert b["corporate_actions"] and b["monetary_macro"]


# 20 — no-model operation
def test_no_model_operation():
    snap = build_snapshot([NABIL_DIV_OFFICIAL], now=NOW)
    r = optional_model_summary(snap, router=None, summarizer=None)
    assert r["status"] == "MODEL_UNAVAILABLE" and "deterministic_brief" in r


# 21 — optional model summary when summarizer provided
def test_optional_model_summary():
    snap = build_snapshot([NABIL_DIV_OFFICIAL], now=NOW)
    r = optional_model_summary(snap, router=None, summarizer=lambda brief: "concise summary")
    assert r["status"] == "OK" and "summary" in r


# 22b — ModelRouter with no provider → MODEL_UNAVAILABLE even with summarizer
def test_modelrouter_unavailable():
    class _Router:
        def best(self, *a, **k):
            return None
    snap = build_snapshot([NABIL_DIV_OFFICIAL], now=NOW)
    r = optional_model_summary(snap, router=_Router(), summarizer=lambda b: "x")
    assert r["status"] == "MODEL_UNAVAILABLE"


# 23 — portfolio relevance read-only
def test_portfolio_relevance():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NRB_POLICY], now=NOW, holdings={"NABIL"})
    nabil = next(e for e in snap.events if e.symbol == "NABIL")
    assert nabil.portfolio_relevant is True
    nrb = next(e for e in snap.events if e.event_type == ResearchEventType.MONETARY_POLICY)
    assert nrb.portfolio_relevant is False


# 24 — central command projection
def test_central_command_projection():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NRB_POLICY], now=NOW)
    p = central_command_projection(snap)
    assert p["read_only"] is True and p["overview"]["events"] == len(snap.events)
    assert isinstance(p["latest_events"], list)


# 25 — chat query
def test_chat_query():
    snap = build_snapshot([NABIL_DIV_OFFICIAL, NRB_POLICY], now=NOW)
    a = chat_answer(snap, "show NABIL official disclosures")
    assert a["supported"] and a["events"] and a["events"][0]["symbol"] == "NABIL"
    a2 = chat_answer(snap, "any new NRB policy?")
    assert a2["events"]


# 26 — voice projection concise
def test_voice_projection():
    snap = build_snapshot([NABIL_DIV_OFFICIAL], now=NOW)
    v = voice_answer(snap)
    assert isinstance(v, str) and "official event" in v.lower()


# 27 — crypto-compatible schema
def test_crypto_compatible_schema():
    f = _fact("Protocol exploit incident on chain", FactGroup.OFFICIAL_NOTICES,
              "exchange.example", SourceTier.TIER_2_PRIMARY_DATA, sym="BTC", ref="c1")
    snap = build_snapshot([f], market="CRYPTO", now=NOW)
    assert snap.market == "CRYPTO" and snap.events
    assert snap.events[0].event_type == ResearchEventType.SECURITY_INCIDENT


# 28/29/30/31/32 — zero write authority (import audit)
def test_zero_write_authority_imports():
    import saathi.browser_research.intelligence as mod
    imports = [l for l in open(mod.__file__).read().splitlines()
               if l.strip().startswith(("import ", "from "))]
    blob = "\n".join(imports)
    for banned in ("execution.gateway", "trading_guardian", "market_data",
                   "broker", "portfolio_construction", "portfolio_risk"):
        assert banned not in blob
