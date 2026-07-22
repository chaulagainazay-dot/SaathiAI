# M17.16 — Governed Bounded Parallel & Branching Pipeline Graphs

## One engine, extended — not a second one

M17.16 adds a small, deterministic, **acyclic** graph capability to the existing
governed pipeline. It does **not** add a second pipeline engine, execution engine,
DAG engine, scheduler, retry framework, checkpoint system, approval system, or
ledger. The execution hierarchy is unchanged:

```
Mission / Scheduler
  └─ MissionEngine
       └─ PipelineRunner                      (M17.12, sequential — untouched)
            └─ Dependency-aware bounded executor   (M17.16 — new, thin)
                 └─ PipelineRunner._run_step  (the SAME governed per-step path)
                      └─ run_harness_action    (ownership → trust → risk/approval)
                           └─ the sole Adapter
                                └─ INDEPENDENT verification
                                     └─ durable ledger + M17.15 checkpoints
```

Every executable step — root, every branch step, and the join — still runs
through `PipelineRunner._run_step` → `run_harness_action`. The graph layer only
decides **which** steps are ready, runs independent ready steps under **bounded
local concurrency**, and enforces **one explicit join barrier**.

## Product outcome

Before M17.16 a pipeline was strictly `A → B → C → D`. After M17.16 a bounded
graph is supported:

```
          ┌→ B ─┐
   A ──────┤     ├──→ D
          └→ C ─┘
```

* `A` (the fork) completes and is independently verified first.
* `B` and `C` are independent branches and may run concurrently.
* `D` (the join) starts only after **both** `B` and `C` succeed and verify.
* If `B` or `C` fails, `D` never runs.
* On resume, verified branches are reused; only invalidated branches and their
  descendants rerun.

## New module — `saathi/application_harness/pipeline_graph.py`

* `GraphStep(name, harness_id, operation_id, plan, dependencies, owner_id)` —
  duck-types as a `PipelineStep` so `_run_step` consumes it directly.
* `GraphSpec(name, owner, steps, concurrency_limit, correlation_id, pipeline_id)`.
* `validate_graph(spec)` → `GraphValidation` — full static validation.
* `GraphPipelineRunner` — bounded dependency-aware executor + graph resume +
  crash reconciliation, wrapping the existing `PipelineRunner`.
* `graph_dependency_fingerprint(step, artifact_fps)` — deterministic, order-
  independent dependency fingerprint (sorted declared deps + their artifact fps).

## Bounded limits (limits must exist and are tested)

| Limit | Value | Constant |
|-------|-------|----------|
| max total steps | 16 | `MAX_STEPS` |
| max concurrent workers | 4 | `MAX_CONCURRENCY` |
| max fork width (branch steps) | 4 | `MAX_BRANCH_WIDTH` |
| joins | ≤ 1 | (topology rule) |
| forks | ≤ 1 | (topology rule) |

## Bounded local concurrency

A single `concurrent.futures.ThreadPoolExecutor(max_workers=concurrency_limit)`
runs ready steps. No unbounded thread/process creation, no shell orchestration, no
distributed queue, no remote worker. The ledger uses WAL + `busy_timeout`, so
concurrent per-step ledger writes serialize safely; the actual work (subprocess
harness) runs in parallel. Each branch step is handed **only its declared
dependency artifacts** — confinement is preserved from the sequential pipeline.

## Determinism

Parallel completion order may vary, but **durable behavior is deterministic**:
graph validation, topological order (Kahn's algorithm, ties broken by declaration
index), ready ordering (declaration index), branch keying (min step name of a
weakly-connected component), dependency fingerprints (sorted), checkpoint
selection, reusable-subgraph computation, and the final pipeline result (success
requires *all* steps succeeded — order-independent). The final result never
depends on thread timing.

## Join barrier

The join is an ordinary step whose `dependencies` are the branch tips. The
dependency mechanism **is** the barrier: the join becomes ready only when every
upstream branch step is in the `succeeded` set with valid verification evidence.
There is no partial join and no "best effort" join — a failed / blocked /
approval-required / stop-uncertain / retry-exhausted upstream branch prevents the
join from ever becoming ready.

## Fail-closed

On the first terminal branch failure the scheduler stops submitting new work; the
join never runs; already-running sibling futures settle honestly and their real
result is recorded; unstarted sibling branches are recorded `cancelled`; the
pipeline finalizes `failed`. No fake rollback, no partial success is ever labelled
succeeded.

## Ledger (additive)

New tables (see `M17_16_MIGRATION.md`): `pipeline_graph` (structure: fork/join/
concurrency/branch count/resumed_from), `pipeline_dependency` (edges),
`pipeline_branch` (per-branch state), `pipeline_step_claim` (durable per-step
execution claim for dedup + crash-safe reclaim). The graph **is** a
`pipeline_run` — it reuses `create_pipeline`/`start_pipeline`/`complete_pipeline`,
`pipeline_step`, and `pipeline_checkpoint` unchanged.

## Reused subsystems (unchanged)

* `PipelineRunner._run_step` — the sole per-step governed execution path.
* M17.15 `pipeline_recovery._validate_checkpoint` — checkpoint integrity.
* M17.15 `RETRY_SCHEDULE`, `retry_delay`, `RETRYABLE_CATEGORIES`, recovery claim.
* M17.13 `MissionEngine` — a graph mission delegates through the SAME runner.
* M17.9 durable ledger, backup/restore, control center, CLI patterns.

See `M17_16_GRAPH_SEMANTICS.md` for states, `M17_16_VALIDATION.md` for results,
`M17_16_OPERATIONS.md` for the operator runbook.
