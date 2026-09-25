# Corporate-Action Boundary

The importer normalizes external facts only. A record such as:

```text
type       BONUS
instrument NEPSE:NABIL
quantity   10
```

does not decide cost basis, tax lot allocation, cash movement, fractional
treatment, merger conversion ratios, reversal posting, or ledger event shape.

Those decisions belong to a future corporate-action accounting and explicit
ledger reconciliation/application milestone. `BONUS`, rights/IPO/FPO
allotments, stock/cash dividends, merger/split adjustments, generic corporate
actions, and reversals are therefore vocabulary and fact containers only.

NEPSE-TXN-1 does not apply any transaction to the Canonical Fund Ledger.
