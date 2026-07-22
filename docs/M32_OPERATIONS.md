# M32 — Operations (CLI)

Module: `python -m saathi.connectors.providers <command>`

| Command | Purpose |
|---------|---------|
| `list` | List registered providers + simulator version. |
| `inspect <provider-id>` | Show identity + `m32_safe` flag. |
| `health <provider-id>` | Provider health probe. |
| `simulate <provider-id> <scenario>` | Run one deterministic scenario (SIMULATION). |
| `shadow <provider-id> <safe-operation>` | Run one SHADOW call; **refused unless the provider is M32-safe**; result marked non-authoritative. |
| `verify` | Explicit simulation verification of the pilot. |
| `drift` | Provider verification drift check (read-only report). |
| `quarantine <provider-id> --reason <safe-reason>` | Quarantine a provider. |
| `recover <provider-id>` | Explicit recovery from quarantine. |

## Safety

The CLI never prints secrets, authorization headers, cookies, raw credentials,
raw private provider payloads, or unsafe account identifiers. The `shadow` command
returns exit code 3 and refuses execution unless `registry.is_m32_safe(provider)`
is true (local/simulation, read-only, credential-free). Scenarios are validated
against the simulator's known set.

## Evidence

`scripts/m32_generate_evidence.py` exercises the governed path over the simulator
and writes leak-scanned, atomic, repository-relative evidence to
`docs/evidence/m32/`.
