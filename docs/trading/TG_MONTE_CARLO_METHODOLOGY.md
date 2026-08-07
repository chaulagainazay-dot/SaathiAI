# Monte Carlo methodology (M189)

## What it does

Resamples **observed trade returns** (or labeled metric-derived decomposition):

- trade-sequence shuffle
- block bootstrap
- return resample
- fee/slippage haircuts
- missed trade / delayed entry
- gap-through-stop amplification
- partial fill

## What it does not do

- Invent alternative real market price paths without labeling
- Authorize live trading
- Alone grant PAPER_ELIGIBLE (tail risk gates required)

## Bounds (8 GB class)

- Max simulations: 500 (default 200; cert paths often 40–100)
- Max trades consumed: 5000
- Deterministic seed

## Outputs

Median/p05/p95 return, median/worst DD, risk of ruin, daily/weekly loss-limit breach probabilities, loss-streak and recovery distributions, cost sensitivity.

## Verdicts

`STABLE` | `ACCEPTABLE_WITH_LIMITS` | `TAIL_RISK_HIGH` | `RISK_OF_RUIN_UNACCEPTABLE` | `INSUFFICIENT_TRADES` | `INSUFFICIENT_EVIDENCE`
