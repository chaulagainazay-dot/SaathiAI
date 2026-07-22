"""Adapter over M18.2 codebase_memory.search (read-only)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.knowledge.permissions import filter_sensitive_results
from saathi.knowledge.registry import KnowledgeSource
from saathi.knowledge.types import (
    EvidenceClass,
    KnowledgeQuery,
    KnowledgeResult,
    RetrievalIntent,
    RetrievalProfile,
    content_fingerprint,
)


class CodebaseMemoryAdapter:
    name = "codebase_memory"

    def __init__(self, *, search_fn=None, base_dir: Path | None = None):
        self._search_fn = search_fn
        self._base_dir = base_dir

    def supports(self, query: KnowledgeQuery, source: KnowledgeSource) -> bool:
        return source.adapter == self.name and source.source_type in (
            "codebase_index",
        )

    def describe_capabilities(self) -> dict:
        return {
            "name": self.name,
            "modes": ["lexical", "symbol", "path"],
            "mutates": False,
            "mcp": False,
        }

    def health(self, source: KnowledgeSource) -> dict:
        try:
            from saathi.codebase_memory.health import index_health
            h = index_health(source.location, base_dir=self._base_dir)
            return {"ok": h.status in ("HEALTHY", "STALE", "EMPTY"), "status": h.status}
        except Exception as e:
            return {"ok": False, "status": "unavailable", "error": type(e).__name__}

    def retrieve(
        self,
        query: KnowledgeQuery,
        source: KnowledgeSource,
        *,
        limit: int = 8,
    ) -> list[KnowledgeResult]:
        search = self._search_fn
        if search is None:
            from saathi.codebase_memory.retrieve import search as _search
            search = _search

        docs_only = query.intent in (
            RetrievalIntent.FIND_DOCUMENTATION,
            RetrievalIntent.RETRIEVE_DECISION_HISTORY,
        ) or query.profile == RetrievalProfile.AUDIT_EVIDENCE and "doc" in query.query.lower()
        tests_only = query.intent == RetrievalIntent.FIND_TESTS
        path_filter = query.path_filters[0] if query.path_filters else ""

        try:
            res = search(
                query.query,
                project_root=source.location,
                top_k=limit,
                path_filter=path_filter,
                documentation_only=docs_only and not tests_only,
                tests_only=tests_only,
                base_dir=self._base_dir,
            )
        except Exception as e:
            return []

        if not getattr(res, "ok", False):
            return []

        out: list[KnowledgeResult] = []
        for h in res.hits or []:
            path = getattr(h, "path", "") or ""
            ok, reason = filter_sensitive_results(path, getattr(h, "snippet", "") or "")
            if not ok:
                continue
            excerpt = (getattr(h, "snippet", "") or "")[:500]
            ftype = (getattr(h, "file_type", "") or "").upper()
            if "TEST" in ftype:
                ev = EvidenceClass.PRIMARY_TESTS
            elif ftype in ("DOCUMENTATION", "ARCHITECTURE", "ROADMAP", "STYLE_GUIDE"):
                ev = EvidenceClass.CANONICAL_DOCS
            else:
                ev = EvidenceClass.PRIMARY_CODE
            score = float(getattr(h, "score", 0) or 0)
            rid = getattr(h, "result_id", "") or content_fingerprint(path + excerpt)
            out.append(KnowledgeResult(
                result_id=f"{source.source_id}:{rid}",
                source_id=source.source_id,
                source_type=source.source_type,
                repository_id=source.repository_id,
                object_id=path,
                path=path,
                title=getattr(h, "symbol", "") or path.rsplit("/", 1)[-1],
                excerpt=excerpt,
                normalized_content=excerpt,
                native_score=score,
                normalized_score=min(1.0, score / 40.0) if score > 1 else score,
                trust_score=1.0 if source.trust.value == "high" else 0.6,
                freshness_score=0.9 if "CURRENT" in str(getattr(h, "freshness", "")) else 0.5,
                final_score=0.0,
                evidence_class=ev,
                is_generated=False,
                language="",
                provenance={
                    "citation": getattr(h, "citation", ""),
                    "branch": getattr(h, "branch", ""),
                    "commit": getattr(h, "commit_sha", ""),
                    "freshness": getattr(h, "freshness", ""),
                    "adapter": self.name,
                },
                start_line=int(getattr(h, "start_line", 0) or 0),
                end_line=int(getattr(h, "end_line", 0) or 0),
                content_fingerprint=content_fingerprint(excerpt),
                warnings=list(getattr(h, "warnings", None) or []),
            ))
        return out
