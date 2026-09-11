# UNKNOWN State Contract

UNKNOWN is not healthy and is never converted to RECONCILED by a later healthy
snapshot. Only explicit `record_submission_reconciliation` can resolve an
ambiguous attempt, and an externally found order remains non-retryable.
