# CURRENT_PORTFOLIO_STATE_INVENTORY

Classification of pre-existing portfolio-related components (ui-next-1 base).

| Component | Path | Class | Writer? | Notes |
| --- | --- | --- | --- | --- |
| Paper trading service | `saathi/platform/paper_trading/service.py` | **OPERATIONAL PAPER OMS** | Yes (paper orders/fills) | Decimal, long-only, TG+approval gated. Average-cost positions. |
| Paper store | `saathi/platform/paper_trading/store.py` | **DURABLE PAPER OMS** | Yes | SQLite accounts/positions/fills/ledger lines |
| Paper reconciliation | `saathi/platform/paper_trading/reconciliation.py` | DERIVED | No | Replays avg-cost from fills |
| Strategy accountant | `saathi/platform/strategy/accounting.py` | BACKTEST / DERIVED | In-memory sim | Average-cost; backtest only |
| TG portfolio | `saathi/platform/tg/portfolio.py` | LEGACY / EXPERIMENTAL | Unclear | TG-era portfolio helpers |
| Paper activation portfolio engine | `tg/paper_activation/portfolio_engine.py` | DUPLICATE / MILESTONE | Milestone-scoped | M192+ activation path |
| Intelligence portfolio engine | `tg/intelligence/portfolio_engine.py` | DERIVED / RESEARCH | Analytics | Not books & records |
| Portfolio risk package | `tg/portfolio_risk/*` | RISK / DERIVED | No | M296 risk intelligence — consume state, not own cash |
| Research lab portfolio builder | `tg/research_lab/portfolio_builder.py` | RESEARCH | Constructs proposals | Not ledger |
| saathi/portfolio.py | root | LEGACY | Mixed | Older portfolio module |
| portfolio_readonly package | `apps/packages/portfolio_readonly` | UI_ONLY / READ | No | Read surface |
| Paper UI pages | `saathi-os/app/trading/paper-*` | UI_ONLY | No | Display OMS/sim state |
| Central Command investment | `command-composition.js` | UI_ONLY | No | Was NOT AVAILABLE for P&L/exposure |
| **NEW fund_ledger** | `saathi/platform/fund_ledger/*` | **CANONICAL** | **Yes (sole books writer)** | FIFO lots, event-sourced, NAV/P&L |

## Competing authorities (pre T-NEXT-1)

Cash / positions / P&L appeared in:

1. Paper OMS store (avg-cost)
2. Strategy accountant (backtest)
3. Multiple TG portfolio engines
4. UI-derived displays

## Post T-NEXT-1 rule

```text
CANONICAL books & records writer = PortfolioLedgerService (fund_ledger)
Paper OMS = order/fill lifecycle authority (posts fills INTO ledger via bridge)
TG = permission/risk veto (does not own cash)
UI = projection of canonical APIs only
```

