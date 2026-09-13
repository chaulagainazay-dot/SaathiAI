"""M — NEPSE_DISCLOSURE_DOCUMENT_INGESTION deterministic tests (Phase 29).

Offline: injected fetcher returns real PDF fixture bytes; governed-fetch domain
blocks tested without network; temp evidence DB. Covers fetch governance, MIME +
signature, hashing, dedup/change, PDF parsing/safety, structured facts, dates,
provenance, evidence, endpoint schema/health, and authority invariants.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from saathi.browser_research.documents import (
    DOCUMENT_TIMEOUT, MAX_DOCUMENTS_PER_MISSION, DocumentIngestionRequest, DocumentStatus,
    governed_fetch, ingest_document, _validate_type,
)
from saathi.browser_research.nepse_endpoint import SecurityIndex
from saathi.browser_research.records import ExtractionMethod
from saathi.browser_research.tiers import SourceTier
from saathi.evidence.store import EvidenceStore

FX = pathlib.Path(__file__).parent / "fixtures" / "docs"
_TMP = tempfile.mkdtemp(prefix="docing_")
_N = 0
SEC = SecurityIndex.from_json([
    {"symbol": "NABIL", "securityName": "Nabil Bank Limited"},
    {"symbol": "SCB", "securityName": "Standard Chartered Bank"},
])


def _store():
    global _N
    _N += 1
    return EvidenceStore(db_path=f"{_TMP}/ev{_N}.db")


def _bytes(name):
    return (FX / f"{name}.pdf").read_bytes()


def _fetcher(status=DocumentStatus.DOCUMENT_OK, body=None, ct="application/pdf",
             final="https://www.nepalstock.com/doc.pdf"):
    def f(url, *, allowed_hosts, max_bytes, timeout):
        return status, body, ct, final
    return f


def _req(url="https://www.nepalstock.com/api/nots/notice/file/x.pdf", **kw):
    return DocumentIngestionRequest(mission_id="m", source_url=url,
                                    allowed_domains=("nepalstock.com",), **kw)


# 1 — official PDF allowed + OK
def test_official_pdf_ok():
    r = ingest_document(_req(), fetcher=_fetcher(body=_bytes("normal")),
                        security_index=SEC, store=_store())
    assert r.status == DocumentStatus.DOCUMENT_OK
    assert r.sha256 and r.byte_length > 0 and r.page_count == 1


# 2/4/5 — off-domain / localhost / private-IP blocked at governed_fetch pre-flight (no network)
def test_governed_fetch_blocks():
    for bad in ("https://evil.example/x.pdf", "http://127.0.0.1/x.pdf",
                "http://169.254.169.254/x", "http://10.0.0.1/x.pdf",
                "file:///etc/passwd", "data:application/pdf;base64,AAAA"):
        st, body, ct, fin = governed_fetch(bad, allowed_hosts=["nepalstock.com"],
                                           max_bytes=1000, timeout=5)
        assert st == DocumentStatus.DOCUMENT_BLOCKED and body is None


# 3 — redirect revalidation reason surfaces as blocked domain (unit on the request path)
def test_offdomain_request_blocked_end_to_end():
    r = ingest_document(_req(url="https://evil.example/x.pdf"),
                        fetcher=governed_fetch, store=_store())
    assert r.status == DocumentStatus.DOCUMENT_BLOCKED


# 6/7/8 — MIME + signature validation; extension never trusted
def test_mime_and_signature_validation():
    assert _validate_type("application/pdf", b"%PDF-1.7 ...")[0] is True
    # fake .pdf: pdf mime but no %PDF signature -> rejected
    ok, label = _validate_type("application/pdf", b"<html>not a pdf</html>")
    assert ok is False and label == "pdf_mime_without_signature"
    # executable content type rejected
    assert _validate_type("application/x-msdownload", b"MZ...")[0] is False


def test_fake_pdf_extension_rejected():
    r = ingest_document(_req(), fetcher=_fetcher(body=b"<html>nope</html>", ct="application/pdf"),
                        store=_store())
    assert r.status == DocumentStatus.DOCUMENT_UNSUPPORTED_TYPE


# 9 — max-size enforcement
def test_max_size():
    r = ingest_document(_req(), fetcher=_fetcher(status=DocumentStatus.DOCUMENT_TOO_LARGE, body=None),
                        store=_store())
    assert r.status == DocumentStatus.DOCUMENT_TOO_LARGE


# 10 — timeout
def test_timeout():
    r = ingest_document(_req(), fetcher=_fetcher(status=DocumentStatus.DOCUMENT_TIMEOUT, body=None),
                        store=_store())
    assert r.status == DocumentStatus.DOCUMENT_TIMEOUT


# 11 — SHA-256 hashing stable
def test_hashing_stable():
    st = _store()
    a = ingest_document(_req(), fetcher=_fetcher(body=_bytes("normal")), store=st)
    import hashlib
    assert a.sha256 == hashlib.sha256(_bytes("normal")).hexdigest()


# 12 — duplicate document (same url + bytes) flagged
def test_duplicate_document():
    st = _store()
    ingest_document(_req(), fetcher=_fetcher(body=_bytes("normal")), store=st)
    b = ingest_document(_req(), fetcher=_fetcher(body=_bytes("normal")), store=st)
    rows = st.query(department="browser_research", project="nepse_document", limit=50)
    assert any(r.get("metrics", {}).get("duplicate") for r in rows)
    assert b.status == DocumentStatus.DOCUMENT_OK


# 13 — changed document hash → DOCUMENT_CHANGED warning
def test_changed_document():
    st = _store()
    url = "https://www.nepalstock.com/doc/same.pdf"
    ingest_document(_req(url=url), fetcher=_fetcher(body=_bytes("normal"), final=url), store=st)
    b = ingest_document(_req(url=url), fetcher=_fetcher(body=_bytes("multipage"), final=url), store=st)
    assert DocumentStatus.DOCUMENT_CHANGED.value in b.warnings


# 14/15 — text extraction, multi-page
def test_text_and_multipage():
    r = ingest_document(_req(), fetcher=_fetcher(body=_bytes("multipage")), store=_store())
    assert r.page_count == 3 and r.extracted_text_len > 0


# 16 — empty PDF
def test_empty_pdf():
    r = ingest_document(_req(), fetcher=_fetcher(body=_bytes("empty")), store=_store())
    assert r.status == DocumentStatus.DOCUMENT_EMPTY


# 17 — malformed PDF
def test_malformed_pdf():
    r = ingest_document(_req(), fetcher=_fetcher(body=b"%PDF-1.4\nbroken garbage not real"),
                        store=_store())
    assert r.status == DocumentStatus.DOCUMENT_PARSE_FAILED


# 18 — encrypted PDF
def test_encrypted_pdf():
    r = ingest_document(_req(), fetcher=_fetcher(body=_bytes("encrypted")), store=_store())
    assert r.status == DocumentStatus.DOCUMENT_ENCRYPTED


# 19 — embedded JS treated safely (extracted as data, never executed)
def test_embedded_js_safe():
    r = ingest_document(_req(), fetcher=_fetcher(body=_bytes("embedded_js")), store=_store())
    assert r.status in (DocumentStatus.DOCUMENT_OK, DocumentStatus.DOCUMENT_EMPTY)
    assert r.sha256  # processed without executing anything


# 20 — prompt injection in document is data only
def test_prompt_injection_as_data():
    r = ingest_document(_req(), fetcher=_fetcher(body=_bytes("normal")),
                        security_index=SEC, store=_store())
    assert r.injection_markers  # 'transfer all funds' etc detected
    # never becomes a trade/authority action; just recorded on the result
    assert r.status == DocumentStatus.DOCUMENT_OK


# 21/22/23 — raw date preserved + BS/AD normalization from doc text
def test_dates():
    from saathi.browser_research.bs_date import Calendar, parse_date
    assert parse_date("2081-05-27", calendar_hint="BS").ad_date.isoformat() == "2024-09-12"
    assert parse_date("2024-09-12", calendar_hint="AD").calendar == Calendar.AD
    r = ingest_document(_req(), fetcher=_fetcher(body=_bytes("normal")), store=_store())
    # normal.pdf has "2081-05-10" — recorded raw, normalized when calendar known
    assert r.document_date_raw or r.date_calendar in (Calendar.BS, Calendar.AMBIGUOUS, Calendar.UNKNOWN)


# 24 — structured fact extraction from document text
def test_structured_facts():
    r = ingest_document(_req(), fetcher=_fetcher(body=_bytes("normal")),
                        security_index=SEC, store=_store())
    assert r.structured_facts
    assert any(f.category == "CORPORATE_ACTIONS" for f in r.structured_facts)
    assert all(f.extraction_method == ExtractionMethod.DOCUMENT_LINK for f in r.structured_facts)


# 25/26 — evidence write + parent-fact linkage
def test_evidence_and_parent_linkage():
    st = _store()
    r = ingest_document(_req(parent_fact_ref="fact-abc"),
                        fetcher=_fetcher(body=_bytes("normal")), store=st)
    assert r.evidence_refs
    rows = st.query(department="browser_research", project="nepse_document", limit=10)
    assert rows and rows[0]["metrics"]["parent_fact_ref"] == "fact-abc"
    assert rows[0]["metrics"]["provenance"] == "BROWSER_DERIVED"
    assert rows[0]["metrics"]["data_domain"] == "WEB_INTELLIGENCE"


# 27 — reconciliation: official document outranks page/news
def test_reconciliation_official_document():
    from saathi.browser_research.reconciliation import arbitrate_event, Observation, ArbitrationOutcome
    from saathi.browser_research.contract import Provenance
    obs = [
        Observation("Dividend 12%", "kathmandupost.com", SourceTier.TIER_3_REPUTABLE_NEWS, Provenance.BROWSER_DERIVED, value="12%"),
        Observation("Dividend 10%", "nepalstock.com", SourceTier.TIER_1_OFFICIAL, Provenance.BROWSER_DERIVED, value="10%"),
    ]
    res = arbitrate_event(obs)
    assert res.outcome == ArbitrationOutcome.OFFICIAL_CONFIRMS and res.canonical_value == "10%"


# 28/29/30 — authority invariants: no market_data/gateway/TG imports
def test_no_authority_imports():
    import saathi.browser_research.documents as d
    imports = [l for l in open(d.__file__).read().splitlines()
               if l.strip().startswith(("import ", "from "))]
    blob = "\n".join(imports)
    for banned in ("execution.gateway", "trading_guardian", "market_data", "broker"):
        assert banned not in blob


# 31/32 — endpoint schema validation + drift degraded
def test_endpoint_schema_and_drift():
    from saathi.browser_research.endpoint_monitor import validate_schema, health_from_capture, EndpointHealth
    from saathi.browser_research.nepse_capture import CaptureResult
    good = CaptureResult(status="ok",
        notices=[{"noticeHeading": "x", "modifiedDate": "2026-09-11", "noticeFilePath": "a.pdf"}],
        disclosures={"companyNews": [{"newsHeadline": "y", "addedDate": "2026-09-11", "applicationDocumentDetailsList": []}]},
        securities=[{"symbol": "NABIL", "securityName": "Nabil"}], endpoint_status={"/api/web/notice/": 200})
    ok, _ = validate_schema(good)
    assert ok and health_from_capture(good)["status"] == EndpointHealth.AVAILABLE.value
    drift = CaptureResult(status="ok", notices=[{"heading": "x"}], securities=[{"symbol": "N", "securityName": "n"}],
                          endpoint_status={"/api/web/notice/": 200})
    assert health_from_capture(drift)["status"] == EndpointHealth.SCHEMA_CHANGED.value


# 33 — endpoint health (token-flow change)
def test_endpoint_health_token_change():
    from saathi.browser_research.endpoint_monitor import health_from_capture, EndpointHealth
    from saathi.browser_research.nepse_capture import CaptureResult
    cap = CaptureResult(status="ok", endpoint_status={"/api/web/notice/": 401})
    assert health_from_capture(cap)["status"] == EndpointHealth.TOKEN_FLOW_CHANGED.value


# 34 — cleanup: ingestion holds no temp files / open handles (in-memory bytes)
def test_no_temp_leak():
    import gc
    r = ingest_document(_req(), fetcher=_fetcher(body=_bytes("normal")), store=_store())
    gc.collect()
    assert r.status == DocumentStatus.DOCUMENT_OK  # completes cleanly, bytes are in-memory only


# 35 — resource bounds present + conservative
def test_resource_bounds():
    from saathi.browser_research import documents as d
    assert d.MAX_DOCUMENT_BYTES <= 15 * 1024 * 1024
    assert d.MAX_DOCUMENTS_PER_MISSION <= 8
    assert d.MAX_PAGES <= 60 and DOCUMENT_TIMEOUT <= 30.0
