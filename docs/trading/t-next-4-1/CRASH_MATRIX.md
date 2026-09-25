# Crash Matrix

Crashes before attempt persistence are safe to retry only after the normal
readiness gate. Crashes after an UNKNOWN intent, during/after send, or before
outcome persistence are `RECONCILE_FIRST`. ACK persistence and ledger writes
are atomic/idempotent; no blind retry is permitted.
