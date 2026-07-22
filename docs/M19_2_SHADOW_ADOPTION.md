# M19.2 — Shadow Evaluation Campaign and Second-Wave Knowledge Service Adoption

**Status:** Pilot (not production-ready)
**Verdict target:** `M19.2 SHADOW ADOPTION READY`
**Base:** M19.1 Knowledge Service adoption

---

## Purpose

1. Run a deterministic shadow evaluation campaign (legacy baseline vs unified).
2. Record quality and latency metrics (no LLM scoring).
3. Adopt **at most two** second-wave callers with legacy rollback.
4. Keep chat LTM, voice, Trading Guardian, payments, and InsForge out of scope.

---

## Shadow campaign

Module: `saathi/knowledge/campaign.py`
Fixtures: `CAMPAIGN_CASES` in `saathi/knowledge/eval_set.py`

### Modes

| Mode | Role in campaign |
|------|------------------|
| `legacy` | Authoritative baseline path |
| `shadow` | Dual-path; legacy authoritative |
| `unified_with_fallback` | Not auto-promoted; decision gate only |
| `unified_only` | Caller tests / opt-in |

### Sampling policy

- **`full`** (default): every case runs legacy + unified.
- **`half`**: alternate cases dual; others legacy-only (recorded in warnings).

### Metrics captured

query count · successful comparisons · top-1 agreement · top-3/5 overlap ·
canonical-source hit rate · exact-symbol hit rate · primary/generated ratios ·
duplicate rate · no-result rates · partial rate · permission-denial correctness ·
context-budget compliance · deterministic repeatability · p50/p95 latency ·
shadow overhead · per-profile aggregates · result fingerprint (paths only)

Sensitive content is **not** stored in aggregates.

### Promotion gate (advisory)

`decision_ready_for_unified_fallback(report)` requires:

- enough comparisons
- 100% permission-denial correctness
- 100% context-budget compliance
- no forbidden-path case failures

Does **not** auto-change rollout.

---

## Second-wave callers

| Caller key | Entry | Profile | Default mode |
|------------|-------|---------|--------------|
| `control_center_repository_search` | `control_center_repository_search()` + optional `federated_search(types=["repository"])` | FAST_LOOKUP | `legacy` |
| `repair_context_prepare` | `repair_context_prepare()` | CODE_EXPLAIN | `legacy` |

### Control Center

- Default federated search (`types` empty) **unchanged**.
- Repository facet only when `entity_types` includes `repository`.
- Operator projection: bounded title/summary, labels, `untrusted=true`.
- No kill-switch / safety-control dependency.

### Repair context

- Retrieves implementation / tests / docs evidence.
- `authorizes_code_modification=False`, `authorizes_tool_invocation=False`.
- Prompt blocks wrap evidence as untrusted.
- Does not modify `repair/loop.py` execution path automatically.

### Configuration

```bash
export SAATHI_KS_ROLLOUT_CONTROL_CENTER_REPOSITORY_SEARCH=shadow
export SAATHI_KS_ROLLOUT_REPAIR_CONTEXT_PREPARE=shadow
```

```python
from saathi.knowledge.rollout import set_caller_mode, RolloutMode
set_caller_mode("control_center_repository_search", RolloutMode.SHADOW)
set_caller_mode("repair_context_prepare", RolloutMode.SHADOW)
```

### Rollback

1. Unset `SAATHI_KS_ROLLOUT*` or set `legacy`.
2. `reset_rollout_state()` for runtime overrides.
3. First-wave and M18.2 paths remain intact.

---

## Prompt injection

Retrieved repository content that says “ignore rules / trade / deploy / leak secrets”
remains **data**. Partitioning:

- governing system policy
- canonical SaathiOS policy
- mission objective
- retrieved evidence (wrapped)
- generated synthesis

No retrieved source expands permissions.

---

## Trading Guardian / InsForge

- Knowledge package has no trading imports or order APIs.
- Shadow campaign cannot place or approve orders.
- InsForge not started, not expanded, dual-flag defaults unchanged.

---

## Disable notes

Same as M19.1 plus second-wave env keys above.
