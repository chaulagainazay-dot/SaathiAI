# M62.8 — SaathiOS Trading Operator Workspace

The browser now exposes the bounded **paper-trading operator workspace** backed by
the canonical M62.5–M62.7 services. It replaces the M54 advisory-only "Trading
Guardian" placeholder ("Trading execution is not available", "NO_TRADING_AUTHORITY",
"NOT EXERCISED"), which was misleading now that paper execution is implemented.

> Paper execution available · Live execution unavailable · Simulation-only ·
> Long-only · Localhost-only. The workspace never calculates or mutates authoritative
> financial state — the server is authoritative for all accounting.

Frontend app: `saathi-os/` (Next.js 15 app router). API base: `http://localhost:8765`.

## Route map

| Route | Surface |
|-------|---------|
| `/trading` | Overview — posture, aggregate cash/equity/reserved, accounts, breakers, trips, alerts, drift, latest sweep/reconciliation, market-data note |
| `/trading/accounts` | Paper accounts list (state, cash, reserved, equity, realized P&L) |
| `/trading/accounts/[accountId]` | Account detail — balances, positions (fixture marks), open orders, halt posture, breaker states, reconciliation history |
| `/trading/orders` | Orders list (tenant-scoped) |
| `/trading/orders/[orderId]` | Order detail — facts, authority lifecycle, state transitions, immutable fills |
| `/trading/positions` | Positions across accounts (marks labelled REPLAY / FIXTURE) |
| `/trading/strategies` | Strategy version + thesis references from order intents |
| `/trading/reconciliation` | Reconciliation runs, 7-dimension findings, repair plans (PLAN ONLY — never executed) |
| `/trading/safety` | Breaker states, trips, sweeps, alerts, breaker definitions + acknowledge/reset workflow |
| `/trading/approvals` | Trading approvals from the Approval Center (reset approvals, single-use, scope-bound) |
| `/trading/evidence` | Read-only immutable evidence timeline (trip/sweep/reconciliation/repair-plan/alert/order/fill) |

## API-to-screen mapping (all authenticated `/api/v1/platform/*`, `X-Platform-Token`)

| Screen | Endpoints |
|--------|-----------|
| Overview | `/me`, `/paper/accounts`, `/paper/safety/{states,trips,alerts,sweeps}`, `/paper/reconciliation/runs`, `/approvals`, `POST /paper/safety/sweeps` |
| Accounts | `/paper/accounts`, `/paper/accounts/{id}`, `/paper/accounts/{id}/positions` |
| Orders | `/paper/orders`, `/paper/orders/{id}` (transitions), `/paper/orders/{id}/fills` |
| Positions | `/paper/accounts`, `/paper/accounts/{id}/positions` |
| Strategies | `/paper/order-intents`, `/paper/order-intents/{id}` |
| Reconciliation | `/paper/reconciliation/{runs,runs/{id},repair-plans}`, `POST /paper/reconciliation/runs` |
| Safety | `/paper/safety/{breakers,states,trips,sweeps,alerts}`, `POST /paper/safety/sweeps`, `.../trips/{id}/acknowledge`, `.../trips/{id}/reset-requests`, `.../reset-requests/{id}/execute` |
| Approvals | `/approvals?status=` (Approval Center) |
| Evidence | aggregate of `/paper/safety/{trips,sweeps,alerts}`, `/paper/reconciliation/{runs,repair-plans}`, `/paper/orders` |

New M62.8 backend additions (read + integrated-run only; no new mutation authority):
`GET /paper/reconciliation/runs`, `/runs/{id}`, `/repair-plans`, `/repair-plans/{id}`,
`POST /paper/reconciliation/runs` (integrated reconcile→auto-trip; never repairs);
account detail now returns `halt_reason` + `mark_source`.

## Data layer

`saathi-os/lib/trading.js` — one authenticated `plat()` path with bounded retry on
transient/cold failures; `useTradingOverview` (aggregate), `useAuthMe` (permissions),
`useResource` (single resource with loading/empty/error/retry); `actions.*` route
bounded mutations back through the same authenticated APIs → Runtime → Gateway.
Display formatting only (`fmtMoney`/`fmtNum`/`fmtPct` over server decimal strings) —
never client-side accounting.

`saathi-os/components/trading/TradingShell.jsx` — sub-navigation tabs, proportional
safety banner (neutral when healthy; amber/red only for real posture), `SignInGate`,
`StatCard`, `StateChip`, `DataTable` (semantic `<th scope>`, `overflow-x:auto`,
keyboard-activatable rows).

## Concurrency hardening

The workspace fans out concurrent authenticated reads. Both single-host SQLite
connections (`PaperStore` shared by SafetyStore/ReconStore, and `PlatformStore`) are
now wrapped by a reentrant-lock facade (`_SerializedConn`) that materializes each
SELECT's rows + `lastrowid`/`rowcount` under the lock — eliminating the
`sqlite3.InterfaceError` that concurrent threadpool reads previously raised. Existing
`with lock, conn:` write blocks are unaffected (the lock is reentrant).
