# M19.0 — Unified Knowledge Service, Retrieval Router, Multi-Repository Context

**Status:** Pilot (not production-ready)
**Package:** `saathi/knowledge/`
**Starting point:** M18.2 codebase memory remains the primary code index

---

## Role

Preferred **governed retrieval entry point** that coordinates existing sources:

| Source type | Adapter | Authority |
|-------------|---------|-----------|
| `codebase_index` | M18.2 `codebase_memory.search` | Code truth (per repo) |
| `documentation` | FS lexical over `docs/` | Docs |
| `decision_docs` | FS lexical (milestones/SES) | Operational decisions |
| `provider_metadata` | InsForge public config (read-only) | Provider status |
| `memory_ltm` | Memory engine (MISSION_CONTEXT only) | Not code authority |

Does **not** replace memory, KG, indexes, ExecutionGateway, or InsForge control plane.

---

## Profiles

| Profile | Use | Budget (chars) |
|---------|-----|----------------|
| `FAST_LOOKUP` | symbols, paths | 4k |
| `CODE_EXPLAIN` | how/where implementation | 12k |
| `MULTI_REPO_COMPARE` | cross-repo | 16k |
| `MISSION_CONTEXT` | mission prep | 14k |
| `AUDIT_EVIDENCE` | compliance, primary evidence | 10k |

## Ranking (weighted_fusion_v1)

```
final = 0.40*normalized_native
      + 0.15*trust
      + 0.10*freshness
      + 0.20*evidence_class_weight
      + exact_token_boosts
      − generated_penalty
```

Stable sort: `(-final_score, path, result_id)`.

## Compatibility

```python
from saathi.knowledge.compat import search_compatible
search_compatible(q, use_unified=False)  # legacy M18.2 default
search_compatible(q, use_unified=True)   # unified mapping
search_compatible(q, shadow=True)        # legacy + unified_shadow
```

## Permissions

* Unregistered repos not queryable via free params alone
* Sensitive paths (`.env`, keys, secrets) filtered
* Trading secrets / exchange sources denied
* TG unengaged

## Disable / rollback

Remove or stop calling `KnowledgeService`; M18.2 paths remain.
`git revert <m19.0-commit>`
