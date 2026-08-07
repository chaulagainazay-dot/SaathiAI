# Policy Gate and Risk Control Reference

## Policy engine (`saathi/platform/tg/policy.py`)

Versioned. Deterministic. Fail-closed on mandatory gate failure.

Each gate emits: name, PASS|FAIL|NOT_APPLICABLE, reason code, explanation, evidence, policy version, timestamp.

See `docs/trading/M166_M175_TRADING_GUARDIAN_FOUNDATION.md` for the full gate list.

## Risk engine (`saathi/platform/tg/risk.py`)

Position size:

```
qty = floor( (equity * max_risk_per_trade_pct/100) / stop_distance )
qty = min(qty, max_position_value/entry, cash/entry)
```

Rejects: invalid stop, size below minimum, fees/slippage destroying edge, R:R below policy, stale price, unreconciled portfolio, kill switch, daily/weekly loss, drawdown, consecutive losses, martingale/doubling, averaging down (unless explicitly approved).

Leverage, margin, withdrawals: always disabled.

## Kill switches

Scopes: GLOBAL, STRATEGY, INSTRUMENT, MARKET, WORKSPACE, PORTFOLIO, AUTOMATION, TRADING_GUARDIAN.

Activation is immediate, persistent, audited. Strategy/LLM/agent cannot activate or clear.
