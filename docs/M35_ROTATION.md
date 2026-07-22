# M35 — Credential Rotation

`validate_rotation` (`saathi/credentials/m35.py`) guards a rotation before the M31
`broker.rotate` is applied. No real credential is rotated in M35.

## Flow

old credential registered → new reference registered → new credential validated →
new fingerprint generated → account + scope re-verified → new lease eligibility
confirmed → old credential revoked → old leases invalidated → rotation evidence
recorded. No overlap is required.

## Fail-closed detections

- `same_secret_reuse` — new fingerprint equals the old;
- `provider_mismatch`, `account_mismatch`, `environment_mismatch`;
- `scope_broadening` — new scopes exceed old;
- `invalid_replacement` — replacement not valid;
- `expired_replacement` — replacement already expired.

The M31 `broker.rotate` revokes prior leases for the credential
(`revoke_for_credential`) as part of rotation. Rotation never contacts a provider.
