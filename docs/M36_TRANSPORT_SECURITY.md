# M36 — Transport Security

All real requests use M33 `ExternalTransport` only.

Enforced: HTTPS, hostname allowlist (`api.github.com`), DNS rebinding / SSRF
protections, redirect policy (0 for github_meta), TLS verification, timeout,
response-size ceiling, content-type policy, call-budget accounting, method and
endpoint ceilings, header redaction, response normalization, quarantine triggers.

Authorization is injected **only** in the sender wrapper (never stored on the
request envelope, never logged, never written to evidence).
