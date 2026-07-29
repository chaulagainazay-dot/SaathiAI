# M192–M199 — Paper Activation Governance

**Terminal verdict:** `PAPER_ACTIVATION_GOVERNANCE_CERTIFIED_WITH_LIMITATIONS`

**Date:** 2026-07-29

## Authority

| Claim | Status |
| --- | --- |
| Paper only | YES |
| Live trading authorized | **NO** |
| Broker credentials | NO |
| Exchange connected | NO |
| Production authorized | NO |
| LLM may approve/execute | NO |
| Owner sign-off | Automated browser only — not human owner sign-off |

## Flow

```
Historical Research → Qualification → Owner Approval → PAPER_ACTIVE
  → Paper Orders → Paper Portfolio → Risk Monitoring
  → Analytics → Journal → Reconciliation → Evidence
```

## Activation rules

`PAPER_ACTIVE` requires:

1. `PAPER_ELIGIBLE` qualification verdict  
2. Authoritative non-fixture historical dataset  
3. Walk-forward + stress + Monte Carlo complete  
4. Acceptable risk of ruin  
5. Realistic fees/slippage  
6. Owner human approval (single-use, reason required)  

Everything else remains `RESEARCH_ONLY` / non-active.

## Modules

`saathi/platform/tg/paper_activation/`

| Module | Role |
| --- | --- |
| models | Portfolio, orders, positions, approvals, risk limits |
| activation | PAPER_ACTIVE gating |
| approvals | Owner approval center |
| portfolio_engine | Multi-portfolio cash fund simulator |
| order_simulator | Market/limit/stop/IOC/FOK, partial fills, gaps |
| risk_controls | Daily/weekly loss, exposure, circuit breaker |
| reconciliation | Fail-closed consistency |
| analytics | Sharpe/Sortino/Calmar/win rate/… |
| journal | Immutable trade journal |
| service | Governance facade |

Composes over M62 `paper_trading`, TG risk/kill-switch, historical qualification — does not replace them.

## API

`/tg/paper/posture`, `/status`, `/portfolios`, `/approvals/*`, `/activate`, `/orders`, `/tick`, `/analytics`, `/journal`, `/reconcile`, `/kill-switch`

## CLI

`python -m saathi.platform.tg paper-gov {status,create,portfolio,approve,reject,activate,orders,positions,analytics,reconcile,stop,kill}`

## UI

`/trading/paper-portfolio`, `paper-orders`, `paper-journal`, `paper-risk`, `paper-approvals`, `paper-analytics`, `paper-reconcile`

## Safety

- Long-only cash execution (margin/leverage fields are **display labels only**)  
- Kill switch halts all paper portfolios  
- Unreconciled → fail closed  
- Journal immutable  
- No broker APIs, no private exchange endpoints, no secrets  

## Limitations

- Process-local governance store (not multi-process durable)  
- Average hold time not claimed without full round-trip timing  
- Soft browser journeys may gate on auth  
- Not a profitability or live-readiness claim  
