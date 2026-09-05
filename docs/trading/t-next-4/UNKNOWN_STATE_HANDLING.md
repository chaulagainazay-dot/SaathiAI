# UNKNOWN as a First-Class Unsafe State

The brief's central requirement: *UNKNOWN must be treated as a first-class unsafe
state.* This document records exactly where UNKNOWN can arise and what happens.

## Where UNKNOWN can arise

| Origin | Representation | Consequence |
|---|---|---|
| A submission attempt with no information | `SubmissionOutcome.UNKNOWN` | `RETRY: RECONCILE_FIRST`; `may_submit` = False |
| A submission that may or may not have been transmitted | `TIMEOUT_AFTER_SEND`, `CONNECTION_LOST` | same as above |
| An adapter returning an outcome string we do not recognise | coerced to `RECONCILE_FIRST` | `may_submit` = False |
| A persisted order whose state is `UNKNOWN` or `RECONCILIATION_REQUIRED` | `ExecutionReadiness.UNKNOWN` | `permits_new_execution` = False |
| An external snapshot we could not obtain | `ExecutionReadiness.DATA_INSUFFICIENT` | `permits_new_execution` = False |
| Expected cash or positions not supplied | `ExecutionReadiness.DATA_INSUFFICIENT` | `permits_new_execution` = False |
| A ledger posting that raised | `portfolio_status = RECONCILIATION_REQUIRED` | fill preserved, posting retried, execution readiness denied |

## The three rules

**1. UNKNOWN never auto-retries.**
`classify_submission` maps every ambiguous or unrecognised outcome to
`RECONCILE_FIRST`. `may_submit` returns False for any unresolved
`RECONCILE_FIRST`. There is no code path from UNKNOWN to an automatic retry.
Asserted by `test_unknown_is_never_safe_to_retry`,
`test_no_ambiguous_outcome_is_ever_safe_to_retry`, `F3`, `F18`.

**2. UNKNOWN never permits execution.**
`readiness_permits` returns True only for `RECONCILED`. `UNKNOWN`,
`MISMATCH`, and `DATA_INSUFFICIENT` return False even when
`allow_execution_while_pending=True` — the permissive flag only ever affects
`TEMPORARILY_PENDING`. Asserted exhaustively by
`test_no_readiness_other_than_reconciled_permits_execution`.

**3. UNKNOWN is escaped only by explicit reconciliation.**
`record_reconciliation` is the sole exit, and it unblocks resubmission **only**
when reconciliation proved no external order exists *and* the resolved outcome is
`SAFE_TO_RETRY`. If reconciliation finds the order at the venue, the key stays
blocked and `already_submitted` becomes True. Asserted by
`test_reconciliation_clearance_unblocks_only_when_not_transmitted` and
`test_reconciliation_finding_external_order_keeps_submission_blocked`.

## Why the unrecognised-value case matters

```python
def classify_submission(outcome):
    try:
        key = outcome if isinstance(outcome, SubmissionOutcome) else SubmissionOutcome(outcome)
    except (ValueError, KeyError, TypeError):
        return RetryDisposition.RECONCILE_FIRST
    return _DISPOSITION.get(key, RetryDisposition.RECONCILE_FIRST)
```

A future adapter — particularly a real broker adapter — will eventually return an
outcome this code has never seen. The default must be "stop", not "retry". Both
the exception path and the dictionary lookup default to `RECONCILE_FIRST`, and
`test_unrecognised_outcome_fails_closed` pins it with `""`, `"MAYBE"`, `"OK"`,
`None`, `0`, and a bare `object()`.

This is the single most important line in the module. A system that treats an
unfamiliar response as retryable will eventually double-submit real capital.
