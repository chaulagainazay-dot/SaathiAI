# M46 — Approval Schema

Template: `docs/m46/operator_canary_approval.template.json`
Local filled records: `docs/m46/*.local.json` (**gitignored**).

## Required fields

approval_id, milestone (=M46), operator_id, issued_at, expires_at, provider,
provider_identity_fingerprint, credential_reference_kind,
credential_reference_locator_fingerprint, request_id, rollout_id,
allowed_operation, allowed_endpoint, maximum_calls, maximum_duration_seconds,
rollout_percent (1 only), read_only=true, writes/deployment/production/
autonomous/trading_guardian all false, rollback_conditions, kill_switch_owner,
incident_owner, acknowledgements (8 tokens), approval_integrity_fingerprint.

## Endpoint rule (Model A)

For `allowed_operation=IDENTITY_READ`, `allowed_endpoint` **must be** `user`.
`meta` is not valid for identity-binding canaries.

## Rules

- Deny-by-default; template is invalid until filled and signed.
- Expires automatically; one approval → one canary (durable consume ledger).
- No raw credentials.
- Integrity: HMAC over canonical core (`approval_fingerprint`).
