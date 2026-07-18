# M32 — Response Normalization & Error Taxonomy

Modules: `normalization.py` (`normalize_response`, `normalize_headers`), `errors.py`

## Response normalization

- Parses bytes/str/dict; malformed body → `MALFORMED_RESPONSE` (fail closed).
- Enforces the response-size ceiling; oversized → `MALFORMED_RESPONSE`.
- Strips sensitive body keys: `access_token`, `refresh_token`, `token`, `api_key`,
  `authorization`, `cookie`, `secret`, `password`, `private_key`, `bearer`,
  `client_secret`, `stack`, `traceback`, `exception`, … plus a defense-in-depth
  `redact_payload` pass.
- `normalize_headers` drops `set-cookie`, `cookie`, `authorization`,
  `www-authenticate`, `x-api-key`, `x-auth-token`, and any token/secret-shaped header.
- Partial success (HTTP 206 / `partial` flag) is represented, never coerced to success.
- Raw provider response objects never escape the adapter boundary — only
  `normalized_data` + `safe_metadata` surface.

## Canonical error taxonomy (`ProviderErrorCode`)

`AUTHENTICATION_FAILED`, `AUTHORIZATION_FAILED`, `SCOPE_INSUFFICIENT`,
`RATE_LIMITED`, `TIMEOUT`, `CONNECTION_FAILED`, `PROVIDER_UNAVAILABLE`,
`MALFORMED_RESPONSE`, `INVALID_REQUEST`, `NOT_FOUND`, `CONFLICT`, `DUPLICATE`,
`PARTIAL_SUCCESS`, `CANCELLED`, `POLICY_BLOCKED`, `INTERNAL_ADAPTER_ERROR`,
`UNKNOWN_PROVIDER_ERROR`.

`classify_status` maps HTTP status → code; `classify_exception` maps raw
exceptions → code; unknown → `UNKNOWN_PROVIDER_ERROR` (fail closed).
`safe_error_message` produces a bounded, redacted message — never tokens, keys,
cookies, authorization headers, raw account ids, raw HTML, or huge bodies.
