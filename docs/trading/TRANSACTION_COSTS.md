# M62.4 — Transaction Costs, Slippage & Fill Assumptions

All costs are `Decimal`. `execution_model.py`.

## Fill assumptions (conservative, documented)

* **Next-bar fill.** A signal on bar *i* fills on bar *i+1* — never same-bar.
* **MARKET** fills at the next bar's **open**, adjusted by slippage *against* the trader
  (buys pay up, sells receive less).
* **LIMIT** fills only if the next bar trades through the limit:
  BUY when `next.low <= limit` (fill `min(limit, open)`); SELL when `next.high >= limit`
  (fill `max(limit, open)`). Ambiguous intra-bar ordering resolves **conservatively** —
  never the favourable path. When a limit is not reached the order is **rejected**.
* **Volume participation** caps quantity to `max_volume_participation * bar.volume`;
  excess becomes a **partial** fill (illiquidity bites).
* Negative/zero quantity, or a limit price ≤ 0 → **rejected**.

## Cost model (`CostModel`)

| Field | Meaning |
|-------|---------|
| `fixed_fee` | flat per trade |
| `pct_fee` | fraction of notional (e.g. `0.0005` = 5 bp) |
| `per_unit_fee` | per-share/contract |
| `min_fee` | floor applied when any quantity trades |
| `slippage_bps` | fixed adverse slippage in basis points |
| `spread_slippage` | add a half-spread proxy from the bar range |
| `max_volume_participation` | liquidity cap vs bar volume |

Standard tiers: `ZERO_COST`, `REALISTIC_COST` (5 bp + $1 min + 5 bp slip + 10% vol cap),
`STRESSED_COST` (30 bp + $2 min + 50 bp slip + 5% vol cap).

## Cost inclusion

All costs flow into cash, realized P&L, total return, turnover, and trade statistics.
`fee_impact` and `slippage_impact` are reported metrics. Every certification strategy is
run at all three tiers; profitable-only-at-zero-cost is flagged (`BACKTEST_BIAS_CONTROLS.md`).
