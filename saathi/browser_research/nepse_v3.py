"""Phase 5/8/17 — NEPSE deep mission with acquisition failover.

Order: OFFICIAL_ENDPOINT (governed Playwright JSON capture) → PLAYWRIGHT/HTTP DOM
text (existing v2 path) → typed degraded. The capture function is injected so the
mission is deterministically testable with fixtures. Output is the FROZEN
ResearchResult; provenance BROWSER_DERIVED / WEB_INTELLIGENCE throughout.
"""
from __future__ import annotations

import time
import uuid
from typing import Callable

from saathi.browser_research.contract import (
    Citation, MissionType, ResearchRequest, ResearchResult, ResearchStatus,
)
from saathi.browser_research.extract_v2 import records_to_facts
from saathi.browser_research.freshness import Freshness, meets_requirement
from saathi.browser_research.nepse_capture import CaptureResult, capture_nepse
from saathi.browser_research.nepse_endpoint import (
    NEPSE_ORIGIN, NEPSEJsonExtractor, SecurityIndex,
)
from saathi.browser_research.records import deduplicate
from saathi.browser_research.tiers import SourceTier


def _from_capture(cap: CaptureResult, *, now: float):
    idx = SecurityIndex.from_json(cap.securities)
    ex = NEPSEJsonExtractor(idx)
    records = ex.from_notices(cap.notices) + ex.from_disclosures(cap.disclosures)
    unique, dupes = deduplicate(records)
    facts = records_to_facts(unique, now=now)
    stats = {
        "records": len(records), "unique": len(unique), "duplicates": dupes,
        "dated": sum(1 for r in unique if r.published_at_normalized is not None),
        "with_document": sum(1 for r in unique if r.document_url),
        "resolved_symbols": sum(1 for r in unique if r.symbol),
        "securities_loaded": len(idx.by_symbol),
    }
    return facts, stats, unique, idx


def _ingest_documents(records, *, mission_id, security_index, document_fetcher, store, max_docs):
    """Phase 14/15 — ingest captured document URLs (bounded). Returns result dicts."""
    from saathi.browser_research.documents import (
        DocumentIngestionRequest, MAX_DOCUMENTS_PER_MISSION, ingest_document,
    )
    from saathi.browser_research.tiers import host_of
    cap = max_docs or MAX_DOCUMENTS_PER_MISSION
    out = []
    for r in records:
        if len(out) >= cap:
            break
        if not r.document_url:
            continue
        req = DocumentIngestionRequest(
            mission_id=mission_id, source_url=r.document_url,
            parent_fact_ref=r.dedup_key(), source_page=r.source_url,
            source_tier=r.source_tier, expected_issuer=r.symbol,
            allowed_domains=(host_of(r.document_url) or "nepalstock.com",),
        )
        kw = {"security_index": security_index, "store": store}
        if document_fetcher is not None:
            kw["fetcher"] = document_fetcher
        out.append(ingest_document(req, **kw).as_dict())
    return out


def run_nepse_deep_mission(
    request: ResearchRequest,
    *,
    capture_fn: Callable[..., CaptureResult] = capture_nepse,
    http_provider=None,
    seed_urls: tuple[str, ...] | None = None,
    now: Callable[[], float] | float = time.time,
    detail_pages: tuple[str, ...] = ("/company-disclosure",),
    ingest_documents: bool = False,
    document_fetcher=None,
    document_store=None,
    max_documents: int = 0,
) -> ResearchResult:
    request.validate()
    now_fn = now if callable(now) else (lambda: now)
    started = now_fn()
    result = ResearchResult(
        mission_id=request.mission_id, mission_type=MissionType.NEPSE_DAILY_INTELLIGENCE,
        status=ResearchStatus.RUNNING, started_at=started,
        browser_trace_id=uuid.uuid4().hex[:16],
    )

    acquisition = "NONE"
    cap = None
    from saathi.browser_research.documents import MAX_DOCUMENTS_PER_MISSION
    doc_cap = (max_documents or MAX_DOCUMENTS_PER_MISSION) if ingest_documents else 0
    try:
        cap = capture_fn(detail_pages=detail_pages, max_documents=doc_cap)
    except Exception as e:
        result.warnings.append(f"capture raised: {type(e).__name__}")
        cap = CaptureResult(status="degraded", error_category="CAPTURE_EXCEPTION")

    # endpoint health / schema drift (Phase 23-25)
    if cap is not None:
        from saathi.browser_research.endpoint_monitor import health_from_capture
        result.resource["endpoint_health"] = health_from_capture(cap)

    if cap and cap.status == "ok" and (cap.notices or cap.disclosures):
        acquisition = "OFFICIAL_ENDPOINT"
        facts, stats, records, sec_idx = _from_capture(cap, now=now_fn())
        result.extracted_facts.extend(facts)
        if ingest_documents:
            fetcher = document_fetcher
            if fetcher is None and getattr(cap, "documents", None):
                from saathi.browser_research.documents import browser_document_fetcher
                fetcher = browser_document_fetcher(cap.documents)
            docs = _ingest_documents(
                records, mission_id=request.mission_id, security_index=sec_idx,
                document_fetcher=fetcher, store=document_store,
                max_docs=max_documents)
            result.resource["documents"] = docs
            changed = sum(1 for d in docs if "DOCUMENT_CHANGED" in d.get("warnings", []))
            failed = sum(1 for d in docs if d.get("status") != "DOCUMENT_OK")
            result.resource["document_summary"] = {
                "count": len(docs), "changed": changed, "failed": failed,
                "parsed": sum(1 for d in docs if d.get("extracted_text_len", 0) > 0),
            }
        result.sources.append(Citation(
            url=f"{NEPSE_ORIGIN}/api/web/notice/", host="nepalstock.com", title="NEPSE Notices",
            source_tier=SourceTier.TIER_1_OFFICIAL, retrieval_ts=now_fn()))
        result.sources.append(Citation(
            url=f"{NEPSE_ORIGIN}/api/nots/news/companies/disclosure", host="nepalstock.com",
            title="NEPSE Company Disclosures", source_tier=SourceTier.TIER_1_OFFICIAL,
            retrieval_ts=now_fn()))
        result.resource["extraction"] = [stats]
        result.resource["endpoint_status"] = cap.endpoint_status
        result.resource["capture_cleanup"] = cap.cleanup
        if cap.off_domain_blocked:
            result.warnings.append(f"off-domain responses blocked: {len(cap.off_domain_blocked)}")
    else:
        # Failover to existing HTTP/text v2 mission.
        acquisition = "HTTP_FALLBACK"
        if cap is not None and cap.error_category:
            result.warnings.append(f"endpoint capture degraded: {cap.error_category}")
        if http_provider is not None:
            from saathi.browser_research.nepse import run_nepse_mission
            fb = run_nepse_mission(http_provider, request,
                                   seed_urls=seed_urls or ("https://www.sebon.gov.np/",), now=now_fn)
            result.extracted_facts.extend(fb.extracted_facts)
            result.sources.extend(fb.sources)
            result.warnings.extend(fb.warnings)
        else:
            result.warnings.append("no http fallback provider supplied")

    # freshness warnings + status
    stale = [f for f in result.extracted_facts if f.freshness == Freshness.STALE]
    if stale:
        result.warnings.append(f"{len(stale)} facts are STALE (>=7d)")
    if request.freshness_requirement != Freshness.UNKNOWN:
        unmet = [f for f in result.extracted_facts
                 if not meets_requirement(f.freshness, request.freshness_requirement)]
        if unmet:
            result.warnings.append(
                f"{len(unmet)} facts below freshness requirement {request.freshness_requirement.value}")

    result.completed_at = now_fn()
    result.resource["acquisition"] = acquisition
    if result.extracted_facts:
        result.confidence = round(
            sum(f.confidence for f in result.extracted_facts) / len(result.extracted_facts), 3)
        result.status = ResearchStatus.COMPLETE if result.sources else ResearchStatus.PARTIAL
    else:
        result.status = ResearchStatus.PARTIAL if result.sources else ResearchStatus.FAILED
    return result.validate()
