# TRADING_CONTRACT_ADAPTER_DECISION

## Decision

```text
FIXTURE_ADAPTER_MATCHING_CANONICAL_SCHEMA
```

## Why

- UI-NEXT-2.1 base is `design/ui-next-2-saathios-design-dna` (UI ancestry).
- T-NEXT-1/1.1/2 live under trading branches; **not** merged into design branch.
- Merging would pull runtime trading code into a design PR and violate separation.

## Pattern

1. `lib/design-lab/contracts.js` fixtures use **exact public keys** from:
   - `PortfolioLedgerService.command_center_summary` / `get_state`
   - `PortfolioRiskEngine.command_risk_contract`
2. `loadCommandReadModel({ preferLive })` ready for future REAL fetch; currently DEMO.
3. Display formatting only (`formatMoney` / `formatFraction`) — **no accounting/risk math**.

## Rejected

- Cherry-pick entire fund_ledger package into UI branch
- Frontend recomputation of NAV/P&L/risk

