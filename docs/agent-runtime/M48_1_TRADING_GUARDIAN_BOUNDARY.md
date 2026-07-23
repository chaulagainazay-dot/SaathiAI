# M48.1 — Trading Guardian Boundary

## State

```text
TRADING_GUARDIAN_UNENGAGED_ADVISORY_ONLY
```

Agent runtime **must not** engage live trading.

## Allowed (future, gated)

market data read · strategy/risk analysis · paper simulation · backtesting · trade **proposal** · approval request · evidence

## Prohibited (contract-enforced)

live orders · broker auth · exchange mutation · withdrawals · leverage enablement · approval bypass · autonomous financial execution

`AuthorityClass.FINANCIAL_EXECUTION` and capabilities `trade_execute` / `broker_order` / `withdraw` are **PROHIBITED** in `contracts.py`.

## UI

`/trading` remains advisory-only (M47). No agent path may auto-enable execution.
