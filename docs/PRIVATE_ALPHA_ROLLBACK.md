**Production authorized: false.** Local-only private alpha.

# Private Alpha Rollback

## Configuration

History snapshots under `data/alpha/config/history/`.

```python
from saathi.platform.private_alpha import rollback_config
rollback_config()
```

## Upgrade

Local fixture upgrades create a pre-upgrade system backup. On smoke failure,
`rollback_upgrade` restores config history and marks state rolled back.

## Restore

1. Prefer isolated restore + verification
2. Keep pre-restore checkpoint
3. Destructive live overwrite only with explicit approval token
4. On failed restore, restore the checkpoint and re-verify

## Services

```bash
bin/saathi-alpha stop
# fix config / restore backup
bin/saathi-alpha start
bin/saathi-alpha doctor
```
