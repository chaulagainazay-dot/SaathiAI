"""M19.0 — Unified Knowledge Service (retrieval router + multi-repo context).

Coordinates existing retrieval (codebase memory, docs, registered sources).
Does **not** replace memory, knowledge graph, indexes, or InsForge control.
"""
from __future__ import annotations

from saathi.knowledge.service import KnowledgeService, default_knowledge_service
from saathi.knowledge.types import KnowledgeQuery, KnowledgeResponse, RetrievalProfile

__all__ = [
    "KnowledgeQuery",
    "KnowledgeResponse",
    "KnowledgeService",
    "RetrievalProfile",
    "default_knowledge_service",
]
