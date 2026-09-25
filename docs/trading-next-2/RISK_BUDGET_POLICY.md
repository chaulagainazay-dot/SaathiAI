# RISK_BUDGET_POLICY

`paper-risk-budget/v1` (PAPER, conservative):

| Limit | Default |
| --- | --- |
| max_gross_exposure | 100% NAV |
| max_position_weight | 15% |
| max_top3 / top5 | 40% / 60% |
| min_cash_buffer | 5% |
| max_daily_loss | 3% |
| max_weekly_loss | 7% |
| max_drawdown | 15% |
| max_trade_notional | 10,000 |
| max_trade_risk_fraction | 1% NAV |

Leverage/shorts disabled. Timezone UTC. Agents cannot mutate budgets.

