# M19.2 — Call-Site Gap Analysis (pre-implementation)

**Status:** Complete
**Base HEAD:** `1705461` (post M19.1)
**Date:** 2026-07-15

This analysis was produced before second-wave caller modifications.

---

## What M19.0/M19.1 already provide

| Component | Role |
|-----------|------|
| `KnowledgeService` | Canonical retrieve |
| `adoption.adopt_retrieve` | Rollout modes + fallback + shadow |
| `shadow.compare_retrieval` | Deterministic path overlap metrics |
| `eval_set.EVAL_CASES` | Small UK eval set |
| First-wave callers | CBM search/symbol/document/explain, compat, mission_context, audit_evidence |
| Rollout default | `legacy` |
| Safety wrappers | Untrusted evidence boundaries |
| TG isolation tests | Knowledge package free of trade paths |

---

## Gaps for M19.2

1. **No campaign-scale dual-path evaluation** — only unit-level shadow compare.
2. **Missing quality metrics** — top-1 / top-3 / top-5 / latency p50-p95 aggregates.
3. **Control Center search** still pure federated connector/approval search; no repository knowledge facet.
4. **Repair planning** has no governed repository-context facade.
5. **Deferred callers** from M19.1 remain deferred (correctly).

---

## Second-wave classification (M19.2)

| ID | File / symbol | Subsystem | Current path | Shape | Latency | Permission | Fail | Profile | Shadow? | Fallback? | Risk | Recommendation |
|----|---------------|-----------|--------------|-------|---------|------------|------|---------|---------|-----------|------|----------------|
| C30 | `control_center/search.py` `federated_search` | Control Center | connectors/approvals/accounts only | SearchResult list | med | owner scope | empty | FAST_LOOKUP (repo facet) | yes | soft only | med | **SHADOW_IN_M19_2** (explicit `types=repository` only) |
| C29 | repair planning context (new facade) | Repair | none | ContextPackage | med | system | empty | CODE_EXPLAIN | yes | soft only | med | **SHADOW_IN_M19_2** / opt-in unified |
| C13 | chat LTM | Chat | MemoryEngine | context_block | low | firewall | empty | — | no | — | high | **DEFER_SAFETY_CRITICAL** |
| C15 | agent runtime memory | Agent | MemoryEngine | context | med | scope | empty | — | no | — | high | **DEFER_SAFETY_CRITICAL** |
| C26 | Trading Guardian | Trading | TG stack | orders | critical | TG | kill | — | no | — | critical | **DEFER_SAFETY_CRITICAL** |
| C27 | Auth / payment | Security | respective | decision | critical | strict | deny | — | no | — | critical | **DEFER_SAFETY_CRITICAL** |
| C28 | Voice turn | Voice | voice stack | response | ultra-low | voice | degrade | — | no | — | high | **KEEP_LEGACY** |
| C31 | InsForge reads | Providers | InsForge | rows | med | dual flag | deny | — | no | — | med | **KEEP_LEGACY** |
| C10–C12 | retrieve/adapters/KS | Core | internal | typed | — | — | — | — | — | — | — | **NOT_RETRIEVAL** (infrastructure) |
| C14 | chat API store search | Chat API | store | results | low | auth | empty | — | no | — | med | **NOT_RETRIEVAL** |
| C01–C09 | first wave | various | adoption | dict | med | MCP/scope | degrade | various | done | done | low | **KEEP** first-wave (M19.1) |

---

## Selected second-wave callers (≤2)

1. **`control_center_repository_search`** (`CALLER_CONTROL_CENTER_REPO`)
   - Explicit `entity_types=["repository"]` only — default federated search unchanged
   - Default rollout: `legacy` (empty facet)
   - Shadow/unified via existing adoption gateway
   - Read-only operator projection; secrets excluded

2. **`repair_context_prepare`** (`CALLER_REPAIR_CONTEXT`)
   - Facade only — does **not** auto-patch or invoke tools
   - Default rollout: `legacy` empty package
   - Buckets: implementation / tests / architecture docs / limitations
   - Retrieved text is untrusted evidence

---

## Explicitly not selected

- Chat LTM, voice, TG, auth/payment, browser dispatch, InsForge expansion
- Broad repository-wide replacement of retrieve callers
- New retrieval infrastructure

---

## Architecture constraints confirmed

- Reuse M19.0/M19.1 only
- No InsForge Docker / credentials
- No Trading Guardian behaviour changes
- 8 GB Mac: sequential campaign, no large model downloads
