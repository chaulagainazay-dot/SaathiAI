# M32 — Security

## Endpoint controls

Deny-by-default endpoints: only `inprocess`/`loopback`, loopback `http`, or
`https` with a host. External HTTP without TLS, arbitrary schemes, and
caller-supplied endpoints all fail closed. Production environment disabled.

## Secret handling

- Configuration is secret-free; auth profile must be `none`/`public`/`sandbox_none`.
- Request fingerprints and idempotency records exclude secret material.
- Responses strip tokens, cookies, authorization, api-keys, stack traces.
- Error messages are redacted and bounded.
- Evidence is leak-scanned (M31 detector) **before** every write; a leak raises
  `LeakDetected` and nothing is written.

## Raw-response containment

Raw provider response objects never escape the adapter boundary. Only
`normalized_data` + `safe_metadata` surface; the runtime never stores raw
transport objects.

## Side-effect restrictions

Permitted: `NONE`, `READ_ONLY`. Prohibited (fail closed): `REVERSIBLE_WRITE`,
`IRREVERSIBLE_WRITE`, `FINANCIAL`, `SECURITY_SENSITIVE`, `ACCOUNT_MUTATION`.
Undeclared side-effect class fails closed.

## Data classification

Pilot uses only `PUBLIC` / `INTERNAL`. Redaction fails closed for unknown
sensitive fields. No real personal, health, financial, or credential-bearing
payloads.

## Forbidden provider categories

`provider_is_prohibited` blocks any provider id/capability matching
`trade|order|broker|exchange|wallet|withdraw|transfer|payment|bank|financial|
leverage|margin|futures|crypto|binance|…` and the prohibited id set
(gmail, calendar, slack, facebook, instagram, youtube/linkedin publish). Such a
provider cannot be selected, registered, resolved, or pass eligibility.

## Bypass posture

The M32 provider runtime is an authorized governed call site (allowlisted in
`gov/bypass_guard.py`, analogous to `gov/runtime.py`). Connector bypasses,
connector-conformance bypasses, provider-adapter bypasses, and direct provider
bypasses all remain 0.

## Trading Guardian

UNCHANGED / UNENGAGED. Regression tests prove financial/trading providers cannot
be selected as the pilot or pass provider eligibility.
