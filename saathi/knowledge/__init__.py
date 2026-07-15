"""M19.0–M19.3 — Unified Knowledge Service + adoption + campaigns + pilot promotion.

Coordinates existing retrieval (codebase memory, docs, registered sources).
Does **not** replace memory, knowledge graph, indexes, or InsForge control.

M19.1 adds first-wave caller adoption with rollout modes, shadow evaluation,
and governed fallback — without new retrieval infrastructure.

M19.2 adds shadow evaluation campaign metrics and second-wave callers
(control-center repository search, repair-context prepare).

M19.3 runs real-index campaigns and promotes exactly one low-risk caller
(``codebase_memory_search``) to ``unified_with_fallback`` with per-caller
disable and ``SAATHI_KS_DISABLE_PROMOTIONS``.
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
from saathi.knowledge.composer import (
    ComposerProfile,
    ComposedContext,
    compose_context,
    compose_for_mission,
    compose_from_response,
    composer_profiles,
)
from saathi.knowledge.real_campaign import (
    run_real_index_campaign,
    write_campaign_report,
)
from saathi.knowledge.rollout import RolloutMode, resolve_mode, rollout_snapshot
from saathi.knowledge.service import KnowledgeService, default_knowledge_service
from saathi.knowledge.types import KnowledgeQuery, KnowledgeResponse, RetrievalProfile

__all__ = [
    "ComposerProfile",
    "ComposedContext",
    "KnowledgeQuery",
    "KnowledgeResponse",
    "KnowledgeService",
    "RetrievalProfile",
    "RolloutMode",
    "adopt_retrieve",
    "adopted_codebase_search",
    "audit_evidence_lookup",
    "compose_context",
    "compose_for_mission",
    "compose_from_response",
    "composer_profiles",
    "control_center_repository_search",
    "default_knowledge_service",
    "metrics_snapshot",
    "mission_context_prepare",
    "repair_context_prepare",
    "resolve_mode",
    "rollout_snapshot",
    "run_real_index_campaign",
    "write_campaign_report",
]
