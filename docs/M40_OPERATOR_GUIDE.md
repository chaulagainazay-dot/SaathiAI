# M40 — Operator Guide

Run the M40 live certification only when you can supply a **disposable, read-only,
sandbox** credential as a reference. Never paste a raw token.

## Prerequisites

1. M31–M40 regression green; offline gates pass; leak scans clean.
2. A disposable GitHub sandbox PAT with **read-only** permissions (`/user`, `/meta`
   only). No repo write, org admin, billing, or workflow-secret scope.
3. Store it as a reference:
   - Keychain: `security add-generic-password -s <service> -a <account> -w` (you
     enter the value; SaathiOS never sees it), then use `--source-kind OS_KEYCHAIN_REFERENCE --locator <service>:<account>`, or
   - Env var: `export MY_TOKEN=<value>` then `--source-kind ENV_REFERENCE --env-var-name MY_TOKEN`.

## Run (live window only)

```bash
export SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION=1   # live window only
python -m saathi.credentials.cli m40-certify \
  --source-kind OS_KEYCHAIN_REFERENCE --locator <service>:<account> \
  --operator-authorized --environment-confirmed --live-flag \
  --ack I_CONFIRM_CREDENTIAL_IS_DISPOSABLE \
  --ack I_CONFIRM_SANDBOX_ACCOUNT_WHERE_POSSIBLE \
  --ack I_CONFIRM_MINIMUM_READ_ONLY_PERMISSIONS \
  --ack I_CONFIRM_NO_REPOSITORY_WRITE_PERMISSION \
  --ack I_CONFIRM_NO_ORG_ADMIN_PERMISSION \
  --ack I_CONFIRM_NO_BILLING_PERMISSION \
  --ack I_CONFIRM_NO_PACKAGE_DEPLOY_WORKFLOW_SECRET_WRITE \
  --ack I_CONFIRM_REVOKE_IMMEDIATELY_AFTER_VALIDATION \
  --ack I_CONFIRM_READINESS_IS_NOT_AUTHORIZATION \
  --ack I_CONFIRM_NO_PRODUCTION_ROLLOUT_CANARY_ACTIVE_WRITE
```

## Stop the run at any time

```bash
export SAATHI_M39_KILL_SWITCH=1
```

## After the run

1. **Revoke the PAT externally** (GitHub → Developer settings → delete). Confirm it
   returns 401.
2. Record revocation and re-run leak scans.
3. Interpret the verdict:
   - `LIVE_CERTIFIED` — all stages passed against the real provider.
   - `LIVE_FAILED` — a stage failed; read the failing stage; do not retry blindly.
   - `LIVE_BLOCKED*` — a gate blocked (missing secret, kill switch, preflight).

## Rehearse first (no credential)

```bash
python -m saathi.credentials.cli m40-rehearsal   # SIMULATED_NOT_LIVE, safe
```

## What M40 will never do

Push git, merge, deploy, enable production/canary/active, create/destroy
infrastructure, rotate or store your credential. Revocation is your action; SaathiOS
only records your confirmation.

## Canary

M40 does not grant canary. Even a `LIVE_CERTIFIED` result only produces evidence; a
separate, explicit operator authorization (M39.3 approval record) remains mandatory.
