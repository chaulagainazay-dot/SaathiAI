"""SaathiOS Knowledge and Grounding Runtime (M87–M94).

Centralized retrieval for ConversationService / Yeti. Does not create a parallel
assistant, search authority for execution, or bypass of RBAC/Approval/Gateway.
"""
from __future__ import annotations

from .grounding import CitationAssembler, GroundedAnswerPolicy, GroundingContextBuilder
from .models import (
    ClaimKind,
    Citation,
    GroundingContext,
    KnowledgeChunk,
    KnowledgeDocument,
    SourceAuthority,
)
from .service import (
    KnowledgeService,
    default_knowledge_service,
    make_test_knowledge_service,
    reset_knowledge_service_for_tests,
)

__all__ = [
    "Citation",
    "CitationAssembler",
    "ClaimKind",
    "GroundedAnswerPolicy",
    "GroundingContext",
    "GroundingContextBuilder",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeService",
    "SourceAuthority",
    "default_knowledge_service",
    "make_test_knowledge_service",
    "reset_knowledge_service_for_tests",
]
