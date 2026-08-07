# Paper Accounting & Reservations (M62.5)

Decimal throughout (`decimal.Decimal`, never binary float). No margin, no borrowed
cash, no short positions.

## Account

`PaperAccount`: `starting_cash` (must be positive) · `current_cash` · `reserved_cash`
· `available_cash = current_cash − reserved_cash` · `realized_pnl` · status
(`DRAFT → ACTIVE → HALTED/CLOSED`) · environment (`PAPER`) · `version`.

`PaperPosition`: `quantity` · `reserved_quantity` ·
`available_quantity = quantity − reserved_quantity` · `avg_cost` · `realized_pnl`.

## Cash reservation (BUY)

At submit the broker reserves `notional + estimated fee + bounded slippage reserve`
(`PaperBroker.reserve_for_buy`). `available_cash` drops; `current_cash` is unchanged
until a fill. On each fill: actual `gross + fee` is deducted from `current_cash` and
a proportional slice of the reservation is released; on completion/cancel any
residual reservation is released in full. Reservation can never drive
`available_cash` negative, and duplicate submissions never double-reserve
(unique idempotency key).

## Position reservation (SELL)

A SELL reserves `available_quantity` up front (long-only — a SELL may never exceed
the available long position; oversell is rejected before any write). On fill the
reserved quantity and position quantity both decrease; on cancel the unfilled
reserved quantity is released.

## Fills

Each `PaperFill` is immutable and append-only, recording quantity, price,
gross amount, fee, per-unit slippage, fee-model version, slippage-model version,
market-data reference, sequence, and `result_hash`. Sum of fills can never exceed
order quantity; a duplicate market event produces no duplicate fill (dedup by
`(order, event_hash)`).

## Invariants (`check_account_invariants`, asserted by tests)

```
available_cash  = current_cash − reserved_cash
available_qty   = position_quantity − reserved_quantity
position_qty    = Σ BUY fills − Σ SELL fills          (long-only, ≥ 0)
available_cash ≥ 0 · reserved_cash ≥ 0 · reserved_quantity ≥ 0
fills reconcile to order filled quantity
orders reconcile to the account ledger
```

## Transaction boundaries (atomic, single SQLite transaction each)

- **Submission** — approval consumption + reservation + order creation + intent
  state + transition + ledger + idempotency record. Any failure rolls back the whole
  set (`test_atomic_rollback_on_approval_failure`): no order, no reservation.
- **Fill** — event dedup + fill insert + order update + reservation update + cash
  ledger + position + P&L + transition.
- **Cancellation** — state validation + state update + reservation release + ledger.

## Fees & slippage (versioned)

`FeeModel` (fixed / pct / per-unit / minimum) and `SlippageModel` (bps /
spread-aware / participation cap) are versioned; every fill persists the model
versions and the resulting fee and slippage. Costs are always reflected in account
P&L — never hidden. Named tiers: `ZERO_FEE`/`REALISTIC_FEE`,
`ZERO_SLIP`/`REALISTIC_SLIP`.
