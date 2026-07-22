# Auto-Repair Security

## Non-negotiables

The loop never prints, stores, commits, or exposes: Hugging Face tokens, Gmail
OAuth tokens, Firebase admin keys, service-account keys, API keys, cookies,
refresh tokens, private SSH keys, passwords.

## Secret scanning (`saathi/repair/secrets_scan.py`)

Runs before every repair commit and on all evidence/reports. Patterns cover:
HF tokens, OpenAI/Google/Slack/AWS keys, GitHub PATs, JWTs, private-key blocks,
URL-embedded credentials, and generic `secret/password/token/api_key = "..."`
assignments. Template placeholders (`REPLACE_WITH`, `YOUR_`, `example`,
`REDACTED`, `<...>`, `sk-local`) are allow-listed to avoid false positives.

On match:
```
abort commit → mark SECURITY_ERROR → rollback → report file:line (never the value)
```

- `scan_text` / `scan_files` → hits with **line numbers only**.
- `redact` → replaces secret-looking substrings with `***redacted***`;
  applied to incident stack traces, logs, evidence free-text, and history rows
  on write.

## Evidence discipline

- Environment variables are recorded as **presence booleans** only
  (`HF_TOKEN_PRESENT=true`), never values.
- `RepairIncident.__post_init__` redacts stack traces + logs at construction.
- `RepairEvidence.sanitize()` redacts all free-text fields before storage.
- `RepairHistory.record()` redacts every string field before writing JSON.

## Git safety

- Never `push`, `force-push`, open a PR, merge, deploy, or rewrite history.
- Remote credential check: `git remote -v` must contain no `user:pass@` — the
  loop only creates local commits and rollback references.
- Rollback point recorded before any edit; unrelated dirty work blocks repair.

## Boundaries the loop will not cross

External-auth failures (`CONNECTOR_AUTH_ERROR`) are classified as manual setup —
never "repaired" by inventing fake connector data or rewriting working code.
Dependency upgrades, migrations, permission/policy changes, and anything Level 2+
require explicit human approval outside the automatic loop.
