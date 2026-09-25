# CURRENT_RISK_INVENTORY

| Component | Class | Role |
| --- | --- | --- |
| `trading_guardian.py` (M62) | **CANONICAL allow/deny** | Order-level veto; not full portfolio risk budgets |
| `tg/risk.py` (M170 RiskEngine) | REUSE / LEGACY TG path | Fixed-fractional + policy limits; parallel TG family |
| `tg/portfolio_risk/*` (M296) | RESEARCH_ONLY / DUPLICATE | Analytics, VaR, optimisers, float-heavy research |
| `strategy/sizing.py` | REUSE (backtest) | Backtest sizing only |
| `strategy/stress.py` | RESEARCH_ONLY | Sim stress |
| `paper_activation/risk_controls.py` | LEGACY | Activation-era |
| `paper_simulation/risk.py` | LEGACY | Sim UI |
| **`portfolio_risk_engine` (T-NEXT-2)** | **CANONICAL portfolio risk** | Budgets, drawdown, trade impact on ledger |

TG remains allow/deny authority. New engine does not own orders/fills/ledger.

