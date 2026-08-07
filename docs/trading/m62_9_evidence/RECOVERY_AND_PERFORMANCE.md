# M62.9 — Long-Duration, Performance & Recovery Evidence

Harness: `long_duration_harness.py` (in this directory). Drives
`PaperTradingService` directly for load isolation; the Runtime→Gateway→Guardian
mutation boundary is certified separately by `test_m62_5_paper_broker.py`.

Raw metrics: `PERFORMANCE.json`.

## Long-duration simulation

| dimension | value |
|---|---|
| tenants | 3 |
| paper accounts | 9 |
| symbols | 3 (TRENDING, STEADY, VOLA) |
| orders | 1,620 |
| fills | 1,620 |
| market events | 4,860 |
| wall time | 4.81 s |

Each order runs full lifecycle: propose → Guardian evaluate → submit (reserve) →
market-event fill → completion → duplicate-event replay (idempotency probe).
BUY/SELL cycled so positions stay under the Guardian's `max_position_notional`.

## Performance

| metric | value |
|---|---|
| order latency p50 / p95 / p99 | 1.21 / 4.12 / 5.43 ms |
| fill latency p50 / p95 / p99 | 1.21 / 1.95 / 5.41 ms |
| order throughput | ~337 orders/s |
| event throughput | ~1,010 events/s |
| DB growth | 12.4 MB / 1,620 orders (~7.85 KB/order) |
| max RSS | 37.6 MB (stable) |
| restart time (reopen store) | 0.5 ms |

No premature optimization applied. Numbers are single-process, SQLite-backed,
localhost, deterministic paper simulation — not a live-trading benchmark.

## Accounting consistency

- Invariant violations across all 9 accounts: **0**
  (`check_account_invariants`: cash + reserved reconciles to fills; positions
  reconcile to fills).
- Duplicate fill IDs in session: **0** of 1,620 unique fills.

## Recovery certification

Store reopened from the same SQLite file (simulated restart), then a completed
order's fill event was **replayed**:

| check | result |
|---|---|
| invariants hold after restart | ✅ yes (all 9 accounts) |
| duplicate fills after restart replay | **0** |
| duplicate accounting after restart | **none** |
| silent repair | none — recovery is deterministic replay + idempotency, not mutation |

Idempotency keys on submission and per-event fill dedup guarantee that replaying
market events after a restart or mid-transaction crash produces no duplicate fills
and no duplicate cash/position accounting.

## Determinism proof

- Fill engine: `test_fill_determinism_identical_inputs_identical_hash` — identical
  inputs yield identical `result_hash`.
- Harness is fully reproducible: no wall-clock or RNG in the trading path; fixed
  seeds; fixed market events. Re-running yields identical order/fill/event counts and
  identical zero-violation accounting.
