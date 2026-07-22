"""Index health model for Control Center / CLI / MCP negotiation."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from saathi.codebase_memory.identity import INDEX_SCHEMA_VERSION, resolve_identity
from saathi.codebase_memory.store import IndexStore, index_db_path
from saathi.mcp_governance.policy import is_enabled
from saathi.mcp_governance.inventory import CANONICAL_CODEBASE_MEMORY_ID, continuum_status


@dataclass
class IndexHealth:
    status: str = "UNKNOWN"
    # UNKNOWN|EMPTY|BUILDING|HEALTHY|DEGRADED|STALE|CORRUPT|DISABLED|UNAVAILABLE|REBUILD_REQUIRED
    mcp_id: str = CANONICAL_CODEBASE_MEMORY_ID
    enabled: bool = True
    repository_id: str = ""
    namespace: str = ""
    branch: str = ""
    commit_sha: str = ""
    indexed_commit: str = ""
    indexed_branch: str = ""
    schema_version: str = ""
    schema_ok: bool = False
    integrity_ok: bool = False
    files: int = 0
    chunks: int = 0
    symbols: int = 0
    exclusions: int = 0
    stale: bool = False
    semantic_available: bool = False
    lexical_available: bool = True
    last_successful_index: float = 0.0
    degraded_reason: str = ""
    continuum_status: str = "BLOCKED_LICENSE"
    db_path: str = ""
    dirty_worktree: bool = False
    tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SUPPORTED_TOOLS = [
    "codebase_memory_health",
    "codebase_memory_index",
    "codebase_memory_refresh",
    "codebase_memory_search",
    "codebase_memory_symbol",
    "codebase_memory_document",
    "codebase_memory_explain",
    "codebase_memory_rebuild",
]


def index_health(
    project_root: str | Path | None = None,
    *,
    base_dir: Path | None = None,
    store: IndexStore | None = None,
) -> IndexHealth:
    h = IndexHealth(
        continuum_status=continuum_status()["status"],
        tools=list(SUPPORTED_TOOLS),
    )
    h.enabled = is_enabled(CANONICAL_CODEBASE_MEMORY_ID)
    if not h.enabled:
        h.status = "DISABLED"
        h.degraded_reason = "SAATHI_MCP_CODEBASE_MEMORY_DISABLED or set_enabled(False)"
        return h

    try:
        ident = resolve_identity(project_root)
    except Exception as e:
        h.status = "UNAVAILABLE"
        h.degraded_reason = str(e)[:200]
        return h

    h.repository_id = ident.repository_id
    h.namespace = ident.project_namespace
    h.branch = ident.branch
    h.commit_sha = ident.commit_sha
    h.dirty_worktree = ident.dirty_worktree

    owns = store is None
    st = None
    try:
        st = store or IndexStore(index_db_path(ident, base=base_dir))
        h.db_path = str(st.path)
        h.integrity_ok = st.integrity_ok()
        if not h.integrity_ok:
            h.status = "CORRUPT"
            h.degraded_reason = "sqlite_integrity_failed"
            return h

        h.schema_version = st.get_meta("index_schema_version") or ""
        h.schema_ok = (not h.schema_version) or h.schema_version == INDEX_SCHEMA_VERSION
        if h.schema_version and h.schema_version != INDEX_SCHEMA_VERSION:
            h.status = "REBUILD_REQUIRED"
            h.degraded_reason = "schema_mismatch"
            h.schema_ok = False
            return h

        counts = st.counts()
        h.files = counts["files"]
        h.chunks = counts["chunks"]
        h.symbols = counts["symbols"]
        h.exclusions = counts["exclusions"]
        h.indexed_commit = st.get_meta("last_index_commit")
        h.indexed_branch = st.get_meta("last_index_branch")
        try:
            h.last_successful_index = float(st.get_meta("last_successful_index") or 0)
        except ValueError:
            h.last_successful_index = 0.0

        try:
            from saathi.memory.engine.embeddings import LocalDeterministicEmbedder
            h.semantic_available = LocalDeterministicEmbedder().available()
        except Exception:
            h.semantic_available = False

        if h.chunks == 0:
            h.status = "EMPTY"
            h.degraded_reason = "no_chunks_indexed"
            return h

        if h.indexed_commit and h.indexed_commit != ident.commit_sha:
            h.stale = True
            h.status = "STALE"
            h.degraded_reason = "head_changed_since_index"
            return h
        if h.indexed_branch and h.indexed_branch != ident.branch:
            h.stale = True
            h.status = "STALE"
            h.degraded_reason = "branch_changed_since_index"
            return h

        h.status = "HEALTHY"
        return h
    except Exception as e:
        h.status = "UNAVAILABLE"
        h.degraded_reason = str(e)[:200]
        return h
    finally:
        if owns and st is not None:
            try:
                st.close()
            except Exception:
                pass


def capability_negotiation(project_root: str | Path | None = None) -> dict[str, Any]:
    h = index_health(project_root)
    d = h.to_dict()
    d["version"] = "m18.2"
    d["read_write"] = "read_index_only"
    d["write_repository_files"] = False
    d["supported_tools"] = SUPPORTED_TOOLS
    return d
