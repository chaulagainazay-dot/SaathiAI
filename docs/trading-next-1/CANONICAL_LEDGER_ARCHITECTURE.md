# CANONICAL_LEDGER_ARCHITECTURE

```text
Paper OMS accepted fill
        │
        ▼
  paper_bridge.post_paper_fill_to_ledger
        │
        ▼
  PortfolioLedgerService.record_fill  (idempotent)
        │
        ▼
  fl_events (append-only SQLite)
        │
        ▼
  reduce_events (FIFO lots, Decimal)
        │
        ├── cash / lots / realized
        ├── marks → unrealized / NAV / exposure
        └── reconcile vs OMS fill list
                │
                ▼
        Command Center / Risk (read-only)
```

## Package

`saathi/platform/fund_ledger/`

| Module | Role |
| --- | --- |
| money.py | Decimal money; reject float; currency tag |
| models.py | Fund, Security, LedgerEvent, lots, NAV views |
| reducer.py | Deterministic apply + invariants |
| store.py | SQLite append-only events |
| service.py | PortfolioLedgerService API |
| reconcile.py | OMS vs ledger comparison |
| paper_bridge.py | OMS → ledger one-way adapter |

## Authority statement

- **One canonical writer:** `PortfolioLedgerService`
- Agents: no direct cash/position/NAV mutation
- No `set_position` / `set_nav` / `set_pnl`

