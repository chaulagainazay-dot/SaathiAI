# Fill Ingestion Contract

## Schema (`PaperFill`, `paper_trading/models.py`)

`id` · `paper_order_id` · `org_id` · `event_ts` · `quantity` · `price` ·
`gross_amount` · `fee` · `slippage` · `side` · `liquidity_ref` ·
`market_data_ref` · `fee_model_version` · `slippage_model_version`

Fee and slippage carry **model versions**, so a fill is reproducible against the
exact pricing rules in force when it happened. `fill_result_hash` gives a
deterministic digest of a fill outcome.

## Guarantees

| Requirement | Mechanism | Test |
|---|---|---|
| Duplicate fill ingestion is idempotent | `PaperStore.event_processed(order_id, event_hash)` deduplicates on the market event hash before any fill is written | `F6` |
| Ledger changes once for a duplicated fill | `post_accepted_fill` short-circuits on a prior `POSTED`/`DUPLICATE` record for the same `fill_id` | `F6`, `F10` |
| Partial fill updates remaining quantity | `PaperOrder.filled_quantity` accumulates; `remaining_quantity` is derived, never stored independently | pre-existing partial-fill suite |
| Final fill closes the order only at full quantity | broker transitions to `FILLED` only when `remaining_quantity == 0` | `F20b` |
| **Overfill fails closed** | `filled_quantity` can never exceed `original_quantity`; `ReconciliationAuthority` flags any observed overfill as `MISMATCH` | `F20`, `F20b` |
| Out-of-order fills handled deterministically | fills are keyed by event hash, not by arrival order; a stale replayed event is a dedup no-op and cannot reduce or inflate filled quantity | `F7` |
| Unknown order fill requires reconciliation | an external fill whose `order_id` is unknown to the OMS is a `MISMATCH` finding and blocks execution | `F19` |

## Overfill is treated as a contradiction, not a value

An overfill means the OMS and the venue disagree about reality. The system does
not attempt to absorb it into the ledger. It surfaces as `MISMATCH`, execution
readiness is denied, and a human resolves it. That is the correct behaviour for
an accounting system: refusing to record an impossible state is better than
recording it and reconciling later.

## Ordering

Fills are idempotent on event hash rather than ordered by sequence number,
because the paper venue is deterministic and replay-safe. A real venue with a
monotonic sequence number should additionally reject a fill whose sequence
precedes the highest applied sequence for that order. That is recorded in
`LIMITATIONS.md` as work required before a shadow adapter carries real fills.
