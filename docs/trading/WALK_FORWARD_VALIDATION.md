# M62.4 — Walk-Forward Validation

`walk_forward.py`. Time series are **never shuffled**.

## Splits

`make_chronological_splits(epochs, train, validation)` returns contiguous
`TRAIN < VALIDATION < TEST` ranges (half-open). `check_splits` detects overlap,
non-positive spans, and TEST-before-TRAIN. Unsorted input raises.

Rules enforced:

* non-overlapping time ranges,
* chronological ordering,
* no random shuffling,
* TEST untouched until final evaluation,
* each fold records `selected_before_test` so test metrics can be proven to post-date
  parameter selection.

## Folds

`build_folds(epochs, n_folds, mode, train_min, test_size)`:

* `mode="expanding"` — train window grows from the start.
* `mode="rolling"` — fixed-length train window slides forward.

Each `Fold` records train/validation/test ranges, parameters, dataset hash, strategy
version, trade count, metrics, and status (`OK | FAILED | EMPTY`).

## Aggregation

`aggregate_folds` reports `ok / failed / empty` counts, the worst test drawdown across
folds, average test return, and a `consistent` flag. **Failed folds are surfaced, never
averaged away** — a catastrophic period cannot be hidden behind an average.

The service wires the strategy's dataset through `_walk_forward`; results are persisted
under the run's `walk_forward` artifact and feed the `evaluate_backtest`
`walk_forward_consistent` input.
