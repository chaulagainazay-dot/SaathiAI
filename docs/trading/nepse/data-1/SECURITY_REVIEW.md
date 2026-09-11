# Security review

No live adapter was added. Future adapters require HTTPS/TLS verification, host allowlisting, redirect and response-size bounds, strict JSON validation, canonical instrument mapping, secret redaction, and fail-closed handling of HTML, prompt-like text, malformed payloads, rate limits, timeouts, and schema drift.
