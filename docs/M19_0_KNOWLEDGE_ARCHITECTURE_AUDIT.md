# M19.0 Architecture Audit — Retrieval Inventory (pre-implementation)

**Date:** 2026-07-15
**Starting HEAD:** `da2f8d0`
**Prior:** M18.2 codebase memory, M18.3/M18.4 InsForge (not expanded here)

## Existing retrieval systems found

| System | Path | Role | Gap for multi-repo agents |
|--------|------|------|---------------------------|
| Codebase memory hybrid search | `saathi/codebase_memory/retrieve.py` | Lexical/symbol/local embed per repo index | Single bound namespace; not multi-source |
| Codebase memory runtime | `saathi/codebase_memory/service.py` | Index + search facade | No cross-source routing |
| M9 memory engine | `saathi/memory/engine/` | Long-term personal/business memory | Separate authority; not repo code |
| Platform memory | `saathi/memory/platform.py` | Episode/Knowledge | Product memory, not code search |
| MCP governance inventory | `saathi/mcp_governance/inventory.py` | MCP metadata | Not a search API |
| InsForge provider | `saathi/providers/insforge/` | Backend data plane | Metadata/logs only; not knowledge |
| SES-000E / EXTERNAL_CAPABILITY | docs | Source registration | No runtime router |

## Duplication / risk

* Multiple “search” entry points without a single plan/audit surface.
* Agents can call codebase_memory or memory engine independently → inconsistent provenance.
* No multi-repository quota or trust balancing.

## Decision

Add **`saathi/knowledge/`** as coordination layer only:

* Query contract + profiles + router + adapters + rank/dedupe/context
* Adapters wrap **existing** M18.2 search and registered doc roots
* No new vector DB, no InsForge expansion, no memory replacement

## Explicit non-goals (M19.0)

InsForge write expansion · live web search · auto-clone repos · KG rewrite · delete legacy APIs
