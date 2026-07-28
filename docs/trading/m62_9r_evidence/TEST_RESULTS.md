# M62.9R Test Results

Environment: macOS (Darwin 25.5.0), Python 3.12.13, `.venv`, Next.js 15.1.6, single host, localhost.

## Full platform suite

```
python -m pytest tests/ -q
5182 passed, 1 skipped, 0 failed  in 798.45s (13m18s)
```

The 1 skip is an environment-gated non-trading test (`test_m17_*` — browser binary / sqlite+zip
dependency `skipif`), not a trading, safety, authority, or determinism test.

## Trading suites (per-file)

| Suite | Tests | Result |
|-------|------:|--------|
| test_m62_trading_models.py | 19 | pass |
| test_m62_2_market_data.py | 16 | pass |
| test_m62_3_research.py | 14 | pass |
| test_m62_4_strategy.py | 47 | pass |
| test_m62_5_paper_broker.py | 46 | pass |
| test_m62_6_reconciliation.py | 22 | pass |
| test_m62_7_safety.py | 41 | pass |
| test_m62_8_workspace.py | 4 | pass |
| test_m49_3_trading_boundary.py | 4 | pass |
| **Total trading** | **213** | **pass** |

## Runtime / Gateway / Authorization

```
test_agent_runtime.py + test_execution_gateway.py + test_m17_22_execution_gateway.py
+ test_m48_1_agent_runtime_contracts.py + test_m36_authorization_and_security.py
150 passed
```

## Bounded certification regression (all cert-relevant suites together)

```
382 passed  in 124.25s
```

## Key fault-injection tests (prior M62.9 blockers, now closed)

| Test | Proves | Result |
|------|--------|--------|
| `test_m62_7_safety.py::test_atomic_trip_rolls_back` | injected SQLite interruption mid-trip → full rollback, no partial halt, no orphan trip/alert, error surfaced | pass |
| `test_m62_6_reconciliation.py::test_interrupted_transaction_leaves_no_partial_state` | failed approval-consume rolls back → account still reconciles clean | pass |
| `test_m62_6_reconciliation.py::test_corrupted_fill_detected_and_halts` | tampered immutable fill → CRITICAL, account halts | pass |
| `test_m62_6_reconciliation.py::test_repair_plan_generated_but_never_executed` | corruption produces a plan but is never repaired | pass |
| `test_m62_2_market_data.py` (corrupted checkpoint, out-of-order, malformed) | fail-closed replay | pass |

## Determinism

| Test | Result |
|------|--------|
| `test_m62_4_strategy.py::test_deterministic_result_hash` (r1==r2==r3) | pass |
| `test_m62_2_market_data.py::test_replay_deterministic_and_controls` | pass |
| Long-duration sim financial outputs, 2 runs identical | pass |

## Frontend

```
saathi-os $ npm test          → 130 pass, 0 fail (node --test lib/*.test.js)
saathi-os $ npm run lint      → clean (eslint . --max-warnings 5)
saathi-os $ npm run build     → success (next build, exit 0)
```

## Hygiene

```
git diff --check   → clean (no whitespace errors)
```
