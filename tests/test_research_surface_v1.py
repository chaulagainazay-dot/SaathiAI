"""M — RESEARCH_SURFACE_UI_WIRING backend tests (Phase 33).

In-process: seed a temp evidence store, drive the read-only BFF (research_surface)
that the API routes delegate to. No network, no model, no live server.
"""
from __future__ import annotations

import datetime as dt
import tempfile

from saathi import research_surface as RS
from saathi.browser_research.contract import (
    DataDomain, ExtractedFact, FactGroup, MissionType, Provenance, ResearchResult, ResearchStatus,
)
from saathi.browser_research.evidence_bridge import write_result_to_evidence
from saathi.browser_research.freshness import Freshness
from saathi.browser_research.tiers import SourceTier
from saathi.evidence.schema import Evidence
from saathi.evidence.store import EvidenceStore

NOW = dt.datetime(2024, 9, 13, tzinfo=dt.timezone.utc).timestamp()
PUB = dt.datetime(2024, 9, 12, tzinfo=dt.timezone.utc).timestamp()


def _fact(stmt, group, host, tier, *, sym="", fresh=Freshness.RECENT):
    return ExtractedFact(statement=stmt, group=group, source_url=f"https://{host}/x",
                         source_host=host, source_tier=tier, retrieval_ts=NOW, publication_ts=PUB,
                         value=sym, provenance=Provenance.BROWSER_DERIVED,
                         data_domain=DataDomain.WEB_INTELLIGENCE, confidence=0.9, freshness=fresh)


def _seed():
    store = EvidenceStore(db_path=f"{tempfile.mkdtemp()}/ev.db")
    facts = [
        _fact("MBL dividend 10% declared 2024-09-12", FactGroup.CORPORATE_ACTIONS, "nepalstock.com", SourceTier.TIER_1_OFFICIAL, sym="MBL"),
        _fact("MBL dividend 12% reported", FactGroup.CORPORATE_ACTIONS, "kathmandupost.com", SourceTier.TIER_3_REPUTABLE_NEWS, sym="MBL"),
        _fact("NRB monetary policy directive 2024-09-11", FactGroup.REGULATORY, "nrb.org.np", SourceTier.TIER_1_OFFICIAL),
    ]
    res = ResearchResult(mission_id="seed", mission_type=MissionType.NEPSE_DAILY_INTELLIGENCE,
                         status=ResearchStatus.COMPLETE, started_at=NOW, extracted_facts=facts)
    write_result_to_evidence(res, store=store)
    # a token-gated NEPSE document row
    store.record(Evidence(department="browser_research", project="nepse_document", episode="doc1",
                          director="document", status="DOCUMENT_NOT_FOUND",
                          metrics={"source_url": "https://www.nepalstock.com/api/nots/notice/file/x.pdf",
                                   "sha256": "", "issuer": "MBL", "title": "t"}))
    return store


# 1 snapshot endpoint
def test_intelligence():
    d = RS.intelligence(store=_seed())
    assert d["read_only"] is True and d["state"] == "OK"
    assert d["overview"]["events"] >= 2 and "source_health" in d


# 2 events list
def test_events():
    d = RS.events(store=_seed())
    assert d["read_only"] and d["count"] >= 2 and d["events"]


# 3 event detail
def test_event_detail():
    st = _seed()
    ev0 = RS.events(store=st)["events"][0]
    d = RS.event_detail(ev0["event_id"], store=st)
    assert d["read_only"] and d["event_id"] == ev0["event_id"] and "evidence_refs" in d


# 4 event not found
def test_event_not_found():
    d = RS.event_detail("does-not-exist", store=_seed())
    assert d["error"] == "EVENT_NOT_FOUND"


# 5 daily brief
def test_brief():
    d = RS.brief(store=_seed())
    assert d["read_only"] and "corporate_actions" in d and d["state"] == "OK"


# 6 source health
def test_health():
    d = RS.health(store=_seed())
    sh = d["source_health"]
    assert "nepse" in sh and "documents" in sh
    assert sh["documents"]["token_gated"] == 1                      # 14: token-gated surfaced
    assert sh["documents"]["token_gated_note"] == "DOCUMENT_UNAVAILABLE_TOKEN_GATED"


# 8 unsupported claim
def test_unsupported_claim():
    r = RS.maybe_answer_chat("show ZZZZ disclosures", store=_seed())
    assert r is not None and r["supported"] is False


# 9 deterministic chat
def test_deterministic_chat():
    r = RS.maybe_answer_chat("what changed in nepse today?", store=_seed())
    assert r and r["supported"] and "event" in r["reply"].lower()
    # non-research query returns None (falls through to normal agent)
    assert RS.maybe_answer_chat("what's the weather?") is None


# 10 deterministic voice
def test_deterministic_voice():
    r = RS.maybe_answer_voice("what happened in nepse today?", store=_seed())
    assert r and isinstance(r["reply"], str) and r["reply"]


# 11 no-model mode (surface is deterministic; no model involved at all)
def test_no_model_mode():
    d = RS.intelligence(store=_seed())
    assert d["overview"]["events"] >= 2   # works with zero model dependency


# 12 contradiction response
def test_contradiction():
    st = _seed()
    evs = RS.events(store=st)["events"]
    mbl = next(e for e in evs if e["symbol"] == "MBL")
    assert mbl["contradiction_state"] == "OFFICIAL_SOURCE_WINS"


# 13 citation references
def test_citations():
    st = _seed()
    ev0 = RS.event_detail(RS.events(store=st)["events"][0]["event_id"], store=st)
    assert ev0["evidence_refs"]


# 14b — CC projection event drill-down: latest_events carry an event_id that resolves
def test_cc_projection_event_id_resolves():
    st = _seed()
    d = RS.intelligence(store=st)
    ev = d["latest_events"][0]
    assert ev.get("event_id"), "latest_events must expose event_id for detail drill-down"
    detail = RS.event_detail(ev["event_id"], store=st)
    assert detail.get("error") != "EVENT_NOT_FOUND" and detail["event_id"] == ev["event_id"]


# 15 portfolio relevance read-only
def test_portfolio_relevance():
    d = RS.intelligence(store=_seed(), holdings={"MBL"})
    mbl = next(e for e in d["latest_events"] if e["symbol"] == "MBL")
    assert mbl["portfolio_relevant"] is True


# 7 auth behavior — research routes are NOT whitelisted (follow session auth)
def test_routes_not_whitelisted():
    src = open("saathi/server.py").read()
    # the whitelist that lets a path skip auth must not contain our research paths
    assert "/api/v1/research/intelligence" in src   # route exists
    # ensure not added to any obvious public/whitelist set
    import re
    wl_blocks = re.findall(r"WHITELIST[^\n]*=\s*[\{\(\[].*?[\}\)\]]", src, re.S)
    assert not any("/api/v1/research" in b for b in wl_blocks)


# 16-19 authority invariants — surface imports no execution/trade/portfolio/market_data
def test_no_authority_imports():
    import saathi.research_surface as m
    imports = [l for l in open(m.__file__).read().splitlines()
               if l.strip().startswith(("import ", "from "))]
    blob = "\n".join(imports)
    for banned in ("execution.gateway", "trading_guardian", "market_data", "broker",
                   "portfolio_construction", "portfolio_risk"):
        assert banned not in blob
