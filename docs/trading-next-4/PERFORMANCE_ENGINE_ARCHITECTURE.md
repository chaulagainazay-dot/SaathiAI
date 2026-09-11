# PERFORMANCE_ENGINE_ARCHITECTURE

```
PortfolioLedgerService → observations → PortfolioPerformanceEngine
  → NAV / returns / P&L / drawdown history / POSITION_CONTRIBUTION
  → Command paper_performance contract
```

Read/derived only. Zero mutation of cash, positions, risk, proposals, orders.
