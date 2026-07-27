# M62.4 — Portfolio Accounting

`accounting.py` — single source of truth for a backtest's cash, positions, P&L, fees,
equity curve, turnover, and drawdown. `Decimal` throughout. **Average-cost** lots.
**Long-only** (short-selling not authorized): a SELL never drives quantity below zero;
oversell is clamped.

## Tracked state

Cash ledger · position quantity + average cost · realized P&L · unrealized P&L · fees ·
equity curve (with running drawdown) · gross exposure · turnover.

## Reconciliation invariants

`check_invariants` asserts (and the test suite proves) after every run:

1. `ending_equity == cash + marked positions`
2. `cash == starting_cash − Σ buy_notional + Σ sell_notional − Σ fees`
3. `position_quantity == signed Σ fills` (clamped ≥ 0 for long-only)
4. `realized + unrealized − fees == equity_change` (no deposits)

Any violation marks the run **FAILED** and preserves the invariant errors as evidence.
See `docs/trading/m62_4_evidence/accounting_invariants.json` (all valid runs: `[]`).

## Final liquidation

At the last bar any open position is liquidated at the final close so terminal equity is
clean and comparable. The liquidation is a normal simulated fill (costs apply).
