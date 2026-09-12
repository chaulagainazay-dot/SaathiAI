"""V2 extraction glue: FetchedPage → ExtractedRecord (source-aware, deduped) →
FROZEN ExtractedFact. Freshness uses the normalized AD publication timestamp
(BS-converted where applicable), never retrieval time when publication is known.
"""
from __future__ import annotations

from saathi.browser_research.contract import (
    DataDomain, ExtractedFact, FactGroup, FetchedPage, Provenance,
)
from saathi.browser_research.extractors import extractor_for
from saathi.browser_research.freshness import classify_freshness
from saathi.browser_research.records import ExtractedRecord, deduplicate


def extract_records(page: FetchedPage) -> list[ExtractedRecord]:
    return extractor_for(page.url).extract(page)


def records_to_facts(records: list[ExtractedRecord], *, now: float) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    for r in records:
        fresh = classify_freshness(r.published_at_normalized, now=now)
        facts.append(ExtractedFact(
            statement=r.title,
            group=FactGroup(r.category),
            source_url=r.source_url,
            source_host=r.source_host,
            source_tier=r.source_tier,
            retrieval_ts=now,
            publication_ts=r.published_at_normalized,
            value=r.symbol,
            provenance=Provenance.BROWSER_DERIVED,
            data_domain=DataDomain.WEB_INTELLIGENCE,
            confidence=r.confidence,
            freshness=fresh,
            evidence_ref="",
            independently_confirmed=False,
        ).validate())
    return facts


def extract_facts_v2(page: FetchedPage, *, now: float) -> tuple[list[ExtractedFact], dict]:
    """Full v2 path for one page. Returns (facts, quality_stats)."""
    raw_lines = len([ln for ln in page.content.splitlines() if ln.strip()]) if page.content else 0
    records = extract_records(page)
    unique, dupes = deduplicate(records)
    facts = records_to_facts(unique, now=now)
    dated = sum(1 for r in unique if r.published_at_normalized is not None)
    stats = {
        "raw_lines": raw_lines,
        "records": len(records),
        "unique": len(unique),
        "duplicates": dupes,
        "facts": len(facts),
        "dated": dated,
        "date_parse_rate": round(dated / len(unique), 3) if unique else 0.0,
        "with_symbol": sum(1 for r in unique if r.symbol),
        "with_document": sum(1 for r in unique if r.document_url),
        "noise_dropped": max(0, raw_lines - len(records)),
    }
    return facts, stats
