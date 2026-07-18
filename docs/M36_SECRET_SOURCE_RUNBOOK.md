# M36 — Secret Source Runbook

## Allowed sources

- OS Keychain reference (preferred on macOS)
- Approved environment-variable reference (pre-declared names only)
- Approved encrypted local secret-store reference

## Never

Paste tokens into prompts, source, CLI args, git-tracked `.env`, tests, docs,
evidence, logs, or shell history.

## macOS Keychain template (placeholders only)

```bash
security add-generic-password \
  -a "<sandbox-account-alias>" \
  -s "saathios/m36/github-sandbox" \
  -w
```

The `-w` flag prompts securely; the secret does not appear in shell history.

## CLI

CLI accepts **secret reference / locator only**. Rejected flags:

`--token`, `--api-key`, `--password`, `--secret`, `--authorization-header`

## Retrieval gates

Retrieve only after: valid M36 authorization + valid lease + matching session +
matching provider/account. No fallback. No arbitrary environment scanning.
SecretHandle is zeroized on close. Never printed or serialized.
