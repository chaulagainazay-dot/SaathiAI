"""M18.2 — Governed local-first repository indexing and hybrid retrieval.

Complements M18.1 (``saathi.mcp_governance``): governance + namespace remain
authoritative; this package makes codebase memory operationally useful.

Local-only: SQLite + lexical/symbol search + optional local deterministic
embeddings. No paid APIs, no Continuum, no Trading Guardian engagement.
"""
from __future__ import annotations

from saathi.codebase_memory.health import IndexHealth, index_health
from saathi.codebase_memory.identity import RepoIdentity, resolve_identity
from saathi.codebase_memory.indexer import IndexSummary, index_repository, rebuild_index
from saathi.codebase_memory.retrieve import RetrievalResult, search as memory_search
from saathi.codebase_memory.service import CodebaseMemoryRuntime, default_runtime

SCHEMA_VERSION = "m18.2.1"
PARSER_VERSION = "m18.2.p1"
NAMESPACE_VERSION = "m18.1+m18.2"

__all__ = [
    "SCHEMA_VERSION",
    "PARSER_VERSION",
    "NAMESPACE_VERSION",
    "CodebaseMemoryRuntime",
    "IndexHealth",
    "IndexSummary",
    "RepoIdentity",
    "RetrievalResult",
    "default_runtime",
    "index_health",
    "index_repository",
    "memory_search",
    "rebuild_index",
    "resolve_identity",
]
