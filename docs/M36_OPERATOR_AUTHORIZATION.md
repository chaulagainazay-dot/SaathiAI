# M36 — Operator Authorization

## Purpose

M36 real sandbox sessions require an explicit, time-bounded, use-bounded
authorization record. Prompt authorization alone is insufficient.

## Required acknowledgements (all non-default)

```
I_CONFIRM_DISPOSABLE_SANDBOX_ACCOUNT
I_CONFIRM_READ_ONLY_SCOPE
I_CONFIRM_NO_PRODUCTION_DATA
I_CONFIRM_SECRET_REFERENCE_ONLY
I_CONFIRM_CALL_BUDGET
I_CONFIRM_NO_WRITES
I_CONFIRM_REVOCATION_PLAN
I_CONFIRM_ROLLOUT_REMAINS_OFF
```

## Live environment flag

```
SAATHI_M36_ALLOW_LIVE_SANDBOX_VERIFICATION=1
```

The flag alone does **not** authorize execution. It must combine with a valid
M36 authorization, qualified account, secret reference, and `--live`.

## Authorization record fields (safe)

`authorization_id`, `milestone=M36`, `provider_id`, `account_ref_id`,
`credential_ref_id`, `operation`, `endpoint`, `method`, `environment_class`,
`approved_scope_classes`, `approved_call_budget`, `approved_duration`,
`approved_lease_uses`, `operator_acknowledgements`, `created_at`, `expires_at`,
`status`.

Never includes token material, raw identity, email, Authorization headers, or
sensitive secret locators.

## Rules

- Expires (default ≤ 15 min, hard max 30 min).
- One use (session-specific); not reusable for M37.
- Provider / account / credential / operation / endpoint specific.
- M35 approvals cannot substitute for M36 authorization.

## CLI

```bash
python -m saathi.credentials m36-preflight
python -m saathi.credentials m36-authorize \
  --account-ref <ref> --credential-ref <ref> \
  --ack I_CONFIRM_DISPOSABLE_SANDBOX_ACCOUNT \
  # ... all 8 acks
```
