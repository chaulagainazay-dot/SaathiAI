# COMMAND_RUNTIME_INTEGRATION

`command_center_snapshot(ctx, account_id)` returns:

```text
mode=PAPER
live_execution=UNAVAILABLE
source=canonical_fund_ledger
paper_nav, cash, pnl, gross/net exposure, positions
reconciliation_status / portfolio_healthy
```

No manual source injection for ordinary runtime.
Composition layer already accepts these fields (T-NEXT-1).

