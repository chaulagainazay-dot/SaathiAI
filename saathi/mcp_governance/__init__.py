"""M17.25 — Project MCP governance and memory consolidation.

Authoritative SaathiOS layer for MCP inventory, namespace isolation,
provider-neutral codebase semantic recall, health/degradation, and
write governance. Does **not** replace the run ledger, mission engine,
SecurityStore, Evidence, curated memory, CEO OS memory, or Trading Guardian.

Canonical codebase-memory identity: ``saathi-codebase-memory``.
Continuum remains ``BLOCKED_LICENSE`` — not installed by this package.
"""
from __future__ import annotations

from saathi.mcp_governance.contract import (
    CodebaseMemoryService,
    LessonWriteRequest,
    MemoryCapability,
    MemoryHit,
    MemoryOpResult,
    default_memory_service,
    reset_memory_service,
)
from saathi.mcp_governance.health import McpHealth, health_snapshot, ceo_mcp_summary
from saathi.mcp_governance.inventory import (
    CANONICAL_CODEBASE_MEMORY_ID,
    CODEBASE_MEMORY_ALIASES,
    McpEntry,
    continuum_status,
    detect_duplicates,
    inventory_entries,
    inventory_complete,
    load_inventory,
)
from saathi.mcp_governance.namespace import (
    NamespaceError,
    assert_namespace_bound,
    normalize_project_root,
    project_namespace,
)
from saathi.mcp_governance.policy import (
    is_enabled,
    set_enabled,
    timeout_policy,
    retry_policy,
)

__all__ = [
    "CANONICAL_CODEBASE_MEMORY_ID",
    "CODEBASE_MEMORY_ALIASES",
    "CodebaseMemoryService",
    "LessonWriteRequest",
    "McpEntry",
    "McpHealth",
    "MemoryCapability",
    "MemoryHit",
    "MemoryOpResult",
    "NamespaceError",
    "assert_namespace_bound",
    "ceo_mcp_summary",
    "continuum_status",
    "default_memory_service",
    "detect_duplicates",
    "health_snapshot",
    "inventory_complete",
    "inventory_entries",
    "is_enabled",
    "load_inventory",
    "normalize_project_root",
    "project_namespace",
    "reset_memory_service",
    "retry_policy",
    "set_enabled",
    "timeout_policy",
]
