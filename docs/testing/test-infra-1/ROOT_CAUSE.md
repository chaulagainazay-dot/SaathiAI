# Root Cause

## Classification

**`TEST_HANG_DB_LOCK`** — single primary cause. No secondary cause was needed to
explain the stall.

Explicitly **ruled out** by evidence, not assumption:

| Hypothesis | Ruled out by |
|---|---|
| `TEST_HANG_NETWORK_DEPENDENCY` | `lsof -nP -p <pid>` on the live stalled process showed **zero TCP/UDP sockets**. A direct `httpx` call to the configured `http://127.0.0.1:7130` fails in **0.05 s** with `ConnectionRefused`. |
| `TEST_HANG_BROWSER_DEPENDENCY` | No browser process was a child of the stalled interpreter; the stall reproduces from a two-test pair containing no browser code. |
| `TEST_HANG_SUBPROCESS_LEAK` | Only child was `multiprocessing.resource_tracker`, which is idle bookkeeping, not the blocker. Stack trace shows no subprocess wait. |
| `TEST_HANG_ASYNC_LEAK` | Faulthandler dump shows three plain OS threads, no event loop in any frame. |
| `TEST_HANG_ENVIRONMENT_DEPENDENCY` | Reproduces deterministically from a fixed two-test pair. |

## The stack that settles it

Captured with `pytest -o faulthandler_timeout=30` on the minimal pair:

```
Thread 0x00000001726a7000 (most recent call first):
  File "saathi/security/store.py", line 241 in __init__
  File "saathi/providers/insforge/migration.py", line 623 in _emit
  File "saathi/providers/insforge/migration.py", line 606 in _fail_exec
  File "saathi/providers/insforge/migration.py", line 312 in execute
  File "tests/test_m18_4_insforge_migration.py", line 373 in run
  ...threading.py 1012 in run

Thread 0x000000017169b000 (most recent call first):
  File "saathi/security/store.py", line 241 in __init__
  File "saathi/providers/insforge/migration.py", line 623 in _emit
  File "saathi/providers/insforge/migration.py", line 366 in execute
  File "tests/test_m18_4_insforge_migration.py", line 373 in run
  ...threading.py 1012 in run

Thread 0x00000001ed545e80 (most recent call first):
  File "threading.py", line 1169 in _wait_for_tstate_lock
  File "threading.py", line 1149 in join
  File "tests/test_m18_4_insforge_migration.py", line 378 in test_25_concurrent_claims_one_winner
```

Both worker threads are blocked at the *same* line. The main thread is blocked
in an unbounded `Thread.join()` waiting for them. Nothing times out.

## `saathi/security/store.py:241`

```python
self.db = sqlite3.connect(str(self.path), check_same_thread=False)   # 238
self.db.row_factory = sqlite3.Row                                    # 239
self.db.execute("PRAGMA foreign_keys = ON")                          # 240
self.db.executescript(_SCHEMA)                                       # 241  ← blocked here
```

Line 241 runs the **full schema DDL**. DDL requires an exclusive lock on the
database file.

## The mechanism, end to end

1. `SecurityStore()` with no `db_path` defaulted to **`Path.home() / ".saathi" / "security.db"`** — the operator's real home directory, shared by the entire test session.

2. Three audit call sites constructed a **brand-new `SecurityStore()` on every emit**, bypassing the module's own process-wide singleton `get_store()`:
   - `saathi/providers/insforge/migration.py:623`
   - `saathi/providers/insforge/provider.py:323`
   - `saathi/mcp_governance/events.py:72`

   Each construction opens a new connection *and re-executes the whole schema DDL*. None of them closed. `lsof` on the stalled process showed **25 open handles on `~/.saathi/security.db`**.

3. `tests/test_m15_1_api.py::test_execution_history_owner_scoped` drives `api.execute(...)`, which reaches that audit path and leaves a connection alive holding a lock on the shared file.

4. `tests/test_m18_4_insforge_migration.py::test_25_concurrent_claims_one_winner` then starts **two threads** that both call `svc.execute()`. Both reach `_emit` → `SecurityStore()` → `executescript(_SCHEMA)` → both block on the exclusive lock that is never released.

5. The test joins both threads with **no timeout**, so the deadlock is permanent and silent. Under `pytest -q` the output is buffered, so the suite simply appears to freeze at 32%.

## Order dependency

**Yes — strictly order-dependent.**

| Command | Result |
|---|---|
| `test_25` alone | passes, 0.15 s |
| `test_m18_4_insforge_migration.py` alone | 31 passed, 0.28 s |
| `test_m15_1_api.py` alone | 10 passed, 1.05 s |
| `test_m15_1_api::test_execution_history_owner_scoped` **+** `test_25` | **HANGS** |

The victim (`test_25`) and the trigger (`test_execution_history_owner_scoped`)
are both individually green. Only the pair deadlocks.

## Why it looked like a network hang

The InsForge tests are configured against `http://127.0.0.1:7130`, a port with
nothing listening, and the earlier partial work in the tree had begun adding an
`httpx.MockTransport`. That made a network explanation plausible. It was wrong:
the process held zero sockets while stalled, and the refused connection resolves
in 50 ms. The mission brief's warning — *"Do not assume network solely because
CPU is low"* — was correct.
