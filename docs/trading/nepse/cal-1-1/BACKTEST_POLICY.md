# Backtest Policy

The selected policy for certified NEPSE backtests is
`REQUIRE_CALENDAR_COVERAGE`.

Rules:

- Every date used by the run must resolve through the supplied canonical
  `NepseCalendar`.
- Any `POTENTIAL_OPEN_HOLIDAY_UNKNOWN` or `UNKNOWN` date rejects the dataset with
  `NEPSE_CALENDAR_COVERAGE_REQUIRED`.
- A bar on a `CONFIRMED_CLOSED` date rejects the dataset with
  `NEPSE_CONFIRMED_CLOSED_SESSION_BAR`.
- Covered years use confirmed calendar truth, including sourced holidays.
- No Monday-Friday fallback, holiday inference, or row skipping is allowed.

The direct strategy engine writes calendar version/source/coverage/policy into
its deterministic manifest. Historical research checks the imported manifest
before conversion, regime segmentation, walk-forward, stress, Monte Carlo, or
fills. It also propagates the same calendar into downstream strategy runs.

`SKIP_UNKNOWN_SESSION` is deliberately not the certification default. It could
change the sample without a fully justified point-in-time policy.
