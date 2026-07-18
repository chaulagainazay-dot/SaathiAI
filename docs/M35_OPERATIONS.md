# M35 — Operations

All commands are offline, metadata-only, and never accept a raw secret as a
positional or flag value. Every command prints the banner:

```
SANDBOX GOVERNANCE
NON-PRODUCTION
NO LIVE SECRET LOADED
NO EXTERNAL CALL
NO WRITE AUTHORITY
ROLLOUT REMAINS OFF
```

## CLI (`python -m saathi.credentials`)

| Command | Purpose |
|---------|---------|
| `m35-verify` | run the deterministic synthetic sandbox-governance session; print sanitized result + certification + validation summary |
| `m35-drift` | print the deterministic M35 governance fingerprint |
| `m35-scope-policy` | print allowed/forbidden scope classes |
| `m35-secret-source-policy` | print retrievable/prohibited secret sources |
| `emit-m35-evidence` | regenerate `docs/evidence/m35/` via the offline generator |

The existing M31 commands (`status`, `readiness`, `profiles`, `list-credentials`,
`list-links`, `inspect-credential`, `inspect-link`, `demo`, `emit-evidence`,
`verify`) are unchanged.

## Evidence generator

```
.venv/bin/python scripts/m35_generate_evidence.py
```

Offline, synthetic fixtures only, no network, no keychain, no real environment
secret, deterministic, leak-scanned, atomic, repository-relative paths. Writes 22
files to `docs/evidence/m35/`.

## What operators cannot do via M35

Load a production or real sandbox credential, connect an account, run OAuth, make a
live provider call, perform a write, activate CANARY/ACTIVE, or engage the Trading
Guardian. A real sandbox session requires a separate, explicit future operator
authorization.
