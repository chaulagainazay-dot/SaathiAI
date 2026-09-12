"""Phase 9 — write results into the EXISTING saathi/evidence store.

No second evidence store. One episode row (CEO/dashboard summary) plus one row
per extracted fact, all in the universal Evidence schema, department
``browser_research``. Each fact is rebuilt with its evidence row id so the
returned result carries the evidence reference (Phase 8 requirement).
"""
from __future__ import annotations

import dataclasses

from saathi.browser_research.contract import FactGroup, ResearchResult
from saathi.evidence.schema import Evidence
from saathi.evidence.store import default_store

DEPARTMENT = "browser_research"


def write_result_to_evidence(result: ResearchResult, *, store=None) -> tuple[str, ResearchResult]:
    """Persist the mission + facts. Returns (episode_id, result_with_refs)."""
    st = store or default_store()
    market = "NEPSE"

    # 1) per-fact rows, rebuilding each fact with its evidence ref.
    new_facts = []
    for f in result.extracted_facts:
        ev = Evidence(
            department=DEPARTMENT, project=market, episode=result.mission_id,
            run=result.browser_trace_id, director=f.group.value,
            provider="governed_browser", model="playwright",
            confidence=float(f.confidence), status=result.status.value,
            metrics={
                "statement": f.statement, "value": f.value,
                "source_url": f.source_url, "source_host": f.source_host,
                "source_tier": f.source_tier.name, "provenance": f.provenance.value,
                "data_domain": f.data_domain.value, "freshness": f.freshness.value,
                "publication_ts": f.publication_ts, "retrieval_ts": f.retrieval_ts,
                "independently_confirmed": f.independently_confirmed,
            },
        )
        ref = st.record(ev)
        new_facts.append(dataclasses.replace(f, evidence_ref=ref))

    result = dataclasses.replace(result, extracted_facts=new_facts)

    # 2) episode summary row.
    group_counts = {g.value: 0 for g in FactGroup}
    for f in new_facts:
        group_counts[f.group.value] += 1
    episode_ev = Evidence(
        department=DEPARTMENT, project=market, episode=result.mission_id,
        run=result.browser_trace_id, director=result.mission_type.value,
        provider="governed_browser", model="playwright",
        confidence=float(result.confidence), status=result.status.value,
        metrics={
            "sources": len(result.sources), "facts": len(new_facts),
            "group_counts": group_counts, "contradictions": len(result.contradictions),
            "warnings": len(result.warnings), "resource": result.resource,
            "browser_trace_id": result.browser_trace_id,
        },
        artifacts={"grouped": result.grouped()},
    )
    episode_id = st.record(episode_ev)
    result.resource["evidence_episode_id"] = episode_id
    return episode_id, result
