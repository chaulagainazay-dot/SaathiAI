# Qualification and stress policy

Every candidate reports gross return, net return, same-asset benchmark return, excess return, maximum drawdown, annualized volatility, turnover, completed round-trip trade count, direct cost drag, hit rate when defined, average holding period when defined, and every walk-forward OOS segment.

A `PAPER_CANDIDATE` requires a non-synthetic real/replay dataset snapshot, non-failing net/benchmark-relative OOS evidence, drawdown no greater than 35%, at least three completed trades, both bounded walk-forward OOS folds positive, no cost-erased edge, no stress fragility, exact visible trial count, and no PIT violation. Benchmark underperformance remains visible even when other behavior is useful. No sole metric or statistical-significance claim promotes a candidate.

Cost sensitivity is fixed to base costs, 2× fees only, 2× spread only, and 2× slippage only. Operational stress is fixed to a two-observation delay, removal of every seventeenth test observation, one-tenth liquidity participation with doubled spread/slippage, and observed high-volatility regimes labelled using trailing data only. The volatility review uses observed regimes instead of inventing an extreme price path.

Qualification states are limited to `REJECTED`, `RESEARCH_ONLY`, `OOS_VALIDATED_WITH_LIMITATIONS`, and `PAPER_CANDIDATE`. There is no `LIVE_READY` state.
