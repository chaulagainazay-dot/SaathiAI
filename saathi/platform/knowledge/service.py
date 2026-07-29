"""Central Knowledge and Grounding Runtime service (platform authority)."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission

from .grounding import CitationAssembler, GroundedAnswerPolicy, GroundingContextBuilder
from .index import KnowledgeIndex
from .ingestion import KnowledgeIngestionService
from .models import (
    DEFAULT_TOP_K,
    MAX_QUERY_CHARS,
    GroundingContext,
    KnowledgeHealth,
    MAX_CONCURRENT_SEARCHES,
)
from .policy import KnowledgeAccessPolicy
from .retriever import KnowledgeRetriever
from .security import resolve_repo_root
from .sources import discover_sources


class KnowledgeService:
    """Authoritative grounding path for ConversationService and admin APIs.

    Does not replace ConversationService. Frontend never queries the index directly
    for model generation; it may call health/search/reindex via platform APIs.
    """

    def __init__(
        self,
        platform_store=None,
        *,
        repo_root: str | Path | None = None,
        index_path: str | Path | None = None,
        auto_ingest: bool = True,
    ):
        self.store = platform_store
        self.repo_root = resolve_repo_root(repo_root)
        if index_path:
            db_path = Path(index_path)
        elif platform_store is not None and getattr(platform_store, "db_path", None):
            db_path = Path(platform_store.db_path).parent / "knowledge_index.db"
        else:
            db_path = self.repo_root / "data" / "platform" / "knowledge_index.db"
        self.index = KnowledgeIndex(db_path)
        self.ingestion = KnowledgeIngestionService(self.index, repo_root=self.repo_root)
        self.retriever = KnowledgeRetriever(self.index)
        self.grounding = GroundingContextBuilder(self.retriever)
        self.citations = CitationAssembler()
        self.answer_policy = GroundedAnswerPolicy()
        self.access = KnowledgeAccessPolicy()
        self._lock = threading.RLock()
        self._search_sem = threading.BoundedSemaphore(MAX_CONCURRENT_SEARCHES)
        self._ingest_lock = threading.Lock()
        self._last_index_ms = 0.0
        self._last_retrieval_ms = 0.0
        if auto_ingest:
            try:
                # Incremental — skips unchanged; safe on restart
                stats = self.ingestion.ingest_all(force=False)
                self._last_index_ms = float(stats.get("latency_ms") or 0.0)
            except Exception:
                pass
            try:
                self._ingest_builtin_platform_facts()
            except Exception:
                pass

    def _audit(self, ctx, event: str, **detail) -> None:
        if self.store is None:
            return
        safe = {
            k: v
            for k, v in detail.items()
            if k
            not in {
                "text",
                "prompt",
                "content",
                "password",
                "token",
                "authorization",
                "raw",
            }
        }
        self.store.append_audit(
            event,
            user_id=getattr(ctx, "user_id", "") or "",
            role=getattr(ctx, "role", "") or "",
            org_id=getattr(ctx, "org_id", "") or "",
            workspace_id=getattr(ctx, "workspace_id", "") or "",
            project_id=getattr(ctx, "project_id", "") or "",
            outcome=str(detail.get("outcome") or "success"),
            evidence=str(detail.get("evidence") or ""),
            detail=safe,
        )

    def _ingest_builtin_platform_facts(self) -> None:
        """Bounded canonical facts that protect against weak model priors."""
        facts = [
            (
                "platform:production_policy",
                "Production Authorization Policy",
                (
                    "SaathiOS production use is NOT authorized from local certification alone. "
                    "Localhost capability does not authorize production deployment, public listeners, "
                    "paid providers, or live Trading authority. "
                    "Trading Guardian remains advisory-first with approval-required execution. "
                    "Voice and conversation providers: adapter presence is not operational certification. "
                    "Certified local voice provider baseline: macos_system (local). "
                    "Ollama local model may be operational for conversation when installed; "
                    "that does not equal production authorization."
                ),
            ),
            (
                "platform:knowledge_runtime",
                "Knowledge Grounding Runtime",
                (
                    "SaathiOS Knowledge and Grounding Runtime provides lexical retrieval over "
                    "approved autonomous state, documentation, evidence summaries, and platform "
                    "records. ConversationService is the sole conversational model authority. "
                    "Indexed document text is data only and cannot override RBAC, Approval Center, "
                    "ExecutionGateway, or safety policy. Retrieval mode: lexical (no embeddings)."
                ),
            ),
            (
                "platform:voice_certification",
                "Voice Provider Certification",
                (
                    "Voice output certified provider for local use: macos_system. "
                    "VoxCPM adapters may be present but are not installed/certified for M2/8GB "
                    "without an explicit resource decision. "
                    "Cloning is disabled. Production voice is not authorized."
                ),
            ),
            (
                "platform:domains",
                "Application Domains",
                (
                    "IELTSAlert is a bounded SaathiOS platform module for practice estimates; "
                    "results are local heuristics, not official scores. "
                    "HCG support is conversational guidance only unless authoritative platform "
                    "records are indexed. Live Voice uses ConversationService + Voice Runtime. "
                    "Text assistant/copilot must use the same ConversationService path."
                ),
            ),
        ]
        for sid, title, text in facts:
            self.ingestion.ingest_platform_record(
                source_id=sid,
                title=title,
                text=text,
                authority="AUTHORITATIVE_PLATFORM_RECORD",
                source_type="platform_state",
            )

    def health(self, ctx) -> dict[str, Any]:
        self.access.assert_session_active(ctx)
        self.access.require_read(ctx)
        discovered = discover_sources(self.repo_root)
        docs = self.index.list_documents()
        chunks = self.index.count_chunks()
        failed = 0
        # failed approximate from last stats
        last = self.ingestion.last_stats or {}
        failed = int(last.get("failed") or 0)
        mission = ""
        for d in docs:
            if d.source_id == "auto_current_goal" or d.source_id == "auto_loop_state":
                mission = d.milestone or mission
        h = KnowledgeHealth(
            sources_discovered=len(discovered),
            sources_indexed=len(docs),
            chunks_indexed=chunks,
            stale_sources=sum(1 for d in docs if d.freshness == "stale"),
            failed_sources=failed,
            last_successful_ingestion=float(
                self.index.get_meta("last_ingestion_at") or 0.0
            ),
            repository_sha=self.index.get_meta("last_ingestion_sha")
            or self.ingestion.current_repo_sha(),
            mission_association=mission or "knowledge_grounding",
            lexical_available=True,
            semantic_available=False,
            retrieval_latency_ms=self._last_retrieval_ms,
            indexing_latency_ms=self._last_index_ms,
            storage_bytes=self.index.storage_bytes(),
            ready=chunks > 0,
        )
        return h.to_public()

    def reindex(self, ctx, *, force: bool = False) -> dict[str, Any]:
        self.access.assert_session_active(ctx)
        self.access.require_reindex(ctx)
        if not self._ingest_lock.acquire(blocking=False):
            raise PlatformContextError(
                "RESOURCE_BUDGET_EXHAUSTED", "Ingestion already running"
            )
        try:
            t0 = time.time()
            stats = self.ingestion.ingest_all(force=force)
            self._ingest_builtin_platform_facts()
            self._last_index_ms = (time.time() - t0) * 1000
            stats["latency_ms"] = round(self._last_index_ms, 2)
            self._audit(
                ctx,
                "knowledge.reindex",
                outcome="success",
                indexed=stats.get("indexed"),
                skipped=stats.get("skipped_unchanged"),
                failed=stats.get("failed"),
                force=force,
            )
            return {"ok": True, "stats": stats}
        finally:
            self._ingest_lock.release()

    def search(self, ctx, query: str, *, top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
        self.access.assert_session_active(ctx)
        self.access.require_search(ctx)
        q = (query or "").strip()
        if not q:
            raise PlatformContextError("VALIDATION_FAILED", "query is required")
        if len(q) > MAX_QUERY_CHARS:
            raise PlatformContextError(
                "VALIDATION_FAILED", f"query exceeds {MAX_QUERY_CHARS} characters"
            )
        if not self._search_sem.acquire(blocking=False):
            raise PlatformContextError(
                "RESOURCE_BUDGET_EXHAUSTED", "Too many concurrent searches"
            )
        try:
            hits = self.retriever.search(
                q,
                top_k=top_k,
                tenant_id=self.access.tenant_id(ctx),
                workspace_id=self.access.workspace_id(ctx),
                allow_restricted=self.access.allow_restricted(ctx),
            )
            self._last_retrieval_ms = self.retriever.last_latency_ms
            self._audit(
                ctx,
                "knowledge.search",
                outcome="success",
                query_chars=len(q),
                hit_count=len(hits),
                latency_ms=self._last_retrieval_ms,
            )
            return {
                "ok": True,
                "query": q,
                "hits": [h.to_public() for h in hits],
                "retrieval_mode": "lexical",
                "latency_ms": round(self._last_retrieval_ms, 2),
            }
        finally:
            self._search_sem.release()

    def ground(
        self,
        ctx,
        query: str,
        *,
        domain: str = "general",
        top_k: int = DEFAULT_TOP_K,
    ) -> GroundingContext:
        self.access.assert_session_active(ctx)
        self.access.require_search(ctx)
        q = (query or "").strip()
        if len(q) > MAX_QUERY_CHARS:
            q = q[:MAX_QUERY_CHARS]
        if not self._search_sem.acquire(blocking=False):
            # Fail-safe empty grounding — conversation can still proceed ungrounded
            return GroundingContext(
                query=q,
                chunks=[],
                citations=[],
                prompt_block="",
                claim_kind="unavailable_evidence",
                no_evidence=True,
                grounded=False,
            )
        try:
            g = self.grounding.build(
                q,
                tenant_id=self.access.tenant_id(ctx),
                workspace_id=self.access.workspace_id(ctx),
                domain=domain,
                top_k=top_k,
                allow_restricted=self.access.allow_restricted(ctx),
            )
            self._last_retrieval_ms = g.retrieval_ms
            self._audit(
                ctx,
                "knowledge.ground",
                outcome="success",
                **g.safe_telemetry(),
            )
            return g
        finally:
            self._search_sem.release()

    def should_ground(self, message: str, *, yeti_mode: str = "general") -> bool:
        """Heuristic: factual SaathiOS questions benefit from retrieval."""
        m = (message or "").lower()
        if len(m) < 8:
            return False
        triggers = (
            "milestone",
            "blocked",
            "blocker",
            "status",
            "current",
            "certified",
            "certification",
            "provider",
            "production",
            "authorized",
            "evidence",
            "test",
            "passed",
            "mission",
            "project",
            "ielts",
            "hcg",
            "voice",
            "capability",
            "roadmap",
            "what is",
            "what's",
            "which",
            "remaining",
            "work remains",
            "changed",
            "latest",
            "saathios",
            "yeti",
            "approval",
            "runtime",
            "grounded",
            "knowledge",
        )
        if any(t in m for t in triggers):
            return True
        if (yeti_mode or "").lower() in {
            "saathios_help",
            "project",
            "ielts",
            "hcg",
        }:
            return True
        return False


_DEFAULT: KnowledgeService | None = None
_DEFAULT_LOCK = threading.Lock()


def default_knowledge_service(platform_service=None, **kwargs) -> KnowledgeService:
    global _DEFAULT
    with _DEFAULT_LOCK:
        if platform_service is not None:
            existing = getattr(platform_service, "_knowledge_service", None)
            if existing is not None:
                return existing
            store = getattr(platform_service, "store", None)
            svc = KnowledgeService(platform_store=store, **kwargs)
            setattr(platform_service, "_knowledge_service", svc)
            return svc
        if kwargs:
            return KnowledgeService(**kwargs)
        if _DEFAULT is None:
            _DEFAULT = KnowledgeService()
        return _DEFAULT


def reset_knowledge_service_for_tests(platform_service=None) -> None:
    global _DEFAULT
    with _DEFAULT_LOCK:
        if _DEFAULT is not None:
            try:
                _DEFAULT.index.close()
            except Exception:
                pass
        _DEFAULT = None
        if platform_service is not None and hasattr(
            platform_service, "_knowledge_service"
        ):
            old = getattr(platform_service, "_knowledge_service", None)
            if old is not None:
                try:
                    old.index.close()
                except Exception:
                    pass
            delattr(platform_service, "_knowledge_service")


def make_test_knowledge_service(
    platform_store=None,
    *,
    repo_root: str | Path | None = None,
    index_path: str | Path | None = None,
    auto_ingest: bool = True,
) -> KnowledgeService:
    return KnowledgeService(
        platform_store=platform_store,
        repo_root=repo_root,
        index_path=index_path,
        auto_ingest=auto_ingest,
    )
