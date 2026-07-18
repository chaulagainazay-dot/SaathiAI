# M38 — Recovery and Reconciliation

## Principles

1. Detect stale/inconsistent state
2. Cleanup residual authority only
3. Never recreate secrets from evidence
4. Reopen secrets only via new governed retrieval + reauthorization
5. Idempotent cleanup and recovery
6. Exhaustion → TERMINAL_FAILED + operator action
7. No authority escalation during recovery

## Cases covered offline

Interrupt after authorization, qualification, identity, before cleanup;
orphan missing session; duplicate recovery; recovery exhaustion; reconcile scan.
