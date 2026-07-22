"""Unified Knowledge Service — preferred governed retrieval entry point."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from saathi.knowledge.adapters.codebase import CodebaseMemoryAdapter
from saathi.knowledge.adapters.docs import DocumentationAdapter
from saathi.knowledge.adapters.memory_ltm import MemoryLtmAdapter
from saathi.knowledge.adapters.provider_meta import ProviderMetaAdapter
from saathi.knowledge.assemble import assemble_context
from saathi.knowledge.dedupe import dedupe_results
from saathi.knowledge.rank import fuse_and_rank
from saathi.knowledge.registry import (
    KnowledgeSource,
    default_source_registry,
    filter_by_tenant,
    registry_by_id,
)
from saathi.knowledge.router import build_plan
from saathi.knowledge.types import (
    KnowledgeQuery,
    KnowledgeResponse,
    KnowledgeResult,
    RetrievalIntent,
    RetrievalProfile,
    classify_intent,
)


class KnowledgeService:
    def __init__(
        self,
        *,
        sources: list[KnowledgeSource] | None = None,
        saathi_root: str | Path | None = None,
        adapters: dict | None = None,
        codebase_base_dir: Path | None = None,
        codebase_search_fn=None,
    ):
        self.sources = sources or default_source_registry(saathi_root=saathi_root)
        self._by_id = registry_by_id(self.sources)
        self.adapters = adapters or {
            "codebase_memory": CodebaseMemoryAdapter(
                search_fn=codebase_search_fn, base_dir=codebase_base_dir,
            ),
            "documentation": DocumentationAdapter(),
            "decision_docs": DocumentationAdapter(),
            "provider_meta": ProviderMetaAdapter(),
            "memory_ltm": MemoryLtmAdapter(),
        }
        self._events: list[dict] = []

    def retrieve(self, query: KnowledgeQuery) -> KnowledgeResponse:
        t0 = time.time()
        if not (query.query or "").strip():
            return KnowledgeResponse(
                ok=False, request_id=query.request_id, query=query.query or "",
                plan={}, denied=True, error_category="empty_query",
            )

        # Auto-intent if general
        if query.intent == RetrievalIntent.GENERAL_REPO:
            query.intent = classify_intent(query.query, query.profile)

        sources = filter_by_tenant(
            self.sources,
            tenant_id=query.tenant_id,
            workspace_id=query.workspace_id,
        )
        # Explicit repository scope: if provided, only those repos
        if query.repository_ids:
            sources = [s for s in sources if s.repository_id in query.repository_ids]

        plan = build_plan(query, sources)
        self._emit("knowledge.plan", plan.to_dict())

        raw_results: list[KnowledgeResult] = []
        errors: list[dict] = []

        for sel in plan.selections:
            if not sel.selected:
                continue
            src = self._by_id.get(sel.source_id)
            if not src:
                errors.append({"source_id": sel.source_id, "error": "unknown_source"})
                continue
            adapter = self.adapters.get(src.adapter)
            if adapter is None:
                errors.append({"source_id": sel.source_id, "error": "adapter_missing"})
                continue
            if not adapter.supports(query, src):
                errors.append({"source_id": sel.source_id, "error": "adapter_unsupported"})
                continue
            try:
                from dataclasses import replace
                q2 = replace(query, query=sel.query_variant or query.query)
                hits = adapter.retrieve(q2, src, limit=sel.limit)
                raw_results.extend(hits)
            except Exception as e:
                errors.append({
                    "source_id": sel.source_id,
                    "error": type(e).__name__,
                })

        # Multi-repo quota: min per repo then relevance
        raw_results = self._apply_repo_quotas(raw_results, plan.total_result_quota)

        ranked = fuse_and_rank(raw_results, profile=query.profile, query=query.query)
        deduped, dedupe_meta = dedupe_results(ranked)
        top = deduped[: plan.total_result_quota]

        ctx = assemble_context(
            top,
            budget=query.resolved_budget(),
            max_per_repo=max(3, plan.total_result_quota // 2),
            max_per_source=max(3, plan.total_result_quota // 2),
        )

        legacy_shadow = None
        if query.shadow_compare_legacy:
            legacy_shadow = self._legacy_shadow(query)

        resp = KnowledgeResponse(
            ok=True,
            request_id=query.request_id,
            query=query.query,
            plan=plan.to_dict(),
            results=top,
            context=ctx.to_dict(),
            dedupe_meta=dedupe_meta,
            latency_ms=(time.time() - t0) * 1000,
            errors=errors,
            legacy_shadow=legacy_shadow,
        )
        self._emit("knowledge.retrieve", {
            "request_id": query.request_id,
            "result_count": len(top),
            "profile": query.profile.value,
            "errors": len(errors),
        })
        return resp

    def _apply_repo_quotas(
        self, results: list[KnowledgeResult], total: int,
    ) -> list[KnowledgeResult]:
        if not results:
            return results
        repos = sorted({r.repository_id for r in results})
        if len(repos) <= 1:
            return results
        min_q = max(1, total // (len(repos) * 2))
        by_repo: dict[str, list[KnowledgeResult]] = {r: [] for r in repos}
        for r in results:
            by_repo[r.repository_id].append(r)
        for r in repos:
            by_repo[r].sort(key=lambda x: -x.native_score)
        out: list[KnowledgeResult] = []
        for r in repos:
            out.extend(by_repo[r][:min_q])
        remaining = total - len(out)
        rest = []
        for r in repos:
            rest.extend(by_repo[r][min_q:])
        rest.sort(key=lambda x: -x.native_score)
        out.extend(rest[: max(0, remaining + total)])  # rank will cut later
        return out

    def _legacy_shadow(self, query: KnowledgeQuery) -> dict:
        try:
            from saathi.codebase_memory.retrieve import search
            root = None
            for s in self.sources:
                if s.source_type == "codebase_index":
                    root = s.location
                    break
            r = search(query.query, project_root=root, top_k=query.resolved_top_k())
            return {
                "ok": r.ok,
                "hit_count": len(r.hits or []),
                "paths": [h.path for h in (r.hits or [])[:8]],
            }
        except Exception as e:
            return {"ok": False, "error": type(e).__name__}

    def _emit(self, event: str, payload: dict) -> None:
        self._events.append({"type": event, "payload": payload})
        if len(self._events) > 100:
            del self._events[: len(self._events) - 100]
        try:
            from saathi.events import bus as bus_mod
            b = getattr(bus_mod, "default_bus", None)
            if callable(b):
                b().emit(event, "knowledge_service", payload)
        except Exception:
            pass

    def recent_events(self, limit: int = 20) -> list[dict]:
        return list(self._events[-limit:])


_default: KnowledgeService | None = None


def default_knowledge_service(**kwargs) -> KnowledgeService:
    global _default
    if kwargs:
        return KnowledgeService(**kwargs)
    if _default is None:
        _default = KnowledgeService()
    return _default


def reset_default_knowledge_service() -> None:
    global _default
    _default = None
