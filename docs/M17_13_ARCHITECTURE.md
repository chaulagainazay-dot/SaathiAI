# M17.13 Architecture — Autonomous Mission Engine

## Position in the stack
The Mission Engine is strictly ABOVE the pipeline. It adds a business-objective
layer and delegates downward; it introduces no new execution path.

```
Mission        (mission.py MissionEngine — objective, params, approval, template)
  ↓ delegates ONE PipelineSpec
Pipeline       (pipeline.py PipelineRunner — sequential, fail-closed, confined)
  ↓ per step
Harness Step   (service.run_harness_action — the SOLE governed entry)
  ↓
Adapter        (ApplicationHarnessAdapter — the SOLE process boundary)
  ↓
Verification   (independent; never trusts a tool's own success)
  ↓
Ledger         (run_ledger.py — durable, owner-safe, concurrency-proof)
```

A Mission NEVER knows how to run FFmpeg, SQLite, jq, zip, a shell, or a browser.
The ONLY place a mission touches concrete harness operations is a template's
`build_steps(params) -> list[PipelineStep]`, authored in trusted Python (like the
pilots). That step list becomes a `PipelineSpec` handed to the existing
`PipelineRunner`.

## Domain model
- **Mission**: id, owner, title, objective, mission_type (manual|scheduled|
  triggered|recurring|one_time), trigger, priority, risk, approval_required,
  template ref, validated params, schedule metadata, run_count, last_pipeline_id,
  failure_code, correlation_id, and lifecycle timestamps. Persisted in the `mission`
  table (owner-safe projection via `_MISSION_SAFE_FIELDS`).
- **MissionRun**: one execution attempt (`mission_run` table, UNIQUE per
  (mission_id, attempt)) recording the delegated pipeline_id, terminal state,
  failure_code, and steps_run — the durable execution history.
- **MissionTemplate**: reusable blueprint (title/objective/risk/approval/params +
  `build_steps`). Templates PRODUCE mission instances.
- **MissionParameter**: strongly-typed input (str|int|float|bool|enum, required,
  choices, default), validated before any execution by `validate_params`.

## State machine (fail-closed, terminal-immutable)
```
draft ─┬─> approval_required ─> approved ─> queued ─> running ─┬─> completed
       └─> approved ────────────────────────────────           ├─> failed
   (any active) ─> cancelled | blocked                          └─> (cancelled|blocked)
```
Enforced by an explicit `_MISSION_VALID` graph; any unlisted move is rejected. All
transitions run inside `BEGIN IMMEDIATE` with a state precondition (CAS-style), so
concurrent writers resolve deterministically and terminals never resurrect.

## Fail-closed execution
`MissionEngine.run` requires `queued`, opens a `mission_run` attempt
(`begin_mission_run`, guarded to `queued` only — no double-run), builds the trusted
steps, delegates ONE `PipelineSpec`, then:
- pipeline ok → mission `completed`;
- pipeline not ok / exception / missing-or-empty template → mission `failed`.
No partial success. A mission fails closed on: pipeline failure, approval denied,
owner mismatch, missing template, or any critical exception.

## Approval & ownership
- Ownership is checked on every engine op (`_owned`); a mismatch is rejected and
  never executes.
- Approval-required missions cannot be queued/run until explicitly approved;
  unapproved enqueue transitions to `approval_required` (no silent elevation). The
  per-step `run_harness_action` risk gate (risk≥3 → approval, risk 4 manual-only)
  still applies independently underneath — the mission layer can only be as
  permissive as the governed step layer allows.

## Read/observe surface
- Control Center `harnesses()` cell exposes owner-safe `missions` +
  `mission_health`; `_attention` surfaces failed (high) and approval_required
  (medium) missions as `harness_mission` items — owner-scoped.
- CLI: `mission-health` (always-on census) + admin-gated owner-safe `missions`,
  `mission-inspect`, `mission-history`, `mission-run`, `mission-retry`.

## Non-goals (this milestone)
Untrusted mission-spec JSON ingestion, live scheduling + event/triggered execution
(recurrence = instance-per-occurrence; no scheduler wired), parallel missions,
multi-user load. These are additive future work; the design leaves room for each
without touching the governed step/pipeline layers.

## Separation from the legacy `saathi/missions/` package
The pre-existing `saathi/missions/` (intake/proposal/brand/twin/…) is an OLDER
business-content subsystem in a different lineage with its own store. It is
UNTOUCHED. The M17.13 mission engine lives in
`saathi/application_harness/mission.py` alongside `pipeline.py` and the ledger, to
stay in the governed harness lineage and share the same durable ledger DB.
