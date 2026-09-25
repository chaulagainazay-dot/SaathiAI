"""M — STRUCTURED_FINANCIAL_EVIDENCE_AND_MEMORY tests.

Proves typed evidence, provenance + content hashing, supersession (immutable rows),
fact/derivation/interpretation separation, composition from canonical views, and — critically
— privacy rejection of credentials / raw surface / secrets.
"""
from __future__ import annotations

import pytest

from saathi.platform.finance.financial_memory import (
    EvidenceClass, EvidenceType, FinancialEvidence, FinancialMemoryRejected,
    FinancialMemoryStore, market_evidence, portfolio_evidence, position_evidences,
)


@pytest.fixture()
def store(tmp_path):
    return FinancialMemoryStore(db_path=str(tmp_path / "mem.db"))


VIEW = {
    "provider": "TMS", "currency": "NPR", "asset_count": 2, "total_value": "115450",
    "snapshot_id": "obs_abc123", "source": "OWNER_AUTHENTICATED_BROWSER_OBSERVED",
    "top_concentration_pct": 52.0, "largest_position": {"symbol": "NABIL", "weight_pct": 52.0},
    "positions": [
        {"symbol": "NABIL", "instrument_id": "NEPSE:NABIL", "quantity": "100",
         "market_value": "55400", "current_price": "554", "current_price_source": "OFFICIAL_PAGE_OBSERVED"},
        {"symbol": "HDL", "instrument_id": "NEPSE:HDL", "quantity": "50", "market_value": "60050"},
    ],
}


# 1 — record + latest + content hash
def test_record_latest_hash(store):
    ev = portfolio_evidence(VIEW, provider="TMS", runtime_id="ofr_1", session_id="s1")
    eid = store.record(ev)
    assert eid.startswith("fev_")
    rows = store.latest(provider="TMS", evidence_type=EvidenceType.PORTFOLIO_SNAPSHOT.value)
    assert rows and rows[0]["evidence_id"] == eid
    assert rows[0]["content_hash"] and rows[0]["canonical_ref"] == "obs_abc123"
    assert rows[0]["evidence_class"] == EvidenceClass.FACT.value


# 2 — privacy: reserved sensitive keys rejected
@pytest.mark.parametrize("bad", [
    {"password": "x"}, {"otp": "123456"}, {"cookie": "a=b"}, {"session_token": "t"},
    {"dom": "<html>"}, {"html": "<div>"}, {"frame_b64": "AAAA"}, {"keystrokes": "abc"},
    {"storage_state": "{}"}, {"api_key": "sk-1"},
])
def test_reject_sensitive_keys(store, bad):
    ev = FinancialEvidence(provider="TMS", evidence_type=EvidenceType.ACCOUNT_SUMMARY.value,
                           evidence_class=EvidenceClass.FACT.value, observed_at=1.0, payload=bad)
    with pytest.raises(FinancialMemoryRejected):
        store.record(ev)


# 3 — privacy: credential-SHAPED values rejected (bearer, kv-secret, JWT, long opaque token)
# (bare numbers like amounts/quantities are NOT rejected — they are legitimate financial data)
@pytest.mark.parametrize("val", [
    "Bearer abcdefghijklmnop",
    "token=aVeryLongOpaqueToken1234567890",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop",
    "AKIA1234567890ABCDEFGHIJ1234567890abcdefghij",
])
def test_reject_secret_values(store, val):
    ev = FinancialEvidence(provider="TMS", evidence_type=EvidenceType.ACCOUNT_SUMMARY.value,
                           evidence_class=EvidenceClass.FACT.value, observed_at=1.0,
                           payload={"note": val})
    with pytest.raises(FinancialMemoryRejected):
        store.record(ev)


# 4 — composition: portfolio view → FACT, no cost-basis inference, references snapshot
def test_portfolio_composition(store):
    ev = portfolio_evidence(VIEW, provider="TMS")
    store.record(ev)
    assert ev.evidence_type == EvidenceType.PORTFOLIO_SNAPSHOT.value
    assert "cost_basis" not in ev.payload and "pnl" not in ev.payload
    assert ev.payload["asset_count"] == 2 and ev.payload["largest_position"] == "NABIL"


# 5 — position evidences: one FACT per holding, instrument_id set
def test_position_evidences(store):
    evs = position_evidences(VIEW, provider="TMS")
    assert len(evs) == 2
    ids = {e.instrument_id for e in evs}
    assert ids == {"NEPSE:NABIL", "NEPSE:HDL"}
    for e in evs:
        assert e.evidence_class == EvidenceClass.FACT.value
        store.record(e)
    assert store.latest(instrument_id="NEPSE:NABIL")


# 6 — supersession: new observation NEVER mutates the old; both remain, latest points to new
def test_supersession(store):
    v1 = portfolio_evidence(VIEW, provider="TMS", now=100.0)
    id1 = store.record(v1)
    v2 = portfolio_evidence({**VIEW, "total_value": "120000"}, provider="TMS",
                            supersedes=id1, now=200.0)
    id2 = store.record(v2)
    assert store.get(id1) is not None and store.get(id2)["supersedes"] == id1
    latest = store.latest(provider="TMS", evidence_type=EvidenceType.PORTFOLIO_SNAPSHOT.value)
    assert latest[0]["evidence_id"] == id2                 # newest first
    assert store.get(id1)["payload"]["total_value"] == "115450"   # historical unchanged


# 7 — fact vs interpretation: interpretation references a fact, cannot overwrite it
def test_fact_vs_interpretation(store):
    fact = portfolio_evidence(VIEW, provider="TMS")
    fid = store.record(fact)
    interp = FinancialEvidence(
        provider="TMS", evidence_type=EvidenceType.INVESTMENT_THESIS.value,
        evidence_class=EvidenceClass.MODEL_INTERPRETATION.value, observed_at=300.0,
        canonical_ref=fid, provenance="model reading", payload={"view": "concentrated in NABIL"})
    iid = store.record(interp)
    assert iid != fid
    assert store.get(fid)["evidence_class"] == EvidenceClass.FACT.value        # fact intact
    assert store.get(iid)["evidence_class"] == EvidenceClass.MODEL_INTERPRETATION.value
    assert store.get(iid)["canonical_ref"] == fid                              # references the fact


# 8 — history ordering by instrument
def test_history(store):
    store.record(market_evidence(provider="NEPSE", instrument_id="NEPSE:NABIL", ltp="550",
                                 source_type="OFFICIAL_PAGE_OBSERVED", now=10.0))
    store.record(market_evidence(provider="NEPSE", instrument_id="NEPSE:NABIL", ltp="554",
                                 source_type="OFFICIAL_PAGE_OBSERVED", now=20.0))
    h = store.history("NEPSE:NABIL")
    assert len(h) == 2 and h[0]["observed_at"] == 20.0


# 9 — clear session removes session-derived rows only
def test_clear_session(store):
    store.record(portfolio_evidence(VIEW, provider="TMS", session_id="sess_x"))
    store.record(market_evidence(provider="NEPSE", instrument_id="NEPSE:NABIL", ltp="1",
                                 source_type="OFFICIAL_PAGE_OBSERVED"))   # no session
    n = store.clear_session("sess_x")
    assert n == 1 and store.count() == 1


# 10 — market evidence is a FACT with the price authority source
def test_market_evidence():
    ev = market_evidence(provider="NEPSE", instrument_id="NEPSE:NABIL", ltp="554",
                         source_type="OFFICIAL_PAGE_OBSERVED")
    assert ev.evidence_type == EvidenceType.MARKET_OBSERVATION.value
    assert ev.evidence_class == EvidenceClass.FACT.value
    assert ev.source_type == "OFFICIAL_PAGE_OBSERVED"
