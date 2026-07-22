# M17.12 Audit — Governed Multi-Harness Pipeline

Start / rollback point: HEAD `22c2fe0` (M17.11). Branch `milestone/m7-security-engine`.
Full suite at start: 1,634 passed / 1 skipped.

## Repository truth established
- `22c2fe0` (M17.11) present in branch history; M17.11 code + tests + docs exist
  and were committed this session after full validation (34 M17.11 tests + 139
  critical checks + full suite 1,634 green).
- **Execution surface**: `service.run_harness_action(defn, op, intent, argv,
  work_dir, file_roots, owner, approved, verify_target, verify_kind)` is the SOLE
  governed entry (ownership → trust → risk/approval → the single
  `ApplicationHarnessAdapter.run` → INDEPENDENT verification → sanitized evidence).
  Returns `success | blocked | timeout | failed | uncertain | approval_required`.
- **The one adapter** (`adapter.py`) confines `work_dir` to `file_roots`, rejects
  non-argv/NUL args, resolves a trusted absolute entrypoint, and never uses a
  shell. A single harness action does NOT create a ledger `run` row (the adapter
  journal is only wired for M17.8 long-running control, not through the service).
- **Four live apps present + wrapped**: ffmpeg (media), sqlite (db), jq (json),
  zip (archive). Each pilot exposes `definition()` + `operations()` + argv
  builders + an independent verifier (`verify_db`, `verify_zip_safe`, `json_stdout`).
- **Ledger** (`run_ledger.py`): M17.9 `run` + CAS state machine, M17.10 `run_alert`,
  M17.11 `run_alert_delivery`; `_conn()` WAL + `BEGIN IMMEDIATE`; `_clean_str` /
  `_reject_secrets` sanitizers; `_event()` bus emitter; owner-safe field
  projections. QUEUED only transitions to STARTING/CANCELLED/BLOCKED/STOP_UNCERTAIN
  — so a fabricated per-step run row could not be cleanly settled; therefore the
  pipeline records steps in a dedicated table, not synthetic `run` rows.
- **Control Center** (`aggregator.py`): `harnesses()` cell + ranked `_attention()`
  already fold M17.10 alerts + M17.11 deliveries — extend with pipelines.
- **Roadmap gate**: the "AI Studio multi-harness pipeline" candidate was explicitly
  gated on "after execution reliability is proven". M17.8 (task control) + M17.9
  (durable ledger) + M17.10 (monitoring) + M17.11 (alert delivery) have now proven
  it — the gate is cleared. Higher product value than a 5th monitoring milestone.

## Why this implementation is bounded
Smallest coherent slice that makes the proven live apps composable: a
deterministic SEQUENTIAL orchestrator that reuses the governed service per step,
one confined workspace, additive ledger tables, the existing event bus, the
existing Control Center attention, and the existing admin gate. No second
execution engine (steps only run via `run_harness_action`), no new trust/risk
model, no new DB/scheduler/bus. Parallel/branching DAGs, pipeline
retry/resume/checkpoint, scheduling, and untrusted spec-JSON ingestion are
deliberately deferred.

## Design
- **Persistence** — additive `pipeline_run` (PK-unique) + `pipeline_step`
  (unique `(pipeline_id, step_index)`) in the SAME ledger DB. State machine
  `pending → running → {succeeded | failed}`; terminal immutable. Owner-safe field
  projections; free-text sanitized; secret-shaped names rejected.
- **Orchestrator** (`pipeline.py`) — `PipelineRunner.run(spec)`: create + start the
  pipeline, then for each step resolve `(defn, op)`, build a confined `StepPlan`
  from trusted Python, validate confinement, run through `run_harness_action`,
  record the step; the first non-`success` halts (fail-closed) and marks the
  pipeline failed at that step. A producing step's artifact is exposed to later
  steps by name inside the workspace.
- **Confinement** — one workspace root is the SOLE `file_roots`; reject before
  execution an absolute/`..`/escaping `produces` or `verify_target`.
- **Control Center** — owner-safe `pipelines` + `pipeline_health`; failed
  pipelines folded into attention (`kind: harness_pipeline`).
- **CLI** — `pipeline-health` (always), `pipelines` + `pipeline-inspect`
  (admin-gated, verified OS identity, owner-safe).

## Files changed
`run_ledger.py` (tables + methods + health census), `pipeline.py` (NEW),
`control_center/aggregator.py` (pipelines cell + attention), `cli.py` (+3
commands + docstring/usage), `repair/critical_checks.json` (7 blocking entries),
`tests/test_m17_12_harness_pipeline.py` (NEW), docs + roadmap/state/matrix/debt +
memory files.

## Security
Preserve all M17.9/M17.10/M17.11 controls. No second execution engine; independent
per-step verification retained; owner-scoped + owner-safe records; workspace
confinement with pre-execution escape rejection; approval gates honoured (no
silent elevation, risk 4 manual-only); argv-only (no shell); admin-gated CLI with
verified OS identity; deterministic control flow. Alert/pipeline content treated
as DATA.

## Trading Guardian boundary
Not engaged. No pipeline executes a financial action; no step triggers a trade; no
pipeline result authorizes financial execution; approval gates are strengthened,
never bypassed.

## Migration / compatibility
Additive `CREATE TABLE IF NOT EXISTS` for both tables — existing ledger DBs gain
them on next open; no destructive change. Rollback = revert the single commit
(existing DBs retain two unused tables).

## Out of scope
Parallel/branching DAGs; pipeline retry/resume/checkpoint; scheduling; untrusted
spec-JSON ingestion; a second execution engine; autonomous trading; arbitrary
user handlers; secrets in ledger/repo; new bus/DB/auth/dashboard; unrelated
refactor.

## Acceptance criteria
Live chain + artifact wiring; fail-closed short-circuit (incl. unknown /
non-executable / plan-error); workspace confinement; approval gates; shell-safety;
owner scope + owner-safe records + secret rejection; ledger invariants +
multi-process concurrency; Control Center attention; additive migration;
M17.9/M17.10/M17.11 green; dedicated blocking critical checks; full suite; clean
commit.

## Rollback
Single bounded commit on `22c2fe0`. Revert restores M17.11 exactly; the two
additive tables are left unused in existing DBs.
