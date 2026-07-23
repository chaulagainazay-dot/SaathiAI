# M49.1 Retry and Outcome Contract

Outcomes: SUCCESS_CONFIRMED, FAILURE_CONFIRMED, CANCELLED_CONFIRMED, TIMEOUT_CONFIRMED,
SIDE_EFFECT_UNKNOWN, TOOL_OUTCOME_UNKNOWN, BLOCKED, PROHIBITED, REQUIRES_REVIEW.

Never auto-retry: uncertain mutation, missing idempotency key, cancelled, prohibited, invalid output.
`classify_retry()` encodes policy.
