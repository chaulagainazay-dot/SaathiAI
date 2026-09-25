# MD-1.1 Test Report

Tests were written before implementation. The first collection run failed for
the missing identity module. A later fresh-pass compatibility run found and
fixed frozen-event mutation and synthetic-venue handling; each received a
regression test.

- MD-1.1 identity tests: **15 passed**.
- NEPSE, MD-1, historical, and market-data suites: **274 passed**.
- Fund-ledger and trading-authority regression: **328 passed**.

The canonical offline suite completed before the final alias regression with
**7858 passed, 8 skipped, 12 deselected, 0 failed**. Storage was 10.9 GB before
that run and 7.8 GB after. A post-fix rerun was not started because storage was
below the 10 GB preferred floor: `OFFLINE_REGRESSION_BLOCKED_STORAGE`. The
repository hard block is 5 GB. No live, network, broker, or production
execution was enabled.
