# Failure Injection Matrix (Phase 14)

All scenarios in `tests/execution_integrity/test_failure_matrix.py`. Each asserts
a terminal behaviour, not merely absence of an exception.

| ID | Scenario | Expected terminal behaviour | Result |
|---|---|---|---|
| F1 | Duplicate submit, same intent | one order; second call returns the same `order.id` | **PASS** |
| F1b | Duplicate submit after `ACKNOWLEDGED` | `may_submit` = False | **PASS** |
| F2 | Timeout before send | `SAFE_TO_RETRY`; `may_submit` = True | **PASS** |
| F3 | Timeout after possible send | `may_submit` = False; `requires_reconciliation` = True | **PASS** |
| F4 | Process crash after submit | order reloads from durable store; resubmit returns the same order; nothing disappears | **PASS** |
| F5 | Duplicate acknowledgement | idempotent on `request_id`; one attempt row | **PASS** |
| F6 | Duplicate fill (same market event replayed) | fills unchanged, positions unchanged — ledger moves once | **PASS** |
| F7 | Out-of-order (stale) fill event | filled quantity never decreases and never exceeds original | **PASS** |
| F8 | Cancel after full fill | `FILLED` is terminal; cannot transition to `CANCELLED` or `OPEN` | **PASS** |
| F9 | Illegal state resurrection (6 forbidden pairs) | every pair refused by `can_broker_transition` | **PASS** |
| F10 | Ledger write failure | `POST_FAILED` + `portfolio_status = RECONCILIATION_REQUIRED`; fill not erased | **PASS** |
| F11 | Reconciliation mismatch | `MISMATCH`; `permits_new_execution` = False | **PASS** |
| F12 | Stale market data | submission refused before any order is created | **PASS** |
| F12b | Zero / negative price | submission refused — **defect found and fixed by this mission** | **PASS** (after fix) |
| F13 | Unknown / invalid approval id supplied | submission refused — **defect found and fixed by this mission** | **PASS** (after fix) |
| F14 | Unknown / expired intent | no order can be produced | **PASS** |
| F17 | Kill switch (account halted) | new orders refused | **PASS** |
| F18 | Corrupted / ambiguous persisted state | `UNKNOWN`; execution blocked | **PASS** |
| F19 | Unknown external order | `MISMATCH`; execution blocked | **PASS** |
| F20 | Overfill observed in reconciliation | `MISMATCH`; execution blocked | **PASS** |
| F20b | Repeated fill events on one order | filled quantity never exceeds original quantity | **PASS** |

## Coverage gaps, stated plainly

Three scenarios from the brief are **covered by construction rather than by an
injected failure**, and are recorded here rather than claimed as tested:

- **F15 — Trading Guardian flips allow → block between approval and execution.**
  The guardian is evaluated server-side inside `submit_order`, atomically with
  the order write, so there is no window between the guardian decision and the
  order write in which the verdict could change. The scenario is therefore not
  reachable in the current design. It becomes reachable — and must be tested —
  the moment guardian evaluation is cached or moved out of the write transaction.
- **F16 — risk budget breach between approval and execution.** Same argument.
  Risk reservation happens inside the same transaction as the order write.
- **F9 (fill during cancel)** is covered at the state-machine level
  (`CANCEL_PENDING → FILLED` is deliberately legal) but not as a concurrent
  race, because the paper venue is single-threaded and deterministic.

These three are listed in `LIMITATIONS.md` as prerequisites for shadow execution
against a real venue, where concurrency and caching make all three reachable.

## Defects found by this matrix

Writing the failure tests before the fixes was the point: two real fail-open
defects in the deterministic plane were found, both in the pre-submission path.

1. **D1 (F12b)** — an order could be admitted and cash reserved against a
   non-positive reference price.
2. **D2 (F13)** — a supplied-but-invalid `approval_id` was silently ignored when
   the order did not independently require approval.

Both fixed; full trading regression unchanged (258 passing before and after).
