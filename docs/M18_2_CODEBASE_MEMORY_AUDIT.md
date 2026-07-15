# M18.2 Codebase Memory Audit

**Date:** 2026-07-15
**Branch:** `milestone/m7-security-engine`
**Starting HEAD:** `2223322` (M18.1 / historically labeled M17.25 MCP governance)
**Scope:** Read-only inventory of MCP, indexers, sources, retrieval, persistence, security.

### Milestone renumbering note

| Historical label | Canonical label |
|------------------|-----------------|
| M17.25 Project MCP Governance and Memory Consolidation | **M18.1** Project MCP Governance and Memory Consolidation |

Originally implemented and committed under the temporary label “M17.25 — Project MCP Governance and Memory Consolidation” (commit `2223322`); canonical roadmap designation is now **M18.1**.

**Do not confuse** with browser milestone:

```text
M17.25 — Governed Interactive Browser Sessions, Actions, and Human Handoffs
```

That browser milestone remains **M17.25**.

---

## 5.1 MCP identity and configuration inventory

| MCP identity | Configuration source | Scope | Namespace | Command | Transport | Enabled? | Health | Write capability | Secret exposure risk | Canonical? | Required action |
|--------------|---------------------|-------|-----------|---------|-----------|----------|--------|------------------|----------------------|------------|-----------------|
| `saathi-codebase-memory` | `saathi/mcp_governance` + M18.2 `saathi/codebase_memory` | Product | project-bound | in-process + optional local binary | local/SQLite | yes (disable via env) | `index_health()` | index rebuild only; no repo file writes | low if policy held | **Yes** | Complete M18.2 indexing |
| `codebase-memory` | `~/.grok/config.toml` | User session | tool-defined | `~/.local/bin/codebase-memory-mcp` | stdio | yes | binary presence | index writes to MCP store | medium | Alias | Document only; optional disable |
| `codebase-memory-mcp` | home + Claude | User session | same binary | same | stdio | yes | same | same | medium | **DISABLED_ALIAS** candidate | Manual `enabled=false` |
| `context7` | home grok | Session | n/a | npx context7 | stdio | yes | session | read docs | low | No | Leave session |
| `headroom` | home | Session | n/a | missing binary | stdio | config true | **FAILED** | unknown | noise | broken | User disable |
| `continuum` | none | — | — | NOT INSTALLED | — | no | n/a | n/a | n/a | **BLOCKED_LICENSE** | Do not install |
| `exa` | `config/mcporter.json` | sample | n/a | remote URL | HTTP | unused | none | read | remote | experimental | Ignore |
| `CodeMemoryConnector` | `saathi/infrastructure/.../code_memory.py` | Product driver | — | CLI single-shot | subprocess | if binary | AUTH_REQUIRED/OK | tool exec | local | DELEGATES_TO_CANONICAL | Keep; M18.2 is lexical store |

---

## 5.2 Indexer inventory

| Indexer | File and symbol | Content types | Incremental? | Commit-aware? | Branch-aware? | Ignore-aware? | Secret-safe? | Restart-safe? | Production reachable? | Disposition |
|---------|----------------|---------------|--------------|---------------|---------------|---------------|--------------|---------------|----------------------|-------------|
| **M18.2 IndexStore indexer** | `saathi/codebase_memory/indexer.py` | source, tests, docs, config | **Yes** (hash) | **Yes** | **Yes** | policy+gitignore-like dirs | **Yes** | SQLite checkpoint | via CLI/tools | **CANONICAL** |
| M18.1 FakeMemoryBackend | `mcp_governance/contract.py` | verified lessons only | n/a | no | no | n/a | yes | yes | tests | DELEGATES (lessons) |
| Home codebase-memory-mcp | external binary | graph/code | unknown | unknown | unknown | tool | unknown | unknown | session only | DISABLED_ALIAS / external |
| Continuum | — | — | — | — | — | — | — | — | no | **BLOCKED_LICENSE** |
| Chroma/semantic memory (PIELTS) | `saathi/memory/semantic.py` | student patterns | partial | no | no | n/a | n/a | yes | product (PIELTS) | Separate authority — not codebase MCP |
| M9 memory engine embeddings | `saathi/memory/engine` | business memory | yes | no | no | n/a | policy | yes | product | Separate — reused for optional local embed only |

---

## 5.3 Indexed-source inventory

| Source type | Included? | Reason | Freshness source | Sensitivity | Retention | Exclusion rule | Validation status |
|-------------|-----------|--------|------------------|-------------|-----------|----------------|-------------------|
| Source code | Yes | first-party | git+hash | internal | until delete | secret/path policy | tested |
| Tests | Yes | governance evidence | git+hash | internal | until delete | — | tested |
| Markdown docs | Yes | architecture | git+hash | internal | until delete | — | tested |
| Brain/Business/Style | Yes | canonical docs | git+hash | internal | until delete | force-include names | tested |
| Configuration | Yes (safe) | examples | git+hash | internal | until delete | secret assignment scan | tested |
| Migrations/SQL | Yes | schema | git+hash | internal | until delete | — | policy |
| Lock files | Partial | often noisy | hash | low | optional | size limits | soft |
| Generated / build | **No** | noise | — | — | — | dir names | tested |
| Vendor / node_modules | **No** | leakage/size | — | — | — | dir names | tested |
| Secrets / .env | **No** | security | — | secret | never | path+content | tested |
| Binary / media | **No** | size | — | — | — | suffix | tested |
| Git metadata | Meta only | branch/commit | git | internal | meta table | no blob of .git | tested |
| Nested repos | Separate | isolation | own identity | — | — | skip nested .git | tested |
| External repos | **No** | out of scope | — | — | — | root bound | policy |

---

## 5.4 Retrieval-path inventory

| Tool or API | Caller | Query input | Namespace-bound? | Commit-bound? | Result citations? | Ranking method | Stale-result handling | Production reachable? | Remediation |
|-------------|--------|-------------|------------------|---------------|-------------------|----------------|----------------------|----------------------|-------------|
| `codebase_memory_search` | agents/CLI | text+filters | **Yes** | preferred current | path:lines | hybrid lexical/symbol/local embed | warn + downrank | yes (local) | M18.2 |
| `codebase_memory_symbol` | agents | name | yes | yes | yes | symbol table | same | yes | M18.2 |
| `codebase_memory_document` | agents | text | yes | yes | yes | docs boost | same | yes | M18.2 |
| CLI `python -m saathi.codebase_memory` | human | args | root | yes | yes | same | status codes | yes | M18.2 |
| Home MCP search | session | tool | tool | unknown | varies | external | unknown | session | not product |
| M18.1 lesson search | Fake/backend | lesson | bound | n/a | limited | lesson store | degrade | product lessons | keep separate |

---

## 5.5 Persistence and invalidation inventory

| Store | Location | Schema | Repository-bound? | Branch-bound? | Commit-bound? | File hash stored? | Rename handling | Delete handling | Corruption handling | Cleanup | Remediation |
|-------|----------|--------|-------------------|---------------|---------------|-------------------|-----------------|-----------------|---------------------|---------|-------------|
| **IndexStore SQLite** | `~/.saathi/codebase_memory/<index_key>.sqlite` | m18.2.1 | **Yes** (id+worktree) | recorded | recorded | **Yes** | reindex path (delete old) | mark deleted | integrity_check → CORRUPT | clear/rebuild | CANONICAL |
| M18.1 lesson Fake | memory | n/a | namespace | no | no | no | n/a | archive | n/a | n/a | lessons only |
| External MCP index | vendor path | unknown | tool | ? | ? | ? | ? | ? | ? | ? | not product |

Invalidation triggers: HEAD/branch change → STALE health; file hash change → reindex; schema mismatch → REBUILD_REQUIRED; secret/policy version in meta.

---

## 5.6 Security and privacy inventory

| Risk | Current control | Secret class | Affected paths | Logging exposure | Index exposure | Cross-project exposure | Required remediation |
|------|-----------------|--------------|----------------|------------------|----------------|------------------------|----------------------|
| Secret file indexing | path policy + scan | keys/tokens | .env, pem, keys | reason only | excluded | denied by namespace | **done** |
| Secret in source assignment | high-confidence regex | API keys | any | reason labels | excluded | n/a | **done** |
| Cross-project search | M18.1 namespace bind | n/a | all | event | denied | fail closed | **done** |
| Snippet leakage | redaction on secret-like | mixed | results | redacted | redacted | n/a | **done** |
| Home alias dual index | document + project canonical | n/a | home config | n/a | separate | low | manual alias disable |
| Continuum license | BLOCKED_LICENSE | n/a | n/a | n/a | not installed | n/a | keep blocked |
| Trading secrets | never index exchange paths; TG unengaged | trading | trade modules not special-cased for index of credentials | no | excluded by secret patterns | n/a | verified no TG hooks |

---

## Root causes (pre-M18.2)

1. M18.1 delivered **governance** (identity, permissions, degrade) but not a **first-party index** of the SaathiAI tree.
2. Home `codebase-memory-mcp` was session-level, not commit/freshness-aware product path.
3. No hybrid lexical/symbol retrieval with live-file verification.
4. No deterministic evaluation harness for retrieval quality.

---

## Disposition summary

- **CANONICAL:** `saathi/codebase_memory/*` + M18.1 governance
- **BLOCKED_LICENSE:** Continuum
- **DISABLED_ALIAS:** home `codebase-memory-mcp` (optional human disable)
- **Separate authorities:** run ledger, CEO memory, SecurityStore, TG ledger, M9 business memory
