# M46 — Operator Guide

> Offline implementation only. Live canary requires a **later explicit** authorization.

## CLI

```bash
python -m saathi.credentials.cli m46-status
python -m saathi.credentials.cli m46-simulate
python -m saathi.credentials.cli m46-validate-approval --approval-file docs/m46/....local.json
python -m saathi.credentials.cli m46-create-plan --approval-file ... --request-file ... --snapshot-file ...
python -m saathi.credentials.cli m46-preflight --approval-file ... --request-file ... --snapshot-file ...
python -m saathi.credentials.cli m46-run-canary --mode simulate
# LIVE — only after separate authorization:
# export SAATHI_M46_LIVE_GATE=1
# python -m saathi.credentials.cli m46-run-canary --mode live --live-flag \
#   --approval-file ... --request-file ... --snapshot-file ... \
#   --secret-source-kind OS_KEYCHAIN_REFERENCE --secret-locator 'svc:acct' \
#   --expected-subject-fp ...
python -m saathi.credentials.cli m46-run-revocation --mode simulate
python -m saathi.credentials.cli m46-verify-cleanup
python -m saathi.credentials.cli m46-emit-evidence
```

## Manual prerequisites for a later live phase

1. Create a **fresh disposable read-only** provider credential.
2. Store only a **reference** (e.g. Keychain); never paste the secret into chat/CLI value flags beyond locator.
3. Fill `docs/m46/operator_canary_approval.template.json` → `*.local.json` (gitignored).
4. Sign approval integrity fingerprint via `sign_approval`.
5. Build M44 request + fresh M45 snapshot.
6. Preflight must pass; rollout_percent=1.
7. One-command live gate: `SAATHI_M46_LIVE_GATE=1` and `--live-flag`.
8. After canary: external revoke → live 401 → remove local ref → verify cleanup.

Success still grants **nothing**.
