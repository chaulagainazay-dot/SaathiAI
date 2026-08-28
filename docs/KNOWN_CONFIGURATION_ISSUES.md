# Known configuration issues (unresolved)

Recorded here so they are not rediscovered as bugs. Nothing in this file is
fixed by the commit that created it.

## `SAATHI_DOTENV_FILE` is set by launchers and read by nothing

The isolated R2.1 validation backend (and any launcher copied from it) exports
`SAATHI_DOTENV_FILE`. That name appears nowhere in the source tree. The dotenv
policy reads two other names (`saathi/dotenv_policy.py`):

* `SAATHI_LOAD_DOTENV` — falsey disables loading entirely;
* `SAATHI_DOTENV_PATH` — an absolute path that overrides the default target.

Containment is not currently at risk: the same launcher also sets
`SAATHI_LOAD_DOTENV=false`, so `apply_dotenv()` returns `disabled` and the
worktree `.env` is never read. The defect is that the *intent* expressed by
`SAATHI_DOTENV_FILE` is silently ignored — a launcher that dropped the
`SAATHI_LOAD_DOTENV=false` line while keeping `SAATHI_DOTENV_FILE` would
believe it had redirected dotenv while actually loading the worktree file.

Fix direction, when someone takes it: rename the variable in the launchers to
`SAATHI_DOTENV_PATH`, or have `dotenv_policy` refuse to start when an unknown
`SAATHI_DOTENV_*` name is present. Not attempted here — it touches process
startup, and this repair is scoped to one status field.
