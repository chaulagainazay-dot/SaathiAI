# Test Report

Starting commit: `13485618a7df776bbf2935c85597c6c020bf6696`.

Tests were written before the implementation. The first run failed collection
with `ModuleNotFoundError: saathi.platform.nepse.transactions`, proving the new
contract did not already exist.

## Focused results

```text
pytest -q tests/nepse/test_transaction_import.py
52 passed

pytest -q tests/nepse tests/market_data \
  tests/test_m184_m191_historical_research.py \
  tests/test_m256_m263_market_data.py \
  tests/test_m264_m271_recovery_historical.py \
  tests/test_m62_2_market_data.py
284 passed, 7 warnings

ledger + execution + guardian + construction + risk authority regression
327 passed, 14 warnings
```

The independent fresh-context pass found five defects. Each was reproduced by
a failing regression test before the fix:

1. Decimal magnitude/scale was unbounded.
2. Conflicting explicit `available_at` values could be called exact duplicates.
3. Formula-prefixed header cells normalized into legitimate headers.
4. Conflicting known type/description aliases used first-match semantics.
5. Invalid numeric rejection detail echoed raw untrusted cell content.

All five are fixed and the final 52-test transaction suite passes.

## Canonical offline regression

Pre-run storage: 14.4 GB free, `storage_report().healthy=True`.

```text
pytest tests -m "not browser and not live and not external and not network" -q
7844 passed, 8 skipped, 12 deselected, 324 warnings in 584.90s
```

Post-run storage: 11.3 GB free, healthy. No storage block occurred.

Python 3.12 compileall, mission-file whitespace validation, evidence JSON
parsing, and `git diff --check` are final handoff gates. Ruff is not installed
in the repository environment, so no Ruff result is claimed.
