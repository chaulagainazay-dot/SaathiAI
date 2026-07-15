"""M19.0–M19.2 — Unified Knowledge Service + adoption + shadow campaign.

Coordinates existing retrieval (codebase memory, docs, registered sources).
Does **not** replace memory, knowledge graph, indexes, or InsForge control.

M19.1 adds first-wave caller adoption with rollout modes, shadow evaluation,
and governed fallback — without new retrieval infrastructure.

M19.2 adds shadow evaluation campaign metrics and second-wave callers
(control-center repository search, repair-context prepare).
"""
from __future__ import annotations

from saathi.knowledge.adoption import (
    adopt_retrieve,
    adopted_codebase_search,
    audit_evidence_lookup,
    control_center_repository_search,
    metrics_snapshot,
    mission_context_prepare,
    repair_context_prepare,
)
from saathi.knowledge.rollout import RolloutMode, resolve_mode, rollout_snapshot
from saathi.knowledge.service import KnowledgeService, default_knowledge_service
from saathi.knowledge.types import KnowledgeQuery, KnowledgeResponse, RetrievalProfile

__all__ = [
    "KnowledgeQuery",
    "KnowledgeResponse",
    "KnowledgeService",
    "RetrievalProfile",
    "RolloutMode",
    "adopt_retrieve",
    "adopted_codebase_search",
    "audit_evidence_lookup",
    "control_center_repository_search",
    "default_knowledge_service",
    "metrics_snapshot",
    "mission_context_prepare",
    "repair_context_prepare",
    "resolve_mode",
    "rollout_snapshot",
]
