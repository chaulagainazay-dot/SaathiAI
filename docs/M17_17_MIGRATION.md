# M17.17 — Migration & Deployment Guide

## Schema

**No new tables. No destructive change. Additive‑only, backward‑compatible.**

M17.17 reuses existing records (schedule, occurrence, mission, mission_run,
pipeline_run, pipeline_graph, pipeline_branch, pipeline_step_claim,
pipeline_checkpoint, pipeline_recovery) and their existing columns. The only ledger
addition is a **read‑only** query method, `RunLedger.pipelines_for_correlation`, which
runs against the existing `pipeline_run.correlation_id` column — no migration required.

All M17.8–M17.16 data, backup files, restore paths, and integrity checks remain valid.
An M17.16 database opens unchanged under M17.17; an M17.17 database opens unchanged under
M17.16 (the new behavior is code‑level, not schema‑level).

## Rollback

Rollback point: commit `e7207dd` (M17.16). To roll back:

```
git revert <M17.17 commit>      # or: git reset --hard e7207dd  (local only)
```

No data migration to undo. Because M17.17 adds no schema, an existing database keeps
working after a code rollback; graph missions simply lose the scheduled‑recovery
integration behavior and fall back to M17.16 semantics.

## Enablement

The scheduled‑graph coordinator is **opt‑in**. Nothing runs automatically:

- Fresh scheduled graph missions: register a graph‑backed template (or use the bundled
  `graph_data_bundle`), create a schedule bound to it, and drive
  `ScheduledGraphCoordinator.sweep(...)` (or the existing scheduler runner) on your cadence.
- Recovery/reconciliation: call `coordinator.reconcile(...)` on your cadence. It is
  bounded, deterministic, and restart‑safe; it holds no long‑lived process.

The M17.14 scheduler default (`graph_recovery=False`) is preserved — existing scheduled
sequential missions and existing dispatch call sites are unaffected.

## Compatibility checklist

- [x] Additive schema only (none added)
- [x] Backup/restore compatible (existing graph/mission backup tests pass)
- [x] Integrity checks pass
- [x] M17.14 dispatch signature backward compatible (`graph_recovery` defaults off)
- [x] M17.16 graph execution unchanged
- [x] M17.15 sequential recovery unchanged
- [x] No second engine / scheduler / recovery framework introduced
