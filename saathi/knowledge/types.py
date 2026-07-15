"""Canonical knowledge query / result / plan contracts (M19.0)."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RetrievalProfile(str, Enum):
    FAST_LOOKUP = "FAST_LOOKUP"
    CODE_EXPLAIN = "CODE_EXPLAIN"
    MULTI_REPO_COMPARE = "MULTI_REPO_COMPARE"
    MISSION_CONTEXT = "MISSION_CONTEXT"
    AUDIT_EVIDENCE = "AUDIT_EVIDENCE"


class RetrievalIntent(str, Enum):
    LOCATE_SYMBOL = "locate_symbol"
    EXPLAIN_ARCHITECTURE = "explain_architecture"
    FIND_IMPLEMENTATION = "find_implementation"
    FIND_TESTS = "find_tests"
    FIND_DOCUMENTATION = "find_documentation"
    FIND_RECENT_CHANGE = "find_recent_change"
    COMPARE_REPOSITORIES = "compare_repositories"
    RETRIEVE_DECISION_HISTORY = "retrieve_decision_history"
    RETRIEVE_PROCEDURE = "retrieve_operational_procedure"
    GATHER_MISSION_CONTEXT = "gather_mission_context"
    INSPECT_PROVIDER = "inspect_provider_capability"
    GENERAL_REPO = "general_repository_question"


class EvidenceClass(str, Enum):
    PRIMARY_CODE = "primary_code"
    PRIMARY_TESTS = "primary_tests"
    CANONICAL_DOCS = "canonical_documentation"
    OPERATIONAL_RECORD = "structured_operational_record"
    PROVIDER_METADATA = "approved_repository_metadata"
    GENERATED_SUMMARY = "generated_summary"
    INFERRED = "inferred_relationship"
    UNVERIFIED_EXTERNAL = "unverified_external"


class TrustLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNTRUSTED = "untrusted"


# Profile → default budgets (characters for context package)
PROFILE_BUDGETS = {
    RetrievalProfile.FAST_LOOKUP: 4_000,
    RetrievalProfile.CODE_EXPLAIN: 12_000,
    RetrievalProfile.MULTI_REPO_COMPARE: 16_000,
    RetrievalProfile.MISSION_CONTEXT: 14_000,
    RetrievalProfile.AUDIT_EVIDENCE: 10_000,
}

PROFILE_TOP_K = {
    RetrievalProfile.FAST_LOOKUP: 5,
    RetrievalProfile.CODE_EXPLAIN: 12,
    RetrievalProfile.MULTI_REPO_COMPARE: 16,
    RetrievalProfile.MISSION_CONTEXT: 14,
    RetrievalProfile.AUDIT_EVIDENCE: 10,
}


@dataclass
class KnowledgeQuery:
    query: str
    profile: RetrievalProfile = RetrievalProfile.CODE_EXPLAIN
    intent: RetrievalIntent = RetrievalIntent.GENERAL_REPO
    requesting_component: str = "agent"
    mission_id: str = ""
    run_id: str = ""
    workspace_id: str = "default"
    tenant_id: str = "default"
    repository_ids: list[str] = field(default_factory=list)  # empty = default registry set
    source_type_allowlist: list[str] = field(default_factory=list)
    source_type_denylist: list[str] = field(default_factory=list)
    path_filters: list[str] = field(default_factory=list)
    language_filters: list[str] = field(default_factory=list)
    max_results: int = 0  # 0 → profile default
    max_context_chars: int = 0  # 0 → profile default
    min_trust: TrustLevel = TrustLevel.LOW
    include_generated: bool = False
    permission_actor: str = "system"
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    shadow_compare_legacy: bool = False

    def resolved_top_k(self) -> int:
        if self.max_results > 0:
            return min(int(self.max_results), 40)
        return PROFILE_TOP_K[self.profile]

    def resolved_budget(self) -> int:
        if self.max_context_chars > 0:
            return min(int(self.max_context_chars), 40_000)
        return PROFILE_BUDGETS[self.profile]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["profile"] = self.profile.value
        d["intent"] = self.intent.value
        d["min_trust"] = self.min_trust.value
        return d


@dataclass
class SourceSelection:
    source_id: str
    selected: bool
    reason: str
    query_variant: str = ""
    limit: int = 8
    timeout_sec: float = 5.0


@dataclass
class RetrievalPlan:
    request_id: str
    profile: str
    intent: str
    selections: list[SourceSelection]
    ranking_strategy: str = "weighted_fusion_v1"
    parallel: bool = False  # sequential default for determinism
    fallback: str = "codebase_memory_only"
    total_result_quota: int = 12

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "profile": self.profile,
            "intent": self.intent,
            "selections": [asdict(s) for s in self.selections],
            "ranking_strategy": self.ranking_strategy,
            "parallel": self.parallel,
            "fallback": self.fallback,
            "total_result_quota": self.total_result_quota,
            "selected_ids": [s.source_id for s in self.selections if s.selected],
            "rejected": [
                {"source_id": s.source_id, "reason": s.reason}
                for s in self.selections if not s.selected
            ],
        }


@dataclass
class KnowledgeResult:
    result_id: str
    source_id: str
    source_type: str
    repository_id: str
    object_id: str
    path: str
    title: str
    excerpt: str
    normalized_content: str
    native_score: float
    normalized_score: float
    trust_score: float
    freshness_score: float
    final_score: float
    evidence_class: EvidenceClass
    is_generated: bool
    language: str = ""
    timestamp: float = 0.0
    permission_scope: str = "internal"
    provenance: dict = field(default_factory=dict)
    start_line: int = 0
    end_line: int = 0
    content_fingerprint: str = ""
    warnings: list[str] = field(default_factory=list)
    score_explanation: list[str] = field(default_factory=list)
    duplicate_of: str = ""
    duplicate_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_class"] = self.evidence_class.value
        return d


@dataclass
class ContextPackage:
    text: str
    char_count: int
    budget: int
    truncated: bool
    included_result_ids: list[str]
    excluded_reasons: list[dict]
    fingerprint: str
    version: str = "m19.0.1"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class KnowledgeResponse:
    ok: bool
    request_id: str
    query: str
    plan: dict
    results: list[KnowledgeResult] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    dedupe_meta: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    errors: list[dict] = field(default_factory=list)
    legacy_shadow: dict | None = None
    denied: bool = False
    error_category: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "request_id": self.request_id,
            "query": self.query,
            "plan": self.plan,
            "results": [r.to_dict() for r in self.results],
            "context": self.context,
            "dedupe_meta": self.dedupe_meta,
            "latency_ms": round(self.latency_ms, 2),
            "errors": self.errors,
            "legacy_shadow": self.legacy_shadow,
            "denied": self.denied,
            "error_category": self.error_category,
        }


def content_fingerprint(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()[:16]


def classify_intent(query: str, profile: RetrievalProfile) -> RetrievalIntent:
    q = (query or "").lower()
    if profile == RetrievalProfile.FAST_LOOKUP:
        if any(x in q for x in ("test ", "tests", "pytest")):
            return RetrievalIntent.FIND_TESTS
        return RetrievalIntent.LOCATE_SYMBOL
    if profile == RetrievalProfile.MULTI_REPO_COMPARE:
        return RetrievalIntent.COMPARE_REPOSITORIES
    if profile == RetrievalProfile.MISSION_CONTEXT:
        return RetrievalIntent.GATHER_MISSION_CONTEXT
    if profile == RetrievalProfile.AUDIT_EVIDENCE:
        return RetrievalIntent.RETRIEVE_DECISION_HISTORY
    if any(x in q for x in ("where is", "defined", "symbol", "function", "class ")):
        return RetrievalIntent.LOCATE_SYMBOL
    if any(x in q for x in ("how does", "architecture", "design", "explain")):
        return RetrievalIntent.EXPLAIN_ARCHITECTURE
    if "test" in q:
        return RetrievalIntent.FIND_TESTS
    if any(x in q for x in ("doc", "readme", "milestone", "roadmap")):
        return RetrievalIntent.FIND_DOCUMENTATION
    if "provider" in q or "insforge" in q:
        return RetrievalIntent.INSPECT_PROVIDER
    return RetrievalIntent.FIND_IMPLEMENTATION
