# Kotegawa-inspired Mean Reversion — Assumptions and Limitations

## Nature of the strategy

This is an **interpretation inspired by publicly discussed principles** associated with
mean-reversion / panic-buying narratives around Takashi Kotegawa. It is **not** an
exact reproduction of any private method, proprietary system, or claimed historical
trade sequence.

## Required confirmation (non-negotiable)

A signal is emitted only when **all** of the following hold:

1. Price deviation below a short-term moving average exceeds threshold.
2. Volume is abnormally elevated vs its recent average.
3. Reversal confirmation is present (green bar by default — halt of free-fall alone is insufficient when `reversal_require_green=True`).
4. Liquidity and spread strategy-level checks pass.

**The strategy must not buy solely because price has fallen.**

## Declared assumptions

- Liquid instruments with short-term mean-reverting behavior.
- Long-only paper simulation; no leverage.
- Event / earnings windows should be blocked by policy.
- Historical edge may decay.

## Invalidation

- Breakdown below volatility-normalized stop without reversal.
- Liquidity collapse or wide spread.
- Event-risk or earnings-window flags.
- Persistent BEAR_TREND without exhaustion confirmation.

## Limitations

- Simulated fills ≠ real execution.
- Past performance ≠ future results.
- No profitability claim.
- Paper trading only; no live authorization.
