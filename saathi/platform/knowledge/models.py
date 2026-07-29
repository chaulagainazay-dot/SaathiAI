"""Knowledge & Grounding Runtime contracts (M87–M94).

Platform-owned. ConversationService remains the sole conversational model path.
This package never executes tools, never listens publicly, and never auto-downloads models.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import re
import time
from typing import Any

# ── Resource bounds (M2 / 8 GB) ──────────────────────────────────────────────
MAX_FILE_BYTES = 512_000
MAX_CHUNKS_PER_DOCUMENT = 48
MAX_TOTAL_CHUNKS = 8_000
MAX_CHUNK_CHARS = 1_200
CHUNK_OVERLAP_CHARS = 80
MAX_INGEST_CONCURRENCY = 1
MAX_RETRIEVAL_TOP_K = 12
DEFAULT_TOP_K = 6
MAX_CONTEXT_CHARS = 4_500
MAX_QUERY_CHARS = 500
QUERY_TIMEOUT_SEC = 3.0
REINDEX_TIMEOUT_SEC = 120.0
MAX_CONCURRENT_SEARCHES = 4
MAX_CONCURRENT_INGESTIONS = 1
MAX_INDEX_STORAGE_BYTES = 64 * 1024 * 1024
MAX_RETRIES = 1
INGESTION_BATCH = 40

ALLOWED_SUFFIXES = frozenset({".md", ".txt", ".json", ".rst", ".yml", ".yaml"})
DENIED_NAME_PARTS = frozenset({
    ".env", "credentials", "secret", "private_key", "id_rsa", ".pem",
    "cookie", "token.json", "auth.json",
})
DENIED_DIR_PARTS = frozenset({
    ".git", "node_modules", ".venv", "__pycache__", "dist", "build",
    ".next", "caches", "cache", "model_weights", "weights", "gguf",
    "design-spec",
})

INDEX_VERSION = "m87.1.0"


class SourceAuthority(str, Enum):
    AUTHORITATIVE_RUNTIME = "AUTHORITATIVE_RUNTIME"
    AUTHORITATIVE_EVIDENCE = "AUTHORITATIVE_EVIDENCE"
    AUTHORITATIVE_PLATFORM_RECORD = "AUTHORITATIVE_PLATFORM_RECORD"
    AUTHORITATIVE_DOCUMENTATION = "AUTHORITATIVE_DOCUMENTATION"
    DERIVED_SUMMARY = "DERIVED_SUMMARY"
    USER_PROVIDED_CONTEXT = "USER_PROVIDED_CONTEXT"
    MODEL_PRIOR = "MODEL_PRIOR"
    UNVERIFIED = "UNVERIFIED"


AUTHORITY_RANK: dict[SourceAuthority, int] = {
    SourceAuthority.AUTHORITATIVE_RUNTIME: 100,
    SourceAuthority.AUTHORITATIVE_EVIDENCE: 90,
    SourceAuthority.AUTHORITATIVE_PLATFORM_RECORD: 80,
    SourceAuthority.AUTHORITATIVE_DOCUMENTATION: 60,
    SourceAuthority.DERIVED_SUMMARY: 40,
    SourceAuthority.USER_PROVIDED_CONTEXT: 30,
    SourceAuthority.MODEL_PRIOR: 10,
    SourceAuthority.UNVERIFIED: 0,
}


class SourceType(str, Enum):
    AUTONOMOUS_RUNTIME = "autonomous_runtime"
    REPOSITORY_DOCUMENTATION = "repository_documentation"
    EVIDENCE = "evidence"
    PLATFORM_STATE = "platform_state"
    APPLICATION_DOMAIN = "application_domain"
    CAPABILITY = "capability"
    ROADMAP = "roadmap"
    CERTIFICATION = "certification"


class Sensitivity(str, Enum):
    PUBLIC_INTERNAL = "public_internal"
    TENANT_INTERNAL = "tenant_internal"
    RESTRICTED = "restricted"
    SECRET = "secret"  # never indexed


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    CONFLICTING = "conflicting"


class ClaimKind(str, Enum):
    GROUNDED_FACT = "grounded_fact"
    INFERENCE = "inference"
    RECOMMENDATION = "recommendation"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    UNAVAILABLE_EVIDENCE = "unavailable_evidence"


@dataclass
class KnowledgeSourceSpec:
    """Allowlisted source descriptor (not raw filesystem trust)."""

    source_id: str
    title: str
    source_type: SourceType
    authority: SourceAuthority
    relative_path: str
    sensitivity: Sensitivity = Sensitivity.PUBLIC_INTERNAL
    optional: bool = False
    max_bytes: int = MAX_FILE_BYTES

    def to_public(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "source_type": self.source_type.value,
            "authority": self.authority.value,
            "relative_path": self.relative_path,
            "sensitivity": self.sensitivity.value,
            "optional": self.optional,
        }


@dataclass
class KnowledgeDocument:
    document_id: str
    source_id: str
    title: str
    source_type: str
    authority: str
    relative_path: str
    content_hash: str
    created_at: float = 0.0
    modified_at: float = 0.0
    indexed_at: float = field(default_factory=time.time)
    milestone: str = ""
    commit_sha: str = ""
    tenant_id: str = "platform"
    workspace_scope: str = "*"  # * = all workspaces in tenant after auth
    sensitivity: str = Sensitivity.PUBLIC_INTERNAL.value
    chunk_count: int = 0
    byte_size: int = 0
    tombstoned: bool = False
    freshness: str = FreshnessStatus.UNKNOWN.value
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_id": self.source_id,
            "title": self.title,
            "source_type": self.source_type,
            "authority": self.authority,
            "relative_path": self.relative_path,
            "content_hash": self.content_hash,
            "indexed_at": self.indexed_at,
            "milestone": self.milestone,
            "commit_sha": (self.commit_sha or "")[:12],
            "sensitivity": self.sensitivity,
            "chunk_count": self.chunk_count,
            "freshness": self.freshness,
            "tombstoned": self.tombstoned,
        }


@dataclass
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    source_id: str
    ordinal: int
    text: str
    content_hash: str
    authority: str
    source_type: str
    relative_path: str
    title: str
    start_char: int = 0
    end_char: int = 0
    tenant_id: str = "platform"
    workspace_scope: str = "*"
    sensitivity: str = Sensitivity.PUBLIC_INTERNAL.value
    milestone: str = ""
    commit_sha: str = ""
    indexed_at: float = field(default_factory=time.time)
    freshness: str = FreshnessStatus.UNKNOWN.value
    tombstoned: bool = False

    def to_public(self, *, include_text: bool = True) -> dict[str, Any]:
        out = {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "source_id": self.source_id,
            "ordinal": self.ordinal,
            "authority": self.authority,
            "source_type": self.source_type,
            "title": self.title,
            "relative_path": self.relative_path,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "freshness": self.freshness,
            "milestone": self.milestone,
            "commit_sha": (self.commit_sha or "")[:12],
            "sensitivity": self.sensitivity,
        }
        if include_text:
            out["text"] = self.text[:MAX_CHUNK_CHARS]
            out["text_chars"] = len(self.text or "")
        return out


@dataclass
class RetrievedChunk:
    chunk: KnowledgeChunk
    score: float
    rank_reasons: list[str] = field(default_factory=list)
    adjacent_expanded: bool = False

    def to_public(self) -> dict[str, Any]:
        base = self.chunk.to_public(include_text=True)
        base["score"] = round(self.score, 4)
        base["rank_reasons"] = list(self.rank_reasons)
        base["adjacent_expanded"] = self.adjacent_expanded
        return base


@dataclass
class Citation:
    source_id: str
    document_id: str
    chunk_id: str
    title: str
    source_type: str
    authority: str
    freshness: str
    relative_path: str
    milestone: str = ""
    commit_sha: str = ""
    evidence_id: str = ""
    location: str = ""
    claim_kind: str = ClaimKind.GROUNDED_FACT.value

    def to_public(self) -> dict[str, Any]:
        # Never expose absolute filesystem paths
        return {
            "source_id": self.source_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "source_type": self.source_type,
            "authority": self.authority,
            "freshness": self.freshness,
            "path": self.relative_path,  # repo-relative only
            "milestone": self.milestone,
            "commit_sha": (self.commit_sha or "")[:12],
            "evidence_id": self.evidence_id,
            "location": self.location,
            "claim_kind": self.claim_kind,
        }


@dataclass
class GroundingContext:
    query: str
    chunks: list[RetrievedChunk]
    citations: list[Citation]
    prompt_block: str
    claim_kind: str
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    stale_warnings: list[str] = field(default_factory=list)
    no_evidence: bool = False
    truncated: bool = False
    retrieval_ms: float = 0.0
    context_chars: int = 0
    injection_flags: list[str] = field(default_factory=list)
    grounded: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "grounded": self.grounded and not self.no_evidence,
            "claim_kind": self.claim_kind,
            "citations": [c.to_public() for c in self.citations],
            "conflicts": list(self.conflicts),
            "stale_warnings": list(self.stale_warnings),
            "no_evidence": self.no_evidence,
            "truncated": self.truncated,
            "retrieval_ms": round(self.retrieval_ms, 2),
            "context_chars": self.context_chars,
            "chunk_count": len(self.chunks),
            "injection_flags": list(self.injection_flags),
        }

    def safe_telemetry(self) -> dict[str, Any]:
        return {
            "grounded": self.grounded,
            "claim_kind": self.claim_kind,
            "citation_count": len(self.citations),
            "conflict_count": len(self.conflicts),
            "stale_count": len(self.stale_warnings),
            "no_evidence": self.no_evidence,
            "retrieval_ms": round(self.retrieval_ms, 2),
            "context_chars": self.context_chars,
            "injection_flag_count": len(self.injection_flags),
        }


@dataclass
class KnowledgeHealth:
    sources_discovered: int = 0
    sources_indexed: int = 0
    chunks_indexed: int = 0
    stale_sources: int = 0
    failed_sources: int = 0
    last_successful_ingestion: float = 0.0
    index_version: str = INDEX_VERSION
    repository_sha: str = ""
    mission_association: str = ""
    lexical_available: bool = True
    semantic_available: bool = False
    retrieval_latency_ms: float = 0.0
    indexing_latency_ms: float = 0.0
    storage_bytes: int = 0
    ready: bool = False
    errors: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "service": "knowledge_grounding",
            "ready": self.ready,
            "sources_discovered": self.sources_discovered,
            "sources_indexed": self.sources_indexed,
            "chunks_indexed": self.chunks_indexed,
            "stale_sources": self.stale_sources,
            "failed_sources": self.failed_sources,
            "last_successful_ingestion": self.last_successful_ingestion,
            "index_version": self.index_version,
            "repository_sha": (self.repository_sha or "")[:12],
            "mission_association": self.mission_association,
            "lexical_available": self.lexical_available,
            "semantic_available": self.semantic_available,
            "retrieval_mode": "lexical",
            "retrieval_latency_ms": round(self.retrieval_latency_ms, 2),
            "indexing_latency_ms": round(self.indexing_latency_ms, 2),
            "storage_bytes": self.storage_bytes,
            "bounds": {
                "max_file_bytes": MAX_FILE_BYTES,
                "max_chunks_per_document": MAX_CHUNKS_PER_DOCUMENT,
                "max_total_chunks": MAX_TOTAL_CHUNKS,
                "max_top_k": MAX_RETRIEVAL_TOP_K,
                "max_context_chars": MAX_CONTEXT_CHARS,
            },
            "errors": list(self.errors)[:10],
            "production_authorized": False,
            "auto_model_download": False,
        }


def stable_id(*parts: str, prefix: str = "kd_") -> str:
    raw = "|".join(str(p or "") for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}{digest}"


def content_hash(text: str | bytes) -> str:
    if isinstance(text, bytes):
        data = text
    else:
        data = (text or "").encode("utf-8", errors="replace")
    return hashlib.sha256(data).hexdigest()


_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}", re.I)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def authority_rank(authority: str | SourceAuthority) -> int:
    try:
        a = SourceAuthority(authority) if not isinstance(authority, SourceAuthority) else authority
    except ValueError:
        return 0
    return AUTHORITY_RANK.get(a, 0)
