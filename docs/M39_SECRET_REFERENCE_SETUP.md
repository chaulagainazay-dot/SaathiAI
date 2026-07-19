# M39 — Secret Reference Setup

## Approved backends

| Kind | Locator meaning | Notes |
|------|-----------------|-------|
| `OS_KEYCHAIN_REFERENCE` | `service` or `service:account` | macOS Keychain via `security` |
| `ENV_REFERENCE` | Opaque locator; env **name** via `--env-var-name` | Never put the token in the locator |
| `ENCRYPTED_STORE_REFERENCE` | Operator-wired store | Requires operator wiring |

## Create a disposable GitHub sandbox PAT

1. Use a dedicated sandbox GitHub account where possible.
2. Grant **minimum** read-only scopes (e.g. public metadata / `read:user` only).
3. **No** repo write, org admin, billing, packages, workflows, secrets, deploy keys.
4. Store only in an approved backend — never in the repo or shell history.

### macOS Keychain example

```bash
# Interactive prompt stores the secret; it is not passed as a CLI flag value in SaathiOS.
security add-generic-password -a pat -s saathi-m39-github-sandbox -w
```

Locator for SaathiOS: `saathi-m39-github-sandbox:pat`

### Environment reference example

```bash
# Operator sets the env var in their shell/session manager (not committed).
# SaathiOS receives the NAME only.
export SAATHI_M39_SBX_PAT_REF_NAME=MY_DISPOSABLE_GITHUB_PAT_ENV
# (operator separately exports MY_DISPOSABLE_GITHUB_PAT_ENV with the value)
```

```bash
.venv/bin/python -m saathi.credentials m39-qualify-secret-reference \
  --source-kind ENV_REFERENCE \
  --locator m39_env_ref \
  --env-var-name MY_DISPOSABLE_GITHUB_PAT_ENV
```

## Rejected inputs

- Plaintext token as locator
- `--token` / `--api-key` / `--secret`
- Token in Markdown, JSON evidence, Git, logs

## After validation

Revoke the token in GitHub settings immediately, then:

```bash
.venv/bin/python -m saathi.credentials m39-confirm-external-revocation \
  --confirmed --note revoked_in_github_ui
```

SaathiOS does **not** gain token-deletion authority.
