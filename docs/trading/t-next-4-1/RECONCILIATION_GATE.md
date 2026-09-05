# Reconciliation Gate

Only `ExecutionReadiness.RECONCILED` permits a new paper execution.
`MISMATCH`, `UNKNOWN`, `DATA_INSUFFICIENT`, and `TEMPORARILY_PENDING` are
denials by default. OMS, paper-external, and canonical-ledger snapshots remain
separate structures.
