# Test Report

Starting verified baseline supplied by the operator:

- 7778 passed
- 2 skipped
- 12 deselected
- 0 failed

Pre-change semantic proof:

```text
2026-08-30 Sunday legacy=CLOSED canonical=OPEN
2026-08-31 Monday legacy=OPEN canonical=OPEN
2026-09-03 Thursday legacy=OPEN canonical=OPEN
2026-09-04 Friday legacy=OPEN canonical=CLOSED
2026-09-05 Saturday legacy=CLOSED canonical=CLOSED
```

Tests were written first. The first migration run failed during collection
because the new typed/versioned API did not yet exist. After implementation:

- `pytest -q tests/nepse/test_calendar_consumer_migration.py`: 15 passed.
- Existing calendar plus historical suites: 63 passed.
- Calendar, historical, market-data, strategy, recovery, paper-simulation, and
  canonical market-data focused group: 234 passed.
- Trading-authority regression: 270 passed.

The first focused group was accidentally invoked with Apple Python 3.9 and
reported two unrelated `hashlib.scrypt` failures. The repository runner is
`/opt/homebrew/bin/pytest` on Python 3.12; the identical group passed there.

Canonical offline regression:

```text
7787 passed
8 skipped
12 deselected
0 failed
324 warnings
576.30 seconds
```

The nine-pass increase over the starting baseline is the net of 15 new
migration tests and six additional environment skips. Those six are explained:
five PyObjC-native tests skipped because PyObjC is unavailable, and one guarded
live-Ollama test skipped because the listener/resource/live-opt-in safety
preconditions were not satisfied. The other two skips are the existing opt-in
slow render and unavailable `faster_whisper` tests. No calendar, historical,
market-data, backtest, or trading-authority test was skipped.

Post-regression validation also passed Python 3.12 compileall, `git diff
--check`, focused migration tests, evidence JSON parsing, and the refreshed
code-graph/static legacy-policy scan. Ruff was not installed in the repository
environment, so no Ruff result is claimed.

---

## Re-run after the fresh-context review fixes

The regression above was recorded before the three review fixes (R-A, R-C, R-D)
landed. It is superseded by the run below.

Six tests were added, each written before the fix it covers:

| Test | Covers |
|---|---|
| `test_nepse_instrument_cannot_bypass_the_calendar_gate_by_omitting_it` | R-A, the omission path |
| `test_nepse_instrument_with_an_explicitly_wrong_calendar_is_rejected` | R-A, explicit mismatch |
| `test_a_non_nepse_instrument_is_unaffected_by_the_new_guard` | R-A, no collateral damage |
| `test_confirmed_closed_session_bar_blocks_market_data_quality_not_just_scores_it` | R-C, blocking + escalation |
| `test_an_offsetless_timestamp_is_treated_as_utc_not_string_sliced` | R-D, +05:45 day boundary |
| `_OffsetlessStoreStub` fixture | R-D input construction |

Focused ladder on the final tree:

```text
tests/nepse                                             103 passed
+ market_data + historical research + paper simulation  217 passed
-k "strategy or backtest"                                67 passed  (7745 deselected)
trading authority regression (16 suites)                324 passed
```

Zero failures in calendar, NEPSE, historical, market-data, backtest, or
trading-authority tests.

## Canonical offline regression — ENVIRONMENT BLOCKED

```text
8 failed, 7790 passed, 2 skipped, 12 deselected in 545.74s
```

All eight failures are the host running out of disk, not defects:

```text
tests/test_m157_private_alpha.py::test_prepare_idempotent_and_no_secrets
tests/test_m157_private_alpha.py::test_init_with_platform
tests/test_m157_private_alpha.py::test_upgrade_preflight_and_local_fixture
tests/test_m157_private_alpha.py::test_private_alpha_certification_gate
tests/test_m336_m343_regression_closure.py::test_release_gate_reports_non_material_markers_instead_of_hiding_them
tests/test_ops.py::test_release_gate_passes_baseline
tests/test_studio_os.py::test_disk_preflight_passes_small_job
tests/test_studio_os.py::test_full_short_video_workflow_produces_real_artifacts
```

Proof, not assertion:

1. The host has ~2.9 GB free. `saathi/ops/storage.py` blocks below **5.0 GB**.
   `test_studio_os` fails with the threshold quoted verbatim:
   `InsufficientDisk: insufficient disk: 2.9GB free, job needs ~0.0GB, would
   breach the 5.0GB safety margin`.
2. `test_ops.py::test_release_gate_passes_baseline` fails `assert 9 in (0, 1)`
   — exit code 9 is `EXIT_STORAGE`.
3. The `KeyError: 'secret_scan'` in the M336–M343 test has the same root:
   `release_check` returns at the storage gate, before the secret-scan gate is
   ever added to the report. Reproduced deterministically by forcing
   `storage_report()['healthy'] = False`, which yields exit 9 and a report
   containing only `{'storage'}`.
4. All eight fail **in isolation in 9 seconds**, so this is not test-ordering
   or cross-test pollution.
5. None of the eight touches calendar, NEPSE, trading, market-data,
   historical, or backtest code. The intersection is empty.

Marker: `OFFLINE_REGRESSION_BLOCKED_HOST_DISK_BELOW_GATE_THRESHOLD`.

The regression must be re-run once the host has more than 5 GB free before the
offline suite can be claimed green again. The last clean full run on this tree
(before the three fixes) was `7787 passed, 0 failed`, and the three fixes touch
only `strategy/engine.py` and `tg/market_data/quality.py`, both covered by the
focused ladder above.
