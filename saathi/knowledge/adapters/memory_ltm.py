"""Optional long-term memory adapter — mission context only; never code authority."""
from __future__ import annotations

from saathi.knowledge.registry import KnowledgeSource
from saathi.knowledge.types import (
    EvidenceClass,
    KnowledgeQuery,
    KnowledgeResult,
    RetrievalProfile,
    content_fingerprint,
)
from saathi.mcp_governance.redaction import redact_text


class MemoryLtmAdapter:
    name = "memory_ltm"

    def supports(self, query: KnowledgeQuery, source: KnowledgeSource) -> bool:
        if source.adapter != self.name:
            return False
        # Only mission context may pull LTM by default
        return query.profile == RetrievalProfile.MISSION_CONTEXT

    def describe_capabilities(self) -> dict:
        return {"name": self.name, "modes": ["keyword"], "mutates": False}

    def health(self, source: KnowledgeSource) -> dict:
        return {"ok": True, "status": "optional"}

    def retrieve(
        self,
        query: KnowledgeQuery,
        source: KnowledgeSource,
        *,
        limit: int = 8,
    ) -> list[KnowledgeResult]:
        try:
            from saathi.memory.engine import core as mem_core
            eng = getattr(mem_core, "default_engine", None)
            if eng is None:
                return []
            engine = eng() if callable(eng) else eng
            if hasattr(engine, "retrieve_for_chat"):
                pack = engine.retrieve_for_chat(
                    query.query, user=query.permission_actor or "ajay",
                )
                results = pack.get("memories") or pack.get("results") or []
                mode = pack.get("mode", "ltm")
            elif hasattr(engine, "retrieve"):
                results, mode, _ = engine.retrieve(
                    query.query, actor=query.permission_actor or "ajay",
                )
            else:
                return []
        except Exception:
            return []

        out: list[KnowledgeResult] = []
        for row in (results or [])[:limit]:
            if isinstance(row, dict):
                content = str(row.get("content") or row.get("text") or "")[:400]
                mid = str(row.get("id") or content_fingerprint(content))
            else:
                content = str(getattr(row, "content", row))[:400]
                mid = str(getattr(row, "id", content_fingerprint(content)))
            content = redact_text(content, max_len=400)
            out.append(KnowledgeResult(
                result_id=f"{source.source_id}:{mid}",
                source_id=source.source_id,
                source_type=source.source_type,
                repository_id=source.repository_id,
                object_id=mid,
                path=f"memory:{mid}",
                title="ltm",
                excerpt=content,
                normalized_content=content,
                native_score=0.5,
                normalized_score=0.4,
                trust_score=0.55,
                freshness_score=0.5,
                final_score=0.0,
                evidence_class=EvidenceClass.OPERATIONAL_RECORD,
                is_generated=False,
                provenance={"adapter": self.name, "mode": str(mode) if 'mode' in dir() else ""},
                content_fingerprint=content_fingerprint(content),
                warnings=["ltm_not_code_authority"],
            ))
        return out
