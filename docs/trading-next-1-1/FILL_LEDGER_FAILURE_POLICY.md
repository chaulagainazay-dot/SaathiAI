# FILL_LEDGER_FAILURE_POLICY

```text
OMS fill succeeds
ledger post fails
  → fill remains durable
  → fl_fill_posts status = FAILED/PENDING
  → portfolio_status = RECONCILIATION_REQUIRED
  → retry via retry_ledger_posts (idempotent)
  → NO silent repair, NO automatic fill delete
```

Atomic cross-DB transaction is not assumed (OMS DB ≠ fund ledger DB).
Convergence via pending queue + recon gate.

