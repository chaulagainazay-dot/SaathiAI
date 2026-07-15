# M19.3 — Real-Index Knowledge Campaign and Controlled Promotion

**Status:** Pilot (not production-ready)  
**Base:** M19.2 shadow campaign + M18.2 codebase memory  
**Verdict target:** `M19.3 REAL-INDEX PILOT PROMOTED`

---

## Purpose

1. Evaluate Unified Knowledge Service retrieval against **real registered repository indexes** (not synthetic stubs).
2. Collect durable aggregate quality metrics (no retrieved bodies / secrets).
3. Promote **exactly one** low-risk caller from default legacy to `unified_with_fallback`.
4. Preserve per-caller and global disable/rollback controls.
5. Keep chat LTM, voice, auth, payments, deployment, and Trading Guardian out of scope.

---

## Architecture reuse

| Layer | Reused as-is |
|-------|----------------|
| Indexer / store / retrieve | M18.2 `saathi.codebase_memory` |
| KnowledgeService router/rank/dedupe/context | M19.0 |
| Adoption gateway + fallback policy | M19.1 |
| Shadow campaign metrics | M19.2 `campaign.py` |
| Rollout modes / env | M19.1–M19.2 `rollout.py` |

**New module:** `saathi/knowledge/real_campaign.py`

- `inspect_registered_indexes` — health inventory for `codebase_memory` sources  
- `ensure_index_current` — bounded M18.2 index ensure (no full rescans when healthy)  
- `run_real_index_campaign` — dual-path legacy vs unified on real indexes  
- `write_campaign_report` — aggregate JSON only  
- `promotion_evidence_summary` — handoff-safe summary  

Does **not** create a second Knowledge Service or parallel retrieval stack.

---

## Real-index campaign

### Cases

Bounded subset of M19.2 `CAMPAIGN_CASES` (`REAL_INDEX_CASE_IDS`, 12 cases):

exact symbol · file location · architecture · related tests · milestone evidence ·
repair planning · control-center operator · permission denial · secret path ·
context budget · prompt injection · recent change

### Metrics recorded

| Metric | Notes |
|--------|--------|
| top-1 / top-3 / top-5 agreement-overlap | vs legacy paths |
| canonical source hit rate | docs/primary ranking |
| exact symbol hit rate | symbol category |
| repository-selection accuracy | no foreign `repository_id` |
| primary-evidence ratio | mean |
| duplicate rate | mean |
| stale-result rate | freshness labels |
| no-result / partial rates | legacy + unified |
| permission-denial correctness | must be 1.0 |
| context-budget compliance | must be 1.0 |
| deterministic repeatability | optional re-run |
| p50 / p95 latency | may flag insufficient n for p95 |

Sensitive content is never stored in aggregates.

### Promotion gate

`promotion_decision.ready` requires:

- index ready (`HEALTHY`/`STALE`/`DEGRADED` with enough chunks)
- ≥5 successful comparisons
- 100% permission-denial correctness
- 100% context-budget compliance
- 100% repository-selection accuracy
- campaign case `ok` (no forbidden path hits)

Ranking need not match legacy exactly; prefer canonical evidence quality.

---

## Controlled promotion

| Field | Value |
|-------|--------|
| Caller | `codebase_memory_search` (operator code lookup) |
| Mode | `unified_with_fallback` |
| Why this caller | Real M18.2 legacy fallback path; first-wave; not safety-critical |
| Not promoted | mission context, audit evidence, CC repo, repair, LTM, TG, auth, payments |

### Resolution order

```
explicit → runtime caller → env caller → runtime global → env global
  → M19.3 promoted default → legacy
```

### Disable / rollback

```bash
# Per-caller
export SAATHI_KS_ROLLOUT_CODEBASE_MEMORY_SEARCH=legacy

# All pilot promotions
export SAATHI_KS_DISABLE_PROMOTIONS=1

# Global
export SAATHI_KS_ROLLOUT=legacy
```

Runtime: `set_caller_mode("codebase_memory_search", RolloutMode.LEGACY)`  
or `reset_rollout_state()` after env clear.

---

## Security

- Retrieved text remains data (prompt-injection boundaries preserved).
- No security-denial fallback (M19.1 policy unchanged).
- No Trading Guardian coupling; no InsForge expansion.
- No path traversal via free query params; registry remains closed.
- Campaign report write refuses known secret markers.

---

## Out of scope

- Chat LTM / voice turn retrieval  
- Global adoption of all callers  
- Production deployment / merge to main  
- M19.4 context composer (next)  
- M19.5 incremental refresh automation beyond existing M18.2 indexer  
