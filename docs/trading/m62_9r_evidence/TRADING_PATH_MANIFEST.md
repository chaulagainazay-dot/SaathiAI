# M62.9R Trading-Path Manifest (human-readable)

**Milestone:** M62.9R — End-to-End Paper Trading Operational Re-certification
**Branch:** `milestone/m61-backend-workflow-persistence`
**Starting HEAD:** `918b079`
**Code changes required:** None. Certification passed with documentation/evidence only.

## Authority path (canonical mutation chain)

```
Research thesis (immutable version)
  → Immutable strategy version
    → Deterministic backtest
      → OrderIntent
        → Trading Guardian (independent fail-closed veto)
          → Approval (where required)
            → PlatformAgentRuntime
              → ExecutionGateway.execute_registered_tool
                → Registered paper tool (paper.order.submit/cancel/process_event)
                  → PaperTradingService → PaperBroker → PaperOrder
                    → Immutable fills → Accounting
                      → ReconciliationEngine (verify, may halt, never repair)
                        → Safety evaluation (circuit breakers)
                          → Alert + halt when necessary
                            → Acknowledgement (human-only, awareness only)
                              → Reset request → Approval → Runtime → Gateway
                                → paper_safety.reset (technical re-verification battery)
                                  → Bounded reset (no financial mutation)
                                    → Immutable audit evidence
                                      → Browser (read-only operator interface)
```

No alternate executable path mutates financial or protective state outside this chain.
Every HTTP mutation endpoint calls `orchestration.*_via_gateway`, never the service directly.

## Registered tools (8 — the only mutation authority)

| Domain | Tool ID | Side effect |
|--------|---------|-------------|
| paper_trading | `paper.order.submit` | FINANCIAL_EXECUTION |
| paper_trading | `paper.order.cancel` | FINANCIAL_EXECUTION |
| paper_trading | `paper.order.process_event` | FINANCIAL_EXECUTION |
| paper_safety | `paper_safety.trip` | protective state |
| paper_safety | `paper_safety.acknowledge` | awareness only (human) |
| paper_safety | `paper_safety.request_reset` | request only (human) |
| paper_safety | `paper_safety.reset` | protective-state transition only (human) |
| paper_safety | `paper_safety.run_sweep` | protective state (system permitted) |

## Role / actor model

- **Viewer** — read-only across accounts, orders, reconciliation, safety.
- **Operator** — viewer + propose/submit/cancel, run reconciliation, sweep, trip, acknowledge, request reset.
- **Owner** — operator + halt, configure breakers, authorize repair plan, execute reset, decide approvals.
- **System** — scheduled sweeps only; blocked from human-only acknowledge/reset by `is_agent_actor` gate.

## Prohibited-capability assertions (all FALSE / absent)

Live broker · real money · external execution · credentials in trading code · leverage · margin ·
short selling · options/futures/perpetuals/derivatives · borrowing · withdrawals ·
autonomous capital allocation · **automatic financial repair** · eval/exec/subprocess/socket in
trading modules · network egress in trading modules.

All prohibited terms found in trading code are in rejection lists, Guardian constants, docstrings,
or clamping logic — never executable behavior.

## Repair non-execution

No symbol `execute_repair` / `apply_repair` / `repair_account` / `auto_repair` / `fix_financial_state`
exists as executable financial repair. `authorize_repair_plan` marks intent only and audits
`outcome="authorized_not_executed"`. Corruption remains until externally corrected.

## Module hashes (SHA-256, first 16 hex)

See `TRADING_PATH_MANIFEST.json` → `module_hashes_sha256_16`.

## Determinism

- Market-data replay hash stable across repeated runs.
- Backtest result hash equal across three runs (`test_deterministic_result_hash`).
- Long-duration simulation financial outputs identical across two runs.

## Long-duration simulation

4 tenants · 16 accounts · 2240 orders · 6720 events · invariants clean · 0 duplicate fills ·
restart recovery with no duplicate accounting · order p95 1.567 ms / p99 1.801 ms ·
376.5 orders/s · 38.9 MB peak RSS.

## Localhost bindings

`scripts/start_local.sh` binds backend `127.0.0.1:8765` and UI `-H 127.0.0.1:3000`.
`saathi/config.py` HOST env default is `0.0.0.0` (fallback) — recorded as a known limitation;
the canonical launcher overrides it.

## Known limitations

Single-host SQLite · localhost-only · fixture/replay market data · local-only alerts ·
no distributed scheduler · server-side reset-approval creation · limited manual config UI ·
no production deployment / live broker / real funds / autonomous allocation.
