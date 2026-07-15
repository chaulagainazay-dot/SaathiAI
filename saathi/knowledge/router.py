"""Deterministic retrieval router — rule-based, inspectable plans."""
from __future__ import annotations

from saathi.knowledge.permissions import source_permitted
from saathi.knowledge.registry import KnowledgeSource
from saathi.knowledge.types import (
    KnowledgeQuery,
    RetrievalIntent,
    RetrievalPlan,
    RetrievalProfile,
    SourceSelection,
)

# Profile → preferred source types (ordered)
_PROFILE_SOURCES: dict[RetrievalProfile, list[str]] = {
    RetrievalProfile.FAST_LOOKUP: ["codebase_index", "documentation"],
    RetrievalProfile.CODE_EXPLAIN: [
        "codebase_index", "documentation", "decision_docs",
    ],
    RetrievalProfile.MULTI_REPO_COMPARE: ["codebase_index", "documentation"],
    RetrievalProfile.MISSION_CONTEXT: [
        "decision_docs", "codebase_index", "documentation", "memory_ltm", "provider_metadata",
    ],
    RetrievalProfile.AUDIT_EVIDENCE: [
        "decision_docs", "documentation", "codebase_index",
    ],
}


def build_plan(
    query: KnowledgeQuery,
    sources: list[KnowledgeSource],
) -> RetrievalPlan:
    preferred = _PROFILE_SOURCES.get(query.profile, ["codebase_index"])
    top_k = query.resolved_top_k()
    # Per-source limit with multi-repo balance
    n_repos = len({s.repository_id for s in sources if s.enabled}) or 1
    per_source = max(3, top_k // max(1, min(len(preferred), 4)))

    selections: list[SourceSelection] = []
    repo_filter = set(query.repository_ids or [])

    for src in sources:
        ok, reason = source_permitted(query, src)
        if not ok:
            selections.append(SourceSelection(
                source_id=src.source_id, selected=False, reason=reason,
            ))
            continue
        if repo_filter and src.repository_id not in repo_filter:
            # For MULTI_REPO without explicit list, allow all registered
            if query.profile != RetrievalProfile.MULTI_REPO_COMPARE:
                selections.append(SourceSelection(
                    source_id=src.source_id, selected=False,
                    reason="repository_not_in_scope",
                ))
                continue
        if src.source_type not in preferred:
            # still allow if intent specifically needs it
            if not (
                query.intent == RetrievalIntent.INSPECT_PROVIDER
                and src.source_type == "provider_metadata"
            ):
                selections.append(SourceSelection(
                    source_id=src.source_id, selected=False,
                    reason="not_in_profile_sources",
                ))
                continue

        variant = query.query
        if query.intent == RetrievalIntent.FIND_TESTS:
            variant = f"{query.query} test"
        elif query.intent == RetrievalIntent.FIND_DOCUMENTATION:
            variant = f"{query.query} documentation"
        selections.append(SourceSelection(
            source_id=src.source_id,
            selected=True,
            reason="selected",
            query_variant=variant,
            limit=per_source,
            timeout_sec=5.0,
        ))

    # Ensure at least one codebase source if available and nothing selected
    if not any(s.selected for s in selections):
        for src in sources:
            if src.source_type == "codebase_index" and src.enabled:
                ok, reason = source_permitted(query, src)
                if ok:
                    for i, sel in enumerate(selections):
                        if sel.source_id == src.source_id:
                            selections[i] = SourceSelection(
                                source_id=src.source_id, selected=True,
                                reason="fallback_codebase",
                                query_variant=query.query, limit=top_k,
                            )
                    break

    return RetrievalPlan(
        request_id=query.request_id,
        profile=query.profile.value,
        intent=query.intent.value,
        selections=selections,
        ranking_strategy="weighted_fusion_v1",
        parallel=False,
        fallback="codebase_memory_only",
        total_result_quota=top_k,
    )
