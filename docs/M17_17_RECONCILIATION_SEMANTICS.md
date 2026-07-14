# M17.17 — Reconciliation Semantics

Deterministic, bounded, restart‑safe reconciliation for scheduled graph‑backed
missions. The coordinator (`ScheduledGraphCoordinator.reconcile`) reuses the existing
graph and scheduler reconcilers and adds only the graph‑mission cases they do not cover.

## Guarantees

- **Disabled by default / opt‑in** — reconciliation runs only when explicitly called
  (`coordinator.reconcile(...)` or `coordinator.sweep(...)`). No always‑on OS/cloud
  scheduler is added.
- **Deterministic scan order** — occurrences are scanned in ledger order
  (`due_at, occurrence_id`); nothing depends on thread timing.
- **Bounded batch** — at most `_RECONCILE_BATCH` (25) recoverable occurrences per pass.
- **Overlap protection** — every mutating sub‑operation holds its own durable lease
  (occurrence claim, graph‑step claim, graph recovery claim). Two concurrent passes
  cannot double‑execute any step, branch, join, mission, or settlement. A resume already
  claimed by another worker short‑circuits (`resume_in_progress`) and is left recoverable.
- **Idempotent** — repeated passes converge; the recovered mission id is deterministic,
  the graph pipeline id is reused, and terminal records are immutable.
- **No silent infinite loop / no unbounded retry** — retry eligibility and schedule are
  the M15 allowlist + `[0, 60, 300, 900, 3600]s` bound; the occurrence retry counter is
  also bounded. Exhaustion propagates honestly.

## Pass sequence

1. `engine.graph_runner.reconcile(now)` — reclaim stale graph‑step claims (existing M16
   interface).
2. Stale RUNNING/CLAIMED occurrences with a graph mission → `recover()` (cases **F**, **G**).
3. `retry_wait` graph occurrences (bounded, deterministic) → `recover()`.
4. `scheduler.reconcile(now)` — the remaining non‑graph / stale‑lease work (M14).

## Cases

| Case | Situation | Action |
|---|---|---|
| **A** | Occurrence exists, mission missing | `scheduler.reconcile` requeues the occurrence; next dispatch creates the deterministic mission **once** |
| **B** | Mission exists, graph missing | `engine.launch`/re‑drive builds the graph **once** through the MissionEngine |
| **C** | Graph running | observed; never duplicated (per‑step claims) |
| **D** | Stale branch claim | existing graph recovery reclaims it safely |
| **E** | Branches succeeded, join not run | existing graph reconciliation runs the join **once** |
| **F** | Graph terminal, mission still running | `engine.reconcile_running_mission` settles the mission from the authoritative graph state |
| **G** | Mission terminal, occurrence unsettled | `scheduler.settle_occurrence_from_mission` settles the occurrence once |
| **H** | Recovery record exists | continue/observe that recovery; never create a second (recovery claim) |
| **I** | Approval required | stop; propagate `approval_required`; never auto‑approve |
| **J** | Stop uncertain | fail closed; surface attention; never invent success |

## Retry & resume policy

- Reuses M17.15 eligibility (`RETRYABLE_CATEGORIES`, transient/infrastructure only) and
  schedule `[0, 60, 300, 900, 3600]s`, then exhausted. No new graph‑scheduler timing.
- **Never** auto‑retried: `approval_required`, owner mismatch, risk rejection, invalid
  template/graph/parameters, verification failure from bad output, artifact tampering,
  path escape, secret‑policy rejection, manual‑only, cancellation, unknown failure,
  Trading Guardian rejection.
- A scheduled occurrence never repeatedly relaunches a non‑retryable failed graph — such
  failures settle the occurrence terminally on the first dispatch.

## Approval safety

Scheduling, graph parallelism, and recovery **never** imply approval. If any branch
requires approval: the branch stops at `approval_required`, the join never runs, the
mission becomes `blocked (GRAPH_APPROVAL_REQUIRED)`, the occurrence becomes
`approval_required`, reconciliation does not auto‑approve, retries do not auto‑approve,
another branch cannot approve it, and a schedule cannot approve it. Risk‑4 remains
manual‑only. A changed risk/step definition invalidates checkpoint/approval reuse via the
step fingerprint (M17.15/16).

## Owner safety

Schedule, occurrence, trigger, receipt, mission, mission run, graph pipeline, branches,
claims, checkpoints, artifacts, and recovery operation must share one owner. Any mismatch
stops before execution and fails closed. Cross‑owner launch, recovery, checkpoint reuse,
artifact use, occurrence settlement, and Control Center detail are all rejected/hidden.
