# M17.16 — Graph Semantics

## Graph model

Each step carries: `step_id` (name), `step_name`, `owner_id`, `dependencies`, the
step definition (harness/operation/plan), risk level, approval requirement,
expected artifacts (`produces`), verification policy (`verify_kind`/`verify_target`),
retry policy (shared M17.15 schedule), checkpoint policy (verified success →
checkpoint), and an execution fingerprint (`step_fingerprint`).

## Graph rules (all enforced before execution)

* all step ids unique
* every dependency references an existing step
* no self-dependency
* no cycle
* no duplicate dependency edge
* at least one root (in-degree 0)
* every non-root step has explicit dependencies
* the join step has ≥ 2 upstream dependencies
* graph size ≤ `MAX_STEPS` (16)
* concurrency in `[1, MAX_CONCURRENCY]` (4)
* fork width ≤ `MAX_BRANCH_WIDTH` (4)
* at most one fork (out-degree ≥ 2) and at most one join (in-degree ≥ 2) — a
  second fork is rejected as an unsupported nested fork; a second join is rejected
* all steps share the spec owner (per-step `owner_id`, if set, must match)
* no path escape / secret-shaped name / artifact collision / unknown or
  non-executable harness

A validation failure returns `{"ok": False, "reason": "graph_invalid", "errors":
[...]}` and **no pipeline_run is created** — no partial execution.

## Step states

Existing pipeline-step semantics are preserved. Derived/observable step states:
`pending`, `waiting_dependencies`, `ready`, `claimed`, `running`, `succeeded`,
`failed`, `blocked`, `approval_required`, `cancelled`, `skipped`, `stop_uncertain`.
Terminal states are immutable. A step becomes **ready** only when all dependencies
are `succeeded` with valid verification evidence; a checkpoint-reused dependency
counts as `succeeded` only after checkpoint integrity is revalidated.

## Branch states

Each branch (a weakly-connected component of the subgraph excluding roots and the
join, keyed by its min step name) has an explicit durable state:
`pending → running → {succeeded | failed | blocked | approval_required |
cancelled | stop_uncertain}`. A branch is `succeeded` only when **every** step in
it succeeded and verified — never from process exit alone.

## Branch classification (deterministic)

| Step outcome | Branch state |
|--------------|--------------|
| all steps success + verified | `succeeded` |
| error contains `APPROVAL` | `approval_required` |
| error contains `UNCERTAIN`/`VERIFICATION` | `stop_uncertain` |
| status `blocked` | `blocked` |
| any other failure | `failed` |
| never started after a sibling failure | `cancelled` |

## Join barrier

The join runs only when: every required upstream branch is terminal `succeeded`;
all required artifacts exist and pass integrity; upstream verification evidence is
still valid; owner matches; approval/risk rules still hold. It never runs when any
upstream branch is failed / blocked / approval_required / cancelled /
stop_uncertain / retry_exhausted / checkpoint_invalid. No partial join.

## Cancellation

A branch failure prevents new downstream work and requests cancellation of not-yet-
started sibling work; already-running siblings settle safely and honestly.
Execution whose outcome cannot be proven is recorded `stop_uncertain` (never
silently cancelled). We never kill a process in a way that creates uncertain side
effects beyond the existing adapter's cancellation guarantees.

## Checkpoint reuse (dependency-closed)

A branch step's verified success writes a durable checkpoint (M17.15). Reuse
requires identical owner, definition, dependencies, inputs, produced artifact,
verification policy, risk, and approval scope, plus revalidated artifact
integrity. A step is reusable **only if all of its dependencies are also
reusable or freshly succeeded** — the reusable set is dependency-closed. An
isolated downstream checkpoint whose upstream evidence is invalid is never reused.

## Graph resume model

1. Load the original graph; confirm owner + authorization.
2. Validate the graph definition.
3. Validate all existing checkpoints.
4. Build the reusable dependency-closed subgraph.
5. Mark reusable steps succeeded-from-checkpoint; mark invalidated steps and all
   descendants for rerun.
6. Recompute the ready queue; run ready branches under bounded concurrency.
7. Revalidate artifacts before the join; execute the join through
   `run_harness_action`; independently verify.
8. Record reused / rerun / failed / suppressed steps; link the resumed run to the
   original; deduplicate concurrent resume requests via the recovery claim.

## Retry (shared M17.15 framework)

Branch-local retry is allowed only for existing retryable (transient/
infrastructure) categories and is bounded by the shared `RETRY_SCHEDULE`. Retry
never applies to approval / owner / risk / verification / invalid-graph / invalid-
dependency / tamper / path-escape / secret / manual-only / cancellation / unknown /
Trading-Guardian categories. A retry of one branch does not rerun successful
independent sibling branches unless their checkpoints become invalid.

## Determinism guarantees

Validation, topological order, ready ordering, claim tie-breaking, branch naming,
join dependency ordering, artifact mapping, failure classification, final result,
checkpoint selection, resumed-step selection, and control-center summaries are all
deterministic and independent of thread timing.
