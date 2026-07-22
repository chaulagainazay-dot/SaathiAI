# M45 — RuntimeSnapshot Schema

**Schema version:** `m45.runtime_attestation.v1`

## Required fields

| Field | Type | Notes |
|-------|------|-------|
| `snapshot_id` | string | deterministic id |
| `schema_version` | string | must equal schema |
| `generated_at` | ISO-8601 | UTC |
| `expires_at` | ISO-8601 | after generated_at |
| `machine_id_fingerprint` | string | local machine HMAC |
| `process_identity_fingerprint` | string | process HMAC |
| `repository_commit` | string | git HEAD or UNKNOWN |
| `repository_dirty_state` | `clean`\|`dirty`\|`UNKNOWN` | |
| `branch` | string | |
| `provider` | string | default `github_meta` |
| `provider_identity_fingerprint` | string | non-secret provider binding |
| `approved_scope` | string | |
| `credential_reference_kind` | string | e.g. `NONE`, `OS_KEYCHAIN_REFERENCE` |
| `credential_reference_fingerprint` | string | reference only |
| `credential_present` | bool | presence only |
| `credential_secret_read` | bool | **must be false** |
| `credential_lifecycle_state` | string | |
| `live_network_allowed` | bool | must be false for eligibility |
| `write_operations_allowed` | bool | must be false |
| `deployment_allowed` | bool | must be false |
| `rollout_execution_allowed` | bool | must be false |
| `requested_rollout_percent` | int | |
| `maximum_policy_percent` | int | M44 ceiling |
| `open_security_alerts` | int | must be 0 |
| `unresolved_incidents` | int | must be 0 |
| `rollback_active` | bool | must be false |
| `kill_switch_active` | bool | must be false |
| `error_budget_state` | string | must be `healthy` |
| `audit_ledger_state` | string | must be `intact` |
| `m32_state` | string | `PROHIBITION_UNCHANGED` |
| `trading_guardian_state` | string | `UNCHANGED / UNENGAGED` |
| `evidence_fingerprints` | string[] | bound chain |
| `attestation_provenance` | enum | see architecture |
| `attestation_signature` | string | local HMAC |
| `integrity_fingerprint` | string | over core body |
| `lifecycle` | enum | |
| `unknown_fields` | string[] | any ⇒ ineligible |
| `m43_machine_fingerprint` | string | binding |
| `m43_1_closure_fingerprint` | string | binding |
| `m44_completion_fingerprint` | string | binding |
| `m42_review_fingerprint` | string | binding |
| `m44_module_fingerprint` | string | binding |
| `contains_secret_values` | bool | must be false |

## Forbidden content

No raw secrets, tokens, PATs, private keys, passwords, authorization headers, or
provider response bodies.
