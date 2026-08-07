# RECONCILIATION_GATE

`PaperTradingService.portfolio_reconciliation_status`:

- pending/failed ledger posts → `RECONCILIATION_REQUIRED`
- OMS vs ledger fill mismatches → issues surfaced
- healthy only when pending=0 and ledger.reconcile ok

UI/command snapshot includes `portfolio_status` / `portfolio_healthy`.

