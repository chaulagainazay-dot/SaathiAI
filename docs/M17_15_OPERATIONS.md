# M17.15 Operations — Pipeline Retry, Resume & Checkpoints

## Mental model
Recovery continues a failed pipeline through the SAME governed pipeline — it does not
create a second execution path. Verified steps become durable checkpoints; a
resume/retry reuses only the contiguous valid verified prefix and reruns the rest
through `run_harness_action` with independent verification. Approvals, ownership,
confinement, and verification behave exactly as for a fresh run.

## CLI (verified local OS operator; mutations audited via the event bus)
Always available (aggregate census, no secrets):
```
python -m saathi.application_harness.cli pipeline-recovery-health
```
Admin-gated (`SAATHI_HARNESS_ADMIN=1`), owner-safe output:
```
pipeline-checkpoints <pipeline_id>                 # per-step checkpoints (owner-safe)
pipeline-checkpoint-inspect <pipeline_id> <step_index>
pipeline-recovery-history                          # recent recovery records
pipeline-recovery-reconcile                        # settle stale recovery claims only
pipeline-invalidate-checkpoint <pipeline_id> <step_index>   # operator may INVALIDATE
pipeline-resume <pipeline_id>                      # operator-explicit resume
pipeline-retry  <pipeline_id>                      # policy retry (category + backoff)
```
`pipeline-resume` / `pipeline-retry` rebuild the trusted step plan from the pipeline's
owning MISSION template (no arbitrary user-authored spec); they fall closed
(`spec_unavailable`) for a pipeline not produced by a known mission template. There is
NO command to force a checkpoint valid or force a pipeline to success.

## Reading Control Center
The owner-safe recovery cell exposes recovery records, recovery health, and invalid
checkpoints. Attention items (owner-scoped): retry exhausted (high), STOP_UNCERTAIN
(high), missing-artifact checkpoint (high), other invalidated checkpoint (medium). No
raw commands, file contents, secrets, sensitive parameters, or cross-owner records
are shown.

## When does a verified step get reused vs rerun?
Reused only while ALL hold: owner matches, step-definition fingerprint matches,
dependency fingerprint matches, verification policy matches, verification passed, the
artifact exists inside the workspace, and its integrity fingerprint matches. Any
mismatch invalidates the checkpoint and reruns the producing step (and everything
after it). See `M17_15_RECOVERY_SEMANTICS.md`.

## Retry vs resume
- `pipeline-resume` — operator continuation of any eligible failed pipeline.
- `pipeline-retry` — only for an allowlisted transient/infrastructure failure
  category, after the deterministic backoff (`[0,60,300,900,3600]`s), within the
  bounded attempt count. Otherwise `not_retryable` / `backoff_wait` / `retry_exhausted`.

## Crash recovery
`pipeline-recovery-reconcile` settles stale recovery leases: a now-succeeded pipeline
is marked recovered; anything uncertain is re-enabled as `retry_wait` — never assumed
successful. Deterministic checkpoints mean a re-attempt reuses the verified prefix
without duplicate execution.

## Safety invariants (do not weaken)
No shell/adapter/second-execution path; no approval elevation on resume/retry; no
owner substitution; no cross-owner checkpoint reuse; no reuse of a missing/tampered
artifact; no unbounded retry; no active-lease stealing; no terminal mutation beyond
the governed bounded `reopen`; no force-valid / force-success command. Trading
Guardian stays disabled; recovery adds no trading surface.
