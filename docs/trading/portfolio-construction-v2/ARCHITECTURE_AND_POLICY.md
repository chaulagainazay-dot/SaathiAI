# PORTFOLIO-CONSTRUCTION-V2 architecture and frozen policy

## CURRENT_PORTFOLIO_CONSTRUCTION_CALL_GRAPH

```text
TradingSignal -> TradingIntentProposal
                         |
                         v
PortfolioConstructionEngine.construct_from_intents (proposal only)
                         |
                         +-> CandidatePortfolio (target weights; no orders)
                         |
                         +-> build_risk_handoff -> PortfolioRiskEngine
                                                   |
                                                   v
                                      compose_candidate_with_tg
                                                   |
                                                   v
                                           TradingGuardian
                                                   |
                                                   v
                                     Approval (unchanged downstream)
                                                   |
                                                   v
                                  ExecutionGateway (not reachable here)
                                                   |
                                                   v
                              OMS / adapter / Canonical Fund Ledger
```

The existing `PortfolioConstructionEngine` is retained as the sole allocation
authority. V2 adds a typed intent-driven method and target-only result contract; it
does not create a crypto, NEPSE, LLM, or TradingAgents allocator.

## Repository classification

| Component | Decision | Rationale |
|---|---|---|
| `PortfolioConstructionEngine` | ADAPT | Sole canonical allocator; add deterministic intent ingestion. |
| Existing equal/fixed/signal/risk-budget construction | KEEP | Existing callers and M-series behavior remain supported. |
| `ConstructionPolicy` | EXTEND | Reuse 15% position cap and 5% cash floor; add versioned sleeve, volatility, drawdown, correlation, liquidity, and eligibility settings. |
| `PortfolioProposal` | KEEP | Existing rebalance/approval contract remains compatible. |
| `CandidatePortfolio` | COMBINE | New target-only V2 view emitted by the same engine, above risk and approval. |
| Canonical Fund Ledger and `LedgerPortfolioViewAdapter` | KEEP | Books/cash authority; V2 consumes a typed immutable snapshot and never writes it. |
| `PortfolioRiskEngine` | KEEP | Hard risk owner; V2 emits a typed handoff and cannot mark risk approved. |
| `TradingGuardian` and composition helpers | ADAPT | Preserve veto; fail closed when Guardian evaluation is unavailable. |
| Approval and `ExecutionGateway` | KEEP | Unchanged and unreachable from construction. |
| TG research-lab optimiser/sizing utilities | DEFER | Parallel research utilities are not allocation authority. |
| CVXPY/PyPortfolioOpt/ML/Kelly/mean-variance allocator | REJECT | No need for unstable or heavyweight optimization. |

## Frozen construction policy

Policy version: `portfolio-construction/v2.0.0-configured-conservative`.
Hard-risk handoff version: `paper-risk-budget/v2-configured-conservative`.

Existing certified defaults retained:

- maximum instrument weight: 15% NAV;
- minimum cash: 5% NAV;
- maximum gross funded exposure: 100% NAV;
- minimum weight change: 0.5%;
- minimum rebalance notional: 100 units of the portfolio reporting currency;
- long-only, no leverage.

New values are `CONFIGURED_POLICY_ASSUMPTION`, not institutional verification:

- base eligible-candidate weight: 10% NAV, independent of signal strength,
  confidence, or strategy return;
- maximum crypto sleeve: 20% NAV;
- maximum NEPSE sleeve: 0% until a qualified strategy and verified cost policy exist;
- annualized volatility target: 20%, scaling down only and never levering up;
- volatility/correlation lookback: 90 returns, minimum 60 aligned observations;
- annualization: 365 for 24/7 crypto and 252 for NEPSE session data;
- drawdown factors: 1.00 below 5%, 0.75 from 5%, 0.50 from 10%, and zero new
  risk from 15%;
- high-correlation threshold: 0.75; correlated/unknown cluster cap: 15% NAV;
- missing liquidity evidence cap: 5% NAV rather than infinite capacity.

Only `PAPER_CANDIDATE` qualification evidence is eligible by default. Eligibility does
not guarantee positive allocation. Synthetic/unknown/stale data, expired or conflicting
intents, disabled instruments/venues, currency mismatch, missing volatility history,
cash/risk constraints, existing concentration, and severe drawdown may all produce zero
new allocation.

The current BTC mean-reversion qualification is evidence of eligibility only. Its
18.95% TEST return, signal strength, and research confidence are not policy inputs and
cannot become portfolio weight.
