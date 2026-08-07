# M62.7 — Safety Sweeps

A safety sweep evaluates paper-trading safety conditions across a bounded set of
scopes and trips any breaker whose threshold is breached. Sweeps are **on-demand**
(operators + tests) and support a **scheduled/interval** registration that is
**disabled by default** (opt-in, localhost-only, single-host).

## What a sweep evaluates

Per eligible paper account: cash / equity, daily realized & total P&L, drawdown
(with restart-safe persisted peak), gross exposure, position concentration,
open-order count, rejection rate, processing-failure window, and existing breaker
state. `RECONCILIATION_CRITICAL` and market-data breakers are event-driven and are
tripped through `reconcile_and_guard` / `observe_market_event` rather than the
metric sweep.

## Flow

```
sweep starts → select bounded eligible scopes → capture metric snapshots →
evaluate breaker definitions → persist findings → trip required breakers →
enforce halts → emit alerts → write audit evidence → complete sweep manifest
```

## Guarantees

* **Bounded batch** (`batch`, default 100) and safe pagination.
* **Auto-provision**: an account with no breaker definitions is seeded with the
  conservative defaults during the sweep, so **no active account is silently
  unmonitored**. Skipped scopes are recorded explicitly in the manifest.
* **Idempotent**: a breaker already in a blocking state is **not** re-tripped — no
  duplicate trips, no duplicate alerts.
* **Overlap prevention** via a scheduler lease (`acquire_lease` / `release_lease`).
* **Restart-safe**: state, peaks, windows, counters and scheduler registration all
  survive process restart (single-host SQLite).
* **Per-breaker isolation**: an error evaluating one breaker is captured in the
  manifest `errors[]` and never aborts the sweep or silently drops accounts.
* **Deterministic**: identical fixture + evaluation `now` → identical `result_hash`.

## Sweep manifest

Every completed sweep produces an immutable manifest:

```json
{
  "sweep_id": "swp_...",
  "engine_version": "paper-safety/1.0.0",
  "started_at": 1000.0,
  "completed_at": 1000.0,
  "scope_count": 1,
  "accounts_evaluated": 1,
  "definitions_evaluated": 10,
  "findings_by_severity": {"INFO": 8, "WARNING": 0, "ERROR": 1, "CRITICAL": 0},
  "trips_created": 1,
  "alerts_created": 1,
  "errors": [],
  "skipped_scopes": [],
  "result_hash": "<sha256>"
}
```

## Scheduling (opt-in, disabled by default)

`SafetyStore.register_sweep_schedule(name, enabled=False, interval_seconds=...)` is
idempotent. A scheduled run must acquire the lease before executing and release it
after, preventing overlap on a single host. No new scheduler framework is
introduced, no distributed scheduler is claimed, and no alternate user-triggered
execution authority is created — scheduled sweeps use a bounded system-owned service
path consistent with existing conventions.
