# SaathiOS MCP Inventory (Authoritative)

**Milestone:** M17.25 — Project MCP Governance and Memory Consolidation
**Date:** 2026-07-15
**Machine inventory module:** `saathi/mcp_governance/inventory.py`
**Cross-reference:** `docs/EXTERNAL_CAPABILITY_STATUS.md`
**Prior note:** `docs/integrations/MCP_PROJECT_INVENTORY.md` (ECP M17.24) remains historical; **this file is authoritative**.

---

## Memory authorities (must stay distinct)

| Memory type | Authoritative system |
|-------------|----------------------|
| Current mission and execution state | SaathiOS mission engine and run ledger |
| Curated project rules | Tracked SaathiOS documentation (`saathi/memory/conventions.md`, SES) |
| Runtime learned conventions | `data/memory/learned_conventions.*` |
| Codebase semantic recall | **Existing codebase-memory MCP** via `saathi-codebase-memory` |
| Security and approval evidence | SecurityStore and Evidence |
| CEO OS business memory | Existing CEO OS memory |
| Trading records | Trading Guardian-specific ledger only |
| External engineering-memory candidate | Continuum — **BLOCKED_LICENSE** |

The codebase-memory MCP **must not** replace the run ledger, mission state, SecurityStore, Evidence, curated memory, Trading Guardian memory, or personal/business memory.

---

## Canonical codebase-memory identity

| Field | Value |
|-------|-------|
| **Canonical name** | `saathi-codebase-memory` |
| **Aliases (home/session)** | `codebase-memory`, `codebase-memory-mcp`, connector id `code_memory` |
| **Backend** | `~/.local/bin/codebase-memory-mcp` (same binary for all aliases) |
| **Product adapter** | `saathi/mcp_governance` + existing `CodeMemoryConnector` |
| **Disable** | `SAATHI_MCP_CODEBASE_MEMORY_DISABLED=1` or `set_enabled(False)` or user MCP `enabled = false` |

### Duplicate cleanup

Home config (`~/.grok/config.toml`, `~/.claude.json`) currently lists both `codebase-memory` and `codebase-memory-mcp` pointing at the **same** binary. That is a **name alias duplicate**, not a conflicting-backend case.

| Case | Action |
|------|--------|
| Same backend, multiple names | Document aliases; prefer `codebase-memory` in user agents; product uses `saathi-codebase-memory` |
| Different backends, unclear ownership | Stop with `REQUIRES_HUMAN_DECISION` (`detect_duplicates`) |

**Recommended human cleanup (optional, not applied by this milestone):** set `enabled = false` on `[mcp_servers.codebase-memory-mcp]` in home config; leave `codebase-memory` enabled. Do not edit unrelated global MCP entries.

---

## Configuration strategy (clients)

| Client | Project config | User-level | Notes |
|--------|----------------|------------|-------|
| **Grok** | `SaathiAI/.grok/config.toml` (policy; empty pilots) | `~/.grok/config.toml` | Home MCPs are session tools ≠ product integration |
| **Claude Code** | Project skills / docs | `~/.claude.json` | Same inventory rules |
| **Codex** | Docs policy | User MCP | No secrets in repo |
| **OpenCode** | Docs policy | User MCP | Same |
| **SaathiOS-native** | `saathi.mcp_governance.CodebaseMemoryService` | N/A | Authoritative product path |

### Policy rules

- **Project config holds:** policy, disable switches, documentation of allowed MCPs; not secrets.
- **User-level holds:** developer session tools (docs lookup, local codebase-memory binary).
- **Environment paths:** use env overrides (`CODEBASE_MEMORY_BIN`, `SAATHI_MCP_*`); never hardcode secrets.
- **Secrets:** reference env **names** only; never commit values.
- **Enable/disable:** project runtime `set_enabled` / env; user `enabled = false`.
- **Staging vs production:** experimental MCP default `enabled=false` until health + focused tests land.
- **Unavailable MCP:** SaathiOS core continues; search returns degraded with `consulted=false`; missions must not claim memory was consulted.

### Forbidden in project MCP config

- Unrestricted shell MCP
- Live trading MCP
- Production DB write MCP
- Home-directory filesystem MCP
- Continuum until licence cleared

---

## Inventory entries (summary)

Full field set is in `saathi/mcp_governance/inventory.py` (`McpEntry`).

| Canonical name | Classification | Product integrated | Notes |
|----------------|----------------|--------------------|-------|
| `saathi-codebase-memory` | authoritative | **Yes** (governance adapter) | Local binary; namespace-isolated |
| `context7` | experimental | No | Home session docs |
| `headroom` | broken | No | Binary missing — disable when convenient |
| `agent-browser` | experimental | No | Not governed browser path |
| `exa` | experimental | No | `config/mcporter.json` sample only |
| `hosted-agent-connectors` | experimental | No | Host OAuth |
| `continuum` | **blocked** | No | `BLOCKED_LICENSE` |

### Continuum licence status

```
pouyahasanamreji/continuum = BLOCKED_LICENSE
```

- Public repository exists
- Operational documentation may exist
- No clear root licence found
- No clone, packaging, embedding, or redistribution authorized
- Future pilot requires published licence or written permission
- **Not installed** in this milestone

---

## Namespace model

- Deterministic ids: `saathiai`, `ieltsalert`, `cafeteria`, `travel-client`, or `proj_<hash>`
- Bound namespace on `CodebaseMemoryService` — cross-project search denied
- Path traversal (`..`, absolute escapes) rejected
- Symlink/path resolve must stay under project root

## Permission model

| Class | Ops | Control |
|-------|-----|---------|
| Read-only, low risk | `health`, `search`, `get`, `list_namespaces` | No write approval |
| Write, approval-controlled | `write_verified_lesson`, `delete_or_archive_lesson`, rebuild/config | Verified-only; ToolIntent family `mcp`; Evidence on success |

Speculative model output is **never** stored as authoritative knowledge.

## Health and degradation

Fields: configured, enabled, reachable, transport, latency, backend identity, namespace available, read test, write test (disabled by default), last error category, last successful check, degraded reason.

On failure: degraded result, `consulted=false`, Control Center `mcp_health` cell, CEO brief only when degraded/unavailable, short circuit cooldown (no endless retry).

## Timeout and retry

| Parameter | Default | Cap |
|-----------|---------|-----|
| Connect timeout | 5s | 30s |
| Request timeout | 30s | 120s |
| Max retries (reads) | 2 | 3 |
| Write retries | **0** (no blind retry) | — |

Retryable categories (reads only): `timeout`, `connection`, `temporary`, `unavailable`.

## Secret and privacy controls

Redact API keys, tokens, passwords, cookies, authorization headers, exchange credentials, patient-like data. Reject secret-like lesson content. Events use bounded safe summaries — never full memory bodies.

## Evidence and observability

Events: `mcp_health_checked`, `mcp_unavailable`, `mcp_search_succeeded`, `mcp_search_failed`, `mcp_write_requested`, `mcp_write_denied`, `mcp_write_succeeded`, `mcp_secret_rejected`, `mcp_namespace_violation`.

SecurityStore audits denials/failures. Evidence rows for governed writes (metadata only).

---

## Disable methods (quick)

```bash
export SAATHI_MCP_CODEBASE_MEMORY_DISABLED=1
# or in Python:
from saathi.mcp_governance import set_enabled
set_enabled(False)
```

---

## Remaining MCP gaps

- Home `headroom` still enabled but broken
- Optional human dedupe of home alias `codebase-memory-mcp`
- Continuum pilot still licence-blocked
- CodeFlow / other ECP pilots not yet configured
- Live binary end-to-end search not required for governance milestone (fake harness + connector tests cover paths)
