# M39 — Live Disposable Sandbox Validation Runbook

## Purpose

Exercise M31–M38 credential, session, retry, recovery, cleanup, and evidence
architecture against **one** real disposable sandbox credential **reference**.

M39 may evaluate canary **eligibility**. M39 **never** grants CANARY, ACTIVE,
rollout, production, or write authority.

## Prerequisites

1. Branch: `milestone/m7-security-engine`
2. M38 complete (`READY WITH LIMITATIONS`)
3. Operator-supplied **disposable** GitHub sandbox PAT (or fine-grained token)
   stored only as an approved **reference**:
   - macOS Keychain (`OS_KEYCHAIN_REFERENCE`)
   - Env var **name** only (`ENV_REFERENCE`)
   - Approved encrypted store (operator-wired)
4. Feature flag unset by default (fail closed)

## Non-negotiable secret policy

**Never** pass plaintext tokens via:

- CLI `--token` / `--api-key` / `--secret`
- Source, Markdown, JSON evidence, Git, stdout/stderr, shell history

Only secret **references** (Keychain service name, env var name, opaque locator).

## Operator acknowledgements (all required at runtime)

```
I_CONFIRM_CREDENTIAL_IS_DISPOSABLE
I_CONFIRM_SANDBOX_ACCOUNT_WHERE_POSSIBLE
I_CONFIRM_MINIMUM_READ_ONLY_PERMISSIONS
I_CONFIRM_NO_REPOSITORY_WRITE_PERMISSION
I_CONFIRM_NO_ORG_ADMIN_PERMISSION
I_CONFIRM_NO_BILLING_PERMISSION
I_CONFIRM_NO_PACKAGE_DEPLOY_WORKFLOW_SECRET_WRITE
I_CONFIRM_REVOKE_IMMEDIATELY_AFTER_VALIDATION
I_CONFIRM_READINESS_IS_NOT_AUTHORIZATION
I_CONFIRM_NO_PRODUCTION_ROLLOUT_CANARY_ACTIVE_WRITE
```

## Setup secret reference

See `docs/M39_SECRET_REFERENCE_SETUP.md`.

## Live sequence (only after secret reference exists)

```bash
# 1. Feature flag (session-local)
export SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION=1

# 2. Preflight policy dump (no network)
.venv/bin/python -m saathi.credentials m39-preflight

# 3. Qualify reference (existence only; no token print)
.venv/bin/python -m saathi.credentials m39-qualify-secret-reference \
  --source-kind OS_KEYCHAIN_REFERENCE \
  --locator 'saathi-m39-github-sandbox:pat'

# 4. Authorize (all --ack tokens required)
.venv/bin/python -m saathi.credentials m39-authorize-live-validation \
  --account-ref acct_sbx --credential-ref cred_sbx \
  --source-kind OS_KEYCHAIN_REFERENCE \
  --ack I_CONFIRM_CREDENTIAL_IS_DISPOSABLE \
  # ... remaining 9 acks ...

# 5. Single session
.venv/bin/python -m saathi.credentials m39-run-live-single-session \
  --source-kind OS_KEYCHAIN_REFERENCE \
  --locator 'saathi-m39-github-sandbox:pat' \
  --expected-subject-fp '<operator-approved-subject-fingerprint>' \
  --ack ... 

# 6. Multi session (max 2)
.venv/bin/python -m saathi.credentials m39-run-live-multisession ...

# 7. External revocation (manual in GitHub UI), then:
.venv/bin/python -m saathi.credentials m39-confirm-external-revocation \
  --confirmed --note 'revoked_in_github_settings'

# 8. Canary eligibility (read-only recommendation)
.venv/bin/python -m saathi.credentials m39-evaluate-canary-eligibility

# Emergency
export SAATHI_M39_KILL_SWITCH=1
.venv/bin/python -m saathi.credentials m39-interrupt-session
```

## Allowed live calls

| Call | Purpose |
|------|---------|
| `GET /user` | Identity qualification |
| `GET /meta` | Provider transport verification |

No writes. No second provider. Per-session budget ≤ 3.

## Offline path (no secret)

```bash
.venv/bin/python scripts/m39_generate_evidence.py --offline
```

Produces evidence with live statuses `NOT_EXERCISED` and executive verdict:

`M39 BLOCKED — OPERATOR SECRET REFERENCE REQUIRED`

## Kill switch

- Env: `SAATHI_M39_KILL_SWITCH=1`
- CLI: `m39-interrupt-session`
- Effect: block new provider calls; local cleanup; no authority grant

## After live run

1. Local cleanup complete
2. Leases revoked
3. External token revoked by operator
4. Leak scans clean
5. Evidence updated honestly
6. CANARY remains NOT GRANTED
