**Production authorized: false.** Local-only private alpha.

# Private Alpha Backup & Restore

## Scope included

- PlatformStore (`platform.db`)
- Optional legacy app databases (no secrets)
- Redacted configuration
- Release manifest metadata
- Record-count summary
- Integrity hashes

## Scope excluded

- Raw secrets / API keys / tokens
- Unrestricted environment dumps
- Browser cookies / live credentials
- Unnecessary raw audio
- Unrelated filesystem content

## Commands

```bash
bin/saathi-alpha backup [label]
bin/saathi-alpha backups
bin/saathi-alpha verify-backup <archive>
bin/saathi-alpha restore-dry <archive>
bin/saathi-alpha restore <archive> --target /isolated/path
```

## Restore safety

- Default restore is **isolated** (never live data dir without explicit approval)
- Integrity validation required
- Wrong format version rejected
- Corrupted archives rejected
- Destructive overwrite requires:
  - `destructive_overwrite=True`
  - `approval_token=APPROVE_DESTRUCTIVE_RESTORE`
- Pre-restore checkpoint when target already has `platform.db`

## DR drill

```bash
bin/saathi-alpha dr-drill --work-dir data/alpha/dr-drill
```

Expected verdict: `PRIVATE_ALPHA_DR_DRILL_PASSED`
