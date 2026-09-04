# RISK_ENGINE_ARCHITECTURE

```text
Canonical Fund Ledger → Portfolio State
        ↓
PortfolioRiskEngine
  ├── RiskBudget (versioned)
  ├── metrics / drawdown / period PnL
  ├── evaluate_current_state
  ├── evaluate_proposed_trade
  ├── size_position / run_stress
  └── command_risk_contract
        ↓
RiskDecision → Trading Guardian compose → ALLOW/DENY
        ↓
Command Center (PAPER RISK)
```

Package: `saathi/platform/portfolio_risk_engine/`
No ledger mutation. No execution authority.

