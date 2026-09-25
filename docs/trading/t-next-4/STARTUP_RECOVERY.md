# Startup Recovery

## Durability model

All order lifecycle state lives in SQLite (`PaperStore`, `db_path`). Nothing
material is held only in memory. A restart is modelled as constructing a new
`PaperTradingService` over the same database file — which is exactly what
happens in production, and exactly what the tests do.

Submission attempts live in a second durable store
(`SubmissionAttemptStore`, its own SQLite file), so the record of *how a
submission ended* survives independently of the order record. This matters: the
order row alone cannot tell you whether an ambiguous submission was ever
transmitted.

## Behaviour at each critical stage

| Restart point | Recovered state | Guarantee |
|---|---|---|
| Before submission | intent persisted, no order | resubmission proceeds normally |
| During submission | attempt row may or may not exist | if absent → clean retry; if present with `TIMEOUT_BEFORE_SEND` → `SAFE_TO_RETRY`; anything else → `may_submit` = False |
| After submission, before ack | attempt row with `TIMEOUT_AFTER_SEND` / `UNKNOWN` | **blocked**; routes to reconciliation. Never retried blindly |
| After ack | attempt row `ACKNOWLEDGED`; order durable | `already_submitted` = True; resubmission refused |
| During partial fill | order with `filled_quantity` and `PARTIALLY_FILLED` | fills replay idempotently on event hash; no double-count |
| After fill, before ledger posting | fill durable; `FillPostingStore` row `PENDING` or absent | `retry_pending_posts` drains it; the fill is never lost |
| After ledger posting, before reconciliation | ledger event durable with `ledger_event_id` | re-posting short-circuits as idempotent |

## Tested

`F4` (`test_F4_crash_after_submit_reloads_order_and_never_resubmits`) constructs
a brand-new `PaperTradingService` over the same database and asserts:

1. the order is recovered by id — **no order may disappear**;
2. resubmitting the same intent returns the **same** order id — **restart must
   not create a second order**.

`test_attempt_is_persisted_durably` reopens `SubmissionAttemptStore` from disk
and asserts the attempt and its disposition survive.

The pre-existing suite additionally covers restart persistence of accounts,
positions, and the ledger (`test_m200_m207_durable_paper.py`,
`test_t_next_1_1_ledger_cutover.py`).

## The four invariants required by the brief

1. **OMS reloads durable state** — SQLite; verified by `F4`.
2. **No order may disappear** — asserted directly by `F4`.
3. **No filled order may be resubmitted** — intent→order identity plus
   `already_submitted`; asserted by `F1`, `F1b`, `F4`.
4. **No ambiguous submission may be retried blindly; UNKNOWN routes to
   reconciliation** — `may_submit` returns False for every
   `RECONCILE_FIRST` disposition, and the only escape is an explicit
   `record_reconciliation`; asserted by `F3`, `F18`, and
   `test_unknown_outcome_blocks_and_requires_reconciliation`.

## Gap

There is no automatic startup sweep that enumerates unresolved ambiguous
attempts and raises them for operator attention. Today the block is enforced
lazily — at the moment someone tries to submit that key again. That is
fail-closed and therefore safe, but it is not proactive. Recorded in
`LIMITATIONS.md`.
