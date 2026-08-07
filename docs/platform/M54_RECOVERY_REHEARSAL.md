# M54 Recovery Rehearsal

Deterministic single-host restart and race drills. All guarantees are
**single-host SQLite** guarantees; M54 makes no distributed-consensus or
exactly-once claim.

Backend drills live in `tests/test_m54_readiness.py` and reuse the M53 runtime.

## Restart while waiting for approval
Execution enters `WAITING_APPROVAL`; a brand-new `PlatformService` over the same
SQLite file still sees the execution, the attention queue still reports
`APPROVAL_REQUIRED`, the approval can be decided, and resume returns through
`PlatformAgentRuntime` exactly once.
Covered by `test_restart_preserves_waiting_execution_and_allows_single_resume`.

## Restart before dispatch
An execution with no recorded dispatch is eligible for safe resume; after
restart the state reconciles and `RESUME` returns through the runtime with no
duplicate dispatch.

## Restart after dispatch recorded
An execution with `dispatch_started=True` that becomes `PAUSED` is classified
`DISPATCH_OUTCOME_UNCERTAIN` in the attention queue; a `RESUME` reconciliation is
rejected with `DISPATCH_OUTCOME_UNCERTAIN` — automatic replay is forbidden;
operators may only use allowed terminal actions.
Covered by `test_restart_after_recorded_dispatch_cannot_replay`.

## Cancellation race
Cancellation and progression overlap; terminal state remains immutable and no
duplicate terminal transition occurs (M53 CAS transition guard).

## Approval expiry race
An approval that expires near resume is rejected; the execution does not
dispatch.

## Binding lifecycle race
A binding suspended or revoked while an execution is queued invalidates the
stale execution context (`CONTEXT_INVALIDATED` / `BINDING_SUSPENDED` /
`BINDING_REVOKED`); no dispatch occurs under an invalid binding state.

## Limitations
Single-host only. A recorded-but-uncertain dispatch always requires manual
operator resolution and is never resumed or replayed by the platform.
