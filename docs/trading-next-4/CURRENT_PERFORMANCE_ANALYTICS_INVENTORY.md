# CURRENT_PERFORMANCE_ANALYTICS_INVENTORY

| Component | Class | Notes |
| --- | --- | --- |
| portfolio_risk_engine/history NavHistoryStore | REUSE | NAV points for risk drawdown |
| portfolio_risk_engine/drawdown | REUSE | peak/current/max drawdown formula |
| fund_ledger ValuationSnapshot | CANONICAL source | Event-derived valuation |
| tg/portfolio_risk research analytics | RESEARCH_ONLY | M296 — not production books |
| strategy backtest stats | RESEARCH_ONLY | Not fund accounting |
| **portfolio_performance (T-NEXT-4)** | **CANONICAL** | History + contribution + Command contract |

No duplicate risk limit authority.
