# M17.17 — Governed Graph Mission Scheduling & Recovery Integration

## Goal

Complete the integration between M17.14 (governed mission scheduling), M17.15
(governed pipeline recovery), M17.16 (bounded graph pipelines), and M17.13
(MissionEngine) so a **scheduled occurrence can launch a graph‑backed mission,
survive interruption, resume safely through the existing graph + recovery systems,
and settle the mission and scheduler occurrence exactly once.**

No new execution path is introduced. The whole chain is:

```
Scheduler / Trusted Event
  → Mission occurrence
    → MissionEngine            (mission authority)
      → existing PipelineRunner
        → existing bounded graph executor (M17.16)
          → run_harness_action → Adapter → INDEPENDENT verification
            → existing ledger, checkpoints, claims, recovery records (M17.15)
```

## What was already true before M17.17

- The **scheduler already delegates only to the MissionEngine** (`dispatch_occurrence`
  → `engine.create` + `engine.launch`); it never touched a pipeline, adapter, or tool.
- `MissionEngine.run` already dispatched to the **bounded graph executor** when the
  bound template declared `build_graph` (M17.16), through the **same PipelineRunner**.
- Durable links occurrence→mission (`link_occurrence_mission`) and mission→pipeline
  (`finish_mission_run.last_pipeline_id`) already existed.

So the **happy path** (schedule → occurrence → mission → graph → join → settle) was
already reachable. M17.17 closes the **lifecycle‑integration gaps**:

1. **Honest graph→mission state propagation.** A failed graph now maps into an honest
   mission disposition instead of a flat `failed`.
2. **Scheduled graph recovery.** A failed graph mission can resume its *existing* graph
   through the existing recovery interface and settle the occurrence — without a second
   mission, graph, branch, join, or settlement.
3. **Restart‑safe reconciliation** for the crash windows between graph, mission, and
   occurrence settlement.

## Components

### 1. `MissionEngine` additions (mission remains the authority)

- **`_classify_graph_failure(pid, owner, code)`** — maps a FAILED graph into a mission
  disposition by inspecting the durable branch states (owner‑scoped):
  - branch `approval_required` (or `APPROVAL` in code) → mission **BLOCKED**,
    `failure_code = GRAPH_APPROVAL_REQUIRED`
  - branch `stop_uncertain` / verification‑uncertain → mission **BLOCKED**,
    `failure_code = GRAPH_STOP_UNCERTAIN`
  - branch `blocked` → mission **BLOCKED**
  - otherwise → mission **FAILED** (auto‑recoverable upstream if the category is transient)
- **`resume_graph_mission(mission_id, owner)`** — recovers a FAILED graph mission by
  resuming its **existing** graph pipeline through `GraphPipelineRunner.resume` (the
  existing public recovery interface). It reuses dependency‑closed verified checkpoints,
  reruns only the interrupted branch, runs the join once, then records the outcome on a
  **deterministic linked‑retry mission** (`ms_rec_<sha(parent)>`). The original failed
  mission stays **immutable** (audit truth preserved). Fully idempotent.
- **`settle_recovered(...)`** — binds an already‑resumed graph result to a fresh mission
  and finalizes it through the normal mission lifecycle **without launching a second
  graph**. Idempotent on a terminal mission.
- **`reconcile_running_mission(mission_id, owner)`** — crash window F: a mission left
  RUNNING while its graph already reached a terminal state; settle the mission from the
  authoritative graph state (resolving the graph by `last_pipeline_id` or, if never
  written pre‑crash, by `pipelines_for_correlation`).

### 2. `MissionScheduler` additions (still delegates only to the MissionEngine)

- `dispatch_occurrence(..., graph_recovery=False)` and
  `_finalize_from_mission(..., graph_recovery=False)` — additive, **default‑off** (M17.14
  behavior unchanged):
  - mission `BLOCKED` + `GRAPH_APPROVAL_REQUIRED` → occurrence **approval_required**
  - when `graph_recovery=True` and the mission failed with a graph that carries an
    **open, allowlisted‑transient** recovery record with retries remaining, the occurrence
    is **deferred to `retry_wait`** (recoverable) instead of settled `failed` — so the
    coordinator can resume it. A non‑retryable failure still settles terminally at once
    (no relaunch storm).
- `settle_occurrence_from_mission(...)` — public wrapper the coordinator reuses.
- `_graph_retryable(pid)` — **observes** the existing recovery record; never computes
  checkpoint/graph‑ready/branch‑retry logic itself.

### 3. `ScheduledGraphCoordinator` (`saathi/application_harness/scheduled_graph.py`)

The seam — not a new engine. It:

- registers trusted **graph‑backed mission templates** (`graph_data_bundle`: SQLite root
  → two verified SQLite branches → zip join);
- `dispatch()` — dispatches through the scheduler with `graph_recovery=True` (fresh
  execution still flows through `MissionEngine.launch` only — never the graph executor);
- `recover()` — idempotently reconciles ONE occurrence end‑to‑end: confirms owner
  consistency, settles a crash‑stuck running mission (case F), resumes a failed graph
  mission through `engine.resume_graph_mission`, and settles the occurrence exactly once;
- `reconcile()` — bounded, deterministic, restart‑safe pass covering the graph‑mission
  cases the existing scheduler/graph reconcilers do not (F, G, retry_wait recovery, stale
  step claims), delegating the rest to the existing reconcilers;
- `health()` — owner‑safe Control Center aggregate + attention items.

## Idempotency model (layered, durable — never memory‑only)

| Uniqueness | Mechanism |
|---|---|
| one occurrence per due time | scheduler `UNIQUE(dedup_key)` (M17.14) |
| one mission per occurrence | deterministic mission id (M17.14) |
| one graph pipeline per mission run | `create_pipeline` PK + `create_graph` PK (M17.16) |
| one recovery op per graph | `claim_recovery` lease (M17.15) |
| one claim per graph step | `claim_graph_step` lease (M17.16) |
| one join execution | graph join barrier + step claim (M17.16) |
| one recovered mission | deterministic `ms_rec_<sha(parent)>` id |
| one final mission / occurrence settlement | terminal‑immutable transitions (M17.13/14) |

Concurrent sweeps / dispatches / recover calls therefore create no duplicate work: each
mutating sub‑operation holds its own durable lease, so two passes cannot double‑execute
any step, branch, join, mission, or settlement. A resume in progress under another
worker's lease is short‑circuited (`resume_in_progress`) and left recoverable.

## State propagation map

| Graph | Mission | Occurrence |
|---|---|---|
| succeeded | completed | succeeded |
| failed (transient) | failed | retry_wait (deferred) → succeeded after recovery |
| failed (hard) | failed | failed |
| approval_required branch | blocked (`GRAPH_APPROVAL_REQUIRED`) | approval_required |
| stop_uncertain / verification | blocked (`GRAPH_STOP_UNCERTAIN`) | blocked (attention) |
| blocked branch | blocked | blocked |
| running / retry_wait | running | running / retry_wait |

Success is never invented while recovery is pending; a mission is never `completed`
until the graph join and all required verification succeeded.

## Database

**No new tables.** M17.17 reuses existing records and adds one owner‑safe **read‑only**
helper, `RunLedger.pipelines_for_correlation`, to resolve a mission's graph pipeline
after a crash between graph completion and mission settlement. All M17.8–M17.16 data,
backup, restore, and integrity behavior is preserved.

## Boundaries

- **MissionEngine** owns mission validation, ownership, state, history, launch, and
  settlement. The scheduler/coordinator never duplicate mission lifecycle logic.
- **Graph recovery** stays in the existing recovery layer; the coordinator only *requests*
  it via `engine.resume_graph_mission` / `graph_runner.resume`.
- **Trading Guardian remains unengaged.** This layer opens no trading, broker, exchange,
  order, withdrawal, leverage, transfer, or portfolio‑execution surface (regression test).
