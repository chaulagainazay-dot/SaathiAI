# Submission Attempt Lifecycle

An intent records an attempt as `UNKNOWN` immediately before durable paper
submission. Successful persistence finalizes that row as `ACKNOWLEDGED`.
Unexpected interruption leaves `UNKNOWN`, which requires reconciliation. The
store is idempotent on request id and dispositions fail closed.
