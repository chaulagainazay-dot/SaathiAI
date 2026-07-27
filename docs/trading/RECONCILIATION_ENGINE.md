# Reconciliation Engine (M62.6)

`saathi/platform/paper_trading/reconciliation.py`

The reconciliation engine is the **authoritative integrity verifier** for the
paper-trading platform. It is read-mostly and **fail-closed**: it recomputes the
expected account state from the *immutable event record* and compares it against
persisted state. It never silently repairs accounting.

## Authority boundary

| Capability | Engine |
|---|---|
| Read fills / orders / positions / ledger / transitions | ✅ |
| Recompute expected state from immutable events | ✅ |
| Detect + classify drift | ✅ |
| Halt an account on CRITICAL drift (protective) | ✅ (only mutation) |
| Produce immutable reconciliation reports | ✅ |
| Generate repair **plans** | ✅ |
| Modify cash / positions / fills / ledger | ❌ never |
| Execute a repair | ❌ no code path exists |
| Create orders / fills | ❌ no execution authority |

The engine reuses the `PaperStore` SQLite connection, so its writes (reports,
recovery events, protective halt) are atomic and share the same DB file. All
tables and queries are tenant-scoped by `org_id`.

## Source of truth

Expected state is rebuilt from:

- `paper_accounts.starting_cash` (immutable origin)
- `paper_fills` (immutable, append-only, seq-ordered) — the authoritative events
- open (`non-terminal`) `paper_orders` reservations

Replay is deterministic, ordered by `(created_at, paper_order_id, seq)`:

- **BUY**: `cash -= gross + fee`; `qty += q`; `avg_cost` volume-weighted
- **SELL**: `cash += gross - fee`; `realized += (price - avg_cost)*q`; `qty -= q`
- **reserved_cash** = Σ open-order `reserved_cash`; **reserved_qty** = Σ open SELL `reserved_quantity`

`recompute_expected()` is a pure function of persisted events — no writes — so
running it twice yields byte-identical output (proven by
`test_replay_recompute_is_deterministic`).

## The seven reconciliation dimensions

| # | Dimension | Check | Worst severity |
|---|---|---|---|
| 1 | Orders ↔ Fills | `order.filled_quantity` == Σ fills; state-machine consistency | ERROR |
| 2 | Fills ↔ Positions | position qty == signed Σ fills; long-only (qty ≥ 0) | CRITICAL |
| 3 | Positions ↔ Ledger | ledger buy/sell row count == fill count | ERROR |
| 4 | Ledger ↔ Cash | `starting_cash + Σ(buy,sell,fee)` == `current_cash`; last `balance_after`; **cash recomputed from fills** == `current_cash` | CRITICAL |
| 5 | Cash ↔ Equity | recomputed equity == persisted; available_cash ≥ 0 | CRITICAL |
| 6 | Reservations ↔ Balances | reserved == Σ open orders; reserved ≥ 0; reserved ≤ cash; reserved_qty ≤ holding | CRITICAL |
| 7 | Audit ↔ Runtime | every order has a transition trail; terminal state matches last transition | WARNING |

## Drift severity

```text
INFO      all dimensions agree with the immutable record (clean)
WARNING   order-sensitive or audit-trail gaps (avg_cost order, missing transition)
ERROR     derived-projection mismatch (ledger, filled_quantity, equity, reserved)
CRITICAL  integrity violation vs immutable events (cash/position mismatch,
          negative balance, reserved > cash, tampered fill) → HALT
```

**CRITICAL drift halts the affected account** (`ACTIVE → HALTED`, reason
`reconciliation:critical drift <codes>`). This is a protective, fail-closed action
— never a financial mutation — recorded as a recovery event and audited. A halted
account blocks all new orders (`test_critical_halt_blocks_new_orders`).

## Immutable reports

Each `reconcile_account()` call writes one immutable `recon_runs` row + its
`recon_findings`, keyed by a fresh `run_id`, with a deterministic `report_hash`
over `(expected, persisted, findings)`. Re-running creates a NEW run; prior runs
are never mutated (`test_reports_are_immutable_and_persisted`).

## Public API

```text
reconcile_account(ctx, account_id)      -> ReconciliationReport   (RECONCILE_RUN)
reconcile_all(ctx)                      -> list[ReconciliationReport]
recover_account(ctx, account_id)        -> recovery report        (RECONCILE_RUN)
recompute_expected(org_id, account_id)  -> expected state (pure)
list_runs / get_run                     -> immutable reports       (RECONCILE_READ)
list_recovery_events                    -> recovery timeline       (RECONCILE_READ)
list_repair_plans / get_repair_plan     -> plans                   (RECONCILE_READ)
acknowledge_repair_plan(ctx, plan_id)   -> ACKNOWLEDGED   (REPAIR_PLAN_ACKNOWLEDGE)
authorize_repair_plan(ctx, plan_id)     -> AUTHORIZED     (REPAIR_PLAN_AUTHORIZE)
reject_repair_plan(ctx, plan_id)        -> REJECTED
```

## RBAC (M62.6 permissions)

| Permission | viewer | operator | owner |
|---|---|---|---|
| `reconciliation.read` | ✅ | ✅ | ✅ |
| `reconciliation.run` | — | ✅ | ✅ |
| `reconciliation.repair_acknowledge` | — | — | ✅ |
| `reconciliation.repair_authorize` | — | — | ✅ |
