# M248–M255 — Institutional Investment Intelligence & Portfolio Brain

**Terminal verdict:** `INSTITUTIONAL_INVESTMENT_INTELLIGENCE_CERTIFIED_WITH_LIMITATIONS`

**Maximum state:** `PAPER_INTELLIGENCE_ENGINE_READY`

---

## Authority boundary (immutable)

```text
PAPER ONLY
NO BROKER CONNECTIVITY
NO API KEYS
NO LIVE MARKET ACCESS
NO ORDER EXECUTION
NO LIVE TRADING
```

This milestone **does not** connect any broker. It transforms Trading Guardian into an institutional-quality portfolio intelligence engine for future broker connectivity.

Continuing from:

- M216–M223 Broker Sandbox
- M224–M231 Read-Only Broker Readiness
- M232–M239 Reproducibility & Supply Chain Assurance
- M240–M247 Provider Canary Planning (`PROVIDER_CANARY_PLANNING_CERTIFIED_WITH_LIMITATIONS`)

---

## Package layout

```text
saathi/platform/tg/intelligence/
  models.py              # authority locks, enums
  store.py               # SQLite decisions / runs / alerts
  strategy_registry.py   # M248
  portfolio_engine.py    # M249
  backtest_v2.py         # M250
  walk_forward_v2.py     # M251
  monte_carlo.py         # M252
  explainable.py         # M253
  committee.py           # M254
  security.py            # boundary guards
  service.py             # facade + M255 command center data
```

UI: `/trading/intelligence`  
API: `/api/v1/platform/tg/intelligence/*`  
CLI: `python -m saathi.platform.tg.cli strategy-list|strategy-run|portfolio-risk|portfolio-report|backtest-v2|monte-carlo|walk-forward|committee-review|explain|certify-intelligence`  
Also: `paper-gov ii-*` aliases.

---

## M248 — Strategy Registry

Structured strategies across 11 categories:

momentum · mean reversion · trend following · breakout · volatility · DCA · value · growth · swing · scalping · long-term investing

Each strategy records: id, category, description, markets/assets, indicators, entry/exit, stop/take-profit, sizing model, holding period, risk profile, confidence model, confirmations, limitations.

## M249 — Portfolio Intelligence

Paper portfolio metrics:

allocation · diversification · concentration · sector/geo/asset-class exposure · cash utilisation · realised/unrealised P/L · beta · volatility · Sharpe · Sortino · max drawdown · correlation · VaR · expected shortfall

## M250 — Backtesting Engine V2

Deterministic historical replay with transaction costs, slippage, commissions, liquidity participation, partial fills, capital limits, benchmark comparison, performance attribution.

Outputs: equity curve, drawdown curve, monthly/yearly returns, win rate, expectancy, profit factor.

## M251 — Walk-Forward Validation

Rolling windows with train/test separation. Parameter selection **only** on train. Never optimises on the evaluation set. Reports overfitting score, robustness score, confidence score.

## M252 — Monte Carlo Risk Engine

Seeded block-bootstrap simulations: sequence risk, probability of ruin, target return probability, worst-case paths, confidence intervals, recovery analysis. Same seed → same `evidence_hash`.

## M253 — Explainable Investment AI

Every recommendation includes: why, why now, supporting/conflicting evidence, assumptions, risks, confidence, historical behaviour, comparable situations, expected upside/downside, invalidation conditions.

## M254 — Investment Committee

Specialists: Macro, Technical, Fundamental, Quant, Risk Manager, Portfolio Manager.

Produces independent opinions, voting summary, agreements/disagreements, dissenting opinions, synthesised final recommendation + explanation.

## M255 — Portfolio Command Center

`/trading/intelligence` surfaces:

Strategy Library · Portfolio Overview · Risk Dashboard · Performance Dashboard · Backtests · Monte Carlo · Walk-Forward · Investment Committee · Explainable Recommendations · Historical Decisions · Confidence Trends · Watchlists · Alerts · Decision Timeline

**No** broker controls, credential controls, or connection controls.

---

## Success criteria

| Capability | Status |
|---|---|
| Sophisticated paper portfolios | ✓ |
| Compare multiple strategies | ✓ |
| Explain every recommendation | ✓ |
| Institutional risk metrics | ✓ |
| Monte Carlo futures | ✓ |
| Deterministic backtests | ✓ |
| Multi-agent committee | ✓ |
| Professional reports | ✓ |
| No broker integration required | ✓ |

---

## Limitations

- Synthetic/offline bars when historical datasets absent
- VaR/ES are research metrics, not regulatory capital
- Committee agents are deterministic specialists (not live LLM market feeds)
- Single-host SQLite intelligence store
- No claim of profitability or live readiness

---

## Evidence

- `docs/trading/m248_m255_evidence/`
- Tests: `tests/test_m248_m255_institutional_intelligence.py`
- UI unit: `saathi-os/lib/m248_intelligence.test.js`
- Browser cert: `npm run cert:m255` → `docs/trading/m248_m255_evidence/browser/`
