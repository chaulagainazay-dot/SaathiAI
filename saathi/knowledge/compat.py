"""M18.2 compatibility: existing codebase_memory search still works; optional unified route."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.codebase_memory.retrieve import search as legacy_search
from saathi.knowledge.service import KnowledgeService
from saathi.knowledge.types import KnowledgeQuery, RetrievalProfile


def search_compatible(
    query: str,
    *,
    project_root: str | Path | None = None,
    top_k: int = 10,
    use_unified: bool = False,
    shadow: bool = False,
    **legacy_kwargs: Any,
) -> dict:
    """Preserve M18.2-style dict response.

    When use_unified=False (default), calls legacy search unchanged.
    When use_unified=True, routes via KnowledgeService and maps to similar shape.
    """
    if not use_unified:
        r = legacy_search(
            query, project_root=project_root, top_k=top_k, **legacy_kwargs,
        )
        out = r.to_dict()
        if shadow:
            try:
                ks = KnowledgeService(saathi_root=project_root)
                u = ks.retrieve(KnowledgeQuery(
                    query=query,
                    profile=RetrievalProfile.CODE_EXPLAIN,
                    max_results=top_k,
                    shadow_compare_legacy=False,
                ))
                out["unified_shadow"] = {
                    "ok": u.ok,
                    "paths": [x.path for x in u.results[:top_k]],
                    "request_id": u.request_id,
                }
            except Exception as e:
                out["unified_shadow"] = {"ok": False, "error": type(e).__name__}
        return out

    ks = KnowledgeService(saathi_root=project_root)
    u = ks.retrieve(KnowledgeQuery(
        query=query,
        profile=RetrievalProfile.CODE_EXPLAIN,
        max_results=top_k,
    ))
    return {
        "ok": u.ok,
        "query": query,
        "hits": [
            {
                "id": r.result_id,
                "path": r.path,
                "title": r.title,
                "snippet": r.excerpt,
                "score": r.final_score,
                "repository_id": r.repository_id,
                "source_id": r.source_id,
                "untrusted": False,
            }
            for r in u.results
        ],
        "mode": "unified_knowledge",
        "plan": u.plan,
        "context": u.context,
        "consulted_index": True,
        "legacy_compatible": True,
    }
