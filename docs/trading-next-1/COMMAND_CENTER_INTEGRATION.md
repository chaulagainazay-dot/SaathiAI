# COMMAND_CENTER_INTEGRATION

`composeInvestmentSnapshot` accepts canonical ledger summary fields:

```text
source: canonical_fund_ledger
paper_nav / cash / pnl
gross_exposure / net_exposure
positions[]
```

UI never computes accounting. Missing fields remain **NOT AVAILABLE**.
Always labeled **PAPER**; `liveExecution=UNAVAILABLE`.

Lifecycle visibility (conceptual): RESEARCH → PROPOSAL → APPROVAL → PAPER ORDER →
PAPER FILL → LEDGER POSTED → RECONCILED — ledger covers last two legs.

