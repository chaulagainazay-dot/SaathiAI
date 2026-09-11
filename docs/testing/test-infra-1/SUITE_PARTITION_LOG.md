# Suite Partition Log

Deterministic narrowing from 387 test files to a two-test reproduction. Every
step recorded, including the ones that pointed the wrong way.

Collection order captured once and reused so every partition is reproducible:

```
pytest tests --collect-only -q | grep '^tests/' | sed 's/::.*//' | awk '!seen[$0]++'
→ 387 files;  tests/test_m18_4_insforge_migration.py is file #151
```

## Step 0 — establish the victim

| Run | Result |
|---|---|
| `pytest tests -q` (unfiltered) | stalls at **32%**, 0.1 % CPU after ~3 min CPU time |
| `pytest tests -v` (unbuffered) | last line printed: `test_m18_4_insforge_migration.py::test_25_concurrent_claims_one_winner` — **started, never completed** |

Verbose mode was essential: under `-q` the progress dots are buffered and the
stall point is invisible.

## Step 1 — the victim is innocent in isolation

| Run | Result |
|---|---|
| `test_m18_4_insforge_migration.py` alone | **31 passed in 0.28 s** |
| `test_25_concurrent_claims_one_winner` alone | **1 passed in 0.15 s** |
| `test_m18_3` + `test_m18_4` | **59 passed in 0.35 s** |

A false lead was recorded here and then discarded: an early bounded run showed
`test_15` taking 18.4 s, which suggested slow network. A later clean run of the
same file took 0.51 s total. The 18 s was one-off process warm-up, not the fault.

## Step 2 — binary search over the 150 preceding files

| Partition | Files | Result |
|---|---|---|
| 1–150 + m18_4 | 151 | **HANGS** (3:06 CPU then 0.6 %) |
| 1–75 + m18_4 | 76 | 1059 passed, 1 skipped, **17.77 s** |
| 76–150 + m18_4 | 76 | **HANGS** (reached 95 %, killed at deadline) |
| 76–112 + m18_4 | 38 | **HANGS** (reached 86 %) |
| 76–93 + m18_4 | 19 | 160 passed, 1 skipped, **8.88 s** |
| 94–103 + m18_4 | 11 | **HANGS** (reached 82 %) |

Poisoner confined to files 94–103.

## Step 3 — linear scan of the 10 candidates

Each paired with `test_25` alone, 100 s bound:

| File | Result |
|---|---|
| `test_llm_execution.py` | 36 passed, 0.36 s |
| `test_m103_fleet_runtime.py` | 58 passed, 4.48 s |
| `test_m112_skill_runtime.py` | 48 passed, 3.10 s |
| `test_m121_app_runtime.py` | 48 passed, 2.99 s |
| `test_m130_hcg_operations.py` | 47 passed, 1.09 s |
| `test_m139_ielts_productization.py` | 42 passed, 1.12 s |
| `test_m148_core_os.py` | 39 passed, 1.84 s |
| `test_m157_private_alpha.py` | 47 passed, 9.10 s |
| **`test_m15_1_api.py`** | **HANGS** |
| **`test_m15_1_integration.py`** | **HANGS** |

Both `m15_1` files trigger it; they exercise the same connector-execute path.

## Step 4 — narrow within the file

Per-test pairing against `test_25` isolated a single trigger:

```
tests/test_m15_1_api.py::test_execution_history_owner_scoped   *** HANGS ***
```

## Step 5 — minimal reproduction

```bash
pytest "tests/test_m15_1_api.py::test_execution_history_owner_scoped" \
       "tests/test_m18_4_insforge_migration.py::test_25_concurrent_claims_one_winner"
```

Two tests. Both green individually. Together: permanent deadlock.

A rejected hypothesis is recorded here too — `from saathi.server import app`
(the other notable thing `test_m15_1_api.py` does) was tested as a standalone
poisoner and **did not** reproduce the hang.

## Step 6 — stack capture

With the reproduction down to two tests, `-o faulthandler_timeout=30` produced a
usable dump. It had failed on the full suite, which is why the partition work had
to come first. See `ROOT_CAUSE.md`.

## Step 7 — verification after fix

| Run | Before | After |
|---|---|---|
| minimal pair | hangs forever | **2 passed, 0.28 s** |
| `test_25` duration | never completes | **0.02 s** |
| full `pytest tests` | stalls at 32 % | **7642 passed, 2 skipped, 667.63 s** |
