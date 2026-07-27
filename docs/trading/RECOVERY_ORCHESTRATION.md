# Recovery Orchestration (M62.6)

Recovery in the paper-trading platform is **deterministic replay + reconciliation**,
never mutation. There is no "repair on startup" path. Integrity after any
interruption is *proven*, not assumed.

## Principle

The immutable event record (`starting_cash` + `paper_fills` + open-order
reservations) is the source of truth. Persisted account/position/ledger rows are a
*projection* of those events. Recovery recomputes the projection from the events
and confirms the persisted projection matches. If it does not, drift is classified
and (if CRITICAL) the account is halted — the state is **never silently rewritten**.

`recover_account(ctx, account_id)`:

1. `recompute_expected()` — pure replay of immutable events (deterministic).
2. `reconcile_account()` — compare expected vs persisted across all 7 dimensions.
3. Record a `recovery_scan` event with the run id and an `expected_hash`.
4. Return `{expected_state, reconciliation, deterministic: True, silent_repair: False}`.

## Recovery scenarios (all fail-closed)

| Scenario | Mechanism | Outcome | Test |
|---|---|---|---|
| Runtime restart | store reopened on same DB; replay from fills | clean, deterministic | `test_recovery_after_restart_is_clean` |
| Mid-transaction interruption | `persist_*` are single atomic transactions; failed approval consume rolls back fully | no partial state; reconciles clean | `test_interrupted_transaction_leaves_no_partial_state` |
| Duplicate market events | `paper_processed_events` dedup; fill applied once | no double count; recovery idempotent | `test_duplicate_recovery_no_double_count` |
| Duplicate submissions | unique `idempotency_key`; one order | reconciles clean | (M62.5 + recon clean) |
| Duplicate recovery | `recover_account` is read-only replay | identical expected_state on re-run | `test_duplicate_recovery_no_double_count` |
| SQLite interruption | one-transaction writes; partial writes rolled back by SQLite | no partial mutation; reconciles clean | `test_interrupted_transaction_leaves_no_partial_state` |
| Corrupted replay input (tampered fill) | recompute-from-fills diverges from persisted | CRITICAL → account halted | `test_corrupted_fill_detected_and_halts` |
| Replay ordering | deterministic `(created_at, order_id, seq)` ordering | identical recompute | `test_replay_recompute_is_deterministic` |
| Reservation corruption | reserved recomputed from open orders | ERROR (mismatch) / CRITICAL (reserved>cash) | `test_reservation_corruption_error`, `test_reserved_exceeds_cash_is_critical` |
| Ledger corruption | ledger is derived; cash cross-checked against fills | ERROR (ledger only), CRITICAL if cash diverges | `test_ledger_corruption_is_error` |
| Position corruption | position vs signed Σ fills | CRITICAL → halted | `test_position_corruption_is_critical_and_halts` |

## Determinism guarantees

- `recompute_expected()` has no wall-clock, no RNG, and a fixed replay order → the
  same DB always yields the same expected state and the same `expected_hash`.
- Reconciliation report bodies hash `(expected, persisted, findings)`; only the
  `run_id`/`ts` differ between runs, so a clean account produces a stable finding set.

## What recovery never does

- Never writes to `paper_fills`, `paper_orders`, `paper_positions`, or
  `paper_ledger`.
- Never adjusts cash, reservations, or positions to "fix" a mismatch.
- The only write is the protective `ACTIVE → HALTED` transition on CRITICAL drift,
  plus append-only recovery-event and reconciliation-report records.
