# M62.4 — Stress & Sensitivity

`stress.py`. Uses the deterministic M62.2 fixture regimes — no external data.

## Stress regimes

`run_stress` runs the strategy against: `TRENDING`, `MEAN_REVERTING`, `FLAT`,
`HIGH_VOLATILITY`, `GAP_DOWN`, `ILLIQUID`, `FLASH_CRASH_LIKE`, `MISSING_BARS`,
`OUT_OF_ORDER_BARS`, `INVALID_OHLC`.

Expected behaviour (all proven — `docs/trading/m62_4_evidence/stress_results.json`):

* Invalid datasets (`INVALID_OHLC`) **block** the run (`REJECTED`).
* Out-of-order / duplicate bars are detected on the as-received order and block.
* Missing bars are **surfaced** as `GAPPED` in the quality summary.
* Illiquidity constrains fills (volume participation cap → partials).
* Flat market exposes unnecessary turnover.
* High volatility raises risk metrics.

Datasets are classified on the **as-received** order (before the engine's deterministic
sort) so ordering defects cannot be silently sorted away.

## Cost resilience

`cost_resilience` runs zero / realistic / stressed cost tiers. Flags:

* `zero_only` — realistic costs alone erase the edge (strictest),
* `cost_sensitive` — profitable at zero but not under stressed costs (fragile).

## Parameter sensitivity

`run_sensitivity` varies one parameter (the service varies the first feature's lookback)
across bounded neighbours and records the performance surface, trade count, drawdown, and
fees per point. A **cliff** — `|Δ total_return|` between adjacent points beyond a
threshold — sets `unstable=True`, feeding `UNSTABLE_PARAMETERS`. The engine does **not**
auto-select the best historical value without disclosure.
