# M49.2 Async/HTTP Cancellation

`http_cancel.classify_http_outcome` maps request phases to outcomes.
Ambiguous delivery on mutation → SIDE_EFFECT_UNKNOWN, not retryable.
No live paid HTTP in M49.2.
