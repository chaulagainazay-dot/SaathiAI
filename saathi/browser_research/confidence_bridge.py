"""Phase 10 — feed normalized evidence into the EXISTING research confidence
framework (saathi/research.py). We do NOT replace it: we map browser facts onto
its categories and call ``score_confidence``, then add source-tier metadata.
"""
from __future__ import annotations

from saathi.browser_research.contract import FactGroup, ResearchResult
from saathi.browser_research.tiers import SourceTier
from saathi.research import Evidence as REvidence
from saathi.research import ResearchCategory, score_confidence

# Map our fact groups onto the existing weighted research categories.
_GROUP_TO_CATEGORY = {
    FactGroup.CORPORATE_ACTIONS: ResearchCategory.FUNDAMENTALS,
    FactGroup.COMPANY_EVENTS: ResearchCategory.FUNDAMENTALS,
    FactGroup.REGULATORY: ResearchCategory.RISK,
    FactGroup.OFFICIAL_NOTICES: ResearchCategory.NEWS,
    FactGroup.MARKET_CONTEXT: ResearchCategory.MARKET,
}


def to_research_confidence(result: ResearchResult, *, now: float) -> dict:
    """Reuse research.py scoring; annotate with source-tier coverage."""
    evidence: list[REvidence] = []
    for f in result.extracted_facts:
        cat = _GROUP_TO_CATEGORY.get(f.group, ResearchCategory.NEWS)
        evidence.append(REvidence(
            category=cat,
            metric=f"{f.group.value.lower()}:{f.source_host}",
            score=max(0.0, min(100.0, f.confidence * 100.0)),
            source=f.source_host,
            collected_at=f.retrieval_ts,
            note=f.freshness.value,
        ))
    conf = score_confidence(result.mission_id, evidence, now=now)

    tier_counts = {t.name: 0 for t in SourceTier}
    for f in result.extracted_facts:
        tier_counts[f.source_tier.name] += 1
    official = tier_counts[SourceTier.TIER_1_OFFICIAL.name]
    total = len(result.extracted_facts) or 1

    return {
        "overall": conf.overall,
        "coverage": conf.coverage,
        "actionable": conf.actionable,
        "source_count": conf.source_count,
        "contradictions": conf.contradictions,
        "stale_metrics": conf.stale_metrics,
        "missing_evidence": [m.value for m in conf.missing_evidence],
        "tier_counts": tier_counts,
        "official_share": round(official / total, 3),
        "render": conf.render(),
    }
