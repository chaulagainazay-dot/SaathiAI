# Paper Order Lifecycle (M62.5)

Two distinct durable objects, never conflated:

- **`OrderIntent`** (M62.1 canonical) — the platform-level *proposed* action. An
  intent is **not** an order at the broker. No direct transition from a research
  output or strategy signal to a broker order is possible.
- **`PaperOrder`** — the broker-level durable order, created **only** after every
  authorization gate (Guardian veto → approval → reservation) passes.

## Intent state (tracked via M62.1 `OrderState`)

`DRAFT → APPROVAL_REQUIRED → SUBMITTED → PARTIALLY_FILLED → FILLED`
with `REJECTED` (Guardian veto / validation), `CANCELLED`, `EXPIRED`, `FAILED`.

## Broker state machine (`BrokerOrderState`)

```
PENDING_VALIDATION → ACCEPTED → OPEN → PARTIALLY_FILLED → FILLED
                                  ↘ CANCEL_PENDING → CANCELLED
       ↘ REJECTED   (validation / oversell / insufficient cash)
       ↘ EXPIRED    (time-in-force)
       ↘ FAILED
```

Terminal: `FILLED, CANCELLED, REJECTED, EXPIRED, FAILED` (immutable except through
explicit M62.6 reconciliation evidence). Every transition is explicitly validated
(`can_broker_transition`), tenant-scoped, audited to `paper_transitions`, and uses
optimistic concurrency (`version`).

## Enforced rules

- Filled orders cannot be cancelled (`test_cancel_after_fill_rejected`).
- Cancelled orders cannot fill afterward (`test_fill_after_cancel_rejected`).
- Rejected orders cannot reopen.
- Partial fills update `remaining_quantity` exactly; filled quantity is permanent
  (`test_partial_fill_then_cancel_retains_fill`).
- Duplicate transition / submission / event requests are idempotent.

## Fill policy (conservative, documented)

**Market orders** fill at the *next* eligible event at the adverse touch (ask for
BUY, bid for SELL) plus deterministic slippage. Never fills against pre-submission
data.

**Limit orders** — BUY fills only when `ask ≤ limit` and **never above** the limit;
SELL fills only when `bid ≥ limit` and **never below** the limit. No favorable
intrabar OHLC sequencing is assumed; the `from_bar` adapter uses the bar CLOSE for
both touches. When price quality is not `VALID` or the market is not `OPEN`, no fill
occurs.

**Partial fills** — quantity is capped by participation
(`liquidity × max_volume_participation`, floored to whole units); the remainder
stays open for later events.

## Cancellation & expiry

Cancellation follows the same canonical Runtime → Gateway → tool path. Open and
partially-filled orders may be cancelled; the unfilled reservation is released and
completed fills are retained. `DAY` time-in-force is modeled; `GTC` deferred.

## Halt

Account-level halt (owner+) rejects new submissions while preserving all existing
state for read-only inspection — a bounded fail-closed policy; broad incident
automation is out of scope for M62.5.
