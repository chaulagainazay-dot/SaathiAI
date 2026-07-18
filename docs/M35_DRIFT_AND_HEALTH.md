# M35 — Drift and Health

## Drift (`credential_drift_fingerprint` + `check_credential_drift`)

Inputs: provider id, environment class, credential type, secret-source type, scope
set, capability ceiling, account ref, adapter version, credential-policy version.

States (`DriftState`): `FRESH`, `STALE`, `MISMATCHED`, `REVOKED`, `UNKNOWN`.
Any material change to an input marks the credential `MISMATCHED` (drifted).
Account drift uses `SandboxAccount.drift_fingerprint` + `registry.check_drift`.

Eligibility and health reads are **non-mutating**; only explicit verification
commands refresh state.

## Health (`credential_health`, metadata-only)

States (`CredentialHealthState`): `HEALTHY`, `EXPIRING`, `EXPIRED`, `REVOKED`,
`SCOPE_MISMATCH`, `ACCOUNT_MISMATCH`, `PROVIDER_MISMATCH`,
`SECRET_SOURCE_UNAVAILABLE`, `ROTATION_REQUIRED`, `QUARANTINED`, `UNKNOWN`.

Health reads never retrieve a secret, consume a lease, refresh credentials, rotate,
mutate verification timestamps, or contact a provider. Default reads use metadata
only.
