"""Bounded context package assembly with quotas and provenance."""
from __future__ import annotations

import hashlib
from collections import defaultdict

from saathi.knowledge.types import ContextPackage, EvidenceClass, KnowledgeResult

# Preferred section order
_ORDER = [
    EvidenceClass.OPERATIONAL_RECORD,  # policies / decisions first for mission
    EvidenceClass.PRIMARY_CODE,
    EvidenceClass.PRIMARY_TESTS,
    EvidenceClass.CANONICAL_DOCS,
    EvidenceClass.PROVIDER_METADATA,
    EvidenceClass.GENERATED_SUMMARY,
    EvidenceClass.INFERRED,
    EvidenceClass.UNVERIFIED_EXTERNAL,
]


def assemble_context(
    results: list[KnowledgeResult],
    *,
    budget: int,
    max_per_repo: int = 6,
    max_per_source: int = 6,
) -> ContextPackage:
    repo_count: dict[str, int] = defaultdict(int)
    source_count: dict[str, int] = defaultdict(int)
    included: list[KnowledgeResult] = []
    excluded: list[dict] = []

    # Bucket by evidence class preserving score order within
    by_class: dict[EvidenceClass, list[KnowledgeResult]] = defaultdict(list)
    for r in results:
        by_class[r.evidence_class].append(r)

    ordered: list[KnowledgeResult] = []
    for ec in _ORDER:
        ordered.extend(by_class.get(ec, []))
    # Any leftover classes
    for ec, items in by_class.items():
        if ec not in _ORDER:
            ordered.extend(items)

    used = 0
    chunks: list[str] = []
    for r in ordered:
        if repo_count[r.repository_id] >= max_per_repo:
            excluded.append({"result_id": r.result_id, "reason": "repo_quota"})
            continue
        if source_count[r.source_id] >= max_per_source:
            excluded.append({"result_id": r.result_id, "reason": "source_quota"})
            continue
        block = (
            f"### [{r.repository_id}] {r.path}"
            f"{f':{r.start_line}' if r.start_line else ''}\n"
            f"source={r.source_id} evidence={r.evidence_class.value} "
            f"score={r.final_score}\n"
            f"{r.excerpt}\n"
        )
        if used + len(block) > budget:
            excluded.append({
                "result_id": r.result_id,
                "reason": "context_budget",
            })
            # stop adding more large blocks but continue counting exclusions
            continue
        chunks.append(block)
        used += len(block)
        included.append(r)
        repo_count[r.repository_id] += 1
        source_count[r.source_id] += 1

    text = "\n".join(chunks)
    truncated = any(e.get("reason") == "context_budget" for e in excluded)
    fp = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
    return ContextPackage(
        text=text,
        char_count=len(text),
        budget=budget,
        truncated=truncated,
        included_result_ids=[r.result_id for r in included],
        excluded_reasons=excluded[:50],
        fingerprint=fp,
    )
