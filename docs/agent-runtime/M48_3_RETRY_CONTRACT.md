# M48.3 — Retry Contract

`classify_retry` → RetryClass + may_retry + backoff (0,2,10,30).

Hard max attempts: 5. Cancelled / deadline / prohibited / authority / approval /
uncertain mutation → not retryable. Transient errors use policy.should_retry.

`retry_task` refuses terminal runs in-place; bumps attempt when allowed.
