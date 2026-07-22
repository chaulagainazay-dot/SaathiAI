# M17.12 Validation — Governed Multi-Harness Pipeline

Start / rollback point: HEAD `22c2fe0` (M17.11). Makes the four proven live
application harnesses (FFmpeg / SQLite / jq / zip) composable into ONE governed,
deterministic, sequential workflow. This is an ORCHESTRATOR, not a second
execution engine: every step runs through the SAME governed
`service.run_harness_action` (ownership → trust → risk/approval → the sole
adapter → independent verification). Reuses the M17.9 ledger (additive tables),
the event bus, the Control Center attention model, and the admin gate. No new
execution engine / trust model / DB / scheduler / bus.

## What was built
- `run_ledger.py` — additive `pipeline_run` + `pipeline_step` tables in the SAME
  ledger DB. `pipeline_run` PRIMARY-KEY-unique (concurrent duplicate create → one
  winner). Methods: `create_pipeline` (owner-mandatory, secret-rejecting),
  `start_pipeline` (pending→running, terminal-safe), `record_pipeline_step`
  (idempotent upsert, unique `(pipeline_id, step_index)`), `complete_pipeline`
  (running→succeeded|failed, terminal-immutable), owner-scoped reads
  `inspect_pipeline` / `list_pipelines`, and `pipeline_health`. `health()` gains a
  `pipelines` census. State machine: `pending → running → {succeeded | failed}`.
- `pipeline.py` (NEW) — `PipelineRunner` composes `run_harness_action` steps in ONE
  confined per-pipeline workspace under the gitignored harness data dir.
  `PipelineSpec` / `PipelineStep` / `StepPlan` / `StepContext` are declared in
  TRUSTED Python (like the pilots). Fail-closed short-circuit: the first
  non-`success` (blocked/failed/timeout/uncertain/approval_required) halts the
  pipeline; later steps never run. Defence-in-depth confinement: a produced /
  verify / consumed path that is absolute, contains `..`, or resolves outside the
  workspace is rejected BEFORE the step runs. Artifact wiring: a producing step's
  output is exposed to later steps by name via `StepContext.artifacts` (all inside
  the workspace). No per-step ledger `run` row is fabricated — a single harness
  action is not process-journaled, so the `pipeline_step` record IS the durable
  per-step ledger entry.
- `control_center/aggregator.py` — `harnesses()` cell exposes owner-safe
  `pipelines` + `pipeline_health`; `_attention()` folds failed pipelines
  (`kind: harness_pipeline`, high).
- `cli.py` — `pipeline-health` (always: aggregate census, no secrets);
  `pipelines` + `pipeline-inspect <id>` (admin-gated, owner-safe operator
  diagnostic; verified OS identity model unchanged).
- `critical_checks.json` — 7 dedicated **blocking** `pipeline.*` entries.

## Fail-closed policy (deterministic, no LLM)
The orchestration decision is pure control flow. A step is `success` only when the
governed service returns `status == "success"` (which already includes INDEPENDENT
verification — the process's own exit code is never trusted). Any other status —
`blocked`, `failed`, `timeout`, `uncertain`, `approval_required`, an unknown /
non-executable harness, a plan-builder exception, or a confinement violation —
halts the pipeline at that step and marks it `failed` with the step index +
failure code. Later steps NEVER run.

## Confinement
All steps share one workspace root, the SOLE `file_roots` handed to the adapter.
On top of the adapter's own `_confine`, the runner rejects, before execution: an
absolute `produces`, a `produces` containing `..`, a `produces`/`verify_target`
that realpath-resolves outside the workspace. Artifact wiring can therefore never
smuggle a path that escapes the workspace into a later step.

## Approval gates honoured
A step whose operation has `risk >= 3` returns `approval_required` from the
governed service unless the step's `StepPlan.approved` is explicitly set — the
pipeline halts, with no silent elevation and no later step. `risk >= 4` remains
manual-only. Proven both ways (`test_pipeline_approval_gated_step_halts`,
`test_pipeline_approved_step_proceeds`).

## Proven properties (executed)
Environment: `.venv` Python 3.12, macOS/darwin, POSIX; spawn multiprocessing.
Live apps present: ffmpeg, sqlite3, jq, zip.

- LIVE two-application chain: sqlite `safe_mutation` → `data.db` → zip `pack` →
  `bundle.zip`, both independently verified, pipeline `succeeded`, both artifacts
  on disk; the zip provably packages the exact db the sqlite step produced
  (`test_live_sqlite_then_zip_pipeline_succeeds`,
  `test_pipeline_artifact_wiring_uses_prior_output`).
- Fail-closed: a failing middle step halts a 3-step pipeline — the third step is
  never recorded; unknown harness/op, non-executable harness, and a plan-builder
  exception all fail closed (`test_pipeline_fail_closed_short_circuits`,
  `test_pipeline_unknown_harness_operation_fails_closed`,
  `test_pipeline_non_executable_harness_fails_closed`,
  `test_pipeline_step_builder_error_fails_closed`).
- Confinement: escaping `produces` (`..`), absolute `produces`, and escaping
  `verify_target` all rejected before execution; no file created outside the
  workspace (`test_pipeline_confinement_*`).
- Approval: gated step halts when unapproved; proceeds when explicitly approved.
- Shell-safety: a NUL-byte argument is blocked by the adapter (argv-only, never a
  shell string) (`test_pipeline_argv_control_char_blocked_not_shelled`).
- Owner scope + owner-safe records: cross-owner `inspect`/`list` return
  nothing; the serialized record contains no argv/output/SQL/stdout; a
  secret-shaped pipeline name is rejected (`test_pipeline_owner_scoped_inspect`,
  `test_pipeline_records_are_owner_safe`, `test_pipeline_secret_shaped_name_rejected`).
- Ledger invariants: duplicate pipeline id rejected; terminal immutable; empty
  owner rejected; multi-PROCESS concurrent create dedups to exactly one winner
  (`test_pipeline_duplicate_id_rejected`, `test_pipeline_terminal_immutable`,
  `test_concurrent_pipeline_create_dedups`).
- Control Center: a failed pipeline surfaces in owner attention
  (`kind: harness_pipeline`); a different owner sees nothing
  (`test_control_center_surfaces_failed_pipeline`).

## Validation ladder (run, results)
1. M17.12 suite (`test_m17_12_harness_pipeline.py`) → **21 passed**.
2. Dedicated Critical Manifest — 7 blocking `pipeline.*` entries via the real
   manifest runner → **all green** (live chain+wiring, fail-closed, confinement,
   approval+shell-safety, owner-scope+safe-records, ledger+concurrency,
   control-center).
3. Full Critical Manifest (all blocking checks + server smoke) → **146 checks green**
   (139 prior + 7 new `pipeline.*`).
4. Full suite → **1655 passed / 1 skipped / 0 failed** (+21 M17.12 tests over the
   1,634 baseline).
5. Secret scan over M17.12 files → **0 matches**.
6. `git diff --check` → clean.
7. Milestone-owned tree clean; `saathi/memory/conventions.md` remains modified +
   **unstaged** (unrelated auto-learned memory append, preserved).

## Security controls
Preserve all M17.9/M17.10/M17.11 controls. No new execution engine — steps only
run via the governed service (independent verification retained). Owner-scoped
visibility; owner-safe records (no argv/output/SQL/secrets — only a
workspace-relative artifact name); secret-shaped names rejected; workspace
confinement with pre-execution path-escape rejection; approval gates honoured
(no silent elevation); argv-only (no shell); admin-gated CLI with verified OS
identity; deterministic control flow (no LLM).

## Trading Guardian boundary
Not engaged. A pipeline executes no financial action; no step triggers a trade; no
pipeline result authorizes financial execution; approval gates are strengthened,
never bypassed. The orchestrator stays compatible with a future financial-action
step, which would remain approval-gated and advisory unless separately approved.

## Migration / compatibility
Additive `CREATE TABLE IF NOT EXISTS pipeline_run / pipeline_step` — existing
ledger DBs gain them on next open; no destructive change, no rewrite.
M17.9/M17.10/M17.11 fully preserved. Rollback = revert the single commit (existing
DBs retain two unused tables).

## Known limitations / deferred
- Sequential only — parallel / branching DAGs are out of scope.
- No pipeline-level retry / resume / checkpoint (a failed pipeline is re-run as a
  new pipeline); no scheduling.
- Steps are declared in trusted Python; parsing untrusted spec JSON is deferred
  (a larger validation surface).
- Multi-user LOAD still unproven (single-node local).

## Verdict
**GOVERNED MULTI-HARNESS PIPELINE STAGING READY** — real application harnesses
chain into one deterministic, fail-closed, workspace-confined, owner-scoped
workflow over the durable ledger, with independent per-step verification, honoured
approval gates, Control Center attention, and a green blocking Critical Manifest
entry. NOT production-ready (parallel DAGs, pipeline retry/resume, untrusted spec
ingestion, multi-user load remain).
