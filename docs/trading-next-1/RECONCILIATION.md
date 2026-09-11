# RECONCILIATION

`PortfolioLedgerService.reconcile(fund_id, oms_fills=...)` detects:

- MISSING_FILL / EXTRA_LEDGER_FILL
- DUPLICATE_OMS_FILL / DUPLICATE_LEDGER_FILL
- QUANTITY_MISMATCH / PRICE_MISMATCH
- CASH_MISMATCH / INVARIANT

**No silent repair.** Issues returned for operator visibility.

