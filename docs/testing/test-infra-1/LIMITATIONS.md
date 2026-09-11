# Limitations

## Fixed vs. isolated

The hang was **fixed**, not marked away. No test was skipped, no timeout was
padded, no assertion was weakened. `test_25_concurrent_claims_one_winner` keeps
its original unbounded `Thread.join()` and now completes in 0.02 s.

Markers were added only to tests that legitimately require a browser or an
external service. They deselect 12 of 7644 tests.

## Production code was changed

This was a test-infrastructure mission, but the defect lived in production code,
so four production files changed. All four are audit/telemetry plumbing. None is
in the trading plane.

| File | Change |
|---|---|
| `saathi/security/store.py` | added `SAATHI_SECURITY_DB` env override, consulted **only** when no `db_path` argument is given. Historical `~/.saathi/security.db` default unchanged. |
| `saathi/providers/insforge/migration.py` | audit emit uses `get_store()` instead of constructing `SecurityStore()` |
| `saathi/providers/insforge/provider.py` | same |
| `saathi/mcp_governance/events.py` | same |

The `get_store()` change is a switch to the module's own documented singleton.
Same database, same audit call, same recorded rows — one connection instead of
one per emit.

## Tests were writing to the operator's real security database

Before this mission, an unfiltered test session opened dozens of connections to
`~/.saathi/security.db` — the live store holding users, sessions, API tokens, and
the audit log — and wrote audit rows into it. That is a correctness and safety
problem independent of the hang, and it was almost certainly unnoticed.

It is now isolated by `conftest.py`. Anyone who has run this suite before should
assume their real security store contains test-generated audit rows.

## Not addressed

- **`saathi/connectors/platform/store.py:76`** opens SQLite with neither
  `check_same_thread=False` nor an explicit `timeout=`. Not implicated in this
  hang and not exercised across threads by any current test. Changing connection
  semantics on an unimplicated store would be unjustified scope. Technical debt.
- **Suite duration.** 11 minutes serial; 15 tests exceed 7 s, the slowest 18.3 s.
  No optimisation attempted.
- **Parallel execution.** `pytest-xdist` has not been validated. Given that the
  bug just fixed was cross-test contention on a shared SQLite file, parallelising
  before auditing every shared-path default would be premature.
- **`saathi-os` JavaScript tests.** Separate npm toolchain, `node_modules` not
  installed, out of scope.
- **Lint.** `ruff` is absent everywhere and unconfigured; `eslint` is configured
  but uninstalled. Nothing was installed, per the brief.

## Claims deliberately not made

- The brief's "two pre-existing syntax errors" **do not exist in this worktree**.
  `compileall` across the whole repository exits 0. They are not reported as
  fixed, because nothing was found to fix.
- The suite has been proven to complete **on this host, serially, with this
  interpreter**. It has not been run in CI, on Linux, or in a container.
