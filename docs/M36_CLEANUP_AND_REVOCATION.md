# M36 — Cleanup and Revocation

## Preferred disposition

1. Local lease revoked (automatic on session complete)
2. Secret handle closed / zeroized
3. External disposable credential revoked manually by operator
4. Record `EXTERNAL_REVOCATION_OPERATOR_ATTESTED` when manual

## Allowed dispositions

`LEASE_EXPIRED`, `LEASE_REVOKED`, `CREDENTIAL_REVOKED_EXTERNALLY`,
`CREDENTIAL_RETAINED_FOR_FUTURE_EXPLICIT_TEST` (explicit only),
`ACCOUNT_DELETION_PENDING`, `EXTERNAL_REVOCATION_OPERATOR_ATTESTED`.

`SILENT_ACTIVE` is forbidden and fails closed.

No unauthorized provider write for revocation.
