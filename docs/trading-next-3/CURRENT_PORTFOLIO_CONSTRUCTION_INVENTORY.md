# CURRENT_PORTFOLIO_CONSTRUCTION_INVENTORY

## Scope
Inventory of portfolio allocation / sizing / rebalance / target-weight logic present at T-NEXT-3 base (`0507f2a`).

| Component | Path | Class | Notes |
| --- | --- | --- | --- |
| Research sizing | `tg/portfolio_risk/sizing.py` | RESEARCH_ONLY | equal-weight / inv-vol research helpers |
| Research optimiser | `tg/portfolio_risk/optimiser_v2.py` | RESEARCH_ONLY | M276/M296 wrapper; not proposal authority |
| Strategy sizing | `strategy/sizing.py` | REUSE (backtest) | Backtest position sizing only |
| Intelligence portfolio | agent/intelligence portfolio_engine | AGENTIC / RESEARCH | Narrative allocation; not canonical |
| Fund ledger | `saathi.platform.fund_ledger` | CANONICAL | What we own / cash / lots / NAV |
| Risk engine | `saathi.platform.portfolio_risk_engine` | CANONICAL | Risk budgets / breaches / projected trade risk |
| **Portfolio construction** | `saathi.platform.portfolio_construction` | **CANONICAL proposal** | Target + rebalance proposals only |

## Classification rules applied
- **REUSE**: keep as research/backtest; do not promote to proposal authority
- **CANONICAL**: sole production authority for its domain
- **RESEARCH_ONLY / AGENTIC**: may influence universe/signals via structured refs only
- **LEGACY / DUPLICATE**: none elevated in this milestone
- **DEFER**: mean-variance, risk parity, Black-Litterman, HRP, sector construction

## Decision
One proposal engine: `PortfolioConstructionEngine`. No duplication of ledger or hard-risk logic.

