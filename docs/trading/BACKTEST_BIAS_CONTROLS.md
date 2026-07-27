# M62.4 — Backtest Bias Controls

Bias-resistance is the point of this milestone. Controls, and how each is enforced.

## 1. Look-ahead prevention (structural)

At each decision the strategy sees only, via the guarded `BacktestContext`:

* bars ending at or before the current event timestamp,
* known instrument metadata,
* current simulated portfolio state,
* previous signals/features/fills.

Two independent guards:

1. **`FeatureSpec.forward_offset > 0` is rejected** before any run
   (`validation.validate_strategy` → `FUTURE_RETURN_FEATURE`). Features may only look
   *back*.
2. **Runtime instrumentation**: `BacktestContext.max_accessed_epoch` records the highest
   bar timestamp touched during a decision. After every decision the engine asserts
   `max_accessed_epoch <= decision_epoch`; any violation **rejects the run**.

A deliberately leaking fixture (`LOOK_AHEAD_STRATEGY`, via `future_peek`) is proven to
fail — see `docs/trading/m62_4_evidence/look_ahead_rejection.json`.

## 2. Next-bar fill (no same-bar hindsight)

A signal computed on bar *i*'s close fills on bar *i+1*'s open. You cannot trade on a
price you are simultaneously deciding at. See `TRANSACTION_COSTS.md`.

## 3. Data-leakage prevention (train/validation/test)

Splits are chronological, contiguous, and non-overlapping (`walk_forward`). Time series
are never shuffled — `make_chronological_splits` raises on unsorted input. TEST is
untouched until final evaluation; each fold records `selected_before_test`.

## 4. Out-of-sample (walk-forward)

Expanding/rolling folds; every fold records train/validation/test ranges, parameters,
trade count, dataset hash, strategy version, and status. Failed folds are surfaced, not
averaged away (`aggregate_folds`).

## 5. Overfit / single-trade dominance

`evaluate_backtest` flags `SINGLE_TRADE_DOMINANCE` when one trade exceeds 80% of gross
profit (`FAILED_BIAS_CHECK`). Parameter sensitivity flags cliff-edge dependence
(`UNSTABLE_PARAMETERS`).

## 6. Cost sensitivity

Every certification strategy is run at zero / realistic / stressed cost. A strategy
profitable only at low cost is flagged `cost_sensitive` (`COST_SENSITIVE`).

## 7. Statistical sufficiency

Minimum observations, trades, and out-of-sample duration; excessive drawdown;
concentration. Insufficient samples → `INSUFFICIENT_SAMPLE`, never a false PASS.

## Validation outcomes

`PASS_TECHNICAL`, `PASS_WITH_WARNINGS`, `INSUFFICIENT_SAMPLE`, `OVERFIT_SUSPECTED`,
`UNSTABLE_PARAMETERS`, `COST_SENSITIVE`, `EXCESSIVE_DRAWDOWN`, `DATA_QUALITY_FAILURE`,
`FAILED_BIAS_CHECK`. Profitability is **never** the pass criterion.
