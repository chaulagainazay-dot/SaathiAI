# PORTFOLIO_CONSTRUCTION_ARCHITECTURE

```
Research / Strategy Inputs
        │
        ▼
PortfolioConstructionEngine  (proposal only)
        │
        ▼
Target Portfolio → Rebalance Proposal
     │                    │
     ▼                    ▼
Projected Ledger     PortfolioRiskEngine
     └────────┬───────────┘
              ▼
       Proposal Package
              │
              ▼
   Trading Guardian composition (read)
              │
              ▼
      Approval handoff payload
              │
              ▼
   (future) PAPER execution — NOT in this engine
```

## Ownership
| Domain | Owner |
| --- | --- |
| what we own | PortfolioLedgerService |
| what risk exists | PortfolioRiskEngine |
| what portfolio is proposed | PortfolioConstructionEngine |
| whether action allowed | Trading Guardian |
| whether approved | Approval system |
| external action | ExecutionGateway |

## API
- `construct_target(...)`
- `build_rebalance_proposal(...)` (alias)
- `validate_proposal(...)`
- `approval_handoff_payload(...)`
- `command_proposal_contract(...)`
- `attention_hints(...)`

**Forbidden:** `execute()`, `submit_order()`, `set_position()`, ledger mutation, TG override.

