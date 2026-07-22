# M19.1 — Retrieval Call-Site Inventory

**Status:** Complete (pre-implementation gate)
**Repository:** SaathiAI / SaathiOS
**Base commit:** `0332469` (M19.0 Unified Knowledge Service)
**Inventory date:** 2026-07-15

This inventory was produced **before** any M19.1 call-site modifications.
Classifications drive the first migration wave; deferred callers stay on legacy paths.

---

## Classification legend

| Tag | Meaning |
|-----|---------|
| `MIGRATE_NOW` | First-wave adoption via Knowledge Service |
| `SHADOW_ONLY` | Valuable; run unified in shadow only this milestone |
| `KEEP_LEGACY` | Correct to stay on current path for now |
| `BLOCKED` | Unsafe or architecture-forbidden to migrate |
| `REMOVE_LATER` | Duplicate/ad-hoc path; future deprecation candidate |
| `NOT_RETRIEVAL` | Not a knowledge-retrieval caller |

---

## Inventory table

| ID | File / symbol | Subsystem | Purpose | Current source | Query format | Result format | Permission | Mission/run | Latency | Failure | Evidence | Risk | KS profile | Compat | Recommendation |
|----|---------------|-----------|---------|----------------|--------------|---------------|------------|-------------|---------|---------|----------|------|------------|--------|----------------|
| C01 | `codebase_memory/service.py` `CodebaseMemoryRuntime.search` | CBM runtime | Hybrid code/doc search | M18.2 `retrieve.search` | free text + filters | dict hits | MCP enable flag | optional root | medium | degrade empty/disabled | primary code/docs | low | CODE_EXPLAIN / FAST_LOOKUP | preserve dict | **MIGRATE_NOW** |
| C02 | `codebase_memory/service.py` `CodebaseMemoryRuntime.symbol` | CBM runtime | Symbol lookup | wraps search | name | dict hits | same | optional | medium | degrade | primary code | low | FAST_LOOKUP | preserve | **MIGRATE_NOW** |
| C03 | `codebase_memory/service.py` `CodebaseMemoryRuntime.document` | CBM runtime | Docs-only search | wraps search | free text | dict hits | same | optional | medium | degrade | canonical docs | low | CODE_EXPLAIN | preserve | **MIGRATE_NOW** |
| C04 | `codebase_memory/service.py` `CodebaseMemoryRuntime.explain` | CBM runtime | Explain ranking | wraps search | free text | dict | same | optional | medium | degrade | primary | low | CODE_EXPLAIN | preserve | **MIGRATE_NOW** |
| C05 | `codebase_memory/service.py` `dispatch_tool` search/symbol/document/explain | Agent tools | Bounded agent entry | Runtime above | tool args | dict | write ban + enable | project_root | medium | denied/empty | primary | low | profile by tool | preserve | **MIGRATE_NOW** |
| C06 | `codebase_memory/cli.py` `main` search/symbol | Operator CLI | Operator lookup | Runtime | argv | dict/print | enable | --root | medium | exit codes | primary | low | FAST_LOOKUP | preserve | **MIGRATE_NOW** (via runtime) |
| C07 | `knowledge/compat.py` `search_compatible` | KS compat | M18.2 shape bridge | legacy or KS | free text | dict hits | KS perms | project_root | medium | degrade | primary | low | CODE_EXPLAIN | is adapter | **MIGRATE_NOW** (extend with modes) |
| C08 | New facade `mission_context_prepare` | Mission prep | Pre-mission context | none yet | bounded intent | ContextPackage | tenant/scope | mission_id | medium | partial/pause | multi | low | MISSION_CONTEXT | new | **MIGRATE_NOW** |
| C09 | New facade `audit_evidence_lookup` | Audit | Milestone/audit evidence | none yet | bounded intent | ContextPackage | tenant | run_id | medium | report missing | primary prefer | low | AUDIT_EVIDENCE | new | **MIGRATE_NOW** |
| C10 | `codebase_memory/retrieve.py` `search` | CBM core | Index retrieval | SQLite hybrid | free text | RetrievalResult | path policy | n/a | medium | degrade | primary | — | — | n/a | **KEEP_LEGACY** (backend of KS adapter) |
| C11 | `knowledge/adapters/*` | KS | Source adapters | various | KnowledgeQuery | KnowledgeResult | permissions | query fields | medium | empty list | typed | — | — | n/a | **KEEP_LEGACY** (not callers) |
| C12 | `knowledge/service.py` `KnowledgeService` | KS | Unified entry | adapters | KnowledgeQuery | KnowledgeResponse | permissions | query | medium | denied/errors | multi | — | all | n/a | **KEEP_LEGACY** (canonical target) |
| C13 | `chat/engine.py` `_retrieve_memory` / `retrieve_for_chat` | Chat | Pre-send LTM | MemoryEngine | chat text | context_block | scope firewall | conversation | **low** | empty | memory | high | MISSION_CONTEXT only if gated | shape lock | **KEEP_LEGACY** (latency + private memory) |
| C14 | `chat/api.py` store search | Chat API | Conversation search | chat store | q | results | auth | n/a | low | empty | conv | med | — | — | **NOT_RETRIEVAL** (UI search) |
| C15 | `agent_runtime/orchestrator.py` `retrieve_for_chat` | Agent runtime | Task memory | MemoryEngine | objective | context | scope | task | med | empty | memory | high | — | — | **KEEP_LEGACY** |
| C16 | `memory/engine/core.py` `retrieve` / `retrieve_for_chat` | Memory | LTM hybrid | semantic+kw | plan | results | scopes | yes | med | empty | memory | — | — | — | **KEEP_LEGACY** (source, not caller) |
| C17 | `memory/api.py` / `memory/cli.py` | Memory API/CLI | Operator memory | engine | plan_query | JSON | auth | optional | med | empty | memory | med | — | — | **SHADOW_ONLY** future; not wave-1 |
| C18 | `ceo/service.py` `index_health` | CEO OS | Health tile | CBM health | n/a | health dict | n/a | n/a | low | degrade | n/a | low | — | — | **NOT_RETRIEVAL** (health only) |
| C19 | `control_center/aggregator.py` `index_health` | Control Center | Health | CBM health | n/a | health | n/a | n/a | low | degrade | n/a | low | — | — | **NOT_RETRIEVAL** |
| C20 | `knowledge_library/store.py` search/list | Knowledge library | Curated library | SQLite | filters | records | n/a | n/a | med | empty | curated | med | — | — | **KEEP_LEGACY** (curation system) |
| C21 | `missions/reference.py` / `website.py` lib import | Missions | Import reference | library importer | URL/repo | store write | n/a | mission | high | fail | external | high | — | — | **BLOCKED** (mutates library; not pure retrieval) |
| C22 | `bff.py` library store | BFF | Surface library | store | n/a | list | n/a | n/a | med | empty | curated | med | — | — | **KEEP_LEGACY** |
| C23 | `agent.py` tool routing `search_project` / `web_search` | Agent tools | Tool dispatch | tool registry | tool args | tool results | gateway | run | varies | tool fail | mixed | high | — | — | **KEEP_LEGACY** / tools not KS |
| C24 | `tools/web_research.py` / `internet_reach.py` | Research tools | Web research | HTTP/browser | topic | text | gateway | optional | high | fail | external | high | — | — | **BLOCKED** (external action surface) |
| C25 | `tools/agent_browser.py` / browser dispatch | Browser | Live browser | browser adapters | intents | evidence | M17.25/26 | run | high | deny | external | **critical** | — | — | **BLOCKED** (live dispatch) |
| C26 | Trading Guardian / trade paths | Trading | Execution/policy | TG stack | n/a | orders | TG | n/a | **critical** | kill switch | n/a | **critical** | — | — | **BLOCKED** |
| C27 | Auth / passkey / payment | Security/payments | Authz & money | respective | n/a | decision | strict | n/a | critical | deny | n/a | critical | — | — | **BLOCKED** |
| C28 | Voice turn path (M12) | Voice OS | Ultra-low-latency | voice stack | utterance | response | voice policy | session | **ultra-low** | degrade | mixed | high | — | — | **KEEP_LEGACY** (latency) |
| C29 | `repair/*` context (if any ad-hoc) | Repair | Repair planning | mixed | prompt | context | harness | mission | med | partial | code | med | CODE_EXPLAIN | needed | **SHADOW_ONLY** until adapters tested |
| C30 | `control_center/search.py` | Control Center | Operator search | local | q | hits | auth | n/a | med | empty | mixed | med | FAST_LOOKUP | needed | **KEEP_LEGACY** (wave-2 candidate) |
| C31 | InsForge provider read paths | Providers | Data-plane read | InsForge client | allowlisted | rows | dual flags | optional | med | deny | operational | med | PROVIDER meta only | n/a | **KEEP_LEGACY** (M18.3/4 boundary) |
| C32 | Ad-hoc FS doc scans outside KS docs adapter | Various | One-off reads | pathlib | path | text | none | n/a | varies | empty | docs | med | — | — | **REMOVE_LATER** when found in product paths |
| C33 | MCP external codebase-memory (if configured) | MCP | External graph MCP | MCP protocol | MCP tools | MCP | MCP gov | n/a | high | disable | external | high | — | — | **BLOCKED** as KS substitute; inventory only |
| C34 | `skills_library/store.py` | Skills | Skill search | store | q | records | n/a | n/a | med | empty | skills | low | — | — | **NOT_RETRIEVAL** (catalog) |
| C35 | `sessions.py` / conversation history | Sessions | History recall | session store | id | messages | user | session | low | empty | chat | low | — | — | **NOT_RETRIEVAL** |

---

## First migration wave (selected)

| Caller ID | Adoption caller key | Profile | Default rollout | Notes |
|-----------|---------------------|---------|-----------------|-------|
| C01–C06 | `codebase_memory_search` (+ symbol/document/explain) | FAST_LOOKUP / CODE_EXPLAIN | `legacy` | Runtime + CLI + dispatch_tool |
| C07 | `compat_search` | CODE_EXPLAIN | `legacy` | Extended mode support |
| C08 | `mission_context_prepare` | MISSION_CONTEXT | `legacy` (opt-in shadow/unified) | New facade only |
| C09 | `audit_evidence_lookup` | AUDIT_EVIDENCE | `legacy` (opt-in shadow/unified) | New facade only |

Global default for M19.1: **`legacy`** (conservative).
Per-caller override via `SAATHI_KS_ROLLOUT` / `SAATHI_KS_ROLLOUT_<CALLER>`.

---

## Explicitly deferred (with reasons)

| Caller | Why deferred |
|--------|--------------|
| Chat `retrieve_for_chat` | Private LTM, latency-sensitive, exact context shape, scope firewall |
| Agent runtime memory | Same as chat; mission coupling needs adapters |
| Voice turn path | Ultra-low latency budget |
| Live browser dispatch | External action, M17.26 governance separate |
| Trading Guardian | Isolation mandate; execution must not depend on KS |
| Payment / auth | Security-critical decisions |
| Web research tools | External network actions |
| InsForge data-plane | M18.3/4 pilot boundaries; provider_meta only via KS |
| Knowledge library mutate/import | Not read-only retrieval |
| Control center search | Needs adapter + auth mapping (wave-2) |
| Repair ad-hoc | SHADOW_ONLY until fixture parity |

---

## Deprecation candidates (not deprecated this milestone)

1. Direct product imports of `saathi.codebase_memory.retrieve.search` outside adapters/runtime (prefer Runtime or KS).
2. Duplicate ranking/context assembly outside `saathi.knowledge` (none production-critical found beyond M18.2 internals).
3. Unbounded docs FS scans outside DocumentationAdapter (REMOVE_LATER if introduced).

**No API marked deprecated in code this milestone.** Documentation only.

---

## Architecture reuse (no new infrastructure)

* M19.0 `KnowledgeService`, router, rank, dedupe, assemble, permissions, adapters
* M18.2 codebase memory index + search
* Existing events bus best-effort emit
* Existing MCP enable flag for CBM
* Existing env-var configuration convention (`SAATHI_*`)
* Existing test fixtures and eval harness patterns

---

## Safety notes for inventory

* Inventory is read-only classification.
* No trading, payment, auth, or production mutation paths selected.
* Retrieved content is data, not authority.
