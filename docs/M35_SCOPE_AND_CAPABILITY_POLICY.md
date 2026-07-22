# M35 — Scope and Capability Policy

## Least-privilege scope classes (`classify_scope`)

**Allowed (read-only):** `IDENTITY_READ`, `METADATA_READ`, `PUBLIC_DATA_READ`,
`SANDBOX_RESOURCE_READ`.

**Forbidden (fail closed):** `WRITE`, `ADMIN`, `OWNER`, `BILLING`, `PAYMENT`,
`TRANSFER`, `WITHDRAWAL`, `TRADING`, `ORDER_ENTRY`, `PORTFOLIO_CONTROL`,
`SECRET_MANAGEMENT`, `USER_MANAGEMENT`, `REPOSITORY_WRITE`, `EMAIL_SEND`,
`CALENDAR_WRITE`, `SOCIAL_PUBLISH`, `CLOUD_ADMIN`.

**Unknown scopes fail closed** (`UNKNOWN` → not allowed). A declared read-only scope
is not sufficient by itself.

## Scope verification states (`verify_scope_evidence`)

`DECLARED` (insufficient) · `OBSERVED` · `VERIFIED` · `MISMATCHED` · `UNKNOWN`.
Session eligibility requires `VERIFIED` — reached by observed scopes matching
declared, or an explicit synthetic-test classification.

## Capability ceiling (`CapabilityCeiling`)

Derived from the external provider profile (`github_meta`: `get_meta` / `GET` /
`READ_ONLY` / `PUBLIC` / `SANDBOX`) intersected with the credential, account,
operator approval, and connector ceilings.

`request_within_ceiling` requires a session request to be a subset. It fails closed
on: provider substitution, operation broadening, method broadening, write methods,
side-effect escalation, data-classification broadening, environment broadening, and
scope broadening. `intersect_ceilings` requires all ceilings to agree on
provider/operation/method/side-effect/data/env and intersects scopes.
