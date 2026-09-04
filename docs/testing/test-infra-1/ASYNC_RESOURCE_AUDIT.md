# Async / Thread / Subprocess / SQLite Audit

## Async

`pyproject.toml` sets `asyncio_mode = "auto"` and
`asyncio_default_fixture_loop_scope = "function"` — a fresh loop per test, which
is the correct default and rules out cross-test loop reuse.

The faulthandler dump of the stalled process showed **three plain OS threads and
no event-loop frame anywhere**. No leaked asyncio task was involved.

## Threads

47 test files reference `threading`, `subprocess`, or an executor.

The one that mattered:

```python
# tests/test_m18_4_insforge_migration.py::test_25_concurrent_claims_one_winner
t1 = threading.Thread(target=run); t2 = threading.Thread(target=run)
t1.start(); t2.start()
t1.join(); t2.join()          # ← no timeout
```

The unbounded `join()` is what turned a recoverable lock wait into a permanent,
silent suite freeze.

**Deliberately not changed.** Adding `join(timeout=...)` would have converted the
deadlock into a passing test while leaving the real defect — a leaked SQLite
connection re-running schema DDL — in production code. The mission brief is
explicit: *"Do not hide real deadlocks by adding arbitrary sleep or huge timeout
values."* The underlying cause was fixed instead, and `test_25` now completes in
0.02 s with its original unbounded join intact.

## Subprocesses

The only child of the stalled interpreter was `multiprocessing.resource_tracker`
— standard bookkeeping, not a blocker. No orphaned `Popen`, no background daemon,
no temporary server was found holding the suite open.

## SQLite / file locks — the actual fault

| Store | Path | Problem |
|---|---|---|
| `SecurityStore` | **`~/.saathi/security.db`** (real home) | shared across the whole session; new connection **and full schema DDL** per audit emit; never closed. 25 handles observed on the stalled process. |
| `ConnectorStore` | `sqlite3.connect(path)` — no `check_same_thread`, no `timeout` | not implicated in this hang, noted below |
| `MigrationLedger` | own `threading.RLock` + one connection | correct; not implicated |
| paper trading / fund ledger stores | per-test `tmp_path` | correctly isolated |

Three call sites constructed `SecurityStore()` directly, bypassing the module's
own process-wide `get_store()` singleton:

- `saathi/providers/insforge/migration.py:623`
- `saathi/providers/insforge/provider.py:323`
- `saathi/mcp_governance/events.py:72`

All three now use `get_store()`. One connection, schema DDL once, no lock storm.

## Residual observation, not fixed

`saathi/connectors/platform/store.py:76` opens SQLite with neither
`check_same_thread=False` nor an explicit `timeout=`. It did not cause this hang
and no test currently exercises it across threads. Left alone deliberately —
changing connection semantics on a store that is not implicated would be
unjustified scope. Recorded in `LIMITATIONS.md` as technical debt.
