# M17.15 Recovery Semantics

## The guarantee, in one sentence
A failed or interrupted pipeline continues from its last INDEPENDENTLY VERIFIED
successful step — reusing prior work only while it is provably unchanged and intact,
and rerunning everything from the first step that is not.

## Before / after
Before: step1 ✓, step2 ✓, step3 ✗ → rerun the WHOLE pipeline.
After: step1 and step2 stay trusted (verified checkpoints); step3 is retried under a
bounded governed policy; the pipeline resumes from step3; later steps run only after
step3 succeeds and is independently verified.

## Contiguous-prefix rule
Only the longest CONTIGUOUS prefix of valid verified checkpoints is reused. Reuse
stops at the first step that is invalid, missing, changed, or unverified — and NO
later checkpoint is reused even if it looks valid. (You cannot skip a broken middle
step and reuse a downstream one.)

## When an already-verified step MUST rerun
- its artifact is missing;
- its artifact integrity fingerprint no longer matches (tamper/modification);
- its verification evidence is invalid;
- its dependency fingerprint changed (an upstream artifact changed);
- its step-definition fingerprint changed (argv/produces/verify policy/risk/approval);
- an explicit operator-approved full restart is requested (`force_restart`).

## Retry vs resume
- **Resume** — operator-explicit continuation of an eligible failed pipeline; reuses
  the valid prefix, reruns the rest, honours approval.
- **Retry** — the same continuation but POLICY-gated: allowed only for an allowlisted
  transient/infrastructure `failure_category`, only after the deterministic backoff
  has elapsed, and only within the bounded attempt count; otherwise rejected
  (`not_retryable` / `backoff_wait` / `retry_exhausted`).

## Failure-category handling
| category | auto-retry? | outcome |
|---|---|---|
| timeout / transient_lock / fs_contention / adapter_timeout / resource_unavailable / interrupted | yes | retry_wait → (recovered \| exhausted) |
| approval_required | no | stays failed; resume stops closed at approval |
| owner mismatch | no | rejected before execution |
| verification failure / uncertain | no | recovery `stop_uncertain` (manual review) |
| invalid params / path escape / secret policy / manual-only | no | terminal |
| artifact tamper / fingerprint mismatch | no | checkpoint invalidated; producing step reruns |
| cancellation | no | terminal |
| unknown / non-executable harness | no | terminal |
| unknown category | no | not auto-retried (fail closed) |

## Crash windows (reconcile, don't duplicate)
- crash before retry claim → still dispatchable/resumable;
- crash after retry claim (stale lease) → reconcile re-enables retry_wait;
- crash before step execution → reused prefix recomputed, step reruns;
- crash during adapter execution → step outcome uncertain → not assumed success;
- crash after adapter result but before verification persistence → step reruns
  (only a verified success writes a checkpoint);
- crash after verification but before checkpoint persistence → step reruns (no
  checkpoint = not reusable);
- crash after checkpoint persistence but before step terminal update → checkpoint is
  valid and reused;
- crash after final step success but before pipeline terminal update → reconcile
  finalizes from the pipeline/checkpoint state.
Where a step cannot be proven safe to reuse OR safe to rerun, recovery records
`stop_uncertain` rather than fabricating completion.

## Concurrency
Recovery is lease-claimed: exactly one resumer/retrier wins; an active lease is not
stealable; an expired lease is reclaimable. Concurrent resume/retry requests produce
a single resumed run.

## Approval & risk
Approval is never implied by resume/retry. A step that required approval reruns and
stops at `approval_required` unless a still-valid, same-scope approval applies (the
risk and approval requirement are inside the step fingerprint, so any increase
invalidates reuse). Risk-4 remains manual-only.
