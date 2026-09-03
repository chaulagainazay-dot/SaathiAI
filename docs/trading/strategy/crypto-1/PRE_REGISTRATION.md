# Pre-registration

This specification was fixed before any final-test return was evaluated. BTC and ETH are separate experiments; neither asset may select parameters from the other's final test.

## Common experiment policy

- Canonical instruments: `BINANCE:BTC/USDT`, `BINANCE:ETH/USDT`.
- Data: one immutable, hash-verified daily spot revision snapshot per instrument.
- Periods: first 60% of the immutable observation sequence is TRAIN; next 20% is VALIDATION; final 20% is untouched TEST. Timestamps are materialized in `StrategyEvaluationPlan` immediately after acquisition, before value evaluation.
- Walk-forward: two expanding, pre-final-test folds: `0–40 / 40–50 / 50–60%` and `0–60 / 60–70 / 70–80%` for train/validate/OOS.
- Benchmark: same-instrument spot buy-and-hold, selected before evaluation.
- Cost: `crypto-spot-v1`, 10 bps fee, 10 bps spread, 5 bps slippage; `CONFIGURED_CONSERVATIVE_ASSUMPTION`, not an account-specific Binance claim.
- Fill: `next-observation-open-v1`; signals on the last observation are unfilled.
- Starting simulation capital: 10,000 USDT; 95% maximum cash fraction; no borrowing, shorting, margin, or leverage.
- Selection rule: maximum VALIDATION net return, then excess return, then lower drawdown, then lower turnover, then configuration hash.
- Seed: 0. No seed search exists.
- Trial accounting: four initial parameter variants plus four variants in each of two walk-forward folds = exactly 12 trials per family × instrument; 72 for a complete BTC/ETH run.
- Multiple testing: `MULTIPLE_TESTING_LIMITED`; no statistical-significance assertion.

## Hypotheses and fixed grids

### `crypto_spot_trend_momentum` version `1.0.0`

Economic hypothesis: persistent spot trends may continue after fast/slow moving-average alignment and bounded multi-period return confirmation.

Features: close, fast SMA, slow SMA, multi-period return.

Variants: `(fast, slow, momentum, threshold)` = `(5,20,10,0)`, `(5,20,10,0.01)`, `(10,40,20,0)`, `(10,40,20,0.01)`.

### `crypto_spot_breakout` version `1.0.0`

Economic hypothesis: a close above a fully prior spot range may continue when execution occurs only at the next observation.

Features: close, prior high, prior low. The decision bar never defines its own breakout boundary.

Variants: `(entry lookback, confirmation, exit lookback)` = `(20,0,10)`, `(20,0.005,10)`, `(55,0,20)`, `(55,0.005,20)`.

### `crypto_spot_mean_reversion` version `1.0.0`

Economic hypothesis: a bounded negative deviation from a prior close average may revert only after same-bar reversal confirmation. A drop alone is insufficient.

Features: open, close, prior close average, deviation.

Variants: `(lookback, entry deviation, exit deviation)` = `(10,0.03,0)`, `(10,0.05,0)`, `(20,0.03,0)`, `(20,0.05,0)`.

## Pre-registered rejection conditions

`OOS_FAILED`, `COSTS_ERASE_EDGE`, `WALK_FORWARD_UNSTABLE`, `EXCESS_DRAWDOWN`, `TOO_FEW_TRADES`, `HIGH_SELECTION_RISK`, `REGIME_DEPENDENT`, `BENCHMARK_UNDERPERFORMANCE`, and `INSUFFICIENT_DATA`.

Changing a hypothesis, family, grid, benchmark, cost/fill model, or selection rule creates a new experiment. A spent TEST window cannot become unbiased again after a configuration change.
