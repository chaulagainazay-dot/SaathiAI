# TRADING_AND_FUND_READINESS

**Inspection tip:** `e1738d7deec5f44600fbf0d99e2b8f74a4bc83d0`  
**Authority preserved:** Trading Guardian fail-closed; live trading unauthorized; providers mock/disabled unless separately certified.

## Capability classification (code-backed)

| Capability | Classification | Evidence path |
| --- | --- | --- |
| Trading Guardian core | **implemented** (paper/research governance) | `saathi/platform/tg/` |
| Market data / observation | **implemented** (read-only / fixtures / observation services) | `market_observation/`, `market_data/` |
| Signal validation | **implemented** (research/validation packages) | M256–M263 lineage in tree |
| Historical data qualification | **implemented** (historical packages + evidence) | `tg/historical`, docs/trading evidence |
| Research agents / lab / orchestrator | **implemented** (research-only) | `research_lab/`, `research_orchestrator/` |
| Strategy / experiment registries | **implemented** | `tg/registry.py`, research models |
| Backtesting / walk-forward | **implemented** (deterministic research) | `walk_forward.py`, research lab |
| Transaction costs in sim | **partial / implemented in sim** | order_simulator fees/slippage |
| Portfolio ledger (paper/sim) | **implemented** (paper portfolio engine + paper_simulation ledger) | `paper_activation/portfolio_engine.py`, `paper_simulation/ledger.py` |
| Cash ledger / NAV / P&L | **implemented in paper/sim accounting** | `docs/trading/PORTFOLIO_ACCOUNTING.md`, accounting modules |
| Portfolio construction | **implemented** (research PortfolioBuilder / optimiser) | `research_lab/portfolio_builder.py` |
| Risk engine | **implemented** (multiple RiskEngine classes — TG + security) | `tg/risk.py`, portfolio_risk |
| Independent risk veto | **partial** — risk halt/lock paths on paper portfolio; not a separate legal-entity risk desk | `PaperPortfolioEngine.halt/lock` |
| Hedge optimizer | **research-only / partial** | research lab optimisation |
| Compliance layer | **governance-only / partial** | connectivity governance, approval policy denylists |
| Paper OMS | **implemented** (sim order lifecycle) | order_simulator + portfolio submit_order |
| Fill simulation | **implemented** | `OrderSimulator.try_fill` |
| Post-trade reconciliation | **implemented** (paper + broker_readiness recon engines) | reconciliation modules |
| Performance attribution | **partial** | analytics / trade_journal PortfolioAttribution |
| Broker sandbox emulator | **mock-only / architecture** | `broker_sandbox/` |
| Sandbox provider connectivity | **governance-only; not live-authorized** | connectivity_governance, provider_contracts |
| Live broker | **unimplemented / prohibited** | flags false |
| Kill switch | **implemented** | `tg/kill_switch.py` |
| Canonical fund accounting ledger (institutional multi-book) | **MISSING / partial** — paper/sim ledgers exist; not a full multi-entity fund admin ledger | — |
| Deterministic portfolio construction for live capital | **paper/research only** | — |
| Live trading authority | **false** | LOOP_STATE + production_readiness certification fields |

## Explicit separations (product truth)

```text
agent recommendation  → research agents / chat / orchestrators (non-authoritative)
deterministic calculation → portfolio engines, risk math, walk-forward, accounting invariants
governance authorization → approvals, connectivity governance, TG policy, kill switch
execution → PROHIBITED for live; paper OMS + simulator only
```

## What SaathiOS currently has vs lacks (hedge-fund bar)

| Fund bar item | Present? |
| --- | --- |
| Canonical fund accounting ledger | **No** (paper/sim only) |
| Deterministic portfolio construction | **Yes** (research/paper) |
| Deterministic risk calculation | **Yes** (engines present) |
| Independent risk veto | **Partial** |
| Paper OMS | **Yes** |
| Fill simulation | **Yes** |
| Post-trade reconciliation | **Yes** (paper/readiness) |
| Broker sandbox connectivity | **Architecture/mock; not authorized live** |
| Live trading authority | **No** |

## Next paper-only investment milestone (recommendation)

**T-NEXT-1 — Canonical paper fund ledger + single portfolio authority:**  
Collapse dual portfolio modules toward TG paper ledger as the sole accounting truth for UI and agents; expose NAV/P&L/cash invariants on command-center read models; no broker credentials; no live flags.

## Governance state (from private-alpha LOOP_STATE heritage)

All of: real connectivity, broker connectivity, OAuth, credential provisioning, order submission/execution, transfer/withdrawal, canary, live trading, automated investment authority = **false**.
