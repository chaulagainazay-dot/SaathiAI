"""M62.3 — canonical, server-side research domain.

Evidence-backed research substrate. Reuses M62.1/M62.2 read-only (market data as
evidence). NO trading, approval, broker, or execution authority. Source text is
untrusted data — it can never choose tools, expand permissions, or trigger
execution. Fact classification is mandatory before a statement may enter a
published thesis.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── classifications ───────────────────────────────────────────────────────────
class FactClass(str, Enum):
    FACT = "FACT"
    CALCULATION = "CALCULATION"
    ASSUMPTION = "ASSUMPTION"
    INFERENCE = "INFERENCE"
    OPINION = "OPINION"
    FORECAST = "FORECAST"


class SourceType(str, Enum):
    LOCAL_DOCUMENT = "LOCAL_DOCUMENT"
    PLATFORM_MARKET_DATA = "PLATFORM_MARKET_DATA"
    STRUCTURED_DATASET = "STRUCTURED_DATASET"
    OPERATOR_NOTE = "OPERATOR_NOTE"
    APPROVED_WEB_SOURCE_REFERENCE = "APPROVED_WEB_SOURCE_REFERENCE"
    API_RESULT = "API_RESULT"
    RESEARCH_OUTPUT = "RESEARCH_OUTPUT"


class TrustClass(str, Enum):
    PRIMARY_AUTHORITY = "PRIMARY_AUTHORITY"
    REGULATORY_OR_OFFICIAL = "REGULATORY_OR_OFFICIAL"
    COMPANY_DISCLOSURE = "COMPANY_DISCLOSURE"
    REPUTABLE_STRUCTURED_DATA = "REPUTABLE_STRUCTURED_DATA"
    REPUTABLE_NEWS = "REPUTABLE_NEWS"
    SPECIALIST_RESEARCH = "SPECIALIST_RESEARCH"
    SECONDARY_COMMENTARY = "SECONDARY_COMMENTARY"
    OPERATOR_SUPPLIED = "OPERATOR_SUPPLIED"
    UNVERIFIED = "UNVERIFIED"
    REJECTED = "REJECTED"


class SourceQuality(str, Enum):
    UNVERIFIED = "UNVERIFIED"      # initial, pre-classification
    VALID = "VALID"
    STALE = "STALE"
    INCOMPLETE = "INCOMPLETE"
    UNVERIFIED_AUTHOR = "UNVERIFIED_AUTHOR"
    MISSING_DATE = "MISSING_DATE"
    MISSING_LOCATOR = "MISSING_LOCATOR"
    DUPLICATE = "DUPLICATE"
    SUPERSEDED = "SUPERSEDED"
    CONFLICT_OF_INTEREST = "CONFLICT_OF_INTEREST"
    PROMPT_INJECTION_SUSPECTED = "PROMPT_INJECTION_SUSPECTED"
    MALFORMED = "MALFORMED"
    REJECTED = "REJECTED"


class InjectionState(str, Enum):
    CLEAN = "CLEAN"
    SUSPECTED = "SUSPECTED"
    BLOCKED = "BLOCKED"


class Verification(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class ContradictionType(str, Enum):
    DIRECT_CONFLICT = "DIRECT_CONFLICT"
    NUMERICAL_CONFLICT = "NUMERICAL_CONFLICT"
    TEMPORAL_CONFLICT = "TEMPORAL_CONFLICT"
    SCOPE_CONFLICT = "SCOPE_CONFLICT"
    DEFINITION_CONFLICT = "DEFINITION_CONFLICT"
    SOURCE_REVISION = "SOURCE_REVISION"
    FORECAST_DISAGREEMENT = "FORECAST_DISAGREEMENT"


# ── orchestration state machine ───────────────────────────────────────────────
class ResearchState(str, Enum):
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    COLLECTING_SOURCES = "COLLECTING_SOURCES"
    VALIDATING_SOURCES = "VALIDATING_SOURCES"
    EXTRACTING_CLAIMS = "EXTRACTING_CLAIMS"
    VERIFYING_CITATIONS = "VERIFYING_CITATIONS"
    SEARCHING_CONTRADICTIONS = "SEARCHING_CONTRADICTIONS"
    SYNTHESIZING = "SYNTHESIZING"
    CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"
    UNDER_CHALLENGE = "UNDER_CHALLENGE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    APPROVED_FOR_PUBLICATION = "APPROVED_FOR_PUBLICATION"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


RESEARCH_TRANSITIONS: dict[ResearchState, frozenset[ResearchState]] = {
    ResearchState.DRAFT: frozenset({ResearchState.PLANNED, ResearchState.FAILED}),
    ResearchState.PLANNED: frozenset({ResearchState.COLLECTING_SOURCES, ResearchState.FAILED}),
    ResearchState.COLLECTING_SOURCES: frozenset({ResearchState.VALIDATING_SOURCES, ResearchState.FAILED}),
    ResearchState.VALIDATING_SOURCES: frozenset({ResearchState.EXTRACTING_CLAIMS, ResearchState.REJECTED, ResearchState.FAILED}),
    ResearchState.EXTRACTING_CLAIMS: frozenset({ResearchState.VERIFYING_CITATIONS, ResearchState.FAILED}),
    ResearchState.VERIFYING_CITATIONS: frozenset({ResearchState.SEARCHING_CONTRADICTIONS, ResearchState.REJECTED, ResearchState.FAILED}),
    ResearchState.SEARCHING_CONTRADICTIONS: frozenset({ResearchState.SYNTHESIZING, ResearchState.FAILED}),
    ResearchState.SYNTHESIZING: frozenset({ResearchState.CHALLENGE_REQUIRED, ResearchState.FAILED}),
    ResearchState.CHALLENGE_REQUIRED: frozenset({ResearchState.UNDER_CHALLENGE, ResearchState.FAILED}),
    ResearchState.UNDER_CHALLENGE: frozenset({ResearchState.HUMAN_REVIEW_REQUIRED, ResearchState.SYNTHESIZING, ResearchState.REJECTED, ResearchState.FAILED}),
    ResearchState.HUMAN_REVIEW_REQUIRED: frozenset({ResearchState.APPROVED_FOR_PUBLICATION, ResearchState.SYNTHESIZING, ResearchState.REJECTED}),
    ResearchState.APPROVED_FOR_PUBLICATION: frozenset({ResearchState.PUBLISHED, ResearchState.REJECTED}),
    ResearchState.PUBLISHED: frozenset({ResearchState.EXPIRED}),
    ResearchState.REJECTED: frozenset(),
    ResearchState.EXPIRED: frozenset(),
    ResearchState.FAILED: frozenset(),
}


def can_research_transition(cur: ResearchState | str, tgt: ResearchState | str) -> bool:
    c = ResearchState(cur) if not isinstance(cur, ResearchState) else cur
    t = ResearchState(tgt) if not isinstance(tgt, ResearchState) else tgt
    return t in RESEARCH_TRANSITIONS.get(c, frozenset())


class ThesisState(str, Enum):
    DRAFT = "DRAFT"
    CHALLENGED = "CHALLENGED"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    REVIEW_READY = "REVIEW_READY"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


# ── hashing ───────────────────────────────────────────────────────────────────
def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ── records (lightweight; persisted as rows/JSON by store.py) ─────────────────
@dataclass
class ResearchSource:
    source_id: str
    project_id: str
    org_id: str
    workspace_id: str
    source_type: SourceType
    title: str
    locator: str = ""                 # URL / doc id / dataset ref — NOT a fetchable proxy
    content: str = ""                 # raw source text (untrusted data)
    publisher: str = ""
    author: str = ""
    published_at: float = 0.0
    retrieved_at: float = 0.0
    effective_at: float = 0.0
    mime_type: str = "text/plain"
    language: str = "en"
    trust: TrustClass = TrustClass.UNVERIFIED
    quality: SourceQuality = SourceQuality.UNVERIFIED
    injection: InjectionState = InjectionState.CLEAN
    findings: list[str] = field(default_factory=list)
    hash: str = ""

    def compute_hash(self) -> str:
        self.hash = content_hash(self.content)
        return self.hash

    def to_public(self, *, include_content: bool = False) -> dict[str, Any]:
        d = {
            "source_id": self.source_id, "project_id": self.project_id,
            "source_type": self.source_type.value, "title": self.title, "locator": self.locator,
            "publisher": self.publisher, "author": self.author, "published_at": self.published_at,
            "retrieved_at": self.retrieved_at, "effective_at": self.effective_at,
            "mime_type": self.mime_type, "language": self.language, "trust": self.trust.value,
            "quality": self.quality.value, "injection": self.injection.value,
            "findings": self.findings, "hash": self.hash,
        }
        if include_content:
            d["content"] = self.content
        return d


@dataclass
class Claim:
    claim_id: str
    project_id: str
    source_id: str
    statement: str
    fact_class: FactClass
    locator: str                      # must resolve within the source
    confidence: float = 0.5
    materiality: str = "medium"       # low|medium|high
    time_relevance: float = 0.0
    agent_role: str = ""
    model_provenance: str = "rule_based_extractor"
    verification: Verification = Verification.UNVERIFIED
    excerpt: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id, "project_id": self.project_id, "source_id": self.source_id,
            "statement": self.statement, "fact_class": self.fact_class.value, "locator": self.locator,
            "confidence": self.confidence, "materiality": self.materiality,
            "time_relevance": self.time_relevance, "agent_role": self.agent_role,
            "model_provenance": self.model_provenance, "verification": self.verification.value,
            "excerpt": self.excerpt,
        }


@dataclass
class Citation:
    citation_id: str
    claim_id: str
    source_id: str
    locator: str
    source_hash: str = ""
    verification: Verification = Verification.UNVERIFIED
    detail: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "citation_id": self.citation_id, "claim_id": self.claim_id, "source_id": self.source_id,
            "locator": self.locator, "source_hash": self.source_hash,
            "verification": self.verification.value, "detail": self.detail,
        }


@dataclass
class Contradiction:
    contradiction_id: str
    project_id: str
    claim_a: str
    claim_b: str
    kind: ContradictionType
    severity: str = "medium"          # low|medium|high|critical
    resolution: str = "UNRESOLVED"    # UNRESOLVED | RESOLVED | ACCEPTED
    notes: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id, "project_id": self.project_id,
            "claim_a": self.claim_a, "claim_b": self.claim_b, "kind": self.kind.value,
            "severity": self.severity, "resolution": self.resolution, "notes": self.notes,
        }
