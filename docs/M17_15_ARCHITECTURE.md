# M17.15 Architecture — Governed Pipeline Retry, Resume & Checkpoints

## Position in the stack
Recovery lives IMMEDIATELY AROUND the existing `PipelineRunner`. It adds no second
pipeline/execution engine, retry framework, verification path, or ledger. The
execution hierarchy is unchanged:

```
Mission / Scheduler → MissionEngine → PipelineRunner → run_harness_action →
Adapter → independent verification → durable ledger
```

Recovery only decides WHICH already-verified steps may be reused, reopens the failed
pipeline, and hands the remaining steps back to the SAME `PipelineRunner`
(`execute_resume`). Static test asserts `pipeline_recovery.py` references no
`run_harness_action`, adapter, `subprocess`, `Popen`, or `os.system` — the only
downward call is `PipelineRunner.execute_resume`.

## Components (additive)
- `run_ledger.py` — two additive tables (`pipeline_checkpoint`,
  `pipeline_recovery`) + owner-safe methods + a governed `reopen_pipeline`.
- `pipeline.py` — writes a durable checkpoint after each SUCCESS+verified step;
  fingerprint helpers (`step_fingerprint`, `dependency_fingerprint`,
  `file_fingerprint`); `execute_resume` runs from a start index with seeded reused
  artifacts (identical governed loop).
- `pipeline_recovery.py` — NEW `PipelineRecovery` coordinator (checkpoint
  validation, contiguous-prefix computation, resume, retry, reconcile, health) +
  the `RETRYABLE_CATEGORIES` allowlist.
- `control_center/aggregator.py` — owner-safe recovery cell + attention.
- `cli.py` — `pipeline-recovery-health` (always) + 7 admin-gated owner-safe commands.

## Checkpoint model
`pipeline_checkpoint` (UNIQUE per `pipeline_id, step_index`): checkpoint_id,
pipeline_id, owner, step_index, step_name, step_fingerprint,
dependency_fingerprint, input_fingerprint, artifact, artifact_fingerprint,
verify_kind, verification_result, status, version, created_at, invalidated_at,
invalidation_reason. Status ∈ {valid, invalid, superseded, missing_artifact,
verification_failed}. A checkpoint is written ONLY where a step returns SUCCESS —
which, in the governed service, means it was already independently verified
(blocked/failed/uncertain/approval_required never reach that branch).

## Pipeline-run / recovery model
`pipeline_recovery` (one row per pipeline_id): owner, attempt, max_attempts,
next_retry_at, retry_reason, failure_category, reused_steps, rerun_steps,
claim_owner, lease_expires_at, state ∈ {retry_wait, resuming, exhausted, recovered,
stop_uncertain}. The existing `pipeline_run` / `pipeline_step` records are
preserved; a resumed run reuses the SAME `pipeline_id` and confined workspace (so
verified artifacts are exactly the ones on disk), and the recovery row records
reused vs rerun counts and attempts. `reopen_pipeline` is the ONE governed, audited,
attempt-bounded exception to pipeline terminal immutability (`complete_pipeline`
stays immutable for normal runs).

## Fingerprinting
Deterministic, canonical JSON, sha256-truncated; never hashes raw secrets.
- **step_fingerprint** = harness/operation identity + workspace-normalized argv +
  produced artifact + verify_kind + verify_target + approved + risk + approval
  requirement. Cosmetic fields don't enter it; an execution-affecting change does.
- **dependency_fingerprint** = ordered prior step names + their artifact
  fingerprints (a changed/missing upstream artifact changes it).
- **input_fingerprint** = the dependency fingerprint (conservative).
- **artifact_fingerprint** = sha256 of the produced file bytes.
Stable across process restarts (pure functions of durable inputs).

## Checkpoint validation (fail closed on ANY mismatch)
owner matches · step identity (name) matches · step_fingerprint matches ·
dependency_fingerprint matches · verify_kind matches · verification_result true ·
artifact exists · artifact realpath inside the workspace · artifact_fingerprint
matches · status == valid. A previously-valid checkpoint that no longer holds is
invalidated with the specific reason/status.

## Resume behaviour
`resume(spec, owner)`: owner check → eligibility (pipeline failed) → seed a recovery
record if absent → claim recovery lease (one winner) → compute the longest
CONTIGUOUS valid verified prefix → reopen the pipeline → `execute_resume` from the
first non-reusable step, seeding reused artifacts. Reused steps do NOT re-execute;
the first invalid/missing/changed step and every later step rerun through
`run_harness_action` with independent verification and new checkpoints. Fail-closed
at the first non-success. `force_restart=True` invalidates all checkpoints and
reruns from step 0.

## Retry eligibility & policy
Auto-retry only for the `RETRYABLE_CATEGORIES` allowlist (timeout / transient lock /
fs contention / adapter timeout / resource unavailable / interrupted). Everything
else — approval_required, owner mismatch, verification failure, invalid params, path
escape, secret policy, manual-only, cancellation, tamper, fingerprint mismatch,
unknown/non-executable harness — does NOT auto-retry. Unknown categories do not
retry. Bounded deterministic backoff reuses the shared `RETRY_SCHEDULE`
`[0,60,300,900,3600]`s → `exhausted`. Injectable clock; no real sleeps.

## Crash reconciliation
`reconcile()` scans stale recovery leases: if the pipeline is now `succeeded` →
`recovered`; otherwise re-enable as `retry_wait` (execution status uncertain → never
assume success). The deterministic step-and-checkpoint model means a re-attempt
reuses the verified prefix and reruns idempotently — no duplicate execution. An
uncertain step outcome (`HARNESS_VERIFICATION_FAILED`) sets recovery `stop_uncertain`
and is not auto-retried.

## Approval & risk safety
Risk and approval requirement are part of `step_fingerprint`, so an increased risk
(or changed approval scope) makes the prior checkpoint non-reusable → the step
reruns and stops at `approval_required` if not approved. Resume/retry never imply
approval; risk-4 stays manual-only via the unchanged `run_harness_action`. An
operator may INVALIDATE a checkpoint but can never mark one valid (no force-success).

## Trading Guardian boundary
Not engaged. `pipeline_recovery.py` contains no trading/withdraw/leverage/order/
broker surface (asserted). Recovery adds no execution path, so it cannot retry or
resume any trading action.
