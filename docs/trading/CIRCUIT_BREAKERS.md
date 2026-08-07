# M62.7 — Automated Paper-Trading Circuit Breakers

Automated, durable, deterministic operational safety on top of the M62.5 paper
broker and the M62.6 reconciliation engine. Breakers continuously/periodically
evaluate safety conditions and **halt the smallest affected scope** when an unsafe
condition is detected.

> PAPER only, long-only, localhost-only. Breakers HALT / FREEZE / REJECT /
> ACKNOWLEDGE and (fail-closed) RESET. They **never** repair financial state, never
> touch fills/positions/cash/ledger, and fail closed on any prohibited capability.
> Reconciliation (M62.6) remains the authoritative integrity verifier. No live
> broker, real money, leverage, margin, short-selling, derivatives, borrowing,
> credentials, or network access exists.

Package: `saathi/platform/safety/`

```
models.py        domain, enums, state machine, config guard, trading-day, hashing
store.py         SafetyStore (shares the PaperStore SQLite connection; atomic)
metrics.py       MetricsCollector — deterministic metrics from persisted paper state
evaluator.py     BreakerEvaluator + conservative default breaker policies
service.py       SafetyService — sweeps, trips, ack, reset, Guardian posture, recon
execution_tool.py  registered paper_safety.* tools (the canonical mutation path)
orchestration.py Runtime→Gateway→tool helpers
```

## Authoritative flow

```
paper activity → metric collection → deterministic evaluation → threshold breach
or integrity failure → durable trip → scope halted → new submissions rejected →
operator alert → acknowledgement → safe-condition verification → approval-backed
reset request → bounded reset through Runtime/Gateway → audit evidence
```

## Authority model (unchanged)

```
PlatformAgentRuntime  — canonical agent runtime
ExecutionGateway      — sole authority for registered mutation tools
Trading Guardian      — independent fail-closed veto (now consumes breaker posture)
PaperBroker           — PAPER-only simulation
Reconciliation (M62.6)— authoritative integrity verifier; may halt, never repairs
Circuit breakers (M62.7) — may halt/freeze/reject/ack/reset only, never repair
```

## Breaker-type matrix

| Type | Trips when | Default severity | Default open-order policy |
|------|-----------|------------------|---------------------------|
| `DAILY_REALIZED_LOSS` | daily realized P&L ≤ −threshold | ERROR | CANCEL_REMAINING_QUANTITY |
| `DAILY_TOTAL_LOSS` | realized + unrealized (daily) ≤ −threshold | ERROR | CANCEL_REMAINING_QUANTITY |
| `MAX_DRAWDOWN` | equity drawdown % ≥ threshold (peak persisted) | ERROR | CANCEL_REMAINING_QUANTITY |
| `GROSS_EXPOSURE` | gross long exposure > threshold | ERROR | CANCEL_REMAINING_QUANTITY |
| `POSITION_CONCENTRATION` | one symbol > threshold % of equity (warn band) | ERROR/WARNING | CANCEL_REMAINING_QUANTITY |
| `OPEN_ORDER_COUNT` | open/partial orders > threshold | ERROR | CANCEL_REMAINING_QUANTITY |
| `ORDER_REJECTION_RATE` | rate > threshold over window, denom ≥ min_samples | ERROR | CANCEL_REMAINING_QUANTITY |
| `PROCESSING_FAILURE` | failures ≥ threshold in window | CRITICAL | FREEZE_OPEN_ORDERS |
| `RECONCILIATION_CRITICAL` | M62.6 emits a CRITICAL finding | CRITICAL | FREEZE_OPEN_ORDERS |
| `RECONCILIATION_ERROR_STREAK` | repeated ERROR findings (optional) | ERROR | FREEZE_OPEN_ORDERS |
| `STALE_MARKET_DATA` | data age > policy | ERROR | FREEZE_OPEN_ORDERS |
| `INVALID_MARKET_DATA` | invalid quality / seq regress / dup / hash mismatch / corrupted replay | CRITICAL | FREEZE_OPEN_ORDERS |
| `ACCOUNTING_INVARIANT` | M62.5/M62.6 invariant fails at runtime | CRITICAL | FREEZE_OPEN_ORDERS |
| `MANUAL_KILL_SWITCH` | authorized manual trip | CRITICAL | FREEZE_OPEN_ORDERS |

Rejection numerator/denominator, window and sample-sufficiency are persisted with
every metric snapshot; a below-`min_samples` window never produces an unstable trip.

## Scope matrix

| Scope | Blocks | Manual-trip authority |
|-------|--------|-----------------------|
| `GLOBAL_PAPER` | all paper submissions across the local platform | owner/admin |
| `TENANT` | one tenant's paper submissions | owner/admin |
| `WORKSPACE` | one workspace's submissions | operator+ |
| `PAPER_ACCOUNT` | one paper account (reuses M62.5 `ACTIVE→HALTED`) | operator+ |
| `STRATEGY_VERSION` | intents referencing a strategy version | operator+ |
| `INSTRUMENT` | new orders for one instrument | operator+ |
| `MARKET_DATA_SOURCE` | events from a stale/invalid/corrupted source | operator+ / system |
| `PAPER_BROKER_PROCESSOR` | broker event processing when unsafe | operator+ / system |

`GLOBAL_PAPER` never implies production or live authority.

## State machine

```
NORMAL ─▶ WARNING ─▶ NORMAL
NORMAL ─▶ TRIPPED ─▶ HALTED ─▶ ACKNOWLEDGED ─▶ RESET_PENDING ─▶ RESET ─▶ NORMAL
WARNING ─▶ TRIPPED
```

Rules (enforced by `can_breaker_transition` + `SafetyService`):

* A trip immediately enforces the configured halt (atomic).
* Acknowledgement does **not** remove the halt.
* A reset request does **not** remove the halt.
* Approval alone does **not** remove the halt.
* Reset completes only after **all** safe-condition checks pass at execution time.
* Agents cannot acknowledge or reset by default (RBAC + `is_agent_actor` guard).
* Trips, metric snapshots, findings, alerts, acks and decisions are immutable.
* Repeated evaluation of the same breach is idempotent (a blocking breaker is not
  re-tripped by a sweep); a breaker may re-trip immediately once reset to NORMAL.

## Determinism

For identical persisted state + definitions + market-data refs + reconciliation
reports + evaluation timestamp, the subsystem produces identical metric snapshots,
findings, severity, trip decision, scope, open-order policy, trip hash and sweep
`result_hash`. Determinism inputs: safety engine version, breaker definition version,
scope-state, account snapshot, market-data health, reconciliation report hash,
evaluation timestamp, calendar, timezone, window boundaries. No wall-clock inside a
decision (the caller passes `now`), no RNG, no unsorted-query dependence.

## Threshold policy

Thresholds are explicit, versioned, tenant-scoped, validated, durable, Decimal-based
where financial, and bounded (`0 ≤ threshold ≤ 1e9`; concentration ≤ 100%). Updates
create a new version + immutable revision row and never mutate historical trip
evidence. Where no safe generic default exists (daily loss limits, gross exposure),
the breaker ships `requires_config=True` and stays **inert** — a fail-closed default
for high-impact operations — until an owner sets a threshold. Configuration requires
`PAPER_SAFETY_CONFIGURE` (owner) and rejects any prohibited capability.
