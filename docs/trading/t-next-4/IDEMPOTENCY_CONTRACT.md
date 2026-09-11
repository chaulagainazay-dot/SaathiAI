# Idempotency and Submission Contract

## The rule

> Same approved order + same idempotency key + repeated `ExecutionGateway`
> invocation **cannot** create two submitted orders.

Three independent layers enforce it. Any one of them failing does not open the
door on its own.

## Layer 1 — gateway digest (pre-existing)

`ExecutionGateway.execute_registered_tool(..., idempotency_key=...)` routes to
`UniversalBoundary._submit_locked`, which computes a digest over the intent and
refuses a duplicate under lock.

## Layer 2 — OMS intent→order identity (pre-existing)

`PaperTradingService.submit_order(intent_id=...)` is idempotent on the intent:
submitting the same intent twice returns the same `order.id` with
`idempotent_replay: true`. `PaperStore.get_order_by_idempotency(org_id, key)`
resolves an existing order for a key. Verified by `F1` and by the pre-existing
`test_idempotent_submit_same_order`.

## Layer 3 — submission attempt ledger (added by this mission)

`SubmissionAttemptStore` records every attempt durably and answers the only
question that matters before a retry: *may we submit this key again?*

### Fields per attempt

`request_id` (primary key, makes `record()` itself idempotent) ·
`client_order_id` · `idempotency_key` · `attempt` · `outcome` · `disposition` ·
`broker_adapter_ref` · `correlation_id` · `evidence_ref` · `recorded_at`

The table is append-only: attempt 1 is preserved verbatim when attempt 2 is
written (`test_attempt_history_is_append_only`).

## Disposition table

| Submission outcome | Disposition | Rationale |
|---|---|---|
| `ACKNOWLEDGED` | `DO_NOT_RETRY` | the venue has it; retrying duplicates |
| `REJECTED` | `DO_NOT_RETRY` | definitively refused |
| `TIMEOUT_BEFORE_SEND` | `SAFE_TO_RETRY` | **provably** never left the process |
| `TIMEOUT_AFTER_SEND` | `RECONCILE_FIRST` | may or may not have been received |
| `CONNECTION_LOST` | `RECONCILE_FIRST` | may or may not have been received |
| `UNKNOWN` | `RECONCILE_FIRST` | no information at all |
| *anything unrecognised* | `RECONCILE_FIRST` | fail closed |

`TIMEOUT_BEFORE_SEND` is the **only** outcome that is ever safe to retry
(`test_only_definitely_untransmitted_is_safe_to_retry` asserts the set has
exactly one member). A future adapter inventing a new outcome string cannot
accidentally unlock retry — `classify_submission` coerces the unknown case to
`RECONCILE_FIRST`.

## `may_submit()` — the fail-closed gate

```
no attempts recorded                        → True
already_submitted (ack, or recon found it)  → False
requires_reconciliation (unresolved)        → False
reconciliation recorded                     → True only if the resolved outcome is SAFE_TO_RETRY
otherwise                                   → latest attempt disposition == SAFE_TO_RETRY
```

## Escaping ambiguity

`record_reconciliation(idempotency_key, external_order_found, resolved_outcome,
evidence_ref)` is the **only** way an ambiguous attempt becomes actionable again.

- `external_order_found=True` → `already_submitted` is now True → still blocked.
  Correct: reconciliation proved the order exists at the venue.
- `external_order_found=False` with `resolved_outcome=TIMEOUT_BEFORE_SEND` →
  `may_submit` returns True. Correct: reconciliation proved nothing was sent.

There is no code path from `UNKNOWN` to an automatic retry.

## Required distinction (Phase 4 cases)

| Case | Outcome recorded | Result |
|---|---|---|
| request sent, ack received | `ACKNOWLEDGED` | DO_NOT_RETRY |
| request rejected | `REJECTED` | DO_NOT_RETRY |
| timeout before transmission | `TIMEOUT_BEFORE_SEND` | SAFE_TO_RETRY |
| timeout after possible transmission | `TIMEOUT_AFTER_SEND` | RECONCILE_FIRST |
| connection drops after acceptance | `CONNECTION_LOST` | RECONCILE_FIRST |
| duplicate callback | same `request_id` | idempotent no-op |
| duplicate retry | new attempt row | gated by `may_submit` |
| process crash during submission | attempt row survives restart | gated by `may_submit` |
