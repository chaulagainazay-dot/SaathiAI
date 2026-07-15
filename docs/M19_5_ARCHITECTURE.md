# M19.5 — Incremental Knowledge Refresh and Repository Change Awareness

**Status:** Pilot (not production-ready)  
**Base:** M18.2 codebase_memory indexer + M19.0–M19.4 knowledge stack  
**Verdict target:** `M19.5 INCREMENTAL REFRESH READY`

---

## Purpose

Detect repository changes and refresh **only affected index portions**, with
durable fingerprints, cache-epoch invalidation, lease-safe concurrency, and
audit evidence — without full unnecessary rescans or source mutation.

---

## Module

`saathi/knowledge/refresh.py`

| API | Role |
|-----|------|
| `repository_fingerprint` | Stable repo+commit+branch+schema digest |
| `detect_changes` | git diff when possible; else full-walk note |
| `incremental_refresh` | lease → index_repository → fingerprint → cache epoch → evidence |
| `refresh_registered_repositories` | per-source isolated refresh |
| `last_refresh_evidence` | load durable meta |
| `acquire_refresh_lease` / `release_refresh_lease` | concurrency + stale recovery |

`CodebaseMemoryRuntime.refresh()` routes through `incremental_refresh` (falls
back to M18.2 `index(rebuild=False)` on import failure).

---

## Behaviours

1. Resolve current identity (commit, branch, worktree).
2. Compare with indexed commit + stored fingerprint.
3. If fingerprint matches and index has data → `skipped_fresh`.
4. Else acquire lease (recover stale leases).
5. Call M18.2 `index_repository` (hash-based skip of unchanged files; mark deleted).
6. Update `repository_fingerprint` and bump `cache_epoch`.
7. Persist aggregate evidence in index meta (`last_refresh_evidence`).
8. Clear in-progress marker; release lease.

Git-aware change detection (`git diff --name-status old..new`) records:

* changed files
* deleted files  
* renames (`R*` status)

Secret / excluded paths are filtered before reporting.

---

## Multi-repository isolation

* Each source refreshes with its own `location` and identity index key.
* No cross-repo store sharing by repository_id collision (identity `index_key`).
* `refresh_registered_repositories` iterates registry sources independently.

---

## Safety

* Source trees are never written by refresh.
* Secret paths remain excluded (M18.2 policy + content scan).
* No embedding model downloads.
* No arbitrary repository clones.
* No Trading Guardian / InsForge coupling.
* Evidence JSON contains aggregates only (paths in change_set are relative; no bodies).

---

## Out of scope

* Distributed multi-host index consensus
* Semantic re-embedding pipelines
* Background daemon scheduler (CLI/runtime on-demand only)
* Production auto-refresh on every edit
