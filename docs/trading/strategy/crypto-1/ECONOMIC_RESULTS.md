# STRATEGY-CRYPTO-1 economic results

The unchanged preregistration was executed once against certified real Binance Spot
daily bars. Returns and drawdowns below are decimal fractions, not percentages. The
benchmark is same-instrument unlevered spot buy-and-hold, selected before TEST.

| Strategy | Instrument | Trials | TRAIN net | VALIDATION net | TEST gross | TEST net | Benchmark | Excess | Max DD | Volatility | Turnover | Trades | Cost drag | Hit rate | Avg hold |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Trend/momentum | BTC/USDT | 12 | 4.480953 | 1.093510 | 0.272828 | 0.237632 | 0.264937 | -0.027306 | 0.260522 | 0.281641 | 17.598111 | 8 | 0.035197 | 0.375000 | 37.375000 |
| Breakout | BTC/USDT | 12 | 5.169695 | 0.830825 | 0.049126 | 0.011570 | 0.264937 | -0.253367 | 0.283458 | 0.268470 | 18.777824 | 9 | 0.037556 | 0.333333 | 28.555556 |
| Mean reversion | BTC/USDT | 12 | -0.686831 | 0.707503 | 0.241245 | 0.189532 | 0.264937 | -0.075406 | 0.190792 | 0.242631 | 25.856210 | 12 | 0.051713 | 0.666667 | 11.916667 |
| Trend/momentum | ETH/USDT | 12 | 15.647061 | 0.460571 | 0.639758 | 0.608776 | -0.207404 | 0.816180 | 0.336853 | 0.425965 | 15.490527 | 8 | 0.030982 | 0.375000 | 31.750000 |
| Breakout | ETH/USDT | 12 | 2.757277 | 0.532464 | 0.698625 | 0.684436 | -0.207404 | 0.891840 | 0.182771 | 0.348521 | 7.093885 | 3 | 0.014189 | 1.000000 | 53.333333 |
| Mean reversion | ETH/USDT | 12 | -0.861714 | 0.617627 | 0.411998 | 0.333949 | -0.207404 | 0.541353 | 0.350479 | 0.408296 | 39.024826 | 17 | 0.078049 | 0.647059 | 13.000000 |

## Locked configurations and decisions

| Strategy | Instrument | Locked configuration | Walk-forward net returns | Worst OOS | Decision | Explicit limitations/rejection reasons |
|---|---|---|---|---:|---|---|
| Trend/momentum | BTC/USDT | fast 10, slow 40, momentum 20, threshold 0 | -0.303069, 0.700129 | -0.303069 | OOS_VALIDATED_WITH_LIMITATIONS | WALK_FORWARD_UNSTABLE; BENCHMARK_UNDERPERFORMANCE |
| Breakout | BTC/USDT | lookback 20, exit 10, confirmation 0 | -0.305956, 0.688515 | -0.305956 | OOS_VALIDATED_WITH_LIMITATIONS | COSTS_ERASE_EDGE; WALK_FORWARD_UNSTABLE; BENCHMARK_UNDERPERFORMANCE; REGIME_DEPENDENT |
| Mean reversion | BTC/USDT | lookback 20, entry deviation 0.03, exit deviation 0 | 0.024278, 0.309792 | 0.024278 | PAPER_CANDIDATE | BENCHMARK_UNDERPERFORMANCE |
| Trend/momentum | ETH/USDT | fast 10, slow 40, momentum 20, threshold 0 | -0.127068, 0.621510 | -0.127068 | OOS_VALIDATED_WITH_LIMITATIONS | WALK_FORWARD_UNSTABLE |
| Breakout | ETH/USDT | lookback 55, exit 20, confirmation 0 | -0.062843, 0.721993 | -0.062843 | OOS_VALIDATED_WITH_LIMITATIONS | WALK_FORWARD_UNSTABLE; only 3 TEST trades |
| Mean reversion | ETH/USDT | lookback 20, entry deviation 0.03, exit deviation 0 | -0.454575, 0.284181 | -0.454575 | REJECTED | WALK_FORWARD_UNSTABLE; EXCESS_DRAWDOWN |

BTC mean reversion is the only paper candidate. Its positive final TEST net return,
positive net return in both pre-TEST walk-forward segments, 12 TEST trades, lower
drawdown than its benchmark, and survival under all cost/stress cases meet the frozen
bar. It is not claimed to beat BTC buy-and-hold: final TEST excess return was
`-0.0754055326`, and its TRAIN net return was negative. That adverse evidence remains
part of the qualification.

## Cost sensitivity and stress

The BTC mean-reversion candidate returned `0.1895318557` at base costs,
`0.1627012681` at 2x fees, `0.1760397411` at 2x spread, and `0.1760397411` at 2x
slippage. Delayed fill, missing-observation, liquidity-degradation, and observed
volatility-spike scenarios produced net returns of `0.1901431515`, `0.3903883075`,
`0.1627013145`, and `0.1895318557`, respectively. These are deterministic scenario
results, not probability-weighted forecasts.

Trailing-only regime labels did not use future observations. Candidate mean return was
negative in downtrends (`-0.0008210032`), positive in ranges (`0.0013605722`), high
volatility (`0.0009622603`), and low volatility (`0.0000503540`), and zero in the
uptrend bucket. This analysis did not alter parameters.

The exact machine-readable metrics, scenario assumptions, fills, and period returns
are retained in the immutable local qualification artifact identified by SHA-256
`45a115c978047e228c769d05cbef48e5d1a59070c94f4706dc2903f561bccd40`.
No result asserts statistical significance.
