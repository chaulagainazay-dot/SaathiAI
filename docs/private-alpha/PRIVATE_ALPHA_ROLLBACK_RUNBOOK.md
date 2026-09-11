# Private Alpha — Rollback Runbook

Rolling back a private alpha is cheap. Deciding late is expensive. When in doubt,
roll back and investigate afterwards — the testers lose an afternoon, not their
data.

---

## 1. Rollback triggers

Roll back immediately on any of these:

| Trigger | Why it is not negotiable |
| --- | --- |
| Any listener bound to `0.0.0.0` or `*:` | private alpha must never be publicly reachable |
| An approval was executed without a human decision | the human-in-the-loop guarantee is broken |
| A tester saw another tester's workspace or organization data | isolation failure |
| A session survived revocation | the owner has lost control of access |
| The audit trail is missing executions that occurred | evidence integrity is gone |
| A real credential was requested, accepted or stored | the credential boundary is broken |
| Any outbound request to a broker, exchange or provider | the connectivity boundary is broken |
| Database corruption or unrecoverable mission state | data integrity is gone |
| Runaway log, queue or database growth threatening the host | availability |

Roll back after discussion for: repeated mission failures, badly degraded
latency, or an alert storm with no clear cause.

## 2. Record both SHAs before touching anything

```bash
git -C <repo> rev-parse HEAD                       # CURRENT (bad) — full sha
git -C <repo> log --oneline -20                    # find the last good release
git -C <repo> rev-parse <previous-release-sha>     # PREVIOUS (target) — full sha
```

Write both full SHAs into the incident record now. You will need the current one
to reproduce the fault after service is restored.

## 3. Back up before rolling back — always

A rollback is a change. Never roll back an unbacked database.

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from saathi.platform.private_alpha.backup_restore import create_system_backup, verify_system_backup
b = create_system_backup(dest_dir=Path("data/backups/system"), label="pre-rollback",
                         db_path=Path("data/platform/platform.db"))
print(b["archive"])
print(verify_system_backup(b["archive"]))
PY
```

**Verify the backup before continuing.** An unverified backup is not a backup. If
verification fails, stop and treat it as a data-integrity incident.

## 4. Check database compatibility

Determine whether the previous release can read the current database.

- **No migration ran since the previous release** → the database is compatible.
  Proceed with a code-only rollback (step 6).
- **A migration ran** → decide between rollback and forward-fix:
  - a migration that only **added** tables or nullable columns is usually
    backward compatible; the previous code ignores what it does not know about,
  - a migration that **renamed, dropped or tightened** anything is not. Prefer a
    **forward fix** on the current SHA over restoring an older database, because
    restoring loses everything the testers did since the backup.

Record which path you chose and why.

## 5. Stop the application

```bash
bin/saathi-local stop
bin/saathi-local status     # confirm nothing is still listening
```

`stop` terminates only launcher-owned processes. If something is still on 8765 or
3000, it is not ours — find and stop it deliberately.

## 6. Roll the code back

```bash
git -C <repo> checkout <previous-release-full-sha>
git -C <repo> status --short          # must be empty
```

Do not force, reset hard, or clean. If the tree is dirty, stop and find out why
before destroying anything.

## 7. Migration rollback, or forward fix

**Code-only rollback (compatible database):** nothing to do here.

**Incompatible database, rolling back:** restore the pre-release backup.

```bash
.venv/bin/python - <<'PY'
from saathi.platform.private_alpha.backup_restore import dry_run_restore, restore_system_backup
archive = "<path to the pre-RELEASE backup, not the pre-rollback one>"
print(dry_run_restore(archive))     # inspect first — this touches nothing
# then, only if the dry run is clean:
print(restore_system_backup(archive))
PY
```

Always dry-run first. Tell the testers exactly what window of work was lost.

**Forward fix:** stay on the current SHA, fix the defect, and re-run the release
runbook from step 5. This is usually the better option once testers have real
data.

## 8. Reinstall dependencies for the target SHA

```bash
.venv/bin/pip install -e '.[dev]'
cd saathi-os && npm install && npm run build && cd -
```

## 9. Restart

```bash
bin/saathi-local start
bin/saathi-local status
```

## 10. Validate

```bash
.venv/bin/python -m saathi.ops release-gate
.venv/bin/python -c "from saathi.platform.private_alpha.journey import run_private_alpha_journey as j; print(j()['verdict'])"
bin/saathi-alpha doctor
```

Then confirm, specifically, that the condition which triggered the rollback is
gone. A rollback that restores service without confirming the trigger is
resolved is not finished.

## 11. Evidence

Record: both full SHAs, the trigger, who decided, the timestamps, whether a
restore ran, what data window was lost, the validation output, and the
follow-up owner.

## 12. Tell the testers

Send, in plain language:

- what went wrong, in one sentence, without jargon,
- whether any of their work was lost, and exactly which window,
- whether they need to do anything (usually: sign in again),
- when to expect the next build.

Do not minimise data loss. If a tester lost work, say so directly.

---

## What a rollback never does

- It never makes the system publicly reachable.
- It never enables broker connectivity, order execution or live trading.
- It never re-enables public registration.
- It never marks owner review as complete.
