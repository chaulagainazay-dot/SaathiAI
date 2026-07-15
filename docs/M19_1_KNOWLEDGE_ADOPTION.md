# M19.1 — Knowledge Service Adoption, Shadow Evaluation, Legacy Migration

**Status:** Pilot (not production-ready)
**Base:** M19.0 `0332469` Unified Knowledge Service
**Verdict target:** `KNOWLEDGE SERVICE ADOPTION PILOT READY`

---

## Purpose

Migrate a **bounded first wave** of high-value, low-risk callers onto the
canonical `KnowledgeService` without building parallel retrieval infrastructure.

---

## First-wave callers

| Caller key | Entry | Profile | Default mode |
|------------|-------|---------|--------------|
| `codebase_memory_search` | `CodebaseMemoryRuntime.search` / `dispatch_tool` | CODE_EXPLAIN | `legacy` |
| `codebase_memory_symbol` | `.symbol` | FAST_LOOKUP | `legacy` |
| `codebase_memory_document` | `.document` | CODE_EXPLAIN | `legacy` |
| `codebase_memory_explain` | `.explain` | CODE_EXPLAIN | `legacy` |
| `compat_search` | `search_compatible` | CODE_EXPLAIN | `legacy` |
| `mission_context_prepare` | `mission_context_prepare()` | MISSION_CONTEXT | `legacy` |
| `audit_evidence_lookup` | `audit_evidence_lookup()` | AUDIT_EVIDENCE | `legacy` |

Global default remains **`legacy`** (M18.2 behaviour unchanged until opted in).

---

## Rollout modes

| Mode | Behaviour |
|------|-----------|
| `legacy` | Legacy path only |
| `shadow` | Legacy authoritative; KS runs for comparison only |
| `unified_with_fallback` | KS first; soft-error fallback to legacy |
| `unified_only` | KS only; no legacy fallback |

### Configuration

```bash
# Global (optional)
export SAATHI_KS_ROLLOUT=legacy          # default if unset

# Per-caller
export SAATHI_KS_ROLLOUT_CODEBASE_MEMORY_SEARCH=shadow
export SAATHI_KS_ROLLOUT_MISSION_CONTEXT_PREPARE=unified_with_fallback
```

Runtime (tests / operator):

```python
from saathi.knowledge.rollout import set_caller_mode, set_global_mode, RolloutMode
set_global_mode(RolloutMode.SHADOW)
set_caller_mode("codebase_memory_search", RolloutMode.UNIFIED_WITH_FALLBACK)
```

---

## Canonical flow

```text
caller
→ deterministic query builder (bounded intent)
→ resolve rollout mode
→ KnowledgeService.retrieve() when unified/shadow
→ validate / map via compatibility adapter
→ consume structured context (untrusted boundaries)
→ metrics + events (no sensitive bodies)
```

Callers **must not** invoke retrieval adapters directly.

---

## Fallback policy

**Allowed soft categories:** `source_unavailable`, `timeout`, `index_unavailable`,
`unsupported_adapter`, `partial_below_threshold`, `empty_results`, `exception`, …

**Never fallback:** `permission_denied`, `secret_path_denial`, `tenant_isolation`,
`invalid_query`, `security_policy_denial`, …

Security denials are final.

---

## Shadow evaluation

Deterministic metrics only (no ungoverned LLM scoring):

* path Jaccard / top-K overlap
* legacy-only / unified-only paths
* latency both sides
* primary-evidence ratio, duplicate rate, truncation
* permission-denied correctness

---

## Prompt-injection handling

Retrieved text is wrapped:

```text
<<<RETRIEVED_EVIDENCE untrusted=true authority=data_only …>>>
…
<<<END_RETRIEVED_EVIDENCE>>>
```

Cannot authorize tools, trades, payments, kill-switch changes, or deploys.

---

## Disable / rollback (M19.1 only)

1. Unset all `SAATHI_KS_ROLLOUT*` env vars **or** set `SAATHI_KS_ROLLOUT=legacy`.
2. Call `reset_rollout_state()` if runtime overrides were applied.
3. M19.0 KnowledgeService and M18.2 indexes remain intact.
4. Optional: `git revert <m19.1-commit>` — **do not** revert M19.0 to disable adoption.

---

## Trading Guardian

Outside this wave. Engineering/audit may retrieve TG **code/docs** only via
authorized profiles. Execution, approvals, credentials, kill switches: independent.

---

## Package map

| Module | Role |
|--------|------|
| `saathi/knowledge/rollout.py` | Modes + config |
| `saathi/knowledge/adoption.py` | Gateway, builders, fallback, metrics, facades |
| `saathi/knowledge/shadow.py` | Comparison model |
| `saathi/knowledge/safety.py` | Untrusted boundaries |
| `saathi/knowledge/compat.py` | Legacy shape adapter |
| `saathi/codebase_memory/service.py` | First-wave wiring |

---

## Related docs

* `docs/M19_1_RETRIEVAL_CALLSITE_INVENTORY.md`
* `docs/M19_1_VALIDATION.md`
* `docs/M19_0_UNIFIED_KNOWLEDGE_SERVICE.md`
