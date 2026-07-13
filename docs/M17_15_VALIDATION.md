# M17.15 Validation — Governed Pipeline Retry, Resume & Checkpoints

Start/rollback point: HEAD `4cad92a` (M17.14). Branch `milestone/m7-security-engine`.
Verdict: **GOVERNED PIPELINE RETRY / RESUME / CHECKPOINT STAGING READY** (not
production).

## What was built
Deterministic, durable, approval-safe pipeline recovery: a failed/interrupted
pipeline continues from its last independently-verified step instead of restarting.
Implemented inside/around the existing `PipelineRunner` + ledger — no second engine,
retry framework, verification path, or ledger.

### Deliverables
- Ledger: additive `pipeline_checkpoint` + `pipeline_recovery` tables + owner-safe
  methods + governed `reopen_pipeline`; `health()` extended (`checkpoints`,
  `recoveries`).
- `pipeline.py`: checkpoint written after each verified success; deterministic
  fingerprints; `execute_resume` (same governed loop from a start index with seeded
  reused artifacts).
- `pipeline_recovery.py` (NEW): `PipelineRecovery` coordinator + `RETRYABLE_CATEGORIES`.
- Control Center: owner-safe recovery cell + attention (retry exhausted,
  stop_uncertain, invalid checkpoint, artifact mismatch).
- CLI: `pipeline-recovery-health` (always) + 7 admin-gated owner-safe commands.
- Ops: 9 blocking `pipeline_recovery.*` critical-manifest checks.
- Tests: `tests/test_m17_15_pipeline_recovery.py` (35).

## Evidence
- New tests: **35 passed**.
- 9 `pipeline_recovery.*` manifest checks: **ALL GREEN** via the real runner.
- Harness-lineage + CC regression (m17_15…m17_9, m17_3, m16): **249 passed**.
- Full suite: **1771 passed / 1 skipped / 0 failed** (+35 over the 1736 baseline).
- Release gate: exit 0 (database_ok / backup_ok / restore_verified true).
- Backup/restore: dedicated test proves checkpoints + recoveries survive a sqlite
  online backup with `integrity_check == ok`.
- `git diff --check` clean; secret scan over changed files: 0 real matches.
- Live CLI: `pipeline-recovery-health` with no admin; `pipeline-resume` /
  `pipeline-checkpoints` return rc 3 without `SAATHI_HARNESS_ADMIN=1`.

## Security properties proven (deterministic)
- **Checkpoint integrity**: only verified success writes a checkpoint; missing /
  modified / path-escaping artifacts invalidate reuse; fingerprints stable across
  restart.
- **Contiguous prefix**: reuse only the valid verified prefix; a changed step
  definition / dependency / verification policy stops reuse; the first invalid step
  and all later steps rerun; already-verified steps do not rerun.
- **Retry policy**: category-allowlisted, bounded, deterministic backoff, terminal
  exhaustion; unknown / approval / owner / verification failures never auto-retry.
- **Approval & ownership**: increased risk invalidates checkpoint reuse; resume
  stops closed at approval_required; owner mismatch executes nothing; no elevation.
- **Concurrency / crash**: one recovery claimant; active lease not stealable; expired
  reclaimable; reconcile avoids duplicate execution; uncertain fails closed.
- **Delegation only**: static assertion — no run_harness_action/adapter/subprocess
  in the recovery module; recovery re-enters `PipelineRunner.execute_resume`.
- **Mission integration**: a mission's failed pipeline resumes in place with no
  duplicate mission; owner preserved.
- **Trading Guardian**: not engaged; recovery module has no trading surface (asserted).

## Live proof
`sqlite safe_mutation → data.db` (verified, checkpoint stored) then `zip pack` with a
controlled transient failure: pipeline fails → recovery `retry_wait` → advance
injected clock → retry reuses step1 (not rerun), step1 artifact revalidated, step2
runs through `run_harness_action`, independently verified, pipeline succeeds; the
resumed run links to the original (same pid); a duplicate resume is refused
(`recovery_claimed`); reconcile after a simulated crash re-settles without duplicate
work. Separately: modifying `data.db` invalidates the checkpoint (`missing_artifact`
/ integrity) and resume then reruns from step 1; no later checkpoint is reused after
an invalid earlier step.

## Deferred (documented, not pretended)
Parallel/branching DAGs; distributed/remote/cloud checkpoints; arbitrary user-authored
pipeline JSON; automatic recovery of untrusted steps; cross-owner checkpoint reuse;
production auto-scheduling; external transports; multi-region execution.
