# Hang Reproduction

## Verdict: `HANG_REPRODUCED`

Reproduced deterministically, then reduced to two tests, then fixed and verified.

## Original signature

```bash
pytest tests -q --no-header
```

- Progress stops at **32 %**
- CPU falls from ~78 % to **0.0–0.6 %** after roughly 3 minutes of CPU time
- Process never exits; no summary line is ever printed
- Under `-q` the stall point is invisible because progress dots are buffered

Attempted three times across the session. Two unfiltered runs stalled and were
killed; a third bounded run with `-k "not browser and not live and not network"`
also stalled.

## Diagnostics captured from the live stalled process

| Probe | Result |
|---|---|
| `lsof -nP -p <pid> \| grep -E "TCP\|UDP"` | **0 entries** — no sockets |
| child processes | one `multiprocessing.resource_tracker` (idle bookkeeping) |
| `ps -M -p <pid>` | 3 threads |
| open SQLite files | **25 handles on `/Users/macbookpro/.saathi/security.db`**, plus per-test tmp `ledger.sqlite` / `appr.db` |
| CPU | 0.0 % — blocked, not spinning |

The 25 handles on a single shared, real-home database were the first strong
signal, and they pointed at the right place.

## Making the stall point visible

`-q` buffers. Re-running unbuffered with `-v` printed the culprit directly:

```bash
python -u -m pytest tests -v --no-header -p no:cacheprovider
...
tests/test_m18_4_insforge_migration.py::test_24_duplicate_suppressed PASSED [ 32%]
tests/test_m18_4_insforge_migration.py::test_25_concurrent_claims_one_winner   ← started, never finished
```

An earlier attempt to identify the test from the newest `pytest-of-*` tmp
directory pointed at `test_26` and was **wrong** — leftover directories from a
previous run. The verbose run corrected it. Recorded here because the wrong
answer was briefly believed.

## Minimal reproduction (before fix)

```bash
pytest "tests/test_m15_1_api.py::test_execution_history_owner_scoped" \
       "tests/test_m18_4_insforge_migration.py::test_25_concurrent_claims_one_winner"
```

Two tests, each green in isolation, deadlocking together. See
`SUITE_PARTITION_LOG.md` for the narrowing steps.

## Stack capture

`pytest -o faulthandler_timeout=30` on the minimal pair produced the dump in
`ROOT_CAUSE.md`. The same option produced nothing on the full suite, which is why
partitioning had to come first — a useful thing to know for next time.

## Verification after fix

| Check | Before | After |
|---|---|---|
| minimal pair | hangs indefinitely | **2 passed, 0.28 s** |
| `test_25_concurrent_claims_one_winner` | never completes | **0.02 s** |
| `test_m18_4_insforge_migration.py` | 31 passed alone; hangs in suite | 31 passed in both |
| full `pytest tests` | stalls at 32 % | **7642 passed, 2 skipped, 667.63 s** |

An intermediate state is worth recording: after isolating the security DB to a
temp path but *before* fixing the connection leak, the pair completed in **33 s**
instead of hanging — `test_25` alone accounted for 32.88 s. That residual was the
same lock contention, merely survivable. It was not accepted as the fix; the leak
fix took it to 0.02 s.
