# M45 — Rollback Guide

## Operational rollback

M45 does not execute rollouts. There is nothing to operationally roll back in
production traffic.

Snapshot lifecycle actions:

```bash
python -m saathi.credentials.cli m45-expire-snapshot <id>
python -m saathi.credentials.cli m45-invalidate-snapshot <id> --reason ...
```

## Code rollback

M45 is additive. To remove:

```bash
git rm -r docs/evidence/m45 docs/M45_*.md
git rm saathi/credentials/m45.py tests/test_m45_runtime_attestation.py
# revert m45 block in saathi/credentials/cli.py
```

No M31–M44 source is required to change for pure removal. Historical evidence
under `docs/evidence/m39`–`m44` is untouched by M45.

## Safety

Invalidating snapshots does not revoke provider credentials (none are held by
M45). Credential lifecycle remains under M39–M43.1 procedures.
