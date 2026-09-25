# READ_CONTRACT_INVENTORY

| Surface | Source | Authority | Freshness | Availability on design branch | Fallback | UI label |
| --- | --- | --- | --- | --- | --- | --- |
| paper_nav, cash, positions, P&L, exposure | PortfolioLedgerService | Ledger | event-time | Not shipped on UI-NEXT-2 base | DEMO fixture exact schema | Portfolio |
| portfolio_status / recon | T-NEXT-1.1 recon | Ledger cutover | post-fill | Adapter only | DEMO recon scenarios | Recon strip |
| risk_status, budgets, stress, drawdown | PortfolioRiskEngine | Risk engine | snapshot | Not shipped on base | DEMO fixture exact schema | PAPER RISK |
| VoiceSession states | voice runtime / command-authority mapper | Voice | session | Partial (mapper exists) | READY + cycle | Voice |
| Approvals | approvals APIs | Approvals | poll | Not wired in lab | DEMO list RO | Approvals |
| Missions/agents | mission/agent reads | Runtime | poll | Not wired | DEMO topology | Agents |
| Evidence | audit feeds | Audit | append | Not wired | DEMO causal chain | Evidence |
| System health | monitoring/overview | Ops | poll | Partial production command | DEMO strip | Status |

Every lab field carries provenance: REAL | DERIVED_FROM_REAL | DEMO | UNAVAILABLE.

