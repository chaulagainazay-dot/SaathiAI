# M43 — Operator Guide (machine-verified bounded canary)

Run only with a **fresh disposable, read-only, sandbox** GitHub PAT and a **valid
filled M39.3 approval record**. Never paste a raw token.

## Prerequisites

1. A valid approval record JSON (fill `docs/m41/operator_canary_approval.template.json`;
   validate with `m39-3-validate-approval --record-file <file>` → `"valid": true`).
2. A fresh disposable read-only PAT stored as a Keychain reference (value entered at the
   TTY prompt, never in chat):
   `security add-generic-password -s saathi_m43 -a github_meta -w`

## Phase 1 — validation (live bounded read-only canary)

```bash
export SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION=1   # live window only
python -m saathi.credentials.cli m43-run-validation \
  --approval-file <approval.json> \
  --cert-file docs/evidence/m40/live_certification_record.json \
  --source-kind OS_KEYCHAIN_REFERENCE --locator saathi_m43:github_meta \
  --expected-subject-fp <account_subject_fingerprint> \
  --rollout-percent 1 --live-flag \
  --ack ...(10 M39 acks)
```
Expect `MACHINE_CANARY_VALIDATED_PENDING_REVOCATION`. (The agent captures the account
subject fingerprint on the first identity call, as in M40.)

## Phase 2 — revocation (live 401 proof)

Revoke the PAT externally at GitHub, then:

```bash
python -m saathi.credentials.cli m43-run-revocation \
  --source-kind OS_KEYCHAIN_REFERENCE --locator saathi_m43:github_meta \
  --expected-subject-fp <fingerprint> --live-flag --validation-passed \
  --ack ...(10 M39 acks)
```
Expect `MACHINE_CANARY_VERIFIED` (http 401 confirmed). The machine record is written to
`docs/evidence/m43/machine_verified_canary_completion.json`.

## Phase 3 — revalidate graduation

```bash
python -m saathi.credentials.cli m43-revalidate
```
With the machine record present, M42 should return `GRADUATION_RECOMMENDED` (advisory
only — grants nothing).

## Cleanup (mandatory)

`security delete-generic-password -s saathi_m43 -a github_meta` and confirm the PAT is
revoked (401). Kill switch any time: `export SAATHI_M39_KILL_SWITCH=1`.

## Rehearse first (no credential)

`python -m saathi.credentials.cli m43-rehearsal`
