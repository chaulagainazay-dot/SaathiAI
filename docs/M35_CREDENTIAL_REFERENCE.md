# M35 — Credential Reference Model

Extends the M31 `CredentialReference` (`saathi/credentials/models.py`) — metadata
only, never secret values — with strict M35 environment classification and
secret-source policy (`saathi/credentials/m35.py`).

## Environment classes

| Class | Permitted in M35 |
|-------|------------------|
| `SYNTHETIC` | yes |
| `LOCAL_TEST` | yes |
| `SANDBOX` | yes |
| `PRODUCTION` | **fails closed** (`production_environment_forbidden`) |

`classify_environment` maps free-form M31 environment strings (`test`, `dev`,
`local`, `sandbox`, `prod`, …) to a class; unknown strings fail closed.
`assert_environment_allowed` rejects `PRODUCTION` and any non-allowed class.

## What a reference contains / never contains

Reference fields (metadata only): `credential_ref_id`, `provider_id`,
`account_link_id`, `owner_scope`, `environment`, `storage_backend`,
`secret_fields_present` (field **names**), `scopes`, timestamps, `rotation_state`,
`revocation_state`, `status`, `fingerprint`, `backend_locator`, `connector_ids`.

Never present: secret value, API key, access/refresh token, password, private key,
session cookie, authorization header. `to_safe_dict()` carries
`contains_secret_values: false` and strips forbidden keys.

## Credential fingerprinting

Two distinct fingerprints, both non-reversible:

- **Metadata fingerprint** (M31 `compute_fingerprint`) — stable id/provider/owner/
  scopes/status digest; no secret involved.
- **Secret-material fingerprint** (M35 `m35_secret_fingerprint`) — domain-separated
  HMAC over the secret bytes + provider + account. Fixed 32-hex width (no length
  leak), no prefix/suffix leak, empty when no secret is loaded, provider- and
  account-bound, and **cannot authenticate** (feeding it back as a secret yields a
  different fingerprint).

## Secret storage behaviour

Secret material lives only in the M31 `SecretBackend` (in-memory for M35). A
reference records the field *names* and a backend locator, never the values.
Prohibited providers (financial/trading/etc.) fail closed at creation.
