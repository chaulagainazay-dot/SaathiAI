# M17.16 — Migration & Deployment

## Schema changes (additive only)

Four new tables are added to the harness run-ledger schema (`_SCHEMA` in
`saathi/application_harness/run_ledger.py`). All use `CREATE TABLE IF NOT EXISTS`
and are created automatically on ledger open — **no data migration, no backfill,
no destructive change**. Existing tables (`pipeline_run`, `pipeline_step`,
`pipeline_checkpoint`, `pipeline_recovery`, `mission*`, `run*`) are untouched.

### `pipeline_graph` (graph structure for an existing `pipeline_run`)
```
pipeline_id TEXT PRIMARY KEY   -- == the pipeline_run id (the graph IS a pipeline)
owner, name, step_count, concurrency_limit,
fork_step, join_step, branch_count, resumed_from, correlation_id,
created_at, updated_at
FOREIGN KEY(pipeline_id) REFERENCES pipeline_run(pipeline_id)
```

### `pipeline_dependency` (edges)
```
id, pipeline_id, step_name, depends_on
UNIQUE(pipeline_id, step_name, depends_on)
```

### `pipeline_branch` (per-branch durable state)
```
id, pipeline_id, branch_key, owner, step_names, state, failure_code, updated_at
UNIQUE(pipeline_id, branch_key)
```

### `pipeline_step_claim` (durable per-step execution claim)
```
id, pipeline_id, step_index, step_name, claim_owner, state,
lease_expires_at, claimed_at
UNIQUE(pipeline_id, step_index)
```

Indexes added: `idx_graph_owner`, `idx_dependency_pipeline`, `idx_branch_pipeline`,
`idx_branch_owner`, `idx_stepclaim_pipeline`, `idx_stepclaim_state`.

## Ledger API additions

`create_graph`, `inspect_graph`, `list_graphs`, `graph_health`, `upsert_branch`,
`set_branch_state`, `list_branches`, `branches_owned`, `claim_graph_step`,
`release_graph_step`, `reclaim_stale_step_claims`, `list_step_claims`. The
`health()` integrity report now also counts `graphs`, `branches`, `dependencies`,
and `step_claims` (backup/restore verified).

## Backward compatibility

* A ledger created before M17.16 gains the new tables on first open; existing rows
  are preserved and readable.
* Sequential pipelines (M17.12) and their recovery (M17.15) are unchanged — no
  behavioral difference.
* Backup and restore remain compatible: `sqlite3 .backup` copies the new tables;
  the restored integrity report matches the source (see the backup/restore test).

## Rollback

The tables and code are additive. To roll the code back, revert the M17.16 commit:
existing sequential pipelines and missions continue to work; the new tables simply
go unused (they are `IF NOT EXISTS`, so a re-forward is a no-op). No data loss.

## Deployment

Nothing is deployed, scheduled, or live-activated by this milestone. Graph
pipelines run only when a caller (a trusted mission template with `build_graph`, a
test, or an admin CLI resume) invokes them. Trading Guardian remains unengaged; no
external transport is activated.
