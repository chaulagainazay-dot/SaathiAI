# M49.3 Async/HTTP Completion

Phases: NOT_STARTED, DNS_OR_CONNECT, CONNECTED, HEADERS_SENT, BODY_PARTIAL, BODY_SENT, RESPONSE_HEADERS, RESPONSE_PARTIAL, RESPONSE_COMPLETE, UNKNOWN (+ M49.2 aliases).

Rules:
- cancel before send → CANCELLED_CONFIRMED
- BODY_SENT without confirmed response on mutation → SIDE_EFFECT_UNKNOWN (not retryable)
- timeout on mutation after send → SIDE_EFFECT_UNKNOWN
- no fallback after cancellation; no retry after ambiguous mutation
