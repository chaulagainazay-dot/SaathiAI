# M35 — Sandbox Account Registry

`SandboxAccountRegistry` (`saathi/credentials/m35.py`) — metadata-only registry of
governed sandbox accounts. Composes with, and never replaces, the M31
`AccountLinkRegistry`.

## Account record

`account_ref_id`, `provider_id`, `environment_class`, `account_subject_fingerprint`
(non-reversible), `display_alias`, `declared_scopes`, `verified_scopes`,
`capability_ceiling`, `verification_state`, `verified_at`, `expires_at`,
`revoked_at`, `drift_state`, `metadata_safe`.

## Identity protection

- The subject is stored only as a non-reversible fingerprint (`subject_fingerprint`).
- A `display_alias`, subject, or metadata value containing a raw email or phone is
  rejected (`raw_personal_identifier`).
- Metadata keys for password/token/cookie/billing/payment/card/IBAN/account-number/
  email/phone are rejected (`forbidden_account_field`).
- `to_safe_dict()` carries `contains_secret_values: false`.

## Verification

`verify(observed_scopes=…, synthetic=…)` runs scope-evidence verification:
- `synthetic=True` → `SYNTHETIC_VERIFIED`;
- observed scopes match declared → `VERIFIED`;
- observed broaden/miss declared → `MISMATCHED`;
- otherwise `FAILED`.

Production accounts fail closed at registration (`production_environment_forbidden`).
Prohibited providers fail closed.

## Drift and revocation

`check_drift(expected_fingerprint=…)` compares a deterministic account fingerprint
(provider/env/subject/scopes/ceiling) → `FRESH`/`MISMATCHED`/`REVOKED`/`UNKNOWN`.
`revoke()` sets `REVOKED`, blocks re-verification, and leaves unrelated accounts
untouched.
